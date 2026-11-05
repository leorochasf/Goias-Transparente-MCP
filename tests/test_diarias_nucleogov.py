"""Diárias dos portais NucleoGov (`diarias_cnt` em Posse, `diarias_frl` em Senador Canedo), no ponto `Portal` e pelo
cliente MCP. Offline: o portal é simulado com `responses`. Os registros imitam os campos medidos ao vivo em 04/11/2026
(desenho dos módulos extras, seção D da descoberta); os nomes são inventados.
"""
import json
import urllib.parse

import anyio
import pytest
import responses
from mcp import Client

from transparencia_municipal import Portal, catalogo, servidor_mcp
from transparencia_municipal.cliente import ErroPortal

URL = "https://acessoainformacao.exemplo.go.gov.br"

#: Posse (`diarias_cnt`): `valor` e `quantidade` inteiros, datas dd/mm/aaaa, `orgao_nome`, `destino` livre e `cidade`
POSSE = {"id": 1, "id_empenho": 19561, "id_orgao": 3, "orgao_nome": "PODER EXECUTIVO", "favorecido": "PESSOA UM",
         "cargo": "MOTORISTA", "destino": "HOSPITAL ESTADUAL", "cidade": "GOIÂNIA", "valor": 1100, "quantidade": 2,
         "data_inicio": "14/01/2025", "data_fim": "15/01/2025", "descricao": "Levar paciente ao hospital"}
#: Senador Canedo (`diarias_frl`): valor, quantidade, cargo e chegada vazios; destino " - "
CANEDO = {"id": 7, "orgao": "FMS - FUNDO MUNICIPAL DE SAUDE", "orgao_id": "9", "favorecido": "PESSOA DOIS",
          "data_saida": "13/01/2025", "data_chegada": None, "data_empenho": "2025-01-13", "destino": " - ",
          "quantidade": None, "valor": None, "descricao": "Curso de capacitação em Brasília", "descricao_produto": None,
          "anobase": "2025", "cargo": None}


@pytest.fixture(autouse=True)
def sem_catalogo(monkeypatch):
    monkeypatch.setattr(catalogo, "carregar", lambda: [])


def _api(acao, *paginas, total=None):
    """Simula `acao` página a página; guarda o corpo (os filtros) de cada chamada."""
    pedidos, fila = [], list(paginas)

    def callback(requisicao):
        corpo = json.loads(urllib.parse.parse_qs(requisicao.body.decode())["params"][0])
        ident, filtros = next(iter(corpo.items()))
        pedidos.append(filtros)
        dados = fila.pop(0) if fila else []
        n = total if total is not None else sum(len(p) for p in paginas)
        return 200, {}, json.dumps({ident: {"dados": dados, "total": n}})
    responses.add_callback(responses.POST, f"{URL}/api/{acao}", callback=callback, content_type="application/json")
    return pedidos


def _posse(**mudar):
    return {**POSSE, **mudar}


def _canedo(**mudar):
    return {**CANEDO, **mudar}


@responses.activate
def test_campos_de_posse_viram_os_nomes_comuns_e_o_periodo_vai_no_filtro():
    pedidos = _api("diarias_cnt/listar", [_posse(), _posse(id=2, id_orgao=5, orgao_nome="FUNDO", cargo="")])
    r = Portal(URL, pausa=0, sufixos={"diarias": "cnt"}).diarias("2025-01-01", "31/03/2025")
    assert pedidos[0]["datamin"] == "2025-01-01" and pedidos[0]["datamax"] == "2025-03-31"
    assert "txtbusca" not in pedidos[0] and "orgao" not in pedidos[0]
    assert r["total"] == 2
    assert r["registros"][0] == {
        "favorecido": "PESSOA UM", "matricula": None, "cargo": "MOTORISTA", "orgao": "PODER EXECUTIVO",
        "destino": "HOSPITAL ESTADUAL (GOIÂNIA)", "motivo": "Levar paciente ao hospital", "data_saida": "14/01/2025",
        "data_chegada": "15/01/2025", "quantidade": "2", "valor": "1.100,00", "valor_unitario": None,
        "empenho": None, "fonte": "NucleoGov"}
    assert r["registros"][1]["cargo"] is None  # texto vazio é ausente, não ""


