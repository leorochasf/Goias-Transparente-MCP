"""Teste de fumaça da Prefeitura de Goiânia (TransWeb e BSIT) e das despesas da Câmara de Goiânia, contra os sistemas
REAIS.

Desligado por padrão; ligue com TRANSPARENCIA_AO_VIVO=1 (cerca de 25 consultas, 1 s de pausa; os dois sistemas
aceitam a identificação da ferramenta). As asserções comparam só campos de filtro: nada de nome de pessoa na tela.
"""
import os
from datetime import date, datetime

import pytest

from transparencia_municipal import Portal
from transparencia_municipal.goiania import FONTE_BSIT, FONTE_TRANSWEB

pytestmark = [
    pytest.mark.ao_vivo,
    pytest.mark.skipif(os.environ.get("TRANSPARENCIA_AO_VIVO") != "1",
                       reason="consulta o portal real; ligue com TRANSPARENCIA_AO_VIVO=1"),
]


@pytest.fixture(scope="module")
def prefeitura():
    return Portal("https://www.goiania.go.gov.br/transparencia")


def _dia(texto):
    return datetime.strptime(texto, "%d/%m/%Y").date()


def test_folha_por_nome_vem_do_bsit_filtrada_pelo_proprio_sistema(prefeitura):
    r = prefeitura.folha(2026, 9, "souza", maximo=20)
    assert r["total"] > 20 and {x["fonte"] for x in r["registros"]} == {FONTE_BSIT}
    assert all("SOUZA" in x["nome"].upper() for x in r["registros"])
    assert all(x["vinculo"] and x["total_liquido"] for x in r["registros"])


def test_despesas_de_um_mes_batem_com_os_totais_do_transweb(prefeitura):
    r = prefeitura.despesas("2026-09-01", "2026-09-30", maximo=50)
    assert r["total"] > 50 and {x["fonte"] for x in r["registros"]} == {FONTE_TRANSWEB}
    assert all(date(2026, 9, 1) <= _dia(x["data"]) <= date(2026, 9, 30) for x in r["registros"])
    assert set(r["somas_do_periodo"]) == {"empenhado", "liquidado", "pago"}


def test_despesas_da_camara_vem_do_transweb_e_sao_so_da_camara():
    camara = Portal("https://camaragoiania.nucleogov.com.br", navegador=True)
    r = camara.despesas("2026-09-01", "2026-09-30", maximo=100)
    assert r["total"] > 0 and {x["fonte"] for x in r["registros"]} == {FONTE_TRANSWEB}
    assert {x["orgao"] for x in r["registros"]} == {"CAMARA MUNICIPAL DE GOIANIA"}


def test_receitas_do_mes(prefeitura):
    r = prefeitura.receitas(2026, 9, maximo=500)
    assert r["total"] > 100 and {(x["ano"], x["mes"]) for x in r["registros"]} == {(2026, 9)}


def test_contratos_e_aditivos_do_ano_pela_firmatura(prefeitura):
    c = prefeitura.contratos(2025, maximo=50)
    assert c["total"] > 0 and {x["ano"] for x in c["registros"]} == {"2025"}
    assert {x["tipo"] for x in c["registros"]} == {"Contrato"}
    a = prefeitura.contratos(2025, tipo="aditivo", maximo=20)
    assert {x["tipo"] for x in a["registros"]} <= {"Aditivo"}


def test_licitacoes_e_dispensas_do_ano_corrente(prefeitura):
    """O TransWeb só exporta as licitações do ano corrente (05/11/2026); outro ano é recusado sem consulta."""
    corrente = date.today().year
    r = prefeitura.licitacoes(ano=corrente, maximo=50)
    assert r["total"] > 0 and {x["ano"] for x in r["registros"]} == {str(corrente)}
    d = prefeitura.licitacoes(dispensas=True, maximo=50)
    assert all("DISPENSA" in x["modalidade"].upper() or "INEXIGIBILIDADE" in x["modalidade"].upper()
               for x in d["registros"])


def test_diarias_de_um_mes(prefeitura):
    r = prefeitura.diarias("2025-09-01", "2025-09-30", maximo=100)
    assert r["total"] > 0
    assert all(date(2025, 9, 1) <= _dia(x["data_saida"]) <= date(2025, 9, 30) for x in r["registros"])
