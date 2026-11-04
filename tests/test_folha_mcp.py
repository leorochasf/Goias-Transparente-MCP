"""Ferramentas de folha do MCP, por um cliente MCP no mesmo processo. Offline."""
import json
import urllib.parse

import anyio
import pytest
import responses
from mcp import Client

from transparencia_municipal import Portal, servidor_mcp

PORTAL = "https://acessoainformacao.exemplo.go.gov.br"
ACAO = f"{PORTAL}/api/servidores_frl/listar"


def _linha(i, **campos):
    return {"matricula": str(i), "nome": f"PESSOA {i}", "cpf": "***.000.000-**", "cargo": "AGENTE",
            "lotacao": "SECRETARIA DE SAÚDE" if i % 2 else "SECRETARIA DE EDUCAÇÃO",
            "vinculo": "03 - COMISSIONADO" if i % 3 == 0 else "02 - Concursado",
            "tipo_folha": "Folha Mensal", "total_proventos": "1.000,00", "total_desconto": "100,00",
            "total_liquido": "900,00", "eventos": [{"x": 1}],
            "lista_proventos": [{"evento": "1", "nome": "VENCIMENTO", "valor": "1.000,00", "tipo": "Provento"}],
            "lista_descontos": [{"evento": "9", "nome": "INSS", "valor": "100,00", "tipo": "Desconto"}],
            **campos}


def _portal_com(linhas):
    """Simula o portal com estas linhas, 100 por página."""
    def callback(requisicao):
        campos = urllib.parse.parse_qs(requisicao.body.decode("utf-8"))
        ident, corpo = next(iter(json.loads(campos["params"][0]).items()))
        offset, n = (int(v) for v in corpo["limit"].split(","))
        return 200, {}, json.dumps({ident: {"dados": linhas[offset:offset + n], "total": len(linhas)}})
    responses.add_callback(responses.POST, ACAO, callback=callback, content_type="application/json")


@pytest.fixture(autouse=True)
def sem_pausa(monkeypatch):
    monkeypatch.setattr(servidor_mcp, "_portal", lambda url=None: Portal(url or PORTAL, pausa=0))
    servidor_mcp._LEITURAS.clear()
    yield
    servidor_mcp._LEITURAS.clear()


def _chamar(ferramenta, **argumentos):
    """Chama a ferramenta como um assistente chamaria; devolve (resultado, avisos de progresso)."""
    avisos = []

    async def ao_progredir(progresso, total, mensagem):
        avisos.append((progresso, total, mensagem))

    async def rodar():
        async with Client(servidor_mcp.mcp) as cliente:
            r = await cliente.call_tool(ferramenta, argumentos, progress_callback=ao_progredir)
            return json.loads(r.content[0].text)  # o que o assistente recebe

    return anyio.run(rodar), avisos


@responses.activate
def test_consultar_folha_por_nome_traz_linhas_leves_com_rubricas_ate_10_linhas():
    _portal_com([_linha(1), _linha(2)])
    r, _ = _chamar("consultar_folha", ano=2025, mes=3, busca="PESSOA")
    assert r["total"] == 2 and len(r["linhas"]) == 2
    assert "eventos" not in r["linhas"][0]
    assert [x["nome"] for x in r["linhas"][0]["rubricas"]] == ["VENCIMENTO", "INSS"]


@responses.activate
def test_consultar_folha_com_mais_de_10_linhas_vem_sem_rubricas_e_avisa():
    _portal_com([_linha(i) for i in range(11)])
    r, _ = _chamar("consultar_folha", ano=2025, mes=3, busca="PESSOA")
    assert all("rubricas" not in x for x in r["linhas"])
    assert "rubricas" in r["aviso_rubricas"]


def test_ferramentas_de_folha_exigem_o_mes():
    async def esquemas():
        async with Client(servidor_mcp.mcp) as cliente:
            return {t.name: t.input_schema for t in (await cliente.list_tools()).tools}
    esquema = anyio.run(esquemas)
    for nome in ("consultar_folha", "listar_folha", "resumir_folha"):
        assert "mes" in esquema[nome]["required"], nome


@responses.activate
def test_listar_folha_filtra_o_mes_inteiro_avisa_o_progresso_e_o_corte():
    _portal_com([_linha(i) for i in range(250)])  # comissionados: i múltiplo de 3 → 84 linhas
    r, avisos = _chamar("listar_folha", ano=2025, mes=3, vinculo="comissionado", maximo=50)
    assert r["total_do_mes"] == 250 and r["encontradas"] == 84 and len(r["linhas"]) == 50
    assert "50 de 84" in r["aviso_corte"]
    assert [(p, t) for p, t, _ in avisos] == [(100, 250), (200, 250), (250, 250)]
    assert "página 3 de 3" in avisos[-1][2]


@responses.activate
def test_resumir_folha_agrupa_sem_nomes_e_reaproveita_a_leitura():
    _portal_com([_linha(i) for i in range(250)])
    r, _ = _chamar("resumir_folha", ano=2025, mes=3, agrupar_por="lotacao", vinculo="comissionado")
    mensal = r["por_tipo_de_pagamento"]["Folha Mensal"]
    assert (mensal["linhas"], mensal["bruto"], mensal["liquido"]) == (84, 84000.0, 75600.0)
    assert {g["grupo"] for g in mensal["grupos"]} == {"SECRETARIA DE SAÚDE", "SECRETARIA DE EDUCAÇÃO"}
    assert "PESSOA" not in json.dumps(r)
    chamadas = len(responses.calls)
    _chamar("listar_folha", ano=2025, mes=3)
    assert len(responses.calls) == chamadas


@responses.activate
def test_resumir_folha_recusa_agrupamento_invalido_antes_de_ler_o_mes():
    _portal_com([_linha(1)])
    r, _ = _chamar("resumir_folha", ano=2025, mes=3, agrupar_por="secretaria")
    assert "cargo, lotacao ou vinculo" in r["erro"]
    assert len(responses.calls) == 0



@responses.activate
def test_listar_folha_filtra_pelo_nome_na_leitura_do_mes():
    _portal_com([_linha(i) for i in range(30)])
    r, _ = _chamar("listar_folha", ano=2025, mes=3, nome="pessoa 1")
    assert sorted(x["nome"] for x in r["linhas"]) == ["PESSOA 1"] + [f"PESSOA 1{i}" for i in range(10)]
