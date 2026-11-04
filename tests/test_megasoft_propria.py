"""Megasoft de domínio próprio (`*.megasofttransparencia.com.br`), pelo `Portal`. Offline: o portal é simulado.

Formato medido em Corumbaíba (04/11/2026): a senha pública vem de `/api/configuracao/carregamento-inicial`
(`tokenPortal`); as listagens respondem `{paginaAtual, registros, total}`, com `pagina` começando em 1.
"""
import json
import urllib.parse

import pytest
import responses

from transparencia_municipal import Portal, megasoft_propria
from transparencia_municipal.cliente import ErroPortal

URL = "https://exemplo.megasofttransparencia.com.br"
SENHA = f"{URL}/api/configuracao/carregamento-inicial"
FOLHA = f"{URL}/api/orgaos-e-servidores/servidor/paginado"
EMPENHOS = f"{URL}/api/receitas-e-despesas/empenho/paginado"


@pytest.fixture(autouse=True)
def _senhas_limpas():
    megasoft_propria._SENHAS.clear()
    yield
    megasoft_propria._SENHAS.clear()


def _servidor(i, **campos):
    return {"ano": 2025, "mes": "09", "mesAno": "09/2025", "matricula": i, "nome": f"PESSOA {i}",
            "cpf": "XXX.123.456-XX", "cargo": "AGENTE", "departamento": "SECRETARIA DE SAÚDE",
            "tipoDeVinculo": "Comissionado", "dataAdmissao": "02/01/2023", "dataExoneracao": "",
            "cargaHoraria": 40, "proventos": 3512.4, "descontos": 512.4, "totalLiquido": 3000.0,
            "situacao": "Ativo", "situacaoPagamento": "PAGO", "chave": {"matricula": i, "mesAno": "09/2025"},
            **campos}


def _empenho(codigo, documento="25.107.525/0001-51", nome="EMPRESA A LTDA", data="15/01/2025", **campos):
    return {"codigo": codigo, "data": data, "cnpjENomeDoFornecedor": f"{documento}/{nome}",
            "nomeDoFornecedor": nome, "historico": "MATERIAL", "valorDoEmpenho": 1000.0,
            "valorDaAnulacaoDoEmpenho": 0.0, "valorTotalDoEmpenho": 1000.0, "valorTotalDaLiquidacao": 800.0,
            "valorTotalDoPagamento": 500.0, **campos}


def _senhas(*senhas):
    """Cada visita a `carregamento-inicial` entrega a senha seguinte."""
    for senha in senhas:
        responses.add(responses.GET, SENHA, json={"cidade": "Exemplo", "tokenPortal": senha})


def _listagem(endereco, registros, *, senha="senha-1", total=None):
    """Simula a listagem paginada; só responde a quem traz os dois cabeçalhos obrigatórios e a senha válida."""
    def callback(requisicao):
        if requisicao.headers.get("Authorization") != f"Bearer {senha}":
            return 401, {}, '{"status":401,"error":"Unauthorized"}'
        if requisicao.headers.get("cliente-integrado") != "megasoft-portal-da-transparencia":
            return 400, {}, "{}"
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(requisicao.url).query))
        pagina, tamanho = int(q["pagina"]), int(q["tamanhoDaPagina"])
        lote = registros[(pagina - 1) * tamanho:pagina * tamanho]
        n = len(registros) if total is None else total
        return 200, {}, json.dumps({"paginaAtual": pagina, "registros": lote, "total": n})
    responses.add_callback(responses.GET, endereco, callback=callback, content_type="application/json")


def _consultas(endereco):
    return [dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(c.request.url).query))
            for c in responses.calls if c.request.url.startswith(endereco)]


@responses.activate
def test_folha_traduzida_com_fonte_e_senha_obtida_uma_vez_por_portal():
    _senhas("senha-1")
    _listagem(FOLHA, [_servidor(1), _servidor(2)])
    portal = Portal(URL, pausa=0)
    r = portal.folha(2025, 9)
    assert r["total"] == 2
    linha = r["registros"][0]
    assert linha["fonte"] == "Megasoft" and linha["matricula"] == "1"
    assert linha["lotacao"] == "SECRETARIA DE SAÚDE" and linha["total_proventos"] == "3.512,40"
    portal.folha(2025, 9)
    Portal(URL, pausa=0).folha(2025, 9)  # outro objeto, mesmo portal: a senha da memória serve
    assert len([c for c in responses.calls if c.request.url == SENHA]) == 1
    pedido = _consultas(FOLHA)[0]
    assert (pedido["ano"], pedido["mes"], pedido["pagina"]) == ("2025", "09", "1")
    cabecalhos = responses.calls[0].request.headers
    assert "mcp-transparencia-municipal" in cabecalhos["User-Agent"]  # identificação honesta do projeto


@responses.activate
def test_senha_recusada_com_401_e_renovada_e_a_consulta_repetida():
    _senhas("senha-vencida", "senha-1")
    _listagem(FOLHA, [_servidor(1)])  # só aceita a senha-1: a vencida leva 401
    r = Portal(URL, pausa=0).folha(2025, 9)
    assert r["total"] == 1 and r["registros"][0]["matricula"] == "1"
    assert len([c for c in responses.calls if c.request.url == SENHA]) == 2
    assert megasoft_propria._SENHAS[URL] == "senha-1"


