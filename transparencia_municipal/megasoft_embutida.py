"""Acesso à Megasoft embutida no portal NucleoGov (menus `mgservidores`, `mgdespesas`, `mgreceitas`, `contratos_mg`,
`licitacoes_mg` e `sgdiarias`). Encaixe do ticket 03; único arquivo dele.

O `Portal` manda para cá a folha, as despesas, as receitas, os contratos e as licitações quando o menu aponta a
Megasoft e a API NucleoGov não serve o módulo, e as diárias quando o menu é `sgdiarias`. O contrato dos encaixes está
em megasoft_propria.py; o dos módulos extras, no ticket 01 dos módulos extras.

Folha e despesas:

Vai pela própria API NucleoGov do portal, no envelope `multi_request`, com `acao = megasoft/servidores` ou
`megasoft/empenhos`; paginação por `pagina` (a partir de 1), `tamanhoDaPagina` e `ordenacao: {}`. Medido em Aruanã
(04/11/2026): o `limit` que o envelope NucleoGov acrescenta é ignorado; 5.000 por página foram aceitos; o período
das despesas é respeitado; o filtro de fornecedor não filtra no servidor (medição anterior), por isso CNPJ e nome são filtrados
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
from .traducao_megasoft import FONTE, _br, _data, despesa, linha_da_folha

POR_PAGINA = 5000


def _ler(portal, acao, filtros, *, maximo, campo_chave, progresso=None):
    """Páginas de `acao` até o total anunciado ou `maximo`. Devolve (total anunciado, registros sem repetidos).

    Repetido é o registro com o mesmo `campo_chave` (`codigo` no empenho, `chave` na folha); sem ele, o registro
    inteiro. O total anunciado conta chaves distintas (medição anterior).
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



# ── módulos extras (ticket 03): interface no ticket 01 dos módulos extras, `## Comments` ─────────────────────────
#
# Medido em Aruanã (04/11/2026; desenho dos módulos extras, descoberta B, e o ticket 03):
# - receitas: `megasoft/receitas`, paginada como a folha; 09/2025 deu 133 linhas de 9 órgãos, todas com `chave` 2025/09;
# - diárias (`sgdiarias`), contratos (`contratos_mg`) e licitações (`licitacoes_mg`) são módulos do próprio NucleoGov,
#   paginados pelo `limit` do envelope (páginas de 100 sem repetir; 700 numa página só também);
# - diárias: o período (`datamin`/`datamax`, aaaa-mm-dd) recorta pela saída (646 no 1º trimestre de 2025, nenhuma fora);
#   `txtbusca` filtra (408 de 646 com "GOIANIA", todas casando); `valor` é o da linha (cresce com a quantidade); em 3
#   delas a quantidade veio com seis dígitos; o `total` de cada linha é a contagem da consulta, não dinheiro;
# - contratos: `ano` filtra (245 em 2025; sem ano, 1.550 de todos os anos); `txtbusca` zera a resposta e `objeto`
#   filtra (21 de 245, todos casando); `orgao` vem só como código;
# - licitações: `ano` (o da licitação) e `dispensas` filtram (40 e 1.078 em 2025); `descricao` filtra (9, todas
#   casando); o período por data (`datapub_min`/`datapub_max`) dá erro.

#: `sgdiarias` é módulo do próprio NucleoGov; os `*_mg` e `megasoft/*` trazem os dados da Megasoft
FONTE_SG = "NucleoGov"
#: quantidade de diárias acima disto numa linha não é plausível (Aruanã: três linhas com seis dígitos)
DIARIAS_PLAUSIVEIS = 31


def receitas(portal, *, ano, mes, maximo):
    """Receitas de `mes`/`ano` (int), com os nomes comuns de receitas (`acao = megasoft/receitas`).

    Sem `codigoDoOrgao`, vêm todas as entidades. Cada linha tem de ser do mês pedido; senão, `ErroPortal`.
    """
    # repetido é o registro inteiro: a `chave` não traz a fonte do recurso, e a mesma receita vem uma vez por fonte
    total, registros = _ler(portal, "megasoft/receitas", {"ano": str(ano), "mes": f"{mes:02d}"}, maximo=maximo,
                            campo_chave=None)
    fora = [r.get("chave") for r in registros if _competencia(r.get("chave")) != (ano, mes)]
    if fora:
        raise ErroPortal(f"{portal.url} devolveu {len(fora)} receitas de outro mês ao pedir {mes:02d}/{ano} "
                         f"(ex.: {fora[0]}); a resposta misturaria meses. Tente de novo.")
    return {"total": total, "registros": [_receita(r, ano, mes) for r in registros[:maximo]],
            "ressalvas": ["as receitas deste portal trazem todas as entidades juntas (Prefeitura, Câmara, fundos e "
                          "previdência): o campo orgao diz de qual órgão é cada linha; some por órgão"]}


def _competencia(chave):
    try:
        return int(chave["ano"]), int(chave["mes"])
    except (TypeError, KeyError, ValueError):
        return None


def _receita(reg, ano, mes):
    natureza = str(reg.get("naturezaDaReceita") or "")
    return {
        "orgao": reg.get("orgaoUnidadeGestora") or None, "codigo": natureza.split(" - ")[0].strip() or None,
        "receita": reg.get("receita") or None, "fonte_recurso": reg.get("fonteDaReceita") or None,
        "valor_orcado": _br(reg.get("valorOrcado")), "valor_previsto_atualizado": None,
        "valor_arrecadado_mes": _br(reg.get("arrecadacao")),
        "valor_arrecadado_ate_mes": _br(reg.get("valorAcumulado")),
        "ano": ano, "mes": mes, "analitica": None, "fonte": FONTE,
    }


