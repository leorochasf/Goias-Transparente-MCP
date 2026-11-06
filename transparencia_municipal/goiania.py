"""Acesso aos sistemas próprios da Prefeitura de Goiânia: o TransWeb (despesas, receitas, contratos, licitações,
diárias) e o BSIT (folha). Também as despesas da Câmara de Goiânia, que estão no TransWeb.

O `Portal` manda para cá o portal inteiro quando a plataforma é `goiania` (endereço `goiania.go.gov.br`), e as despesas
de um portal NucleoGov com o sufixo `transweb` (a Câmara de Goiânia, cujo portal aponta o TransWeb).

Medido em 05/11/2026 (desenho e números em docs/design/2026-11-05-goiania.md):
- TransWeb (OutSystems): cada tela exporta CSV por um POST do formulário. A exportação das diárias devolve a última
  pesquisa, não o formulário: toda leitura faz "Pesquisar" e depois "Exportar", com os mesmos filtros. O valor das
  opções de mês muda de tela para tela: a escolha é pelo rótulo. As despesas trazem, no fim, as somas do próprio
  TransWeb, conferidas aqui;
- BSIT (JSF): "Gerar CSV" (Ajax) e depois o download; referência MM/AAAA; o nome filtra no próprio sistema.
"""
from __future__ import annotations

import calendar
import csv
import html
import io
import re
import time
from datetime import date
from decimal import Decimal, InvalidOperation

import requests

from .cliente import ErroPortal, ModuloNaoSuportado, PortalBloqueou
from .folha_leve import _comparavel
from .plataformas import _host
from .sg import _dia, _digitos, _meses
from .traducao_megasoft import _br

FONTE_BSIT = "BSIT (folha da Prefeitura de Goiânia)"
FONTE_TRANSWEB = "TransWeb (Prefeitura de Goiânia)"
TRANSWEB = "https://www10.goiania.go.gov.br/TransWeb/"
BSIT = "http://goiania.bsit-br.com.br/portal/employee-transparency-simplified.jsf"
#: tipo de folha "Folha Mensal" no BSIT (os outros: 13º, férias, sessão extraordinária, diferença, rescisão)
FOLHA_MENSAL = "1"


# ── rede ──────────────────────────────────────────────────────────────────────────────────────────────────────────

def _pedir(portal, metodo, url, data=None):
    try:
        r = portal.sessao.request(metodo, url, data=data, timeout=max(portal.timeout, 300),
                                  headers={"User-Agent": portal.user_agent})
    except requests.RequestException as e:
        raise ErroPortal(f"não foi possível falar com {url}: {e}") from e
    if r.status_code == 403:
        raise PortalBloqueou(f"{url} respondeu 403.")
    if r.status_code != 200:
        raise ErroPortal(f"{url} respondeu HTTP {r.status_code}: {r.text[:200]}")
    return r


def _texto(conteudo):
    """O arquivo em texto: UTF-8 (BSIT) ou cp1252 (TransWeb)."""
    try:
        return conteudo.decode("utf-8")
    except UnicodeDecodeError:
        return conteudo.decode("cp1252")


def _planilha(conteudo):
    """As linhas do CSV como dicionários, com o separador do cabeçalho (`;` no TransWeb, `,` nos contratos e no BSIT)."""
    texto = _texto(conteudo).replace("\r\n", "\n").lstrip("﻿")
    primeira = texto.split("\n", 1)[0]
    separador = ";" if primeira.count(";") >= primeira.count(",") else ","
    return list(csv.DictReader(io.StringIO(texto, newline=""), delimiter=separador))


def _limpo(valor):
    return (valor or "").replace(" ", " ").strip() or None


def _reais(valor):
    """'R$ 6.710,67' → '6.710,67'."""
    v = _limpo(valor)
    return re.sub(r"^R\$\s*", "", v) if v else None


# ── folha (BSIT) ──────────────────────────────────────────────────────────────────────────────────────────────────

