"""Fechamento dos módulos extras (ticket 07): `error` da API, somas por órgão e os nomes unificados. Offline."""
import json
import urllib.parse

import pytest
import responses

from transparencia_municipal import ErroPortal, Portal, cli, megasoft_embutida, ortrel, traducao_megasoft
from transparencia_municipal.servidor_mcp import _aviso_orgaos

PORTAL = "https://acessoainformacao.exemplo.go.gov.br"


def _responde(bruto):
    def callback(requisicao):
        campos = urllib.parse.parse_qs(requisicao.body.decode("utf-8"))
        ident = next(iter(json.loads(campos["params"][0])))
        return 200, {}, json.dumps({ident: bruto})
    return callback


@responses.activate
def test_campo_error_da_api_vira_erro_claro_e_nao_zero_calado():
    """A Megasoft embutida responde `error` (não `erro`) ao filtro de período das licitações, com total 0."""
    responses.add_callback(responses.POST, f"{PORTAL}/api/licitacoes_mg/listarCidadao",
                           callback=_responde({"dados": [], "total": 0, "error": "Houve um problema com a requisição"}))
    with pytest.raises(ErroPortal, match="Houve um problema"):
        Portal(PORTAL, sufixos={}).consultar("licitacoes_mg/listarCidadao", {"data_inicial": "2025-01-01"})


@pytest.mark.parametrize("vazio", ["", "null", None])
@responses.activate
def test_campo_error_vazio_ou_null_nao_e_erro(vazio):
    responses.add_callback(responses.POST, f"{PORTAL}/api/contratos_mg/listar",
                           callback=_responde({"dados": [{"numero": "1"}], "total": 1, "error": vazio}))
    assert Portal(PORTAL, sufixos={}).consultar("contratos_mg/listar")["total"] == 1


def test_aviso_orgaos_olha_as_somas_por_orgao_quando_os_registros_vem_cortados():
    """Centi em Posse com `maximo` 100: só vem o Poder Executivo nos registros, mas a resposta tem 13 órgãos."""
    r = {"total": 611, "registros": [{"orgao": "PODER EXECUTIVO"}] * 3,
         "somas_por_orgao": [{"orgao": "Poder Executivo", "linhas": 300}, {"orgao": "FPPS", "linhas": 20},
                             {"orgao": "Fundo vazio", "linhas": 0}]}
    assert "2:" in _aviso_orgaos(r, "as receitas")["aviso_orgaos"]


def test_aviso_orgaos_dos_contratos_usa_o_nome_do_orgao():
    r = {"total": 2, "registros": [{"orgao": 3, "orgao_nome": "PODER EXECUTIVO"},
                                   {"orgao": 7, "orgao_nome": "FUNDO DE SAÚDE"}]}
    assert "aviso_orgaos" in _aviso_orgaos(r, "os contratos")
    assert "aviso_orgaos" not in _aviso_orgaos({"total": 1, "registros": [{"orgao": 3}]}, "os contratos")


def test_linha_de_comando_imprime_as_somas_por_orgao(monkeypatch, capsys):
    resposta = {"total": 2, "registros": [{"orgao": "Poder Executivo"}], "ressalvas": [],
                "somas_por_orgao": [{"orgao": "Poder Executivo", "linhas": 2, "linhas_analiticas": 1,
                                     "valor_arrecadado_mes": "1.400,00", "valor_arrecadado_ate_mes": "9.000,00"},
                                    {"orgao": "Fundo vazio", "linhas": 0, "linhas_analiticas": 0,
                                     "valor_arrecadado_mes": None, "valor_arrecadado_ate_mes": None}]}
    monkeypatch.setattr(Portal, "receitas", lambda self, ano, mes, maximo: resposta)
    cli.main(["--portal", PORTAL, "receitas", "--ano", "2025", "--mes", "9"])
    saida = capsys.readouterr().out
    assert "Poder Executivo" in saida and "1.400,00" in saida and "9.000,00" in saida
    assert "Fundo vazio" in saida and "0 linhas" in saida


# ── nomes unificados: os do NucleoGov quando existem ─────────────────────────────────────────────────────────────────

CONTRATO_NUCLEOGOV = {"id", "numero", "ano", "orgao_nome", "situacao", "objeto", "fornecedor_nome",
                      "fornecedor_cpfcnpj", "valor", "data_firmatura", "fim_vigencia", "fiscal_contrato"}
ANTIGOS_CONTRATO = {"codigo", "exercicio", "fornecedor", "cpf_cnpj", "data_assinatura", "vigencia", "vigencia_fim",
                    "fiscal", "data"}
LICITACAO_NUCLEOGOV = {"numero", "label", "modalidade", "situacao", "orgao", "descricao", "data_publicacao"}
ANTIGOS_LICITACAO = {"codigo", "objeto", "valor"}


