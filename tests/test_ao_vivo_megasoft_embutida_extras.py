"""Teste de fumaça dos módulos extras da Megasoft embutida contra o portal REAL de Aruanã: receitas, diárias, contratos
e licitações, cada filtro conferido nos dados que voltam.

Desligado por padrão; ligue com TRANSPARENCIA_AO_VIVO=1 (5 consultas, 1 s de pausa).
Outro portal com os mesmos menus: TRANSPARENCIA_PORTAL_MEGASOFT_EMBUTIDA=https://acessoainformacao.<municipio>.go.gov.br
As asserções comparam só campos de filtro, datas e contagens: nada de nome de pessoa na tela.
"""
import os
from datetime import date, datetime

import pytest

from transparencia_municipal import Portal

pytestmark = [
    pytest.mark.ao_vivo,
    pytest.mark.skipif(os.environ.get("TRANSPARENCIA_AO_VIVO") != "1",
                       reason="consulta o portal real; ligue com TRANSPARENCIA_AO_VIVO=1"),
]

URL = os.environ.get("TRANSPARENCIA_PORTAL_MEGASOFT_EMBUTIDA", "https://acessoainformacao.aruana.go.gov.br")
AMOSTRA = 20


@pytest.fixture(scope="module")
def portal():
    return Portal(URL, navegador=True)


def test_receitas_de_um_mes_vem_da_megasoft_so_desse_mes_e_de_varios_orgaos(portal):
    r = portal.receitas(2025, 9, maximo=200)
    assert r["total"] > AMOSTRA and len(r["registros"]) == r["total"]
    assert {(x["fonte"], x["ano"], x["mes"]) for x in r["registros"]} == {("Megasoft", 2025, 9)}
    assert len({x["orgao"] for x in r["registros"]}) > 1 and r["ressalvas"]
    assert all(x["codigo"] and x["valor_arrecadado_ate_mes"] is not None for x in r["registros"])


def test_diarias_de_um_trimestre_saem_dentro_do_periodo(portal):
    r = portal.diarias("2025-01-01", "2025-03-31", maximo=AMOSTRA)
    assert r["total"] > AMOSTRA and len(r["registros"]) == AMOSTRA
    assert {x["fonte"] for x in r["registros"]} == {"NucleoGov"}
    saidas = {datetime.strptime(x["data_saida"], "%d/%m/%Y").date() for x in r["registros"]}
    assert all(date(2025, 1, 1) <= d <= date(2025, 3, 31) for d in saidas), sorted(saidas)
    assert all(x["valor"] for x in r["registros"])


def test_contratos_de_um_ano_sao_desse_ano_e_a_busca_casa_no_objeto(portal):
    r = portal.contratos(2025, maximo=AMOSTRA)
    assert r["total"] > AMOSTRA and len(r["registros"]) == AMOSTRA
    assert {(x["fonte"], x["ano"]) for x in r["registros"]} == {("Megasoft", 2025)}
    palavra = "AQUISI"
    r = portal.contratos(2025, busca=palavra, maximo=AMOSTRA)
    assert r["total"] > 0
    assert all(palavra in x["objeto"].upper() and x["ano"] == 2025 for x in r["registros"])


def test_licitacoes_de_um_ano_sao_desse_ano_e_dizem_que_so_o_ano_filtra(portal):
    r = portal.licitacoes(ano=2025, maximo=100)
    assert 0 < r["total"] == len(r["registros"])
    assert {(x["fonte"], x["ano"]) for x in r["registros"]} == {("Megasoft", 2025)}
    assert not any("DISPENSA" in (x["modalidade"] or "") for x in r["registros"])
    assert any("só filtram por ano" in x for x in r["ressalvas"])