def _linha_da_folha(reg, ano, mes):
    return {
        "nome": _limpo(reg.get("NOME")), "matricula": _limpo(reg.get("MATRICULA")), "cpf": None,
        "cargo": _limpo(reg.get("CARGO")), "lotacao": _limpo(reg.get("LOCAL_TRABALHO")),
        "vinculo": _limpo(reg.get("TIPO_ADMISSAO")), "tipo_folha": _limpo(reg.get("TIPO_FOLHA")),
        "data_admissao": _limpo(reg.get("DATA_ADMISSAO")),
        "data_demissao": _limpo(reg.get("DATA_EXONERACAO_INATIVACAO")),
        "carga_horaria": _limpo(reg.get("CARGA_HORARIA")), "salario_base": _reais(reg.get("SALARIO")),
        "total_proventos": _reais(reg.get("VALOR_PROVENTOS")), "total_desconto": _reais(reg.get("VALOR_DESCONTOS")),
        "total_liquido": _reais(reg.get("VALOR_LIQUIDO")), "ano": ano, "mes": mes, "orgao": None,
        "fonte": FONTE_BSIT,
    }


def folha(portal, *, ano, mes, busca, maximo, progresso=None):
    """A folha mensal de `mes`/`ano` (int). `busca`: nome do servidor, no filtro do próprio BSIT (conferido aqui)."""
    if mes is None:
        raise ValueError("a folha da Prefeitura de Goiânia é lida por mês: informe o mês")
    referencia = f"{mes:02d}/{ano}"
    pagina = _pedir(portal, "GET", BSIT).text
    acao = re.search(r'<form[^>]*id="employeeSearchForm"[^>]*action="([^"]+)"', pagina)
    estado = re.search(r'name="javax\.faces\.ViewState"[^>]*value="([^"]*)"', pagina)
    if not acao or not estado:
        raise ErroPortal(f"a página da folha do BSIT ({BSIT}) mudou: não achei o formulário de pesquisa")
    endereco = re.match(r"https?://[^/]+", BSIT).group(0) + html.unescape(acao.group(1))
    campos = {"employeeSearchForm": "employeeSearchForm", "employeeSearchForm:institutions": "",
              "employeeSearchForm:reference": referencia, "employeeSearchForm:registration": "",
              "employeeSearchForm:payrollTypeId": FOLHA_MENSAL, "employeeSearchForm:name": busca or "",
              "employeeSearchForm:position": "", "employeeSearchForm:admissionType": "",
              "employeeSearchForm:generateFile": "false", "javax.faces.ViewState": estado.group(1)}
    time.sleep(portal.pausa)
    gerado = _pedir(portal, "POST", endereco, {**campos, "AJAXREQUEST": "_viewRoot",
                                               "employeeSearchForm:generateCSV": "employeeSearchForm:generateCSV"})
    marca = re.search(r'id="employeeSearchForm:generateFile"[^>]*value="([^"]*)"', gerado.text)
    if not marca or marca.group(1) != "true":
        raise ErroPortal(f"o BSIT não gerou a planilha da folha de {referencia} (mês sem folha publicada ou "
                         "referência recusada pelo sistema)")
    time.sleep(portal.pausa)
    arquivo = _pedir(portal, "POST", endereco, {**campos, "employeeSearchForm:generateFile": "true",
                                                "employeeSearchForm:downloadAnalyticFile":
                                                    "employeeSearchForm:downloadAnalyticFile"})
    if "attachment" not in arquivo.headers.get("Content-Disposition", ""):
        raise ErroPortal(f"o BSIT não devolveu a planilha da folha de {referencia}")
    linhas = [_linha_da_folha(r, ano, mes) for r in _planilha(arquivo.content)]
    if busca:
        fora = [x for x in linhas if _comparavel(busca) not in _comparavel(x["nome"])]
        if fora:
            raise ErroPortal(f"o BSIT ignorou o filtro de nome na folha de {referencia}: {len(fora)} linha(s) sem o "
                             "nome pedido; nada foi devolvido.")
    return {"total": len(linhas), "registros": linhas[:maximo],
            "ressalvas": ["a folha do BSIT não traz o órgão de cada servidor: lotacao (o local de trabalho) diz onde "
                          "trabalha",
                          "folha mensal: o 13º, as férias e a rescisão são folhas separadas no BSIT, não lidas aqui"]}


