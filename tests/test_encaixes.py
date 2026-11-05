"""Os encaixes dos módulos extras, decididos no ponto único do `Portal`. Offline; cada encaixe é trocado por um dublê.

Sistemas: Megasoft de domínio próprio (o endereço basta), Megasoft embutida (menus `mg*`, `*_mg` e `sgdiarias`), Centi
(menu `cnt*`), diárias do NucleoGov (`diarias_cnt`/`diarias_frl`) e Ortrel (página com `/src/main.jsx`, ou plataforma
`ortrel` no catálogo). Interface de cada encaixe: ticket 01 dos módulos extras, seção `## Comments`.

Os blocos `# ticket 0X` testam a resposta "ainda não disponível" de cada encaixe: o dono do ticket os apaga quando o
encaixe passar a funcionar. Ficam separados por testes permanentes, para dois tickets não colidirem no merge.
"""
import json
import urllib.parse
from datetime import date

import pytest
import responses

from transparencia_municipal import (Portal, catalogo, centi, diarias_nucleogov, megasoft_embutida, megasoft_propria,
                                     ortrel, servidor_mcp)
from transparencia_municipal.cliente import ModuloNaoSuportado

pytestmark = pytest.mark.descobre_sufixos
NUCLEOGOV = "https://acessoainformacao.exemplo.go.gov.br"
PROPRIA = "https://exemplo.megasofttransparencia.com.br"
ORTREL = "https://transparencia.exemplo.go.leg.br"
PAGINA_ORTREL = '<div id="root"></div><script type="module" src="/src/main.jsx"></script>'
#: página de um portal NucleoGov com os módulos da Megasoft embutida (Aruanã, 04/11/2026)
PAGINA_EMBUTIDA = ('<div class="nucleogov"><a href="x/mgreceitas">R</a><a href="x/contratos_mg">C</a>'
                   '<a href="x/licitacoes_mg">L</a><a href="x/sgdiarias">D</a></div>')


def _sem_dados(*acoes):
    """A API NucleoGov não serve estes módulos: total 0."""
    def callback(requisicao):
        ident = next(iter(json.loads(urllib.parse.parse_qs(requisicao.body.decode())["params"][0])))
        return 200, {}, json.dumps({ident: {"dados": [], "total": 0}})
    for acao in acoes:
        responses.add_callback(responses.POST, f"{NUCLEOGOV}/api/{acao}/listar", callback=callback,
                               content_type="application/json")


def _duble(monkeypatch, modulo, funcao):
    """Troca o encaixe por um dublê que guarda os argumentos e devolve um registro marcado."""
    chamadas = []

    def duble(portal, **argumentos):
        chamadas.append((portal.url, argumentos))
        return {"total": 1, "registros": [{"fonte": f"dublê {modulo.__name__}.{funcao}"}]}
    monkeypatch.setattr(modulo, funcao, duble)
    return chamadas


#: módulo → (chamada no Portal, argumentos que o encaixe recebe)
CHAMADAS = {
    "folha": (lambda p: p.folha(2025, 9, "FULANO"),
              {"ano": 2025, "mes": 9, "busca": "FULANO", "maximo": 200, "progresso": None}),
    "despesas": (lambda p: p.despesas("2025-01-01", "2025-01-31", "25107525000151"),
                 {"de": "01/01/2025", "ate": "31/01/2025", "cnpj": "25.107.525/0001-51", "busca": None,
                  "maximo": 200}),
    "receitas": (lambda p: p.receitas(2025, "09", maximo=50), {"ano": 2025, "mes": 9, "maximo": 50}),
    "contratos": (lambda p: p.contratos(2025, busca="OBRA"),
                  {"ano": 2025, "tipo": "contrato", "busca": "OBRA", "maximo": 200}),
    "licitacoes": (lambda p: p.licitacoes(dispensas=True, ano=2025),
                   {"busca": None, "dispensas": True, "ano": 2025, "maximo": 200}),
    "diarias": (lambda p: p.diarias("2025-01-01", "31/03/2025", "goiania", maximo=10),
                {"de": date(2025, 1, 1), "ate": date(2025, 3, 31), "busca": "goiania", "maximo": 10}),
    "legislacao": (lambda p: p.legislacao("lei", "cargo", ano=2024),
                   {"tipo": "LEI", "busca": "cargo", "ano": 2024, "maximo": 200}),
    "detalhe_servidor": (lambda p: p.detalhe_servidor(" 1234 ", 2025, 9), {"matricula": "1234", "ano": 2025, "mes": 9}),
}


