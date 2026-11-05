"""Sistema de gestão (SG) integrado ao NucleoGov (menus `sgservidores`, `sgdespesas`, `sgreceitas`). Offline.

O portal simulado segue o medido em Anápolis (05/11/2026): `POST /api/sg<modulo>/listar` no envelope `multi_request`,
paginado pelo `limit` do envelope, resposta `{dados, total}`; a API NucleoGov comum (`servidores_frl`...) responde zero.
- folha: `ano` + `mes` respeitados, uma linha por servidor (`chave` distinta);
- despesas: uma linha por movimento (Empenho, Liquidação, Pagamento); `tipo` 0 traz só os empenhos; `ano` +
  `datamin`/`datamax` (aaaa-mm-dd) recortam pela data; só com `ano`, o portal devolve o mês mais recente;
- receitas: `ano` + `mes`; todos os órgãos juntos; conta sem movimento no mês vem com `mes` nulo.
"""
import json
import urllib.parse
from datetime import date, datetime

import anyio
import pytest
import responses
from mcp import Client

from transparencia_municipal import Portal, servidor_mcp, sg
from transparencia_municipal.cliente import ErroPortal, ModuloNaoSuportado

pytestmark = pytest.mark.descobre_sufixos
PORTAL = "https://acessoainformacao.exemplo.go.gov.br"


def _pedido(requisicao):
    return next(iter(json.loads(urllib.parse.parse_qs(requisicao.body.decode())["params"][0]).items()))


def _portal_sg(*, servidores=(), movimentos=(), receitas=(), ignora_periodo=False):
    """Página inicial com os menus `sg*`, API NucleoGov comum vazia e o SG respondendo. Devolve os pedidos ao SG."""
    responses.add(responses.GET, f"{PORTAL}/", body=(
        '<div class="nucleogov"><a href="cidadao/transparencia/sgservidores">F</a>'
        '<a href="cidadao/transparencia/sgdespesas">D</a><a href="cidadao/transparencia/sgreceitas">R</a>'
        '<a href="cidadao/informacao/sgcontratos">C</a></div>'))

    def vazio(requisicao):
        ident, _ = _pedido(requisicao)
        return 200, {}, json.dumps({ident: {"dados": [], "total": 0}})
    for modulo in ("servidores", "despesas", "receitas", "contratos"):
        for sufixo in ("frl", "cnt"):
            responses.add_callback(responses.POST, f"{PORTAL}/api/{modulo}_{sufixo}/listar", callback=vazio,
                                   content_type="application/json")
    pedidos = []

    def sg(selecionar):
        def callback(requisicao):
            ident, corpo = _pedido(requisicao)
            pedidos.append(corpo)
            todos = selecionar(corpo)
            inicio, tamanho = (int(x) for x in corpo["limit"].split(","))
            return 200, {}, json.dumps({ident: {"total": str(len(todos)), "dados": todos[inicio:inicio + tamanho]}})
        return callback

    def da_folha(corpo):
        return [s for s in servidores if ignora_periodo or (s["ano"], s["mes"]) == (corpo["ano"], corpo["mes"])]

    def dos_movimentos(corpo):
        sel = [m for m in movimentos if corpo.get("tipo") in (None, m["tipo"])
               and (corpo.get("cpf_cnpj") is None or _digitos(corpo["cpf_cnpj"]) == _digitos(m["cpf_cnpj"]))]
        if ignora_periodo:
            return sel
        de, ate = (date.fromisoformat(corpo[c]) for c in ("datamin", "datamax"))
        return [m for m in sel if de <= datetime.strptime(m["data"], "%d/%m/%Y").date() <= ate]

    def das_receitas(corpo):
        return [r for r in receitas if ignora_periodo or (r["ano"] == corpo["ano"] and r["mes"] in (corpo["mes"], None))]

    for acao, selecionar in (("sgservidores", da_folha), ("sgdespesas", dos_movimentos),
                             ("sgreceitas", das_receitas)):
        responses.add_callback(responses.POST, f"{PORTAL}/api/{acao}/listar", callback=sg(selecionar),
                               content_type="application/json")
    return pedidos


