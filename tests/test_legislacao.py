"""Legislação: offline, sem requisição real.

Medido ao vivo em Senador Canedo (04/11/2026): `atos_pf_senador_canedo/listar` volta vazio;
os atos estão em `atos/buscaAvancada`, com tipo numérico (1 decreto, 2 portaria, 3 resolução)
e a busca livre no campo `search`.
"""
import json
import urllib.parse

import pytest
import responses

from transparencia_municipal import Portal, cli, servidor_mcp

PORTAL = "https://acessoainformacao.exemplo.go.gov.br"
ATOS = f"{PORTAL}/api/atos/buscaAvancada"
DECRETO = {"id": "4972", "numero": "770", "data_publicacao": "2026-05-20", "tipo": "1",
           "tipo_nome": "Decreto", "ementa": "DISPÕE SOBRE NOMEAÇÃO EM FUNÇÃO"}


def _corpo_enviado(requisicao):
    campos = urllib.parse.parse_qs(requisicao.body.decode("utf-8"))
    return next(iter(json.loads(campos["params"][0]).values()))


def _resposta(registros, total):
    def callback(requisicao):
        campos = urllib.parse.parse_qs(requisicao.body.decode("utf-8"))
        ident = next(iter(json.loads(campos["params"][0])))
        return 200, {}, json.dumps({ident: {"dados": registros, "total": total}})
    return callback


def _mock_atos():
    responses.add_callback(responses.POST, ATOS, callback=_resposta([DECRETO], 1),
                           content_type="application/json")


@responses.activate
def test_decretos_vem_do_modulo_atos_com_tipo_numerico_e_busca_no_campo_search():
    _mock_atos()
    r = Portal(PORTAL).legislacao("DECRETO", busca="cargo", ano=2026)
    assert r == {"total": 1, "registros": [DECRETO]}
    enviado = _corpo_enviado(responses.calls[0].request)
    assert enviado["acao"] == "atos/buscaAvancada"
    assert enviado["tipo"] == 1
    assert enviado["search"] == "cargo" and "txtbusca" not in enviado
    assert enviado["ano"] == "2026"


@responses.activate
def test_sem_tipo_traz_decretos():
    _mock_atos()
    Portal(PORTAL).legislacao()
    enviado = _corpo_enviado(responses.calls[0].request)
    assert enviado["tipo"] == 1 and "search" not in enviado and "ano" not in enviado


@pytest.mark.parametrize("tipo,codigo", [
    ("portaria", 2), ("PORTARIA", 2), ("Resolução", 3), ("resolucao", 3), ("decreto", 1), (2, 2), ("3", 3)])
@responses.activate
def test_tipo_aceita_nome_ou_codigo(tipo, codigo):
    _mock_atos()
    Portal(PORTAL).legislacao(tipo)
    assert _corpo_enviado(responses.calls[0].request)["tipo"] == codigo


def test_tipo_desconhecido_diz_quais_existem():
    with pytest.raises(ValueError, match="DECRETO, PORTARIA, RESOLUCAO"):
        Portal(PORTAL).legislacao("senador_canedo")


@responses.activate
def test_cli_legislacao_dispensa_apelido_e_aceita_ano(capsys):
    _mock_atos()
    cli.main(["--portal", PORTAL, "legislacao", "--tipo", "portaria", "--busca", "fiscal", "--ano", "2025"])
    enviado = _corpo_enviado(responses.calls[0].request)
    assert enviado["tipo"] == 2 and enviado["search"] == "fiscal" and enviado["ano"] == "2025"
    assert "1 registros no portal" in capsys.readouterr().out


@responses.activate
def test_mcp_consultar_legislacao(monkeypatch):
    monkeypatch.delenv("TRANSPARENCIA_NAVEGADOR", raising=False)
    _mock_atos()
    r = servidor_mcp.consultar_legislacao(tipo="DECRETO", busca="cargo", ano=2026, portal=PORTAL)
    assert r["registros"] == [DECRETO] and "aviso" in r
    enviado = _corpo_enviado(responses.calls[0].request)
    assert enviado["tipo"] == 1 and enviado["search"] == "cargo" and enviado["ano"] == "2026"
