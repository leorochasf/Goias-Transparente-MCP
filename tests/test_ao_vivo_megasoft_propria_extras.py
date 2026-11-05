"""Módulos extras da Megasoft de domínio próprio contra o portal REAL (Prefeitura de Corumbaíba), ticket 02.

Desligado por padrão, como `test_ao_vivo.py`: TRANSPARENCIA_AO_VIVO=1 pytest -m ao_vivo
São 8 chamadas (senha, receitas de um mês, diárias de um trimestre, contratos de um ano, dispensas de um ano, uma linha
da folha, o detalhe dessa matrícula e o de uma matrícula que não existe), com pausa de 1 s. As asserções comparam só
campos de filtro (mês, datas, ano, matrícula) e contagens: nada de nome de pessoa sai na tela.
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
ANO, MES = 2025, 9
DE, ATE = date(2025, 1, 1), date(2025, 3, 31)


@pytest.fixture(scope="module")
def portal():
    return Portal(URL)


def _dia(texto):
    return datetime.strptime(texto, "%d/%m/%Y").date()


def test_receitas_de_um_mes_vem_inteiras_so_desse_mes_e_de_varios_orgaos(portal):
    r = portal.receitas(ANO, MES, maximo=sys.maxsize)
    assert r["total"] > 0 and len(r["registros"]) == r["total"]
    assert {(x["ano"], x["mes"]) for x in r["registros"]} == {(ANO, MES)}
    assert len({x["orgao"] for x in r["registros"]}) > 1 and r["ressalvas"]
    assert {x["fonte"] for x in r["registros"]} == {"Megasoft"}


def test_diarias_de_um_trimestre_vem_inteiras_e_so_com_saida_no_periodo(portal):
    time.sleep(1)
    r = portal.diarias(DE.isoformat(), ATE.isoformat(), maximo=sys.maxsize)
    assert r["total"] > 0 and len(r["registros"]) == r["total"]
    saidas = [_dia(x["data_saida"]) for x in r["registros"]]
    assert all(DE <= d <= ATE for d in saidas), (min(saidas), max(saidas))
    assert all(x["valor"] and x["quantidade"] for x in r["registros"])


def test_contratos_de_um_ano_vem_inteiros_distintos_e_so_desse_ano(portal):
    time.sleep(1)
    r = portal.contratos(ANO, maximo=sys.maxsize)
    assert r["total"] > 0 and len(r["registros"]) == r["total"]
    assert len({x["codigo"] for x in r["registros"]}) == r["total"]
    assert {x["exercicio"] for x in r["registros"]} == {ANO}


def test_dispensas_de_um_ano_vem_inteiras_e_so_publicadas_nesse_ano(portal):
    time.sleep(1)
    r = portal.licitacoes(dispensas=True, ano=ANO, maximo=sys.maxsize)
    assert r["total"] > 0 and len(r["registros"]) == r["total"]
    assert len({x["codigo"] for x in r["registros"]}) == r["total"]
    assert {_dia(x["data_publicacao"]).year for x in r["registros"]} == {ANO}


def test_detalhe_de_uma_matricula_da_folha_traz_decreto_e_movimentos_e_matricula_inexistente_da_zero(portal):
    time.sleep(1)
    matricula = portal.folha(ANO, MES, maximo=1)["registros"][0]["matricula"]
    time.sleep(1)
    r = portal.detalhe_servidor(matricula, ANO, MES)
    assert r["total"] == 1
    d = r["registros"][0]
    assert d["matricula"] == matricula and d["fonte"] == "Megasoft"
    assert "decreto" in d and "data_decreto" in d and d["movimentos"]
    time.sleep(1)
    assert portal.detalhe_servidor("99999999", ANO, MES) == {"total": 0, "registros": []}
