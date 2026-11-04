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

from . import catalogo
from .cliente import FONTE, ErroPortal, Portal
from .folha_leve import AGRUPAMENTOS, filtrar, linha_leve, resumir

mcp = MCPServer("transparencia-municipal",
                instructions="Consulta dados públicos do Portal da Transparência de municípios brasileiros na plataforma NucleoGov: folha de pagamento, empenhos, contratos, licitações, receitas e legislação. Folha e empenhos também da Megasoft e da contabilidade Centi.")

AVISO = ("Dado público do Portal da Transparência do município (Lei 12.527/2011), lido na hora. "
         "Confira no portal antes de usar em peça, denúncia ou matéria.")


def _endereco(url=None):
    endereco = url or os.getenv("TRANSPARENCIA_PORTAL")
    if not endereco:
        raise ValueError("Informe o portal (ex.: https://acessoainformacao.cidade.go.gov.br; use encontrar_portal "
                         "para achá-lo pelo município) ou defina TRANSPARENCIA_PORTAL.")
    return endereco


def _portal(url=None):
    """Portal pronto para consulta. Recusa, sem chamar o portal, o Ortrel; o caminho da Megasoft o Portal decide."""
    endereco = _endereco(url)
    orgao = catalogo.por_portal(endereco)
    plataforma = (orgao or {}).get("plataforma")
    if plataforma == "ortrel":
        raise ValueError(f"A {catalogo.nome_do_orgao(orgao)} usa a plataforma "
                         f"{catalogo.NOMES_PLATAFORMA[plataforma]}, ainda não suportada por este projeto.")
    sufixos = dict(orgao["sufixos"]) if orgao and orgao.get("sufixos") else None
    return Portal(endereco, navegador=os.getenv("TRANSPARENCIA_NAVEGADOR") == "1", sufixos=sufixos)


def _situacao(url=None):
    try:
        orgao = catalogo.por_portal(_endereco(url))
    except ValueError:
        return None
    return catalogo.situacao(orgao) if orgao else "portal fora do catálogo de Goiás: não conferido"


#: leitura do mês: (portal, ano, mês) → linhas leves. Só na memória, enquanto o servidor estiver aberto.
_LEITURAS: dict[tuple[str, int, int], list[dict]] = {}


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
    _LEITURAS[chave] = [linha_leve(x) for x in linhas]
    return _LEITURAS[chave]


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


