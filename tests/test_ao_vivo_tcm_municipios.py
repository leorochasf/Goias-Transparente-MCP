"""Nomes dos municípios no TCM-GO contra as listas oficiais REAIS (eSiproc `/listar-campo` e TCMJuris `/filtros`).

Desligado por padrão; liga com `TRANSPARENCIA_AO_VIVO=1 pytest -m ao_vivo`. Duas consultas, com pausa de 1 s.
Percebe quando o TCM muda a grafia de um município e o catálogo precisa ser remontado.
"""
import os

import pytest

from transparencia_municipal import catalogo
from transparencia_municipal.tcm import FONTES, ClienteTCM

pytestmark = [
    pytest.mark.ao_vivo,
    pytest.mark.skipif(os.environ.get("TRANSPARENCIA_AO_VIVO") != "1",
                       reason="consulta o TCM-GO real; ligue com TRANSPARENCIA_AO_VIVO=1"),
]


def test_todo_nome_do_catalogo_ainda_esta_na_lista_oficial_de_cada_fonte_e_resolve_na_hora():
    cliente = ClienteTCM()
    for fonte in FONTES:
        usados = {n for _, n in cliente.lista_oficial(fonte)}
        gravados = {x["tcm"][fonte] for x in catalogo.carregar()}
        assert len(usados) == 246 and gravados <= usados, (fonte, sorted(gravados - usados))
        # a resolução na hora (sem catálogo) chega ao mesmo nome
        assert cliente.municipio(fonte, "Nova Crixás", na_hora=True) == cliente.municipio(fonte, "Nova Crixás")
        assert cliente.municipio(fonte, "Alto Paraíso de Goiás", na_hora=True) == \
            cliente.municipio(fonte, "alto paraiso de goias")