def test_contratos_da_megasoft_propria_com_os_nomes_do_nucleogov():
    c = traducao_megasoft.contrato({"codigo": 9, "numero": 12, "nomeDoOrgao": "PREFEITURA", "exercicioAno": 2025,
                                    "nomeDoFornecedor": "EMPRESA", "cpfOuCnpjDoFornecedor": "11111111000111",
                                    "data": "2025-02-03", "vigencia": "2025-12-31", "nomeDoFiscalDoContrato": "F",
                                    "objeto": "x", "situacao": "Vigente", "valor": 10})
    assert CONTRATO_NUCLEOGOV <= set(c) and not set(c) & ANTIGOS_CONTRATO
    assert (c["id"], c["ano"], c["orgao_nome"], c["fornecedor_cpfcnpj"]) == (9, 2025, "PREFEITURA",
                                                                             "11.111.111/0001-11")
    assert c["data_firmatura"] == "03/02/2025" and c["fim_vigencia"] == "31/12/2025"


def test_contratos_da_megasoft_embutida_com_os_nomes_do_nucleogov():
    c = megasoft_embutida._contrato({"numero": "5", "ano": 2025, "orgao": 3, "fornecedor_nome": "E",
                                     "fornecedor_cpfcnpj": "11.111.111/0001-11", "data_firmatura": "01/02/2025",
                                     "fiscal_contrato": "F", "fim_vigencia": "01/02/2026"})
    assert {"numero", "ano", "orgao", "fornecedor_nome", "fornecedor_cpfcnpj", "data_firmatura", "fiscal_contrato",
            "fim_vigencia"} <= set(c) and not set(c) & ANTIGOS_CONTRATO
    assert c["orgao"] == "3" and c["fornecedor_nome"] == "E"


def test_contratos_do_ortrel_com_os_nomes_do_nucleogov():
    c = ortrel.contrato({"id": 1, "numero_contrato": "1/2025", "nome_orgao": "CÂMARA", "exercicio_ano": 2025,
                         "nome_fornecedor": "E", "cnpj_fornecedor": "11.111.111/0001-11",
                         "data_assinatura": "2025-02-03", "data_vigencia_fim": "2025-12-31", "nome_fiscal": "F"})
    assert CONTRATO_NUCLEOGOV <= set(c) and not set(c) & ANTIGOS_CONTRATO
    assert c["orgao_nome"] == "CÂMARA" and c["data_firmatura"] == "03/02/2025" and c["fim_vigencia"] == "31/12/2025"


def test_licitacoes_da_megasoft_propria_com_os_nomes_do_nucleogov():
    x = traducao_megasoft.licitacao({"codigo": 4, "numeroAno": "24/2025", "historico": "obra",
                                     "valorVencedorTotal": 10, "dataDePublicacao": "2025-03-01", "orgao": "PREF"})
    assert LICITACAO_NUCLEOGOV <= set(x) and not set(x) & ANTIGOS_LICITACAO
    assert (x["id"], x["numero"], x["label"], x["descricao"], x["valor_vencedor"]) == (4, "24", "24/2025", "obra",
                                                                                      "10,00")


def test_licitacoes_da_megasoft_embutida_com_os_nomes_do_nucleogov():
    x = megasoft_embutida._licitacao({"numero": "24", "label": "024/2025", "ano": 2025, "descricao": "obra",
                                      "orgao": "PREF", "valor_vencedor_total": "10,00"})
    assert LICITACAO_NUCLEOGOV <= set(x) and not set(x) & ANTIGOS_LICITACAO
    assert (x["numero"], x["label"], x["descricao"]) == ("24", "024/2025", "obra")


def test_licitacoes_do_ortrel_com_os_nomes_do_nucleogov():
    x = ortrel.licitacao({"id_licitacao": 4, "numero_ano": "24/2025", "descricao": "obra", "orgao": "CÂMARA",
                          "data_publicacao": "2025-03-01"})
    assert LICITACAO_NUCLEOGOV <= set(x) and not set(x) & ANTIGOS_LICITACAO
    assert (x["id"], x["numero"], x["label"], x["descricao"]) == (4, "24", "24/2025", "obra")


@responses.activate
def test_ano_dos_contratos_no_nucleogov_vai_no_filtro_ano_e_nao_no_anobase():
    """Medido em Alexânia (04/11/2026): `anobase` é ignorado (6.989 contratos de todos os anos); `ano` filtra (798)."""
    pedidos = []

    def callback(requisicao):
        campos = urllib.parse.parse_qs(requisicao.body.decode("utf-8"))
        ident, corpo = next(iter(json.loads(campos["params"][0]).items()))
        pedidos.append(corpo)
        return 200, {}, json.dumps({ident: {"dados": [{"ano": 2025}], "total": 1}})
    responses.add_callback(responses.POST, f"{PORTAL}/api/contratos_frl/listar", callback=callback)
    Portal(PORTAL, sufixos={"contratos": "frl"}, plataforma="nucleogov").contratos(2025)
    assert pedidos[0]["ano"] == "2025" and "anobase" not in pedidos[0]
