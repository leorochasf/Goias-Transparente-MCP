"""Prefeitura de Goiânia (TransWeb e BSIT) e despesas da Câmara de Goiânia, pelo `Portal`. Offline: os dois sistemas são
simulados no formato medido em 05/11/2026 (docs/design/2026-11-05-goiania.md):

- TransWeb: uma tela por módulo, formulário OutSystems (`__OSVSTATE`), botão "Pesquisar" e exportação CSV pelo botão
  `btnExportar`. A exportação devolve a ÚLTIMA PESQUISA (sem pesquisa, a lista padrão), como nas diárias reais; os
  valores das opções de mês mudam de tela para tela;
- BSIT: "Gerar CSV" é um POST Ajax que marca `generateFile`; o POST de `downloadAnalyticFile` devolve o CSV.
"""
import calendar
import csv
import io
import urllib.parse
from datetime import date
from decimal import Decimal

import pytest
import responses

from transparencia_municipal import Portal, catalogo, goiania
from transparencia_municipal.cliente import ErroPortal, ModuloNaoSuportado
from transparencia_municipal.plataformas import plataforma_pelo_endereco, reconhecer

PREFEITURA = "https://www.goiania.go.gov.br/transparencia"
CAMARA = "https://camaragoiania.nucleogov.com.br"
TW = "https://www10.goiania.go.gov.br/TransWeb/"
BSIT = "http://goiania.bsit-br.com.br/portal/employee-transparency-simplified.jsf"
MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro",
         "Novembro", "Dezembro"]


@pytest.fixture(autouse=True)
def _limpo(monkeypatch):
    monkeypatch.setattr(catalogo, "carregar", lambda: [])


def _portal(url=PREFEITURA, **kw):
    return Portal(url, pausa=0, **kw)


# ── simulador do BSIT ─────────────────────────────────────────────────────────────────────────────────────────────

FOLHA_CABECALHO = ["MATRICULA", "NOME", "CARGO", "LOCAL_TRABALHO", "TIPO_FOLHA", "TIPO_ADMISSAO", "CARGA_HORARIA",
                   "SALARIO", "VALOR_PROVENTOS", "VALOR_DESCONTOS", "VALOR_LIQUIDO", "DATA_ADMISSAO",
                   "DATA_EXONERACAO_INATIVACAO"]


def _servidor(matricula, nome="PESSOA A", vinculo="COMISSIONADO SEM VINCULO", liquido="R$ 3.795,04"):
    return [matricula, nome, "GERENTE (CDI-1)", "GERENCIA DE FINANCAS", "Folha Mensal", vinculo, "180h Mensal",
            "R$ 5.306,26", "R$ 6.710,67", "R$ 2.915,63", liquido, "24/06/2025", ""]


class Bsit:
    """O BSIT: guarda os campos do último "Gerar CSV" e devolve o CSV deles no download."""

    def __init__(self, linhas, *, gera=True, ignora_nome=False):
        self.linhas, self.gera, self.ignora_nome = linhas, gera, ignora_nome
        self.pedidos, self.ultimo = [], None
        responses.add(responses.GET, BSIT, body=self._pagina())
        responses.add_callback(responses.POST, f"{BSIT};jsessionid=ABC123", callback=self._post)

    @staticmethod
    def _pagina(gerar="false"):
        return ('<form id="employeeSearchForm" name="employeeSearchForm" method="post" '
                'action="/portal/employee-transparency-simplified.jsf;jsessionid=ABC123">'
                '<input id="employeeSearchForm:reference" type="text" name="employeeSearchForm:reference" '
                'value="10/2026" />'
                f'<input id="employeeSearchForm:generateFile" type="hidden" name="employeeSearchForm:generateFile" '
                f'value="{gerar}" />'
                '<input type="hidden" name="javax.faces.ViewState" id="javax.faces.ViewState" value="j_id1" /></form>')

    def _post(self, request):
        campos = {k: v[0] for k, v in urllib.parse.parse_qs(request.body, keep_blank_values=True).items()}
        self.pedidos.append(campos)
        if "AJAXREQUEST" in campos:
            self.ultimo = campos
            gera = self.gera and campos.get("employeeSearchForm:reference", "").startswith(("0", "1"))
            return 200, {}, f'<?xml version="1.0"?><html>{self._pagina("true" if gera else "false")}</html>'
        assert "employeeSearchForm:downloadAnalyticFile" in campos and self.ultimo, "download sem Gerar CSV antes"
        nome = self.ultimo.get("employeeSearchForm:name", "")
        linhas = [x for x in self.linhas if self.ignora_nome or nome.upper() in x[1].upper()]
        saida = io.StringIO()
        csv.writer(saida, lineterminator="\r\n").writerows([FOLHA_CABECALHO, *linhas])
        cabecalhos = {"Content-Type": "text/csv;charset=ISO-8859-1",
                      "Content-Disposition": 'attachment;filename="RELATORIO-DE-SERVIDOR.CSV"'}
        return 200, cabecalhos, saida.getvalue().encode("utf-8")


