"""Acesso à contabilidade Centi integrada ao portal NucleoGov (menu `cntdespesas`). Encaixe do ticket 04; único
arquivo dele, com a tradução Centi → formato de despesas do projeto (o mesmo de `traducao_megasoft.despesa`).

O `Portal` manda para cá as despesas quando o menu aponta a Centi e a API NucleoGov não serve o módulo. A Centi não
tem folha: sem função `folha`, o `Portal` recusa. O contrato dos encaixes está em megasoft_propria.py.

Medido em Posse (04/11/2026):
- `POST {portal}/api/centi`, formulário simples (sem `multi_request`), `acao=empenhos`, `id_orgao=0` (todas as
  entidades), `data_inicio`/`data_fim` em dd/mm/aaaa. Resposta: lista inteira do período, sem páginas; cada registro
  traz `TotalRegistros`, o total declarado.
- O período é respeitado. A mesma página chama `relatorioEmpenhos`, que só devolve três somas
  (`total_empenhado` = soma de `ValorEmpenhado` − `ValorAnulacao`, conferido ao centavo em 01 e 02/2025).
- O filtro `cpf_cnpj` da Centi devolve lista vazia para um CNPJ que tem empenhos: não é mandado; o CNPJ é filtrado aqui.
"""
from __future__ import annotations

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


def _empenhos(portal, de, ate):
    """A lista crua da Centi para o período."""
    corpo = urllib.parse.urlencode({**FILTROS, "data_inicio": de, "data_fim": ate, "acao": "empenhos"})
    try:
        r = portal.sessao.post(
            f"{portal.url}/api/centi", data=corpo, timeout=portal.timeout,
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
        lista = r.json()
    except ValueError:
        lista = None
    if not isinstance(lista, list):
        raise ErroPortal(f"{portal.url} devolveu resposta inesperada na Centi (acao=empenhos; "
                         f"{len(r.content)} bytes, começa com {r.text[:80]!r})")
    return lista


def _sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFKD", str(texto or "")) if not unicodedata.combining(c)).casefold()


def _dia(texto):
    try:
        return datetime.strptime(str(texto), "%d/%m/%Y").date()
    except ValueError:
        return None


def _total_declarado(portal, lista):
    """`TotalRegistros`, que todo registro traz e é o mesmo em todos; senão a resposta não é a que conhecemos."""
    totais = {x.get("TotalRegistros") if isinstance(x, dict) else None for x in lista}
    total = totais.pop() if len(totais) == 1 else None
    if not isinstance(total, int) or isinstance(total, bool):
        raise ErroPortal(f"{portal.url} devolveu empenhos da Centi sem um total declarado único "
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
