"""Acesso ao sistema de gestão (SG) integrado ao portal NucleoGov (menus `sgservidores`, `sgdespesas`, `sgreceitas`).

O `Portal` manda para cá a folha, as despesas e as receitas quando o menu aponta o SG: nesses portais a API NucleoGov
comum (`servidores_frl`...) responde zero, sem erro. Contratos e licitações do SG (`sgcontratos`, `sglicitacoes`)
ainda não foram medidos e são recusados. As diárias `sgdiarias` seguem no encaixe da Megasoft embutida.

Vai pela própria API NucleoGov do portal, no envelope `multi_request`, com `acao = sg<modulo>/listar`, paginado pelo
`limit` do envelope. Medido em Anápolis (05/11/2026; desenho em docs/design/2026-11-05-nucleogov-sg.md):
- folha: `ano` + `mes` respeitados; 06/2025 deu 7.604 linhas, uma por servidor, lidas em páginas de 1.000 sem
  repetir; `orgao` filtra (o nome do órgão vem na linha; vazio no órgão principal);
- despesas: o documento pode vir formatado (Anápolis) ou só com dígitos e sem zeros à esquerda (Águas Lindas);
  uma linha por movimento (Empenho, Liquidação, Pagamento; 4.698 em 06/2025, de 2.001 empenhos); `tipo` 0
  traz só os empenhos; `ano` + `datamin`/`datamax` (aaaa-mm-dd) recortam pela data; **só com `ano`, o portal devolve o
  mês mais recente**; `cpf_cnpj` filtra (45 de 45); os valores da linha são os do momento do movimento (o empenho
  traz liquidado e pago zerados);
- receitas: `ano` + `mes`; todos os órgãos juntos (16 em 06/2025); conta sem movimento no mês vem com `mes` nulo e
  arrecadação zero.
"""
from __future__ import annotations

import calendar
import time
from datetime import date, datetime, timedelta

from .cliente import ErroPortal
from .folha_leve import _comparavel
from .traducao_megasoft import _br, _data

FONTE = "NucleoGov (sistema de gestão)"
#: `maximo` de quem precisa do período inteiro (para filtrar aqui)
TUDO = 10**9


#: páginas de 1.000 lidas sem repetir nem perder em Anápolis (folha de 06/2025: 7.604 em 8 páginas)
POR_PAGINA = 1000


def _ler(portal, acao, filtros, *, maximo, progresso=None):
    """Lê em páginas de POR_PAGINA (o portal guarda o próprio tamanho de página para as outras consultas)."""
    antes, portal.por_pagina = portal.por_pagina, POR_PAGINA
    try:
        r = portal.consultar(acao, filtros, maximo=maximo, progresso=progresso)
    finally:
        portal.por_pagina = antes
    return r["total"], r["registros"]


def _incompleta(o_que, lidos, total):
    return ErroPortal(f"a leitura {o_que} veio incompleta: {lidos} de {total} registros; filtrar sobre ela "
                      "esconderia o que faltou. Tente de novo.")


# ── folha ─────────────────────────────────────────────────────────────────

def _tipo_folha(tipo):
    """'Folha Normal' é a folha mensal: o rótulo leva "Mensal" para o resumo contar a linha."""
    return f"Mensal ({tipo})" if _comparavel(tipo) == "folha normal" else tipo


def linha_da_folha(reg):
    return {
        "nome": reg.get("nome"), "matricula": reg.get("matricula"), "cpf": reg.get("cpf_mascarado"),
        "cargo": reg.get("cargo") or reg.get("funcao"), "lotacao": reg.get("lotacao") or reg.get("local_trabalho"),
        "vinculo": reg.get("vinculo"), "tipo_folha": _tipo_folha(reg.get("tipo")),
        "data_admissao": _data(reg.get("data_admissao")), "data_demissao": _data(reg.get("data_desligamento")),
        "carga_horaria": reg.get("carga_horaria"), "total_proventos": _br(reg.get("proventos")),
        "total_desconto": _br(reg.get("descontos")), "total_liquido": _br(reg.get("liquido")),
        "ano": reg.get("ano"), "mes": reg.get("mes"), "orgao": reg.get("orgao") or None,
        "situacao": reg.get("situacao_servidor"), "fonte": FONTE,
    }


