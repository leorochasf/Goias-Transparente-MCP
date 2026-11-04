"""Megasoft embutida no NucleoGov (menu `mgservidores`/`mgdespesas`). Offline: página inicial e API simuladas.

O portal simulado segue o medido em Aruanã (04/11/2026): `POST /api/megasoft/<acao>` no envelope `multi_request`,
paginação por `pagina` (a partir de 1) e `tamanhoDaPagina`, resposta `{total, registros, paginaAtual}`; o filtro de
fornecedor não filtra no servidor (AJE); a fronteira de página pode repetir um registro e perder outro.
"""
import json
import urllib.parse
from datetime import datetime

import anyio
import pytest
import responses
from mcp import Client

from transparencia_municipal import Portal, megasoft_embutida, servidor_mcp
from transparencia_municipal.cliente import ErroPortal

pytestmark = pytest.mark.descobre_sufixos
PORTAL = "https://acessoainformacao.exemplo.go.gov.br"


def _pedido(requisicao):
    ident, corpo = next(iter(json.loads(urllib.parse.parse_qs(requisicao.body.decode())["params"][0]).items()))
    return ident, corpo


def _portal_com_megasoft(*, servidores=(), empenhos=(), repete_na_fronteira=False):
    """Página inicial com os menus `mg*`, API NucleoGov sem esses módulos e a Megasoft embutida respondendo.

    Devolve a lista dos corpos recebidos pela Megasoft, na ordem.
    """
    responses.add(responses.GET, f"{PORTAL}/",
                  body='<div class="nucleogov"><a href="x/mgservidores">F</a><a href="x/mgdespesas">D</a></div>')

    def vazio(requisicao):
        ident, _ = _pedido(requisicao)
        return 200, {}, json.dumps({ident: {"dados": [], "total": 0}})
    for modulo in ("servidores", "despesas"):
        for sufixo in ("frl", "cnt"):
            responses.add_callback(responses.POST, f"{PORTAL}/api/{modulo}_{sufixo}/listar", callback=vazio,
                                   content_type="application/json")
    pedidos = []

    def megasoft(registros_de):
        def callback(requisicao):
            ident, corpo = _pedido(requisicao)
            pedidos.append(corpo)
            todos = registros_de(corpo)
            n, p = corpo["tamanhoDaPagina"], corpo["pagina"]
            pagina = todos[(p - 1) * n:p * n]
            if repete_na_fronteira and p > 1:  # repete o último da página anterior e perde o primeiro desta
                pagina = [todos[(p - 1) * n - 1]] + pagina[1:]
            return 200, {}, json.dumps({ident: {"total": len(todos), "registros": pagina, "paginaAtual": p}})
        return callback

    def da_folha(corpo):
        return [s for s in servidores if (s["ano"], s["mes"]) == (int(corpo["ano"]), corpo["mes"])]

    def do_periodo(corpo):
        de, ate = (datetime.strptime(corpo[c], "%d/%m/%Y") for c in ("dataInicial", "dataFinal"))
        return [e for e in empenhos if de <= datetime.strptime(e["data"], "%d/%m/%Y") <= ate]

    responses.add_callback(responses.POST, f"{PORTAL}/api/megasoft/servidores", callback=megasoft(da_folha),
                           content_type="application/json")
    responses.add_callback(responses.POST, f"{PORTAL}/api/megasoft/empenhos", callback=megasoft(do_periodo),
                           content_type="application/json")
    return pedidos


def _servidor(i, **campos):
    return {"ano": 2025, "mes": "06", "mesAno": "06/2025", "matricula": i, "nome": f"PESSOA {i}",
            "cpf": "XXX.000.000-XX", "cargo": "AGENTE", "departamento": "SECRETARIA DE SAÚDE",
            "tipoDeVinculo": "Comissionado" if i % 2 else "Concursado", "proventos": 1000 + i, "descontos": 100,
            "totalLiquido": 900 + i, "situacao": "Ativo", "situacaoPagamento": "PAGO",
            "chave": {"matricula": i, "mes": 6, "ano": 2025}, **campos}


def _empenho(codigo, data, documento="25.107.525/0001-51", nome="EMPRESA EXEMPLO LTDA"):
    return {"codigo": codigo, "data": data, "cnpjENomeDoFornecedor": f"{documento}/{nome}", "nomeDoFornecedor": nome,
            "historico": "MATERIAL", "valorTotalDoEmpenho": 100, "valorTotalDaLiquidacao": 100,
            "valorTotalDoPagamento": 100}


@pytest.fixture
def pagina_de_2(monkeypatch):
    monkeypatch.setattr(megasoft_embutida, "POR_PAGINA", 2)


# ── ponto `Portal` ────────────────────────────────────────────────────────

@responses.activate
def test_folha_mg_vem_traduzida_com_fonte_e_paginacao_completa(pagina_de_2):
    pedidos = _portal_com_megasoft(servidores=[_servidor(i) for i in range(1, 6)] + [_servidor(9, mes="07")])
    andamento = []
    r = Portal(PORTAL, pausa=0).folha(2025, 6, maximo=1000, progresso=lambda lidas, total: andamento.append(lidas))
    assert r["total"] == 5
    assert [x["matricula"] for x in r["registros"]] == ["1", "2", "3", "4", "5"]
    assert {x["fonte"] for x in r["registros"]} == {"Megasoft"}
    assert r["registros"][0]["total_proventos"] == "1.001,00" and r["registros"][0]["vinculo"] == "Comissionado"
    assert andamento == [2, 4, 5]
    assert [(p["pagina"], p["tamanhoDaPagina"]) for p in pedidos] == [(1, 2), (2, 2), (3, 2)]
    assert {(p["mes"], p["ano"], p["mesInteger"], json.dumps(p["ordenacao"])) for p in pedidos} == {
        ("06", "2025", 6, "{}")}


