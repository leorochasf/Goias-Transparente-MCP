"""Cliente do TCM-GO (parte comum): nome do município em cada fonte, erros claros e encaixes. Offline."""
import json

import pytest
import responses

from transparencia_municipal import catalogo, esiproc, tcm, tcmjuris
from transparencia_municipal.tcm import ClienteTCM, ErroTCM, MunicipioNaoEncontrado, NaoDisponivel, TetoAtingido

ESIPROC = tcm.FONTES["esiproc"]["base"]
TCMJURIS = tcm.FONTES["tcmjuris"]["base"]


def _lista_esiproc(*nomes):
    """`/listar-campo` do eSiproc no formato real: buckets de uma agregação."""
    responses.post(f"{ESIPROC}/listar-campo", json={
        "took": 3, "timed_out": False, "_shards": {"total": 1, "successful": 1, "skipped": 0, "failed": 0},
        "hits": {"total": {"value": 10000, "relation": "gte"}, "hits": []},
        "aggregations": {"distinct": {"buckets": [{"key": n, "doc_count": 7} for n in nomes]}}})


def _lista_tcmjuris(*municipios):
    """`/filtros` do TCMJuris no formato real: `data.municipios[] {nome, valor}`."""
    responses.get(f"{TCMJURIS}/v1/acordao/jurisprudencia/filtros", json={
        "success": True, "timestamp": "2026-11-04T10:00:00",
        "data": {"anos": [2020, 2021], "conselheiros": [], "assuntos": [],
                 "municipios": [{"nome": n, "valor": v} for n, v in municipios]}})


@pytest.fixture
def cliente():
    return ClienteTCM(pausa=0)


@pytest.fixture
def sem_catalogo(monkeypatch):
    monkeypatch.setattr(catalogo, "carregar", lambda: [])


# --- nome do município em cada fonte -------------------------------------------------------------------------------

def test_casamento_ignora_caixa_acento_e_apostrofo():
    assert tcm.casar("sitio d'abadia", ["SÍTIO DABADIA", "SÃO DOMINGOS"]) == "SÍTIO DABADIA"
    assert tcm.casar("Nova Crixás", ["NOVA CRIXÁS", "CRIXÁS"]) == "NOVA CRIXÁS"


def test_casamento_e_exato_nunca_aproxima():
    assert tcm.casar("Crixás", ["NOVA CRIXÁS"]) is None
    assert tcm.casar("Nova Crixa", ["NOVA CRIXÁS"]) is None


def test_apelido_conferido_casa_o_nome_que_o_tcmjuris_encurta():
    assert tcm.casar("Alto Paraíso de Goiás", ["Alto Paraiso", "Alto Horizonte"]) == "Alto Paraiso"
    assert tcm.casar("alto paraiso", ["ALTO PARAÍSO DE GOIÁS"]) == "ALTO PARAÍSO DE GOIÁS"


def test_catalogo_traz_o_nome_de_cada_fonte_sem_consultar_o_tcm(cliente):
    # sem `responses` ativo, qualquer chamada de rede falharia (trava do conftest)
    assert cliente.municipio("esiproc", "nova crixas") == "NOVA CRIXÁS"
    assert cliente.municipio("tcmjuris", "Alto Paraíso") == "ALTO PARAISO"
    assert cliente.municipio("tcmjuris", "Abadia de Goiás") == "ABADIA GOIAS"


def test_todo_municipio_do_catalogo_tem_o_nome_nas_duas_fontes_do_tcm():
    sem_nome = {x["municipio"] for x in catalogo.carregar()
                if not (x.get("tcm") or {}).get("esiproc") or not (x.get("tcm") or {}).get("tcmjuris")}
    assert sem_nome == set()


@responses.activate
def test_fora_do_catalogo_consulta_a_lista_oficial_na_hora(cliente, sem_catalogo):
    _lista_esiproc("NOVA CRIXÁS", "CRIXÁS")
    _lista_tcmjuris(("Abadia de Goiás", "ABADIA GOIAS"), ("Nova Crixás", "NOVA CRIXAS"))
    assert cliente.municipio("esiproc", "Nova Crixás") == "NOVA CRIXÁS"
    assert cliente.municipio("tcmjuris", "abadia de goias") == "ABADIA GOIAS"
    corpo = json.loads(responses.calls[0].request.body)
    assert corpo["campo"] == "municipio.keyword" and corpo["filtros"] == {}
    assert responses.calls[0].request.headers["Referer"] == tcm.FONTES["esiproc"]["referer"]