# ── plataforma ────────────────────────────────────────────────────────────────────────────────────────────────────

def test_a_prefeitura_de_goiania_e_reconhecida_pelo_endereco_mesmo_com_a_marca_nucleogov_na_pagina():
    assert plataforma_pelo_endereco(PREFEITURA) == "goiania"
    assert plataforma_pelo_endereco("https://goiania.go.gov.br/") == "goiania"
    assert plataforma_pelo_endereco("saude.goiania.go.gov.br") is None
    pagina = '<link href="https://file.nucleogov.com.br/webfonts/styles.css" />'  # o WordPress carrega fontes NucleoGov
    assert reconhecer(pagina, "www.goiania.go.gov.br") == {"plataforma": "goiania", "sufixos": {}}


def test_a_camara_que_aponta_as_despesas_do_transweb_ganha_o_sufixo_transweb():
    html = ('<div class="nucleogov"><a href="cidadao/transparencia/servidores_cnt">Folha</a>'
            '<a href="https://www10.goiania.go.gov.br/transweb/portal_despesas.aspx?orgao=01">Despesas</a></div>')
    assert reconhecer(html, CAMARA)["sufixos"] == {"servidores": "cnt", "despesas": "transweb"}


# ── folha (BSIT) ──────────────────────────────────────────────────────────────────────────────────────────────────

@responses.activate
def test_folha_do_mes_vem_do_bsit_com_o_vinculo_e_os_valores_sem_o_simbolo():
    bsit = Bsit([_servidor("204001"), _servidor("204002", vinculo="NOMEADO EFETIVO E ESTAVEL (CONCURSADO)")])
    r = _portal().folha(2026, 9)
    assert r["total"] == 2
    x = r["registros"][0]
    assert (x["matricula"], x["cargo"], x["lotacao"], x["vinculo"]) == (
        "204001", "GERENTE (CDI-1)", "GERENCIA DE FINANCAS", "COMISSIONADO SEM VINCULO")
    assert (x["total_proventos"], x["total_desconto"], x["total_liquido"]) == ("6.710,67", "2.915,63", "3.795,04")
    assert (x["ano"], x["mes"], x["fonte"], x["data_admissao"]) == (2026, 9, goiania.FONTE_BSIT, "24/06/2025")
    assert "Mensal" in x["tipo_folha"]
    gerar = bsit.pedidos[0]
    assert (gerar["employeeSearchForm:reference"], gerar["employeeSearchForm:payrollTypeId"],
            gerar["employeeSearchForm:name"], gerar["employeeSearchForm:institutions"]) == ("09/2026", "1", "", "")
    assert any("órgão" in s for s in r["ressalvas"])


@responses.activate
def test_busca_por_nome_vai_no_filtro_do_bsit():
    bsit = Bsit([_servidor("1", nome="ANA SOUZA"), _servidor("2", nome="BRUNO LIMA")])
    r = _portal().folha(2026, 9, "souza")
    assert [x["matricula"] for x in r["registros"]] == ["1"] and r["total"] == 1
    assert bsit.pedidos[0]["employeeSearchForm:name"] == "souza"


@responses.activate
def test_busca_por_nome_ignorada_pelo_bsit_e_erro():
    Bsit([_servidor("1", nome="ANA SOUZA"), _servidor("2", nome="BRUNO LIMA")], ignora_nome=True)
    with pytest.raises(ErroPortal, match="nome"):
        _portal().folha(2026, 9, "souza")


@responses.activate
def test_mes_sem_planilha_no_bsit_e_erro_que_diz_o_mes():
    Bsit([_servidor("1")], gera=False)
    with pytest.raises(ErroPortal, match="09/2026"):
        _portal().folha(2026, 9)


def test_folha_sem_mes_e_recusada():
    with pytest.raises(ValueError, match="mês"):
        _portal().folha(2026)


# ── simulador do TransWeb ─────────────────────────────────────────────────────────────────────────────────────────

P = "WebPatterns_wt2$block$wtMainContent$Blocos_wt1$block$"
EXPORTAR = [("__ossli_0", "Exportar"), ("__ossli_1", "XLS"), ("__ossli_2", "CSV"), ("__ossli_3", "JSON")]
SELECIONADA = ' selected="selected"'


