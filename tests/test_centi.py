"""Despesas pela contabilidade Centi (menu `cntdespesas`). Offline: página inicial, API NucleoGov e Centi simuladas.

Exemplos montados à mão no formato medido em Posse (04/11/2026): `POST /api/centi` num formulário simples, resposta
em lista sem páginas, cada registro com `TotalRegistros`; valores em texto ("1.600,00"); `Data` em dd/mm/aaaa;
`CpfCnpjCredor` com CNPJ formatado ou CPF mascarado ("123.xxx.xxx-45").
"""
import json
import urllib.parse

import anyio
import pytest
import responses
from mcp import Client

from transparencia_municipal import Portal, servidor_mcp
from transparencia_municipal.cliente import ErroPortal

pytestmark = pytest.mark.descobre_sufixos
PORTAL = "https://acessoainformacao.exemplo.go.gov.br"
CENTI = f"{PORTAL}/api/centi"
CNPJ = "25.107.525/0001-51"


def _empenho(**campos):
    return {"$type": "ServerAppWCF.Service.Portal.Controllers.EmpenhoItem, Wcf", "Id": 188810, "Numero": "188810",
            "Sequencial": 0, "Data": "15/01/2025", "Fornecedor": "EMPRESA EXEMPLO LTDA", "CpfCnpjCredor": CNPJ,
            "ValorEmpenhado": "12.000,50", "ValorAnulacao": "2.000,00", "ValorLiquidado": "8.000,00",
            "SaldoPagar": "0,00", "ValorPago": "7.500,00", "Historico": "AQUISIÇÃO DE MATERIAL DE EXPEDIENTE",
            "OrgaoGestor": "PODER EXECUTIVO", "TotalRegistros": 1, **campos}


def _centi(*respostas):
    """A página inicial aponta a Centi, a API NucleoGov não serve despesas e a Centi responde, em ordem, `respostas`."""
    responses.add(responses.GET, f"{PORTAL}/", body='<div class="nucleogov"><a href="x/cntdespesas">D</a></div>')

    def vazio(requisicao):
        ident = next(iter(json.loads(urllib.parse.parse_qs(requisicao.body.decode())["params"][0])))
        return 200, {}, json.dumps({ident: {"dados": [], "total": 0}})
    for acao in ("despesas_frl", "despesas_cnt"):
        responses.add_callback(responses.POST, f"{PORTAL}/api/{acao}/listar", callback=vazio,
                               content_type="application/json")
    for resposta in respostas:
        responses.add(responses.POST, CENTI, body=resposta if isinstance(resposta, str) else json.dumps(resposta),
                      content_type="text/json; charset=utf-8")


def _lista(*registros):
    return [{**r, "TotalRegistros": len(registros)} for r in registros]


def _enviado():
    """O formulário mandado à Centi na última chamada."""
    corpo = [c for c in responses.calls if c.request.url == CENTI][-1].request.body
    return dict(urllib.parse.parse_qsl(corpo if isinstance(corpo, str) else corpo.decode(), keep_blank_values=True))


@responses.activate
def test_despesas_da_centi_vem_no_formato_do_projeto_com_a_fonte():
    _centi(_lista(_empenho()))
    r = Portal(PORTAL, pausa=0).despesas("2025-01-01", "2025-01-31")
    assert r == {"total": 1, "registros": [{
        "empenho": "188810", "data": "15/01/2025", "cpf_cnpj": CNPJ, "fornecedor": "EMPRESA EXEMPLO LTDA",
        "valor_empenhado": "10.000,50", "valor_liquidado": "8.000,00", "valor_pago": "7.500,00",
        "historico": "AQUISIÇÃO DE MATERIAL DE EXPEDIENTE", "fonte": "Centi"}]}
    enviado = _enviado()  # id_orgao 0 = todas as entidades (Câmara e fundos incluídos)
    assert {k: enviado[k] for k in ("acao", "id_orgao", "data_inicio", "data_fim")} == {
        "acao": "empenhos", "id_orgao": "0", "data_inicio": "01/01/2025", "data_fim": "31/01/2025"}


@responses.activate
def test_cnpj_e_filtrado_pelo_projeto_e_nao_vai_ao_filtro_da_centi():
    """Posse, 04/11/2026: com `cpf_cnpj` preenchido a Centi devolveu lista vazia para um CNPJ que tinha 10 empenhos."""
    _centi(_lista(_empenho(Numero="1"), _empenho(Numero="2", CpfCnpjCredor="06.134.339/0001-67"),
                  _empenho(Numero="3", CpfCnpjCredor="123.xxx.xxx-45"), _empenho(Numero="4", CpfCnpjCredor="")))
    r = Portal(PORTAL, pausa=0).despesas("2025-01-01", "2025-01-31", "25107525000151")
    assert r["total"] == 1 and [x["empenho"] for x in r["registros"]] == ["1"]
    assert _enviado()["cpf_cnpj"] == ""


