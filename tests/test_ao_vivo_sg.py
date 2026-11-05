"""Teste de fumaça do sistema de gestão (SG) integrado ao NucleoGov contra o portal REAL de Anápolis.

Desligado por padrão; ligue com TRANSPARENCIA_AO_VIVO=1 (cerca de 10 consultas, 1 s de pausa).
Outro portal com menu `sgservidores`: TRANSPARENCIA_PORTAL_SG=https://acessoainformacao.<municipio>.go.gov.br
As asserções comparam só campos de filtro: nada de nome de pessoa na tela.
"""
import os
import re
from datetime import date, datetime

import pytest

from transparencia_municipal import Portal

pytestmark = [
    pytest.mark.ao_vivo,
    pytest.mark.skipif(os.environ.get("TRANSPARENCIA_AO_VIVO") != "1",
                       reason="consulta o portal real; ligue com TRANSPARENCIA_AO_VIVO=1"),
]

URL = os.environ.get("TRANSPARENCIA_PORTAL_SG", "https://acessoainformacao.anapolis.go.gov.br")
FONTE = "NucleoGov (sistema de gestão)"
AMOSTRA = 20


@pytest.fixture(scope="module")
def portal():
    return Portal(URL, navegador=True)


def test_folha_de_um_mes_vem_do_sg_e_so_desse_mes(portal):
    r = portal.folha(2025, 6, maximo=AMOSTRA)
    assert r["total"] > AMOSTRA and len(r["registros"]) == AMOSTRA
    assert {(x["fonte"], x["ano"], x["mes"]) for x in r["registros"]} == {(FONTE, "2025", "6")}


def test_despesas_de_dez_dias_sao_empenhos_do_periodo_e_o_cnpj_filtra(portal):
    r = portal.despesas("2025-06-01", "2025-06-10", maximo=200)
    assert r["total"] > 0 and {x["fonte"] for x in r["registros"]} == {FONTE}
    datas = {datetime.strptime(x["data"], "%d/%m/%Y").date() for x in r["registros"]}
    assert all(date(2025, 6, 1) <= d <= date(2025, 6, 10) for d in datas), sorted(datas)
    cnpj = next(x["cpf_cnpj"] for x in r["registros"]
                if re.fullmatch(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", x["cpf_cnpj"] or ""))
    so = portal.despesas("2025-06-01", "2025-06-10", cnpj, maximo=200)
    assert so["total"] > 0 and {x["cpf_cnpj"] for x in so["registros"]} == {cnpj}


def test_receitas_de_um_mes_trazem_os_orgaos_e_o_mes(portal):
    r = portal.receitas(2025, 6, maximo=1000)
    assert r["total"] == len(r["registros"]) > 0
    assert {(x["fonte"], x["ano"], x["mes"]) for x in r["registros"]} == {(FONTE, 2025, 6)}
    assert len({x["orgao"] for x in r["registros"]}) > 1


def test_contratos_e_aditivos_do_ano_e_dispensas(portal):
    c = portal.contratos(2025, maximo=50)
    assert c["total"] > 0 and {(x["fonte"], x["ano"]) for x in c["registros"]} == {(FONTE, "2025")}
    assert "Aditivo" not in {x["tipo"] for x in c["registros"]}
    a = portal.contratos(2025, tipo="aditivo", maximo=20)
    assert a["total"] > 0 and {x["tipo"] for x in a["registros"]} == {"Aditivo"}
    d = portal.licitacoes(dispensas=True, ano=2025, maximo=20)
    assert d["total"] > 0 and {x["ano"] for x in d["registros"]} == {"2025"}


def test_somas_do_periodo_e_liquidado_pago_por_cnpj(portal):
    r = portal.despesas("2025-06-01", "2025-06-10", maximo=200)
    assert set(r["somas_do_periodo"]) == {"empenhado", "liquidado", "pago"}
    cnpj = next(x["cpf_cnpj"] for x in r["registros"]
                if re.fullmatch(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", x["cpf_cnpj"] or ""))
    so = portal.despesas("2025-06-01", "2025-06-10", cnpj, maximo=50)
    assert all(x["valor_liquidado"] is not None and x["valor_pago"] is not None for x in so["registros"])