def _opcoes_mes(estilo):
    """Os valores das opções de mês mudam de tela para tela (medido): só o rótulo é confiável."""
    valor = {"zero": lambda i: f"__ossli_{i:02d}", "sem_zero": lambda i: f"__ossli_{i}",
             "embaralhado": lambda i: str((i + 7) % 12 + 1)}[estilo]
    return [("__ossli_0", "Mês")] + [(valor(i), m) for i, m in enumerate(MESES, 1)]


ANOS = [("__ossli_0", "Ano")] + [(str(a), str(a)) for a in range(2026, 2014, -1)]


class TransWeb:
    """Uma tela do TransWeb. `gerar(filtros)` → linhas do CSV (cabeçalho primeiro).

    Diárias (`botao="Pesquisar"`, `segue_pesquisa`): "Pesquisar" guarda os filtros e a exportação devolve a última
    pesquisa (sem pesquisa, a dos filtros padrão), ignorando o formulário. Outras telas (`botao="Buscar"`): a pesquisa
    real é Ajax; enviada como formulário comum, a tela volta sem o botão de exportar (medido nas despesas), e a
    exportação segue o formulário enviado com ela."""

    def __init__(self, pagina, gerar, *, selects, textos=None, arquivo=lambda f: "Arquivo.csv", separador=";",
                 padrao=None, segue_pesquisa=False, botao="Buscar"):
        self.url, self.gerar, self.arquivo, self.separador = TW + pagina, gerar, arquivo, separador
        self.selects, self.textos, self.padrao = selects, textos or {}, padrao or {}
        self.segue_pesquisa, self.botao = segue_pesquisa, botao
        self.pesquisas, self.exportacoes, self.enderecos, self.estado = [], [], [], None
        for metodo in (responses.GET, responses.POST):
            responses.add_callback(metodo, self.url, callback=self._responder)

    def _html(self, exportar=True):
        partes = ['<form name="WebForm1" method="post" action="x" id="WebForm1">',
                  '<input type="hidden" name="__OSVSTATE" id="__OSVSTATE" value="estado123" />',
                  '<input type="hidden" name="__VIEWSTATE" id="__VIEWSTATE" value="" />']
        for sufixo, opcoes in {**self.selects, "wtselExportar": EXPORTAR}.items():
            itens = "".join(f'<option value="{v}"{SELECIONADA if i == 0 else ""}>{r}</option>'
                            for i, (v, r) in enumerate(opcoes))
            partes.append(f'<select name="{P}{sufixo}" id="{P.replace("$", "_")}{sufixo}">{itens}</select>')
        for sufixo, valor in self.textos.items():
            partes.append(f'<input name="{P}{sufixo}" type="text" value="{valor}" id="{sufixo}" />')
        partes.append(f'<input onclick="OsAjax(); return false;" type="submit" name="{P}wt103" '
                      f'value="{self.botao}" id="b1" />')
        partes.append(f'<input onclick="OsAjax(); return false;" type="submit" name="{P}wt104" value="Limpar" '
                      'id="b3" />')
        if exportar:
            partes.append(f'<input type="submit" name="{P}wtbtnExportar" value="OK" id="b2" style="display:none;" />')
        return "".join(partes) + "</form>"

    def _filtros(self, campos):
        filtros = {}
        for sufixo, opcoes in self.selects.items():
            valor = campos.get(P + sufixo)
            filtros[sufixo] = dict(opcoes).get(valor, valor)
        for sufixo in self.textos:
            filtros[sufixo] = campos.get(P + sufixo)
        return filtros

    def _responder(self, request):
        self.enderecos.append(request.url)
        if request.method == "GET":
            return 200, {}, self._html()
        campos = {k: v[0] for k, v in urllib.parse.parse_qs(request.body, keep_blank_values=True).items()}
        assert campos.get("__OSVSTATE") == "estado123"
        assert P + "wt104" not in campos, "apertou Limpar"
        if P + "wt103" in campos:
            assert campos[P + "wt103"] == self.botao
            if self.botao != "Pesquisar":  # "Buscar" é Ajax: como formulário comum, some o botão de exportar
                return 200, {}, self._html(exportar=False)
            self.estado = self._filtros(campos)
            self.pesquisas.append(self.estado)
            return 200, {}, self._html()
        assert campos.get(P + "wtbtnExportar") == "OK" and campos.get(P + "wtselExportar") == "__ossli_2"
        filtros = (self.estado or self.padrao) if self.segue_pesquisa else self._filtros(campos)
        self.exportacoes.append(filtros)
        saida = io.StringIO()
        csv.writer(saida, delimiter=self.separador, lineterminator="\r\n").writerows(self.gerar(filtros))
        cabecalhos = {"Content-Type": "application/text-stream",
                      "Content-Disposition": f'attachment; filename="{self.arquivo(filtros)}"'}
        return 200, cabecalhos, saida.getvalue().encode("cp1252")