# ── TransWeb ──────────────────────────────────────────────────────────────────────────────────────────────────────

MESES = ("Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro",
         "Novembro", "Dezembro")


def _tela(pagina):
    """(campos do formulário com os valores atuais, opções de cada lista, nome do botão "Pesquisar" (só nas diárias),
    nome do botão de exportar)."""
    campos, opcoes, pesquisar, exportar = {}, {}, None, None
    for m in re.finditer(r"<input[^>]*>", pagina):
        tag = m.group(0)
        nome, tipo, valor = (re.search(rf'{a}="([^"]*)"', tag) for a in ("name", "type", "value"))
        if not nome:
            continue
        nome, tipo = html.unescape(nome.group(1)), tipo.group(1) if tipo else "text"
        valor = html.unescape(valor.group(1)) if valor else ""
        if tipo == "submit" and valor == "Pesquisar":
            pesquisar = nome
        elif tipo == "submit" and nome.endswith("$wtbtnExportar"):
            exportar = nome
        elif tipo not in ("submit", "button", "checkbox", "image") and "disabled" not in tag:
            campos[nome] = valor
    for m in re.finditer(r'<select[^>]*name="([^"]+)"[^>]*>(.*?)</select>', pagina, re.S):
        itens = []
        for atributos, rotulo in re.findall(r"<option([^>]*)>(.*?)</option>", m.group(2), re.S):
            rotulo = html.unescape(re.sub(r"<[^>]+>", "", rotulo)).strip()
            valor = re.search(r'value="([^"]*)"', atributos)
            itens.append((html.unescape(valor.group(1)) if valor else rotulo, rotulo, "selected" in atributos))
        nome = html.unescape(m.group(1))
        opcoes[nome] = itens
        marcadas = [v for v, _, marcada in itens if marcada]
        campos[nome] = marcadas[0] if marcadas else (itens[0][0] if itens else "")
    return campos, opcoes, pesquisar, exportar


def _aplicar(campos, opcoes, filtros, pagina):
    """Põe os filtros (sufixo do campo → texto; nas listas, o rótulo da opção) nos campos do formulário."""
    for sufixo, texto in filtros.items():
        nomes = [n for n in campos if n.endswith("$" + sufixo)]
        if len(nomes) != 1:
            raise ErroPortal(f"a tela {pagina} do TransWeb mudou: não achei o filtro {sufixo}")
        nome = nomes[0]
        if nome in opcoes:
            valores = [v for v, rotulo, _ in opcoes[nome] if _comparavel(rotulo) == _comparavel(texto)]
            if not valores:
                raise ErroPortal(f"a tela {pagina} do TransWeb não tem a opção {texto!r} no filtro {sufixo}")
            campos[nome] = valores[0]
        else:
            campos[nome] = texto


def _exportar(portal, pagina, filtros):
    """(nome do arquivo, linhas do CSV) de uma tela do TransWeb com os `filtros`.

    Diárias: a exportação segue a última pesquisa, não o formulário; o botão "Pesquisar" (um envio comum do formulário)
    vem antes, com os mesmos filtros. Nas outras telas a pesquisa ("Buscar") só existe por Ajax, e enviada como
    formulário comum a tela volta sem o botão de exportar: a exportação vai direto, com o formulário (que as despesas,
    as receitas e os contratos respeitam; quem chama confere mês, ano e somas)."""
    url = TRANSWEB + pagina
    campos, opcoes, pesquisar, exportar = _tela(_pedir(portal, "GET", url).text)
    if pesquisar:
        _aplicar(campos, opcoes, filtros, pagina)
        time.sleep(portal.pausa)
        campos, opcoes, _, exportar = _tela(_pedir(portal, "POST", url, {**campos, pesquisar: "Pesquisar"}).text)
    if not exportar:
        raise ErroPortal(f"a tela {pagina} do TransWeb mudou: não achei o botão de exportar")
    _aplicar(campos, opcoes, {**filtros, "wtselExportar": "CSV"}, pagina)
    time.sleep(portal.pausa)
    r = _pedir(portal, "POST", url, {**campos, exportar: "OK"})
    disposicao = r.headers.get("Content-Disposition", "")
    if "attachment" not in disposicao:
        raise ErroPortal(f"o TransWeb não devolveu a planilha de {pagina} (veio {r.headers.get('Content-Type')})")
    nome = re.search(r'filename="?([^";]+)', disposicao)
    return (nome.group(1) if nome else ""), _planilha(r.content)