@pytest.mark.parametrize("nome", ["receitas", "diarias", "contratos", "licitacoes", "detalhe_servidor"])
@responses.activate
def test_megasoft_propria_le_os_modulos_novos_pelo_encaixe_sem_chamar_a_rede(monkeypatch, nome):
    chamar, argumentos = CHAMADAS[nome]
    chamadas = _duble(monkeypatch, megasoft_propria, nome)
    r = chamar(Portal(PROPRIA, pausa=0))
    assert r["registros"][0]["fonte"] == f"dublê transparencia_municipal.megasoft_propria.{nome}"
    assert chamadas == [(PROPRIA, argumentos)]
    assert len(responses.calls) == 0


@pytest.mark.parametrize("nome, sem_dados", [
    ("receitas", ("receitas_frl", "receitas_cnt")),
    ("contratos", ("contratos_frl", "contratos_cnt")),
    ("licitacoes", ("licitacoes_frl", "licitacoes_cnt")),
    ("diarias", ()),  # `sgdiarias` é do próprio NucleoGov, sem sondagem da API
])
@responses.activate
def test_megasoft_embutida_le_os_modulos_novos_pelo_encaixe(monkeypatch, nome, sem_dados):
    responses.add(responses.GET, f"{NUCLEOGOV}/", body=PAGINA_EMBUTIDA)
    _sem_dados(*sem_dados)
    chamar, argumentos = CHAMADAS[nome]
    chamadas = _duble(monkeypatch, megasoft_embutida, nome)
    chamar(Portal(NUCLEOGOV, pausa=0))
    assert chamadas == [(NUCLEOGOV, argumentos)]


@responses.activate
def test_receitas_da_centi_vao_pelo_encaixe_da_centi(monkeypatch):
    responses.add(responses.GET, f"{NUCLEOGOV}/", body='<div class="nucleogov"><a href="x/cntreceitas">R</a></div>')
    _sem_dados("receitas_frl", "receitas_cnt")
    chamar, argumentos = CHAMADAS["receitas"]
    chamadas = _duble(monkeypatch, centi, "receitas")
    chamar(Portal(NUCLEOGOV, pausa=0))
    assert chamadas == [(NUCLEOGOV, argumentos)]


@pytest.mark.parametrize("pagina", ['<div class="nucleogov"><a href="x/diarias_cnt">D</a></div>',
                                    '<div class="nucleogov"></div>'])
@responses.activate
def test_diarias_do_nucleogov_vao_pelo_encaixe_proprio_com_o_sufixo_da_pagina(monkeypatch, pagina):
    responses.add(responses.GET, f"{NUCLEOGOV}/", body=pagina)
    chamar, argumentos = CHAMADAS["diarias"]
    chamadas = _duble(monkeypatch, diarias_nucleogov, "diarias")
    portal = Portal(NUCLEOGOV, pausa=0)
    chamar(portal)
    assert chamadas == [(NUCLEOGOV, argumentos)]
    assert portal.sufixos.get("diarias") == ("cnt" if "diarias_cnt" in pagina else None)
    assert len(responses.calls) == 1  # só a página inicial: a API é do encaixe


@pytest.mark.parametrize("nome", ["folha", "despesas", "contratos", "licitacoes", "diarias", "legislacao"])
@responses.activate
def test_portal_ortrel_e_reconhecido_pela_pagina_e_vai_pelo_encaixe_ortrel(monkeypatch, nome):
    responses.add(responses.GET, f"{ORTREL}/", body=PAGINA_ORTREL)
    chamar, argumentos = CHAMADAS[nome]
    chamadas = _duble(monkeypatch, ortrel, nome)
    chamar(Portal(ORTREL, pausa=0))
    assert chamadas == [(ORTREL, argumentos)]
    assert len(responses.calls) == 1  # só a página inicial


@responses.activate
def test_portal_ortrel_do_catalogo_nao_precisa_da_pagina(monkeypatch):
    chamadas = _duble(monkeypatch, ortrel, "folha")
    Portal(ORTREL, pausa=0, plataforma="ortrel").folha(2025, 9)
    assert len(chamadas) == 1 and len(responses.calls) == 0