def _mes_de(filtros):
    return MESES.index(filtros["wtcboMes"]) + 1


# ── despesas (TransWeb) ───────────────────────────────────────────────────────────────────────────────────────────

DESPESAS = ["Empenho", "DataEmpenho", "VlEmpenhado", "Liquidacao", "DataLiquidacao", "VlLiquidado", "OrdemPagamento",
            "DataPagamento", "VlPago", "NaturezaDespesa", "DsNaturezadaDespesa", "CNPJ", "NmOrgao", "VlAnulado",
            "UnidadeOrcamentaria", "Funcao", "SubFuncao", "FonteRecurso", "NmFavorecido", "Objeto", "Modalidade",
            "NumeroLicitacao"]
PREFEITURA_CNPJ, BANCO = "01612092000123", "00000000000191"


def _mov(empenho, data, empenhado, liq="", vliq="0,00", pag="", vpag="0,00", *, cnpj=PREFEITURA_CNPJ,
         favorecido="EMPRESA A LTDA", anulado="0,00", orgao="SECRETARIA MUNICIPAL DE GOVERNO"):
    return {"Empenho": empenho, "DataEmpenho": f"{data} 00:00:00", "VlEmpenhado": empenhado, "Liquidacao": liq,
            "DataLiquidacao": f"{data} 00:00:00" if liq else "", "VlLiquidado": vliq, "OrdemPagamento": pag,
            "DataPagamento": f"{data} 00:00:00" if pag else "", "VlPago": vpag, "NaturezaDespesa": "33903900",
            "DsNaturezadaDespesa": "OUTROS SERVICOS DE TERCEIROS - PESSOA JURIDICA", "CNPJ": cnpj, "NmOrgao": orgao,
            "VlAnulado": anulado, "UnidadeOrcamentaria": orgao + "   ", "Funcao": "ADMINISTRACAO - 04",
            "SubFuncao": "ADMINISTRACAO GERAL - 122", "FonteRecurso": "500", "NmFavorecido": favorecido,
            "Objeto": "SERVICOS DE LIMPEZA", "Modalidade": "Pregão", "NumeroLicitacao": "12/2026"}


def _valor(texto):
    return Decimal(texto.replace(".", "").replace(",", "."))


def _total(rotulo, valor):
    return {**dict.fromkeys(DESPESAS, ""), "Empenho": rotulo, "VlEmpenhado": f"{valor:.2f}".replace(".", ","),
            "VlLiquidado": "0", "VlPago": "0", "VlAnulado": "0"}


def _totais(movs, erro_no_empenhado=0, erro_no_pago=0):
    """As linhas de total do fim da planilha: empenhado (menos o anulado), liquidado e pago."""
    emp = {m["Empenho"]: _valor(m["VlEmpenhado"]) - _valor(m["VlAnulado"]) for m in movs}
    liq = {(m["Empenho"], m["Liquidacao"]): _valor(m["VlLiquidado"]) for m in movs if m["Liquidacao"]}
    pag = {(m["Empenho"], m["OrdemPagamento"]): _valor(m["VlPago"]) for m in movs if m["OrdemPagamento"]}
    return [_total("-" * 20, 0), _total("Total Empenhado", sum(emp.values()) + erro_no_empenhado),
            _total("Total Liquidado", sum(liq.values())), _total("Total Pago", sum(pag.values()) + erro_no_pago)]


def _despesas(por_mes, **erros):
    """`por_mes`: (ano, mes) → movimentos. A tela padrão é a de novembro de 2026."""
    def gerar(filtros):
        movs = por_mes.get((int(filtros["wtcboAno"]), _mes_de(filtros)), [])
        return [DESPESAS] + [[m[c] for c in DESPESAS] for m in movs + _totais(movs, **erros)]

    def arquivo(filtros):
        ano, mes = int(filtros["wtcboAno"]), _mes_de(filtros)
        return f"Despesas_{ano}{mes:02d}01_{ano}{mes:02d}{calendar.monthrange(ano, mes)[1]}.csv"

    return TransWeb("Portal_Despesas.aspx", gerar,
                    selects={"wtcboMes": _opcoes_mes("zero"), "wtcboAno": ANOS,
                             "wtcboFuncao": [("__ossli_0", "Função")]},
                    textos={"wtNmFavorecido": "", "wtNrEmpenho": ""}, arquivo=arquivo,
                    padrao={"wtcboMes": "Novembro", "wtcboAno": "2026"})


