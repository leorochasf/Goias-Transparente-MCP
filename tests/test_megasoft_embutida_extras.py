"""Megasoft embutida no NucleoGov: receitas, diárias, contratos e licitações (ticket 03 dos módulos extras).

Offline: página inicial e API simuladas como medido em Aruanã (04/11/2026):
- `megasoft/receitas`: paginação por `pagina`/`tamanhoDaPagina`, resposta `{total, registros, paginaAtual}`, `chave`
  com ano e mês;
- `sgdiarias/listar`, `contratos_mg/listar` e `licitacoes_mg/listarCidadao`: módulos do NucleoGov, paginados pelo
  `limit` do envelope, resposta `{dados, total}`;
- nos contratos, `txtbusca` zera a resposta e `objeto` filtra; nas licitações, `descricao` filtra e o período por
  data dá `error`.
"""
import json
import urllib.parse

import anyio
import pytest
import responses
from mcp import Client

from transparencia_municipal import Portal, catalogo, servidor_mcp
from transparencia_municipal.cliente import ErroPortal

pytestmark = pytest.mark.descobre_sufixos
PORTAL = "https://acessoainformacao.exemplo.go.gov.br"
PAGINA = ('<div class="nucleogov"><a href="x/mgreceitas">R</a><a href="x/contratos_mg">C</a>'
          '<a href="x/licitacoes_mg">L</a><a href="x/sgdiarias">D</a></div>')


def _pedido(requisicao):
    return next(iter(json.loads(urllib.parse.parse_qs(requisicao.body.decode())["params"][0]).items()))


def _portal(*, receitas=(), diarias=(), contratos=(), licitacoes=()):
    """Página inicial com os módulos embutidos, API NucleoGov sem `receitas`/`contratos`/`licitacoes` e os módulos
    embutidos respondendo. Devolve {acao: [corpos recebidos]}."""
    responses.add(responses.GET, f"{PORTAL}/", body=PAGINA)

    def vazio(requisicao):
        ident, _ = _pedido(requisicao)
        return 200, {}, json.dumps({ident: {"dados": [], "total": 0}})
    for modulo in ("receitas", "contratos", "licitacoes"):
        for sufixo in ("frl", "cnt"):
            responses.add_callback(responses.POST, f"{PORTAL}/api/{modulo}_{sufixo}/listar", callback=vazio,
                                   content_type="application/json")
    pedidos = {}

    def megasoft(acao, filtrar):
        def callback(requisicao):
            ident, corpo = _pedido(requisicao)
            pedidos.setdefault(acao, []).append(corpo)
            todos = filtrar(corpo)
            n, p = corpo["tamanhoDaPagina"], corpo["pagina"]
            return 200, {}, json.dumps({ident: {"total": len(todos), "registros": todos[(p - 1) * n:p * n],
                                                "paginaAtual": p}})
        return callback

    def nucleogov(acao, filtrar):
        def callback(requisicao):
            ident, corpo = _pedido(requisicao)
            pedidos.setdefault(acao, []).append(corpo)
            todos = filtrar(corpo)
            if isinstance(todos, dict):  # erro do sistema, como o período por data das licitações
                return 200, {}, json.dumps({ident: todos})
            inicio, n = (int(x) for x in corpo["limit"].split(","))
            return 200, {}, json.dumps({ident: {"dados": todos[inicio:inicio + n], "total": len(todos)}})
        return callback

    def das_receitas(corpo):
        return [r for r in receitas if r["chave"]["ano"] == int(corpo["ano"])]

    def das_diarias(corpo):
        achadas = [d for d in diarias if corpo["datamin"] <= d["data_inicio"] <= corpo["datamax"]]
        if corpo.get("txtbusca"):
            achadas = [d for d in achadas if corpo["txtbusca"].upper() in json.dumps(d, ensure_ascii=False).upper()]
        return [{**d, "total": str(len(achadas))} for d in achadas]  # `total` na linha é a contagem, não dinheiro

    def dos_contratos(corpo):
        if corpo.get("txtbusca"):
            return []  # medido: `txtbusca` zera a resposta dos contratos
        return [c for c in contratos if (not corpo.get("ano") or c["ano"] == int(corpo["ano"]))
                and corpo.get("objeto", "").upper() in c["objeto"].upper()]

    def das_licitacoes(corpo):
        if corpo.get("datapub_min") or corpo.get("datapub_max"):
            return {"error": "Houve um problema com a requisição", "total": 0}
        dispensa = {"DISPENSA DE LICITAÇÃO", "INEXIGIBILIDADE"}
        return [x for x in licitacoes if (not corpo.get("ano") or x["ano"] == int(corpo["ano"]))
                and (x["modalidade"] in dispensa) == bool(corpo["dispensas"])
                and corpo.get("descricao", "").upper() in x["descricao"].upper()]

    for acao, ler, filtrar in (("megasoft/receitas", megasoft, das_receitas),
                               ("sgdiarias/listar", nucleogov, das_diarias),
                               ("contratos_mg/listar", nucleogov, dos_contratos),
                               ("licitacoes_mg/listarCidadao", nucleogov, das_licitacoes)):
        responses.add_callback(responses.POST, f"{PORTAL}/api/{acao}", callback=ler(acao, filtrar),
                               content_type="application/json")
    return pedidos


