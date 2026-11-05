"""Acesso às câmaras Ortrel (`transparencia.<câmara>.go.leg.br`). Encaixe do ticket 06; único arquivo dele, com a
tradução Ortrel → formato do projeto.

O `Portal` manda para cá o portal inteiro quando o catálogo diz `ortrel` ou a página inicial traz `/src/main.jsx`.
Interface, nomes comuns e marcas da resposta: ticket 01 dos módulos extras, seção `## Comments`. Consultas medidas:
docs/design/2026-11-04-modulos-extras.md, seção E da descoberta (`api.js` com `API_URL` e o token).

Sem função aqui, o `Portal` recusa o módulo (receitas e detalhe do servidor: não medidos ou não existem).
"""
from __future__ import annotations

from .cliente import ORTREL, ainda_nao_disponivel

FONTE = "Ortrel"


def folha(portal, *, ano, mes, busca, maximo, progresso=None):
    """Linhas da folha de `mes`/`ano` (int), com os nomes de campo do NucleoGov (como `traducao_megasoft`)."""
    raise ainda_nao_disponivel(portal, "folha", ORTREL)


def despesas(portal, *, de, ate, cnpj, busca, maximo):
    """Empenhos de `de` a `ate` (dd/mm/aaaa), no formato de despesas. `cnpj` formatado ou None; `busca`: nome."""
    raise ainda_nao_disponivel(portal, "despesas", ORTREL)


def contratos(portal, *, ano, tipo, busca, maximo):
    """Contratos do `ano` (int ou None); `tipo`: "contrato" ou "aditivo"; `busca`: texto ou None."""
    raise ainda_nao_disponivel(portal, "contratos", ORTREL)


def licitacoes(portal, *, busca, dispensas, ano, maximo):
    """Licitações (`dispensas` False) ou dispensas e inexigibilidades (True) do `ano` (int ou None)."""
    raise ainda_nao_disponivel(portal, "licitações", ORTREL)


def diarias(portal, *, de, ate, busca, maximo):
    """Diárias com saída de `de` a `ate` (`datetime.date`), com os nomes comuns de diárias. `busca`: texto ou None."""
    raise ainda_nao_disponivel(portal, "diárias", ORTREL)


def legislacao(portal, *, tipo, busca, ano, maximo):
    """Atos do `tipo` ("LEI", "DECRETO"...: maiúsculas, sem acento), com `busca` na ementa e `ano` (int ou None)."""
    raise ainda_nao_disponivel(portal, "legislação", ORTREL)