SETEMBRO = [
    _mov("20260101000010001", "01/09/2026", "1000,00", "L1", "600,00", "P1", "200,00", anulado="100,00"),
    _mov("20260101000010001", "01/09/2026", "1000,00", "L1", "600,00", "P2", "400,00", anulado="100,00"),
    _mov("20260101000010001", "01/09/2026", "1000,00", "L2", "300,00", "P3", "300,00", anulado="100,00"),
    _mov("20260101000010002", "10/09/2026", "500,00", cnpj=BANCO, favorecido="BANCO DO BRASIL SA"),
]


@responses.activate
def test_despesas_do_mes_sao_os_empenhos_com_liquidado_e_pago_ate_hoje_e_as_somas_do_transweb():
    tela = _despesas({(2026, 9): SETEMBRO})
    r = _portal().despesas("2026-09-01", "2026-09-30")
    assert tela.exportacoes == [{"wtcboMes": "Setembro", "wtcboAno": "2026", "wtcboFuncao": "Função",
                                 "wtNmFavorecido": "", "wtNrEmpenho": ""}]
    assert r["total"] == 2
    a, b = r["registros"]
    assert (a["empenho"], a["data"], a["valor_empenhado"], a["valor_anulado"], a["valor_liquidado"],
            a["valor_pago"]) == ("20260101000010001", "01/09/2026", "1.000,00", "100,00", "900,00", "900,00")
    assert (a["cpf_cnpj"], a["fornecedor"], a["historico"], a["orgao"], a["fonte"]) == (
        "01.612.092/0001-23", "EMPRESA A LTDA", "SERVICOS DE LIMPEZA", "SECRETARIA MUNICIPAL DE GOVERNO",
        goiania.FONTE_TRANSWEB)
    assert (a["modalidade"], a["licitacao"]) == ("Pregão", "12/2026")
    assert (b["cpf_cnpj"], b["valor_liquidado"], b["valor_pago"]) == ("00.000.000/0001-91", "0,00", "0,00")
    assert r["somas_do_periodo"] == {"empenhado": "1.400,00", "liquidado": "900,00", "pago": "900,00"}
    assert any("até hoje" in s for s in r["ressalvas"]) and any("anulado" in s for s in r["ressalvas"])


@responses.activate
def test_periodo_de_dois_meses_le_mes_a_mes_e_corta_pela_data_do_empenho():
    agosto = [_mov("20260101000009001", "15/08/2026", "10,00"), _mov("20260101000009002", "25/08/2026", "20,00")]
    tela = _despesas({(2026, 8): agosto, (2026, 9): SETEMBRO})
    r = _portal().despesas("2026-08-20", "2026-09-05")
    assert [x["empenho"] for x in r["registros"]] == ["20260101000009002", "20260101000010001"]
    assert [p["wtcboMes"] for p in tela.exportacoes] == ["Agosto", "Setembro"]
    assert r["somas_do_periodo"]["empenhado"] == "920,00"


@responses.activate
def test_cnpj_e_nome_do_favorecido_sao_filtrados_aqui():
    _despesas({(2026, 9): SETEMBRO})
    r = _portal().despesas("2026-09-01", "2026-09-30", "00.000.000/0001-91")
    assert [x["empenho"] for x in r["registros"]] == ["20260101000010002"]
    assert r["somas_do_periodo"] == {"empenhado": "500,00", "liquidado": "0,00", "pago": "0,00"}
    r = _portal().despesas("2026-09-01", "2026-09-30", "empresa a")
    assert [x["empenho"] for x in r["registros"]] == ["20260101000010001"]


@responses.activate
def test_pago_que_nao_bate_com_o_do_transweb_e_erro():
    _despesas({(2026, 9): SETEMBRO}, erro_no_pago=1)
    with pytest.raises(ErroPortal, match="somas"):
        _portal().despesas("2026-09-01", "2026-09-30")


@responses.activate
def test_empenhado_que_nao_bate_com_o_do_transweb_vira_ressalva_com_os_dois_valores():
    """Medido em 06/2025 e 12/2025: o "Total Empenhado" ficou abaixo do empenhado menos o anulado, sem explicação."""
    _despesas({(2026, 9): SETEMBRO}, erro_no_empenhado=-100)
    r = _portal().despesas("2026-09-01", "2026-09-30")
    assert r["total"] == 2 and r["somas_do_periodo"]["empenhado"] == "1.400,00"
    assert any("09/2026" in s and "1.400,00" in s and "1.300,00" in s for s in r["ressalvas"])