def _receita(i, *, mes="09", orgao="MUNICIPIO DE EXEMPLO"):
    return {"chave": {"codigoDaReceita": 4700 + i, "ano": 2025, "mes": mes, "codigoDoOrgao": 3},
            "naturezaDaReceita": f"1112.50.0.{i} - IPTU - Principal", "receita": "IPTU - Principal",
            "fonteDaReceita": "1.500.000 - Recursos não Vinculados de Impostos", "origemDoRecurso": "Rendas Locais",
            "orgaoUnidadeGestora": orgao, "valorOrcado": 206358.92, "arrecadacao": 6146.78 + i,
            "valorAcumulado": 190145.09, "ano": 2025}


def _diaria(i, inicio, **campos):
    return {"tabela": "diarias", "orgao_nome": "FUNDO MUNICIPAL DE SAÚDE", "orgao_id": "6", "orgao": "6",
            "favorecido": f"PESSOA {i}", "cargo": "MOTORISTA", "data_inicio": inicio, "data_fim": inicio,
            "data_liquidacao": None, "destino": "GOIÂNIA", "cidade": None, "quantidade": "2", "valor": "1234.5",
            "numero_processo": None, "numero_empenho": None, "descricao": "LEVAR PACIENTE", "anexos": [],
            "chave": f"[{i}-1-1]", **campos}


def _contrato(i, *, ano=2025, objeto="AQUISIÇÃO DE COMBUSTÍVEL"):
    return {"id": 4000 + i, "label": f"Contrato {i}/{ano}", "orgao": 3, "licitacao_id": 8, "licitacao_label":
            "PREGÃO ELETRÔNICO 024/2025", "licitacao_label_short": "PREGÃO...", "licitacao_url": "x", "numero": str(i),
            "ano": ano, "situacao": "Vigente", "data_publicacao": "23/12/2025", "data_firmatura": "22/12/2025",
            "inicio_vigencia": "23/12/2025", "fim_vigencia": "23/02/2026", "fornecedor_nome": "POSTO EXEMPLO LTDA",
            "fornecedor_cpfcnpj": "25.107.525/0001-51", "objeto": objeto, "fiscal_contrato": "PESSOA FISCAL",
            "periodo": "2 meses", "valor": "501.902,40", "valor_executado": "1.000,00", "saldo": None,
            "local_da_execucao": None, "numero_colare": None, "data_colare": None, "coronavirus": 0, "anexos": []}


