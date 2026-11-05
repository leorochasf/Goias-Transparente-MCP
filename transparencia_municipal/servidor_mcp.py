"""Servidor MCP: deixa um assistente de IA consultar o Portal da Transparência de um município.

Rodar:  python -m transparencia_municipal.servidor_mcp
Config: TRANSPARENCIA_PORTAL (portal padrão), TRANSPARENCIA_NAVEGADOR=1 (ver README, "O 403").
"""
from __future__ import annotations

import math
import os
import sys

import anyio
from mcp.server.mcpserver import Context, MCPServer

from . import catalogo, tcm
from .cliente import AVISO_DETALHE, AVISO_DIARIAS, FONTE, ErroPortal, Portal, marcas_em_texto
from .folha_leve import AGRUPAMENTOS, filtrar, linha_leve, resumir
from .plataformas import _host
from .tcm import ClienteTCM

mcp = MCPServer("goias-transparente",
                instructions="Consulta dados públicos do Portal da Transparência de municípios de Goiás: folha de pagamento, empenhos, contratos, licitações, receitas, diárias e legislação. "
                             "Plataformas: NucleoGov, Megasoft (embutida no NucleoGov ou de domínio próprio, esta com o detalhe do servidor), contabilidade Centi e câmaras Ortrel; o que um sistema não publica é recusado com aviso. "
                             "Do TCM-GO, os processos de contas (eSiproc) e os acórdãos desde 2020 (TCMJuris).")

AVISO = ("Dado público do Portal da Transparência do município (Lei 12.527/2011), lido na hora. "
         "Confira no portal antes de usar em peça, denúncia ou matéria.")


def _endereco(url=None):
    endereco = url or os.getenv("TRANSPARENCIA_PORTAL")
    if not endereco:
        raise ValueError("Informe o portal (ex.: https://acessoainformacao.cidade.go.gov.br; use encontrar_portal "
                         "para achá-lo pelo município) ou defina TRANSPARENCIA_PORTAL.")
    return endereco


def _portal(url=None):
    """Portal pronto para consulta, com os sufixos e a plataforma do catálogo. O caminho de cada módulo o Portal decide.

    A plataforma do catálogo só vale no endereço do próprio portal: os outros endereços do órgão (o site da câmara,
    a API) não são o portal.
    """
    endereco = _endereco(url)
    orgao = catalogo.por_portal(endereco)
    sufixos = dict(orgao["sufixos"]) if orgao and orgao.get("sufixos") else None
    plataforma = orgao.get("plataforma") if orgao and _host(orgao["portal"]) == _host(endereco) else None
    return Portal(endereco, navegador=os.getenv("TRANSPARENCIA_NAVEGADOR") == "1", sufixos=sufixos,
                  plataforma=plataforma)


def _situacao(url=None):
    try:
        orgao = catalogo.por_portal(_endereco(url))
    except ValueError:
        return None
    return catalogo.situacao(orgao) if orgao else "portal fora do catálogo de Goiás: não conferido"


#: leitura do mês: (portal, ano, mês) → linhas leves. Só na memória, enquanto o servidor estiver aberto.
_LEITURAS: dict[tuple[str, int, int], list[dict]] = {}
#: as ressalvas que o encaixe deu na leitura do mês (Ortrel, Megasoft), para repetir em cada resposta sobre ela
_RESSALVAS: dict[tuple[str, int, int], list[str]] = {}


def _ler_mes(portal, ano, mes, progresso=None):
    """A folha inteira do mês, em linhas leves. Guarda só a leitura completa; falha não fica guardada."""
    chave = (portal.url, int(ano), int(mes))
    if chave in _LEITURAS:
        return _LEITURAS[chave]
    andamento = {"lidas": 0, "total": 0}

    def ao_ler(lidas, total):
        andamento.update(lidas=lidas, total=total)
        if progresso:
            progresso(lidas, total)

    quando = f"{int(mes):02d}/{ano}"
    try:
        r = portal.folha(ano, mes, maximo=sys.maxsize, progresso=ao_ler)
    except ErroPortal as e:
        raise ErroPortal(f"a leitura da folha de {quando} parou em {andamento['lidas']} de "
                         f"{andamento['total']} linhas: {e}") from e
    if r["total"] == 0:
        raise ValueError(f"o portal não tem folha de {quando}")
    if len(r["registros"]) != r["total"]:
        raise ErroPortal(f"a leitura da folha de {quando} veio incompleta: {len(r['registros'])} de "
                         f"{r['total']} linhas. Nada foi guardado; tente de novo.")
    linhas = r["registros"] + _orgaos_escondidos(portal, ano, mes, r, quando)
    _RESSALVAS[chave] = list(r.get("ressalvas") or [])
    _LEITURAS[chave] = [linha_leve(x) for x in linhas]
    return _LEITURAS[chave]