@responses.activate
def test_destino_igual_a_cidade_nao_se_repete():
    _api("diarias_cnt/listar", [_posse(destino="GOIANIA.", cidade="GOIÂNIA"), _posse(id=2, destino="", cidade="ANÁPOLIS")])
    r = Portal(URL, pausa=0, sufixos={"diarias": "cnt"}).diarias("2025-01-01", "2025-03-31")
    assert [x["destino"] for x in r["registros"]] == ["GOIANIA.", "ANÁPOLIS"]  # a cidade, sem acento, já está no destino


@responses.activate
def test_campos_de_senador_canedo_e_o_valor_vazio_vem_como_none_com_ressalva():
    _api("diarias_frl/listar", [_canedo(), _canedo(id=8, orgao="PREFEITURA MUNICIPAL", orgao_id="3",
                                                   data_saida="2025-03-28")])
    r = Portal(URL, pausa=0, sufixos={"diarias": "frl"}).diarias("2025-01-01", "2025-03-31")
    x = r["registros"][0]
    assert x["valor"] is None and x["quantidade"] is None and x["cargo"] is None
    assert x["destino"] is None and x["data_chegada"] is None  # " - " é o destino vazio do portal
    assert x["orgao"] == "FMS - FUNDO MUNICIPAL DE SAUDE" and x["motivo"] == "Curso de capacitação em Brasília"
    assert x["data_saida"] == "13/01/2025" and x["fonte"] == "NucleoGov"
    assert r["registros"][1]["data_saida"] == "28/03/2025"  # aaaa-mm-dd vira dd/mm/aaaa
    ressalvas = " ".join(r["ressalvas"])
    assert "não publicou o valor" in ressalvas and "não é zero" in ressalvas
    assert "órgão principal" not in ressalvas  # vieram dois órgãos


@responses.activate
def test_parte_das_diarias_sem_valor_e_dita_com_a_contagem():
    _api("diarias_cnt/listar", [_posse(), _posse(id=2, valor=None), _posse(id=3, valor="")])
    r = Portal(URL, pausa=0, sufixos={"diarias": "cnt"}).diarias("2025-01-01", "2025-03-31")
    assert [x["valor"] for x in r["registros"]] == ["1.100,00", None, None]
    assert any("2 de 3 diárias vieram sem valor" in s for s in r["ressalvas"])


@responses.activate
def test_diaria_com_saida_fora_do_periodo_e_erro_e_nao_mistura():
    _api("diarias_cnt/listar", [_posse(), _posse(id=2, data_inicio="02/04/2025")])
    with pytest.raises(ErroPortal, match="fora do período"):
        Portal(URL, pausa=0, sufixos={"diarias": "cnt"}).diarias("2025-01-01", "2025-03-31")


@responses.activate
def test_todas_de_um_orgao_so_trazem_a_ressalva_do_orgao_principal():
    _api("diarias_cnt/listar", [_posse(), _posse(id=2)])
    r = Portal(URL, pausa=0, sufixos={"diarias": "cnt"}).diarias("2025-01-01", "2025-03-31")
    ressalva = next(s for s in r["ressalvas"] if "órgão principal" in s)
    assert "PODER EXECUTIVO" in ressalva and "Câmara" in ressalva


@responses.activate
def test_nenhuma_diaria_tambem_traz_a_ressalva_do_orgao_principal():
    _api("diarias_cnt/listar", [], total=0)
    r = Portal(URL, pausa=0, sufixos={"diarias": "cnt"}).diarias("2025-01-01", "2025-03-31")
    assert r["total"] == 0 and r["registros"] == []
    assert any("órgão principal" in s for s in r["ressalvas"])