@responses.activate
def test_folha_que_nao_fecha_devolve_o_lido_e_o_total_anunciado(pagina_de_2):
    _portal_com_megasoft(servidores=[_servidor(i) for i in range(1, 6)], repete_na_fronteira=True)
    r = Portal(PORTAL, pausa=0).folha(2025, 6, maximo=1000)
    assert r["total"] == 5
    assert len(r["registros"]) < 5  # repetido tirado; quem lê o mês declara "incompleta"
    assert len({x["matricula"] for x in r["registros"]}) == len(r["registros"])


@responses.activate
def test_folha_por_nome_filtra_aqui_e_recusa_filtrar_leitura_que_nao_fecha(pagina_de_2):
    _portal_com_megasoft(servidores=[_servidor(i) for i in range(1, 6)] + [_servidor(7, nome="Fulána de Tal")])
    r = Portal(PORTAL, pausa=0).folha(2025, 6, "fulana")
    assert r["total"] == 1 and [x["matricula"] for x in r["registros"]] == ["7"]

    responses.reset()
    _portal_com_megasoft(servidores=[_servidor(i) for i in range(1, 6)], repete_na_fronteira=True)
    with pytest.raises(ErroPortal, match="incompleta"):
        Portal(PORTAL, pausa=0).folha(2025, 6, "PESSOA 3")


@responses.activate
def test_despesas_mg_vem_traduzidas_e_sem_filtro_pedem_so_o_maximo():
    pedidos = _portal_com_megasoft(empenhos=[_empenho(i, f"{i:02d}/01/2025") for i in range(1, 8)])
    r = Portal(PORTAL, pausa=0).despesas("2025-01-01", "2025-03-31", maximo=3)
    assert r["total"] == 7 and len(r["registros"]) == 3
    assert r["registros"][0] == {"empenho": 1, "data": "01/01/2025", "cpf_cnpj": "25.107.525/0001-51",
                                 "fornecedor": "EMPRESA EXEMPLO LTDA", "valor_empenhado": "100,00",
                                 "valor_liquidado": "100,00", "valor_pago": "100,00", "historico": "MATERIAL",
                                 "fonte": "Megasoft"}
    assert [(p["dataInicial"], p["dataFinal"], p["pagina"], p["tamanhoDaPagina"]) for p in pedidos] == [
        ("01/01/2025", "31/03/2025", 1, 3)]


@responses.activate
def test_despesas_por_cnpj_filtram_aqui_mes_a_mes_no_periodo_inteiro():
    """O servidor não filtra o fornecedor; mês a mês, cada leitura cabe numa página e não cruza fronteira."""
    outro = "11.364.935/0001-73"
    empenhos = [_empenho(1, "10/01/2025"), _empenho(2, "11/01/2025", outro, "OUTRA LTDA"),
                _empenho(3, "28/02/2025"), _empenho(4, "05/03/2025", outro, "OUTRA LTDA"),
                _empenho(5, "01/04/2025")]
    pedidos = _portal_com_megasoft(empenhos=empenhos)
    r = Portal(PORTAL, pausa=0).despesas("2025-01-15", "2025-03-31", "25107525000151", maximo=1)
    assert r["total"] == 1 and [x["empenho"] for x in r["registros"]] == [3]
    assert [(p["dataInicial"], p["dataFinal"]) for p in pedidos] == [
        ("15/01/2025", "31/01/2025"), ("01/02/2025", "28/02/2025"), ("01/03/2025", "31/03/2025")]

    r = Portal(PORTAL, pausa=0).despesas("2025-01-01", "2025-03-31", "outra")
    assert r["total"] == 2 and [x["empenho"] for x in r["registros"]] == [2, 4]


@responses.activate
def test_despesas_com_filtro_recusam_mes_que_nao_fecha(pagina_de_2):
    _portal_com_megasoft(empenhos=[_empenho(i, f"{i:02d}/01/2025") for i in range(1, 6)], repete_na_fronteira=True)
    with pytest.raises(ErroPortal, match="incompleta"):
        Portal(PORTAL, pausa=0).despesas("2025-01-01", "2025-01-31", "25107525000151")


# ── ponta a ponta, por cliente MCP no mesmo processo ─────────────────────

@responses.activate
def test_listar_folha_por_vinculo_num_portal_com_folha_megasoft_embutida(monkeypatch):
    _portal_com_megasoft(servidores=[_servidor(i) for i in range(1, 6)])
    monkeypatch.setattr(servidor_mcp, "_portal", lambda url=None: Portal(url or PORTAL, pausa=0))
    servidor_mcp._LEITURAS.clear()

    async def rodar():
        async with Client(servidor_mcp.mcp) as cliente:
            r = await cliente.call_tool("listar_folha", {"ano": 2025, "mes": 6, "vinculo": "comissionado"})
            return json.loads(r.content[0].text)
    try:
        r = anyio.run(rodar)
    finally:
        servidor_mcp._LEITURAS.clear()
    assert "erro" not in r, r
    assert (r["total_do_mes"], r["encontradas"]) == (5, 3)
    assert [x["matricula"] for x in r["linhas"]] == ["1", "3", "5"]
    assert {x["fonte"] for x in r["linhas"]} == {"Megasoft"}
