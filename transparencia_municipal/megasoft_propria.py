"""Acesso à Megasoft de domínio próprio (`*.megasofttransparencia.com.br`). Encaixe do ticket 02; único arquivo dele.

O `Portal` manda para cá o portal inteiro, só pelo endereço; aqui se leem folha, despesas, receitas, diárias,
contratos, licitações e o detalhe do servidor (legislação: o `Portal` recusa).
Contrato dos encaixes (o mesmo em megasoft_embutida.py e centi.py):
- devolve {"total": <total anunciado pelo sistema>, "registros": [<até `maximo` registros traduzidos>]};
- registros traduzidos (Megasoft: `traducao_megasoft.linha_da_folha` e `despesa`; Centi: `centi.despesa`, com as
  mesmas chaves), cada um com `fonte`;
- leitura que não fecha (registros lidos ≠ total, com `maximo` suficiente) devolve o que leu e o total anunciado:
  quem lê o mês declara "incompleta"; nunca devolver total 0 para esconder falha;
- `cnpj` (já 00.000.000/0000-00) é filtrado aqui sobre os registros do período, mesmo se o sistema filtrar;
- erro de rede ou resposta inesperada: `ErroPortal`, com mensagem que diga o que houve;
- pausa `portal.pausa` entre páginas; identificação `portal.user_agent`; sessão `portal.sessao`.

Medido em Corumbaíba (04/11/2026):
- a senha pública (`tokenPortal`, JWT) sai de `/api/configuracao/carregamento-inicial`, sem login, e vale cerca de
  24 h; senha vencida dá 401 (medição anterior) e senha ilegível, 500 "Token inválido";
- a busca por nome (`nome`, `filtro`) não filtra no servidor: o nome é filtrado aqui;
- `cnpjDoFornecedor` filtra no servidor (597 de 4.314 no 1º trimestre de 2025), e o projeto confere mesmo assim;
- em páginas de 100 os empenhos repetem e perdem registros na fronteira (fevereiro/2025: 1.555 lidos, 1.319 códigos
  distintos); numa página de 5.000, os 1.555 vieram distintos. Por isso a página é grande e o código tira repetidos.
"""
from __future__ import annotations

import json
import sys
import time
import unicodedata
from datetime import datetime

import requests

from . import traducao_megasoft
from .cliente import ErroPortal, PortalBloqueou

#: senha pública por portal, só na memória enquanto o processo estiver aberto
_SENHAS: dict[str, str] = {}
#: registros por página: grande, porque a fronteira de página repete e perde registros (ver acima)
TAMANHO = 5000
FOLHA = "orgaos-e-servidores/servidor/paginado"
EMPENHOS = "receitas-e-despesas/empenho/paginado"
RECEITAS = "receitas-e-despesas/receita/receitas-pelo-tipo-de-natureza-detalhada/paginado"
DIARIAS = "orgaos-e-servidores/diaria/paginado"
CONTRATOS = "contratos-convenios-e-licitacoes/contrato/paginado"
LICITACOES = "contratos-convenios-e-licitacoes/procedimento-licitatorio/paginado"
DETALHE = "orgaos-e-servidores/servidor/detalhe"


def _senha(portal, *, renovar=False):
    if renovar or portal.url not in _SENHAS:
        endereco = f"{portal.url}/api/configuracao/carregamento-inicial"
        try:
            r = portal.sessao.get(endereco, timeout=portal.timeout, headers={"User-Agent": portal.user_agent})
            senha = r.json().get("tokenPortal") if r.status_code == 200 else None
        except (requests.RequestException, ValueError, AttributeError) as e:
            raise ErroPortal(f"não foi possível obter a senha pública de {portal.url}: {e}") from e
        if not senha:
            raise ErroPortal(f"{portal.url} não entregou a senha pública (HTTP {r.status_code} em "
                             "configuracao/carregamento-inicial)")
        _SENHAS[portal.url] = senha
    return _SENHAS[portal.url]


