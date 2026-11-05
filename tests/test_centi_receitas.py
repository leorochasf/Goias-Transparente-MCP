"""Receitas pela contabilidade Centi (menu `cntreceitas`). Offline: página inicial, API NucleoGov e Centi simuladas.

Exemplos montados à mão no formato medido em Posse (04/11/2026):
- órgãos em `sgcenti/listarOrgaos`, no envelope `multi_request`, como lista crua `[{id, valor, principal}]`;
- receitas em `POST /api/centi` (formulário simples) com `acao=receitas`, `ano`, `mes` ("09") e `orgao` (obrigatório);
  resposta `{dados, ano, mes, ..., error}`, cada linha com `TotalRegistros`, `Ano`, `mes` por extenso ("Setembro"),
  `Orgao` (o nome do órgão filtrado) e `TipoConta` (1 analítica, 2 sintética, 0 sem marca); valores em texto.
"""
import json
import urllib.parse

import anyio
import pytest
import responses
from mcp import Client

from transparencia_municipal import Portal, servidor_mcp
from transparencia_municipal.cliente import ErroPortal, PortalBloqueou

pytestmark = pytest.mark.descobre_sufixos
PORTAL = "https://acessoainformacao.exemplo.go.gov.br"
CENTI = f"{PORTAL}/api/centi"
ORGAOS = f"{PORTAL}/api/sgcenti/listarOrgaos"
#: como Posse lista: o principal primeiro, ids em texto
LISTA_ORGAOS = [{"id": "3", "valor": "Poder Executivo", "principal": "1"},
                {"id": "6", "valor": "FUNDO MUNICIPAL DE SAÚDE", "principal": "0"}]


def _linha(codigo, tipo, mes_valor, acumulado, **campos):
    return {"$type": "ServerAppWCF.Service.Portal.Controllers.ReceitaItem, Wcf", "CodigoElemento": codigo,
            "DescricaoElemento": f"RECEITA {codigo}", "CodigoFonte": "", "Fonte": "", "Destinacao": "",
            "ValorOrcado": "1.000,00", "ValoReceitaAcumuladoMes": mes_valor, "ValoReceitaAcumulado": acumulado,
            "PrevisaoAtualizada": "1.100,00", "DiferencaPositiva": "0,00", "DiferencaNegativa": "0,00", "Id": 1,
            "Ano": 2025, "Orgao": "PODER EXECUTIVO", "TipoConta": tipo, "Especificacao": "", "mes": "Setembro",
            **campos}


def _executivo():
    """Raízes 1 (correntes) e 91 (dedução), sintéticas, e as analíticas que fecham com elas no mês e no acumulado."""
    return [_linha("1.0.0.0.00.0.0", 2, "1.500,00", "9.000,00"),
            _linha("1.1.1.2.50.0.1", 1, "1.000,00", "6.000,00", CodigoFonte="100", Fonte="Recursos Ordinários"),
            _linha("1.7.1.1.51.0.1", 1, "500,00", "3.000,00"),
            _linha("91.0.0.0.00.0.0", 2, "-100,00", "-600,00"),
            _linha("91.1.1.2.50.0.1", 1, "-100,00", "-600,00")]


def _saude():
    return [_linha("1.0.0.0.00.0.0", 2, "300,00", "900,00", Orgao="FUNDO MUNICIPAL DE SAÚDE / FMS"),
            _linha("1.3.2.1.00.0.1", 1, "300,00", "900,00", Orgao="FUNDO MUNICIPAL DE SAÚDE / FMS")]


def _resposta(linhas, *, total=None, ano="2025", mes="09", error=None):
    return {"dados": [{**x, "TotalRegistros": len(linhas) if total is None else total} for x in linhas],
            "ano": ano, "mes": mes, "lista_categoria_economica": [], "lista_origem": [], "lista_especie": [],
            "lista_desdobramento": [], "lista_tipo": [], "error": error}


def _centi(por_orgao, orgaos=LISTA_ORGAOS):
    """Página com `cntreceitas`, API NucleoGov sem receitas, órgãos e Centi. `por_orgao`: id → resposta, ou lista
    de respostas dadas em ordem (a última se repete)."""
    responses.add(responses.GET, f"{PORTAL}/", body='<div class="nucleogov"><a href="x/cntreceitas">R</a></div>')

    def vazio(requisicao):
        ident = next(iter(json.loads(urllib.parse.parse_qs(requisicao.body.decode())["params"][0])))
        return 200, {}, json.dumps({ident: {"dados": [], "total": 0}})
    for acao in ("receitas_frl", "receitas_cnt"):
        responses.add_callback(responses.POST, f"{PORTAL}/api/{acao}/listar", callback=vazio,
                               content_type="application/json")

    def lista_orgaos(requisicao):
        ident = next(iter(json.loads(_formulario(requisicao.body)["params"])))
        return 200, {}, json.dumps({ident: orgaos})
    responses.add_callback(responses.POST, ORGAOS, callback=lista_orgaos, content_type="application/json")

    fila = {k: list(v) if isinstance(v, list) else [v] for k, v in por_orgao.items()}

    def receitas(requisicao):
        orgao = _formulario(requisicao.body)["orgao"]
        respostas = fila[orgao]
        resposta = respostas.pop(0) if len(respostas) > 1 else respostas[0]
        if isinstance(resposta, tuple):
            return resposta
        return 200, {}, resposta if isinstance(resposta, str) else json.dumps(resposta)
    responses.add_callback(responses.POST, CENTI, callback=receitas, content_type="text/json; charset=utf-8")


