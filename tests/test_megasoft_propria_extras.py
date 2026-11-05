"""Módulos extras da Megasoft de domínio próprio (ticket 02): receitas, diárias, contratos, licitações e o detalhe do
servidor, pelo `Portal` e pelo cliente MCP. Offline: o portal é simulado.

Formato medido em Corumbaíba (04/11/2026; desenho dos módulos extras, descoberta A): receitas pela consulta detalhada
por natureza (`ano`, `mes`); diárias com `data=1` (recorte pela saída); contratos e licitações só por POST, com os
filtros no corpo JSON; detalhe do servidor por GET, e matrícula inexistente responde 406.
"""
import json
import urllib.parse

import anyio
import pytest
import responses
from mcp import Client

from transparencia_municipal import Portal, catalogo, megasoft_propria, servidor_mcp
from transparencia_municipal.cliente import ErroPortal

URL = "https://exemplo.megasofttransparencia.com.br"
SENHA = f"{URL}/api/configuracao/carregamento-inicial"
RECEITAS = f"{URL}/api/receitas-e-despesas/receita/receitas-pelo-tipo-de-natureza-detalhada/paginado"
DIARIAS = f"{URL}/api/orgaos-e-servidores/diaria/paginado"
CONTRATOS = f"{URL}/api/contratos-convenios-e-licitacoes/contrato/paginado"
LICITACOES = f"{URL}/api/contratos-convenios-e-licitacoes/procedimento-licitatorio/paginado"
DETALHE = f"{URL}/api/orgaos-e-servidores/servidor/detalhe"


@pytest.fixture(autouse=True)
def _senhas_limpas(monkeypatch):
    megasoft_propria._SENHAS.clear()
    monkeypatch.setattr(catalogo, "carregar", lambda: [])
    responses.add(responses.GET, SENHA, json={"tokenPortal": "senha-1"})
    yield
    megasoft_propria._SENHAS.clear()


def _autorizada(requisicao):
    return (requisicao.headers.get("Authorization") == "Bearer senha-1"
            and requisicao.headers.get("cliente-integrado") == "megasoft-portal-da-transparencia")


def _get(endereco, registros, total=None):
    """Listagem por GET, paginada como a Megasoft (`pagina` a partir de 1); POST responde 405."""
    def callback(requisicao):
        if not _autorizada(requisicao):
            return 401, {}, "{}"
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(requisicao.url).query))
        pagina, tamanho = int(q["pagina"]), int(q["tamanhoDaPagina"])
        lote = registros[(pagina - 1) * tamanho:pagina * tamanho]
        return 200, {}, json.dumps({"paginaAtual": pagina, "registros": lote,
                                    "total": len(registros) if total is None else total})
    responses.add_callback(responses.GET, endereco, callback=callback, content_type="application/json")
    responses.add(responses.POST, endereco, status=405)


def _post(endereco, registros, total=None):
    """Listagem só por POST, com `pagina`, `tamanhoDaPagina` e os filtros no corpo JSON; GET responde 405."""
    def callback(requisicao):
        if not _autorizada(requisicao):
            return 401, {}, "{}"
        corpo = json.loads(requisicao.body)
        pagina, tamanho = corpo["pagina"], corpo["tamanhoDaPagina"]
        lote = registros[(pagina - 1) * tamanho:pagina * tamanho]
        return 200, {}, json.dumps({"paginaAtual": pagina, "registros": lote,
                                    "total": len(registros) if total is None else total})
    responses.add_callback(responses.POST, endereco, callback=callback, content_type="application/json")
    responses.add(responses.GET, endereco, status=405)


def _consultas(endereco):
    return [dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(c.request.url).query))
            for c in responses.calls if c.request.url.startswith(endereco)]


def _corpos(endereco):
    return [json.loads(c.request.body) for c in responses.calls
            if c.request.url.startswith(endereco) and c.request.method == "POST"]


# ── receitas ───────────────────────────────────────────────────────────────────────────────────────────────────

def _receita(codigo, mes="09", orgao="PREFEITURA MUNICIPAL DE EXEMPLO", ano=2025):
    return {"chave": {"codigoDaReceita": codigo, "ano": ano, "mes": mes, "codigoDoOrgao": 3},
            "orgaoUnidadeGestora": orgao, "fonteDaReceita": "1.00.000 - Recursos Não vinculados de Impostos",
            "receita": "IPTU", "naturezaDaReceita": "1112.50.0.1 - IPTU", "origemDoRecurso": "Rendas Locais",
            "valorOrcado": 280000.0, "arrecadacao": 1471.6, "valorAcumulado": 291320.16, "ano": ano}


