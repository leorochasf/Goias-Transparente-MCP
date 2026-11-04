"""eSiproc do TCM-GO: os processos eletrônicos de um município. Desenho: docs/design/2026-11-04-tcm-go.md.

Encaixe do `ClienteTCM`: o cliente já resolveu o município e zerou o teto de chamadas.
"""
from __future__ import annotations

from .tcm import NaoDisponivel


def processos(cliente, *, municipio, tipo, ano, finalizado, relator, numero, maximo) -> dict:
    """Processos do município. Devolve {"total", "registros"} (veja o ticket 01, seção Comments)."""
    raise NaoDisponivel("processos do TCM-GO (eSiproc): ainda não disponível neste projeto")
