"""O caminho de cada módulo, decidido num ponto único do `Portal`. Offline; cada encaixe é trocado por um dublê.

Caminhos: API NucleoGov; Megasoft embutida (menu `mg*`); Centi (menu `cnt*`); Megasoft de domínio próprio
(`*.megasofttransparencia.com.br`, o portal inteiro). Os encaixes ainda recusam (`ModuloNaoSuportado`).
"""
import json
import urllib.parse

import pytest
import responses

from transparencia_municipal import Portal, centi, megasoft_embutida, megasoft_propria, servidor_mcp
from transparencia_municipal.cliente import ModuloNaoSuportado

pytestmark = pytest.mark.descobre_sufixos
NUCLEOGOV = "https://acessoainformacao.exemplo.go.gov.br"
PROPRIA = "https://exemplo.megasofttransparencia.com.br"


def _sem_dados(*acoes):
    """A API NucleoGov não serve estes módulos: total 0 (medido em Posse, 04/11/2026)."""
    def callback(requisicao):
        ident = next(iter(json.loads(urllib.parse.parse_qs(requisicao.body.decode())["params"][0])))
        return 200, {}, json.dumps({ident: {"dados": [], "total": 0}})
    for acao in acoes:
        responses.add_callback(responses.POST, f"{NUCLEOGOV}/api/{acao}/listar", callback=callback,
                               content_type="application/json")


def _duble(monkeypatch, modulo, funcao):
    """Troca o encaixe por um dublê que guarda os argumentos e devolve uma linha marcada."""
    chamadas = []

    def duble(portal, **argumentos):
        chamadas.append((portal.url, argumentos))
        return {"total": 1, "registros": [{"fonte": f"dublê {modulo.__name__}.{funcao}"}]}
    monkeypatch.setattr(modulo, funcao, duble)
    return chamadas


@responses.activate
def test_portal_megasoft_proprio_vai_inteiro_pelo_encaixe_sem_pagina_inicial(monkeypatch):
    folha = _duble(monkeypatch, megasoft_propria, "folha")
    despesas = _duble(monkeypatch, megasoft_propria, "despesas")
    portal = Portal(PROPRIA, pausa=0)
    assert portal.folha(2025, 6, maximo=50)["registros"][0]["fonte"].endswith("megasoft_propria.folha")
    portal.despesas("2025-01-01", "2025-03-31", "25107525000151")
    assert folha == [(PROPRIA, {"ano": 2025, "mes": 6, "busca": None, "maximo": 50, "progresso": None})]
    assert despesas == [(PROPRIA, {"de": "01/01/2025", "ate": "31/03/2025", "cnpj": "25.107.525/0001-51",
                                   "busca": None, "maximo": 200})]
    assert len(responses.calls) == 0  # nem página inicial, nem API NucleoGov: o endereço basta


@responses.activate
def test_modulo_mg_vai_pelo_encaixe_da_megasoft_embutida(monkeypatch):
    responses.add(responses.GET, f"{NUCLEOGOV}/", body='<div class="nucleogov"><a href="x/mgservidores">F</a></div>')
    _sem_dados("servidores_frl", "servidores_cnt")
    chamadas = _duble(monkeypatch, megasoft_embutida, "folha")
    r = Portal(NUCLEOGOV, pausa=0).folha(2025, 6, "FULANO")
    assert r["registros"][0]["fonte"].endswith("megasoft_embutida.folha")
    assert chamadas == [(NUCLEOGOV, {"ano": 2025, "mes": 6, "busca": "FULANO", "maximo": 200, "progresso": None})]