def diarias(portal, *, de, ate, busca, maximo):
    """Diárias com saída de `de` a `ate` (`datetime.date`), com os nomes comuns de diárias (`acao = sgdiarias/listar`).

    `busca` vai no `txtbusca` do sistema, que procura em todos os campos.
    """
    filtros = {"datamin": de.isoformat(), "datamax": ate.isoformat()}
    if busca:
        filtros["txtbusca"] = busca
    r = portal.consultar("sgdiarias/listar", filtros, maximo=maximo)
    linhas = [_diaria(x) for x in r["registros"]]
    saida = {"total": r["total"], "registros": linhas}
    estranhas = sum(1 for x in linhas if not str(x["quantidade"] or "").isdigit()
                    or int(x["quantidade"]) > DIARIAS_PLAUSIVEIS)
    if estranhas:
        saida["ressalvas"] = [f"{estranhas} diária{'s' if estranhas > 1 else ''} com a quantidade vazia ou impossível "
                              f"(mais de {DIARIAS_PLAUSIVEIS} numa linha), como o portal publicou: conte pelas linhas "
                              "e use o valor, que é o total da linha"]
    return saida


def _diaria(reg):
    quantidade = reg.get("quantidade")
    return {
        "favorecido": reg.get("favorecido") or None, "matricula": None, "cargo": reg.get("cargo") or None,
        "orgao": reg.get("orgao_nome") or None, "destino": reg.get("destino") or reg.get("cidade") or None,
        "motivo": reg.get("descricao") or None, "data_saida": _data(reg.get("data_inicio")) or None,
        "data_chegada": _data(reg.get("data_fim")) or None,
        "quantidade": None if quantidade in (None, "") else str(quantidade), "valor": _br(reg.get("valor")),
        "valor_unitario": None, "empenho": reg.get("numero_empenho") or reg.get("numero_processo") or None,
        "fonte": FONTE_SG,
    }


def contratos(portal, *, ano, tipo, busca, maximo):
    """Contratos do `ano` (int ou None: todos os anos) (`acao = contratos_mg/listar`). `busca` procura no objeto.

    Aditivos: a consulta não foi medida, e o pedido é recusado.
    """
    if tipo != "contrato":
        raise ValueError(f"tipo={tipo!r}: neste portal (Megasoft embutida) só os contratos foram medidos, não os "
                         "aditivos; consulte tipo='contrato'")
    filtros = {"ano": str(ano)} if ano else {}
    ressalvas = ["o campo orgao dos contratos deste portal é o código do órgão no portal: o sistema não dá o nome"]
    if busca:  # medido: `txtbusca` zera a resposta; `objeto` filtra
        filtros["objeto"] = busca
        ressalvas.append("a busca dos contratos deste portal procura só no objeto do contrato "
                         "(não no fornecedor nem no número)")
    r = portal.consultar("contratos_mg/listar", filtros, maximo=maximo)
    return {"total": r["total"], "registros": [_contrato(x) for x in r["registros"]], "ressalvas": ressalvas}


def _contrato(reg):
    orgao = reg.get("orgao")
    return {
        "numero": reg.get("numero") or None, "ano": reg.get("ano"),
        "orgao": None if orgao in (None, "") else str(orgao), "situacao": reg.get("situacao") or None,
        "objeto": reg.get("objeto") or None, "fornecedor": reg.get("fornecedor_nome") or None,
        "cpf_cnpj": reg.get("fornecedor_cpfcnpj") or None, "valor": reg.get("valor") or None,
        "valor_executado": reg.get("valor_executado") or None, "saldo": reg.get("saldo") or None,
        "data_publicacao": reg.get("data_publicacao") or None, "data_assinatura": reg.get("data_firmatura") or None,
        "inicio_vigencia": reg.get("inicio_vigencia") or None, "fim_vigencia": reg.get("fim_vigencia") or None,
        "licitacao": reg.get("licitacao_label") or None, "fiscal": reg.get("fiscal_contrato") or None, "fonte": FONTE,
    }


def licitacoes(portal, *, busca, dispensas, ano, maximo):
    """Licitações ou dispensas do `ano` (int ou None: todos os anos) (`acao = licitacoes_mg/listarCidadao`).

    `busca` procura na descrição. O período por data dá erro no sistema: não é usado, e toda resposta diz isso.
    """
    filtros = {"dispensas": 1 if dispensas else 0, "fracassadas_desertas": 0, "abertas": 0}
    if ano:
        filtros["ano"] = str(ano)
    if busca:
        filtros["descricao"] = busca
    r = portal.consultar("licitacoes_mg/listarCidadao", filtros, maximo=maximo)
    return {"total": r["total"], "registros": [_licitacao(x) for x in r["registros"]],
            "ressalvas": ["as licitações deste portal só filtram por ano, e é o ano da licitação, não o da publicação "
                          "(algumas foram publicadas no ano anterior): o filtro por período de datas dá erro no sistema",
                          "os chamamentos públicos vêm tanto nas licitações quanto nas dispensas: ao juntar as duas "
                          "listas, não os conte duas vezes"]}


def _licitacao(reg):
    return {
        "numero": reg.get("label") or reg.get("numero") or None, "ano": reg.get("ano"),
        "modalidade": reg.get("modalidade") or None, "situacao": reg.get("situacao") or None,
        "orgao": reg.get("orgao") or None, "objeto": reg.get("descricao") or None,
        "data_publicacao": reg.get("data_publicacao") or None, "data_abertura": reg.get("data_abertura") or None,
        "data_julgamento": reg.get("data_julgamento") or None, "data_homologacao": reg.get("data_homologacao") or None,
        "valor_vencedor": reg.get("valor_vencedor_total") or None, "fonte": FONTE,
    }