def _decimal(texto):
    """'1000,00' ou '6131894.82' → Decimal; vazio ou ilegível → zero."""
    v = _limpo(texto) or "0"
    if "," in v:
        v = v.replace(".", "").replace(",", ".")
    try:
        return Decimal(v)
    except InvalidOperation:
        return Decimal(0)


def _data(texto):
    """'25/09/2026 00:00:00' → '25/09/2026'."""
    v = _limpo(texto)
    return v[:10] if v else None


def _documento(texto):
    d = _digitos(texto)
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    return _limpo(texto)


# ── despesas ──────────────────────────────────────────────────────────────────────────────────────────────────────

#: portal NucleoGov cujas despesas estão no TransWeb → código do órgão (a tela fica presa a ele)
ORGAO_NO_TRANSWEB = {"camaragoiania.nucleogov.com.br": "01"}
#: linha de total no fim da planilha de despesas → soma (o "Total Empenhado" já vem sem o anulado)
TOTAIS = {"total empenhado": "empenhado", "total liquidado": "liquidado", "total pago": "pago"}


def _empenhos_do_mes(portal, pagina, inicio):
    """(empenhos emitidos no mês de `inicio`, cada um com as liquidações e os pagamentos até hoje; ressalva ou None).

    Confere o arquivo (o do mês pedido), a data de cada empenho e as somas contra os totais do próprio TransWeb: o
    liquidado e o pago bateram ao centavo nos 5 meses medidos (05/11/2026) e diferença neles é erro (planilha
    incompleta). O "Total Empenhado" bateu com o empenhado menos o anulado em 3 meses e ficou abaixo em 2 (06/2025:
    R$ 86.641,55; 12/2025: R$ 702.031,00), sem regra que os dados expliquem: a diferença vira ressalva."""
    ultimo = calendar.monthrange(inicio.year, inicio.month)[1]
    arquivo, linhas = _exportar(portal, pagina, {"wtcboMes": MESES[inicio.month - 1], "wtcboAno": str(inicio.year)})
    if f"{inicio:%Y%m}01_{inicio:%Y%m}{ultimo:02d}" not in arquivo:
        raise ErroPortal(f"o TransWeb devolveu a planilha {arquivo!r} ao pedir as despesas de {inicio:%m/%Y}: o filtro "
                         "de mês não foi respeitado; nada foi devolvido.")
    totais, empenhos = {}, {}
    for r in linhas:
        rotulo = _comparavel(_limpo(r.get("Empenho")))
        if rotulo in TOTAIS:
            totais[TOTAIS[rotulo]] = _decimal(r.get("VlEmpenhado"))
            continue
        if not _limpo(r.get("DataEmpenho")):  # o separador "-----" antes dos totais
            continue
        dia = _dia(_data(r.get("DataEmpenho")))
        if not dia or (dia.year, dia.month) != (inicio.year, inicio.month):
            raise ErroPortal(f"o TransWeb devolveu empenho de {_data(r.get('DataEmpenho'))}, fora de {inicio:%m/%Y}, "
                             "na planilha do mês: a resposta misturaria meses; nada foi devolvido.")
        e = empenhos.setdefault(r["Empenho"].strip(), {"linha": r, "dia": dia, "liquidacoes": {}, "pagamentos": {}})
        if _limpo(r.get("Liquidacao")):  # a linha é liquidação × pagamento: a liquidação se repete
            e["liquidacoes"][r["Liquidacao"].strip()] = _decimal(r.get("VlLiquidado"))
        if _limpo(r.get("OrdemPagamento")):
            e["pagamentos"][r["OrdemPagamento"].strip()] = _decimal(r.get("VlPago"))
    somas = _somas(empenhos.values())
    if set(totais) != set(TOTAIS.values()) or any(totais[k] != somas[k] for k in ("liquidado", "pago")):
        raise ErroPortal(f"as somas da planilha de despesas de {inicio:%m/%Y} não batem com os totais do próprio "
                         f"TransWeb (lidas: {somas}; do TransWeb: {totais}): a planilha pode ter vindo incompleta; "
                         "nada foi devolvido.")
    ressalva = None
    if totais["empenhado"] != somas["empenhado"]:
        ressalva = (f"em {inicio:%m/%Y}, o empenhado sem o anulado somado das linhas da planilha (R$ "
                    f"{_br(somas['empenhado'])}) difere do \"Total Empenhado\" do próprio TransWeb (R$ "
                    f"{_br(totais['empenhado'])}); o liquidado e o pago batem. A diferença não tem explicação nos dados: "
                    "confira no portal antes de usar o total empenhado")
    return list(empenhos.values()), ressalva


