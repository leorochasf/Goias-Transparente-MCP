"""Teste de fumaça das receitas da Centi contra o portal REAL (Prefeitura de Posse, menu `cntreceitas`).

Desligado por padrão; liga com `TRANSPARENCIA_AO_VIVO=1 pytest -m ao_vivo`. Uma leitura de um mês: a página inicial, a
sondagem da API NucleoGov, a lista de órgãos e uma consulta por órgão (13 em Posse, mais uma repetição por órgão
vazio), com pausa. Receitas são contas, não pessoas: as asserções olham contagens, códigos, meses e somas.
"""
import os
import re

import pytest

from transparencia_municipal import Portal

pytestmark = [
    pytest.mark.ao_vivo,
    pytest.mark.skipif(os.environ.get("TRANSPARENCIA_AO_VIVO") != "1",
                       reason="consulta o portal real; ligue com TRANSPARENCIA_AO_VIVO=1"),
]

URL = os.environ.get("TRANSPARENCIA_PORTAL_CENTI", "https://acessoainformacao.posse.go.gov.br")


def test_posse_responde_receitas_do_mes_por_orgao_pela_centi_e_o_mes_confere_com_as_raizes():
    r = Portal(URL, navegador=True).receitas(2025, 9, maximo=5000)
    regs = r["registros"]
    assert r["total"] > 0 and len(regs) == r["total"] and "incompleta" not in r  # leitura completa
    assert {x["fonte"] for x in regs} == {"Centi"} and {(x["ano"], x["mes"]) for x in regs} == {(2025, 9)}
    orgaos = {x["orgao"] for x in regs}
    assert len(orgaos) >= 2  # Prefeitura e fundos, cada um lido em separado
    assert {x["analitica"] for x in regs} >= {True, False}
    assert all(re.fullmatch(r"\d+(\.\d+)+", x["codigo"] or "") for x in regs)

    principal = r["somas_por_orgao"][0]
    assert principal["orgao"] == "PODER EXECUTIVO"
    # medido em 04/11/2026 (descoberta e esta frente): o mês das analíticas fecha ao centavo com as contas do topo
    assert principal["valor_arrecadado_mes"] == "11.626.838,01"
    assert not [x for x in r["ressalvas"] if "PODER EXECUTIVO, no mês" in x]
    print(f"\n{len(regs)} linhas, {len(orgaos)} órgãos com linhas, {len(r['somas_por_orgao'])} órgãos lidos")
    for x in r["ressalvas"]:
        print("RESSALVA:", x)