@responses.activate
def test_senha_ilegivel_da_500_token_invalido_e_tambem_e_renovada():
    """Medido em Corumbaíba: senha que não é JWT válido leva 500 "Token inválido", não 401."""
    _senhas("senha-1")
    megasoft_propria._SENHAS[URL] = "x.y.z"
    responses.add(responses.GET, FOLHA, status=500, json={"status": 500, "message": "Token inválido: 'x.y.z'"})
    _listagem(FOLHA, [_servidor(1)])
    assert Portal(URL, pausa=0).folha(2025, 9)["total"] == 1


@responses.activate
def test_senha_que_continua_recusada_depois_de_renovar_vira_erro_claro():
    _senhas("senha-a", "senha-b")
    _listagem(FOLHA, [_servidor(1)], senha="outra")
    with pytest.raises(ErroPortal, match="HTTP 401"):
        Portal(URL, pausa=0).folha(2025, 9)


@responses.activate
def test_folha_em_varias_paginas_vem_inteira_e_avisa_o_progresso(monkeypatch):
    monkeypatch.setattr(megasoft_propria, "TAMANHO", 2)
    _senhas("senha-1")
    _listagem(FOLHA, [_servidor(i) for i in range(1, 6)])
    avisos = []
    r = Portal(URL, pausa=0).folha(2025, 9, maximo=10_000, progresso=lambda lidas, total: avisos.append((lidas, total)))
    assert r["total"] == 5 and [x["matricula"] for x in r["registros"]] == ["1", "2", "3", "4", "5"]
    assert avisos == [(2, 5), (4, 5), (5, 5)]
    assert [c["pagina"] for c in _consultas(FOLHA)] == ["1", "2", "3"]


@responses.activate
def test_registro_repetido_na_fronteira_de_pagina_conta_uma_vez_e_a_falta_fica_declarada(monkeypatch):
    """Fevereiro/2025 em Corumbaíba, páginas de 100: o total era 1.555 e vieram só 1.319 códigos distintos."""
    monkeypatch.setattr(megasoft_propria, "TAMANHO", 2)
    _senhas("senha-1")
    _listagem(FOLHA, [_servidor(1), _servidor(2), _servidor(2), _servidor(4)])  # o 3 se perdeu, o 2 repetiu
    r = Portal(URL, pausa=0).folha(2025, 9, maximo=10_000)
    assert [x["matricula"] for x in r["registros"]] == ["1", "2", "4"]
    assert r["total"] == 4  # o total anunciado fica: quem lê o mês vê 3 de 4 e declara "incompleta"


@responses.activate
def test_folha_por_nome_e_filtrada_pelo_projeto_sem_acento_nem_caixa():
    """Medido em Corumbaíba: `nome` e `filtro` não filtram no servidor; o total volta o do mês inteiro."""
    _senhas("senha-1")
    _listagem(FOLHA, [_servidor(1, nome="JOSÉ DA SILVA"), _servidor(2, nome="MARIA SOUZA"),
                      _servidor(3, nome="ANA JOSE PEREIRA")])
    r = Portal(URL, pausa=0).folha(2025, 9, "jose", maximo=1)
    assert r["total"] == 2 and [x["matricula"] for x in r["registros"]] == ["1"]


@responses.activate
def test_busca_por_nome_numa_leitura_que_nao_fechou_falha_em_vez_de_contar_menos():
    _senhas("senha-1")
    _listagem(FOLHA, [_servidor(1, nome="JOSÉ")], total=2)
    with pytest.raises(ErroPortal, match="incompleta"):
        Portal(URL, pausa=0).folha(2025, 9, "JOSE")


@responses.activate
def test_despesas_do_periodo_traduzidas_com_fonte_ate_o_maximo():
    _senhas("senha-1")
    _listagem(EMPENHOS, [_empenho(10), _empenho(11, "11.222.333/0001-81", "OUTRA SA", "20/01/2025")])
    r = Portal(URL, pausa=0).despesas("2025-01-01", "2025-01-31", maximo=1)
    assert r["total"] == 2
    assert r["registros"] == [{"empenho": 10, "data": "15/01/2025", "cpf_cnpj": "25.107.525/0001-51",
                               "fornecedor": "EMPRESA A LTDA", "valor_empenhado": "1.000,00",
                               "valor_liquidado": "800,00", "valor_pago": "500,00", "historico": "MATERIAL",
                               "orgao": None, "fonte": "Megasoft"}]
    pedido = _consultas(EMPENHOS)[0]
    assert (pedido["dataInicial"], pedido["dataFinal"]) == ("01/01/2025", "31/01/2025")


