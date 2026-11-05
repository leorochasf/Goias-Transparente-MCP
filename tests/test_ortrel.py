"""Câmaras Ortrel, pelo `Portal` e pelas ferramentas MCP. Offline: o site e a API Ortrel são simulados.

Formato medido em Cidade Ocidental (04/11/2026; seção E da descoberta e `## Comments` do ticket 06):
- o site serve `/src/services/api.js` com `import.meta.env = {"API_URL": ..., "VITE_FIXED_TOKEN": ...}`;
- folha, diárias, contratos, licitações e legislação vêm inteiros numa chamada; as despesas, por ano e mês, em
  páginas de 100 (`page`, `totalPages`);
- o documento do credor pessoa física vem mascarado (`930******72`); o CNPJ da empresa vem completo.
"""
import json
from datetime import date

import anyio
import pytest
import responses
from mcp import Client

from transparencia_municipal import Portal, catalogo, ortrel, servidor_mcp
from transparencia_municipal.cliente import ErroPortal

URL = "https://transparencia.exemplo.go.leg.br"
API = "https://api.transparencia.exemplo.go.leg.br"
TOKEN = "eyJ.teste.token"
API_JS = ('import { createHotContext } from "/@vite/client";\n'
          f'import.meta.env = {{"API_URL": "{API}", "BASE_URL": "/", "DEV": true, "VITE_FIXED_TOKEN": "{TOKEN}"}};\n'
          'const API_DEP = import.meta.env.API_URL || API_LOCAL;\n')
FOLHA = f"{API}/api/dados/rh/folha_de_pagamento"
DESPESAS = f"{API}/api/dados/despesas"
DIARIAS = f"{API}/api/dados/rh/diarias"
CONTRATOS = f"{API}/api/dados/todos-contratos"
LICITACOES = f"{API}/api/dados/licitacoes"
LEIS = f"{API}/api/dados/legislacao/leis_municipais"


@pytest.fixture(autouse=True)
def _limpo(monkeypatch):
    ortrel._ACESSOS.clear()
    servidor_mcp._LEITURAS.clear()
    servidor_mcp._RESSALVAS.clear()
    monkeypatch.setattr(catalogo, "carregar", lambda: [])
    yield
    ortrel._ACESSOS.clear()


def _portal():
    return Portal(URL, pausa=0, plataforma="ortrel")


def _site(api_js=API_JS):
    responses.add(responses.GET, f"{URL}/src/services/api.js", body=api_js, content_type="application/javascript")


def _itens(*rubricas, ano=2025, mes="09"):
    return json.dumps([{"nome_item": n, "tipo": t, "provento": p, "desconto": d, "ano": str(ano), "mes": mes}
                       for n, t, p, d in rubricas])


def _servidor(matricula, ano=2025, mes="09", proventos="3000.00", itens=None, **campos):
    return {"matricula": matricula, "nome": f"PESSOA {matricula}", "cpf": "***.***.***-12", "cargo": "ASSESSOR",
            "situacao": "Ativo", "data_admissao": "2025-01-01", "proventos": proventos, "descontos": "500.00",
            "total_liquido": "2500.00", "departamento": "GABINETE DE VEREADOR(A)", "situacao_pagamento": "Não Informado",
            "ano": ano, "mes": mes, "orgao": "GABINETE DE VEREADOR(A)", "decreto": "12/2025",
            "data_decreto": "2025-01-01", "tipo_vinculo": "SERVIDOR PUBLICO NAOEFETIVO DEMISSIVEL AD NUTUM",
            "nivel": "Não informado", "carga_horaria": 200, "jornada_semanal": 40,
            "itens": itens if itens is not None else _itens(("SALARIO BASE", "Proventos", "3000.0", "0.0"),
                                                           ("INSS", "Descontos", "0.0", "500.0"), ano=ano, mes=mes),
            **campos}