@responses.activate
def test_modulo_centi_vai_pelo_encaixe_da_centi(monkeypatch):
    responses.add(responses.GET, f"{NUCLEOGOV}/", body='<div class="nucleogov"><a href="x/cntdespesas">D</a></div>')
    _sem_dados("despesas_frl", "despesas_cnt")
    chamadas = _duble(monkeypatch, centi, "despesas")
    r = Portal(NUCLEOGOV, pausa=0).despesas("2025-01", "2025-01-31", "EMPRESA X", maximo=10)
    assert r["registros"][0]["fonte"].endswith("centi.despesas")
    assert chamadas == [(NUCLEOGOV, {"de": "01/01/2025", "ate": "31/01/2025", "cnpj": None,
                                     "busca": "EMPRESA X", "maximo": 10})]


@responses.activate
def test_portal_megasoft_proprio_recusa_os_modulos_que_nao_le_e_nao_chama_o_portal():
    portal = Portal(PROPRIA, pausa=0)
    for consulta in (lambda: portal.receitas(2025, 3), lambda: portal.contratos(2025),
                     lambda: portal.legislacao("DECRETO")):
        with pytest.raises(ModuloNaoSuportado, match="Megasoft"):
            consulta()
    assert len(responses.calls) == 0


@responses.activate
def test_modulo_que_o_encaixe_nao_le_e_recusado_pelo_portal(monkeypatch):
    """A Centi de despesas não traz receitas: o módulo `cntreceitas` continua recusado, como hoje."""
    responses.add(responses.GET, f"{NUCLEOGOV}/", body='<div class="nucleogov"><a href="x/cntreceitas">R</a></div>')
    _sem_dados("receitas_frl", "receitas_cnt")
    with pytest.raises(ModuloNaoSuportado, match="Centi"):
        Portal(NUCLEOGOV, pausa=0).receitas(2025, 3)


@responses.activate
def test_leitura_do_mes_de_outro_sistema_nao_sonda_orgaos_e_leva_a_fonte(monkeypatch):
    """A sondagem de órgãos escondidos é exclusiva do NucleoGov."""
    linha = {"matricula": "1", "nome": "PESSOA 1", "tipo_folha": "Mensal", "total_proventos": "1.000,00",
             "total_liquido": "900,00", "orgao_id": "3", "fonte": "Megasoft"}
    monkeypatch.setattr(megasoft_propria, "folha", lambda portal, **_: {"total": 1, "registros": [linha]})
    servidor_mcp._LEITURAS.clear()
    try:
        linhas = servidor_mcp._ler_mes(Portal(PROPRIA, pausa=0), 2025, 6)
    finally:
        servidor_mcp._LEITURAS.clear()
    assert [x["fonte"] for x in linhas] == ["Megasoft"]
    assert len(responses.calls) == 0


def test_mcp_deixa_a_decisao_da_megasoft_para_o_portal(monkeypatch):
    """O catálogo marca o órgão como `megasoft`; quem decide o caminho é o Portal, não o servidor MCP."""
    from transparencia_municipal import catalogo
    corumbaiba = {"municipio": "Corumbaíba", "orgao": "prefeitura", "portal": PROPRIA, "plataforma": "megasoft",
                  "sufixos": {}, "outros_enderecos": [], "conferencia": None}
    monkeypatch.setattr(catalogo, "carregar", lambda: [corumbaiba])
    chamadas = _duble(monkeypatch, megasoft_propria, "despesas")
    r = servidor_mcp.consultar_despesas("2025-01-01", "2025-01-31", portal=PROPRIA)
    assert "erro" not in r and len(chamadas) == 1


def test_consultar_folha_de_outro_sistema_avisa_que_nao_ha_rubricas(monkeypatch):
    """Rubricas da Megasoft exigiriam a consulta de detalhe por servidor: fora do escopo, e a resposta avisa."""
    linha = {"matricula": "1", "nome": "PESSOA 1", "tipo_folha": "Mensal", "fonte": "Megasoft"}
    monkeypatch.setattr(megasoft_propria, "folha", lambda portal, **_: {"total": 1, "registros": [linha]})
    r = servidor_mcp.consultar_folha(2025, 6, busca="PESSOA", portal=PROPRIA)
    assert "rubricas" not in r["linhas"][0] and r["linhas"][0]["fonte"] == "Megasoft"
    assert "não traz rubricas" in r["aviso_rubricas"]