@responses.activate
def test_total_declarado_diferente_do_trazido_volta_como_esta_para_a_leitura_se_declarar_incompleta():
    _centi([_empenho(Numero="1", TotalRegistros=3), _empenho(Numero="2", TotalRegistros=3)])
    r = Portal(PORTAL, pausa=0).despesas("2025-01-01", "2025-01-31")
    assert r["total"] == 3 and len(r["registros"]) == 2


@responses.activate
def test_cnpj_sobre_leitura_que_nao_fecha_e_erro_e_nao_contagem_parcial():
    _centi([_empenho(Numero="1", TotalRegistros=3), _empenho(Numero="2", TotalRegistros=3)])
    with pytest.raises(ErroPortal, match="2 de 3"):
        Portal(PORTAL, pausa=0).despesas("2025-01-01", "2025-01-31", CNPJ)


@responses.activate
def test_lista_vazia_e_repetida_antes_de_virar_zero():
    """Posse, 04/11/2026: uma janela de meio mês voltou `[]` em 0,4 s; repetida, trouxe os empenhos."""
    _centi([], _lista(_empenho()))
    assert Portal(PORTAL, pausa=0).despesas("2025-01-01", "2025-01-15")["total"] == 1


@responses.activate
def test_periodo_sem_empenhos_e_zero_depois_de_repetir():
    _centi([], [], [])
    assert Portal(PORTAL, pausa=0).despesas("2025-01-01", "2025-01-15") == {"total": 0, "registros": []}
    assert sum(1 for c in responses.calls if c.request.url == CENTI) == 3


@responses.activate
def test_empenho_fora_do_periodo_pedido_e_erro_e_nao_soma_calada():
    """Medido: a Centi respeita o período. Se deixar de respeitar, a resposta não pode passar por certa."""
    _centi(_lista(_empenho(), _empenho(Numero="2", Data="01/02/2025")))
    with pytest.raises(ErroPortal, match="fora do período"):
        Portal(PORTAL, pausa=0).despesas("2025-01-01", "2025-01-31")


@responses.activate
def test_busca_por_nome_e_filtrada_pelo_projeto_sem_caixa_nem_acento():
    _centi(_lista(_empenho(Numero="1", Fornecedor="CONSTRUTORA ÁGUA LIMPA LTDA"), _empenho(Numero="2")))
    r = Portal(PORTAL, pausa=0).despesas("2025-01-01", "2025-01-31", "agua limpa")
    assert r["total"] == 1 and [x["empenho"] for x in r["registros"]] == ["1"]


@responses.activate
def test_maximo_corta_os_registros_e_mantem_o_total():
    _centi(_lista(*(_empenho(Numero=str(i)) for i in range(5))))
    r = Portal(PORTAL, pausa=0).despesas("2025-01-01", "2025-01-31", maximo=2)
    assert r["total"] == 5 and [x["empenho"] for x in r["registros"]] == ["0", "1"]


@pytest.mark.parametrize("resposta", ["Ação não encontrada", {"erro": "x"},
                                      [_empenho(TotalRegistros=None)],
                                      [_empenho(TotalRegistros=2), _empenho(TotalRegistros=3)]])
@responses.activate
def test_resposta_estranha_da_centi_e_erro_do_portal(resposta):
    _centi(resposta)
    with pytest.raises(ErroPortal, match="Centi"):
        Portal(PORTAL, pausa=0).despesas("2025-01-01", "2025-01-31")


@responses.activate
def test_assistente_consulta_despesas_por_cnpj_num_portal_centi(monkeypatch):
    monkeypatch.setattr(servidor_mcp, "_portal", lambda url=None: Portal(url or PORTAL, pausa=0))
    _centi(_lista(_empenho(Numero="1"), _empenho(Numero="2", CpfCnpjCredor="06.134.339/0001-67")))

    async def rodar():
        async with Client(servidor_mcp.mcp) as cliente:
            r = await cliente.call_tool("consultar_despesas", {"de": "2025-01-01", "ate": "2025-01-31",
                                                               "busca": "25.107.525/0001-51", "portal": PORTAL})
            return json.loads(r.content[0].text)  # o que o assistente recebe
    r = anyio.run(rodar)
    assert "erro" not in r and r["total"] == 1
    assert [(x["empenho"], x["cpf_cnpj"], x["valor_empenhado"], x["fonte"]) for x in r["registros"]] == [
        ("1", CNPJ, "10.000,50", "Centi")]
