"""Sufixo do módulo por portal (`servidores_cnt` × `servidores_frl`). Offline.

Medido em 04/11/2026: com o sufixo errado, o portal responde 200 e total 0 (Chapadão do Céu: `servidores_frl`
→ 0, `servidores_cnt` → 224). Ou seja, um sufixo errado vira "o município não tem folha", sem erro nenhum.
"""
import json
import urllib.parse

import pytest
import responses

from transparencia_municipal import ErroPortal, Portal

pytestmark = pytest.mark.descobre_sufixos
PORTAL = "https://acessoainformacao.exemplo.go.gov.br"


def _modulo(acao, total):
    def callback(requisicao):
        campos = urllib.parse.parse_qs(requisicao.body.decode("utf-8"))
        ident = next(iter(json.loads(campos["params"][0])))
        return 200, {}, json.dumps({ident: {"dados": [{"id": i} for i in range(total)][:100], "total": total}})
    responses.add_callback(responses.POST, f"{PORTAL}/api/{acao}", callback=callback, content_type="application/json")


def _acoes():
    return [c.request.url.split("/api/")[1] for c in responses.calls if "/api/" in c.request.url]


@responses.activate
def test_aprende_o_sufixo_na_pagina_inicial_uma_vez_so():
    responses.add(responses.GET, f"{PORTAL}/", body='<div class="nucleogov"><a href="/servidores_cnt">x</a></div>')
    _modulo("servidores_cnt/listar", 224)
    portal = Portal(PORTAL, pausa=0)
    assert portal.folha(2025, 3, maximo=1)["total"] == 224
    assert portal.folha(2025, 4, maximo=1)["total"] == 224
    assert _acoes() == ["servidores_cnt/listar", "servidores_cnt/listar"]
    assert sum(1 for c in responses.calls if c.request.method == "GET") == 1


@responses.activate
def test_modulo_fora_da_pagina_tenta_frl_e_com_zero_tenta_cnt_e_guarda():
    responses.add(responses.GET, f"{PORTAL}/", body='<div class="nucleogov"></div>')
    _modulo("despesas_frl/listar", 0)
    _modulo("despesas_cnt/listar", 37)
    portal = Portal(PORTAL, pausa=0)
    assert portal.despesas("2025-01-01", "2025-01-31")["total"] == 37
    assert portal.despesas("2025-02-01", "2025-02-28")["total"] == 37
    assert _acoes() == ["despesas_frl/listar", "despesas_cnt/listar", "despesas_cnt/listar"]


@responses.activate
def test_zero_nos_dois_sufixos_e_zero_mesmo():
    responses.add(responses.GET, f"{PORTAL}/", status=500)
    _modulo("receitas_frl/listar", 0)
    _modulo("receitas_cnt/listar", 0)
    assert Portal(PORTAL, pausa=0).receitas(2025, 3)["total"] == 0


@responses.activate
def test_sufixos_informados_dispensam_a_pagina_inicial():
    _modulo("contratos_cnt/listar", 5)
    assert Portal(PORTAL, pausa=0, sufixos={"contratos": "cnt"}).contratos(2025)["total"] == 5
    assert all(c.request.method == "POST" for c in responses.calls)


@responses.activate
def test_modulo_da_megasoft_embutida_e_recusado_em_vez_de_devolver_zero():
    responses.add(responses.GET, f"{PORTAL}/", body='<div class="nucleogov"><a href="x/mgdespesas">D</a></div>')
    with pytest.raises(ErroPortal, match="Megasoft"):
        Portal(PORTAL, pausa=0).despesas("2025-01-01", "2025-01-31")
    assert all(c.request.method == "GET" for c in responses.calls)
