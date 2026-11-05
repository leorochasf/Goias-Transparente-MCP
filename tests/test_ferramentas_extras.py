"""Ferramentas e comandos dos módulos extras: consultar_diarias, detalhe_servidor, licitações por ano e as marcas da
resposta (ressalvas, total piso, leitura incompleta). Offline; os encaixes são dublês. Pelo cliente MCP no mesmo
processo, como em test_tcm_mcp.py."""
import json

import anyio
import pytest
from mcp import Client

from transparencia_municipal import catalogo, cli, megasoft_propria, ortrel, servidor_mcp

PROPRIA = "https://exemplo.megasofttransparencia.com.br"
ORTREL = "https://transparencia.exemplo.go.leg.br"
NUCLEOGOV = "https://acessoainformacao.exemplo.go.gov.br"
DIARIA = {"favorecido": "PESSOA 1", "matricula": "10", "cargo": "MOTORISTA", "orgao": "PREFEITURA",
          "destino": "GOIÂNIA", "motivo": "levar paciente", "data_saida": "10/01/2025", "data_chegada": "10/01/2025",
          "quantidade": "1", "valor": "150,00", "valor_unitario": None, "empenho": "123", "fonte": "Megasoft"}


@pytest.fixture(autouse=True)
def sem_catalogo(monkeypatch):
    monkeypatch.setattr(catalogo, "carregar", lambda: [])


def _chamar(ferramenta, **argumentos):
    async def rodar():
        async with Client(servidor_mcp.mcp) as cliente:
            r = await cliente.call_tool(ferramenta, argumentos)
            return json.loads(r.content[0].text)
    return anyio.run(rodar)


def _esquemas():
    async def rodar():
        async with Client(servidor_mcp.mcp) as cliente:
            return {t.name: t.input_schema for t in (await cliente.list_tools()).tools}
    return anyio.run(rodar)


def test_ferramentas_novas_existem_com_os_parametros_combinados():
    e = _esquemas()
    assert set(e["consultar_diarias"]["properties"]) == {"de", "ate", "busca", "portal", "maximo"}
    assert set(e["consultar_diarias"]["required"]) == {"de", "ate"}
    assert set(e["detalhe_servidor"]["properties"]) == {"matricula", "ano", "mes", "portal"}
    assert set(e["detalhe_servidor"]["required"]) == {"matricula", "ano", "mes"}
    assert "ano" in e["consultar_licitacoes"]["properties"]


def test_consultar_diarias_traz_os_avisos_as_ressalvas_e_a_leitura_incompleta(monkeypatch):
    recebido = {}

    def falso(portal, **pedido):
        recebido.update(pedido)
        return {"total": 3, "registros": [DIARIA], "incompleta": "a fonte parou na página 2",
                "ressalvas": ["o portal recorta pela data de saída"]}
    monkeypatch.setattr(megasoft_propria, "diarias", falso)
    r = _chamar("consultar_diarias", de="2025-01-01", ate="2025-03-31", busca="goiania", portal=PROPRIA, maximo=5)
    assert str(recebido["de"]) == "2025-01-01" and recebido["busca"] == "goiania" and recebido["maximo"] == 5
    assert r["registros"] == [DIARIA] and r["total"] == 3
    assert r["ressalvas"] == ["o portal recorta pela data de saída"]
    assert "a fonte parou na página 2" in r["aviso_leitura"]
    assert "não publicou" in r["aviso_diarias"] and "dossiê" in r["aviso_diarias"]
    assert r["aviso"] == servidor_mcp.AVISO


def test_leitura_que_parou_antes_do_total_sem_marca_tambem_e_dita(monkeypatch):
    monkeypatch.setattr(megasoft_propria, "diarias", lambda portal, **_: {"total": 9, "registros": [DIARIA]})
    r = _chamar("consultar_diarias", de="2025-01-01", ate="2025-01-31", portal=PROPRIA)
    assert "1 de 9" in r["aviso_leitura"]


def test_total_piso_e_dito(monkeypatch):
    monkeypatch.setattr(megasoft_propria, "diarias",
                        lambda portal, **_: {"total": 100, "registros": [DIARIA], "total_e_piso": True})
    r = _chamar("consultar_diarias", de="2025-01-01", ate="2025-01-31", portal=PROPRIA, maximo=1)
    assert "piso" in r["aviso_total"] and "aviso_leitura" not in r


def test_consultar_diarias_com_erro_traz_o_aviso_das_diarias(monkeypatch):
    r = _chamar("consultar_diarias", de="2025-03-01", ate="2025-01-31", portal=PROPRIA)
    assert "anterior" in r["erro"] and "aviso_diarias" in r


def test_detalhe_servidor_traz_o_aviso_de_que_a_megasoft_nao_tem_rubricas(monkeypatch):
    recebido = {}

    def falso(portal, **pedido):
        recebido.update(pedido)
        return {"total": 1, "registros": [{"matricula": "10", "decreto": "12/2021", "fonte": "Megasoft"}]}
    monkeypatch.setattr(megasoft_propria, "detalhe_servidor", falso)
    r = _chamar("detalhe_servidor", matricula="10", ano=2025, mes=9, portal=PROPRIA)
    assert recebido == {"matricula": "10", "ano": 2025, "mes": 9}
    assert r["registros"][0]["decreto"] == "12/2021"
    assert "rubricas" in r["aviso_rubricas"] and "decreto" in r["aviso_rubricas"]


