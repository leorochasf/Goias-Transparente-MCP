"""Teste de fumaça das diárias NucleoGov contra os portais REAIS: Posse (`diarias_cnt`) e Senador Canedo (`diarias_frl`).

Desligado por padrão; liga com `TRANSPARENCIA_AO_VIVO=1 pytest -m ao_vivo`. Três consultas à API (uma em Posse, duas em
Senador Canedo), com pausa. Nada de nome sai na tela: as asserções olham datas, órgãos, contagens e a presença do valor.
"""
import os
import re
import time
import unicodedata
from collections import Counter
from datetime import date, datetime

import pytest

from transparencia_municipal import Portal

pytestmark = [
    pytest.mark.ao_vivo,
    pytest.mark.skipif(os.environ.get("TRANSPARENCIA_AO_VIVO") != "1",
                       reason="consulta o portal real; ligue com TRANSPARENCIA_AO_VIVO=1"),
]

POSSE = os.environ.get("TRANSPARENCIA_PORTAL_DIARIAS_CNT", "https://acessoainformacao.posse.go.gov.br")
CANEDO = os.environ.get("TRANSPARENCIA_PORTAL_DIARIAS_FRL", "https://acessoainformacao.senadorcanedo.go.gov.br")
DE, ATE = date(2025, 1, 1), date(2025, 3, 31)


def _sem_acento(texto):
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().upper()


def _no_trimestre(r):
    saidas = [datetime.strptime(x["data_saida"], "%d/%m/%Y").date() for x in r["registros"]]
    return all(DE <= d <= ATE for d in saidas)


def test_posse_traz_as_diarias_do_trimestre_com_valor_e_avisa_do_orgao_principal():
    r = Portal(POSSE, navegador=True).diarias(DE, ATE, maximo=5000)
    assert r["total"] > 0 and len(r["registros"]) == r["total"]
    assert {x["fonte"] for x in r["registros"]} == {"NucleoGov"}
    assert _no_trimestre(r)
    assert all(x["valor"] and x["quantidade"] for x in r["registros"])  # Posse publica o valor
    assert len({x["orgao"] for x in r["registros"]}) == 1
    assert any("órgão principal" in s for s in r["ressalvas"])


def test_senador_canedo_traz_varios_orgaos_sem_valor_e_a_busca_conta_certo():
    portal = Portal(CANEDO, navegador=True)
    r = portal.diarias(DE, ATE, maximo=5000)
    assert r["total"] > 0 and len(r["registros"]) == r["total"]
    assert _no_trimestre(r)
    assert len({x["orgao"] for x in r["registros"]}) > 1
    assert all(x["valor"] is None for x in r["registros"])  # vazio vira None, nunca zero
    assert any("não publicou o valor" in s for s in r["ressalvas"])

    # uma palavra do motivo que está em parte das diárias (não é impressa)
    palavras = Counter(p for x in r["registros"] for p in set(re.findall(r"[A-Za-zÀ-ú]{6,}", x["motivo"] or "")))
    palavra, vezes = next((p, n) for p, n in palavras.most_common() if n < r["total"])
    esperado = sum(1 for x in r["registros"]
                   if any(_sem_acento(palavra) in _sem_acento(x[c]) for c in ("favorecido", "cargo", "destino", "motivo")))
    time.sleep(1)
    achadas = portal.diarias(DE, ATE, palavra, maximo=5000)
    assert achadas["total"] == esperado == len(achadas["registros"]) >= vezes
