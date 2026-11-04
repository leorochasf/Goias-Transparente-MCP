"""Catálogo de portais: achar o portal pelo município e dizer a situação dele. Offline, com catálogo de exemplo."""
import json

import pytest
import responses

from transparencia_municipal import catalogo, servidor_mcp

EXEMPLO = [
    {"ibge": "5218003", "municipio": "Posse", "orgao": "prefeitura", "portal": "https://acessoainformacao.posse.go.gov.br",
     "plataforma": "nucleogov", "sufixos": {"servidores": "cnt"}, "outros_enderecos": ["posse.go.gov.br"],
     "conferencia": {"data": "2026-11-04", "referencia": "06/2025",
                     "filtros": {"folha_mes": "ok", "despesas_cnpj": "falhou"},
                     "detalhes": {"despesas_cnpj": "buscou X, vieram também Y"}}},
    {"ibge": "5218003", "municipio": "Posse", "orgao": "camara", "portal": "https://acessoainformacao.posse.go.leg.br",
     "plataforma": "nucleogov", "sufixos": {}, "outros_enderecos": [], "conferencia": None},
    {"ibge": "5202155", "municipio": "Aruanã", "orgao": "prefeitura", "portal": "https://acessoainformacao.aruana.go.gov.br",
     "plataforma": "nucleogov", "sufixos": {}, "outros_enderecos": [], "conferencia": None},
    {"ibge": "5206404", "municipio": "Corumbaíba", "orgao": "prefeitura",
     "portal": "https://corumbaiba.megasofttransparencia.com.br", "plataforma": "megasoft", "sufixos": {},
     "outros_enderecos": [], "conferencia": None},
    {"ibge": "5204409", "municipio": "Caldazinha", "orgao": "prefeitura",
     "portal": "https://acessoainformacao.caldazinha.go.gov.br", "plataforma": "nucleogov-megasoft",
     "sufixos": {"servidores": "mg", "despesas": "mg", "contratos": "cnt"},
     "outros_enderecos": [], "conferencia": None},
]


@pytest.fixture(autouse=True)
def catalogo_de_exemplo(monkeypatch):
    monkeypatch.setattr(catalogo, "carregar", lambda: EXEMPLO)


def test_encontra_pelo_municipio_sem_acento_e_filtra_o_orgao():
    assert [x["orgao"] for x in catalogo.encontrar("posse")] == ["prefeitura", "camara"]
    assert [x["portal"] for x in catalogo.encontrar("aruana", "prefeitura")] == ["https://acessoainformacao.aruana.go.gov.br"]
    assert catalogo.encontrar("Cidade Que Não Existe") == []


def test_acha_o_orgao_por_qualquer_endereco_dele():
    assert catalogo.por_portal("https://acessoainformacao.posse.go.gov.br/")["orgao"] == "prefeitura"
    assert catalogo.por_portal("posse.go.gov.br")["orgao"] == "prefeitura"
    assert catalogo.por_portal("https://outro.go.gov.br") is None


def test_situacao_diz_a_conferencia_e_o_que_falhou():
    assert "conferido em 2026-11-04" in catalogo.situacao(EXEMPLO[0])
    assert "despesas_cnpj" in catalogo.situacao(EXEMPLO[0])
    assert "não conferido" in catalogo.situacao(EXEMPLO[1])


def test_mcp_encontrar_portal():
    r = servidor_mcp.encontrar_portal("Posse", "camara")
    assert r["orgaos"][0]["portal"] == "https://acessoainformacao.posse.go.leg.br"
    assert "não conferido" in r["orgaos"][0]["situacao"]


def test_mcp_recusa_portal_de_outra_plataforma_sem_chamar_o_portal():
    r = servidor_mcp.consultar_despesas("2025-01-01", "2025-01-31", portal="https://corumbaiba.megasofttransparencia.com.br")
    assert "Megasoft" in r["erro"] and "Corumbaíba" in r["erro"]


@responses.activate
def test_mcp_recusa_os_modulos_da_megasoft_embutida_quando_a_api_nao_os_serve():
    caldazinha = "https://acessoainformacao.caldazinha.go.gov.br"
    for acao in ("servidores_frl", "servidores_cnt", "despesas_frl", "despesas_cnt"):
        responses.add(responses.POST, f"{caldazinha}/api/{acao}/listar", body="[]")  # sufixo sem dados
    assert "Megasoft" in servidor_mcp.consultar_folha(2025, 3, portal=caldazinha)["erro"]
    assert "Megasoft" in servidor_mcp.consultar_despesas("2025-01-01", "2025-01-31", portal=caldazinha)["erro"]


@responses.activate
def test_mcp_resposta_traz_a_situacao_do_portal_e_usa_os_sufixos_do_catalogo():
    def callback(requisicao):
        import urllib.parse
        ident = next(iter(json.loads(urllib.parse.parse_qs(requisicao.body.decode())["params"][0])))
        return 200, {}, json.dumps({ident: {"dados": [], "total": 0}})
    responses.add_callback(responses.POST, "https://acessoainformacao.posse.go.gov.br/api/servidores_cnt/listar",
                           callback=callback, content_type="application/json")
    r = servidor_mcp.consultar_folha(2025, 3, busca="FULANO", portal="https://acessoainformacao.posse.go.gov.br")
    assert "despesas_cnpj" in r["situacao_do_portal"]
    assert responses.calls[0].request.url.endswith("servidores_cnt/listar")