@responses.activate
def test_receitas_do_mes_pela_consulta_detalhada_traduzidas_com_fonte_e_ressalva_dos_orgaos():
    _get(RECEITAS, [_receita(1), _receita(2, orgao="CAMARA MUNICIPAL DE EXEMPLO")])
    r = Portal(URL, pausa=0).receitas(2025, 9)
    assert _consultas(RECEITAS)[0]["ano"] == "2025" and _consultas(RECEITAS)[0]["mes"] == "09"
    assert r["total"] == 2
    linha = r["registros"][0]
    assert linha == {"orgao": "PREFEITURA MUNICIPAL DE EXEMPLO", "codigo": "1112.50.0.1", "receita": "IPTU",
                     "fonte_recurso": "1.00.000 - Recursos Não vinculados de Impostos",
                     "valor_orcado": "280.000,00", "valor_previsto_atualizado": None,
                     "valor_arrecadado_mes": "1.471,60", "valor_arrecadado_ate_mes": "291.320,16", "ano": 2025,
                     "mes": 9, "analitica": None, "fonte": "Megasoft"}
    assert any("órgão" in x or "orgao" in x for x in r["ressalvas"])


@responses.activate
def test_receitas_com_linha_de_outro_mes_viram_erro_em_vez_de_mistura():
    _get(RECEITAS, [_receita(1), _receita(2, mes="12")])
    with pytest.raises(ErroPortal, match="outro mês"):
        Portal(URL, pausa=0).receitas(2025, 9)


# ── diárias ────────────────────────────────────────────────────────────────────────────────────────────────────

def _diaria(codigo, saida="10/01/2025", destino="GOIÂNIA-GO", cargo="MOTORISTA", motivo="LEVAR PACIENTE",
            numero=2.0, valor=100.0):
    return {"codigoDaViagem": codigo, "matriculaDoFuncionario": 10 + codigo, "nomeDoFuncionario": f"PESSOA {codigo}",
            "cargoDoFuncionario": cargo, "destino": destino, "codigoDaLiquidacao": 346451, "dataDaSaida": saida,
            "dataDaChegada": saida, "valorDaDiaria": valor, "numeroDeDiarias": numero, "motivoDaViagem": motivo,
            "numeroDaLiquidacao": "20254506"}


@responses.activate
def test_diarias_pedem_data_1_e_saem_com_os_nomes_comuns():
    _get(DIARIAS, [_diaria(1), _diaria(2, numero=1.5, valor=75.0)])
    r = Portal(URL, pausa=0).diarias("2025-01-01", "2025-03-31")
    q = _consultas(DIARIAS)[0]
    assert (q["data"], q["dataInicial"], q["dataFinal"]) == ("1", "01/01/2025", "31/03/2025")
    assert r["total"] == 2
    assert r["registros"][0] == {
        "favorecido": "PESSOA 1", "matricula": "11", "cargo": "MOTORISTA", "orgao": None, "destino": "GOIÂNIA-GO",
        "motivo": "LEVAR PACIENTE", "data_saida": "10/01/2025", "data_chegada": "10/01/2025", "quantidade": "2",
        "valor": "100,00", "valor_unitario": None, "empenho": "20254506", "fonte": "Megasoft"}
    assert r["registros"][1]["quantidade"] == "1,5"
    assert any("valor" in x for x in r["ressalvas"])


@responses.activate
def test_diarias_por_busca_sao_filtradas_pelo_projeto_em_destino_cargo_e_motivo():
    _get(DIARIAS, [_diaria(1), _diaria(2, destino="BRASÍLIA-DF", cargo="SECRETARIO", motivo="CURSO"),
                   _diaria(3, destino="CALDAS NOVAS", motivo="Reunião em Goiania")])
    portal = Portal(URL, pausa=0)
    assert portal.diarias("2025-01-01", "2025-03-31", "goiania")["total"] == 2
    assert portal.diarias("2025-01-01", "2025-03-31", "secretário")["registros"][0]["destino"] == "BRASÍLIA-DF"


