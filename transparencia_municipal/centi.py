"""Acesso à contabilidade Centi integrada ao portal NucleoGov (menus `cntdespesas` e `cntreceitas`). Encaixe único
da Centi, com a tradução Centi → formato do projeto (despesas como `traducao_megasoft.despesa`; receitas com os nomes
comuns do ticket 01 dos módulos extras).

O `Portal` manda para cá despesas e receitas quando o menu aponta a Centi e a API NucleoGov não serve o módulo. A
Centi não tem folha nem diárias aqui: sem a função, o `Portal` recusa. O contrato dos encaixes está em
megasoft_propria.py. As receitas estão no fim do arquivo, com o que foi medido nelas.

Medido em Posse (04/11/2026):
- `POST {portal}/api/centi`, formulário simples (sem `multi_request`), `acao=empenhos`, `id_orgao=0` (todas as
  entidades), `data_inicio`/`data_fim` em dd/mm/aaaa. Resposta: lista inteira do período, sem páginas; cada registro
  traz `TotalRegistros`, o total declarado.
- O período é respeitado. A mesma página chama `relatorioEmpenhos`, que só devolve três somas
  (`total_empenhado` = soma de `ValorEmpenhado` − `ValorAnulacao`, conferido ao centavo em 01 e 02/2025).
- O filtro `cpf_cnpj` da Centi devolve lista vazia para um CNPJ que tem empenhos: não é mandado; o CNPJ é filtrado aqui.
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
import urllib.parse
from datetime import datetime
from decimal import Decimal, InvalidOperation

import requests

from .cliente import ErroPortal, PortalBloqueou, _cnpj

FONTE = "Centi"
#: o formulário que a página `cntdespesas` manda, com os filtros zerados (os mesmos nomes e valores)
FILTROS = {"numero": "0", "processo": "0", "credor": "", "cpf_cnpj": "", "ano": "0", "valor_inicial": "0",
           "valor_final": "0", "id_orgao": "0", "id_funcao": "0", "licitacao": "0", "elemento": "",
           "sub_funcao": "", "dp_acao": "", "covid": ""}


def _decimal(valor):
    """'12.000,50' → Decimal('12000.50'); vazio ou ilegível → None."""
    try:
        return Decimal(str(valor).replace(".", "").replace(",", ".")) if valor not in (None, "") else None
    except InvalidOperation:
        return None


def _br(d):
    return None if d is None else f"{d:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def despesa(reg):
    """Um empenho da Centi no formato de despesas do projeto.

    `valor_empenhado` é o empenhado menos a anulação, como no relatório da própria página (e como o total da
    Megasoft). Liquidado e pago saem como a Centi os dá. `orgao` é o `OrgaoGestor`: com `id_orgao=0` vêm a Câmara e
    os fundos junto com a Prefeitura.
    """
    empenhado, anulado = _decimal(reg.get("ValorEmpenhado")), _decimal(reg.get("ValorAnulacao"))
    documento = reg.get("CpfCnpjCredor") or None
    return {
        "empenho": reg.get("Numero"), "data": reg.get("Data"),
        "cpf_cnpj": (_cnpj(documento) or documento) if documento else None,
        "fornecedor": reg.get("Fornecedor") or None,
        "valor_empenhado": _br(None if empenhado is None else empenhado - (anulado or 0)),
        "valor_liquidado": _br(_decimal(reg.get("ValorLiquidado"))),
        "valor_pago": _br(_decimal(reg.get("ValorPago"))),
        "historico": reg.get("Historico"), "orgao": reg.get("OrgaoGestor") or None, "fonte": FONTE,
    }


def _post(portal, campos, rotulo):
    """`POST {portal}/api/centi` num formulário simples; devolve o JSON (ou None, se não for JSON)."""
    try:
        r = portal.sessao.post(
            f"{portal.url}/api/centi", data=urllib.parse.urlencode(campos), timeout=portal.timeout,
            headers={"User-Agent": portal.user_agent, "X-Requested-With": "XMLHttpRequest",
                     "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
    except requests.RequestException as e:
        raise ErroPortal(f"não foi possível falar com {portal.url}: {e}") from e
    if r.status_code == 403:
        raise PortalBloqueou(f"{portal.url} respondeu 403 na Centi para um cliente que se identifica como ferramenta "
                             "(ver README, \"O 403\"; CLI: --navegador).")
    if r.status_code != 200:
        raise ErroPortal(f"{portal.url} respondeu HTTP {r.status_code} na Centi: {r.text[:200]}")
    try:
        return r.json()
    except ValueError:
        raise ErroPortal(f"{portal.url} devolveu resposta inesperada na Centi ({rotulo}; "
                         f"{len(r.content)} bytes, começa com {r.text[:80]!r})") from None


def _empenhos(portal, de, ate):
    """A lista crua da Centi para o período."""
    lista = _post(portal, {**FILTROS, "data_inicio": de, "data_fim": ate, "acao": "empenhos"}, "acao=empenhos")
    if not isinstance(lista, list):
        raise ErroPortal(f"{portal.url} devolveu resposta inesperada na Centi (acao=empenhos; não é uma lista)")
    return lista


def _sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFKD", str(texto or "")) if not unicodedata.combining(c)).casefold()


def _dia(texto):
    try:
        return datetime.strptime(str(texto), "%d/%m/%Y").date()
    except ValueError:
        return None


def _total_declarado(portal, lista, quais="empenhos"):
    """`TotalRegistros`, que todo registro traz e é o mesmo em todos; senão a resposta não é a que conhecemos."""
    totais = {x.get("TotalRegistros") if isinstance(x, dict) else None for x in lista}
    total = totais.pop() if len(totais) == 1 else None
    if not isinstance(total, int) or isinstance(total, bool):
        raise ErroPortal(f"{portal.url} devolveu {quais} da Centi sem um total declarado único "
                         "(`TotalRegistros` ausente ou divergente entre os registros)")
    return total


def despesas(portal, *, de, ate, cnpj, busca, maximo):
    """Empenhos de `de` a `ate` (dd/mm/aaaa). `cnpj` formatado ou None; `busca`: nome do fornecedor ou None.

    A Centi não filtra CNPJ (medido) e o filtro de credor não foi medido: os dois são aplicados aqui.
    """
    lista = _empenhos(portal, de, ate)
    for fator in (2, 5):
        if lista:
            break
        # Posse (04/11/2026): `[]` em 0,4 s numa janela com empenhos; repetida, respondeu. Vazio que se repete é zero.
        time.sleep(portal.pausa * fator)
        lista = _empenhos(portal, de, ate)
    total = _total_declarado(portal, lista) if lista else 0
    registros = [despesa(x) for x in lista]
    inicio, fim = _dia(de), _dia(ate)
    fora = [x["data"] for x in registros if not (_dia(x["data"]) and inicio <= _dia(x["data"]) <= fim)]
    if fora:
        raise ErroPortal(f"{portal.url}: a Centi devolveu {len(fora)} empenho(s) fora do período {de} a {ate} "
                         f"(ex.: {fora[0]!r}); a resposta não foi usada.")
    if cnpj or busca:
        if len(lista) != total:  # filtrar sobre parte do período seria uma contagem parcial calada
            raise ErroPortal(f"{portal.url}: a Centi entregou {len(lista)} de {total} empenhos de {de} a {ate}; "
                             "a busca precisa do período inteiro. Tente uma janela menor.")
        if cnpj:
            registros = [x for x in registros if x["cpf_cnpj"] == cnpj]
        else:
            registros = [x for x in registros if _sem_acento(busca) in _sem_acento(x["fornecedor"])]
        total = len(registros)
    return {"total": total, "registros": registros[:maximo]}


# ── receitas (menu `cntreceitas`; ticket 04 dos módulos extras) ──────────────────────────────────────────────────

MESES = ("janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro")
#: `TipoConta` da Centi → `analitica`: 1 analítica (pode ser somada), 2 sintética (agrega outras); 0 e o resto: não diz
ANALITICA = {1: True, 2: False}
RAIZ = re.compile(r"\d+(\.0+)+")  # 1.0.0.0.00.0.0, 91.0.0.0.00.0.0: as contas do topo de cada grupo


def _orgaos(portal):
    """Os órgãos da Centi (`sgcenti/listarOrgaos`, envelope `multi_request`), o principal primeiro: [(id, nome)].

    Posse, 04/11/2026: a resposta é a lista crua `[{id, valor, principal}]`, sem `dados` (o `_pagina` não serve).
    """
    ident = "0-centi"
    try:
        r = portal.sessao.post(
            f"{portal.url}/api/sgcenti/listarOrgaos", timeout=portal.timeout,
            data=urllib.parse.urlencode({"multi_request": "true",
                                         "params": json.dumps({ident: {"acao": "sgcenti/listarOrgaos"}})}),
            headers={"User-Agent": portal.user_agent, "X-Requested-With": "XMLHttpRequest",
                     "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
    except requests.RequestException as e:
        raise ErroPortal(f"não foi possível falar com {portal.url}: {e}") from e
    if r.status_code == 403:
        raise PortalBloqueou(f"{portal.url} respondeu 403 na lista de órgãos da Centi (ver README, \"O 403\"; "
                             "CLI: --navegador).")
    try:
        lista = r.json()[ident] if r.status_code == 200 else None
    except (ValueError, KeyError, TypeError):
        lista = None
    if not isinstance(lista, list) or not lista or not all(isinstance(o, dict) and o.get("id") for o in lista):
        raise ErroPortal(f"{portal.url} não deu a lista de órgãos da Centi (HTTP {r.status_code}, começa com "
                         f"{r.text[:80]!r}); as receitas são lidas por órgão e não há como lê-las sem ela.")
    lista = sorted(lista, key=lambda o: str(o.get("principal")) != "1")
    return [(str(o["id"]), o.get("valor") or str(o["id"])) for o in lista]


def _receitas_do_orgao(portal, ano, mes, orgao):
    """As linhas cruas de um órgão no mês; `[]` se a Centi não tem nenhuma."""
    d = _post(portal, {"acao": "receitas", "ano": str(ano), "mes": f"{mes:02d}", "orgao": orgao}, "acao=receitas")
    if not isinstance(d, dict) or not isinstance(d.get("dados", []), list):
        raise ErroPortal(f"{portal.url} devolveu resposta inesperada na Centi (acao=receitas, órgão {orgao}; "
                         "sem a lista `dados`)")
    erro = d.get("error")
    if isinstance(erro, str) and erro.strip() and erro.strip() != "null":  # "null" vem com a lista vazia (Posse)
        raise ErroPortal(f"{portal.url}: a Centi recusou as receitas do órgão {orgao}: {erro}")
    return d.get("dados") or []


def receita(reg, ano, mes):
    """Uma linha de receita da Centi com os nomes comuns de receitas do projeto (ticket 01, `## Comments`)."""
    codigo_fonte, nome_fonte = reg.get("CodigoFonte") or "", reg.get("Fonte") or ""
    return {
        "orgao": reg.get("Orgao") or None, "codigo": reg.get("CodigoElemento") or None,
        "receita": reg.get("DescricaoElemento") or None,
        "fonte_recurso": " - ".join(x for x in (codigo_fonte, nome_fonte) if x) or None,
        "valor_orcado": _br(_decimal(reg.get("ValorOrcado"))),
        "valor_previsto_atualizado": _br(_decimal(reg.get("PrevisaoAtualizada"))),
        "valor_arrecadado_mes": _br(_decimal(reg.get("ValoReceitaAcumuladoMes"))),
        "valor_arrecadado_ate_mes": _br(_decimal(reg.get("ValoReceitaAcumulado"))),
        "ano": ano, "mes": mes, "analitica": ANALITICA.get(reg.get("TipoConta")), "fonte": FONTE,
    }


def _soma(linhas, campo):
    return sum((_decimal(x.get(campo)) or Decimal(0) for x in linhas), Decimal(0))


def _conferir_raizes(nome, linhas):
    """Ressalvas onde a soma das analíticas não fecha com a das contas do topo (sintéticas 1.0.0..., 91.0.0...).

    Posse, 09/2025, Poder Executivo: no mês fecha ao centavo; no acumulado, as analíticas passam das raízes em
    R$ 334.029,19, sem explicação achada.
    """
    raizes = [x for x in linhas if x.get("TipoConta") == 2 and RAIZ.fullmatch(str(x.get("CodigoElemento") or ""))]
    analiticas = [x for x in linhas if x.get("TipoConta") == 1]
    if not raizes or not analiticas:
        return []
    ressalvas = []
    for campo, quando in (("ValoReceitaAcumuladoMes", "no mês"), ("ValoReceitaAcumulado", "no acumulado do ano")):
        a, b = _soma(analiticas, campo), _soma(raizes, campo)
        if a != b:
            ressalvas.append(f"em {nome}, {quando}, a soma das contas analíticas (R$ {_br(a)}) difere da soma das "
                             f"contas do topo (R$ {_br(b)}) em R$ {_br(a - b)}; a diferença não tem explicação "
                             "conhecida: confira no portal antes de usar esse valor.")
    return ressalvas


def receitas(portal, *, ano, mes, maximo):
    """Receitas de `mes`/`ano` (int), com os nomes comuns de receitas.

    A Centi exige o órgão: cada órgão de `sgcenti/listarOrgaos` é lido em separado, e as linhas são juntadas, o
    principal primeiro. Todas as contas vêm, cada uma marcada em `analitica` (as sintéticas, `False`, não podem ser
    somadas com as outras); `somas_por_orgao` traz a soma das analíticas de cada órgão sobre o mês inteiro (não só
    sobre os `maximo` registros devolvidos). Conferido em cada linha: ano, mês e um só órgão por resposta, diferente
    de órgão para órgão (filtro ignorado seria contagem em dobro).
    """
    registros, somas, ressalvas, vazios, faltas, vistos = [], [], [], [], [], {}
    total = sem_marca = 0
    for orgao, nome_da_lista in _orgaos(portal):
        time.sleep(portal.pausa)
        linhas = _receitas_do_orgao(portal, ano, mes, orgao)
        for fator in (2, 5):
            # Posse, 04/11/2026: o Fundo de Cultura veio vazio em 09/2025 e, minutos depois, com 16 linhas
            if linhas:
                break
            time.sleep(portal.pausa * fator)
            linhas = _receitas_do_orgao(portal, ano, mes, orgao)
        if not linhas:
            vazios.append(nome_da_lista)
            somas.append({"orgao": nome_da_lista, "linhas": 0, "linhas_analiticas": 0,
                          "valor_arrecadado_mes": None, "valor_arrecadado_ate_mes": None})
            continue
        nomes = {x.get("Orgao") for x in linhas}
        if len(nomes) != 1:
            raise ErroPortal(f"{portal.url}: a Centi devolveu {len(nomes)} órgãos numa consulta do órgão "
                             f"{nome_da_lista}; a resposta não foi usada.")
        nome = nomes.pop() or nome_da_lista
        if nome in vistos:
            raise ErroPortal(f"{portal.url}: a Centi devolveu as receitas de {nome} para o órgão {nome_da_lista} e "
                             f"para o {vistos[nome]}: o filtro do órgão parece ignorado; a resposta não foi usada.")
        vistos[nome] = nome_da_lista
        fora = [x for x in linhas if x.get("Ano") != ano or _sem_acento(x.get("mes")) != MESES[mes - 1]]
        if fora:
            raise ErroPortal(f"{portal.url}: a Centi devolveu {len(fora)} linha(s) de receita fora de {mes:02d}/{ano} "
                             f"no órgão {nome} (ex.: {fora[0].get('mes')!r}/{fora[0].get('Ano')!r}); a resposta não "
                             "foi usada.")
        declarado = _total_declarado(portal, linhas, "receitas")
        if len(linhas) < declarado:
            faltas.append(f"{nome}: {len(linhas)} de {declarado}")
        total += declarado
        analiticas = [x for x in linhas if x.get("TipoConta") == 1]
        sem_marca += sum(1 for x in linhas if x.get("TipoConta") not in ANALITICA)
        somas.append({"orgao": nome, "linhas": len(linhas), "linhas_analiticas": len(analiticas),
                      "valor_arrecadado_mes": _br(_soma(analiticas, "ValoReceitaAcumuladoMes")),
                      "valor_arrecadado_ate_mes": _br(_soma(analiticas, "ValoReceitaAcumulado"))})
        ressalvas += _conferir_raizes(nome, linhas)
        registros += [receita(x, ano, mes) for x in linhas]
    ressalvas[:0] = [
        f"a Centi só dá as receitas de um órgão por vez: os {len(somas)} órgãos do município (Prefeitura e fundos) "
        "foram lidos em separado e juntados; o campo orgao diz de qual é cada linha, e o projeto não consolida os "
        "órgãos.",
        "vêm todas as contas, analíticas e sintéticas, cada uma marcada no campo analitica: só as linhas com "
        "analitica = true podem ser somadas (as sintéticas, false, agregam as outras, e somá-las conta em dobro); "
        "a soma das analíticas de cada órgão, sobre o mês inteiro, está em somas_por_orgao (no MCP; a linha de comando a imprime)."]
    if sem_marca:
        ressalvas.append(f"{sem_marca} linha(s) sem dizer se é analítica ou sintética (analitica = null): fora das "
                         "somas.")
    if vazios:
        ressalvas.append(f"{len(vazios)} órgão(s) sem receitas em {mes:02d}/{ano} (lista vazia, pedida três vezes): "
                         f"{', '.join(vazios)}. A Centi já devolveu vazio por falha passageira: repita a consulta "
                         "antes de concluir que o órgão não arrecadou.")
    r = {"total": total, "registros": registros[:maximo], "somas_por_orgao": somas, "ressalvas": ressalvas}
    if faltas:
        r["incompleta"] = "a Centi entregou menos linhas que declarou em " + "; ".join(faltas)
    return r