@responses.activate
def test_empenho_de_outro_mes_na_planilha_e_erro():
    _despesas({(2026, 9): SETEMBRO + [_mov("20260101000010009", "02/10/2026", "5,00")]})
    with pytest.raises(ErroPortal, match="fora"):
        _portal().despesas("2026-09-01", "2026-09-30")


@responses.activate
def test_despesas_da_camara_de_goiania_vem_do_transweb_preso_a_camara():
    tela = _despesas({(2026, 9): [_mov("20260101001910017", "05/09/2026", "58,00", orgao="CAMARA MUNICIPAL")]})
    r = _portal(CAMARA, sufixos={"despesas": "transweb", "servidores": "cnt"}).despesas("2026-09-01", "2026-09-30")
    assert [x["orgao"] for x in r["registros"]] == ["CAMARA MUNICIPAL"]
    assert tela.enderecos and all(u.endswith("Portal_Despesas.aspx?orgao=01") for u in tela.enderecos)


# ── receitas ──────────────────────────────────────────────────────────────────────────────────────────────────────

RECEITAS = ["Codigo", "Natureza da Receita", "Valor Previsto", "Valor do Mês", "Valor Acumulado", "CategoriaEconomica",
            "OrigemReceita", "EspecieReceita", "TipoReceita"]


def _receitas(*, arquivo=None):
    linhas = [["11125003", "IMPOSTO SOBRE A PROPRIEDADE PREDIAL", "115969000", "6131894.82", "57007967.38",
               "1 - RECEITAS CORRENTES", "11 - IMPOSTOS", "111 - IMPOSTOS", "1112 - IMPOSTOS SOBRE O PATRIMONIO"],
              ["917215201", "DEDUCAO DA COTA-PARTE", "1362000", "-131006.41", "-1154288.99", "", "", "", ""]]
    return TransWeb("Portal_Receitas.aspx", lambda f: [RECEITAS] + linhas,
                    selects={"wtcboMes": _opcoes_mes("sem_zero"), "wtcboAno": ANOS},
                    arquivo=arquivo or (lambda f: f"Receitas_{f['wtcboAno']}_{_mes_de(f)}.csv"))


@responses.activate
def test_receitas_do_mes_com_os_valores_do_transweb():
    tela = _receitas()
    r = _portal().receitas(2026, 9)
    assert tela.exportacoes[0]["wtcboMes"] == "Setembro" and tela.exportacoes[0]["wtcboAno"] == "2026"
    a, b = r["registros"]
    assert (a["codigo"], a["receita"], a["valor_orcado"], a["valor_arrecadado_mes"], a["valor_arrecadado_ate_mes"]) == (
        "11125003", "IMPOSTO SOBRE A PROPRIEDADE PREDIAL", "115.969.000,00", "6.131.894,82", "57.007.967,38")
    assert (a["ano"], a["mes"], a["fonte"]) == (2026, 9, goiania.FONTE_TRANSWEB)
    assert b["valor_arrecadado_mes"] == "-131.006,41"
    assert r["total"] == 2 and any("órgãos" in s for s in r["ressalvas"])


@responses.activate
def test_planilha_de_receitas_de_outro_mes_e_erro():
    _receitas(arquivo=lambda f: "Receitas_2026_11.csv")
    with pytest.raises(ErroPortal, match="mês"):
        _portal().receitas(2026, 9)


# ── contratos ─────────────────────────────────────────────────────────────────────────────────────────────────────

CONTRATOS = ["NrTransparencia", "NumeroContratoSCC", "NumeroAditivo", "OrgaoExecutor", "NrContratoAnoOrgao",
             "NmContratado", "TituloProjeto", "Descricao_Objeto", "DataPublicacao", "DtFirmatura", "DtVigenciaIni",
             "DtVigenciaFim", "NrProcessoSei", "ValorContrato", "Arquivo"]


def _contrato(numero, firmatura, aditivo="0", objeto="LIMPEZA URBANA"):
    return ["1089", "837173", aditivo, "EDUCACAO - SECRETARIA MUNICIPAL", numero, "EMPRESA B LTDA",
            "CONTRATO DE PRESTACAO DE SERVICOS", objeto, f"{firmatura} 00:00:00", f"{firmatura} 00:00:00",
            "02/09/2026 00:00:00", "01/09/2027 00:00:00", "26240000378414", "65492,82000000",
            "https://www10.goiania.go.gov.br/arquivo.pdf"]