def _do_mes(reg, ano, mes):
    return str(reg.get("ano")) == str(ano) and str(reg.get("mes")).lstrip("0") == str(mes)


def folha(portal, *, ano, mes, busca, maximo, progresso=None):
    """Linhas da folha de `mes`/`ano` (int; `mes` None é recusado). `busca`: nome do servidor, filtrado aqui."""
    if mes is None:
        raise ValueError("a folha do sistema de gestão é lida por mês: informe o mês")
    total, registros = _ler(portal, "sgservidores/listar", {"ano": str(ano), "mes": str(mes)},
                            maximo=TUDO if busca else maximo, progresso=progresso)
    fora = [r for r in registros if not _do_mes(r, ano, mes)]
    if fora:
        raise ErroPortal(f"{portal.url} devolveu {len(fora)} linha(s) da folha de outro mês ao pedir {mes:02d}/{ano} "
                         f"(ex.: {fora[0].get('mes')}/{fora[0].get('ano')}); a resposta misturaria meses.")
    linhas = [linha_da_folha(r) for r in registros]
    if busca:
        if len(linhas) != total:
            raise _incompleta(f"da folha de {mes:02d}/{ano}", len(linhas), total)
        linhas = [x for x in linhas if _comparavel(busca) in _comparavel(x["nome"])]
        total = len(linhas)
    return {"total": total, "registros": linhas[:maximo]}


# ── despesas ──────────────────────────────────────────────────────────────

RESSALVA_MOVIMENTOS = ("neste portal (sistema de gestão integrado ao NucleoGov), a liquidação e o pagamento são "
                       "movimentos separados do empenho: valor_liquidado e valor_pago ficam vazios, e a lista traz os "
                       "empenhos emitidos no período, com o valor empenhado")


def _meses(de, ate):
    """Janelas mensais (date, date) que cobrem de `de` a `ate`."""
    inicio = de
    while inicio <= ate:
        ultimo = date(inicio.year, inicio.month, calendar.monthrange(inicio.year, inicio.month)[1])
        yield inicio, min(ultimo, ate)
        inicio = ultimo + timedelta(days=1)


def _dia(texto):
    try:
        return datetime.strptime(str(texto or ""), "%d/%m/%Y").date()
    except ValueError:
        return None


def _digitos(texto):
    return "".join(c for c in str(texto or "") if c.isdigit())


def _documento(texto):
    """CPF ou CNPJ formatado. Em Águas Lindas (05/11/2026) o documento vem só com dígitos e sem os zeros à esquerda:
    12 ou 13 dígitos só podem ser CNPJ (o CPF tem 11). Outro formato fica como veio."""
    d = _digitos(texto)
    if 12 <= len(d) <= 14 and len(d) == len(str(texto).strip()):
        d = d.zfill(14)
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    if 9 <= len(d) <= 11 and len(d) == len(str(texto).strip()):
        d = d.zfill(11)
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    return texto or None


def despesa(reg):
    return {
        "empenho": reg.get("numero") or reg.get("empenho"), "data": reg.get("data"),
        "cpf_cnpj": _documento(reg.get("cpf_cnpj")), "fornecedor": reg.get("fornecedor") or None,
        "valor_empenhado": reg.get("valor_empenho") or reg.get("valor") or None,
        "valor_liquidado": None, "valor_pago": None, "historico": reg.get("descricao") or None,
        "orgao": reg.get("orgao") or None, "fonte": FONTE,
    }