def _senha_recusada(r):
    """401 (senha vencida) ou 500 "Token inválido" (senha ilegível), como medido."""
    return r.status_code == 401 or (r.status_code == 500 and "Token" in r.text)


def _requisicao(portal, caminho, consulta, *, metodo="GET"):
    """Uma requisição à API (GET com a consulta no endereço; POST com ela no corpo JSON). Senha recusada: renova uma vez
    e repete. Devolve a resposta, de qualquer HTTP."""
    for renovar in (False, True):
        cabecalhos = {"User-Agent": portal.user_agent, "Authorization": f"Bearer {_senha(portal, renovar=renovar)}",
                      "cliente-integrado": "megasoft-portal-da-transparencia"}
        dados = {"params": consulta} if metodo == "GET" else {"json": consulta}
        try:
            r = portal.sessao.request(metodo, f"{portal.url}/api/{caminho}", headers=cabecalhos,
                                      timeout=portal.timeout, **dados)
        except requests.RequestException as e:
            raise ErroPortal(f"não foi possível falar com {portal.url}: {e}") from e
        if not _senha_recusada(r):
            break
    return r


def _http_ok(portal, r, caminho):
    if r.status_code == 403:
        raise PortalBloqueou(f"{portal.url} respondeu 403 em {caminho}.")
    if r.status_code != 200:
        raise ErroPortal(f"{portal.url} respondeu HTTP {r.status_code} em {caminho}: {r.text[:200]}")


def _pagina(portal, caminho, filtros, pagina, tamanho, metodo="GET"):
    """Uma página: (registros crus, total anunciado)."""
    r = _requisicao(portal, caminho, {**filtros, "pagina": pagina, "tamanhoDaPagina": tamanho}, metodo=metodo)
    _http_ok(portal, r, caminho)
    try:
        corpo = r.json()
        registros, total = corpo["registros"], int(corpo["total"])
    except (ValueError, KeyError, TypeError) as e:
        raise ErroPortal(f"{portal.url} devolveu resposta inesperada em {caminho} "
                         f"({len(r.content)} bytes, começa com {r.text[:80]!r})") from e
    if not isinstance(registros, list):
        raise ErroPortal(f"{portal.url} devolveu `registros` que não é lista em {caminho}")
    return registros, total


def _ler(portal, caminho, filtros, *, chave, ate, progresso=None, metodo="GET"):
    """Lê página a página até ter `ate` registros distintos (pela `chave`; sem ela, pelo registro inteiro) ou acabar.
    Devolve (distintos, total). `metodo`: "POST" nos contratos e nas licitações, que recusam GET (405)."""
    distintos, total, pagina = {}, 0, 1
    tamanho = min(TAMANHO, max(ate, 1))
    while True:
        lote, total_da_pagina = _pagina(portal, caminho, filtros, pagina, tamanho, metodo)
        total = total_da_pagina if pagina == 1 else total  # vale o total anunciado na 1ª página
        for reg in lote:
            distintos.setdefault(chave(reg) or json.dumps(reg, sort_keys=True), reg)
        if progresso:
            progresso(len(distintos), total)
        if len(lote) < tamanho or len(distintos) >= min(total, ate) or pagina * tamanho >= total:
            return list(distintos.values()), total
        pagina += 1
        time.sleep(portal.pausa)


def _simples(texto):
    """Sem acento e em maiúsculas, para a busca por nome."""
    return "".join(c for c in unicodedata.normalize("NFD", str(texto or "")) if not unicodedata.combining(c)).upper()


def _filtrado(regs, total, casa, onde):
    """Filtra pelo projeto. A leitura que não fechou não permite contar: falha em vez de devolver total menor."""
    if len(regs) != total:
        raise ErroPortal(f"a leitura de {onde} veio incompleta ({len(regs)} de {total} registros): "
                         "não dá para contar os que casam com a busca. Tente de novo.")
    return [x for x in regs if casa(x)]