@responses.activate
def test_lista_oficial_e_lida_uma_vez_por_processo(cliente, sem_catalogo):
    _lista_esiproc("NOVA CRIXÁS", "CRIXÁS")
    cliente.municipio("esiproc", "Nova Crixás")
    cliente.municipio("esiproc", "Crixás")
    assert len(responses.calls) == 1


@responses.activate
def test_sem_casamento_exato_recusa_e_mostra_os_mais_parecidos(cliente, sem_catalogo):
    _lista_esiproc("NOVA CRIXÁS", "CRIXÁS", "POSSE")
    with pytest.raises(MunicipioNaoEncontrado) as e:
        cliente.municipio("esiproc", "Nova Crixa")
    assert "NOVA CRIXÁS" in str(e.value) and "POSSE" not in str(e.value)
    assert "Nova Crixa" in str(e.value)


@responses.activate
def test_na_hora_ignora_o_catalogo(cliente):
    _lista_esiproc("NOVA CRIXÁS (NOVO NOME)")
    with pytest.raises(MunicipioNaoEncontrado):
        cliente.municipio("esiproc", "Nova Crixás", na_hora=True)


# --- erros claros -------------------------------------------------------------------------------------------------

@responses.activate
def test_fonte_fora_do_ar_vira_erro_claro(cliente, sem_catalogo):
    responses.post(f"{ESIPROC}/listar-campo", status=503, body="Service Unavailable")
    with pytest.raises(ErroTCM, match="eSiproc.*503"):
        cliente.municipio("esiproc", "Posse")


@responses.activate
def test_html_com_200_vira_erro_e_nao_lista_vazia(cliente, sem_catalogo):
    responses.get(f"{TCMJURIS}/v1/acordao/jurisprudencia/filtros", body="<html>manutenção</html>",
                  content_type="text/html")
    with pytest.raises(ErroTCM, match="TCMJuris.*inesperada"):
        cliente.municipio("tcmjuris", "Posse")


@responses.activate
def test_sem_conexao_vira_erro_claro(cliente, sem_catalogo):
    import requests
    responses.post(f"{ESIPROC}/listar-campo", body=requests.ConnectionError("recusada"))
    with pytest.raises(ErroTCM, match="eSiproc"):
        cliente.municipio("esiproc", "Posse")


@responses.activate
def test_teto_de_chamadas_por_consulta(cliente):
    cliente.teto = 2
    responses.get(f"{TCMJURIS}/x", json={"ok": True})
    cliente.nova_consulta()
    cliente.json("tcmjuris", "GET", "/x")
    cliente.json("tcmjuris", "GET", "/x")
    with pytest.raises(TetoAtingido, match="2 chamadas"):
        cliente.json("tcmjuris", "GET", "/x")
    cliente.nova_consulta()
    cliente.json("tcmjuris", "GET", "/x")
    assert len(responses.calls) == 3


@responses.activate
def test_identifica_o_projeto_com_honestidade(cliente):
    responses.get(f"{TCMJURIS}/x", json={"ok": True})
    cliente.json("tcmjuris", "GET", "/x")
    assert "Goias-Transparente-MCP" in responses.calls[0].request.headers["User-Agent"]
    assert responses.calls[0].request.headers["Referer"] == tcm.FONTES["tcmjuris"]["referer"]


# --- encaixes: o cliente resolve o nome e chama o módulo da fonte ---------------------------------------------------

def test_processos_entrega_ao_encaixe_o_nome_oficial_do_eSiproc(cliente, monkeypatch):
    recebido = {}

    def falso(c, **pedido):
        recebido.update(pedido)
        return {"total": 1, "registros": [{"numero": "x"}], "total_e_piso": True}
    monkeypatch.setattr(esiproc, "processos", falso)
    r = cliente.processos("nova crixas", tipo="Contas de Gestão", ano=2023, finalizado=False, maximo=5)
    assert recebido == {"municipio": "NOVA CRIXÁS", "tipo": "Contas de Gestão", "ano": 2023, "finalizado": False,
                        "relator": None, "numero": None, "maximo": 5}
    assert r["municipio_tcm"] == "NOVA CRIXÁS"
    assert "ou mais" in r["aviso_total"]