def _ressalvas_do_mes(portal, ano, mes):
    ressalvas = _RESSALVAS.get((portal.url, int(ano), int(mes)))
    return {"ressalvas": ressalvas} if ressalvas else {}


ORGAOS_SONDADOS = range(1, 16)


def _orgaos_escondidos(portal, ano, mes, sem_filtro, quando):
    """Linhas dos órgãos que a folha sem filtro não traz.

    Em 6 de 10 prefeituras conferidas em 04/11/2026 a folha sem filtro trazia só um órgão (Trindade: o 3;
    com filtro apareciam 5, 6, 7, 8 e 10). Sonda os códigos 1 a 15 que não vieram e lê os que têm linhas.
    Só no NucleoGov: linhas traduzidas de outro sistema trazem outra `fonte` e não são sondadas.
    """
    if any(x.get("fonte", FONTE) != FONTE for x in sem_filtro["registros"]):
        return []
    vistos = {str(x.get("orgao_id")) for x in sem_filtro["registros"] if x.get("orgao_id") is not None}
    if not vistos:
        return []
    largura = len(next(iter(vistos)))
    acao = f"servidores_{(portal.sufixos or {}).get('servidores', 'frl')}/listar"
    extras = []
    for n in ORGAOS_SONDADOS:
        codigo = str(n).zfill(largura)
        if codigo in vistos:
            continue
        filtros = {"ano": str(ano), "mes": str(int(mes)), "orgao": codigo}
        total = portal.consultar(acao, filtros, maximo=1)["total"]
        if total == sem_filtro["total"]:
            return []  # o portal ignora o filtro de órgão: o que veio sem filtro é tudo o que há
        if total:
            r = portal.consultar(acao, filtros, maximo=sys.maxsize)
            if len(r["registros"]) != r["total"]:
                raise ErroPortal(f"a leitura do órgão {codigo} na folha de {quando} veio incompleta: "
                                 f"{len(r['registros'])} de {r['total']} linhas. Nada foi guardado.")
            extras += [{**x, "fonte": FONTE} for x in r["registros"]]
    return extras


def _resposta(dados, portal=None):
    situacao = _situacao(portal)
    return {**dados, "aviso": AVISO, **({"situacao_do_portal": situacao} if situacao else {})}


def _executar(funcao, portal=None, *, maximo=None, avisos=None):
    """Consulta a um portal. Com `maximo`, as marcas do encaixe viram texto (`marcas_em_texto`). `avisos` fixos vão
    em toda resposta, inclusive na de erro."""
    try:
        r = funcao()
        if maximo is not None:
            r = {**r, **marcas_em_texto(r, maximo)}
        return {**_resposta(r, portal), **(avisos or {})}
    except (ErroPortal, ValueError) as e:
        return {"erro": str(e), **(avisos or {})}


def _aviso_orgaos(r, quais):
    """Megasoft e Centi trazem a Câmara e os fundos junto com a Prefeitura: o campo `orgao` diz de quem é cada um.

    Os contratos dão o nome em `orgao_nome` (`orgao` é o código). `somas_por_orgao` (Centi) conta os órgãos com
    linhas no mês inteiro, não só nos registros cortados por `maximo`.
    """
    if r.get("somas_por_orgao"):
        orgaos = {s.get("orgao") for s in r["somas_por_orgao"] if s.get("linhas")}
    else:
        orgaos = {x.get("orgao_nome") or x.get("orgao") for x in r["registros"]} - {None, ""}
    if len(orgaos) > 1:
        r["aviso_orgaos"] = (f"{quais} incluem mais de um órgão ({len(orgaos)}: por exemplo, Câmara e fundos junto "
                             "com a Prefeitura); confira o campo orgao de cada um")
    return r


RUBRICAS_ATE = 10   # na consulta por nome, rubricas só até este número de linhas
LISTA_MAXIMA = 300


