"""Ferramentas do TCM-GO no MCP, por um cliente MCP no mesmo processo. Offline."""
import json

import anyio
import pytest
from mcp import Client

from transparencia_municipal import esiproc, servidor_mcp, tcm, tcmjuris
from transparencia_municipal.tcm import ClienteTCM


@pytest.fixture(autouse=True)
def sem_pausa(monkeypatch):
    monkeypatch.setattr(servidor_mcp, "_tcm", lambda: ClienteTCM(pausa=0))


def _chamar(ferramenta, **argumentos):
    async def rodar():
        async with Client(servidor_mcp.mcp) as cliente:
            r = await cliente.call_tool(ferramenta, argumentos)
            return json.loads(r.content[0].text)
    return anyio.run(rodar)


def test_as_tres_ferramentas_existem_com_os_parametros_da_spec():
    async def esquemas():
        async with Client(servidor_mcp.mcp) as cliente:
            return {t.name: t.input_schema for t in (await cliente.list_tools()).tools}
    e = anyio.run(esquemas)
    assert set(e["processos_tcm"]["properties"]) == {"municipio", "tipo", "ano", "finalizado", "relator", "numero",
                                                     "maximo"}
    assert set(e["acordaos_tcm"]["properties"]) == {"municipio", "texto", "assunto", "ano", "relator", "maximo"}
    assert set(e["ler_acordao_tcm"]["properties"]) == {"id"}
    assert e["ler_acordao_tcm"]["required"] == ["id"]


def test_processos_de_ponta_a_ponta_pelo_esiproc_simulado_com_os_avisos_fixos():  # ticket 02
    import responses  # local: as linhas de import do arquivo não são deste ticket
    fonte = {"numero": "00000131.2023.001.4.14838.0223", "municipio": "NOVA CRIXÁS", "codigo_ibge": "14838",
             "tipo_protocolo": "Contas de Gestão", "ano_competencia": 2023, "finalizado": "SIM",
             "decisoes": [], "envolvidos": [{"nome": "FULANO FICTÍCIO", "tipo_envolvimento": "Gestor",
                                             "tipo_pessoa": "FÍSICA"}]}
    with responses.RequestsMock() as simulado:
        simulado.post(f"{tcm.FONTES['esiproc']['base']}/pesquisar", json={
            "timed_out": False, "_shards": {"total": 1, "successful": 1, "failed": 0},
            "hits": {"total": {"value": 1, "relation": "eq"}, "hits": [{"_source": fonte}]}})
        r = _chamar("processos_tcm", municipio="nova crixas", tipo="Contas de Gestão", ano=2023)
        filtros = json.loads(simulado.calls[0].request.body)["filtros"]
    assert filtros["municipio.keyword"] == "NOVA CRIXÁS" and filtros["ano_competencia"] == 2023
    assert filtros["tipo_protocolo.keyword"] == "Contas de Gestão"
    assert r["total"] == 1 and r["municipio_tcm"] == "NOVA CRIXÁS" and "erro" not in r
    assert r["registros"][0]["numero"] == fonte["numero"] and r["registros"][0]["finalizado"] is True
    assert r["registros"][0]["fonte"] == "TCM-GO eSiproc"
    assert r["aviso_fonte"] == tcm.AVISO_PROCESSOS and r["aviso_envolvidos"] == tcm.AVISO_ENVOLVIDOS
    assert r["aviso"] == tcm.AVISO_GERAL


def test_processos_resolve_o_municipio_e_diz_total_piso(monkeypatch):
    recebido = {}

    def falso(c, **pedido):
        recebido.update(pedido)
        return {"total": 10000, "registros": [{"numero": "00000131.2019"}], "total_e_piso": True}
    monkeypatch.setattr(esiproc, "processos", falso)
    r = _chamar("processos_tcm", municipio="Nova Crixás", tipo="Contas de Gestão", ano=2023, maximo=1)
    assert recebido["municipio"] == "NOVA CRIXÁS" and recebido["ano"] == 2023
    assert r["municipio_tcm"] == "NOVA CRIXÁS" and r["total"] == 10000 and len(r["registros"]) == 1
    assert "piso" in r["aviso_total"]
    assert r["aviso_fonte"] == tcm.AVISO_PROCESSOS and r["aviso_envolvidos"] == tcm.AVISO_ENVOLVIDOS


def test_acordaos_resolve_o_nome_encurtado_e_diz_leitura_incompleta(monkeypatch):
    recebido = {}

    def falso(c, **pedido):
        recebido.update(pedido)
        return {"total": 500, "registros": [], "incompleta": "teto de 60 chamadas atingido"}
    monkeypatch.setattr(tcmjuris, "acordaos", falso)
    r = _chamar("acordaos_tcm", municipio="Alto Paraíso de Goiás", ano=2022)
    assert recebido["municipio"] == "ALTO PARAISO" and recebido["ano"] == 2022
    assert "incompleta" in r["aviso_leitura"] and r["aviso_fonte"] == tcm.AVISO_ACORDAOS


def test_municipio_sem_casamento_exato_e_recusado_com_os_mais_parecidos(monkeypatch):
    monkeypatch.setitem(tcm._LISTAS, "esiproc", [("NOVA CRIXÁS", "NOVA CRIXÁS"), ("POSSE", "POSSE")])
    r = _chamar("processos_tcm", municipio="Nova Crixa")
    assert "NOVA CRIXÁS" in r["erro"] and "zero" not in r["erro"]
    assert r["aviso_fonte"] == tcm.AVISO_PROCESSOS
