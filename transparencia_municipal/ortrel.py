"""Acesso às câmaras Ortrel (`transparencia.<câmara>.go.leg.br`). Encaixe do ticket 06; único arquivo dele, com a
tradução Ortrel → formato do projeto.

O `Portal` manda para cá o portal inteiro quando o catálogo diz `ortrel` ou a página inicial traz `/src/main.jsx`.
Interface, nomes comuns e marcas da resposta: ticket 01 dos módulos extras, seção `## Comments`. Consultas medidas:
docs/design/2026-11-04-modulos-extras.md, seção E da descoberta.

Medido em Cidade Ocidental (04/11/2026):
- `GET {portal}/src/services/api.js` traz `import.meta.env = {"API_URL": ..., "VITE_FIXED_TOKEN": ...}`; as chamadas
  levam `Origin`, `Referer` e `Authorization: Bearer <token>`;
- folha (6.046 linhas, 14 MB), diárias, contratos, licitações e leis vêm inteiros numa chamada, sem filtro: o recorte
  (mês, período, ano, busca) é feito aqui;
- despesas: `ano` e `mes` respeitados, páginas de 100 (`page`, `totalPages`), mesmo pedindo mais;
- o documento do credor pessoa física vem mascarado (`930******72`); o CNPJ de empresa vem completo;
- o 13º, as férias e a rescisão não têm linha própria na folha: são rubricas (`itens`) da linha do mês;
- leis: 217 pares (tipo, número) repetidos, quase todos leis diferentes de anos diferentes (a numeração recomeça);
  a repetida de verdade traz o mesmo ano no nome do ato e às vezes outro no campo `ano`.

Sem função aqui, o `Portal` recusa o módulo (receitas e detalhe do servidor: não medidos ou não existem).
"""
from __future__ import annotations

import collections as C
import json
import re
import time
import unicodedata
from datetime import date, datetime

import requests

from .cliente import ErroPortal, PortalBloqueou, _cnpj
from .traducao_megasoft import _br, _data

FONTE = "Ortrel"
#: endereço do portal → (API_URL, token ou None), lidos do `api.js` uma vez enquanto o processo vive
_ACESSOS: dict[str, tuple[str, str | None]] = {}
TIPO_PAGAMENTO = "Mensal (o 13º, as férias e a rescisão vêm como rubricas na mesma linha)"
RESSALVA_13 = ("Neste portal não há linha separada por tipo de pagamento: o 13º, as férias e as verbas de rescisão vêm "
               "como rubricas dentro da linha do mês.")
RESSALVA_DOCUMENTO = ("Neste portal o CPF do credor pessoa física vem mascarado (ex.: 123******45); o CNPJ de empresa vem "
                      "completo.")
DISPENSAS = ("DISPENSA", "INEXIGIBILIDADE")


def _acesso(portal, *, renovar=False):
    """(API_URL, token) do `api.js` do site."""
    if renovar or portal.url not in _ACESSOS:
        endereco = f"{portal.url}/src/services/api.js"
        try:
            r = portal.sessao.get(endereco, timeout=portal.timeout, headers={"User-Agent": portal.user_agent})
        except requests.RequestException as e:
            raise ErroPortal(f"não foi possível ler {endereco}: {e}") from e
        api = re.search(r'"API_URL"\s*:\s*"([^"]+)"', r.text) if r.status_code == 200 else None
        if not api:
            raise ErroPortal(f"{portal.url} não informou a API_URL em src/services/api.js (HTTP {r.status_code}): "
                             "o site Ortrel mudou ou não é Ortrel.")
        token = re.search(r'"VITE_FIXED_TOKEN"\s*:\s*"([^"]+)"', r.text)
        _ACESSOS[portal.url] = (api.group(1).rstrip("/"), token.group(1) if token else None)
    return _ACESSOS[portal.url]


