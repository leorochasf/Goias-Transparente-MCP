"""Reconhecer a plataforma de um portal pelo endereço e pela página inicial. Offline."""
import pytest

from transparencia_municipal.plataformas import plataforma_pelo_endereco, reconhecer


@pytest.mark.parametrize("endereco, plataforma", [
    ("https://acessoainformacao.senadorcanedo.go.gov.br/", "nucleogov"),
    ("acessoainformacao.posse.go.leg.br", "nucleogov"),
    ("acessoainformacao.camaratrindade.go.gov.br", "nucleogov"),
    ("https://corumbaiba.megasofttransparencia.com.br", "megasoft"),
    ("https://www.novacrixas.go.gov.br", None),  # só a sondagem diz
    ("posse.go.gov.br", None),
])
def test_plataforma_pelo_endereco(endereco, plataforma):
    assert plataforma_pelo_endereco(endereco) == plataforma


def test_reconhece_nucleogov_e_o_sufixo_de_cada_modulo_da_pagina():
    html = ('<script src="https://cdn.nucleogov.com.br/x.js"></script>'
            '<a href="/servidores_cnt">Folha</a><a href="/contratos_cnt">Contratos</a>'
            '<a href="/despesas_frl">Despesas</a>')
    assert reconhecer(html, "novacrixas.go.gov.br") == {
        "plataforma": "nucleogov",
        "sufixos": {"servidores": "cnt", "contratos": "cnt", "despesas": "frl"},
    }


def test_reconhece_a_variante_megasoft_dentro_do_nucleogov():
    html = ('<div class="nucleogov"><a href="cidadao/transparencia/mgservidores">Rec. Humanos</a>'
            '<a href="cidadao/transparencia/mgdespesas">D</a><a href="/contratos_cnt">C</a></div>')
    assert reconhecer(html, "acessoainformacao.abadiadegoias.go.gov.br") == {
        "plataforma": "nucleogov-megasoft",
        "sufixos": {"servidores": "mg", "despesas": "mg", "contratos": "cnt"}}


def test_reconhece_megasoft_pelo_dominio_e_ortrel_pela_pagina():
    assert reconhecer("<div id=app></div>", "corumbaiba.megasofttransparencia.com.br")["plataforma"] == "megasoft"
    html = '<script type="module" src="/src/main.jsx"></script>'
    assert reconhecer(html, "transparencia.amaralina.go.leg.br")["plataforma"] == "ortrel"


def test_pagina_sem_marca_conhecida_fica_sem_plataforma():
    assert reconhecer("<html>Prefeitura</html>", "posse.go.gov.br") == {"plataforma": None, "sufixos": {}}


def test_menu_cntdespesas_e_modulo_da_centi_mas_servidores_cnt_e_nucleogov():
    html = ('<div class="nucleogov"><a href="cidadao/transparencia/servidores_cnt">F</a>'
            '<a href="cidadao/transparencia/cntdespesas">D</a><a href="cidadao/transparencia/cntreceitas">R</a></div>')
    assert reconhecer(html, "acessoainformacao.posse.go.gov.br")["sufixos"] == {
        "servidores": "cnt", "despesas": "centi", "receitas": "centi"}


def test_menus_dos_modulos_extras_contratos_mg_sgdiarias_e_diarias_com_sufixo():
    """Aruanã (contratos_mg, licitacoes_mg, sgdiarias) e Posse (diarias_cnt), medidos em 04/11/2026."""
    aruana = ('<div class="nucleogov"><a href="x/mgservidores">F</a><a href="x/contratos_mg">C</a>'
              '<a href="x/licitacoes_mg">L</a><a href="x/sgdiarias">D</a></div>')
    assert reconhecer(aruana, "acessoainformacao.aruana.go.gov.br")["sufixos"] == {
        "servidores": "mg", "contratos": "mg", "licitacoes": "mg", "diarias": "sg"}
    posse = '<div class="nucleogov"><a href="x/diarias_cnt">D</a></div>'
    assert reconhecer(posse, "acessoainformacao.posse.go.gov.br")["sufixos"] == {"diarias": "cnt"}
