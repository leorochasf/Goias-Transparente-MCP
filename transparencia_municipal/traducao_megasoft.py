"""Tradução Megasoft → formato do projeto. Sem rede, sem estado.

Vale para a Megasoft embutida no NucleoGov e para a de domínio próprio: os campos são os mesmos (medido em
04/11/2026; ver docs/design/2026-11-04-megasoft-centi.md). A folha sai com os nomes de campo do NucleoGov, para que a
linha leve, a leitura do mês e o resumo funcionem sem mudança; as despesas, no formato de despesas do projeto.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from .cliente import _cnpj

FONTE = "Megasoft"

#: Aruanã, 12/2025 (04/11/2026): a listagem da folha não tem campo de tipo de pagamento, e nenhuma matrícula veio
#: duas vezes no mês. `situacao` é a situação funcional; `situacaoPagamento`, PAGO/NÃO PAGO. O rótulo leva "mensal"
#: para o resumo contar a linha, e diz que 13º e rescisão não vêm separados.
TIPO_PAGAMENTO = "Mensal (a Megasoft não separa 13º nem rescisão)"


def _br(valor):
    """3512.4 → '3.512,40', como o NucleoGov escreve valores. Vazio ou ilegível → None."""
    try:
        d = Decimal(str(valor)).quantize(Decimal("0.01")) if valor not in (None, "") else None
    except InvalidOperation:
        return None
    return None if d is None else f"{d:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _data(valor):
    """'15/01/2025' fica; '2025-01-15' ou '2025-01-15T00:00:00' vira '15/01/2025'."""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(valor or ""))
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else valor


def linha_da_folha(reg):
    """Uma linha da listagem `servidor/paginado` (própria) ou `megasoft/servidores` (embutida)."""
    matricula = reg.get("matricula")
    return {
        "nome": reg.get("nome"), "matricula": None if matricula is None else str(matricula), "cpf": reg.get("cpf"),
        "cargo": reg.get("cargo"), "lotacao": reg.get("departamento"), "vinculo": reg.get("tipoDeVinculo"),
        "tipo_folha": TIPO_PAGAMENTO, "data_admissao": reg.get("dataAdmissao"),
        "data_demissao": reg.get("dataExoneracao"), "carga_horaria": reg.get("cargaHoraria"),
        "total_proventos": _br(reg.get("proventos")), "total_desconto": _br(reg.get("descontos")),
        "total_liquido": _br(reg.get("totalLiquido")), "ano": reg.get("ano"), "mes": reg.get("mes"),
        "situacao": reg.get("situacao"), "situacao_pagamento": reg.get("situacaoPagamento"), "fonte": FONTE,
    }


#: o empenho traz o documento no início de `cnpjENomeDoFornecedor` ("25.107.525/0001-51/NOME"); a máscara tem "/"
_DOCUMENTO = re.compile(r"\s*(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}|[\dX*]{3}\.?[\dX*]{3}\.?[\dX*]{3}-?[\dX*]{2})"
                        r"\s*[/-]?\s*(.*)", re.S)


def despesa(reg):
    """Um empenho da listagem `empenho/paginado` (própria) ou `megasoft/empenhos` (embutida).

    Os valores são os totais (`valorTotalDo...`), que a Megasoft dá ao lado do valor e da anulação.
    """
    composto = str(reg.get("cnpjENomeDoFornecedor") or "")
    m = _DOCUMENTO.match(composto)
    documento, resto = (m.group(1), m.group(2).strip()) if m else (None, composto.strip())
    return {
        "empenho": reg.get("codigo"), "data": _data(reg.get("data")),
        "cpf_cnpj": (_cnpj(documento) or documento) if documento else None,
        "fornecedor": reg.get("nomeDoFornecedor") or resto or None,
        "valor_empenhado": _br(reg.get("valorTotalDoEmpenho")),
        "valor_liquidado": _br(reg.get("valorTotalDaLiquidacao")),
        "valor_pago": _br(reg.get("valorTotalDoPagamento")),
        "historico": reg.get("historico"), "fonte": FONTE,
    }