def _licitacao(i, modalidade="PREGÃO PRESENCIAL", *, ano=2025, descricao="MATERIAL DE LIMPEZA"):
    return {"chave": 8200 + i, "label": f"{i:03d}/{ano}", "modalidade": modalidade, "situacao": "Homologada",
            "situacao_id": None, "orgao": "MUNICIPIO DE EXEMPLO", "numero": str(i), "ano": ano,
            "data_publicacao": "01/12/2025", "data_julgamento": "10/12/2025", "data_homologacao": None,
            "data_abertura": None, "data_protocolo": None, "valor_vencedor_total": "7.543.339,30",
            "descricao": descricao}


# ── receitas ──────────────────────────────────────────────────────────────

@responses.activate
def test_receitas_do_mes_vem_com_os_nomes_comuns_e_a_ressalva_dos_orgaos():
    pedidos = _portal(receitas=[_receita(1), _receita(2, orgao="CÂMARA MUNICIPAL"), _receita(3)])
    r = Portal(PORTAL, pausa=0).receitas(2025, 9, maximo=2)
    assert r["total"] == 3 and len(r["registros"]) == 2
    assert r["registros"][0] == {
        "orgao": "MUNICIPIO DE EXEMPLO", "codigo": "1112.50.0.1", "receita": "IPTU - Principal",
        "fonte_recurso": "1.500.000 - Recursos não Vinculados de Impostos", "valor_orcado": "206.358,92",
        "valor_previsto_atualizado": None, "valor_arrecadado_mes": "6.147,78", "valor_arrecadado_ate_mes": "190.145,09",
        "ano": 2025, "mes": 9, "analitica": None, "fonte": "Megasoft"}
    assert any("órgão" in x for x in r["ressalvas"])
    assert [(p["ano"], p["mes"], p["pagina"], p["tamanhoDaPagina"]) for p in pedidos["megasoft/receitas"]] == [
        ("2025", "09", 1, 2)]


@responses.activate
def test_receitas_com_linha_de_outro_mes_sao_recusadas():
    _portal(receitas=[_receita(1), _receita(2, mes="12")])
    with pytest.raises(ErroPortal, match="outro mês"):
        Portal(PORTAL, pausa=0).receitas(2025, 9)


# ── diárias ───────────────────────────────────────────────────────────────

@responses.activate
def test_diarias_vem_pelo_sgdiarias_com_os_nomes_comuns_e_paginadas():
    pedidos = _portal(diarias=[_diaria(i, f"2025-01-{i:02d}") for i in range(1, 6)] + [_diaria(9, "2025-04-01")])
    p = Portal(PORTAL, pausa=0, por_pagina=2)
    r = p.diarias("2025-01-01", "2025-03-31", maximo=100)
    assert r["total"] == 5 and len(r["registros"]) == 5
    assert r["registros"][0] == {
        "favorecido": "PESSOA 1", "matricula": None, "cargo": "MOTORISTA", "orgao": "FUNDO MUNICIPAL DE SAÚDE",
        "destino": "GOIÂNIA", "motivo": "LEVAR PACIENTE", "data_saida": "01/01/2025", "data_chegada": "01/01/2025",
        "quantidade": "2", "valor": "1.234,50", "valor_unitario": None, "empenho": None, "fonte": "NucleoGov"}
    assert [(c["datamin"], c["datamax"], c["limit"]) for c in pedidos["sgdiarias/listar"]] == [
        ("2025-01-01", "2025-03-31", "0, 2"), ("2025-01-01", "2025-03-31", "2, 2"),
        ("2025-01-01", "2025-03-31", "4, 2")]
    assert "ressalvas" not in r


@responses.activate
def test_diarias_com_busca_vao_no_filtro_do_sistema_e_o_destino_vazio_cai_na_cidade():
    pedidos = _portal(diarias=[_diaria(1, "2025-01-10", destino=None, cidade="ANÁPOLIS", numero_empenho="77"),
                               _diaria(2, "2025-01-11")])
    r = Portal(PORTAL, pausa=0).diarias("2025-01-01", "2025-01-31", "anápolis")
    assert r["total"] == 1
    assert (r["registros"][0]["destino"], r["registros"][0]["empenho"]) == ("ANÁPOLIS", "77")
    assert pedidos["sgdiarias/listar"][0]["txtbusca"] == "anápolis"