def _folha(*linhas):
    linhas = list(linhas)
    responses.add(responses.GET, FOLHA, json={"folhaPagamento": linhas, "PagamentosPaginados": linhas,
                                              "totalPages": 1})


def _despesa(i, data="2025-03-10", doc="12.345.678/0001-90", nome="EMPRESA A LTDA", valor="200.00"):
    return {"id_despesa": i, "data": data, "fonte_recurso": "1500", "nome_fornecedor": nome,
            "cpf_cnpj_mascarado": doc, "orgao_unidade_gestora": "Câmara Municipal de Exemplo",
            "unidade": "0101 - CAMARA MUNICIPAL", "valor_empenho": valor, "valor_liquidado": valor,
            "valor_total_pagamento": valor, "bem_servico_prestado": "MATERIAL DE EXPEDIENTE",
            "liquidacoes_json": "[]", "pagamentos_json": "[]"}


def _despesas_do_mes(ano, mes, registros, por_pagina=100):
    """Responde `ano`/`mes`/`page` como a API medida: páginas de 100, `total` e `totalPages`."""
    paginas = [registros[i:i + por_pagina] for i in range(0, len(registros), por_pagina)] or [[]]
    for n, lote in enumerate(paginas, start=1):
        responses.add(responses.GET, DESPESAS,
                      match=[responses.matchers.query_param_matcher(
                          {"ano": str(ano), "mes": str(mes), "page": str(n), "limit": "100"})],
                      json={"despesas": lote, "despesasPaginados": lote, "total": len(registros), "page": n,
                            "limit": 100, "totalPages": len(paginas), "totais": {}})


# ── acesso: api.js e token ──────────────────────────────────────────────────────────────────────────────────────────

@responses.activate
def test_api_e_token_saem_do_api_js_e_vao_nos_cabecalhos_lido_uma_vez():
    _site()
    _folha(_servidor(1))
    _folha(_servidor(1))
    p = _portal()
    p.folha(2025, 9)
    p.folha(2025, 9)
    leituras_api_js = [c for c in responses.calls if c.request.url.endswith("/src/services/api.js")]
    assert len(leituras_api_js) == 1
    chamada = next(c.request for c in responses.calls if c.request.url.startswith(FOLHA))
    assert chamada.headers["Authorization"] == f"Bearer {TOKEN}"
    assert chamada.headers["Origin"] == URL and chamada.headers["Referer"] == f"{URL}/"


@responses.activate
def test_api_js_sem_api_url_e_erro_claro():
    _site("export default {}")
    with pytest.raises(ErroPortal, match="API_URL"):
        _portal().folha(2025, 9)


@responses.activate
def test_api_sem_token_vai_sem_authorization():
    _site(API_JS.replace(f', "VITE_FIXED_TOKEN": "{TOKEN}"', ""))
    _folha(_servidor(1))
    _portal().folha(2025, 9)
    chamada = next(c.request for c in responses.calls if c.request.url.startswith(FOLHA))
    assert "Authorization" not in chamada.headers


@responses.activate
def test_http_diferente_de_200_e_erro_e_nunca_total_zero():
    _site()
    responses.add(responses.GET, FOLHA, status=500, body="erro interno")
    with pytest.raises(ErroPortal, match="500"):
        _portal().folha(2025, 9)


# ── folha ───────────────────────────────────────────────────────────────────────────────────────────────────────────