def _contratos(linhas, *, respeita_datas=True):
    def gerar(f):
        de, ate = (sg_dia(f[k]) for k in ("wtDtInicio", "wtDtFim"))
        return [CONTRATOS] + [x for x in linhas if not respeita_datas or de <= sg_dia(x[9][:10]) <= ate]
    return TransWeb("Portal_ContratoseConvenios.aspx", gerar, separador=",",
                    selects={"wtcboTipo": [("__ossli_0", "Tipo (Todos)"), ("__ossli_1", "Contrato"),
                                           ("__ossli_2", "Aditivo")]},
                    textos={"wtDtInicio": "01/01/1900", "wtDtFim": "05/11/2026", "wttxtNmContratado": ""})


def sg_dia(texto):
    from datetime import datetime
    return datetime.strptime(texto, "%d/%m/%Y").date()


@responses.activate
def test_contratos_do_ano_pela_data_de_firmatura_sem_os_aditivos():
    tela = _contratos([_contrato("1768612026", "01/09/2026"), _contrato("1768612026", "15/10/2026", aditivo="1"),
                       _contrato("1500002025", "10/12/2025")])
    r = _portal().contratos(2026)
    assert (tela.exportacoes[0]["wtDtInicio"], tela.exportacoes[0]["wtDtFim"]) == ("01/01/2026", "31/12/2026")
    assert r["total"] == 1
    x = r["registros"][0]
    assert (x["numero"], x["tipo"], x["orgao_nome"], x["objeto"], x["fornecedor_nome"], x["valor"]) == (
        "1768612026", "Contrato", "EDUCACAO - SECRETARIA MUNICIPAL", "LIMPEZA URBANA", "EMPRESA B LTDA", "65.492,82")
    assert (x["data_firmatura"], x["inicio_vigencia"], x["fim_vigencia"], x["processo"], x["fonte"]) == (
        "01/09/2026", "02/09/2026", "01/09/2027", "26240000378414", goiania.FONTE_TRANSWEB)
    assert x["arquivo"].endswith(".pdf")
    aditivos = _portal().contratos(2026, tipo="aditivo")
    assert [(x["tipo"], x["numero_aditivo"]) for x in aditivos["registros"]] == [("Aditivo", "1")]


@responses.activate
def test_contrato_firmado_em_outro_ano_e_erro():
    _contratos([_contrato("1500002025", "10/12/2025")], respeita_datas=False)
    with pytest.raises(ErroPortal, match="outro ano"):
        _portal().contratos(2026)


@responses.activate
def test_busca_dos_contratos_procura_no_objeto_e_no_contratado():
    _contratos([_contrato("1", "01/09/2026", objeto="LIMPEZA URBANA"), _contrato("2", "02/09/2026", objeto="MERENDA")])
    assert [x["numero"] for x in _portal().contratos(2026, busca="merenda")["registros"]] == ["2"]
    assert len(_portal().contratos(2026, busca="empresa b")["registros"]) == 2


# ── licitações ────────────────────────────────────────────────────────────────────────────────────────────────────

LICITACOES = ["Modalidade_Forma", "Ano_Numero", "Julgamento", "Objeto_Empresa", "Data_Abertura", "Etapa",
              "Valor_Estimado", "Valor_Homologado", "LicitacaoId", "CampoOrdem", "NrSequencial", "StatSigiloso",
              "StatExclusao", "PessoaIdExclusao", "DataHoraExclusao", "MotivoExclusao", "OrgaoId", "modalidadeid", "Ano"]


def _licitacao(numero, modalidade="PREGÃO ELETRÔNICO - SME", ano="2025", excluida="False"):
    return [modalidade, f"{ano}/{numero}", "Menor preço", "AQUISICAO DE MERENDA", f"14/02/{ano} 00:00:00",
            "Finalizada", "R$ 1.000,00", "R$ 900,00", "1", "1", "1", "False", excluida, "", "", "", "166", "3", ano]


CORRENTE = str(date.today().year)


def _licitacoes(linhas):
    """A exportação real traz sempre o ano corrente, qualquer que seja o filtro (05/11/2026)."""
    anos = [(str(a), str(a)) for a in (2029, int(CORRENTE), int(CORRENTE) - 1)]
    return TransWeb("Portal_Licitacoes.aspx", lambda f: [LICITACOES] + [x for x in linhas if x[-1] == CORRENTE],
                    selects={"wtcboMes": _opcoes_mes("sem_zero"), "wtcboAno": anos},
                    arquivo=lambda f: f"Licitacoes_{f['wtcboAno']}__.csv")