def _valores(e):
    r = e["linha"]
    return (_decimal(r.get("VlEmpenhado")), _decimal(r.get("VlAnulado")), sum(e["liquidacoes"].values(), Decimal(0)),
            sum(e["pagamentos"].values(), Decimal(0)))


def _somas(empenhos):
    somas = {"empenhado": Decimal(0), "liquidado": Decimal(0), "pago": Decimal(0)}
    for e in empenhos:
        empenhado, anulado, liquidado, pago = _valores(e)
        somas["empenhado"] += empenhado - anulado
        somas["liquidado"] += liquidado
        somas["pago"] += pago
    return somas


def _despesa(e):
    r = e["linha"]
    empenhado, anulado, liquidado, pago = _valores(e)
    return {
        "empenho": r["Empenho"].strip(), "data": _data(r.get("DataEmpenho")), "cpf_cnpj": _documento(r.get("CNPJ")),
        "fornecedor": _limpo(r.get("NmFavorecido")), "valor_empenhado": _br(empenhado), "valor_anulado": _br(anulado),
        "valor_liquidado": _br(liquidado), "valor_pago": _br(pago), "historico": _limpo(r.get("Objeto")),
        "orgao": _limpo(r.get("NmOrgao")), "natureza": _limpo(r.get("DsNaturezadaDespesa")),
        "modalidade": _limpo(r.get("Modalidade")), "licitacao": _limpo(r.get("NumeroLicitacao")),
        "fonte": FONTE_TRANSWEB,
    }


def despesas(portal, *, de, ate, cnpj, busca, maximo):
    """Empenhos emitidos de `de` a `ate` (dd/mm/aaaa), mês a mês, com liquidado e pago até hoje e as somas do período.
    `cnpj` (formatado) e `busca` (nome do favorecido) são filtrados aqui: o TransWeb não filtra por CNPJ."""
    inicio, fim = _dia(de), _dia(ate)
    orgao = ORGAO_NO_TRANSWEB.get(_host(portal.url))
    pagina = "Portal_Despesas.aspx" + (f"?orgao={orgao}" if orgao else "")
    achados, diferencas = [], []
    for i, (a, b) in enumerate(_meses(inicio, fim)):
        if i:
            time.sleep(portal.pausa)
        empenhos, ressalva = _empenhos_do_mes(portal, pagina, a)
        achados += [e for e in empenhos if a <= e["dia"] <= b]
        diferencas += [ressalva] if ressalva else []
    if cnpj:
        achados = [e for e in achados if _digitos(e["linha"].get("CNPJ")).zfill(14) == _digitos(cnpj)]
    if busca:
        achados = [e for e in achados if _comparavel(busca) in _comparavel(e["linha"].get("NmFavorecido"))]
    return {"total": len(achados), "registros": [_despesa(e) for e in achados[:maximo]],
            "somas_do_periodo": {k: _br(v) for k, v in _somas(achados).items()},
            "ressalvas": ["a lista traz os empenhos emitidos no período; valor_liquidado e valor_pago somam as "
                          "liquidações e os pagamentos de cada empenho até hoje, também os feitos depois do período "
                          "pedido",
                          "valor_anulado é a parte anulada do empenho; em somas_do_periodo o empenhado já vem sem o "
                          "anulado, e o liquidado e o pago foram conferidos, mês a mês, com os totais do próprio "
                          "TransWeb", *diferencas]}