@responses.activate
def test_folha_recorta_o_mes_da_serie_inteira_e_traduz_com_rubricas():
    _site()
    _folha(_servidor(1), _servidor(2), _servidor(1, mes="08"), _servidor(3, ano=2024))
    r = _portal().folha(2025, 9)
    assert r["total"] == 2 and [x["matricula"] for x in r["registros"]] == ["1", "2"]
    linha = r["registros"][0]
    assert linha["fonte"] == "Ortrel" and linha["lotacao"] == "GABINETE DE VEREADOR(A)"
    assert linha["vinculo"].startswith("SERVIDOR PUBLICO NAOEFETIVO")
    assert linha["total_proventos"] == "3.000,00" and linha["total_liquido"] == "2.500,00"
    assert linha["decreto"] == "12/2025" and linha["data_decreto"] == "2025-01-01"
    assert "mensal" in linha["tipo_folha"].lower()
    assert linha["lista_proventos"] == [{"evento": None, "nome": "SALARIO BASE", "valor": "3.000,00",
                                         "tipo": "Provento"}]
    assert linha["lista_descontos"] == [{"evento": None, "nome": "INSS", "valor": "500,00", "tipo": "Desconto"}]
    assert any("13º" in frase for frase in r["ressalvas"])


@responses.activate
def test_folha_busca_pelo_nome_sem_acento_e_conta_os_que_casam():
    _site()
    _folha(_servidor(1, nome="JOSÉ DA SILVA"), _servidor(2), _servidor(3, nome="MARIA JOSE"))
    r = _portal().folha(2025, 9, "jose", maximo=1)
    assert r["total"] == 2 and len(r["registros"]) == 1


@responses.activate
def test_folha_avisa_quando_a_soma_das_rubricas_nao_bate_com_o_bruto():
    _site()
    _folha(_servidor(1), _servidor(2, proventos="3500.00"))
    r = _portal().folha(2025, 9)
    assert any("1 das 2 linhas" in frase for frase in r["ressalvas"])


@responses.activate
def test_folha_de_mes_sem_linhas_da_total_zero():
    _site()
    _folha(_servidor(1))
    assert _portal().folha(2025, 1)["total"] == 0


# ── despesas ────────────────────────────────────────────────────────────────────────────────────────────────────────

@responses.activate
def test_despesas_pedem_mes_a_mes_paginam_e_recortam_o_periodo():
    _site()
    _despesas_do_mes(2025, 3, [_despesa(i, data="2025-03-05") for i in range(100)]
                     + [_despesa(100 + i, data="2025-03-25") for i in range(30)])
    _despesas_do_mes(2025, 4, [_despesa(200, data="2025-04-02"), _despesa(201, data="2025-04-20")])
    r = _portal().despesas("2025-03-20", "2025-04-10", maximo=1000)
    assert r["total"] == 31 and len(r["registros"]) == 31
    x = r["registros"][0]
    assert x["data"] == "25/03/2025" and x["fonte"] == "Ortrel" and x["valor_empenhado"] == "200,00"
    assert x["cpf_cnpj"] == "12.345.678/0001-90" and x["orgao"] == "Câmara Municipal de Exemplo"
    assert any("mascarado" in frase for frase in r["ressalvas"])


@responses.activate
def test_despesas_com_linha_de_outro_mes_sao_erro_porque_o_filtro_foi_ignorado():
    _site()
    _despesas_do_mes(2025, 3, [_despesa(1, data="2025-03-05"), _despesa(2, data="2025-07-01")])
    with pytest.raises(ErroPortal, match="mês"):
        _portal().despesas("2025-03-01", "2025-03-31")


@responses.activate
def test_despesas_por_cnpj_conferem_o_documento_e_avisam_dos_mascarados_que_nao_dao_para_conferir():
    _site()
    _despesas_do_mes(2025, 3, [_despesa(1), _despesa(2, doc="98.765.432/0001-10"), _despesa(3, doc="930******72"),
                               _despesa(4, doc="12.***.***/****-90")])
    r = _portal().despesas("2025-03-01", "2025-03-31", "12345678000190")
    assert r["total"] == 1 and r["registros"][0]["empenho"] == "1"
    assert any("1 empenho" in frase and "não" in frase for frase in r["ressalvas"])


@responses.activate
def test_despesas_busca_pelo_nome_do_fornecedor():
    _site()
    _despesas_do_mes(2025, 3, [_despesa(1, nome="PAPELARIA CENTRAL"), _despesa(2), _despesa(3, nome="Papelaria Sul")])
    r = _portal().despesas("2025-03-01", "2025-03-31", "papelaria")
    assert r["total"] == 2


