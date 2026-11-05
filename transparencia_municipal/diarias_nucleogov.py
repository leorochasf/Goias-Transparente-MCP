"""Diárias dos portais NucleoGov (`diarias_cnt`/`diarias_frl`). Encaixe do ticket 05; único arquivo dele.

O `Portal` manda para cá as diárias de todo portal NucleoGov que não as tenha em `sgdiarias` (estas vão para a
Megasoft embutida). Interface, nomes comuns dos campos e marcas da resposta: ticket 01 dos módulos extras, seção
`## Comments`. Consultas medidas: docs/design/2026-11-04-modulos-extras.md, seção D da descoberta.

O sufixo que a página anunciou está em `portal.sufixos.get("diarias")` ("cnt", "frl" ou None);
`portal._consultar_api("diarias", filtros, maximo=..., progresso=None)` usa esse sufixo e, sem ele, tenta `frl` e
depois `cnt` (o sufixo errado responde zero sem erro).
"""
from __future__ import annotations

from .cliente import NUCLEOGOV, ainda_nao_disponivel

FONTE = "NucleoGov"


def diarias(portal, *, de, ate, busca, maximo):
    """Diárias com saída de `de` a `ate` (`datetime.date`), com os nomes comuns de diárias. `busca`: texto ou None."""
    raise ainda_nao_disponivel(portal, "diárias", NUCLEOGOV)
