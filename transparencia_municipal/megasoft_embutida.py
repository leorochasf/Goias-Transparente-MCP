"""Acesso à Megasoft embutida no portal NucleoGov (menu `mgservidores`, `mgdespesas`). Encaixe do ticket 03; único
arquivo dele.

O `Portal` manda para cá a folha ou as despesas quando o menu aponta a Megasoft e a API NucleoGov não serve o
módulo. Por enquanto, recusa. O contrato dos encaixes está em megasoft_propria.py.
"""
from __future__ import annotations

from .cliente import EXTERNOS, recusa


def folha(portal, *, ano, mes, busca, maximo, progresso=None):
    """Linhas da folha de `mes`/`ano` (int; `mes` None = o portal decide). `busca`: nome do servidor ou None.

    `progresso(lidas, total)`, se dado, é chamado depois de cada página (a leitura do mês avisa o assistente).
    """
    raise recusa(portal, "folha", EXTERNOS["mg"])


def despesas(portal, *, de, ate, cnpj, busca, maximo):
    """Empenhos de `de` a `ate` (dd/mm/aaaa). `cnpj` formatado ou None; `busca`: nome do fornecedor ou None."""
    raise recusa(portal, "despesas", EXTERNOS["mg"])