def _mes(mes):
    if not 1 <= int(mes) <= 12:
        raise ValueError(f"mes: use um número de 1 a 12 (recebido: {mes!r})")
    return int(mes)


async def _ler_mes_avisando(ctx, portal, ano, mes):
    """Leitura do mês numa thread, com aviso de progresso ao assistente a cada página."""
    def progresso(lidas, total):
        paginas = max(1, math.ceil(total / portal.por_pagina))
        pagina = math.ceil(lidas / portal.por_pagina)
        anyio.from_thread.run(ctx.report_progress, lidas, total,
                              f"página {pagina} de {paginas} da folha de {mes:02d}/{ano}")
    return await anyio.to_thread.run_sync(lambda: _ler_mes(portal, ano, mes, progresso))


@mcp.tool()
def consultar_folha(ano: int, mes: int, busca: str | None = None,
                    portal: str | None = None, maximo: int = 100) -> dict:
    """Linhas da folha de um mês, buscando pelo NOME do servidor (a busca do portal não acha cargo).

    Rápida. Ex.: quanto ganhou Fulano de Tal em março e de quê. Com até 10 linhas, cada uma traz as
    rubricas (proventos e descontos). Quem recebe salário e 13º no mesmo mês tem duas linhas; na folha da
    Megasoft (linhas com fonte "Megasoft"), não: a listagem não traz o 13º e vem sem rubricas.
    Para cargo, lotação ou vínculo use listar_folha; para contagens e custos, resumir_folha.
    """
    def consultar():
        consultado = _portal(portal)
        r = consultado.folha(ano, _mes(mes), busca, maximo=maximo)
        # linha traduzida de outro sistema sem as listas de rubricas (Megasoft); o Ortrel as traz
        sem_rubricas = [x for x in r["registros"] if x.get("fonte", FONTE) != FONTE
                        and "lista_proventos" not in x and "lista_descontos" not in x]
        com_rubricas = len(r["registros"]) <= RUBRICAS_ATE and not sem_rubricas
        saida = {"total": r["total"], "linhas": [linha_leve(x, rubricas=com_rubricas) for x in r["registros"]],
                 **marcas_em_texto(r, maximo), **({"ressalvas": r["ressalvas"]} if r.get("ressalvas") else {})}
        orgao = catalogo.por_portal(consultado.url) or {}
        if ((orgao.get("conferencia") or {}).get("filtros") or {}).get("folha_orgaos") == "falhou":
            saida["aviso_orgaos"] = ("neste portal a folha sem filtro esconde órgãos (conferência): a busca por nome "
                                     "pode não achar quem está neles. Para não perder ninguém, use "
                                     "listar_folha(ano, mes, nome=...), que lê o mês inteiro.")
        if sem_rubricas:
            saida["aviso_rubricas"] = (f"a folha deste portal vem da {sem_rubricas[0]['fonte']}, cuja listagem não traz "
                                       "rubricas: só bruto, descontos e líquido de cada linha.")
        elif not com_rubricas:
            saida["aviso_rubricas"] = (f"mais de {RUBRICAS_ATE} linhas: as rubricas não vieram. "
                                       "Refine a busca pelo nome para ver as rubricas de uma pessoa.")
        return saida
    return _executar(consultar, portal)


@mcp.tool()
async def listar_folha(ano: int, mes: int, cargo: str | None = None, lotacao: str | None = None,
                       vinculo: str | None = None, tipo_pagamento: str | None = None, nome: str | None = None,
                       portal: str | None = None, maximo: int = 100, ctx: Context = None) -> dict:
    """Linhas da folha do mês filtradas por cargo, lotação, vínculo ou tipo de pagamento, com nomes.

    Ex.: quem são os comissionados da Secretaria de Saúde. Filtro "contém", sem distinguir maiúscula
    nem acento (vinculo="comissionado" pega todas as variantes); filtros se somam. `nome` também filtra,
    alcançando órgãos que a busca rápida de consultar_folha pode não ver. tipo_pagamento:
    "mensal", "13" ou "rescis". Lê o mês inteiro do portal: na primeira vez pode levar ~10 minutos
    (avisa o progresso); depois o mesmo mês sai na hora. Até 300 linhas; `encontradas` diz quantas
    casaram. Dado de pessoa: use para apuração, não para montar dossiê.
    """
    try:
        consultado = _portal(portal)
        linhas = await _ler_mes_avisando(ctx, consultado, ano, _mes(mes))
        achadas = filtrar(linhas, cargo=cargo, lotacao=lotacao, vinculo=vinculo, tipo_pagamento=tipo_pagamento,
                          nome=nome)
        limite = max(1, min(maximo, LISTA_MAXIMA))
        saida = {"total_do_mes": len(linhas), "encontradas": len(achadas), "linhas": achadas[:limite],
                 **_ressalvas_do_mes(consultado, ano, mes)}
        if len(achadas) > limite:
            saida["aviso_corte"] = (f"mostrando {limite} de {len(achadas)} linhas; refine o filtro "
                                    "ou use resumir_folha para contagens e somas")
        return _resposta(saida, portal)
    except (ErroPortal, ValueError) as e:
        return {"erro": str(e)}