@responses.activate
def test_diarias_com_saida_fora_do_periodo_viram_erro():
    _get(DIARIAS, [_diaria(1), _diaria(2, saida="10/05/2025")])
    with pytest.raises(ErroPortal, match="fora do período"):
        Portal(URL, pausa=0).diarias("2025-01-01", "2025-03-31")


# ── contratos ──────────────────────────────────────────────────────────────────────────────────────────────────

def _contrato(codigo, ano=2025, objeto="OBRA DE PAVIMENTAÇÃO", orgao="FUNDO MUNICIPAL DE SAÚDE"):
    return {"codigo": codigo, "numero": str(codigo), "modalidade": "DISPENSA DE LICITAÇÃO",
            "numeroEAnoDaLicitacao": 3162025, "data": f"01/12/{ano}", "vigencia": f"31/12/{ano}",
            "nomeDoOrgao": orgao, "cpfOuCnpjDoFornecedor": "25.107.525/0001-51", "nomeDoFornecedor": "EMPRESA A LTDA",
            "objeto": objeto, "valor": 5100.0, "nomeDoFiscalDoContrato": "PESSOA F", "exercicioAno": ano,
            "situacao": "Encerrado", "finalidade": "Prestação de Serviços"}


@responses.activate
def test_contratos_do_ano_por_post_traduzidos_com_fonte():
    _post(CONTRATOS, [_contrato(1), _contrato(2)])
    r = Portal(URL, pausa=0).contratos(2025)
    assert _corpos(CONTRATOS)[0]["ano"] == 2025
    assert r["total"] == 2
    assert r["registros"][0] == {
        "id": 1, "numero": "1", "modalidade": "DISPENSA DE LICITAÇÃO", "licitacao": "316/2025",
        "data_firmatura": "01/12/2025", "fim_vigencia": "31/12/2025", "orgao_nome": "FUNDO MUNICIPAL DE SAÚDE",
        "fornecedor_cpfcnpj": "25.107.525/0001-51", "fornecedor_nome": "EMPRESA A LTDA",
        "objeto": "OBRA DE PAVIMENTAÇÃO",
        "valor": "5.100,00", "fiscal_contrato": "PESSOA F", "ano": 2025, "situacao": "Encerrado",
        "finalidade": "Prestação de Serviços", "fonte": "Megasoft"}


@responses.activate
def test_contratos_por_busca_filtrados_pelo_projeto_e_repetidos_tirados(monkeypatch):
    monkeypatch.setattr(megasoft_propria, "TAMANHO", 2)
    # a fronteira de página repete o contrato 2: são 3 distintos
    _post(CONTRATOS, [_contrato(1), _contrato(2), _contrato(2), _contrato(3, objeto="MERENDA")], total=3)
    r = Portal(URL, pausa=0).contratos(2025, busca="pavimentacao")
    assert r["total"] == 2 and [x["id"] for x in r["registros"]] == [1, 2]


@responses.activate
def test_contrato_de_outro_ano_vira_erro():
    _post(CONTRATOS, [_contrato(1), _contrato(2, ano=2024)])
    with pytest.raises(ErroPortal, match="outro ano"):
        Portal(URL, pausa=0).contratos(2025)


@responses.activate
def test_aditivos_nao_tem_consulta_medida_e_sao_recusados_sem_chamar_a_rede():
    with pytest.raises(ValueError, match="aditivo"):
        Portal(URL, pausa=0).contratos(2025, tipo="aditivo")
    assert len(responses.calls) == 0


# ── licitações ─────────────────────────────────────────────────────────────────────────────────────────────────

def _licitacao(codigo, publicacao="15/03/2025", modalidade="PREGÃO ELETRÔNICO", historico="AQUISIÇÃO DE MEDICAMENTOS"):
    return {"codigo": codigo, "numeroAno": f"{codigo}/2025", "dataDeJulgamento": "20/03/2025",
            "modalidade": modalidade, "situacao": "Homologada", "valorVencedorTotal": 49860.0,
            "historico": historico, "orgao": "FUNDO MUNICIPAL DE SAÚDE", "dataDePublicacao": publicacao}


