"""Leitura do mês: a folha inteira, página por página, guardada só quando completa. Offline."""
import json
import urllib.parse

import pytest
import responses

from transparencia_municipal import ErroPortal, Portal, servidor_mcp

PORTAL = "https://acessoainformacao.exemplo.go.gov.br"
ACAO = f"{PORTAL}/api/servidores_frl/listar"


def _folha_paginada(total, *, falha_no_offset=None, para_no_offset=None):
    """Simula o portal: `total` linhas, 100 por página; pode falhar ou parar de mandar linhas num offset."""
    def callback(requisicao):
        campos = urllib.parse.parse_qs(requisicao.body.decode("utf-8"))
        ident, corpo = next(iter(json.loads(campos["params"][0]).items()))
        offset, n = (int(v) for v in corpo["limit"].split(","))
        if offset == falha_no_offset:
            return 500, {}, "erro interno"
        fim = offset if offset == para_no_offset else min(offset + n, total)
        dados = [{"matricula": str(i), "nome": f"PESSOA {i}", "tipo_folha": "Folha Mensal",
                  "total_proventos": "1.000,00", "total_liquido": "900,00", "eventos": [{"x": 1}]}
                 for i in range(offset, fim)]
        return 200, {}, json.dumps({ident: {"dados": dados, "total": total}})
    return callback


@pytest.fixture(autouse=True)
def memoria_limpa():
    servidor_mcp._LEITURAS.clear()
    yield
    servidor_mcp._LEITURAS.clear()


@responses.activate
def test_consultar_avisa_o_progresso_a_cada_pagina():
    responses.add_callback(responses.POST, ACAO, callback=_folha_paginada(250), content_type="application/json")
    avisos = []
    Portal(PORTAL, pausa=0).folha(2025, 3, maximo=10_000, progresso=lambda lidas, total: avisos.append((lidas, total)))
    assert avisos == [(100, 250), (200, 250), (250, 250)]


@responses.activate
def test_leitura_do_mes_traz_linhas_leves_e_a_segunda_vez_nao_chama_o_portal():
    responses.add_callback(responses.POST, ACAO, callback=_folha_paginada(250), content_type="application/json")
    portal = Portal(PORTAL, pausa=0)
    linhas = servidor_mcp._ler_mes(portal, 2025, 3)
    assert len(linhas) == 250 and "eventos" not in linhas[0] and linhas[0]["bruto"] == "1.000,00"
    chamadas = len(responses.calls)
    assert servidor_mcp._ler_mes(portal, 2025, 3) == linhas
    assert len(responses.calls) == chamadas == 3


@responses.activate
def test_falha_no_meio_da_leitura_diz_ate_onde_leu_e_nao_guarda_nada():
    responses.add_callback(responses.POST, ACAO, callback=_folha_paginada(250, falha_no_offset=100),
                           content_type="application/json")
    with pytest.raises(ErroPortal, match="100 de 250"):
        servidor_mcp._ler_mes(Portal(PORTAL, pausa=0), 2025, 3)
    assert servidor_mcp._LEITURAS == {}


@responses.activate
def test_leitura_incompleta_nao_e_guardada():
    responses.add_callback(responses.POST, ACAO, callback=_folha_paginada(250, para_no_offset=200),
                           content_type="application/json")
    with pytest.raises(ErroPortal, match="200 de 250"):
        servidor_mcp._ler_mes(Portal(PORTAL, pausa=0), 2025, 3)
    assert servidor_mcp._LEITURAS == {}


@responses.activate
def test_mes_vazio_diz_que_o_portal_nao_tem_folha():
    responses.add_callback(responses.POST, ACAO, callback=_folha_paginada(0), content_type="application/json")
    with pytest.raises(ValueError, match="não tem folha de 03/2025"):
        servidor_mcp._ler_mes(Portal(PORTAL, pausa=0), 2025, 3)