@mcp.tool()
async def resumir_folha(ano: int, mes: int, agrupar_por: str = "lotacao", cargo: str | None = None,
                        lotacao: str | None = None, vinculo: str | None = None,
                        todos_os_tipos: bool = False, portal: str | None = None,
                        ctx: Context = None) -> dict:
    """Resumo da folha do mês: por grupo (cargo, lotacao ou vinculo), quantas linhas, quantas matrículas
    distintas, bruto e líquido. Sem nomes.

    Ex.: quantos comissionados há por secretaria e quanto custam. Aceita os mesmos filtros de
    listar_folha. Por padrão resume só a Folha Mensal (13º e rescisão vêm contados em
    `fora_do_resumo`); todos_os_tipos=True traz cada tipo de pagamento separado, nunca somado.
    Mesma leitura do mês de listar_folha: ~10 minutos na primeira vez.
    """
    try:
        if agrupar_por not in AGRUPAMENTOS:
            raise ValueError(f"agrupar_por: use cargo, lotacao ou vinculo (recebido: {agrupar_por!r})")
        consultado = _portal(portal)
        linhas = await _ler_mes_avisando(ctx, consultado, ano, _mes(mes))
        achadas = filtrar(linhas, cargo=cargo, lotacao=lotacao, vinculo=vinculo)
        filtros = {k: v for k, v in (("cargo", cargo), ("lotacao", lotacao), ("vinculo", vinculo)) if v}
        return _resposta({"total_do_mes": len(linhas), "filtros": filtros,
                          **resumir(achadas, agrupar_por, todos_os_tipos=todos_os_tipos),
                          **_ressalvas_do_mes(consultado, ano, mes)}, portal)
    except (ErroPortal, ValueError) as e:
        return {"erro": str(e)}


@mcp.tool()
def consultar_despesas(de: str, ate: str, busca: str | None = None,
                       portal: str | None = None, maximo: int = 100) -> dict:
    """Empenhos e pagamentos no período (datas AAAA-MM-DD). `busca` aceita nome ou CNPJ do fornecedor.

    CNPJ (com ou sem pontuação) traz só os empenhos daquele CNPJ; outro texto vai na busca livre.

    Ex.: quanto o município pagou à empresa tal em 2025. Em alguns portais (Megasoft, Centi) os empenhos da
    Prefeitura trazem também os da Câmara e dos fundos: o campo `orgao` diz de qual órgão é cada um.
    """
    return _executar(lambda: _aviso_orgaos(_portal(portal).despesas(de, ate, busca, maximo=maximo), "os empenhos"),
                     portal, maximo=maximo)


@mcp.tool()
def consultar_contratos(ano: int | None = None, tipo: str = "contrato", busca: str | None = None,
                        portal: str | None = None, maximo: int = 100) -> dict:
    """Contratos (tipo="contrato") ou aditivos (tipo="aditivo") do município. `ano`: o ano (exercício) do contrato.

    Os campos têm os nomes do NucleoGov em todo sistema (numero, ano, orgao_nome, objeto, fornecedor_nome,
    fornecedor_cpfcnpj, valor, data_firmatura, fim_vigencia, fiscal_contrato). Aditivos: só nos portais NucleoGov;
    na Megasoft e nas câmaras Ortrel tipo="aditivo" é recusado (lá o aditivo vem dentro do contrato; no Ortrel, em
    valor_aditado e nos anexos). Na Megasoft embutida, a `busca` procura só no objeto e `orgao` é o código do órgão.
    Ex.: os contratos de 2025 da empresa tal (busca = nome ou CNPJ).
    """
    return _executar(lambda: _aviso_orgaos(_portal(portal).contratos(ano, tipo, busca, maximo=maximo), "os contratos"),
                     portal, maximo=maximo)