@responses.activate
def test_licitacoes_do_ano_corrente_sem_as_dispensas_e_sem_as_excluidas():
    tela = _licitacoes([_licitacao("00000001", ano=CORRENTE),
                        _licitacao("00000002", modalidade="DISPENSA DE LICITAÇÃO - SMS", ano=CORRENTE),
                        _licitacao("00000003", excluida="True", ano=CORRENTE)])
    r = _portal().licitacoes(ano=int(CORRENTE))
    assert tela.exportacoes[0]["wtcboAno"] == CORRENTE
    assert [x["numero"] for x in r["registros"]] == [f"{CORRENTE}/00000001"]
    x = r["registros"][0]
    assert (x["modalidade"], x["situacao"], x["descricao"], x["data_abertura"], x["valor_estimado"],
            x["valor_homologado"], x["ano"], x["fonte"]) == (
        "PREGÃO ELETRÔNICO - SME", "Finalizada", "AQUISICAO DE MERENDA", f"14/02/{CORRENTE}", "1.000,00", "900,00",
        CORRENTE, goiania.FONTE_TRANSWEB)
    assert any("excluída" in s for s in r["ressalvas"])
    d = _portal().licitacoes(dispensas=True)
    assert [x["numero"] for x in d["registros"]] == [f"{CORRENTE}/00000002"]
    assert any("ano corrente" in s for s in d["ressalvas"])


def test_licitacoes_de_outro_ano_sao_recusadas_com_o_motivo():
    with pytest.raises(ValueError, match="ano corrente"):
        _portal().licitacoes(ano=int(CORRENTE) - 1)


# ── diárias ───────────────────────────────────────────────────────────────────────────────────────────────────────

DIARIAS = ["Servidor", "Orgao", "Cargo", "Tipo", "DataInicio", "DataFim", "DiariasUsufruidas", "Destino", "Esfera",
           "Motivo", "Valor"]


def _diaria(inicio, valor="193,00000000", nome="PESSOA C", destino="BRASILIA"):
    return [nome, "SECRETARIA MUNICIPAL DE SAUDE", "ASSESSOR", "Diária / Hospedagem", f"{inicio} 00:00:00",
            f"{inicio} 00:00:00", "1", destino, "Federal", "REUNIAO NO MINISTERIO", valor]


def _diarias(por_mes):
    def gerar(f):
        linhas = por_mes.get((int(f["wtcboAno"]), _mes_de(f)), [])
        return [DIARIAS] + [x for x in linhas if _valor(x[-1]) <= _valor(f["wtVlMax"])]
    anos = [(str(a), str(a)) for a in range(2026, 2014, -1)]
    return TransWeb("Portal_DiariasPassagens.aspx", gerar, segue_pesquisa=True, botao="Pesquisar",
                    selects={"wtcboMes": _opcoes_mes("embaralhado"), "wtcboAno": anos,
                             "wtcboOrgao": [("__ossli_0", "Órgãos")]},
                    textos={"wtSearchInput": "", "wtVlMin": "0", "wtVlMax": "10000"},
                    padrao={"wtcboMes": "Mês", "wtcboAno": "2026", "wtVlMax": "10000"},
                    arquivo=lambda f: "DiariasPassagens_0.csv")


@responses.activate
def test_diarias_pesquisam_o_mes_antes_de_exportar_sem_o_teto_de_valor():
    tela = _diarias({(2025, 9): [_diaria("05/09/2025"), _diaria("20/09/2025", valor="12000,00", destino="MANAUS"),
                                 _diaria("28/09/2025")]})
    r = _portal().diarias("2025-09-01", "2025-09-25")
    assert tela.pesquisas[0]["wtcboMes"] == "Setembro" and tela.pesquisas[0]["wtcboAno"] == "2025"
    assert [x["data_saida"] for x in r["registros"]] == ["05/09/2025", "20/09/2025"]
    x = r["registros"][1]
    assert (x["favorecido"], x["orgao"], x["cargo"], x["destino"], x["motivo"], x["quantidade"], x["valor"],
            x["data_chegada"], x["fonte"]) == ("PESSOA C", "SECRETARIA MUNICIPAL DE SAUDE", "ASSESSOR", "MANAUS",
                                               "REUNIAO NO MINISTERIO", "1", "12.000,00", "20/09/2025",
                                               goiania.FONTE_TRANSWEB)
    assert [x["destino"] for x in _portal().diarias("2025-09-01", "2025-09-30", "manaus")["registros"]] == ["MANAUS"]


@responses.activate
def test_diaria_de_outro_mes_na_planilha_e_erro():
    _diarias({(2025, 9): [_diaria("05/10/2025")]})
    with pytest.raises(ErroPortal, match="fora"):
        _portal().diarias("2025-09-01", "2025-09-30")


# ── legislação ────────────────────────────────────────────────────────────────────────────────────────────────────

def test_legislacao_da_prefeitura_aponta_a_camara():
    with pytest.raises(ModuloNaoSuportado, match="Câmara"):
        _portal().legislacao()