def _get(portal, caminho, params=None):
    """O corpo JSON de `GET {API_URL}{caminho}`. Token recusado (401): relê o `api.js` uma vez e repete."""
    for renovar in (False, True):
        api, token = _acesso(portal, renovar=renovar)
        cabecalhos = {"User-Agent": portal.user_agent, "Origin": portal.url, "Referer": f"{portal.url}/"}
        if token:
            cabecalhos["Authorization"] = f"Bearer {token}"
        try:
            r = portal.sessao.get(f"{api}{caminho}", params=params, headers=cabecalhos, timeout=portal.timeout)
        except requests.RequestException as e:
            raise ErroPortal(f"não foi possível falar com {api}: {e}") from e
        if r.status_code != 401:
            break
    if r.status_code == 403:
        raise PortalBloqueou(f"{api} respondeu 403 em {caminho}.")
    if r.status_code != 200:
        raise ErroPortal(f"{api} respondeu HTTP {r.status_code} em {caminho}: {r.text[:200]}")
    try:
        return r.json()
    except ValueError as e:
        raise ErroPortal(f"{api} devolveu resposta inesperada em {caminho} "
                         f"({len(r.content)} bytes, começa com {r.text[:80]!r})") from e


def _lista(portal, caminho, chave, params=None):
    """A lista inteira de um módulo que vem sem filtro, página a página se `totalPages` passar de 1."""
    registros, pagina = [], 1
    while True:
        corpo = _get(portal, caminho, {**(params or {}), **({"page": pagina} if pagina > 1 else {})})
        lote = corpo.get(chave) if isinstance(corpo, dict) else None
        if not isinstance(lote, list):
            raise ErroPortal(f"{portal.url} devolveu resposta sem a lista `{chave}` em {caminho}")
        registros += lote
        if pagina >= int(corpo.get("totalPages") or 1):
            return registros
        pagina += 1
        time.sleep(portal.pausa)


def _simples(texto):
    """Sem acento e em maiúsculas, para as buscas."""
    return "".join(c for c in unicodedata.normalize("NFD", str(texto or "")) if not unicodedata.combining(c)).upper()


def _casa(busca, *campos):
    return _simples(busca) in " ".join(_simples(c) for c in campos)