@responses.activate
def test_mcp_nao_recusa_mais_o_ortrel_e_vai_pelo_encaixe_sem_chamar_a_rede(monkeypatch):
    camara = {"municipio": "Exemplo", "orgao": "camara", "portal": ORTREL, "plataforma": "ortrel", "sufixos": {},
              "outros_enderecos": ["exemplo.go.leg.br"], "conferencia": None}
    monkeypatch.setattr(catalogo, "carregar", lambda: [camara])
    chamadas = _duble(monkeypatch, ortrel, "despesas")
    r = servidor_mcp.consultar_despesas("2025-01-01", "2025-01-31", portal=ORTREL)
    assert "erro" not in r and len(chamadas) == 1
    assert len(responses.calls) == 0


@responses.activate
def test_modulo_ausente_dos_sufixos_do_catalogo_e_aprendido_na_pagina_uma_vez(monkeypatch):
    """O catálogo foi montado antes de `sgdiarias` e `contratos_mg` serem reconhecidos: a página completa."""
    responses.add(responses.GET, f"{NUCLEOGOV}/", body=PAGINA_EMBUTIDA)
    _sem_dados("contratos_frl", "contratos_cnt")
    diarias = _duble(monkeypatch, megasoft_embutida, "diarias")
    contratos = _duble(monkeypatch, megasoft_embutida, "contratos")
    for _ in range(2):
        Portal(NUCLEOGOV, pausa=0, sufixos={"servidores": "mg"}).diarias("2025-01-01", "2025-01-31")
        Portal(NUCLEOGOV, pausa=0, sufixos={"servidores": "mg"}).contratos(2025)
    assert len(diarias) == 2 and len(contratos) == 2
    assert sum(1 for c in responses.calls if c.request.method == "GET") == 1


@responses.activate
def test_detalhe_do_servidor_fora_da_megasoft_propria_e_recusado_sem_chamar_a_rede():
    with pytest.raises(ModuloNaoSuportado, match="Megasoft de domínio próprio"):
        Portal(NUCLEOGOV, pausa=0).detalhe_servidor("1234", 2025, 9)
    assert len(responses.calls) == 0


@responses.activate
def test_licitacoes_por_ano_na_api_nucleogov_sao_recusadas_porque_o_filtro_nao_foi_medido():
    """O portal ignora filtro desconhecido em silêncio (docs/portal-nucleogov.md): melhor recusar que mentir."""
    responses.add(responses.GET, f"{NUCLEOGOV}/", body='<div class="nucleogov"><a href="x/licitacoes_frl">L</a></div>')
    with pytest.raises(ValueError, match="ano"):
        Portal(NUCLEOGOV, pausa=0).licitacoes(ano=2025)
    assert all(c.request.method == "GET" for c in responses.calls)


@pytest.mark.parametrize("de, ate", [("2025-03-01", "2025-01-31"), ("ontem", "2025-01-31")])
def test_diarias_com_periodo_invertido_ou_ilegivel_sao_recusadas(de, ate):
    with pytest.raises(ValueError):
        Portal(PROPRIA, pausa=0).diarias(de, ate)


# ── ticket 02: Megasoft própria ainda não lê os módulos novos ───────────────────────────────────────────────────

@pytest.mark.parametrize("nome", ["receitas", "diarias", "contratos", "licitacoes", "detalhe_servidor"])
@responses.activate
def test_megasoft_propria_modulos_novos_ainda_nao_disponiveis(nome):  # ticket 02
    with pytest.raises(ModuloNaoSuportado, match="ainda não está disponível"):
        CHAMADAS[nome][0](Portal(PROPRIA, pausa=0))
    assert len(responses.calls) == 0


@responses.activate
def test_mcp_receitas_da_megasoft_propria_ainda_nao_disponiveis():  # ticket 02
    r = servidor_mcp.consultar_receitas(2025, 3, portal="https://corumbaiba.megasofttransparencia.com.br")
    assert "Megasoft" in r["erro"] and "corumbaiba" in r["erro"]
    assert len(responses.calls) == 0


# ── permanente: a legislação da Megasoft própria continua recusada ───────────────────────────────────────────────

