"""Ao vivo (fundação dos módulos extras): o reconhecimento do Ortrel pela página e o acórdão por número no TCMJuris.

Roda só com TRANSPARENCIA_AO_VIVO=1. Poucas consultas, uma por vez, com pausa de 1 s. Nenhum nome de pessoa é impresso.
"""
import os
import time

import pytest

from transparencia_municipal import Portal
from transparencia_municipal.tcm import ClienteTCM

pytestmark = [pytest.mark.ao_vivo,
              pytest.mark.skipif(os.getenv("TRANSPARENCIA_AO_VIVO") != "1", reason="defina TRANSPARENCIA_AO_VIVO=1")]

#: as 4 câmaras Ortrel do catálogo (descoberta E)
CAMARAS_ORTREL = ("https://transparencia.cidadeocidental.go.leg.br", "https://transparencia.luziania.go.leg.br",
                  "https://transparencia.saojoaodalianca.go.leg.br", "https://transparencia.camaravalparaiso.go.gov.br")


@pytest.mark.parametrize("endereco", CAMARAS_ORTREL)
def test_camara_ortrel_e_reconhecida_pela_pagina_sem_o_catalogo(endereco):
    time.sleep(1)
    assert Portal(endereco)._plataforma() == "ortrel"


def test_acordao_pelo_numero_completo_e_pela_parte_sem_ano():
    cliente = ClienteTCM(pausa=1)
    r = cliente.acordaos(numero="10175/23")
    assert r["total"] >= 1 and all("casou_com" in x for x in r["registros"])
    assert all(x["numero_processo"].endswith("/23") or x["numero_acordao"].endswith("/23") for x in r["registros"])
    sem_ano = cliente.acordaos(numero="7286")
    assert sem_ano["total"] >= 2 and "sem o ano" in sem_ano["aviso_numero"]
    print(f"\n10175/23: {r['total']} ({[x['casou_com'] for x in r['registros']]}); "
          f"7286: {sem_ano['total']}; aviso: {sem_ano['aviso_numero']}")