def _dia(valor):
    """'2025-03-10' → date; vazio ou ilegível → None."""
    try:
        return datetime.strptime(str(valor or "")[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _decimal(texto):
    try:
        return round(float(texto or 0), 2)
    except (TypeError, ValueError):
        return None


def _resposta(registros, maximo, ressalvas=()):
    r = {"total": len(registros), "registros": registros[:maximo]}
    if ressalvas:
        r["ressalvas"] = list(ressalvas)
    return r


# ── folha ───────────────────────────────────────────────────────────────────────────────────────────────────────────

def _itens(reg):
    try:
        itens = json.loads(reg.get("itens") or "[]")
    except (TypeError, ValueError):
        return [], []
    proventos = [{"evento": None, "nome": i.get("nome_item"), "valor": _br(i.get("provento")), "tipo": "Provento"}
                 for i in itens if i.get("tipo") == "Proventos"]
    descontos = [{"evento": None, "nome": i.get("nome_item"), "valor": _br(i.get("desconto")), "tipo": "Desconto"}
                 for i in itens if i.get("tipo") == "Descontos"]
    return proventos, descontos


def linha_da_folha(reg):
    """Uma linha de `rh/folha_de_pagamento`, com os nomes de campo do NucleoGov e as rubricas."""
    proventos, descontos = _itens(reg)
    matricula = reg.get("matricula")
    return {
        "nome": reg.get("nome"), "matricula": None if matricula is None else str(matricula), "cpf": reg.get("cpf"),
        "cargo": reg.get("cargo"), "lotacao": reg.get("departamento"), "vinculo": reg.get("tipo_vinculo"),
        "tipo_folha": TIPO_PAGAMENTO, "data_admissao": reg.get("data_admissao"), "data_demissao": None,
        "carga_horaria": reg.get("carga_horaria"), "total_proventos": _br(reg.get("proventos")),
        "total_desconto": _br(reg.get("descontos")), "total_liquido": _br(reg.get("total_liquido")),
        "ano": reg.get("ano"), "mes": reg.get("mes"), "situacao": reg.get("situacao"),
        "orgao": reg.get("orgao"), "decreto": reg.get("decreto"), "data_decreto": reg.get("data_decreto"),
        "lista_proventos": proventos, "lista_descontos": descontos, "fonte": FONTE,
    }


def _rubricas_nao_batem(reg):
    try:
        itens = json.loads(reg.get("itens") or "[]")
    except (TypeError, ValueError):
        return True
    soma = round(sum(_decimal(i.get("provento")) or 0 for i in itens if i.get("tipo") == "Proventos"), 2)
    return abs(soma - (_decimal(reg.get("proventos")) or 0)) > 0.01


def folha(portal, *, ano, mes, busca, maximo, progresso=None):
    """Linhas da folha de `mes`/`ano` (int; `mes` None = o ano todo), recortadas da série inteira."""
    serie = _lista(portal, "/api/dados/rh/folha_de_pagamento", "folhaPagamento", {"limit": 100000, "page": 1})
    do_mes = [x for x in serie if str(x.get("ano")) == str(ano) and (mes is None or _int(x.get("mes")) == int(mes))]
    if progresso:
        progresso(len(do_mes), len(do_mes))
    ressalvas = [RESSALVA_13]
    divergentes = sum(1 for x in do_mes if _rubricas_nao_batem(x))
    if divergentes:
        ressalvas.append(f"Em {divergentes} das {len(do_mes)} linhas deste período, a soma das rubricas de proventos "
                         "não bate com o bruto publicado; os totais (bruto, descontos, líquido) são os do portal.")
    if busca:
        do_mes = [x for x in do_mes if _casa(busca, x.get("nome"))]
    return _resposta([linha_da_folha(x) for x in do_mes], maximo, ressalvas)


def _int(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


# ── despesas ────────────────────────────────────────────────────────────────────────────────────────────────────────

def despesa(reg):
    """Um empenho de `/api/dados/despesas`, no formato de despesas do projeto."""
    return {
        "empenho": None if reg.get("id_despesa") is None else str(reg["id_despesa"]), "data": _data(reg.get("data")),
        "cpf_cnpj": reg.get("cpf_cnpj_mascarado") or None, "fornecedor": reg.get("nome_fornecedor") or None,
        "valor_empenhado": _br(reg.get("valor_empenho")), "valor_liquidado": _br(reg.get("valor_liquidado")),
        "valor_pago": _br(reg.get("valor_total_pagamento")), "historico": reg.get("bem_servico_prestado"),
        "orgao": reg.get("orgao_unidade_gestora") or None, "fonte": FONTE,
    }


def _meses(de, ate):
    ano, mes = de.year, de.month
    while (ano, mes) <= (ate.year, ate.month):
        yield ano, mes
        ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)


def _empenhos_do_mes(portal, ano, mes):
    """Todos os empenhos de um mês, conferindo que cada um é do mês e que a leitura fechou com o total."""
    registros, pagina, total = [], 1, 0
    while True:
        corpo = _get(portal, "/api/dados/despesas", {"ano": ano, "mes": mes, "page": pagina, "limit": 100})
        lote = corpo.get("despesas") if isinstance(corpo, dict) else None
        if not isinstance(lote, list):
            raise ErroPortal(f"{portal.url} devolveu resposta sem a lista `despesas` ({mes:02d}/{ano})")
        total = int(corpo.get("total") or 0) if pagina == 1 else total
        registros += lote
        if not lote or pagina >= int(corpo.get("totalPages") or 1):
            break
        pagina += 1
        time.sleep(portal.pausa)
    fora = [x for x in registros if str(x.get("data") or "")[:7] != f"{ano}-{mes:02d}"]
    if fora:
        raise ErroPortal(f"{portal.url} devolveu {len(fora)} empenhos de outro mês ao pedir {mes:02d}/{ano}: "
                         "o filtro de mês foi ignorado; nada foi devolvido para não misturar períodos.")
    if len({x.get("id_despesa") for x in registros}) != total:
        raise ErroPortal(f"a leitura das despesas de {mes:02d}/{ano} em {portal.url} veio incompleta "
                         f"({len(registros)} de {total} empenhos). Tente de novo.")
    return registros


def _mascarado_de_cnpj(documento):
    """Documento com máscara e o tamanho de um CNPJ (14 posições): não dá para conferir."""
    v = re.sub(r"[./\-\s]", "", str(documento or ""))
    return "*" in v and len(v) == 14


def despesas(portal, *, de, ate, cnpj, busca, maximo):
    """Empenhos de `de` a `ate` (dd/mm/aaaa), lidos mês a mês. `cnpj` formatado ou None; `busca`: nome."""
    inicio, fim = (datetime.strptime(d, "%d/%m/%Y").date() for d in (de, ate))
    regs = []
    for n, (ano, mes) in enumerate(_meses(inicio, fim)):
        if n:
            time.sleep(portal.pausa)
        regs += [x for x in _empenhos_do_mes(portal, ano, mes) if inicio <= (_dia(x.get("data")) or inicio) <= fim]
    ressalvas = [RESSALVA_DOCUMENTO]
    if cnpj:
        sem_conferir = sum(1 for x in regs if _mascarado_de_cnpj(x.get("cpf_cnpj_mascarado")))
        if sem_conferir:
            ressalvas.append(f"{sem_conferir} empenho(s) do período têm o documento mascarado com tamanho de CNPJ e "
                             "não puderam ser conferidos com o CNPJ pedido (ficaram de fora).")
        regs = [x for x in regs if _cnpj(x.get("cpf_cnpj_mascarado") or "") == cnpj]
    elif busca:
        regs = [x for x in regs if _casa(busca, x.get("nome_fornecedor"))]
    return _resposta([despesa(x) for x in regs], maximo, ressalvas)


# ── contratos e licitações ──────────────────────────────────────────────────────────────────────────────────────────

def contrato(reg):
    """Um contrato de `/api/dados/todos-contratos`."""
    return {
        "id": None if reg.get("id") is None else str(reg["id"]), "numero": reg.get("numero_contrato"),
        "modalidade": reg.get("modalidade"), "licitacao": reg.get("numero_e_ano_licitacao"),
        "processo": reg.get("numero_processo"), "data_firmatura": _data(reg.get("data_assinatura")),
        "fim_vigencia": _data(reg.get("data_vigencia_fim")), "data_publicacao": _data(reg.get("data_publicacao")),
        "fornecedor_cpfcnpj": reg.get("cnpj_fornecedor"), "fornecedor_nome": reg.get("nome_fornecedor"), "objeto": reg.get("objeto"),
        "valor": _br(reg.get("valor_contratado")), "valor_aditado": _br(reg.get("valor_aditado")),
        "valor_total": _br(reg.get("valor_total")), "valor_executado": _br(reg.get("valor_executado")),
        "saldo": _br(reg.get("saldo")), "fiscal_contrato": reg.get("nome_fiscal"), "situacao": reg.get("situacao"),
        "ano": reg.get("exercicio_ano"), "orgao_nome": reg.get("nome_orgao"), "anexos": reg.get("anexos"), "fonte": FONTE,
    }


def contratos(portal, *, ano, tipo, busca, maximo):
    """Contratos do `ano` (exercício; int ou None); `busca` no número, objeto, fornecedor ou CNPJ."""
    if tipo != "contrato":
        raise ValueError("as câmaras Ortrel não publicam os aditivos em separado: cada contrato traz o valor_aditado "
                         "e os anexos; consulte tipo=\"contrato\".")
    regs = _lista(portal, "/api/dados/todos-contratos", "contratos")
    if ano:
        regs = [x for x in regs if str(x.get("exercicio_ano")) == str(ano)]
    if busca:
        regs = [x for x in regs if _casa(busca, x.get("numero_contrato"), x.get("objeto"), x.get("nome_fornecedor"),
                                         x.get("cnpj_fornecedor"))]
    return _resposta([contrato(x) for x in regs], maximo)


def _ano_da_licitacao(reg):
    dia = _dia(reg.get("data_publicacao")) or _dia(reg.get("data_protocolo"))
    return dia.year if dia else None


def licitacao(reg):
    """Uma licitação de `/api/dados/licitacoes`. `label` = número/ano; `numero`, a parte antes da barra (NucleoGov)."""
    label = reg.get("numero_ano")
    try:
        vencedores = json.loads(reg.get("itens_vencedores") or "[]")
    except (TypeError, ValueError):
        vencedores = reg.get("itens_vencedores")
    return {
        "id": reg.get("id_licitacao"), "numero": label.split("/")[0] if label else None, "label": label,
        "protocolo": reg.get("numero_protocolo"),
        "modalidade": reg.get("modalidade"), "situacao": reg.get("situacao"), "descricao": reg.get("descricao"),
        "data_protocolo": _data(reg.get("data_protocolo")), "data_abertura": _data(reg.get("data_abertura")),
        "data_homologacao": _data(reg.get("data_homologacao")), "data_publicacao": _data(reg.get("data_publicacao")),
        "valor_estimado": _br(reg.get("valor_estimado")), "valor_vencedor": _br(reg.get("valor_vencedor")),
        "itens_vencedores": vencedores, "orgao": reg.get("orgao"), "fonte": FONTE,
    }


def licitacoes(portal, *, busca, dispensas, ano, maximo):
    """Licitações (`dispensas` False) ou dispensas e inexigibilidades (True) do `ano` da publicação (int ou None)."""
    todas = _lista(portal, "/api/dados/licitacoes", "dados")
    regs = [x for x in todas if any(d in _simples(x.get("modalidade")) for d in DISPENSAS) == bool(dispensas)]
    if ano:
        regs = [x for x in regs if _ano_da_licitacao(x) == int(ano)]
    if busca:
        regs = [x for x in regs if _casa(busca, x.get("numero_ano"), x.get("numero_protocolo"), x.get("descricao"),
                                         x.get("modalidade_numero_ano"))]
    sem_data = sum(1 for x in todas if not x.get("data_publicacao"))
    ressalvas = ([f"{sem_data} licitação(ões) deste portal vieram sem data de publicação: o ano delas é o da data do "
                  "protocolo."] if sem_data else [])
    return _resposta([licitacao(x) for x in regs], maximo, ressalvas)


# ── diárias ─────────────────────────────────────────────────────────────────────────────────────────────────────────

def diaria(reg):
    """Uma diária de `/api/dados/rh/diarias`, com os nomes comuns de diárias."""
    return {
        "favorecido": reg.get("nome_funcionario") or None, "matricula": None,
        "cargo": reg.get("cargo_funcionario") or None, "orgao": None, "destino": reg.get("destino") or None,
        "motivo": reg.get("Histórico") or None, "data_saida": _data(reg.get("data_saida")),
        "data_chegada": _data(reg.get("data_chegada")), "quantidade": reg.get("numero_diarias") or None,
        "valor": _br(reg.get("valor_total")), "valor_unitario": _br(reg.get("valor_diaria")), "empenho": None,
        "fonte": FONTE,
    }


def _improvavel(reg, hoje):
    saida = _dia(reg.get("data_saida"))
    return saida is None or saida.year < 2000 or saida > hoje


def diarias(portal, *, de, ate, busca, maximo):
    """Diárias com saída de `de` a `ate` (`datetime.date`), recortadas da série inteira. `busca`: texto ou None."""
    serie = _lista(portal, "/api/dados/rh/diarias", "rhdiarias", {"limit": 1000})
    regs = [x for x in serie if (s := _dia(x.get("data_saida"))) and de <= s <= ate]
    if busca:
        regs = [x for x in regs if _casa(busca, x.get("nome_funcionario"), x.get("cargo_funcionario"),
                                         x.get("destino"), x.get("Histórico"))]
    ressalvas = ["Este portal entrega a série inteira das diárias, sem filtro de período: o recorte pela data de "
                 "saída é feito aqui."]
    estranhas = sorted(str(x.get("data_saida")) for x in serie if _improvavel(x, date.today()))
    if estranhas:
        ressalvas.append(f"{len(estranhas)} diária(s) da série têm data de saída improvável (ex.: {estranhas[0]}): "
                         "ficam fora de qualquer período razoável. Confira no portal.")
    return _resposta([diaria(x) for x in regs], maximo, ressalvas)


# ── legislação ──────────────────────────────────────────────────────────────────────────────────────────────────────

def _ano_do_ato(reg):
    """O ano escrito no nome do ato ("Lei 1471/2025", "de 14 de março de 2025"); sem ele, o campo `ano`."""
    anos = re.findall(r"(?:/|\bde\s)(\d{4})\b", str(reg.get("nome_ato") or ""))
    return int(anos[-1]) if anos else _int(reg.get("ano"))


def _especie(reg):
    """Emenda à Lei Orgânica e lei complementar vêm com tipo "Lei" e numeração própria: não são repetição da lei."""
    nome = _simples(reg.get("nome_ato"))
    return next((e for e in ("EMENDA", "COMPLEMENTAR") if e in nome), "")


def lei(reg):
    """Uma lei de `/api/dados/legislacao/leis_municipais`. `ano`: o do nome do ato, que vence o campo `ano`."""
    ano, no_portal = _ano_do_ato(reg), _int(reg.get("ano"))
    return {
        "id": None if reg.get("id") is None else str(reg["id"]), "tipo": reg.get("tipo"),
        "numero": None if reg.get("numero") is None else str(reg["numero"]), "ano": ano,
        **({"ano_no_portal": no_portal} if no_portal != ano else {}),
        "data_publicacao": _data(reg.get("data_publicacao")), "titulo": reg.get("nome_ato"),
        "ementa": reg.get("descricao"), "arquivo": reg.get("midia_arquivo_assinado"), "fonte": FONTE,
    }


def legislacao(portal, *, tipo, busca, ano, maximo):
    """Leis (o Ortrel só publica leis; `tipo` "LEI"), com `busca` no título e na ementa e `ano` (int ou None)."""
    if tipo != "LEI":
        raise ValueError(f"as câmaras Ortrel publicam só leis: use tipo=\"LEI\" (recebido: {tipo!r}).")
    unicas, repetidas = {}, 0
    for x in _lista(portal, "/api/dados/legislacao/leis_municipais", "leisMunicipais", {"limit": 1000, "page": 1}):
        chave = (_simples(x.get("tipo")), _especie(x), str(x.get("numero")), _ano_do_ato(x))
        if chave in unicas:
            repetidas += 1
            if _int(unicas[chave].get("ano")) != chave[-1] and _int(x.get("ano")) == chave[-1]:
                unicas[chave] = x  # fica a cópia cujo campo `ano` bate com o ano do ato
        else:
            unicas[chave] = x
    mesma_ementa = C.Counter((_especie(x), str(x.get("numero")), _simples(x.get("descricao")))
                             for x in unicas.values() if x.get("descricao"))
    suspeitas = sum(n - 1 for n in mesma_ementa.values() if n > 1)
    regs = [lei(x) for x in unicas.values()]
    if ano:
        regs = [x for x in regs if x["ano"] == int(ano)]
    if busca:
        regs = [x for x in regs if _casa(busca, x["titulo"], x["ementa"])]
    ressalvas = ([f"{repetidas} lei(s) vieram repetidas neste portal (mesmo número e ano, às vezes com outro ano no "
                  "campo `ano`): fica uma de cada. Mesmo número em anos diferentes são leis diferentes."]
                 if repetidas else [])
    if suspeitas:
        ressalvas.append(f"{suspeitas} lei(s) têm o mesmo número e a mesma ementa de outra lei de outro ano: podem ser "
                         "a mesma lei cadastrada de novo, com ano errado. Foram mantidas; confira no PDF (`arquivo`).")
    return _resposta(regs, maximo, ressalvas)
