"""Teste de fumaça da Megasoft de domínio próprio contra o portal REAL (Prefeitura de Corumbaíba).

Desligado por padrão, como `test_ao_vivo.py`: TRANSPARENCIA_AO_VIVO=1 pytest -m ao_vivo
São 4 chamadas (senha, folha de um mês, despesas de um trimestre, despesas de um CNPJ), com pausa de 1 s.
As asserções comparam só campos de filtro (mês, data, CNPJ): nada de nome de pessoa sai na tela.
"""
import os
import sys
import time
from datetime import date, datetime

import pytest

from transparencia_municipal import Portal

pytestmark = [
    pytest.mark.ao_vivo,
    pytest.mark.skipif(os.environ.get("TRANSPARENCIA_AO_VIVO") != "1",
                       reason="consulta o portal real; ligue com TRANSPARENCIA_AO_VIVO=1"),
]

URL = "https://corumbaiba.megasofttransparencia.com.br"
ANO, MES = 2026, 9
DE, ATE = date(2026, 7, 1), date(2026, 9, 30)
CNPJ = "06.789.803/0001-53"  # fornecedor pessoa jurídica com empenhos todo mês em 2025


@pytest.fixture(scope="module")
def portal():
    return Portal(URL)


def _datas(registros):
    return {datetime.strptime(x["data"], "%d/%m/%Y").date() for x in registros}


def test_folha_de_um_mes_recente_vem_inteira_e_so_desse_mes(portal):
    r = portal.folha(ANO, MES, maximo=sys.maxsize)
    assert r["total"] > 0 and len(r["registros"]) == r["total"]
    assert {(x["ano"], x["mes"]) for x in r["registros"]} == {(ANO, f"{MES:02d}")}
    assert {x["fonte"] for x in r["registros"]} == {"Megasoft"}
    assert len({x["matricula"] for x in r["registros"]}) == r["total"]


def test_despesas_de_um_trimestre_vem_inteiras_e_so_do_periodo(portal):
    time.sleep(1)
    r = portal.despesas(DE.isoformat(), ATE.isoformat(), maximo=sys.maxsize)
    assert r["total"] > 0 and len(r["registros"]) == r["total"]  # sem repetidos nem faltas
    datas = _datas(r["registros"])
    assert all(DE <= d <= ATE for d in datas), (min(datas), max(datas))


def test_despesas_por_cnpj_trazem_so_esse_fornecedor_e_so_o_periodo(portal):
    time.sleep(1)
    r = portal.despesas(DE.isoformat(), ATE.isoformat(), CNPJ, maximo=sys.maxsize)
    assert r["total"] > 0 and len(r["registros"]) == r["total"]
    assert {x["cpf_cnpj"] for x in r["registros"]} == {CNPJ}
    datas = _datas(r["registros"])
    assert all(DE <= d <= ATE for d in datas), (min(datas), max(datas))