def folha(portal, *, ano, mes, busca, maximo, progresso=None):
    """Linhas da folha de `mes`/`ano` (int; `mes` None = o portal decide). `busca`: nome do servidor ou None.

    `progresso(lidas, total)`, se dado, é chamado depois de cada página (a leitura do mês avisa o assistente).
    """
    filtros = {"ano": ano} if mes is None else {"ano": ano, "mes": f"{int(mes):02d}"}

    def chave(reg):
        return json.dumps(reg.get("chave"), sort_keys=True) if reg.get("chave") else reg.get("matricula")
    regs, total = _ler(portal, FOLHA, filtros, chave=chave, ate=sys.maxsize if busca else maximo,
                       progresso=progresso)
    linhas = [traducao_megasoft.linha_da_folha(x) for x in regs]
    if busca:
        alvo = _simples(busca)
        linhas = _filtrado(linhas, total, lambda x: alvo in _simples(x["nome"]), f"folha de {portal.url}")
        total = len(linhas)
    return {"total": total, "registros": linhas[:maximo]}


def despesas(portal, *, de, ate, cnpj, busca, maximo):
    """Empenhos de `de` a `ate` (dd/mm/aaaa). `cnpj` formatado ou None; `busca`: nome do fornecedor ou None."""
    filtros = {"dataInicial": de, "dataFinal": ate}
    if cnpj:
        filtros["cnpjDoFornecedor"] = cnpj
    regs, total = _ler(portal, EMPENHOS, filtros, chave=lambda reg: reg.get("codigo"),
                       ate=sys.maxsize if cnpj or busca else maximo)
    empenhos = [traducao_megasoft.despesa(x) for x in regs]
    if cnpj or busca:
        alvo = _simples(busca)
        casa = (lambda x: x["cpf_cnpj"] == cnpj) if cnpj else (lambda x: alvo in _simples(x["fornecedor"]))
        empenhos = _filtrado(empenhos, total, casa, f"despesas de {portal.url}")
        total = len(empenhos)
    return {"total": total, "registros": empenhos[:maximo]}


# ── módulos extras (ticket 02): consultas da descoberta A do desenho dos módulos extras ────────────────────────────

RESSALVA_RECEITAS = ("as receitas da Megasoft trazem todas as entidades juntas (Prefeitura, Câmara, fundos e RPPS): o "
                     "campo orgao diz de qual é cada linha; a Megasoft não diz quais contas são sintéticas "
                     "(analitica vazia), mas na medição a soma das linhas bateu com o total por órgão")
RESSALVA_DIARIAS = ("o portal recorta as diárias pela data de saída e publica um só valor por viagem: pelas combinações "
                    "medidas (ex.: 4 diárias com R$ 350,00), ele parece ser o total da viagem, não o de uma diária; "
                    "confira na tela do portal antes de multiplicar pela quantidade; a listagem não traz o órgão")
RESSALVA_CHAMAMENTO = ("o portal põe o mesmo chamamento público nas licitações e nas dispensas: ao somar as duas "
                       "listas, tire os repetidos pelo codigo")


def _data_ou_none(texto):
    try:
        return datetime.strptime(str(texto or "")[:10], "%d/%m/%Y").date()
    except ValueError:
        return None


def _busca(regs, total, busca, campos, onde):
    """Filtra pelo projeto: `busca` (sem acento nem caixa) contida em algum dos `campos`."""
    alvo = _simples(busca)
    return _filtrado(regs, total, lambda x: any(alvo in _simples(x[c]) for c in campos if x[c]), onde)


def receitas(portal, *, ano, mes, maximo):
    """Receitas de `mes`/`ano` (int), com os nomes comuns de receitas.

    Usa a consulta detalhada por natureza, que respeita ano e mês; `receita/paginado` ignora o período (descoberta A).
    Toda linha é conferida: linha de outro mês é erro, nunca mistura devolvida.
    """
    def chave(reg):
        return json.dumps(reg.get("chave"), sort_keys=True) if reg.get("chave") else None
    regs, total = _ler(portal, RECEITAS, {"ano": ano, "mes": f"{mes:02d}"}, chave=chave, ate=maximo)
    linhas = [traducao_megasoft.receita(x) for x in regs]
    fora = sum(1 for x in linhas if (str(x["ano"]), x["mes"]) != (str(ano), mes))
    if fora:
        raise ErroPortal(f"{portal.url} devolveu receitas de outro mês ({fora} de {len(linhas)} linhas) ao pedir "
                         f"{mes:02d}/{ano}: o filtro de período não foi respeitado e nada foi devolvido, para não "
                         "misturar meses.")
    return {"total": total, "registros": linhas[:maximo], "ressalvas": [RESSALVA_RECEITAS]}