@responses.activate
def test_legislacao_da_megasoft_propria_continua_recusada_sem_chamar_a_rede():
    with pytest.raises(ModuloNaoSuportado, match="Megasoft"):
        Portal(PROPRIA, pausa=0).legislacao("DECRETO")
    assert len(responses.calls) == 0


# ── ticket 03: Megasoft embutida ainda não lê os módulos novos ──────────────────────────────────────────────────

@pytest.mark.parametrize("nome, sem_dados", [
    ("receitas", ("receitas_frl", "receitas_cnt")),
    ("contratos", ("contratos_frl", "contratos_cnt")),
    ("licitacoes", ("licitacoes_frl", "licitacoes_cnt")),
    ("diarias", ()),
])
@responses.activate
def test_megasoft_embutida_modulos_novos_ainda_nao_disponiveis(nome, sem_dados):  # ticket 03
    responses.add(responses.GET, f"{NUCLEOGOV}/", body=PAGINA_EMBUTIDA)
    _sem_dados(*sem_dados)
    with pytest.raises(ModuloNaoSuportado, match="ainda não está disponível"):
        CHAMADAS[nome][0](Portal(NUCLEOGOV, pausa=0))


@responses.activate
def test_mcp_receitas_da_megasoft_embutida_ainda_nao_disponiveis(monkeypatch):  # ticket 03
    prefeitura = {"municipio": "Exemplo", "orgao": "prefeitura", "portal": NUCLEOGOV, "plataforma": "nucleogov-megasoft",
                  "sufixos": {"receitas": "mg"}, "outros_enderecos": [], "conferencia": None}
    monkeypatch.setattr(catalogo, "carregar", lambda: [prefeitura])
    for acao in ("receitas_frl", "receitas_cnt"):
        responses.add(responses.POST, f"{NUCLEOGOV}/api/{acao}/listar", body="[]")  # sufixo sem dados
    assert "Megasoft" in servidor_mcp.consultar_receitas(2025, 3, portal=NUCLEOGOV)["erro"]


# ── permanente: o Ortrel não tem receitas medidas ───────────────────────────────────────────────────────────────

@responses.activate
def test_receitas_do_ortrel_sao_recusadas():
    with pytest.raises(ModuloNaoSuportado, match="Ortrel"):
        Portal(ORTREL, pausa=0, plataforma="ortrel").receitas(2025, 9)
    assert len(responses.calls) == 0


# ── ticket 04: receitas da Centi ainda não disponíveis ───────────────────────────────────────────────────────────

@responses.activate
def test_receitas_da_centi_ainda_nao_disponiveis():  # ticket 04
    responses.add(responses.GET, f"{NUCLEOGOV}/", body='<div class="nucleogov"><a href="x/cntreceitas">R</a></div>')
    _sem_dados("receitas_frl", "receitas_cnt")
    with pytest.raises(ModuloNaoSuportado, match="Centi"):
        Portal(NUCLEOGOV, pausa=0).receitas(2025, 3)


# ── permanente: o detalhe do servidor não existe num portal NucleoGov com a Centi ───────────────────────────────

@responses.activate
def test_detalhe_do_servidor_num_portal_com_a_centi_e_recusado():
    responses.add(responses.GET, f"{NUCLEOGOV}/",
                  body='<div class="nucleogov"><a href="x/cntdespesas">D</a></div>')
    with pytest.raises(ModuloNaoSuportado):
        Portal(NUCLEOGOV, pausa=0).detalhe_servidor("1", 2025, 1)


# ── ticket 05: diárias do NucleoGov ainda não disponíveis ────────────────────────────────────────────────────────

@responses.activate
def test_diarias_do_nucleogov_ainda_nao_disponiveis():  # ticket 05
    responses.add(responses.GET, f"{NUCLEOGOV}/", body='<div class="nucleogov"><a href="x/diarias_cnt">D</a></div>')
    with pytest.raises(ModuloNaoSuportado, match="ainda não está disponível"):
        Portal(NUCLEOGOV, pausa=0).diarias("2025-01-01", "2025-03-31")


# ── permanente: o detalhe do servidor no Ortrel é recusado (decreto e data vêm na folha) ─────────────────────────

@responses.activate
def test_detalhe_do_servidor_no_ortrel_e_recusado():
    with pytest.raises(ModuloNaoSuportado, match="Ortrel"):
        Portal(ORTREL, pausa=0, plataforma="ortrel").detalhe_servidor("1", 2025, 9)