@responses.activate
def test_sondagem_da_api_nucleogov_num_modulo_mg_fica_lembrada_por_endereco(monkeypatch):
    """O servidor MCP cria um Portal por consulta; a API NucleoGov é sondada uma vez só por endereço e módulo."""
    _sem_dados("servidores_frl", "servidores_cnt")
    chamadas = _duble(monkeypatch, megasoft_embutida, "folha")
    for _ in range(3):
        Portal(NUCLEOGOV, pausa=0, sufixos={"servidores": "mg"}).folha(2025, 6, maximo=5)
    assert len(chamadas) == 3
    assert len(responses.calls) == 2  # servidores_frl e servidores_cnt, só na primeira consulta


@responses.activate
def test_registros_da_api_nucleogov_dizem_a_fonte():
    def callback(requisicao):
        ident = next(iter(json.loads(urllib.parse.parse_qs(requisicao.body.decode())["params"][0])))
        return 200, {}, json.dumps({ident: {"dados": [{"nome": "PESSOA 1"}], "total": 1}})
    for acao in ("servidores_frl", "despesas_frl"):
        responses.add_callback(responses.POST, f"{NUCLEOGOV}/api/{acao}/listar", callback=callback,
                               content_type="application/json")
    portal = Portal(NUCLEOGOV, pausa=0, sufixos={"servidores": "frl", "despesas": "frl"})
    assert portal.folha(2025, 6)["registros"] == [{"nome": "PESSOA 1", "fonte": "NucleoGov"}]
    assert portal.despesas("2025-01-01", "2025-01-31")["registros"][0]["fonte"] == "NucleoGov"


def test_consultar_despesas_avisa_quando_os_empenhos_misturam_orgaos(monkeypatch):
    """Centi com `id_orgao=0` (Posse) e Megasoft (Aruanã) trazem a Câmara e os fundos junto com a Prefeitura."""
    from transparencia_municipal import catalogo
    monkeypatch.setattr(catalogo, "carregar", lambda: [])
    misturados = [{"empenho": 1, "orgao": "PODER EXECUTIVO", "fonte": "Megasoft"},
                  {"empenho": 2, "orgao": "PODER LEGISLATIVO", "fonte": "Megasoft"}]
    monkeypatch.setattr(megasoft_propria, "despesas", lambda portal, **_: {"total": 2, "registros": misturados})
    r = servidor_mcp.consultar_despesas("2025-01-01", "2025-01-31", portal=PROPRIA)
    assert "mais de um órgão" in r["aviso_orgaos"] and "orgao" in r["aviso_orgaos"]
    monkeypatch.setattr(megasoft_propria, "despesas",
                        lambda portal, **_: {"total": 1, "registros": misturados[:1]})
    assert "aviso_orgaos" not in servidor_mcp.consultar_despesas("2025-01-01", "2025-01-31", portal=PROPRIA)


def test_consultar_folha_diz_que_na_megasoft_o_13_nao_vem_em_linha_propria():
    doc = servidor_mcp.consultar_folha.__doc__
    assert "13º" in doc and "Megasoft" in doc


@responses.activate
def test_sondagem_que_falhou_na_rede_nao_fica_lembrada(monkeypatch):
    """Erro passageiro da API NucleoGov não pode virar "a API não serve o módulo" até o processo fechar."""
    for acao in ("servidores_frl", "servidores_cnt"):
        responses.add(responses.POST, f"{NUCLEOGOV}/api/{acao}/listar", status=500, body="erro")
    _duble(monkeypatch, megasoft_embutida, "folha")
    for _ in range(2):
        Portal(NUCLEOGOV, pausa=0, sufixos={"servidores": "mg"}).folha(2025, 6, maximo=5)
    assert len(responses.calls) == 4  # sondou de novo na segunda consulta