@responses.activate
def test_licitacoes_e_dispensas_pelo_tipo_de_consulta_e_ano_pela_data_de_publicacao():
    _post(LICITACOES, [_licitacao(1), _licitacao(2, historico="LOCAÇÃO")])
    portal = Portal(URL, pausa=0)
    r = portal.licitacoes(ano=2025)
    portal.licitacoes("medicamentos", dispensas=True)
    licitacoes, dispensas = _corpos(LICITACOES)[0], _corpos(LICITACOES)[-1]
    assert licitacoes["tipoDeConsultaDeModalidade"] == 1 and dispensas["tipoDeConsultaDeModalidade"] == 2
    assert (licitacoes["dataDePublicacaoInicial"], licitacoes["dataDePublicacaoFinal"]) == ("01/01/2025", "31/12/2025")
    assert "dataDePublicacaoInicial" not in dispensas
    assert r["registros"][0] == {
        "id": 1, "numero": "1", "label": "1/2025", "modalidade": "PREGÃO ELETRÔNICO", "situacao": "Homologada",
        "data_publicacao": "15/03/2025", "data_julgamento": "20/03/2025", "valor_vencedor": "49.860,00",
        "descricao": "AQUISIÇÃO DE MEDICAMENTOS", "orgao": "FUNDO MUNICIPAL DE SAÚDE", "fonte": "Megasoft"}
    assert portal.licitacoes("medicamentos", dispensas=True)["total"] == 1
    assert any("chamamento" in x for x in r["ressalvas"])


@responses.activate
def test_licitacao_publicada_fora_do_ano_vira_erro():
    _post(LICITACOES, [_licitacao(1), _licitacao(2, publicacao="02/01/2024")])
    with pytest.raises(ErroPortal, match="outro ano"):
        Portal(URL, pausa=0).licitacoes(ano=2025)


# ── detalhe do servidor ────────────────────────────────────────────────────────────────────────────────────────

def _lista(*registros, total=None):
    return {"total": len(registros) if total is None else total, "registros": list(registros), "paginaAtual": 1}


def _detalhe(**campos):
    vazio = _lista()
    return {"mesAno": "09/2025", "matricula": 325, "cpf": "XXX.123.456-XX", "nome": "PESSOA 325",
            "orgao": "FUNDO MUN. DE EDUCACAO", "cargo": "PROFESSOR I - 40 HRS", "cargoRec": "PROFESSOR I - 40 HRS",
            "dataAdmissao": "18/02/2002", "departamento": "2034- MANUTENÇÃO DO ENSINO FUNDAMENTAL",
            "tipoDeVinculo": "Concursado", "decreto": "202/02", "dataDecreto": "18/02/2002", "classificacao": "34",
            "nivel": "A", "cargaHoraria": 200, "situacao": "Ativo", "localDeTrabalho": "ESCOLA MUNICIPAL",
            "categoriaDoTrabalhadorNoESocial": "301 - Servidor Público Titular de Cargo Efetivo",
            "ferias": vazio, "vidaFuncionalDisposicao": vazio,
            "licenca": _lista({"descricao": "Licença Prêmio", "historico": "", "tipoDeLicenca": "Licença Prêmio",
                               "dataDeAfastamento": "01/09/2025", "dataDeRetorno": "29/11/2025"}),
            "movimentoVencimentos": _lista({"nome": "Outras Remunerações", "proventos": 8543.66, "descontos": 3878.68,
                                            "existeConcessaoDeVerba": False, "matricula": 325}),
            "movimento13Salario": vazio, "movimentoFerias": vazio, "movimentoComplementar": vazio,
            "movimentoSessoesExtraordinarias": vazio, "movimentoRescisao": vazio,
            "somatorioMovimentoVencimentos": {"somatorioProventos": 8543.66, "somatorioDescontos": 3878.68,
                                              "totalLiquido": 4664.98},
            "somatorioMovimento13Salario": {}, "mes": "09", "ano": 2025, **campos}