def diarias(portal, *, de, ate, busca, maximo):
    """Diárias com saída de `de` a `ate` (`datetime.date`), com os nomes comuns de diárias. `busca`: texto ou None,
    filtrado aqui em favorecido, cargo, destino e motivo (o portal não tem busca medida).

    `data=1` recorta pela data de saída (sem ele, o recorte usa outra data); toda saída é conferida.
    """
    filtros = {"dataInicial": de.strftime("%d/%m/%Y"), "dataFinal": ate.strftime("%d/%m/%Y"), "data": 1}
    regs, total = _ler(portal, DIARIAS, filtros, chave=lambda reg: reg.get("codigoDaViagem"),
                       ate=sys.maxsize if busca else maximo)
    linhas = [traducao_megasoft.diaria(x) for x in regs]
    saidas = [_data_ou_none(x["data_saida"]) for x in linhas]
    fora = sum(1 for d in saidas if d and not de <= d <= ate)
    if fora:
        raise ErroPortal(f"{portal.url} devolveu {fora} diárias com saída fora do período pedido: o recorte por data "
                         "não foi respeitado e nada foi devolvido.")
    ressalvas = [RESSALVA_DIARIAS]
    sem_data = saidas.count(None)
    if sem_data:
        ressalvas.append(f"{sem_data} diárias vieram sem data de saída legível")
    if busca:
        linhas = _busca(linhas, total, busca, ("favorecido", "cargo", "destino", "motivo"), f"diárias de {portal.url}")
        total = len(linhas)
    return {"total": total, "registros": linhas[:maximo], "ressalvas": ressalvas}


def contratos(portal, *, ano, tipo, busca, maximo):
    """Contratos do `ano` (int ou None = todos os anos); `tipo`: só "contrato"; `busca`: texto filtrado aqui.

    Só POST (GET dá 405). O `ano` do portal é conferido no `exercicioAno` de cada contrato.
    """
    if str(tipo).strip().lower() != "contrato":
        raise ValueError("tipo: na Megasoft de domínio próprio os aditivos só aparecem dentro do detalhe de cada "
                         "contrato, consulta que este projeto não mediu; use tipo='contrato'")
    regs, total = _ler(portal, CONTRATOS, {"ano": ano} if ano else {}, chave=lambda reg: reg.get("codigo"),
                       ate=sys.maxsize if busca else maximo, metodo="POST")
    linhas = [traducao_megasoft.contrato(x) for x in regs]
    if ano:
        fora = sum(1 for x in linhas if str(x["exercicio"]) != str(ano))
        if fora:
            raise ErroPortal(f"{portal.url} devolveu {fora} contratos de outro ano ao pedir {ano}: o filtro de ano "
                             "não foi respeitado e nada foi devolvido.")
    if busca:
        linhas = _busca(linhas, total, busca, ("objeto", "fornecedor", "cpf_cnpj", "numero", "licitacao",
                                                "modalidade", "orgao", "finalidade"), f"contratos de {portal.url}")
        total = len(linhas)
    return {"total": total, "registros": linhas[:maximo]}


