"""Busca de despesas por CNPJ e acentos da CLI. Testes offline."""
import json
import os
import subprocess
import sys
import urllib.parse
from pathlib import Path

import pytest
import responses

from transparencia_municipal import Portal

PORTAL = "https://acessoainformacao.exemplo.go.gov.br"
ACAO = f"{PORTAL}/api/despesas_frl/listar"


def _corpo_enviado(requisicao):
    campos = urllib.parse.parse_qs(requisicao.body.decode("utf-8"))
    return next(iter(json.loads(campos["params"][0]).values()))


def _resposta(registros, total):
    def callback(requisicao):
        campos = urllib.parse.parse_qs(requisicao.body.decode("utf-8"))
        ident = next(iter(json.loads(campos["params"][0])))
        return 200, {}, json.dumps({ident: {"dados": registros, "total": total}})
    return callback


@pytest.mark.parametrize("busca", ["25.107.525/0001-51", "25107525000151", " 25.107.525/0001-51 "])
@responses.activate
def test_cnpj_vai_no_filtro_cpf_cnpj_formatado_e_nao_na_busca_livre(busca):
    registro = {"fornecedor": "EMPRESA X", "cpf_cnpj": "25.107.525/0001-51"}
    responses.add_callback(responses.POST, ACAO, callback=_resposta([registro], 1),
                           content_type="application/json")
    r = Portal(PORTAL).despesas("2025-01-01", "2025-01-31", busca=busca)
    assert r == {"total": 1, "registros": [registro]}
    enviado = _corpo_enviado(responses.calls[0].request)
    assert enviado["cpf_cnpj"] == "25.107.525/0001-51"
    assert "txtbusca" not in enviado


@pytest.mark.parametrize("busca", ["construtora", "123.456.789-01"])
@responses.activate
def test_texto_que_nao_e_cnpj_continua_na_busca_livre(busca):
    responses.add_callback(responses.POST, ACAO, callback=_resposta([], 0),
                           content_type="application/json")
    Portal(PORTAL).despesas("2025-01-01", "2025-01-31", busca=busca)
    enviado = _corpo_enviado(responses.calls[0].request)
    assert enviado["txtbusca"] == busca
    assert "cpf_cnpj" not in enviado


def test_erro_da_cli_sai_em_utf8_mesmo_com_terminal_em_outra_codificacao():
    """O erro sai por SystemExit em stderr; o terminal lê UTF-8. Porta 9 local: recusa na hora."""
    raiz = Path(__file__).resolve().parents[1]
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
    env.update(PYTHONPATH=str(raiz), PYTHONIOENCODING="cp1252")
    r = subprocess.run([sys.executable, "-m", "transparencia_municipal.cli", "--portal",
                        "http://127.0.0.1:9", "receitas", "--de", "2025-01", "--ate", "2025-02"],
                       capture_output=True, env=env, cwd=raiz, timeout=60)
    assert r.returncode == 1
    assert "não foi possível falar com" in r.stderr.decode("utf-8")