@mcp.tool()
def consultar_licitacoes(busca: str | None = None, dispensas: bool = False, ano: int | None = None,
                         portal: str | None = None, maximo: int = 100) -> dict:
    """Licitações do município; dispensas=True traz dispensas e inexigibilidades.

    `ano`: só nos portais da Megasoft e nas câmaras Ortrel; nos portais NucleoGov é recusado (filtro não medido).
    Os campos têm os nomes do NucleoGov em todo sistema (numero, label = número/ano, modalidade, situacao, orgao,
    descricao, data_publicacao).
    """
    return _executar(lambda: _portal(portal).licitacoes(busca, dispensas=dispensas, ano=ano, maximo=maximo),
                     portal, maximo=maximo)


@mcp.tool()
def consultar_receitas(ano: int, mes: int, portal: str | None = None, maximo: int = 100) -> dict:
    """Receitas de um mês (mes de 1 a 12). O portal responde um mês por vez.

    Para um período (ex.: IPTU no primeiro trimestre), chame uma vez por mês. Na Megasoft e na Centi as receitas da
    Prefeitura trazem também as da Câmara e dos fundos: o campo `orgao` diz de qual órgão é cada linha.

    Centi: vêm as contas analíticas e as sintéticas, marcadas em `analitica` (true: pode somar; false: agrega
    outras, e somar conta em dobro). `somas_por_orgao` traz, para cada órgão, a soma das analíticas no mês inteiro
    (não só nos registros devolvidos); os órgãos não são somados entre si. A Câmara não vem nas receitas da Centi.
    """
    return _executar(lambda: _aviso_orgaos(_portal(portal).receitas(ano, mes, maximo=maximo), "as receitas"),
                     portal, maximo=maximo)


@mcp.tool()
def consultar_diarias(de: str, ate: str, busca: str | None = None,
                      portal: str | None = None, maximo: int = 100) -> dict:
    """Diárias de viagem a serviço pagas no período, pela data de saída (datas AAAA-MM-DD).

    `busca`: texto no nome de quem viajou, no cargo, no destino ou no motivo. Ex.: quantas diárias o motorista da
    Saúde recebeu no 1º trimestre. Os campos vêm com os mesmos nomes em todo portal (favorecido, cargo, destino,
    motivo, data_saida, data_chegada, quantidade, valor). Valor vazio: o portal não o publica (nunca é zero). As
    `ressalvas` dizem o que cada portal tem de diferente; leia-as antes de somar.
    """
    return _executar(lambda: _aviso_orgaos(_portal(portal).diarias(de, ate, busca, maximo=maximo), "as diárias"),
                     portal, maximo=maximo, avisos={"aviso_diarias": AVISO_DIARIAS})


@mcp.tool()
def detalhe_servidor(matricula: str, ano: int, mes: int, portal: str | None = None) -> dict:
    """Detalhe de uma matrícula num mês: cargo, vínculo, decreto de nomeação e a data dele, licenças, férias e os
    movimentos do mês. Só nos portais da Megasoft de domínio próprio (*.megasofttransparencia.com.br).

    A Megasoft não publica as rubricas da folha: este detalhe é o que há no lugar. A matrícula vem da folha
    (consultar_folha). Ex.: por qual decreto e desde quando Fulano ocupa o cargo.
    """
    return _executar(lambda: _portal(portal).detalhe_servidor(matricula, ano, _mes(mes)), portal,
                     avisos={"aviso_rubricas": AVISO_DETALHE})


@mcp.tool()
def consultar_legislacao(tipo: str = "DECRETO", busca: str | None = None, ano: int | None = None,
                         portal: str | None = None, maximo: int = 100) -> dict:
    """Decretos, portarias ou resoluções. `tipo`: DECRETO (padrão), PORTARIA ou RESOLUCAO; nas câmaras Ortrel, LEI.

    `busca` procura palavra na ementa. Ex.: qual decreto criou o cargo de assessor especial.
    """
    return _executar(lambda: _portal(portal).legislacao(tipo, busca, ano=ano, maximo=maximo), portal,
                     maximo=maximo)


