"""Acesso ao sistema de gestão (SG) integrado ao portal NucleoGov (menus `sgservidores`, `sgdespesas`, `sgreceitas`).

O `Portal` manda para cá a folha, as despesas, as receitas, os contratos e as licitações quando o menu aponta o SG
(`sgservidores`, `sgdespesas`, `sgreceitas`, `sgcontratos`, `sglicitacoes`): nesses portais a API NucleoGov comum
(`servidores_frl`...) responde zero, sem erro. As diárias `sgdiarias` seguem no encaixe da Megasoft embutida.

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
import json
import time
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

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


def _cpf_valido(d):
    if len(d) != 11 or len(set(d)) == 1:
        return False
    for n in (9, 10):
        soma = sum(int(d[i]) * (n + 1 - i) for i in range(n))
        if (soma * 10 % 11) % 10 != int(d[n]):
            return False
    return True


def _cnpj_valido(d):
    if len(d) != 14 or len(set(d)) == 1:
        return False
    for n, pesos in ((12, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]), (13, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])):
        resto = sum(int(d[i]) * pesos[i] for i in range(n)) % 11
        if (0 if resto < 2 else 11 - resto) != int(d[n]):
            return False
    return True


def _documento(texto):
    """CPF ou CNPJ formatado. Em Águas Lindas e Caldas Novas (05/11/2026) o documento vem só com dígitos e sem os
    zeros à esquerda (o CNPJ do Banco do Brasil vira "191"): os dígitos verificadores dizem se é CPF ou CNPJ. Já
    formatado, ou sem verificador que feche, fica como veio."""
    bruto = str(texto or "").strip()
    if not bruto.isdigit() or len(bruto) > 14:
        return texto or None
    cpf, cnpj = len(bruto) <= 11 and _cpf_valido(bruto.zfill(11)), _cnpj_valido(bruto.zfill(14))
    if cpf and cnpj:  # "191" fecha nos dois: com 8 dígitos ou menos, um CPF teria 3 zeros ou mais à frente
        cpf = len(bruto) > 8
    if cpf:
        d = bruto.zfill(11)
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    if cnpj:
        d = bruto.zfill(14)
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return texto


def despesa(reg):
    return {
        "empenho": reg.get("numero") or reg.get("empenho"), "data": reg.get("data"),
        "cpf_cnpj": _documento(reg.get("cpf_cnpj")), "fornecedor": reg.get("fornecedor") or None,
        "valor_empenhado": reg.get("valor_empenho") or reg.get("valor") or None,
        "valor_liquidado": None, "valor_pago": None, "historico": reg.get("descricao") or None,
        "orgao": reg.get("orgao") or None, "fonte": FONTE,
    }


RESSALVA_SOMAS = ("somas_do_periodo são as somas do próprio portal para o período pedido, pelos movimentos: o "
                  "liquidado e o pago incluem liquidações e pagamentos do período de empenhos anteriores a ele")
#: movimentos que entram no liquidado e no pago de um empenho
MOVIMENTOS = {"Empenho": None, "Liquidação": "liquidado", "Pagamento": "pago"}


def _numero(texto):
    """'1.234,56' → Decimal; vazio ou ilegível → None."""
    try:
        return Decimal(str(texto).replace(".", "").replace(",", ".")) if texto not in (None, "") else None
    except InvalidOperation:
        return None


def _somas(portal, filtros):
    """As somas do período (`relatorioTotais`), com os mesmos filtros da listagem, sem o tipo."""
    return portal._envelope("sgdespesas/relatorioTotais", {k: v for k, v in filtros.items() if k != "tipo"})


def _ate_hoje(portal, empenhos, inicio, documento):
    """Liquidado e pago de cada empenho (registro do portal), somando as liquidações e os pagamentos do fornecedor
    de `inicio` até hoje. Devolve (chave_empenho → (liquidado, pago) ou None, número de empenhos com movimento
    desconhecido)."""
    hoje = date.today()
    filtros = {"ano": str(inicio.year), "datamin": inicio.isoformat(), "datamax": hoje.isoformat(),
               "cpf_cnpj": documento}
    total, movimentos = _ler(portal, "sgdespesas/listar", filtros, maximo=TUDO)
    if len(movimentos) != total:
        raise _incompleta(f"dos movimentos do fornecedor até {hoje:%d/%m/%Y}", len(movimentos), total)
    chaves = {r.get("chave_empenho") for r in empenhos}
    somas = {c: {"liquidado": Decimal(0), "pago": Decimal(0)} for c in chaves}
    estranhos = set()
    for m in movimentos:
        chave = m.get("chave_empenho")
        if chave not in chaves:
            continue
        campo = MOVIMENTOS.get(m.get("movimento"), "?")
        valor = _numero(m.get("valor_mov"))
        if campo == "?" or (campo and valor is None):
            estranhos.add(chave)
        elif campo:
            somas[chave][campo] += valor
    return {c: None if c in estranhos else (s["liquidado"], s["pago"]) for c, s in somas.items()}, len(estranhos)


def despesas(portal, *, de, ate, cnpj, busca, maximo):
    """Empenhos emitidos de `de` a `ate` (dd/mm/aaaa), mês a mês, e as somas do período. `cnpj` formatado ou None
    (filtro do portal, conferido aqui); com ele, cada empenho traz o liquidado e o pago até hoje. `busca`: nome do
    fornecedor, filtrado aqui sobre o período inteiro (sem somas: o portal não filtra pelo nome)."""
    inicio, fim = _dia(de), _dia(ate)
    achados, total = [], 0
    documento = cnpj
    somas = {"empenhado": Decimal(0), "liquidado": Decimal(0), "pago": Decimal(0)}
    for i, (a, b) in enumerate(_meses(inicio, fim)):
        if i:
            time.sleep(portal.pausa)
        filtros = {"ano": str(a.year), "datamin": a.isoformat(), "datamax": b.isoformat(), "tipo": "0"}
        if documento:
            filtros["cpf_cnpj"] = documento
        resta = TUDO if busca else max(maximo - len(achados), 1)
        total_mes, registros = _ler(portal, "sgdespesas/listar", filtros, maximo=resta)
        if cnpj and not registros and documento == cnpj and cnpj.startswith("0"):
            # Caldas Novas (05/11/2026): o portal guarda o CNPJ só com dígitos e sem os zeros à esquerda; com
            # pontuação o filtro dá zero, e sem os zeros traz os empenhos (em Anápolis, com pontuação funciona)
            time.sleep(portal.pausa)
            filtros["cpf_cnpj"] = _digitos(cnpj).lstrip("0")
            total_mes, registros = _ler(portal, "sgdespesas/listar", filtros, maximo=resta)
            if registros:
                documento = filtros["cpf_cnpj"]
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
        elif somas is not None:
            time.sleep(portal.pausa)
            do_mes = _somas(portal, filtros)
            for nosso, do_portal in (("empenhado", "total_empenhado"), ("liquidado", "total_liquidado"),
                                     ("pago", "total_pago")):
                valor = _numero(do_mes.get(do_portal)) if isinstance(do_mes, dict) else None
                if valor is None:
                    somas = None
                    break
                somas[nosso] += valor
        total += total_mes
        achados += registros
    achados = achados[:maximo]
    saida = {"total": total, "registros": [despesa(r) for r in achados], "ressalvas": []}
    if cnpj and achados:
        time.sleep(portal.pausa)
        valores, estranhos = _ate_hoje(portal, achados, inicio, documento)
        for x, r in zip(saida["registros"], achados):
            v = valores.get(r.get("chave_empenho"))
            if v:
                x["valor_liquidado"], x["valor_pago"] = _br(v[0]), _br(v[1])
        saida["ressalvas"].append(f"valor_liquidado e valor_pago somam as liquidações e os pagamentos de cada empenho "
                                  f"até {date.today():%d/%m/%Y}, também os feitos depois do período pedido")
        if estranhos:
            saida["ressalvas"].append(f"{estranhos} empenho(s) com movimento que não é liquidação nem pagamento (ex.: "
                                      "anulação): liquidado e pago ficam vazios neles; confira no portal")
    else:
        saida["ressalvas"].append(RESSALVA_MOVIMENTOS)
    if not busca and somas is not None:
        saida["somas_do_periodo"] = {k: _br(v) for k, v in somas.items()}
        saida["ressalvas"].append(RESSALVA_SOMAS)
    return saida


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


# ── contratos e licitações ────────────────────────────────────────────────
#
# Medido em Anápolis (05/11/2026): `sgcontratos/listar` com `ano` (360 em 2025; 597 em 2024; sem ano, 12.584);
# contratos e aditivos vêm juntos (`tabela` "contratos"/"aditivos"); `tipo` filtra ("Contrato" 138, "Aditivo" 87;
# há ainda "Convênio", "Registro de Preço", "Contrato de Comodato" e "Distrato"); `objeto` filtra; os contratados
# vêm numa lista JSON (`contratados`). `sglicitacoes/listar` com `ano` (o da licitação, 80 em 2025); com
# `onlyDispensas`, as dispensas e inexigibilidades (129 em 2025); `descricao` filtra (44 de 44).

def _contratados(reg):
    try:
        lista = json.loads(reg.get("contratados") or "[]")
    except (TypeError, ValueError):
        return None, None
    nomes = "; ".join(x.get("nome") or "" for x in lista if isinstance(x, dict)) or None
    docs = "; ".join(_documento(x.get("cpf_cnpj")) or "" for x in lista if isinstance(x, dict)) or None
    return nomes, docs


def _contrato(reg):
    nomes, docs = _contratados(reg)
    return {
        "numero": reg.get("numero") or None, "ano": reg.get("ano"), "tipo": reg.get("tipo") or None,
        "orgao_nome": reg.get("orgao") or None, "situacao": reg.get("situacao") or None,
        "objeto": reg.get("objeto") or None, "fornecedor_nome": nomes, "fornecedor_cpfcnpj": docs,
        "valor": _br(reg.get("valor")), "data_publicacao": _data(reg.get("data_publicacao")) or None,
        "data_firmatura": _data(reg.get("data_firmatura")) or None,
        "inicio_vigencia": _data(reg.get("inicio_vigencia")) or None,
        "fim_vigencia": _data(reg.get("fim_vigencia")) or None, "fiscal_contrato": reg.get("fiscal_contrato") or None,
        "fonte": FONTE,
    }


def _do_ano(registros, ano, portal, o_que):
    fora = [r for r in registros if ano and str(r.get("ano")) != str(ano)]
    if fora:
        raise ErroPortal(f"{portal.url} devolveu {len(fora)} {o_que} de outro ano ao pedir {ano} "
                         f"(ex.: {fora[0].get('ano')}); a resposta misturaria anos.")


def contratos(portal, *, ano, tipo, busca, maximo):
    """Contratos (tipo="contrato": todos os tipos menos os aditivos) ou aditivos do `ano` (int ou None).
    `busca` procura no objeto."""
    filtros = {"ano": str(ano)} if ano else {}
    ressalvas = []
    if tipo == "aditivo":
        filtros["tipo"] = "Aditivo"
    elif tipo != "contrato":
        raise ValueError(f"tipo={tipo!r}: use 'contrato' ou 'aditivo'")
    if busca:
        filtros["objeto"] = busca
        ressalvas.append("a busca dos contratos deste portal procura só no objeto do contrato (não no fornecedor nem "
                         "no número)")
    if tipo == "aditivo":
        total, registros = _ler(portal, "sgcontratos/listar", filtros, maximo=maximo)
    else:  # o portal não tem filtro "tudo menos aditivo": lê tudo e tira os aditivos aqui
        total, registros = _ler(portal, "sgcontratos/listar", filtros, maximo=TUDO)
        if len(registros) != total:
            raise _incompleta("dos contratos", len(registros), total)
        registros = [r for r in registros if r.get("tabela") != "aditivos" and r.get("tipo") != "Aditivo"]
        total = len(registros)
        ressalvas.append("os contratos deste portal incluem convênios, atas de registro de preço, comodatos e "
                         "distratos: o campo tipo diz qual é cada um")
    _do_ano(registros, ano, portal, "contrato(s)")
    return {"total": total, "registros": [_contrato(r) for r in registros[:maximo]], "ressalvas": ressalvas}


def _licitacao(reg):
    return {
        "numero": reg.get("numero") or None, "label": reg.get("label") or None, "ano": reg.get("ano"),
        "modalidade": reg.get("modalidade") or None, "situacao": reg.get("situacao") or None,
        "orgao": reg.get("orgao") or None, "descricao": (reg.get("descricao") or "").strip() or None,
        "processo": reg.get("numero_processo") or None, "data_publicacao": _data(reg.get("data_publicacao")) or None,
        "data_abertura": _data(reg.get("data_abertura")) or None,
        "data_homologacao": _data(reg.get("data_homologacao")) or None,
        "valor_estimado": _br(reg.get("valor_estimado")), "fonte": FONTE,
    }


def licitacoes(portal, *, busca, dispensas, ano, maximo):
    """Licitações ou dispensas e inexigibilidades do `ano` (int ou None). `busca` procura na descrição."""
    filtros = {"ano": str(ano)} if ano else {}
    if dispensas:
        filtros["onlyDispensas"] = True
    if busca:
        filtros["descricao"] = busca
    total, registros = _ler(portal, "sglicitacoes/listar", filtros, maximo=maximo)
    _do_ano(registros, ano, portal, "licitação(ões)")
    return {"total": total, "registros": [_licitacao(r) for r in registros],
            "ressalvas": ["o ano das licitações deste portal é o ano da licitação (o do número), não o da publicação "
                          "(algumas foram publicadas no ano seguinte)"]}