def despesas(portal, *, de, ate, cnpj, busca, maximo):
    """Empenhos emitidos de `de` a `ate` (dd/mm/aaaa), mês a mês. `cnpj` formatado ou None (filtro do portal,
    conferido aqui); `busca`: nome do fornecedor, filtrado aqui sobre o período inteiro."""
    inicio, fim = _dia(de), _dia(ate)
    achados, total = [], 0
    for i, (a, b) in enumerate(_meses(inicio, fim)):
        if i:
            time.sleep(portal.pausa)
        filtros = {"ano": str(a.year), "datamin": a.isoformat(), "datamax": b.isoformat(), "tipo": "0"}
        if cnpj:
            filtros["cpf_cnpj"] = cnpj
        resta = TUDO if busca else max(maximo - len(achados), 1)
        total_mes, registros = _ler(portal, "sgdespesas/listar", filtros, maximo=resta)
        fora = [r for r in registros if r.get("tipo") != "0" or not (d := _dia(r.get("data"))) or not a <= d <= b]
        if fora:
            raise ErroPortal(f"{portal.url} devolveu {len(fora)} movimento(s) fora do período ou que não são empenho "
                             f"ao pedir {a:%d/%m/%Y} a {b:%d/%m/%Y} (ex.: {fora[0].get('movimento')} de "
                             f"{fora[0].get('data')}): o filtro não foi respeitado e nada foi devolvido.")
        if cnpj and any(_digitos(r.get("cpf_cnpj")).zfill(14) != _digitos(cnpj) for r in registros):
            raise ErroPortal(f"{portal.url} ignorou o filtro de CNPJ nas despesas: nada foi devolvido.")
        if busca:
            if len(registros) != total_mes:
                raise _incompleta(f"dos empenhos de {a:%d/%m/%Y} a {b:%d/%m/%Y}", len(registros), total_mes)
            registros = [r for r in registros if _comparavel(busca) in _comparavel(r.get("fornecedor"))]
            total_mes = len(registros)
        total += total_mes
        achados += [despesa(r) for r in registros]
    return {"total": total, "registros": achados[:maximo], "ressalvas": [RESSALVA_MOVIMENTOS]}


# ── receitas ──────────────────────────────────────────────────────────────

def _receita(reg, ano, mes):
    return {
        "orgao": reg.get("orgao_nome") or None, "codigo": reg.get("codigo") or None,
        "receita": reg.get("descricao") or None, "fonte_recurso": None,
        "valor_orcado": _br(reg.get("valor_orcado")), "valor_previsto_atualizado": None,
        "valor_arrecadado_mes": _br(reg.get("arrecadacao")),
        "valor_arrecadado_ate_mes": _br(reg.get("valor_arrecado_periodo")),
        "ano": ano, "mes": mes, "analitica": None, "fonte": FONTE,
    }


def receitas(portal, *, ano, mes, maximo):
    """Receitas de `mes`/`ano` (int), de todos os órgãos. Linha de outro mês ou ano: `ErroPortal`."""
    total, registros = _ler(portal, "sgreceitas/listar", {"ano": str(ano), "mes": str(mes)}, maximo=maximo)
    fora = [r for r in registros
            if str(r.get("ano")) != str(ano) or (r.get("mes") is not None and not _do_mes(r, ano, mes))]
    if fora:
        raise ErroPortal(f"{portal.url} devolveu {len(fora)} receita(s) de outro mês ao pedir {mes:02d}/{ano} "
                         f"(ex.: {fora[0].get('mes')}/{fora[0].get('ano')}); a resposta misturaria meses.")
    return {"total": total, "registros": [_receita(r, ano, mes) for r in registros[:maximo]],
            "ressalvas": ["as receitas deste portal trazem todos os órgãos juntos (Prefeitura, fundos, previdência): "
                          "o campo orgao diz de qual órgão é cada linha; some por órgão",
                          "conta sem movimento no mês vem com a arrecadação do mês zerada"]}
