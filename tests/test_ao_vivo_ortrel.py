"""Teste de fumaça do encaixe Ortrel contra o portal REAL (Câmara de Cidade Ocidental).

Desligado por padrão, como `test_ao_vivo.py`: TRANSPARENCIA_AO_VIVO=1 pytest -m ao_vivo
São 6 chamadas (api.js, a série da folha, 2 páginas de despesas de um mês, de novo para um CNPJ), com pausa de 1 s.
As asserções comparam só campos de filtro (ano, mês, data, CNPJ): nada de nome de pessoa sai na tela.
"""
import os
import sys
from datetime import date, datetime

import pytest

from transparencia_municipal import Portal

pytestmark = [
    pytest.mark.ao_vivo,
    pytest.mark.skipif(os.environ.get("TRANSPARENCIA_AO_VIVO") != "1",
                       reason="consulta o portal real; ligue com TRANSPARENCIA_AO_VIVO=1"),
]

URL = "https://transparencia.cidadeocidental.go.leg.br"
ANO, MES = 2025, 9
CNPJ = "00.178.956/0001-88"  # fornecedor pessoa jurídica com empenhos em 03/2025 (medido em 04/11/2026)


@pytest.fixture(scope="module")
def portal():
    return Portal(URL)


def test_folha_de_um_mes_vem_so_desse_mes_com_rubricas(portal):
    r = portal.folha(ANO, MES, maximo=sys.maxsize)
    assert r["total"] > 0 and len(r["registros"]) == r["total"]
    assert {(x["ano"], int(x["mes"])) for x in r["registros"]} == {(ANO, MES)}
    assert all(x["fonte"] == "Ortrel" and x["lista_proventos"] for x in r["registros"])
    assert len({x["matricula"] for x in r["registros"]}) == r["total"]
    print(f"\nfolha {MES:02d}/{ANO}: {r['total']} linhas; ressalvas: {len(r['ressalvas'])}")


def test_despesas_de_um_mes_vem_inteiras_e_so_desse_mes(portal):
    r = portal.despesas("2025-03-01", "2025-03-31", maximo=sys.maxsize)
    assert r["total"] > 100 and len(r["registros"]) == r["total"]  # mais de uma página de 100
    datas = {datetime.strptime(x["data"], "%d/%m/%Y").date() for x in r["registros"]}
    assert min(datas) >= date(2025, 3, 1) and max(datas) <= date(2025, 3, 31)
    assert len({x["empenho"] for x in r["registros"]}) == r["total"]
    assert any("mascarado" in frase for frase in r["ressalvas"])
    print(f"\ndespesas 03/2025: {r['total']} empenhos")


def test_despesas_por_cnpj_trazem_so_esse_cnpj(portal):
    r = portal.despesas("2025-03-01", "2025-03-31", CNPJ, maximo=sys.maxsize)
    assert r["total"] >= 1 and {x["cpf_cnpj"] for x in r["registros"]} == {CNPJ}
    print(f"\ndespesas 03/2025 do CNPJ: {r['total']} empenhos")