def _formulario(corpo):
    return dict(urllib.parse.parse_qsl(corpo if isinstance(corpo, str) else corpo.decode(), keep_blank_values=True))


def _enviados():
    return [_formulario(c.request.body) for c in responses.calls if c.request.url == CENTI]


def _ler(maximo=200):
    return Portal(PORTAL, pausa=0).receitas(2025, 9, maximo=maximo)


@responses.activate
def test_le_cada_orgao_em_separado_e_junta_no_formato_do_projeto():
    _centi({"3": _resposta(_executivo()), "6": _resposta(_saude())})
    r = _ler()
    assert [(x["acao"], x["ano"], x["mes"], x["orgao"]) for x in _enviados()] == [
        ("receitas", "2025", "09", "3"), ("receitas", "2025", "09", "6")]
    assert r["total"] == 7 and len(r["registros"]) == 7
    assert [x["orgao"] for x in r["registros"]] == ["PODER EXECUTIVO"] * 5 + ["FUNDO MUNICIPAL DE SAÚDE / FMS"] * 2
    assert r["registros"][1] == {
        "orgao": "PODER EXECUTIVO", "codigo": "1.1.1.2.50.0.1", "receita": "RECEITA 1.1.1.2.50.0.1",
        "fonte_recurso": "100 - Recursos Ordinários", "valor_orcado": "1.000,00",
        "valor_previsto_atualizado": "1.100,00", "valor_arrecadado_mes": "1.000,00",
        "valor_arrecadado_ate_mes": "6.000,00", "ano": 2025, "mes": 9, "analitica": True, "fonte": "Centi"}
    assert r["registros"][3]["valor_arrecadado_mes"] == "-100,00"  # dedução: negativa, como vem
    assert any("2 órgãos" in x and "um órgão por vez" in x for x in r["ressalvas"])


@responses.activate
def test_sinteticas_vem_marcadas_e_a_soma_por_orgao_e_so_das_analiticas():
    _centi({"3": _resposta(_executivo() + [_linha("1.7.2.9.53.0.0", 0, "0,00", "50,00")]),
            "6": _resposta(_saude())})
    r = _ler()
    marcas = {x["codigo"]: x["analitica"] for x in r["registros"] if x["orgao"] == "PODER EXECUTIVO"}
    assert marcas == {"1.0.0.0.00.0.0": False, "1.1.1.2.50.0.1": True, "1.7.1.1.51.0.1": True,
                      "91.0.0.0.00.0.0": False, "91.1.1.2.50.0.1": True, "1.7.2.9.53.0.0": None}
    assert r["somas_por_orgao"] == [
        {"orgao": "PODER EXECUTIVO", "linhas": 6, "linhas_analiticas": 3,
         "valor_arrecadado_mes": "1.400,00", "valor_arrecadado_ate_mes": "8.400,00"},
        {"orgao": "FUNDO MUNICIPAL DE SAÚDE / FMS", "linhas": 2, "linhas_analiticas": 1,
         "valor_arrecadado_mes": "300,00", "valor_arrecadado_ate_mes": "900,00"}]
    texto = " ".join(r["ressalvas"])
    assert "analitica" in texto and "em dobro" in texto and "somas_por_orgao" in texto
    assert "1 linha" in texto and "sem dizer" in texto  # TipoConta 0: nem analítica nem sintética
    assert "difere" not in texto  # no mês e no acumulado, as analíticas fecham com as raízes


@responses.activate
def test_analiticas_que_nao_fecham_com_as_raizes_viram_ressalva_com_a_diferenca():
    """Posse, 09/2025, Poder Executivo: o mês fecha ao centavo; o acumulado passa das raízes em R$ 334.029,19."""
    linhas = _executivo()
    linhas[1] = {**linhas[1], "ValoReceitaAcumulado": "6.334,19"}
    _centi({"3": _resposta(linhas), "6": _resposta(_saude())})
    ressalvas = _ler()["ressalvas"]
    acumulado = [x for x in ressalvas if "acumulado" in x and "difere" in x]
    assert len(acumulado) == 1 and "PODER EXECUTIVO" in acumulado[0] and "334,19" in acumulado[0]
    assert not [x for x in ressalvas if "no mês" in x and "difere" in x]


@responses.activate
def test_maximo_corta_os_registros_mas_as_somas_e_o_total_sao_do_mes_inteiro():
    _centi({"3": _resposta(_executivo()), "6": _resposta(_saude())})
    r = _ler(maximo=2)
    assert r["total"] == 7 and len(r["registros"]) == 2
    assert [s["valor_arrecadado_mes"] for s in r["somas_por_orgao"]] == ["1.400,00", "300,00"]