def _digitos(documento):
    """O portal compara o CNPJ pelos dígitos (o filtro vai formatado; a resposta pode vir só com dígitos)."""
    return "".join(c for c in documento if c.isdigit()).zfill(14)


def _servidor(i, **campos):
    return {"chave": str(i), "matricula": str(i), "nome": f"PESSOA {i}", "cpf_mascarado": "***.000.000-**",
            "cargo": "Agente de Endemias", "lotacao": "Vigilância", "vinculo": "30 - Regime Jurídico Único",
            "orgao": None if i % 2 else "Fundo Municipal de Saúde", "data_admissao": "2007-05-01",
            "data_desligamento": None, "carga_horaria": "200 Horas Mensais", "tipo": "Folha Normal", "ano": "2025",
            "mes": "6", "proventos": "6066.55", "descontos": "1749.87", "liquido": "4316.68",
            "situacao_servidor": None, "total": "?", **campos}


def _movimento(empenho, data, tipo="0", cpf_cnpj="25.107.525/0001-51", fornecedor="EMPRESA EXEMPLO LTDA"):
    nome = {"0": "Empenho", "1": "Liquidação", "2": "Pagamento"}[tipo]
    return {"chave_empenho": str(empenho), "tipo": tipo, "movimento": nome, "empenho": f"E{empenho:06d}",
            "numero": f"E{empenho:06d}" if tipo == "0" else f"E{empenho:06d}.0001", "data": data, "ano": data[-4:],
            "orgao": "1", "orgao_empenho": "1", "cpf_cnpj": cpf_cnpj, "fornecedor": fornecedor,
            "descricao": "MATERIAL DE CONSUMO", "valor_empenho": "1.234,56", "valor_mov": "0,00", "valor": "1.234,56",
            "liquidado": "0,00", "acumulado_pagamento": "0,00"}


def _receita(codigo, mes="6", arrecadacao="100.5", orgao="Poder Executivo"):
    return {"codigo": codigo, "descricao": f"Receita {codigo}", "orgao_nome": orgao, "orgao_id": "1", "orgao": "1",
            "ano": "2025", "mes": mes, "valor_orcado": "1000", "valor_arrecado_mes": None,
            "valor_arrecado_periodo": "600.25", "arrecadacao": arrecadacao, "total": "?"}


# ── folha ─────────────────────────────────────────────────────────────────

@responses.activate
def test_folha_sg_vem_inteira_com_os_nomes_do_nucleogov_e_a_fonte(monkeypatch):
    monkeypatch.setattr(sg, "POR_PAGINA", 2)
    pedidos = _portal_sg(servidores=[_servidor(i) for i in range(1, 6)] + [_servidor(9, mes="7")])
    r = Portal(PORTAL, pausa=0).folha(2025, 6, maximo=1000)
    assert r["total"] == 5 and [x["matricula"] for x in r["registros"]] == ["1", "2", "3", "4", "5"]
    x = r["registros"][1]
    assert (x["total_proventos"], x["total_desconto"], x["total_liquido"]) == ("6.066,55", "1.749,87", "4.316,68")
    assert (x["cargo"], x["lotacao"], x["vinculo"], x["orgao"]) == (
        "Agente de Endemias", "Vigilância", "30 - Regime Jurídico Único", "Fundo Municipal de Saúde")
    assert x["data_admissao"] == "01/05/2007" and x["cpf"] == "***.000.000-**"
    assert "mensal" in x["tipo_folha"].lower() and "Folha Normal" in x["tipo_folha"]  # o resumo conta a linha
    assert x["fonte"] == "NucleoGov (sistema de gestão)"
    assert [(p["ano"], p["mes"], p["limit"]) for p in pedidos] == [
        ("2025", "6", "0, 2"), ("2025", "6", "2, 2"), ("2025", "6", "4, 2")]


@responses.activate
def test_folha_sg_com_linha_de_outro_mes_e_recusada():
    _portal_sg(servidores=[_servidor(1), _servidor(2, mes="5")], ignora_periodo=True)
    with pytest.raises(ErroPortal, match="outro mês"):
        Portal(PORTAL, pausa=0).folha(2025, 6)