@responses.activate
def test_diarias_com_quantidade_impossivel_ganham_ressalva():
    _portal(diarias=[_diaria(1, "2025-01-10", quantidade="657437"), _diaria(2, "2025-01-11")])
    r = Portal(PORTAL, pausa=0).diarias("2025-01-01", "2025-01-31")
    assert r["registros"][0]["quantidade"] == "657437"  # como o sistema dá
    assert any("1 diária" in x and "quantidade" in x for x in r["ressalvas"])


# ── contratos ─────────────────────────────────────────────────────────────

@responses.activate
def test_contratos_do_ano_vem_com_a_traducao_e_a_busca_vai_no_objeto():
    pedidos = _portal(contratos=[_contrato(1), _contrato(2, objeto="OBRA DE PAVIMENTAÇÃO"), _contrato(3, ano=2024)])
    p = Portal(PORTAL, pausa=0)
    r = p.contratos(2025)
    assert r["total"] == 2
    assert r["registros"][0] == {
        "numero": "1", "ano": 2025, "orgao": "3", "situacao": "Vigente", "objeto": "AQUISIÇÃO DE COMBUSTÍVEL",
        "fornecedor": "POSTO EXEMPLO LTDA", "cpf_cnpj": "25.107.525/0001-51", "valor": "501.902,40",
        "valor_executado": "1.000,00", "saldo": None, "data_publicacao": "23/12/2025", "data_assinatura": "22/12/2025",
        "inicio_vigencia": "23/12/2025", "fim_vigencia": "23/02/2026", "licitacao": "PREGÃO ELETRÔNICO 024/2025",
        "fiscal": "PESSOA FISCAL", "fonte": "Megasoft"}
    assert any("código" in x for x in r["ressalvas"])

    r = p.contratos(2025, busca="pavimenta")
    assert r["total"] == 1 and r["registros"][0]["numero"] == "2"
    assert any("objeto" in x for x in r["ressalvas"])
    assert pedidos["contratos_mg/listar"][-1].get("objeto") == "pavimenta"
    assert "txtbusca" not in pedidos["contratos_mg/listar"][-1]


@responses.activate
def test_contratos_sem_ano_trazem_todos_os_anos():
    pedidos = _portal(contratos=[_contrato(1), _contrato(3, ano=2024)])
    assert Portal(PORTAL, pausa=0).contratos()["total"] == 2
    assert "ano" not in pedidos["contratos_mg/listar"][0]


@responses.activate
def test_aditivos_da_embutida_sao_recusados_sem_consultar_o_modulo():
    pedidos = _portal(contratos=[_contrato(1)])
    with pytest.raises(ValueError, match="aditivo"):
        Portal(PORTAL, pausa=0).contratos(2025, tipo="aditivo")
    assert "contratos_mg/listar" not in pedidos


# ── licitações ────────────────────────────────────────────────────────────

@responses.activate
def test_licitacoes_do_ano_separam_dispensas_e_sempre_dizem_que_so_o_ano_filtra():
    pedidos = _portal(licitacoes=[_licitacao(1), _licitacao(2, "DISPENSA DE LICITAÇÃO"),
                                  _licitacao(3, "INEXIGIBILIDADE"), _licitacao(4, ano=2024)])
    p = Portal(PORTAL, pausa=0)
    r = p.licitacoes(ano=2025)
    assert r["total"] == 1
    assert r["registros"][0] == {
        "numero": "001/2025", "ano": 2025, "modalidade": "PREGÃO PRESENCIAL", "situacao": "Homologada",
        "orgao": "MUNICIPIO DE EXEMPLO", "objeto": "MATERIAL DE LIMPEZA", "data_publicacao": "01/12/2025",
        "data_abertura": None, "data_julgamento": "10/12/2025", "data_homologacao": None,
        "valor_vencedor": "7.543.339,30", "fonte": "Megasoft"}
    assert any("só filtram por ano" in x for x in r["ressalvas"])
    assert p.licitacoes(dispensas=True, ano=2025)["total"] == 2
    corpo = pedidos["licitacoes_mg/listarCidadao"][-1]
    assert (corpo["ano"], corpo["dispensas"], corpo["fracassadas_desertas"], corpo["abertas"]) == ("2025", 1, 0, 0)
    assert not any(k.startswith("datapub") for c in pedidos["licitacoes_mg/listarCidadao"] for k in c)