@responses.activate
def test_busca_e_feita_no_encaixe_sem_acento_sobre_o_periodo_inteiro():
    pagina1 = [_posse(id=i, cidade="BRASÍLIA", destino="BRASILIA") for i in range(100)]
    pagina2 = [_posse(id=100, cidade="GOIÂNIA", destino="GOIANIA", cargo="Motorista"),
               _posse(id=101, cidade="ANÁPOLIS", destino="ANAPOLIS", descricao="Reunião em goiânia"),
               _posse(id=102, cidade="ANÁPOLIS", destino="ANAPOLIS")]
    pedidos = _api("diarias_cnt/listar", pagina1, pagina2)
    r = Portal(URL, pausa=0, sufixos={"diarias": "cnt"}).diarias("2025-01-01", "2025-03-31", "Goiania", maximo=1)
    assert all("txtbusca" not in p for p in pedidos)  # medido: o `txtbusca` das diárias responde zero
    assert len(pedidos) == 2  # o período inteiro, não só o `maximo`
    assert r["total"] == 2 and len(r["registros"]) == 1
    assert r["registros"][0]["destino"] == "GOIANIA"


@responses.activate
def test_busca_com_leitura_incompleta_e_erro():
    _api("diarias_cnt/listar", [_posse(id=i) for i in range(100)], [], total=250)
    with pytest.raises(ErroPortal, match="incompleta"):
        Portal(URL, pausa=0, sufixos={"diarias": "cnt"}).diarias("2025-01-01", "2025-03-31", "goiania")


@responses.activate
def test_sem_busca_le_so_ate_o_maximo():
    pedidos = _api("diarias_cnt/listar", [_posse(id=i) for i in range(100)], total=500)
    r = Portal(URL, pausa=0, sufixos={"diarias": "cnt"}).diarias("2025-01-01", "2025-03-31", maximo=10)
    assert len(pedidos) == 1 and r["total"] == 500 and len(r["registros"]) == 10


@pytest.mark.descobre_sufixos
@responses.activate
def test_sufixo_desconhecido_tenta_frl_e_depois_cnt():
    responses.add(responses.GET, f"{URL}/", body='<div class="nucleogov"></div>')  # a página não anuncia as diárias
    _api("diarias_frl/listar", [], total=0)
    _api("diarias_cnt/listar", [_posse()])
    portal = Portal(URL, pausa=0)
    r = portal.diarias("2025-01-01", "2025-03-31")
    assert r["total"] == 1 and portal.sufixos["diarias"] == "cnt"


@responses.activate
def test_erro_do_portal_nao_vira_zero():
    responses.add(responses.POST, f"{URL}/api/diarias_cnt/listar", status=500, body="falhou")
    with pytest.raises(ErroPortal, match="HTTP 500"):
        Portal(URL, pausa=0, sufixos={"diarias": "cnt"}).diarias("2025-01-01", "2025-03-31")


# ── de ponta a ponta, pelo cliente MCP no mesmo processo ─────────────────────────────────────────────────────────

def _chamar(ferramenta, **argumentos):
    async def rodar():
        async with Client(servidor_mcp.mcp) as cliente:
            r = await cliente.call_tool(ferramenta, argumentos)
            return json.loads(r.content[0].text)
    return anyio.run(rodar)


@responses.activate
def test_mcp_consultar_diarias_num_portal_nucleogov():
    _api("diarias_frl/listar", [_canedo(), _canedo(id=8, orgao="PREFEITURA MUNICIPAL", orgao_id="3")])
    r = _chamar("consultar_diarias", de="2025-01-01", ate="2025-03-31", portal=URL, maximo=10)
    assert "erro" not in r, r
    assert r["total"] == 2 and {x["fonte"] for x in r["registros"]} == {"NucleoGov"}
    assert r["registros"][0]["valor"] is None
    assert any("não publicou o valor" in s for s in r["ressalvas"])
    assert "aviso_orgaos" in r and "aviso_diarias" in r and "aviso" in r
    assert "aviso_leitura" not in r