# ── receitas ──────────────────────────────────────────────────────────────────────────────────────────────────────

def _receita(r, ano, mes):
    return {
        "orgao": None, "codigo": _limpo(r.get("Codigo")), "receita": _limpo(r.get("Natureza da Receita")),
        "fonte_recurso": None, "valor_orcado": _br(_decimal(r.get("Valor Previsto"))),
        "valor_previsto_atualizado": None, "valor_arrecadado_mes": _br(_decimal(r.get("Valor do Mês"))),
        "valor_arrecadado_ate_mes": _br(_decimal(r.get("Valor Acumulado"))), "ano": ano, "mes": mes,
        "analitica": None, "fonte": FONTE_TRANSWEB,
    }


def receitas(portal, *, ano, mes, maximo):
    """Receitas de `mes`/`ano` (int), de todos os órgãos da Prefeitura juntos."""
    arquivo, linhas = _exportar(portal, "Portal_Receitas.aspx", {"wtcboMes": MESES[mes - 1], "wtcboAno": str(ano)})
    if f"_{ano}_{mes}." not in arquivo:
        raise ErroPortal(f"o TransWeb devolveu a planilha {arquivo!r} ao pedir as receitas de {mes:02d}/{ano}: o filtro "
                         "de mês não foi respeitado; nada foi devolvido.")
    registros = [_receita(r, ano, mes) for r in linhas if _limpo(r.get("Codigo"))]
    return {"total": len(registros), "registros": registros[:maximo],
            "ressalvas": ["as receitas do TransWeb somam todos os órgãos da Prefeitura (fundos e autarquias "
                          "inclusive), sem separar por órgão",
                          "as deduções da receita vêm com valor negativo"]}


# ── contratos ─────────────────────────────────────────────────────────────────────────────────────────────────────

def _e_aditivo(r):
    return (_limpo(r.get("NumeroAditivo")) or "0") != "0"


def _contrato(r):
    firmatura = _data(r.get("DtFirmatura"))
    aditivo = _e_aditivo(r)
    return {
        "numero": _limpo(r.get("NrContratoAnoOrgao")), "numero_aditivo": _limpo(r.get("NumeroAditivo")) if aditivo
        else None, "ano": firmatura[-4:] if firmatura else None, "tipo": "Aditivo" if aditivo else "Contrato",
        "orgao_nome": _limpo(r.get("OrgaoExecutor")), "situacao": None, "objeto": _limpo(r.get("Descricao_Objeto")),
        "titulo": _limpo(r.get("TituloProjeto")), "fornecedor_nome": _limpo(r.get("NmContratado")),
        "fornecedor_cpfcnpj": None, "valor": _br(_decimal(r.get("ValorContrato"))),
        "data_publicacao": _data(r.get("DataPublicacao")), "data_firmatura": firmatura,
        "inicio_vigencia": _data(r.get("DtVigenciaIni")), "fim_vigencia": _data(r.get("DtVigenciaFim")),
        "fiscal_contrato": None, "processo": _limpo(r.get("NrProcessoSei")), "arquivo": _limpo(r.get("Arquivo")),
        "fonte": FONTE_TRANSWEB,
    }