@responses.activate
def test_folha_sg_por_nome_filtra_aqui_sobre_o_mes_inteiro():
    _portal_sg(servidores=[_servidor(i) for i in range(1, 6)] + [_servidor(7, nome="Fulána de Tal")])
    r = Portal(PORTAL, pausa=0).folha(2025, 6, "fulana", maximo=1)
    assert r["total"] == 1 and [x["matricula"] for x in r["registros"]] == ["7"]


# ── despesas ──────────────────────────────────────────────────────────────

@responses.activate
def test_despesas_sg_sao_os_empenhos_do_periodo_mes_a_mes():
    movimentos = [_movimento(1, "10/01/2025"), _movimento(1, "20/01/2025", "2"), _movimento(2, "28/02/2025"),
                  _movimento(3, "05/03/2025"), _movimento(4, "01/04/2025")]
    pedidos = _portal_sg(movimentos=movimentos)
    r = Portal(PORTAL, pausa=0).despesas("2025-01-15", "2025-03-31")
    assert r["total"] == 2 and [x["empenho"] for x in r["registros"]] == ["E000002", "E000003"]
    assert r["registros"][0] == {
        "empenho": "E000002", "data": "28/02/2025", "cpf_cnpj": "25.107.525/0001-51",
        "fornecedor": "EMPRESA EXEMPLO LTDA", "valor_empenhado": "1.234,56", "valor_liquidado": None,
        "valor_pago": None, "historico": "MATERIAL DE CONSUMO", "orgao": "1", "fonte": "NucleoGov (sistema de gestão)"}
    assert any("liquida" in x and "pagamento" in x for x in r["ressalvas"])
    assert [(p["ano"], p["datamin"], p["datamax"], p["tipo"]) for p in pedidos] == [
        ("2025", "2025-01-15", "2025-01-31", "0"), ("2025", "2025-02-01", "2025-02-28", "0"),
        ("2025", "2025-03-01", "2025-03-31", "0")]


@responses.activate
def test_despesas_sg_recusam_linha_fora_do_periodo_ou_que_nao_e_empenho():
    _portal_sg(movimentos=[_movimento(1, "10/01/2025"), _movimento(2, "04/11/2026")], ignora_periodo=True)
    with pytest.raises(ErroPortal, match="fora do período"):
        Portal(PORTAL, pausa=0).despesas("2025-01-01", "2025-01-31")


@responses.activate
def test_despesas_sg_por_cnpj_e_por_nome_do_fornecedor():
    outro = "11.364.935/0001-73"
    movimentos = [_movimento(1, "10/01/2025"), _movimento(2, "11/01/2025", cpf_cnpj=outro, fornecedor="OUTRA LTDA"),
                  _movimento(3, "05/02/2025", cpf_cnpj=outro, fornecedor="OUTRA LTDA")]
    pedidos = _portal_sg(movimentos=movimentos)
    r = Portal(PORTAL, pausa=0).despesas("2025-01-01", "2025-02-28", "11364935000173")
    assert r["total"] == 2 and [x["empenho"] for x in r["registros"]] == ["E000002", "E000003"]
    assert {p.get("cpf_cnpj") for p in pedidos} == {outro}

    r = Portal(PORTAL, pausa=0).despesas("2025-01-01", "2025-02-28", "outra")
    assert r["total"] == 2 and [x["empenho"] for x in r["registros"]] == ["E000002", "E000003"]


# ── receitas ──────────────────────────────────────────────────────────────

@responses.activate
def test_receitas_sg_do_mes_com_todos_os_orgaos_e_contas_sem_movimento():
    _portal_sg(receitas=[_receita("1.1.1"), _receita("1.1.2", mes=None, arrecadacao="0.00"),
                         _receita("1.7.1", orgao="Fundo Municipal de Saúde"), _receita("9.9.9", mes="5")])
    r = Portal(PORTAL, pausa=0).receitas(2025, 6)
    assert r["total"] == 3 and [x["codigo"] for x in r["registros"]] == ["1.1.1", "1.1.2", "1.7.1"]
    assert r["registros"][0] == {
        "orgao": "Poder Executivo", "codigo": "1.1.1", "receita": "Receita 1.1.1", "fonte_recurso": None,
        "valor_orcado": "1.000,00", "valor_previsto_atualizado": None, "valor_arrecadado_mes": "100,50",
        "valor_arrecadado_ate_mes": "600,25", "ano": 2025, "mes": 6, "analitica": None,
        "fonte": "NucleoGov (sistema de gestão)"}
    assert r["registros"][1]["valor_arrecadado_mes"] == "0,00"
    assert any("órgão" in x for x in r["ressalvas"])