# ── contratos ───────────────────────────────────────────────────────────────────────────────────────────────────────

def _contrato(i, ano=2025, objeto="LOCAÇÃO DE VEÍCULO", aditado=None):
    return {"id": i, "numero_contrato": f"{i}.2025.1", "modalidade": "Dispensa de Licitação",
            "numero_e_ano_licitacao": "1/2025", "numero_processo": "10/2025", "data_assinatura": f"{ano}-02-01",
            "data_vigencia_fim": f"{ano}-12-31", "data_publicacao": f"{ano}-02-02", "nome_orgao": "Câmara",
            "cnpj_fornecedor": "12.345.678/0001-90", "nome_fornecedor": "EMPRESA A LTDA", "objeto": objeto,
            "valor_contratado": "1000.00", "valor_executado": "500.00", "valor_aditado": aditado,
            "valor_total": "1000.00", "saldo": "500.00", "nome_fiscal": "PESSOA X", "exercicio_ano": ano,
            "situacao": "Em Vigor", "anexos": []}


@responses.activate
def test_contratos_vem_todos_e_sao_filtrados_por_ano_e_busca():
    _site()
    responses.add(responses.GET, CONTRATOS, json={"contratos": [_contrato(1), _contrato(2, ano=2024),
                                                                _contrato(3, objeto="SERVIÇO DE LIMPEZA")],
                                                  "totalContratos": 3, "totalPages": 1})
    r = _portal().contratos(2025, busca="veiculo")
    assert r["total"] == 1
    x = r["registros"][0]
    assert x["numero"] == "1.2025.1" and x["data_firmatura"] == "01/02/2025" and x["valor"] == "1.000,00"
    assert x["fonte"] == "Ortrel" and x["valor_aditado"] is None


@responses.activate
def test_contratos_aditivos_sao_recusados_porque_vem_dentro_do_contrato():
    _site()
    with pytest.raises(ValueError, match="valor_aditado"):
        _portal().contratos(2025, tipo="aditivo")


# ── licitações ──────────────────────────────────────────────────────────────────────────────────────────────────────

def _licitacao(i, modalidade="Convite para Obras e Serviços de Engenharia", publicacao="2025-05-02",
               protocolo="2025-04-01"):
    return {"id_licitacao": str(i), "numero_protocolo": f"{i}/2025", "numero_ano": f"{i}/25",
            "modalidade_numero_ano": f"{modalidade} - {i}/25", "modalidade": modalidade, "situacao": "Homologada",
            "data_protocolo": protocolo, "data_abertura": None, "data_julgamento": None, "data_homologacao": None,
            "data_publicacao": publicacao, "valor_estimado": "1000.00", "valor_vencedor": None, "orgao": "Câmara",
            "descricao": "AQUISIÇÃO DE MATERIAL", "itens_vencedores": "[]"}


@responses.activate
def test_licitacoes_separam_dispensas_filtram_ano_e_avisam_das_sem_data():
    _site()
    regs = [_licitacao(1), _licitacao(2, modalidade="Dispensa de Licitação"),
            _licitacao(3, modalidade="Inexigibilidade de Licitação"), _licitacao(4, publicacao=None),
            _licitacao(5, publicacao="2024-03-01", protocolo="2024-02-01")]
    responses.add(responses.GET, LICITACOES, json={"dados": regs, "dadosPaginados": regs, "totalPages": 1})
    responses.add(responses.GET, LICITACOES, json={"dados": regs, "dadosPaginados": regs, "totalPages": 1})
    p = _portal()
    licitacoes = p.licitacoes(ano=2025)
    assert [x["chave"] for x in licitacoes["registros"]] == ["1", "4"]
    assert licitacoes["registros"][0]["data_publicacao"] == "02/05/2025"
    assert any("1 licitação" in frase and "protocolo" in frase for frase in licitacoes["ressalvas"])
    dispensas = p.licitacoes(dispensas=True)
    assert [x["chave"] for x in dispensas["registros"]] == ["2", "3"]


