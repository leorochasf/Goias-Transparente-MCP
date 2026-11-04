"""Testes offline: nenhuma requisição real sai daqui."""
import json
import urllib.parse

import pytest
import responses

from transparencia_municipal import ErroPortal, Portal, PortalBloqueou
from transparencia_municipal.cliente import UA_FERRAMENTA, UA_NAVEGADOR, _data_br

PORTAL = "https://acessoainformacao.exemplo.go.gov.br"


def _corpo_enviado(requisicao):
    campos = urllib.parse.parse_qs(requisicao.body.decode("utf-8"))
    return next(iter(json.loads(campos["params"][0]).values()))


def _resposta(registros, total):
    """A API devolve {"<id>": {...}}; o id vem do pedido, então ecoamos o que chegou."""
    def callback(requisicao):
        campos = urllib.parse.parse_qs(requisicao.body.decode("utf-8"))
        ident = next(iter(json.loads(campos["params"][0])))
        return 200, {}, json.dumps({ident: {"dados": registros, "total": total}})
    return callback


@responses.activate
def test_folha_monta_o_pedido_e_devolve_registros():
    responses.add_callback(responses.POST, f"{PORTAL}/api/servidores_frl/listar",
                           callback=_resposta([{"nome": "FULANO"}], 1), content_type="application/json")
    r = Portal(PORTAL).folha(2025, 3, busca="saude")
    assert r == {"total": 1, "registros": [{"nome": "FULANO", "fonte": "NucleoGov"}]}
    enviado = _corpo_enviado(responses.calls[0].request)
    assert enviado["acao"] == "servidores_frl/listar"
    assert enviado["ano"] == "2025" and enviado["mes"] == "3" and enviado["txtbusca"] == "saude"
    assert enviado["limit"] == "0, 100"


@responses.activate
def test_por_padrao_se_identifica_como_ferramenta():
    responses.add_callback(responses.POST, f"{PORTAL}/api/servidores_frl/listar",
                           callback=_resposta([], 0), content_type="application/json")
    Portal(PORTAL).folha(2025)
    assert responses.calls[0].request.headers["User-Agent"] == UA_FERRAMENTA


@responses.activate
def test_navegador_so_quando_pedido():
    responses.add_callback(responses.POST, f"{PORTAL}/api/servidores_frl/listar",
                           callback=_resposta([], 0), content_type="application/json")
    Portal(PORTAL, navegador=True).folha(2025)
    assert responses.calls[0].request.headers["User-Agent"] == UA_NAVEGADOR


@responses.activate
def test_403_explica_o_bloqueio_em_vez_de_contornar():
    responses.add(responses.POST, f"{PORTAL}/api/servidores_frl/listar", status=403, body="Forbidden")
    with pytest.raises(PortalBloqueou) as erro:
        Portal(PORTAL).folha(2025)
    assert "403" in str(erro.value) and "navegador=True" in str(erro.value)
    assert len(responses.calls) == 1, "não pode tentar de novo por conta própria"


@responses.activate
def test_resposta_que_nao_e_json_vira_erro_legivel():
    responses.add(responses.POST, f"{PORTAL}/api/servidores_frl/listar", status=200, body="<html>manutenção</html>")
    with pytest.raises(ErroPortal, match="resposta inesperada"):
        Portal(PORTAL).folha(2025)


@responses.activate
def test_pagina_ate_o_maximo_pedido():
    responses.add_callback(responses.POST, f"{PORTAL}/api/despesas_frl/listar",
                           callback=_resposta([{"id": i} for i in range(5)], 40),
                           content_type="application/json")
    r = Portal(PORTAL, por_pagina=5, pausa=0).despesas("2025-01-01", "2025-01-31", maximo=12)
    assert len(r["registros"]) == 12 and r["total"] == 40
    assert len(responses.calls) == 3
    assert _corpo_enviado(responses.calls[2].request)["limit"] == "10, 5"


@responses.activate
def test_para_quando_o_portal_acaba_antes_do_maximo():
    responses.add_callback(responses.POST, f"{PORTAL}/api/contratos_frl/listar",
                           callback=_resposta([{"id": 1}], 1), content_type="application/json")
    r = Portal(PORTAL, por_pagina=100).contratos(2025, maximo=500)
    assert len(r["registros"]) == 1 and len(responses.calls) == 1


@pytest.mark.parametrize("entrada,esperado", [
    ("2025-03-01", "01/03/2025"), ("2025-03", "01/03/2025"), ("15/04/2025", "15/04/2025")])
def test_datas_aceitam_tres_formatos(entrada, esperado):
    assert _data_br(entrada, campo="de") == esperado


def test_data_invalida_diz_o_que_esperava():
    with pytest.raises(ValueError, match="AAAA-MM-DD"):
        _data_br("março de 2025", campo="de")


def test_endereco_sem_esquema_ganha_https_e_perde_barra():
    assert Portal("acessoainformacao.exemplo.go.gov.br/").url == "https://acessoainformacao.exemplo.go.gov.br"