def licitacoes(portal, *, busca, dispensas, ano, maximo):
    """Licitações (`dispensas` False) ou dispensas e inexigibilidades (True); `ano` (int ou None), pela data de
    publicação; `busca`: texto filtrado aqui.

    Só POST. As duas telas usam o mesmo serviço, com `tipoDeConsultaDeModalidade` 1 ou 2; sem ele vem tudo.
    """
    filtros = {"tipoDeConsultaDeModalidade": 2 if dispensas else 1}
    if ano:
        filtros.update(dataDePublicacaoInicial=f"01/01/{ano}", dataDePublicacaoFinal=f"31/12/{ano}")
    regs, total = _ler(portal, LICITACOES, filtros, chave=lambda reg: reg.get("codigo"),
                       ate=sys.maxsize if busca else maximo, metodo="POST")
    linhas = [traducao_megasoft.licitacao(x) for x in regs]
    publicacoes = [_data_ou_none(x["data_publicacao"]) for x in linhas]
    ressalvas = [RESSALVA_CHAMAMENTO]
    if ano:
        fora = sum(1 for d in publicacoes if d is None or d.year != ano)
        if fora:
            raise ErroPortal(f"{portal.url} devolveu {fora} licitações publicadas em outro ano (ou sem data) ao pedir "
                             f"{ano}: o filtro não foi respeitado e nada foi devolvido.")
        ressalvas.append("o ano é o da data de publicação")
    elif publicacoes.count(None):
        ressalvas.append(f"{publicacoes.count(None)} licitações vieram sem data de publicação")
    if busca:
        linhas = _busca(linhas, total, busca, ("objeto", "numero", "modalidade", "orgao", "situacao"),
                        f"licitações de {portal.url}")
        total = len(linhas)
    return {"total": total, "registros": linhas[:maximo], "ressalvas": ressalvas}


#: listas do detalhe que podem vir cortadas (o portal mostra 5 por vez e ignora o tamanho pedido)
LISTAS_DO_DETALHE = {"licenca": "licenças", "ferias": "férias", "vidaFuncionalDisposicao": "disposições",
                     **{campo: f"movimentos ({nome})" for campo, nome in traducao_megasoft.MOVIMENTOS.items()}}


def detalhe_servidor(portal, *, matricula, ano, mes):
    """O detalhe de uma matrícula (texto) em `mes`/`ano` (int): cargo, vínculo, decreto e data, licenças, movimentos.

    `{"total": 1, "registros": [detalhe]}`; matrícula que não existe no mês: total 0 (o portal responde 406 "Valor de
    chave não existe"). Sem rubricas: a Megasoft não as publica.
    """
    consulta = {"matricula": matricula, "mes": f"{mes:02d}", "ano": ano, "mesInteger": mes}
    r = _requisicao(portal, DETALHE, consulta)
    if r.status_code == 406 and "Valor de chave" in r.text:
        return {"total": 0, "registros": []}
    _http_ok(portal, r, DETALHE)
    try:
        corpo = r.json()
        veio = str(corpo["matricula"])
    except (ValueError, KeyError, TypeError) as e:
        raise ErroPortal(f"{portal.url} devolveu resposta inesperada em {DETALHE} "
                         f"({len(r.content)} bytes, começa com {r.text[:80]!r})") from e
    if veio.lstrip("0") != matricula.lstrip("0"):
        raise ErroPortal(f"{portal.url} devolveu o detalhe de outra matrícula ao pedir {matricula}.")
    ressalvas = []
    for campo, nome in LISTAS_DO_DETALHE.items():
        lista = corpo.get(campo) if isinstance(corpo.get(campo), dict) else {}
        n, total = len(lista.get("registros") or []), int(lista.get("total") or 0)
        if total > n:
            ressalvas.append(f"a lista de {nome} veio com {n} de {total} registros: o portal não entrega o resto "
                             "nesta consulta")
    if any(x.get("existeConcessaoDeVerba") for campo in traducao_megasoft.MOVIMENTOS
           for x in traducao_megasoft._registros(corpo.get(campo))):
        ressalvas.append("há concessão de verba neste mês: o portal a detalha em outra consulta, que este projeto "
                         "não lê")
    resposta = {"total": 1, "registros": [traducao_megasoft.detalhe_servidor(corpo)]}
    if ressalvas:
        resposta["ressalvas"] = ressalvas
    return resposta
