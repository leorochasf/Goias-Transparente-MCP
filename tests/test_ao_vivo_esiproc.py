"""Processos do eSiproc contra o TCM-GO REAL: o `/pesquisar` ainda respeita município, ano e número?

Desligado por padrão; liga com `TRANSPARENCIA_AO_VIVO=1 pytest -m ao_vivo`. Três consultas, com pausa de 1 s.
Nova Crixás é o IBGE 5214838; o eSiproc grava o código sem o prefixo 52 da UF ("14838").
As asserções comparam só campos de filtro: nada de nome de pessoa sai na tela.
"""
import os

import pytest

from transparencia_municipal.tcm import ClienteTCM

pytestmark = [
    pytest.mark.ao_vivo,
    pytest.mark.skipif(os.environ.get("TRANSPARENCIA_AO_VIVO") != "1",
                       reason="consulta o TCM-GO real; ligue com TRANSPARENCIA_AO_VIVO=1"),
]


def test_processos_de_um_ano_sao_todos_do_municipio_e_do_ano_e_o_numero_acha_o_processo():
    cliente = ClienteTCM()
    r = cliente.processos("Nova Crixás", ano=2023, maximo=30)
    assert r["municipio_tcm"] == "NOVA CRIXÁS" and not r.get("total_e_piso") and "incompleta" not in r
    assert 10 < r["total"] <= 30 and len(r["registros"]) == r["total"]  # 12 em 04/11/2026: obriga a 2ª página
    assert len({x["numero"] for x in r["registros"]}) == r["total"]
    assert {(x["codigo_ibge"], x["municipio"], x["ano_competencia"]) for x in r["registros"]} == \
        {("14838", "NOVA CRIXÁS", 2023)}

    numero = r["registros"][0]["numero"]  # ex.: 00018560.2023.001.4.14838.0223
    sequencial, ano = numero.split(".")[:2]
    achado = cliente.processos(numero=f"{int(sequencial):05d}/{ano[2:]}")
    assert numero in {x["numero"] for x in achado["registros"]}
    assert all(x["numero"].startswith(f"{sequencial}.{ano}") for x in achado["registros"])