@pytest.mark.parametrize("campo, valor", [("mes", "Agosto"), ("Ano", 2024)])
@responses.activate
def test_linha_de_outro_mes_ou_ano_e_erro_e_nao_soma_calada(campo, valor):
    linhas = _executivo()
    linhas[2] = {**linhas[2], campo: valor}
    _centi({"3": _resposta(linhas), "6": _resposta(_saude())})
    with pytest.raises(ErroPortal, match="fora de 09/2025"):
        _ler()


@responses.activate
def test_orgao_que_a_centi_ignora_e_erro():
    """Se o filtro do órgão deixasse de valer, cada órgão traria as mesmas linhas, e juntar contaria em dobro."""
    _centi({"3": _resposta(_executivo()), "6": _resposta(_executivo())})
    with pytest.raises(ErroPortal, match="órgão"):
        _ler()


@responses.activate
def test_resposta_com_mais_de_um_orgao_e_erro():
    linhas = _executivo()
    linhas[0] = {**linhas[0], "Orgao": "OUTRO"}
    _centi({"3": _resposta(linhas), "6": _resposta(_saude())})
    with pytest.raises(ErroPortal, match="órgão"):
        _ler()


@responses.activate
def test_orgao_vazio_e_repetido_e_dito_na_ressalva():
    """Posse, 09/2025: o Fundo de Cultura veio vazio e, minutos depois, com 16 linhas. Vazio que se repete vale
    zero, e é dito, com o conselho de repetir."""
    _centi({"3": _resposta(_executivo()), "6": _resposta([], error="null")})
    r = _ler()
    assert r["total"] == 5
    assert [x["orgao"] for x in _enviados()] == ["3", "6", "6", "6"]
    assert any("FUNDO MUNICIPAL DE SAÚDE" in x and "sem receitas" in x and "repita" in x for x in r["ressalvas"])
    assert r["somas_por_orgao"][-1]["linhas"] == 0


@responses.activate
def test_orgao_vazio_que_responde_na_repeticao_entra():
    _centi({"3": _resposta(_executivo()), "6": [_resposta([]), _resposta(_saude())]})
    r = _ler()
    assert r["total"] == 7 and not any("sem receitas" in x for x in r["ressalvas"])


@responses.activate
def test_orgao_que_entrega_menos_linhas_que_declara_marca_a_leitura_incompleta():
    _centi({"3": _resposta(_executivo(), total=9), "6": _resposta(_saude())})
    r = _ler()
    assert r["total"] == 11 and len(r["registros"]) == 7
    assert "PODER EXECUTIVO" in r["incompleta"] and "5 de 9" in r["incompleta"]


@pytest.mark.parametrize("resposta, erro", [
    (_resposta([], error="Campo(s) obrigatório(s) não informado(s): Orgao (long)"), "recusou"),
    ("Ação não encontrada", "inesperada"),
    ({"dados": "x", "error": None}, "inesperada"),
    ({"dados": [_linha("1.0", 1, "1,00", "1,00", TotalRegistros=None)], "error": None}, "TotalRegistros"),
    ((500, {}, "falhou"), "HTTP 500"),
])
@responses.activate
def test_resposta_estranha_da_centi_e_erro_do_portal(resposta, erro):
    _centi({"3": resposta, "6": _resposta(_saude())})
    with pytest.raises(ErroPortal, match=erro):
        _ler()


@responses.activate
def test_403_na_centi_e_bloqueio():
    _centi({"3": (403, {}, "proibido"), "6": _resposta(_saude())})
    with pytest.raises(PortalBloqueou):
        _ler()


@pytest.mark.parametrize("orgaos", [[], {"erro": "x"}, [{"valor": "SEM ID"}]])
@responses.activate
def test_lista_de_orgaos_estranha_e_erro(orgaos):
    _centi({}, orgaos=orgaos)
    with pytest.raises(ErroPortal, match="órgãos"):
        _ler()


@responses.activate
def test_assistente_consulta_receitas_num_portal_centi(monkeypatch):
    monkeypatch.setattr(servidor_mcp, "_portal", lambda url=None: Portal(url or PORTAL, pausa=0))
    _centi({"3": _resposta(_executivo()), "6": _resposta(_saude())})

    async def rodar():
        async with Client(servidor_mcp.mcp) as cliente:
            r = await cliente.call_tool("consultar_receitas", {"ano": 2025, "mes": 9, "portal": PORTAL})
            return json.loads(r.content[0].text)  # o que o assistente recebe
    r = anyio.run(rodar)
    assert "erro" not in r and r["total"] == 7 and "aviso_leitura" not in r
    assert {x["fonte"] for x in r["registros"]} == {"Centi"}
    assert [s["valor_arrecadado_mes"] for s in r["somas_por_orgao"]] == ["1.400,00", "300,00"]
    assert "aviso_orgaos" in r and any("analitica" in x for x in r["ressalvas"])
