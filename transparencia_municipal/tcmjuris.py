"""TCMJuris do TCM-GO: acórdãos julgados desde 2020 e o texto do PDF. Desenho: docs/design/2026-11-04-tcm-go.md.

Encaixe do `ClienteTCM`: o cliente já resolveu o município e zerou o teto de chamadas.
"""
from __future__ import annotations

from .tcm import NaoDisponivel


def acordaos(cliente, *, municipio, texto, assunto, ano, relator, maximo) -> dict:
    """Acórdãos. Devolve {"total", "registros"} (veja o ticket 01, seção Comments)."""
    raise NaoDisponivel("acórdãos do TCM-GO (TCMJuris): ainda não disponível neste projeto")


def ler_acordao(cliente, *, document_id) -> dict:
    """Texto do PDF de um acórdão. Devolve {"total": 1, "registros": [{"document_id", "pdf", "texto"}]}."""
    raise NaoDisponivel("leitura de acórdão do TCM-GO (TCMJuris): ainda não disponível neste projeto")
