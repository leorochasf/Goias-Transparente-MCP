"""Teste de fumaça da Megasoft embutida contra o portal REAL de Aruanã: período e CNPJ respeitados?

Desligado por padrão; ligue com TRANSPARENCIA_AO_VIVO=1 (cerca de 9 consultas, 1 s de pausa).
Outro portal com menu `mg*`: TRANSPARENCIA_PORTAL_MEGASOFT_EMBUTIDA=https://acessoainformacao.<municipio>.go.gov.br
(o CNPJ abaixo foi escolhido em Aruanã). As asserções comparam só campos de filtro: nada de nome de pessoa na tela.
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
CNPJ = "01.067.081/0001-00"  # fornecedor pessoa jurídica com empenhos no 1º trimestre de 2025
AMOSTRA = 20


@pytest.fixture(scope="module")
def portal():
    return Portal(URL, navegador=True)


def test_folha_de_um_mes_vem_da_megasoft_e_so_desse_mes(portal):
    r = portal.folha(2025, 12, maximo=AMOSTRA)
    assert r["total"] > AMOSTRA and len(r["registros"]) == AMOSTRA
    assert {(x["fonte"], int(x["ano"]), x["mes"]) for x in r["registros"]} == {("Megasoft", 2025, "12")}


def test_despesas_de_um_trimestre_por_cnpj_trazem_so_esse_fornecedor_e_so_o_periodo(portal):
    r = portal.despesas("2025-01-01", "2025-03-31", CNPJ, maximo=AMOSTRA)
    assert r["total"] > 0
    assert {(x["fonte"], x["cpf_cnpj"]) for x in r["registros"]} == {("Megasoft", CNPJ)}
    datas = {datetime.strptime(x["data"], "%d/%m/%Y").date() for x in r["registros"]}
    assert all(date(2025, 1, 1) <= d <= date(2025, 3, 31) for d in datas), sorted(datas)