@responses.activate
def test_despesas_por_cnpj_trazem_so_esse_cnpj_mesmo_se_o_servidor_nao_filtrar():
    """Corumbaíba filtra por `cnpjDoFornecedor` (medido); o projeto manda o filtro e confere cada registro."""
    _senhas("senha-1")
    _listagem(EMPENHOS, [_empenho(10), _empenho(11, "11.222.333/0001-81", "OUTRA SA"), _empenho(12)])
    r = Portal(URL, pausa=0).despesas("2025-01-01", "2025-03-31", "25107525000151", maximo=100)
    assert r["total"] == 2 and [x["empenho"] for x in r["registros"]] == [10, 12]
    assert {x["cpf_cnpj"] for x in r["registros"]} == {"25.107.525/0001-51"}
    assert _consultas(EMPENHOS)[0]["cnpjDoFornecedor"] == "25.107.525/0001-51"


@responses.activate
def test_despesas_por_nome_do_fornecedor_sao_filtradas_pelo_projeto():
    """AJE: `nomeFornecedor` não filtra no servidor."""
    _senhas("senha-1")
    _listagem(EMPENHOS, [_empenho(10), _empenho(11, "11.222.333/0001-81", "OUTRA SA")])
    r = Portal(URL, pausa=0).despesas("2025-01-01", "2025-03-31", "outra", maximo=100)
    assert r["total"] == 1 and r["registros"][0]["fornecedor"] == "OUTRA SA"


@responses.activate
def test_resposta_sem_registros_nem_total_vira_erro_claro():
    _senhas("senha-1")
    responses.add(responses.GET, EMPENHOS, body="<html>manutenção</html>")
    with pytest.raises(ErroPortal, match="resposta inesperada"):
        Portal(URL, pausa=0).despesas("2025-01-01", "2025-01-31")


# ── ferramentas MCP, por um cliente MCP no mesmo processo ─────────────────────────────────────────────────────────

def _chamar(ferramenta, **argumentos):
    """Chama a ferramenta como um assistente chamaria e devolve o que ele recebe."""
    import anyio
    from mcp import Client

    from transparencia_municipal import servidor_mcp

    async def rodar():
        async with Client(servidor_mcp.mcp) as cliente:
            r = await cliente.call_tool(ferramenta, argumentos)
            return json.loads(r.content[0].text)
    servidor_mcp._LEITURAS.clear()
    try:
        return anyio.run(rodar)
    finally:
        servidor_mcp._LEITURAS.clear()


@responses.activate
def test_mcp_resumir_folha_de_um_portal_megasoft_proprio():
    _senhas("senha-1")
    _listagem(FOLHA, [_servidor(1), _servidor(2),
                      _servidor(3, departamento="SECRETARIA DE EDUCAÇÃO", proventos=2000, totalLiquido=1800.5)])
    r = _chamar("resumir_folha", ano=2025, mes=9, portal=URL)
    assert "erro" not in r, r
    assert r["total_do_mes"] == 3
    (tipo, resumo), = r["por_tipo_de_pagamento"].items()
    assert "não traz 13º" in tipo
    assert (resumo["linhas"], resumo["matriculas"], resumo["bruto"], resumo["liquido"]) == (3, 3, 9024.8, 7800.5)
    assert [(g["grupo"], g["linhas"], g["bruto"]) for g in resumo["grupos"]] == [
        ("SECRETARIA DE SAÚDE", 2, 7024.8), ("SECRETARIA DE EDUCAÇÃO", 1, 2000.0)]
    assert "PESSOA" not in str(r)  # resumo sem nomes


@responses.activate
def test_mcp_resumir_folha_megasoft_que_nao_fechou_declara_incompleta():
    _senhas("senha-1")
    _listagem(FOLHA, [_servidor(1), _servidor(2)], total=3)
    r = _chamar("resumir_folha", ano=2025, mes=9, portal=URL)
    assert "incompleta" in r["erro"] and "2 de 3" in r["erro"]


@responses.activate
def test_mcp_consultar_despesas_por_cnpj_num_portal_megasoft_proprio():
    _senhas("senha-1")
    _listagem(EMPENHOS, [_empenho(10), _empenho(11, "11.222.333/0001-81", "OUTRA SA"),
                         _empenho(12, data="10/02/2025")])
    r = _chamar("consultar_despesas", de="2025-01-01", ate="2025-03-31", busca="25.107.525/0001-51", portal=URL)
    assert "erro" not in r, r
    assert r["total"] == 2 and [x["empenho"] for x in r["registros"]] == [10, 12]
    assert {(x["cpf_cnpj"], x["fonte"]) for x in r["registros"]} == {("25.107.525/0001-51", "Megasoft")}
    assert _consultas(EMPENHOS)[0]["dataFinal"] == "31/03/2025"


@responses.activate
def test_empenhos_sem_codigo_nao_se_juntam_num_so():
    """Sem a chave, repetido é o registro inteiro: dois empenhos diferentes sem `codigo` continuam dois."""
    _senhas("senha-1")
    _listagem(EMPENHOS, [_empenho(None), _empenho(None, data="16/01/2025")])
    r = Portal(URL, pausa=0).despesas("2025-01-01", "2025-01-31")
    assert r["total"] == 2 and [x["data"] for x in r["registros"]] == ["15/01/2025", "16/01/2025"]