def test_detalhe_servidor_fora_da_megasoft_propria_responde_erro_com_o_aviso():
    r = _chamar("detalhe_servidor", matricula="10", ano=2025, mes=9, portal=NUCLEOGOV)
    assert "Megasoft de domínio próprio" in r["erro"] and "aviso_rubricas" in r


def test_consultar_receitas_avisa_quando_os_orgaos_se_misturam(monkeypatch):
    linhas = [{"orgao": "CÂMARA", "fonte": "Megasoft"}, {"orgao": "PREFEITURA", "fonte": "Megasoft"}]
    monkeypatch.setattr(megasoft_propria, "receitas", lambda portal, **_: {"total": 2, "registros": linhas})
    r = _chamar("consultar_receitas", ano=2025, mes=9, portal=PROPRIA)
    assert "mais de um órgão" in r["aviso_orgaos"]


def test_consultar_licitacoes_por_ano_vai_ao_encaixe(monkeypatch):
    recebido = {}
    monkeypatch.setattr(megasoft_propria, "licitacoes",
                        lambda portal, **p: recebido.update(p) or {"total": 0, "registros": []})
    _chamar("consultar_licitacoes", dispensas=True, ano=2025, portal=PROPRIA)
    assert recebido == {"busca": None, "dispensas": True, "ano": 2025, "maximo": 100}


def test_consultar_folha_com_rubricas_traduzidas_de_outro_sistema_mostra_as_rubricas(monkeypatch):
    """O Ortrel publica as rubricas: a linha traduzida que traz as listas não recebe o aviso de "sem rubricas"."""
    linha = {"matricula": "1", "nome": "PESSOA 1", "tipo_folha": "Mensal", "fonte": "Ortrel",
             "lista_proventos": [{"evento": None, "nome": "SALARIO BASE", "valor": "1.000,00", "tipo": "P"}],
             "lista_descontos": []}
    monkeypatch.setattr(ortrel, "folha", lambda portal, **_: {"total": 1, "registros": [linha]})
    camara = {"municipio": "Exemplo", "orgao": "camara", "portal": ORTREL, "plataforma": "ortrel", "sufixos": {},
              "outros_enderecos": [], "conferencia": None}
    monkeypatch.setattr(catalogo, "carregar", lambda: [camara])
    r = servidor_mcp.consultar_folha(2025, 9, busca="PESSOA", portal=ORTREL)
    assert r["linhas"][0]["rubricas"][0]["nome"] == "SALARIO BASE" and "aviso_rubricas" not in r


def test_mcp_usa_a_plataforma_do_catalogo_so_no_endereco_do_portal(monkeypatch):
    """Outro endereço do órgão (o site da câmara) não é o portal Ortrel: a plataforma do catálogo não vale ali."""
    camara = {"municipio": "Exemplo", "orgao": "camara", "portal": ORTREL, "plataforma": "ortrel", "sufixos": {},
              "outros_enderecos": ["exemplo.go.leg.br"], "conferencia": None}
    monkeypatch.setattr(catalogo, "carregar", lambda: [camara])
    assert servidor_mcp._portal(ORTREL).plataforma == "ortrel"
    assert servidor_mcp._portal("https://exemplo.go.leg.br").plataforma is None


# ── linha de comando ─────────────────────────────────────────────────────────────────────────────────────────────

def test_cli_diarias_imprime_as_ressalvas_e_grava(monkeypatch, capsys, tmp_path):
    recebido = {}

    def falso(portal, **pedido):
        recebido.update(pedido)
        return {"total": 1, "registros": [DIARIA], "ressalvas": ["o valor vem vazio neste portal"]}
    monkeypatch.setattr(megasoft_propria, "diarias", falso)
    saida = tmp_path / "d.json"
    cli.main(["--portal", PROPRIA, "--json", str(saida), "diarias", "--de", "2025-01-01", "--ate", "2025-03-31",
              "--busca", "goiania"])
    assert str(recebido["ate"]) == "2025-03-31" and recebido["busca"] == "goiania"
    assert "AVISO: o valor vem vazio neste portal" in capsys.readouterr().out
    assert json.loads(saida.read_text(encoding="utf-8")) == [DIARIA]


def test_cli_detalhe_servidor_diz_que_nao_ha_rubricas(monkeypatch, capsys):
    monkeypatch.setattr(megasoft_propria, "detalhe_servidor",
                        lambda portal, **p: {"total": 1, "registros": [{"matricula": p["matricula"]}]})
    cli.main(["--portal", PROPRIA, "detalhe-servidor", "--matricula", "10", "--ano", "2025", "--mes", "9"])
    texto = capsys.readouterr().out
    assert "AVISO:" in texto and "rubricas" in texto and '"matricula": "10"' in texto


def test_cli_licitacoes_por_ano(monkeypatch):
    recebido = {}
    monkeypatch.setattr(megasoft_propria, "licitacoes",
                        lambda portal, **p: recebido.update(p) or {"total": 0, "registros": []})
    cli.main(["--portal", PROPRIA, "licitacoes", "--ano", "2025", "--dispensas"])
    assert recebido["ano"] == 2025 and recebido["dispensas"] is True


def test_cli_leitura_incompleta_e_avisada(monkeypatch, capsys):
    monkeypatch.setattr(megasoft_propria, "despesas", lambda portal, **_: {"total": 5, "registros": [{}],
                                                                          "incompleta": "teto de páginas"})
    cli.main(["--portal", PROPRIA, "despesas", "--de", "2025-01-01", "--ate", "2025-01-31"])
    assert "AVISO: leitura incompleta (teto de páginas)" in capsys.readouterr().out