@responses.activate
def test_licitacoes_com_busca_vao_na_descricao():
    pedidos = _portal(licitacoes=[_licitacao(1), _licitacao(2, descricao="LOCAÇÃO DE MÁQUINAS")])
    r = Portal(PORTAL, pausa=0).licitacoes("locação", ano=2025)
    assert r["total"] == 1 and r["registros"][0]["numero"] == "002/2025"
    assert pedidos["licitacoes_mg/listarCidadao"][-1]["descricao"] == "locação"


# ── ponta a ponta, por cliente MCP no mesmo processo ─────────────────────

def _chamar(ferramenta, argumentos):
    async def rodar():
        async with Client(servidor_mcp.mcp) as cliente:
            r = await cliente.call_tool(ferramenta, argumentos)
            return json.loads(r.content[0].text)
    return anyio.run(rodar)


@responses.activate
def test_mcp_consultar_diarias_num_portal_embutido(monkeypatch):
    _portal(diarias=[_diaria(1, "2025-02-10"), _diaria(2, "2025-02-11", orgao_nome="CÂMARA MUNICIPAL")])
    monkeypatch.setattr(servidor_mcp, "_portal", lambda url=None: Portal(url or PORTAL, pausa=0))
    r = _chamar("consultar_diarias", {"de": "2025-02-01", "ate": "2025-02-28", "portal": PORTAL})
    assert "erro" not in r, r
    assert r["total"] == 2 and {x["fonte"] for x in r["registros"]} == {"NucleoGov"}
    assert r["registros"][0]["data_saida"] == "10/02/2025" and r["registros"][0]["valor"] == "1.234,50"
    assert "aviso_diarias" in r and "aviso_orgaos" in r and "aviso_leitura" not in r


@responses.activate
def test_mcp_receitas_e_licitacoes_da_embutida_trazem_as_ressalvas(monkeypatch):
    _portal(receitas=[_receita(1), _receita(2, orgao="CÂMARA MUNICIPAL")], licitacoes=[_licitacao(1)])
    monkeypatch.setattr(servidor_mcp, "_portal", lambda url=None: Portal(url or PORTAL, pausa=0))
    r = _chamar("consultar_receitas", {"ano": 2025, "mes": 9, "portal": PORTAL})
    assert "erro" not in r, r
    assert r["total"] == 2 and r["registros"][0]["fonte"] == "Megasoft"
    assert r["ressalvas"] and "aviso_orgaos" in r
    r = _chamar("consultar_licitacoes", {"ano": 2025, "portal": PORTAL})
    assert r["total"] == 1 and any("só filtram por ano" in x for x in r["ressalvas"])


@responses.activate
def test_mcp_receitas_pelo_catalogo_vao_a_megasoft_embutida(monkeypatch):
    """O catálogo diz `receitas: mg`; a API NucleoGov não serve o módulo; a resposta vem da Megasoft."""
    prefeitura = {"municipio": "Exemplo", "orgao": "prefeitura", "portal": PORTAL, "plataforma": "nucleogov-megasoft",
                  "sufixos": {"receitas": "mg"}, "outros_enderecos": [], "conferencia": None}
    monkeypatch.setattr(catalogo, "carregar", lambda: [prefeitura])
    _portal(receitas=[_receita(1)])
    r = servidor_mcp.consultar_receitas(2025, 9, portal=PORTAL)
    assert "erro" not in r, r
    assert r["total"] == 1 and r["registros"][0]["fonte"] == "Megasoft" and r["registros"][0]["mes"] == 9