@responses.activate
def test_receitas_sg_com_linha_de_outro_mes_sao_recusadas():
    _portal_sg(receitas=[_receita("1.1.1"), _receita("1.1.2", mes="11")], ignora_periodo=True)
    with pytest.raises(ErroPortal, match="outro mês"):
        Portal(PORTAL, pausa=0).receitas(2025, 6)


# ── módulo SG que o projeto ainda não lê: recusa clara, nunca zero ─────────

@responses.activate
def test_contratos_sg_sao_recusados_em_vez_de_responder_zero():
    _portal_sg()
    with pytest.raises(ModuloNaoSuportado, match="sistema de gestão"):
        Portal(PORTAL, pausa=0).contratos(2025)


# ── ponta a ponta, por cliente MCP no mesmo processo ─────────────────────

@responses.activate
def test_resumir_folha_num_portal_sg(monkeypatch):
    _portal_sg(servidores=[_servidor(i) for i in range(1, 6)])
    monkeypatch.setattr(servidor_mcp, "_portal", lambda url=None: Portal(url or PORTAL, pausa=0))
    servidor_mcp._LEITURAS.clear()

    async def rodar():
        async with Client(servidor_mcp.mcp) as cliente:
            r = await cliente.call_tool("resumir_folha", {"ano": 2025, "mes": 6, "agrupar_por": "cargo"})
            return json.loads(r.content[0].text)
    try:
        r = anyio.run(rodar)
    finally:
        servidor_mcp._LEITURAS.clear()
    assert "erro" not in r, r
    texto = json.dumps(r, ensure_ascii=False)
    assert "Agente de Endemias" in texto and "PESSOA" not in texto


@responses.activate
def test_despesas_sg_formatam_o_documento_que_vem_so_com_numeros_e_sem_os_zeros_a_esquerda():
    """Águas Lindas (05/11/2026): `cpf_cnpj` só com dígitos, e o zero à esquerda perdido (13 dígitos num CNPJ)."""
    movimentos = [_movimento(1, "10/01/2025", cpf_cnpj="25107525000151"),
                  _movimento(2, "11/01/2025", cpf_cnpj="1067081000100"),
                  _movimento(3, "12/01/2025", cpf_cnpj="1234567890")]
    pedidos = _portal_sg(movimentos=movimentos)
    r = Portal(PORTAL, pausa=0).despesas("2025-01-01", "2025-01-31")
    assert [x["cpf_cnpj"] for x in r["registros"]] == ["25.107.525/0001-51", "01.067.081/0001-00", "012.345.678-90"]

    r = Portal(PORTAL, pausa=0).despesas("2025-01-01", "2025-01-31", "25.107.525/0001-51")
    assert r["total"] == 1 and r["registros"][0]["cpf_cnpj"] == "25.107.525/0001-51"
    assert pedidos[-1]["cpf_cnpj"] == "25.107.525/0001-51"


@responses.activate
def test_erro_passageiro_na_sondagem_da_api_e_repetido_antes_de_recusar():
    """Portelândia (05/11/2026): menu `sgcontratos`, mas `contratos_cnt` serve 473. Uma falha passageira do `cnt`,
    com o `frl` respondendo zero, fazia o módulo ser recusado: a consulta que falha é repetida uma vez."""
    _portal_sg()
    responses.replace(responses.POST, f"{PORTAL}/api/contratos_cnt/listar", status=500, body="erro")

    def com_contratos(requisicao):
        ident, _ = _pedido(requisicao)
        return 200, {}, json.dumps({ident: {"total": 1, "dados": [{"numero": "1", "ano": "2025"}]}})
    responses.add_callback(responses.POST, f"{PORTAL}/api/contratos_cnt/listar", callback=com_contratos,
                           content_type="application/json")
    assert Portal(PORTAL, pausa=0).contratos(2025)["total"] == 1
