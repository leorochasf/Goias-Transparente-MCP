"""Acesso à Megasoft embutida no portal NucleoGov (menu `mgservidores`, `mgdespesas`). Encaixe do ticket 03; único
arquivo dele.

O `Portal` manda para cá a folha ou as despesas quando o menu aponta a Megasoft e a API NucleoGov não serve o
módulo. O contrato dos encaixes está em megasoft_propria.py.

Vai pela própria API NucleoGov do portal, no envelope `multi_request`, com `acao = megasoft/servidores` ou
`megasoft/empenhos`; paginação por `pagina` (a partir de 1), `tamanhoDaPagina` e `ordenacao: {}`. Medido em Aruanã
(04/11/2026): o `limit` que o envelope NucleoGov acrescenta é ignorado; 5.000 por página foram aceitos; o período
das despesas é respeitado; o filtro de fornecedor não filtra no servidor (AJE), por isso CNPJ e nome são filtrados
aqui; e a fronteira de página repete um empenho e perde outro (ano de 2025 em 2 páginas: 7.481 lidos, 7.480
distintos; fev/2025 em páginas de 100: 567 linhas, 534 códigos). Com filtro, a leitura vai mês a mês, cada mês
numa página só.
"""
from __future__ import annotations

import calendar
import json
import time
from datetime import date, datetime, timedelta

from .cliente import ErroPortal
from .folha_leve import _comparavel
from .traducao_megasoft import despesa, linha_da_folha

POR_PAGINA = 5000


def _ler(portal, acao, filtros, *, maximo, campo_chave, progresso=None):
    """Páginas de `acao` até o total anunciado ou `maximo`. Devolve (total anunciado, registros sem repetidos).

    Repetido é o registro com o mesmo `campo_chave` (`codigo` no empenho, `chave` na folha); sem ele, o registro
    inteiro. O total anunciado conta chaves distintas (AJE).
    """
    tamanho = min(maximo, POR_PAGINA)
    registros, vistos, total, pagina = [], set(), 0, 1
    while True:
        lote, total_da_pagina = portal._pagina(
            acao, {**filtros, "pagina": pagina, "tamanhoDaPagina": tamanho, "ordenacao": {}}, 0)
        total = total_da_pagina if pagina == 1 else total
        for reg in lote:
            chave = json.dumps(reg.get(campo_chave) or reg, sort_keys=True, ensure_ascii=False)
            if chave not in vistos:
                vistos.add(chave)
                registros.append(reg)
        if progresso:
            progresso(len(registros), total)
        if len(lote) < tamanho or pagina * tamanho >= total or len(registros) >= maximo:
            return total, registros
        pagina += 1
        time.sleep(portal.pausa)


def _incompleta(o_que, lidos, total):
    return ErroPortal(f"a leitura {o_que} veio incompleta: {lidos} de {total} registros; filtrar sobre ela "
                      "esconderia o que faltou. Tente de novo.")


def folha(portal, *, ano, mes, busca, maximo, progresso=None):
    """Linhas da folha de `mes`/`ano` (int; `mes` None é recusado). `busca`: nome do servidor ou None.

    `progresso(lidas, total)`, se dado, é chamado depois de cada página (a leitura do mês avisa o assistente).
    A busca por nome é feita aqui, sobre o mês inteiro.
    """
    if mes is None:
        raise ValueError("a folha da Megasoft embutida é lida por mês: informe o mês")
    filtros = {"mes": f"{mes:02d}", "ano": str(ano), "mesInteger": mes}
    total, registros = _ler(portal, "megasoft/servidores", filtros, maximo=float("inf") if busca else maximo,
                            campo_chave="chave", progresso=progresso)
    linhas = [linha_da_folha(r) for r in registros]
    if busca:
        if len(linhas) != total:
            raise _incompleta(f"da folha de {mes:02d}/{ano}", len(linhas), total)
        linhas = [x for x in linhas if _comparavel(busca) in _comparavel(x["nome"])]
        total = len(linhas)
    return {"total": total, "registros": linhas[:maximo]}


def _meses(de, ate):
    """Janelas mensais (dd/mm/aaaa) que cobrem de `de` a `ate`."""
    inicio, fim = (datetime.strptime(d, "%d/%m/%Y").date() for d in (de, ate))
    while inicio <= fim:
        ultimo = date(inicio.year, inicio.month, calendar.monthrange(inicio.year, inicio.month)[1])
        yield inicio.strftime("%d/%m/%Y"), min(ultimo, fim).strftime("%d/%m/%Y")
        inicio = ultimo + timedelta(days=1)


def despesas(portal, *, de, ate, cnpj, busca, maximo):
    """Empenhos de `de` a `ate` (dd/mm/aaaa). `cnpj` formatado ou None; `busca`: nome do fornecedor ou None.

    Sem filtro: uma leitura do período, até `maximo`. Com filtro: o período inteiro, mês a mês, filtrado aqui.
    """
    if not (cnpj or busca):
        total, registros = _ler(portal, "megasoft/empenhos", {"dataInicial": de, "dataFinal": ate},
                                maximo=maximo, campo_chave="codigo")
        return {"total": total, "registros": [despesa(r) for r in registros[:maximo]]}
    achados = []
    for i, (inicio, fim) in enumerate(_meses(de, ate)):
        if i:
            time.sleep(portal.pausa)
        total, registros = _ler(portal, "megasoft/empenhos", {"dataInicial": inicio, "dataFinal": fim},
                                maximo=float("inf"), campo_chave="codigo")
        if len(registros) != total:
            raise _incompleta(f"dos empenhos de {inicio} a {fim}", len(registros), total)
        for x in map(despesa, registros):
            if (x["cpf_cnpj"] == cnpj) if cnpj else _comparavel(busca) in _comparavel(x["fornecedor"]):
                achados.append(x)
    return {"total": len(achados), "registros": achados[:maximo]}