# ── diárias ─────────────────────────────────────────────────────────────────────────────────────────────────────────

def _diaria(saida, chegada=None, nome="PESSOA 1", destino="GOIÂNIA-GO"):
    return {"data_pagamento": saida, "nome_funcionario": nome, "numero_diarias": "2.00", "valor_diaria": "150.00",
            "valor_total": "300.0000", "cargo_funcionario": "VEREADOR", "destino": destino, "data_saida": saida,
            "data_chegada": chegada or saida, "natureza_despesa": "339014 - DIARIAS CIVIL",
            "Histórico": "PARTICIPAÇÃO EM CURSO"}


@responses.activate
def test_diarias_recortam_o_periodo_pela_saida_traduzem_e_avisam_das_datas_espurias():
    _site()
    regs = [_diaria("2025-01-10", "2025-01-12"), _diaria("2025-02-01"), _diaria("1899-12-30"),
            _diaria("2025-01-20", destino="BRASÍLIA-DF")]
    responses.add(responses.GET, DIARIAS, json={"rhdiarias": regs, "totalPages": 1})
    r = _portal().diarias("2025-01-01", "2025-01-31", "brasilia")
    assert r["total"] == 1
    x = r["registros"][0]
    assert x == {"favorecido": "PESSOA 1", "matricula": None, "cargo": "VEREADOR", "orgao": None,
                 "destino": "BRASÍLIA-DF", "motivo": "PARTICIPAÇÃO EM CURSO", "data_saida": "20/01/2025",
                 "data_chegada": "20/01/2025", "quantidade": "2.00", "valor": "300,00", "valor_unitario": "150,00",
                 "empenho": None, "fonte": "Ortrel"}
    assert any("1 diária" in frase and "1899" in frase for frase in r["ressalvas"])


# ── legislação ──────────────────────────────────────────────────────────────────────────────────────────────────────

def _lei(i, numero, ano, nome_ato=None, descricao="DISPÕE SOBRE O PLANO DE CARGOS", publicacao=None):
    return {"id": i, "codigo": None, "tipo": "Lei", "numero": numero, "ano": ano,
            "data_publicacao": publicacao or f"{ano}-03-14", "nome_ato": nome_ato or f"Lei {numero}/{ano}",
            "descricao": descricao, "nome_arquivo": f"{i}.pdf", "caminho_arquivo": f"{i}.pdf",
            "midia_arquivo_assinado": f"https://arquivos.exemplo/{i}.pdf"}


@responses.activate
def test_legislacao_tira_a_lei_repetida_mas_guarda_mesmo_numero_de_outro_ano():
    _site()
    regs = [_lei(1, 1471, 2025),
            # a mesma lei de novo, com o ano errado no campo `ano` (medido: 2026 para uma lei de 2025)
            _lei(2, 1471, 2026, nome_ato="Lei Municipal nº 1.471, de 14 de março de 2025", publicacao="2025-03-16"),
            _lei(3, 11, 1995, descricao="OUTORGA TÍTULO"), _lei(4, 11, 1993, descricao="AUTORIZA OBRA"),
            # emenda à Lei Orgânica com o mesmo número e ano de uma lei: não é repetição
            _lei(5, 11, 2025, nome_ato="Emenda à Lei Orgânica nº 011/2025", descricao="ALTERA O ART. 42"),
            _lei(6, 11, 2025, descricao="DENOMINA RUA"),
            # mesmo número e mesma ementa em outro ano (medido: 7 pares, quase todos cadastrados em 2021): fica, com aviso
            _lei(7, 1210, 2021, descricao="CRIA O FUNDO"), _lei(8, 1210, 2019, descricao="CRIA O FUNDO")]
    responses.add(responses.GET, LEIS, json={"leisMunicipais": regs, "leisMunicipaisPaginados": regs, "totalPages": 1})
    responses.add(responses.GET, LEIS, json={"leisMunicipais": regs, "leisMunicipaisPaginados": regs, "totalPages": 1})
    p = _portal()
    r = p.legislacao("LEI")
    assert r["total"] == 7 and sorted(x["id"] for x in r["registros"]) == ["1", "3", "4", "5", "6", "7", "8"]
    assert any("1 lei" in frase and "repetida" in frase for frase in r["ressalvas"])
    assert any("1 lei" in frase and "mesma ementa" in frase for frase in r["ressalvas"])
    x = next(x for x in r["registros"] if x["id"] == "1")
    assert x["numero"] == "1471" and x["ano"] == 2025 and x["data_publicacao"] == "14/03/2025"
    assert x["arquivo"] == "https://arquivos.exemplo/1.pdf" and x["fonte"] == "Ortrel"
    assert p.legislacao("lei", "titulo", ano=1995)["total"] == 1


