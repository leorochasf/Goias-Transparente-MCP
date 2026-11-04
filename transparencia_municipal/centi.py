"""Acesso à contabilidade Centi integrada ao portal NucleoGov (menu `cntdespesas`). Encaixe do ticket 04; único
arquivo dele, com a tradução Centi → formato de despesas do projeto (o mesmo de `traducao_megasoft.despesa`).

O `Portal` manda para cá as despesas quando o menu aponta a Centi e a API NucleoGov não serve o módulo. Por
enquanto, recusa. A Centi não tem folha: sem função `folha`, o `Portal` recusa. O contrato dos encaixes está em
megasoft_propria.py.
"""
from __future__ import annotations

from .cliente import EXTERNOS, recusa


def despesas(portal, *, de, ate, cnpj, busca, maximo):
    """Empenhos de `de` a `ate` (dd/mm/aaaa). `cnpj` formatado ou None; `busca`: nome do fornecedor ou None."""
    raise recusa(portal, "despesas", EXTERNOS["centi"])
