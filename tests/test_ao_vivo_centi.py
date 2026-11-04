"""Teste de fumaça da Centi contra o portal REAL (Prefeitura de Posse, menu `cntdespesas`).

Desligado por padrão; liga com `TRANSPARENCIA_AO_VIVO=1 pytest -m ao_vivo`. Duas consultas (cada uma passa pela página
inicial e pela API NucleoGov antes da Centi), com pausa. Nada de nome sai na tela: as asserções olham datas, CNPJ e
contagens.
"""
import os
import time
from collections import Counter
from datetime import date, datetime

import pytest

from transparencia_municipal import Portal

pytestmark = [
    pytest.mark.ao_vivo,
    pytest.mark.skipif(os.environ.get("TRANSPARENCIA_AO_VIVO") != "1",
                       reason="consulta o portal real; ligue com TRANSPARENCIA_AO_VIVO=1"),
]

URL = os.environ.get("TRANSPARENCIA_PORTAL_CENTI", "https://acessoainformacao.posse.go.gov.br")


def test_posse_responde_despesas_do_mes_pela_centi_e_a_busca_por_cnpj_traz_so_ele():
    portal = Portal(URL, navegador=True)
    mes = portal.despesas("2025-01-01", "2025-01-31", maximo=5000)
    assert mes["total"] > 0 and len(mes["registros"]) == mes["total"]  # leitura completa
    assert {x["fonte"] for x in mes["registros"]} == {"Centi"}
    datas = {datetime.strptime(x["data"], "%d/%m/%Y").date() for x in mes["registros"]}
    assert all(date(2025, 1, 1) <= d <= date(2025, 1, 31) for d in datas), sorted(datas)

    cnpjs = Counter(x["cpf_cnpj"] for x in mes["registros"] if len(x["cpf_cnpj"] or "") == 18)
    cnpj, vezes = next((c, n) for c, n in cnpjs.most_common() if n >= 2)  # pessoa jurídica com mais de um empenho
    time.sleep(1)
    so_ele = portal.despesas("2025-01-01", "2025-01-31", cnpj, maximo=5000)
    assert so_ele["total"] == vezes == len(so_ele["registros"])
    assert {x["cpf_cnpj"] for x in so_ele["registros"]} == {cnpj}