def test_acordaos_entrega_ao_encaixe_o_valor_do_tcmjuris_e_avisa_leitura_incompleta(cliente, monkeypatch):
    recebido = {}

    def falso(c, **pedido):
        recebido.update(pedido)
        return {"total": 250, "registros": [], "incompleta": "teto de 60 chamadas atingido"}
    monkeypatch.setattr(tcmjuris, "acordaos", falso)
    r = cliente.acordaos("Alto Paraíso de Goiás", assunto="Contas", maximo=3)
    assert recebido["municipio"] == "ALTO PARAISO" and recebido["assunto"] == "Contas"
    assert "teto de 60 chamadas" in r["aviso_leitura"]


def test_acordaos_e_leitura_respondem_ainda_nao_disponivel_enquanto_o_tcmjuris_esta_vazio(cliente):  # ticket 03
    with pytest.raises(NaoDisponivel, match="ainda não disponível"):
        cliente.acordaos("Posse")
    with pytest.raises(NaoDisponivel, match="ainda não disponível"):
        cliente.ler_acordao("7b0e1c2a-0000-0000-0000-000000000000")


def test_acordaos_sem_municipio_nao_filtra_municipio(cliente, monkeypatch):
    recebido = {}
    monkeypatch.setattr(tcmjuris, "acordaos", lambda c, **p: recebido.update(p) or {"total": 0, "registros": []})
    cliente.acordaos(texto="imputação de débito")
    assert recebido["municipio"] is None


def test_processos_exige_municipio_ou_numero(cliente):
    with pytest.raises(ValueError, match="municipio"):
        cliente.processos()


# --- linha de comando ---------------------------------------------------------------------------------------------

def test_cli_tcm_processos_resolve_o_municipio_e_mostra_os_avisos(monkeypatch, capsys, tmp_path):
    from transparencia_municipal import cli
    recebido = {}

    def falso(c, **pedido):
        recebido.update(pedido)
        return {"total": 2, "registros": [{"numero": "1"}, {"numero": "2"}]}
    monkeypatch.setattr(esiproc, "processos", falso)
    saida = tmp_path / "p.json"
    cli.main(["--json", str(saida), "tcm-processos", "--municipio", "nova crixas", "--ano", "2023",
              "--nao-finalizado", "--numero", "00131/19"])
    assert recebido["municipio"] == "NOVA CRIXÁS" and recebido["ano"] == 2023
    assert recebido["finalizado"] is False and recebido["numero"] == "00131/19"
    texto = capsys.readouterr().out
    assert tcm.AVISO_PROCESSOS in texto and tcm.AVISO_ENVOLVIDOS in texto
    assert json.loads(saida.read_text(encoding="utf-8")) == [{"numero": "1"}, {"numero": "2"}]


def test_cli_tcm_acordao_mostra_o_texto(monkeypatch, capsys):
    from transparencia_municipal import cli
    monkeypatch.setattr(tcmjuris, "ler_acordao", lambda c, document_id: {
        "total": 1, "registros": [{"document_id": document_id, "pdf": "https://x/pdf", "texto": "ACÓRDÃO Nº 1"}]})
    cli.main(["tcm-acordao", "abc"])
    assert "ACÓRDÃO Nº 1" in capsys.readouterr().out


def test_cli_tcm_com_a_fonte_vazia_diz_ainda_nao_disponivel():  # ticket 03 substitui
    from transparencia_municipal import cli
    with pytest.raises(SystemExit, match="ainda não disponível"):
        cli.main(["tcm-acordaos", "--municipio", "Caldazinha", "--assunto", "Contas"])


def test_cli_do_portal_continua_exigindo_o_portal():
    from transparencia_municipal import cli
    with pytest.raises(SystemExit, match="--portal"):
        cli.main(["receitas", "--ano", "2025", "--mes", "3"])