def _executar(funcao, portal=None):
    try:
        return _resposta(funcao(), portal)
    except (ErroPortal, ValueError) as e:
        return {"erro": str(e)}


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
        de_outro_sistema = any(x.get("fonte", FONTE) != FONTE for x in r["registros"])  # Megasoft: listagem sem rubricas
        com_rubricas = len(r["registros"]) <= RUBRICAS_ATE and not de_outro_sistema
        saida = {"total": r["total"], "linhas": [linha_leve(x, rubricas=com_rubricas) for x in r["registros"]]}
        orgao = catalogo.por_portal(consultado.url) or {}
        if ((orgao.get("conferencia") or {}).get("filtros") or {}).get("folha_orgaos") == "falhou":
            saida["aviso_orgaos"] = ("neste portal a folha sem filtro esconde órgãos (conferência): a busca por nome "
                                     "pode não achar quem está neles. Para não perder ninguém, use "
                                     "listar_folha(ano, mes, nome=...), que lê o mês inteiro.")
        if de_outro_sistema:
            saida["aviso_rubricas"] = (f"a folha deste portal vem da {r['registros'][0]['fonte']}, cuja listagem não traz "
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
        linhas = await _ler_mes_avisando(ctx, _portal(portal), ano, _mes(mes))
        achadas = filtrar(linhas, cargo=cargo, lotacao=lotacao, vinculo=vinculo, tipo_pagamento=tipo_pagamento,
                          nome=nome)
        limite = max(1, min(maximo, LISTA_MAXIMA))
        saida = {"total_do_mes": len(linhas), "encontradas": len(achadas), "linhas": achadas[:limite]}
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
        linhas = await _ler_mes_avisando(ctx, _portal(portal), ano, _mes(mes))
        achadas = filtrar(linhas, cargo=cargo, lotacao=lotacao, vinculo=vinculo)
        filtros = {k: v for k, v in (("cargo", cargo), ("lotacao", lotacao), ("vinculo", vinculo)) if v}
        return _resposta({"total_do_mes": len(linhas), "filtros": filtros,
                          **resumir(achadas, agrupar_por, todos_os_tipos=todos_os_tipos)}, portal)
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
    def consultar():
        r = _portal(portal).despesas(de, ate, busca, maximo=maximo)
        orgaos = {x.get("orgao") for x in r["registros"] if x.get("orgao")}
        if len(orgaos) > 1:
            r["aviso_orgaos"] = (f"os empenhos incluem mais de um órgão ({len(orgaos)}: por exemplo, Câmara e "
                                 "fundos junto com a Prefeitura); confira o campo orgao de cada um")
        return r
    return _executar(consultar, portal)


@mcp.tool()
def consultar_contratos(ano: int | None = None, tipo: str = "contrato", busca: str | None = None,
                        portal: str | None = None, maximo: int = 100) -> dict:
    """Contratos (tipo="contrato") ou aditivos (tipo="aditivo") do município."""
    return _executar(lambda: _portal(portal).contratos(ano, tipo, busca, maximo=maximo), portal)


@mcp.tool()
def consultar_licitacoes(busca: str | None = None, dispensas: bool = False,
                         portal: str | None = None, maximo: int = 100) -> dict:
    """Licitações do município; dispensas=True traz dispensas e inexigibilidades."""
    return _executar(lambda: _portal(portal).licitacoes(busca, dispensas=dispensas, maximo=maximo), portal)


@mcp.tool()
def consultar_receitas(ano: int, mes: int, portal: str | None = None, maximo: int = 100) -> dict:
    """Receitas de um mês (mes de 1 a 12). O portal responde um mês por vez.

    Para um período (ex.: IPTU no primeiro trimestre), chame uma vez por mês.
    """
    return _executar(lambda: _portal(portal).receitas(ano, mes, maximo=maximo), portal)


@mcp.tool()
def consultar_legislacao(tipo: str = "DECRETO", busca: str | None = None, ano: int | None = None,
                         portal: str | None = None, maximo: int = 100) -> dict:
    """Decretos, portarias ou resoluções. `tipo`: DECRETO (padrão), PORTARIA ou RESOLUCAO.

    `busca` procura palavra na ementa. Ex.: qual decreto criou o cargo de assessor especial.
    """
    return _executar(lambda: _portal(portal).legislacao(tipo, busca, ano=ano, maximo=maximo), portal)


@mcp.tool()
def encontrar_portal(municipio: str, orgao: str | None = None) -> dict:
    """O portal da transparência de um órgão de Goiás pelo nome do município.

    `orgao`: "prefeitura" ou "camara" (vazio traz os dois). Devolve o endereço, a plataforma (NucleoGov inteiro;
    Megasoft só folha e despesas; Ortrel ainda não) e a situação da conferência (se os filtros daquele portal foram
    medidos).
    Ex.: qual o portal da Câmara de Posse. Use o endereço no parâmetro `portal` das outras ferramentas.
    """
    achados = catalogo.encontrar(municipio, orgao)
    if not achados:
        return {"erro": f"{municipio!r} não está no catálogo de Goiás (dados do Radar da Transparência Pública, "
                        "ciclo 2025). Informe o endereço do portal diretamente."}
    return {"orgaos": [{"orgao": catalogo.nome_do_orgao(x), "portal": x["portal"],
                        "plataforma": catalogo.NOMES_PLATAFORMA.get(x["plataforma"], x["plataforma"] or "desconhecida"),
                        "situacao": catalogo.situacao(x)} for x in achados]}


def main():
    mcp.run()


if __name__ == "__main__":
    main()