@responses.activate
def test_legislacao_de_outro_tipo_e_recusada_dizendo_que_so_ha_leis():
    with pytest.raises(ValueError, match="LEI"):
        _portal().legislacao("DECRETO")
    assert len(responses.calls) == 0


# ── ponta a ponta pelo cliente MCP ──────────────────────────────────────────────────────────────────────────────────

def _chamar(ferramenta, **argumentos):
    async def rodar():
        async with Client(servidor_mcp.mcp) as cliente:
            r = await cliente.call_tool(ferramenta, argumentos)
            return json.loads(r.content[0].text)
    return anyio.run(rodar)


def _camara_no_catalogo(monkeypatch):
    camara = {"municipio": "Exemplo", "orgao": "camara", "portal": URL, "plataforma": "ortrel", "sufixos": {},
              "outros_enderecos": [], "conferencia": None}
    monkeypatch.setattr(catalogo, "carregar", lambda: [camara])


@responses.activate
def test_mcp_resumir_folha_numa_camara_ortrel(monkeypatch):
    _camara_no_catalogo(monkeypatch)
    _site()
    _folha(_servidor(1), _servidor(2), _servidor(3, tipo_vinculo="AGENTE POLITICO", departamento="PLENARIO"),
           _servidor(4, mes="08"))
    r = _chamar("resumir_folha", ano=2025, mes=9, agrupar_por="vinculo", portal=URL)
    assert "erro" not in r, r
    assert r["total_do_mes"] == 3 and "PESSOA" not in json.dumps(r)
    (tipo, resumo), = r["por_tipo_de_pagamento"].items()
    assert "mensal" in tipo.lower() and resumo["linhas"] == 3 and resumo["bruto"] == 9000.0
    assert any("13º" in frase for frase in r["ressalvas"])


@responses.activate
def test_mcp_consultar_despesas_numa_camara_ortrel(monkeypatch):
    _camara_no_catalogo(monkeypatch)
    _site()
    _despesas_do_mes(2025, 3, [_despesa(1), _despesa(2, doc="930******72", nome="PESSOA Y")])
    r = _chamar("consultar_despesas", de="2025-03-01", ate="2025-03-31", portal=URL)
    assert "erro" not in r, r
    assert r["total"] == 2 and {x["fonte"] for x in r["registros"]} == {"Ortrel"}
    assert any("mascarado" in frase for frase in r["ressalvas"]) and "aviso_leitura" not in r


def test_diarias_recebem_datas_do_portal(monkeypatch):
    """O `Portal` entrega `datetime.date` ao encaixe (contrato do ticket 01)."""
    recebido = {}
    monkeypatch.setattr(ortrel, "diarias", lambda portal, **a: recebido.update(a) or {"total": 0, "registros": []})
    _portal().diarias("2025-01-01", "2025-01-31")
    assert recebido["de"] == date(2025, 1, 1) and recebido["ate"] == date(2025, 1, 31)