@responses.activate
def test_detalhe_do_servidor_traz_decreto_licencas_e_movimentos_sem_rubricas():
    responses.add(responses.GET, DETALHE, json=_detalhe())
    r = Portal(URL, pausa=0).detalhe_servidor("325", 2025, 9)
    q = _consultas(DETALHE)[0]
    assert (q["matricula"], q["mes"], q["ano"], q["mesInteger"]) == ("325", "09", "2025", "9")
    assert r["total"] == 1
    d = r["registros"][0]
    assert (d["matricula"], d["decreto"], d["data_decreto"], d["vinculo"]) == ("325", "202/02", "18/02/2002", "Concursado")
    assert (d["cargo"], d["lotacao"], d["orgao"], d["fonte"]) == (
        "PROFESSOR I - 40 HRS", "2034- MANUTENÇÃO DO ENSINO FUNDAMENTAL", "FUNDO MUN. DE EDUCACAO", "Megasoft")
    assert d["licencas"] == [{"tipo": "Licença Prêmio", "descricao": "Licença Prêmio", "historico": "",
                              "data_afastamento": "01/09/2025", "data_retorno": "29/11/2025"}]
    assert d["ferias"] == []
    assert d["movimentos"] == {"vencimentos": {
        "eventos": [{"evento": "Outras Remunerações", "proventos": "8.543,66", "descontos": "3.878,68"}],
        "total_proventos": "8.543,66", "total_descontos": "3.878,68", "total_liquido": "4.664,98"}}
    assert "ressalvas" not in r


@responses.activate
def test_detalhe_com_lista_cortada_ou_concessao_de_verba_diz_isso_em_ressalva():
    licenca = {"descricao": "L", "historico": "", "tipoDeLicenca": "L", "dataDeAfastamento": "01/01/2020",
               "dataDeRetorno": "02/01/2020"}
    evento = {"nome": "Gratificação", "proventos": 100.0, "descontos": 0.0, "existeConcessaoDeVerba": True}
    responses.add(responses.GET, DETALHE, json=_detalhe(licenca=_lista(*[licenca] * 5, total=7),
                                                        movimentoVencimentos=_lista(evento)))
    r = Portal(URL, pausa=0).detalhe_servidor("325", 2025, 9)
    assert any("licenças" in x and "5 de 7" in x for x in r["ressalvas"])
    assert any("concessão de verba" in x for x in r["ressalvas"])


@responses.activate
def test_detalhe_de_matricula_que_nao_existe_no_mes_da_zero_e_outro_erro_continua_erro():
    responses.add(responses.GET, DETALHE, status=406, body='{"trace":"x","lista":[{"mensagem":"Valor de chave não '
                                                           'existe para a função indicada.","campos":[]}]}')
    assert Portal(URL, pausa=0).detalhe_servidor("99999999", 2025, 9) == {"total": 0, "registros": []}
    responses.replace(responses.GET, DETALHE, status=500, body="erro interno")
    with pytest.raises(ErroPortal, match="500"):
        Portal(URL, pausa=0).detalhe_servidor("325", 2025, 9)


# ── ponta a ponta, pelo cliente MCP no mesmo processo ──────────────────────────────────────────────────────────

def _chamar(ferramenta, **argumentos):
    async def rodar():
        async with Client(servidor_mcp.mcp) as cliente:
            r = await cliente.call_tool(ferramenta, argumentos)
            return json.loads(r.content[0].text)
    return anyio.run(rodar)


@responses.activate
def test_mcp_consultar_diarias_num_portal_megasoft_proprio():
    _get(DIARIAS, [_diaria(1), _diaria(2, destino="BRASÍLIA-DF")])
    r = _chamar("consultar_diarias", de="2025-01-01", ate="2025-03-31", busca="brasilia", portal=URL)
    assert r["total"] == 1 and r["registros"][0]["destino"] == "BRASÍLIA-DF"
    assert r["registros"][0]["fonte"] == "Megasoft"
    assert "aviso_diarias" in r and r["ressalvas"]
    assert "aviso_leitura" not in r


@responses.activate
def test_mcp_detalhe_servidor_num_portal_megasoft_proprio():
    responses.add(responses.GET, DETALHE, json=_detalhe())
    r = _chamar("detalhe_servidor", matricula="325", ano=2025, mes=9, portal=URL)
    assert r["registros"][0]["decreto"] == "202/02" and "aviso_rubricas" in r


@responses.activate
def test_mcp_consultar_receitas_num_portal_megasoft_proprio_avisa_os_orgaos():
    _get(RECEITAS, [_receita(1), _receita(2, orgao="CAMARA MUNICIPAL DE EXEMPLO")])
    r = _chamar("consultar_receitas", ano=2025, mes=9, portal=URL)
    assert r["total"] == 2 and "aviso_orgaos" in r and r["ressalvas"]