@mcp.tool()
def encontrar_portal(municipio: str, orgao: str | None = None) -> dict:
    """O portal da transparência de um órgão de Goiás pelo nome do município.

    `orgao`: "prefeitura" ou "camara" (vazio traz os dois). Devolve o endereço, a plataforma (NucleoGov, Megasoft,
    Centi ou Ortrel: cada uma responde os módulos que publica, e o que falta é recusado com aviso) e a situação da
    conferência (se os filtros daquele portal foram medidos).
    Ex.: qual o portal da Câmara de Posse. Use o endereço no parâmetro `portal` das outras ferramentas.
    """
    achados = catalogo.encontrar(municipio, orgao)
    if not achados:
        return {"erro": f"{municipio!r} não está no catálogo de Goiás (dados do Radar da Transparência Pública, "
                        "ciclo 2025). Informe o endereço do portal diretamente."}
    return {"orgaos": [{"orgao": catalogo.nome_do_orgao(x), "portal": x["portal"],
                        "plataforma": catalogo.NOMES_PLATAFORMA.get(x["plataforma"], x["plataforma"] or "desconhecida"),
                        "situacao": catalogo.situacao(x)} for x in achados]}


def _tcm():
    return ClienteTCM()


def _executar_tcm(funcao, *avisos):
    """Consulta ao TCM-GO. Toda resposta, inclusive a de erro, traz os avisos fixos da fonte."""
    fixos = {"aviso": tcm.AVISO_GERAL, "aviso_fonte": avisos[0],
             **({"aviso_envolvidos": avisos[1]} if len(avisos) > 1 else {})}
    try:
        return {**funcao(), **fixos}
    except (ErroPortal, ValueError) as e:
        return {"erro": str(e), **fixos}


@mcp.tool()
def processos_tcm(municipio: str | None = None, tipo: str | None = None, ano: int | None = None,
                  finalizado: bool | None = None, relator: str | None = None, numero: str | None = None,
                  maximo: int = 100) -> dict:
    """Processos eletrônicos de um município no TCM-GO (eSiproc): tipo, competência, fase, relator, datas,
    decisões e envolvidos.

    `municipio` pelo nome comum ("Posse"); o projeto usa o nome oficial do TCM e recusa se não casar.
    `tipo`: tipo de protocolo (ex.: "Contas de Gestão"); `ano`: ano de competência; `finalizado`: True/False;
    `numero`: NNNNN/AA, para achar um processo citado nos autos. Ex.: que processos de contas a Prefeitura de
    Posse tem no TCM. O índice não é histórico: não achar não prova que não existe.
    """
    return _executar_tcm(lambda: _tcm().processos(municipio, tipo=tipo, ano=ano, finalizado=finalizado,
                                                  relator=relator, numero=numero, maximo=maximo),
                         tcm.AVISO_PROCESSOS, tcm.AVISO_ENVOLVIDOS)


@mcp.tool()
def acordaos_tcm(municipio: str | None = None, texto: str | None = None, assunto: str | None = None,
                 ano: int | None = None, relator: str | None = None, numero: str | None = None,
                 maximo: int = 100) -> dict:
    """Acórdãos do TCM-GO julgados desde 2020 (TCMJuris): número, data, assunto, resultado, relator.

    `texto`: palavras (aspas para expressão exata); `ano`: ano do julgamento. `numero`: número do processo ou do
    acórdão citado nos autos, NNNNN/AA (ex.: 10175/23); cada resultado é conferido no número e no ano, e `casou_com`
    diz qual dos dois casou. Sem /AA vêm todos os anos, com aviso. Ex.: há acórdão com imputação de débito para
    Trindade? A ementa (`ementa_ia`) é resumo gerado por IA: para citar, leia o acórdão com
    ler_acordao_tcm(id=document_id).
    """
    return _executar_tcm(lambda: _tcm().acordaos(municipio, texto=texto, assunto=assunto, ano=ano, relator=relator,
                                                 numero=numero, maximo=maximo),
                         tcm.AVISO_ACORDAOS)


@mcp.tool()
def ler_acordao_tcm(id: str) -> dict:
    """O texto do PDF original de um acórdão do TCM-GO, para leitura e citação. `id`: o document_id de acordaos_tcm."""
    return _executar_tcm(lambda: _tcm().ler_acordao(id), tcm.AVISO_ACORDAOS)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
