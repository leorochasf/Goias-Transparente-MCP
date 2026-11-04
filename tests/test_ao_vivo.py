"""Teste de fumaça contra o portal REAL: o portal respeita cada filtro que mandamos?

Os testes offline simulam o portal como achamos que ele é; só este confere se ele ainda é assim.
Fica desligado por padrão. Rode antes de cada versão (7 consultas, 1 s de pausa entre elas):

    TRANSPARENCIA_AO_VIVO=1 pytest -m ao_vivo

Outro portal: TRANSPARENCIA_PORTAL=https://acessoainformacao.<municipio>.go.gov.br
(os números de CNPJ e as datas abaixo foram escolhidos em Senador Canedo).
As asserções comparam só campos de filtro: nada de nome de pessoa sai na tela.
"""
import os
import time
from datetime import date, datetime

import pytest

from transparencia_municipal import Portal

pytestmark = [
    pytest.mark.ao_vivo,
    pytest.mark.skipif(os.environ.get("TRANSPARENCIA_AO_VIVO") != "1",
                       reason="consulta o portal real; ligue com TRANSPARENCIA_AO_VIVO=1"),
]

URL = os.environ.get("TRANSPARENCIA_PORTAL", "https://acessoainformacao.senadorcanedo.go.gov.br")
CNPJ = "25.107.525/0001-51"  # fornecedor com empenhos em 2025 (pessoa jurídica)
AMOSTRA = 20


class _ComPausa:
    """O cliente só pausa entre páginas; aqui também entre consultas."""

    def __init__(self, portal):
        self._portal = portal

    def __getattr__(self, nome):
        metodo = getattr(self._portal, nome)

        def chamada(*args, **kwargs):
            time.sleep(1)
            return metodo(*args, **kwargs)
        return chamada


@pytest.fixture(scope="module")
def portal():
    return _ComPausa(Portal(URL, navegador=True))


def test_despesas_por_cnpj_trazem_so_esse_fornecedor_e_so_o_periodo(portal):
    r = portal.despesas("2025-01-01", "2025-03-31", CNPJ, maximo=AMOSTRA)
    assert r["total"] > 0
    assert {x["cpf_cnpj"] for x in r["registros"]} == {CNPJ}
    datas = {datetime.strptime(x["data"], "%d/%m/%Y").date() for x in r["registros"]}
    assert all(date(2025, 1, 1) <= d <= date(2025, 3, 31) for d in datas), sorted(datas)


def test_receitas_trazem_so_o_mes_pedido(portal):
    r = portal.receitas(2025, 3, maximo=AMOSTRA)
    assert r["total"] > 0
    assert {(int(x["ano"]), int(x["mes"])) for x in r["registros"]} == {(2025, 3)}


def test_folha_traz_so_o_mes_pedido(portal):
    r = portal.folha(2025, 3, maximo=AMOSTRA)
    assert r["total"] > 0
    assert {(int(x["ano"]), int(x["mes"])) for x in r["registros"]} == {(2025, 3)}


def test_legislacao_filtra_por_tipo_ano_e_palavra(portal):
    decretos = portal.legislacao("DECRETO", maximo=AMOSTRA)
    portarias = portal.legislacao("PORTARIA", maximo=AMOSTRA)
    assert decretos["total"] > 0 and portarias["total"] > 0
    assert {x["tipo"] for x in decretos["registros"]} == {"1"}
    assert {x["tipo"] for x in portarias["registros"]} == {"2"}

    de_2025 = portal.legislacao("DECRETO", ano=2025, maximo=AMOSTRA)
    assert 0 < de_2025["total"] < decretos["total"]
    assert {x["ano"] for x in de_2025["registros"]} == {"2025"}

    com_cargo = portal.legislacao("DECRETO", "cargo", maximo=AMOSTRA)
    assert 0 < com_cargo["total"] < decretos["total"]
    assert all("cargo" in (x["ementa"] or "").lower() for x in com_cargo["registros"])
