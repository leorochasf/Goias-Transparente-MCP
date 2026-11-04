"""Receitas: o portal só respeita ano + mês (datamin/datamax são ignorados). Testes offline."""
import json
import urllib.parse

import pytest
import responses

from transparencia_municipal import Portal
from transparencia_municipal import cli, servidor_mcp

PORTAL = "https://acessoainformacao.exemplo.go.gov.br"
ACAO = f"{PORTAL}/api/receitas_frl/listar"
REGISTRO = {"ano": 2025, "mes": 3, "descricao": "IPTU", "valor_total_arrecadado_mes": "10.00"}


def _corpo_enviado(requisicao):
    campos = urllib.parse.parse_qs(requisicao.body.decode("utf-8"))
    return next(iter(json.loads(campos["params"][0]).values()))


def _resposta(registros, total):
    def callback(requisicao):
        campos = urllib.parse.parse_qs(requisicao.body.decode("utf-8"))
        ident = next(iter(json.loads(campos["params"][0])))
        return 200, {}, json.dumps({ident: {"dados": registros, "total": total}})
    return callback


def _mock():
    responses.add_callback(responses.POST, ACAO, callback=_resposta([REGISTRO], 1),
                           content_type="application/json")


@responses.activate
def test_receitas_envia_ano_e_mes_sem_datas():
    _mock()
    r = Portal(PORTAL).receitas(2025, 3)
    assert r == {"total": 1, "registros": [REGISTRO]}
    enviado = _corpo_enviado(responses.calls[0].request)
    assert enviado["acao"] == "receitas_frl/listar"
    assert enviado["ano"] == "2025" and enviado["mes"] == "3"
    assert "datamin" not in enviado and "datamax" not in enviado


@responses.activate
def test_receitas_mes_vai_sem_zero_a_esquerda():
    _mock()
    Portal(PORTAL).receitas("2024", "03")
    assert _corpo_enviado(responses.calls[0].request)["mes"] == "3"


@pytest.mark.parametrize("mes", [0, 13, 3.9, "3.9"])
def test_receitas_mes_fora_de_1_a_12_e_valueerror_legivel(mes):
    with pytest.raises(ValueError, match="1 a 12"):
        Portal(PORTAL).receitas(2025, mes)


def test_receitas_ano_e_mes_sao_obrigatorios():
    with pytest.raises(TypeError):
        Portal(PORTAL).receitas(2025)


@responses.activate
def test_cli_receitas_usa_ano_e_mes(capsys):
    _mock()
    cli.main(["--portal", PORTAL, "receitas", "--ano", "2025", "--mes", "3"])
    enviado = _corpo_enviado(responses.calls[0].request)
    assert enviado["ano"] == "2025" and enviado["mes"] == "3"
    assert "1 registros no portal" in capsys.readouterr().out


def test_cli_receitas_exige_mes():
    with pytest.raises(SystemExit):
        cli.main(["--portal", PORTAL, "receitas", "--ano", "2025"])


@responses.activate
def test_cli_receitas_nao_aceita_mais_de_ate():
    with pytest.raises(SystemExit):
        cli.main(["--portal", PORTAL, "receitas", "--de", "2025-01-01", "--ate", "2025-03-31"])


def test_cli_receitas_mes_invalido_vira_erro_legivel():
    with pytest.raises(SystemExit, match="1 a 12"):
        cli.main(["--portal", PORTAL, "receitas", "--ano", "2025", "--mes", "13"])


@responses.activate
def test_mcp_consultar_receitas_usa_ano_e_mes():
    _mock()
    r = servidor_mcp.consultar_receitas(ano=2025, mes=3, portal=PORTAL)
    assert r["registros"] == [REGISTRO] and "aviso" in r
    enviado = _corpo_enviado(responses.calls[0].request)
    assert enviado["ano"] == "2025" and enviado["mes"] == "3"


def test_mcp_consultar_receitas_mes_invalido_devolve_erro():
    r = servidor_mcp.consultar_receitas(ano=2025, mes=13, portal=PORTAL)
    assert "1 a 12" in r["erro"]


def test_mcp_docstring_explica_um_mes_por_vez():
    doc = servidor_mcp.consultar_receitas.__doc__ or ""
    assert "um mês por vez" in doc