def contratos(portal, *, ano, tipo, busca, maximo):
    """Contratos (tipo="contrato") ou aditivos firmados no `ano` (int ou None: todos). `busca`: objeto, título,
    contratado ou número, procurados aqui."""
    if tipo not in ("contrato", "aditivo"):
        raise ValueError(f"tipo={tipo!r}: use 'contrato' ou 'aditivo'")
    de, ate = (f"01/01/{ano}", f"31/12/{ano}") if ano else ("01/01/1900", f"{date.today():%d/%m/%Y}")
    _, linhas = _exportar(portal, "Portal_ContratoseConvenios.aspx", {"wtDtInicio": de, "wtDtFim": ate})
    linhas = [r for r in linhas if _limpo(r.get("NrContratoAnoOrgao")) or _limpo(r.get("NrTransparencia"))]
    fora = [r for r in linhas if ano and (_dia(_data(r.get("DtFirmatura"))) or date.min).year != ano]
    if fora:
        raise ErroPortal(f"o TransWeb devolveu {len(fora)} contrato(s) firmado(s) em outro ano ao pedir {ano} (ex.: "
                         f"{_data(fora[0].get('DtFirmatura'))}): a resposta misturaria anos; nada foi devolvido.")
    linhas = [r for r in linhas if _e_aditivo(r) == (tipo == "aditivo")]
    if busca:
        linhas = [r for r in linhas if _comparavel(busca) in _comparavel(" ".join(
            r.get(c) or "" for c in ("Descricao_Objeto", "TituloProjeto", "NmContratado", "NrContratoAnoOrgao")))]
    return {"total": len(linhas), "registros": [_contrato(r) for r in linhas[:maximo]],
            "ressalvas": ["a lista do TransWeb junta contratos e convênios, e o ano é o da firmatura",
                          "a planilha do TransWeb não traz o CNPJ do contratado, só o nome"]}


# ── licitações ────────────────────────────────────────────────────────────────────────────────────────────────────

def _verdadeiro(texto):
    return _comparavel(_limpo(texto)) == "true"


def _e_dispensa(r):
    modalidade = _comparavel(r.get("Modalidade_Forma"))
    return "dispensa" in modalidade or "inexigibilidade" in modalidade


def _licitacao(r):
    return {
        "numero": _limpo(r.get("Ano_Numero")), "label": None, "ano": _limpo(r.get("Ano")),
        "modalidade": _limpo(r.get("Modalidade_Forma")), "situacao": _limpo(r.get("Etapa")), "orgao": None,
        "descricao": _limpo(r.get("Objeto_Empresa")), "processo": None, "data_publicacao": None,
        "data_abertura": _data(r.get("Data_Abertura")), "data_homologacao": None,
        "valor_estimado": _reais(r.get("Valor_Estimado")), "valor_homologado": _reais(r.get("Valor_Homologado")),
        "julgamento": _limpo(r.get("Julgamento")), "sigilosa": _verdadeiro(r.get("StatSigiloso")),
        "fonte": FONTE_TRANSWEB,
    }


def licitacoes(portal, *, busca, dispensas, ano, maximo):
    """Licitações (ou só dispensas e inexigibilidades) do ano corrente (`ano` None ou o ano corrente; outro ano é
    recusado). `busca`: objeto, número ou modalidade, procurados aqui. As marcadas como excluídas ficam de fora.

    A exportação do TransWeb traz sempre o ano corrente: pedido 2025, o arquivo se chamava "Licitacoes_2025" e as 541
    linhas eram de 2026, mesmo depois da pesquisa por Ajax, que mostrava 2025 na tela (05/11/2026)."""
    corrente = date.today().year
    if ano and ano != corrente:
        raise ValueError(f"ano: o TransWeb da Prefeitura de Goiânia só exporta as licitações do ano corrente "
                         f"({corrente}); as de {ano} só aparecem na tela do portal "
                         f"({TRANSWEB}Portal_Licitacoes.aspx)")
    ressalvas = []
    if not ano:
        ano = corrente
        ressalvas.append(f"vieram as licitações do ano corrente ({ano}): o TransWeb só exporta as desse ano")
    _, linhas = _exportar(portal, "Portal_Licitacoes.aspx", {"wtcboAno": str(ano)})
    linhas = [r for r in linhas if _limpo(r.get("Ano_Numero"))]
    fora = [r for r in linhas if _limpo(r.get("Ano")) != str(ano)]
    if fora:
        raise ErroPortal(f"o TransWeb devolveu {len(fora)} licitação(ões) de outro ano ao pedir {ano} (ex.: "
                         f"{_limpo(fora[0].get('Ano'))}): a resposta misturaria anos; nada foi devolvido.")
    excluidas = [r for r in linhas if _verdadeiro(r.get("StatExclusao"))]
    if excluidas:
        ressalvas.append(f"{len(excluidas)} licitação(ões) marcada(s) como excluída(s) no TransWeb ficaram de fora")
    linhas = [r for r in linhas if not _verdadeiro(r.get("StatExclusao")) and _e_dispensa(r) == bool(dispensas)]
    if busca:
        linhas = [r for r in linhas if _comparavel(busca) in _comparavel(" ".join(
            r.get(c) or "" for c in ("Objeto_Empresa", "Ano_Numero", "Modalidade_Forma")))]
    sigilosas = sum(1 for r in linhas if _verdadeiro(r.get("StatSigiloso")))
    if sigilosas:
        ressalvas.append(f"{sigilosas} licitação(ões) com marca de sigilo no TransWeb (campo sigilosa)")
    return {"total": len(linhas), "registros": [_licitacao(r) for r in linhas[:maximo]], "ressalvas": ressalvas}


# ── diárias ───────────────────────────────────────────────────────────────────────────────────────────────────────

#: o filtro de valor das diárias vem com teto de R$ 10.000; a leitura o tira
SEM_TETO = "999999999"


def _diaria(r):
    return {
        "favorecido": _limpo(r.get("Servidor")), "matricula": None, "cargo": _limpo(r.get("Cargo")),
        "orgao": _limpo(r.get("Orgao")), "destino": _limpo(r.get("Destino")), "motivo": _limpo(r.get("Motivo")),
        "data_saida": _data(r.get("DataInicio")), "data_chegada": _data(r.get("DataFim")),
        "quantidade": _limpo(r.get("DiariasUsufruidas")), "valor": _br(_decimal(r.get("Valor"))) if _limpo(
            r.get("Valor")) else None, "valor_unitario": None, "empenho": None, "fonte": FONTE_TRANSWEB,
    }


def diarias(portal, *, de, ate, busca, maximo):
    """Diárias com saída de `de` a `ate` (`datetime.date`), mês a mês. `busca`: nome, cargo, destino ou motivo."""
    achados = []
    for i, (a, b) in enumerate(_meses(de, ate)):
        if i:
            time.sleep(portal.pausa)
        _, linhas = _exportar(portal, "Portal_DiariasPassagens.aspx",
                              {"wtcboMes": MESES[a.month - 1], "wtcboAno": str(a.year), "wtVlMax": SEM_TETO})
        for r in linhas:
            if not _limpo(r.get("DataInicio")):
                continue
            dia = _dia(_data(r.get("DataInicio")))
            if not dia or (dia.year, dia.month) != (a.year, a.month):
                raise ErroPortal(f"o TransWeb devolveu diária com saída em {_data(r.get('DataInicio'))}, fora de "
                                 f"{a:%m/%Y}: o filtro de mês pode ter sido ignorado; nada foi devolvido.")
            if a <= dia <= b:
                achados.append(_diaria(r))
    if busca:
        achados = [x for x in achados if _comparavel(busca) in _comparavel(" ".join(
            x[c] or "" for c in ("favorecido", "cargo", "destino", "motivo")))]
    return {"total": len(achados), "registros": achados[:maximo]}


# ── legislação ────────────────────────────────────────────────────────────────────────────────────────────────────

def legislacao(portal, **_):
    raise ModuloNaoSuportado(f"{portal.url}: a Prefeitura de Goiânia não publica a legislação em sistema consultável; "
                             "a legislação municipal está no portal da Câmara de Goiânia "
                             "(https://camaragoiania.nucleogov.com.br)")
