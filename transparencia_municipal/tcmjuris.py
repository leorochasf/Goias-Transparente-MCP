"""TCMJuris do TCM-GO: acórdãos julgados desde 2020 e o texto do PDF. Desenho: docs/design/2026-11-04-tcm-go.md.

Encaixe do `ClienteTCM`: o cliente já resolveu o município e zerou o teto de chamadas.
"""
from __future__ import annotations

import io
import re
from urllib.parse import quote

from .tcm import FONTES, INSTALAR_PDF, ErroTCM, TetoAtingido

CAMINHO = "/v1/acordao/jurisprudencia"
POR_PAGINA = 100  # o máximo que a API aceita em page_size

#: chave devolvida → campo do TCMJuris. A ementa é escrita por IA: o nome da chave diz isso.
CAMPOS = {"document_id": "document_id", "numero_processo": "numero_processo", "numero_acordao": "numero_acordao",
          "data_sessao": "data_sessao", "ano": "ano_votacao", "assunto": "assunto", "macro_assunto": "macro_assunto",
          "resultado": "resultado", "entidade_fiscalizada": "entidade_fiscalizada",
          "orgao_julgador": "orgao_julgador", "tipo_processo": "tipo_processo", "relator": "conselheiro_relator",
          "ementa_ia": "ementa"}


def acordaos(cliente, *, municipio, texto, assunto, ano, relator, maximo, numero=None) -> dict:
    """Acórdãos. Devolve {"total", "registros"} (veja o ticket 01, seção Comments). `numero`: ver `_por_numero`."""
    filtros = {"texto": texto, "municipio": municipio, "assunto": assunto, "conselheiro": relator,
               "ano_votacao": ano}
    params = {k: v for k, v in filtros.items() if v not in (None, "")}
    if numero is not None:
        return _por_numero(cliente, params, numero, maximo)
    total, registros, incompleta = _buscar(cliente, params, maximo)
    saida = {"total": total, "registros": registros[:maximo]}
    if incompleta:
        saida["incompleta"] = incompleta
    return saida


#: número do processo ou do acórdão: NNNNN, NNNNN/AA ou NNNNN/AAAA (zeros à esquerda opcionais)
_NUMERO = re.compile(r"0*(\d{1,6})(?:/(\d{2}|\d{4}))?")
#: páginas lidas por filtro numa busca por número; passou disso, o número é curto demais e a leitura sai incompleta
PAGINAS_POR_NUMERO = 5


def numero_pedido(numero):
    """(número sem zeros, ano com 2 dígitos ou None). Fora do formato: ValueError, antes de consultar."""
    m = _NUMERO.fullmatch(str(numero or "").strip())
    if not m:
        raise ValueError(f"numero: use NNNNN/AA (ex.: 10175/23) ou só NNNNN para todos os anos (recebido: {numero!r})")
    return int(m.group(1)), (m.group(2)[-2:] if m.group(2) else None)


def _mesmo_numero(valor, num, ano2):
    m = _NUMERO.fullmatch(str(valor or "").strip())
    return bool(m) and int(m.group(1)) == num and (ano2 is None or (m.group(2) or "")[-2:] == ano2)


def _por_numero(cliente, params, numero, maximo):
    """Acórdãos pelo número do processo ou do acórdão: busca nos dois filtros e confere cada resultado campo a campo.

    Os filtros aceitam parte do número ("começa com"; descoberta F): fica só o resultado cujo número de processo ou
    de acórdão é o pedido, no número e, se veio, no ano. Cada registro diz em `casou_com` qual número casou. Sem o ano,
    vêm todos os anos, e `aviso_numero` diz quais.
    """
    num, ano2 = numero_pedido(numero)
    valor = f"{num:05d}/{ano2}" if ano2 else str(num)
    achados, fora, anos, incompleta = {}, set(), set(), None
    for nome, filtro in (("processo", "numero_processo_filtro"), ("acórdão", "numero_acordao_filtro")):
        try:
            total, registros, parou = _buscar(cliente, {**params, filtro: valor}, PAGINAS_POR_NUMERO * POR_PAGINA)
        except TetoAtingido as e:
            if not achados:
                raise
            incompleta = str(e)
            break
        if parou or len(registros) < total:
            incompleta = incompleta or (f"o filtro de {nome} achou {total} resultados para {valor} e foram lidos "
                                        f"{len(registros)}: informe o número completo, NNNNN/AA")
        for reg in registros:
            casou = [(c, reg.get(chave)) for c, chave in (("processo", "numero_processo"),
                                                          ("acordao", "numero_acordao"))
                     if _mesmo_numero(reg.get(chave), num, ano2)]
            if casou:
                if reg["document_id"] not in achados:
                    achados[reg["document_id"]] = {**reg, "casou_com": " e ".join(c for c, _ in casou)}
                    anos.add(str(casou[0][1]).strip().rpartition("/")[2] or "sem ano")
            else:
                fora.add(reg["document_id"])
    casados = list(achados.values())
    saida = {"total": len(casados), "registros": casados[:maximo]}
    avisos = []
    if ano2 is None:
        anos = sorted(anos)
        avisos.append(f"número sem o ano: vale para todos os anos; vieram {len(anos)} anos "
                      f"({', '.join(anos) or 'nenhum'}). Para um só, informe NNNNN/AA")
    fora -= achados.keys()
    if fora:
        avisos.append(f"o filtro do TCMJuris aceita parte do número: {len(fora)} resultado(s) com outro número "
                      "ficaram fora")
    if avisos:
        saida["aviso_numero"] = "; ".join(avisos)
    if incompleta:
        saida["incompleta"] = incompleta
    return saida


def _buscar(cliente, params, maximo):
    """Uma busca paginada, sem repetidos, até `maximo`. Devolve (total da fonte, registros, motivo de parada ou None).

    O teto de chamadas no meio da leitura devolve o lido e o motivo; logo na 1ª página, `TetoAtingido` sobe.
    """
    params = {**params, "page_size": max(1, min(POR_PAGINA, maximo))}
    registros, vistos, total, busca_id, pagina, incompleta = [], set(), 0, None, 1, None
    while len(registros) < maximo:
        pedido = {**params, "page": pagina, **({"busca_id": busca_id} if busca_id else {})}
        try:
            d = cliente.json("tcmjuris", "GET", f"{CAMINHO}/buscar", params=pedido)
        except TetoAtingido as e:
            if not registros:
                raise
            incompleta = str(e)
            break
        dados, pag = _validar(d)
        total, busca_id = pag["total_items"], d.get("busca_id") or busca_id
        for item in dados:
            if item.get("document_id") not in vistos:
                vistos.add(item.get("document_id"))
                registros.append(_registro(item))
        if not dados or not pag.get("has_next"):
            break
        pagina += 1
    return total, registros, incompleta


def _validar(d):
    """Só vale resposta com `success: true`, `data` (lista) e `pagination` com o total. Fora isso, erro."""
    dados, pag = d.get("data"), d.get("pagination")
    if (d.get("success") is not True or not isinstance(dados, list) or not isinstance(pag, dict)
            or not isinstance(pag.get("total_items"), int)):
        raise ErroTCM(f"{FONTES['tcmjuris']['nome']} devolveu uma busca sem success/data/pagination válidos "
                      f"(chaves: {sorted(d)}): a lista não é confiável")
    return dados, pag


def _registro(item):
    return {**{chave: item.get(campo) for chave, campo in CAMPOS.items()}, "fonte": FONTES["tcmjuris"]["nome"]}


def ler_acordao(cliente, *, document_id) -> dict:
    """Texto do PDF de um acórdão. Devolve {"total": 1, "registros": [{"document_id", "pdf", "texto"}]}."""
    caminho = f"{CAMINHO}/pdf/{quote(document_id, safe='')}"
    link = f"{FONTES['tcmjuris']['base']}{caminho}"
    try:
        import pypdf
    except ImportError:
        raise ErroTCM(f"ler o acórdão precisa da leitura de PDF, que é opcional: {INSTALAR_PDF}. "
                      f"Enquanto isso, o PDF original está em {link}") from None
    r = cliente.pedir("tcmjuris", "GET", caminho)
    if not r.content.startswith(b"%PDF"):
        raise ErroTCM(f"{FONTES['tcmjuris']['nome']}: a resposta para {document_id} não é PDF "
                      f"({len(r.content)} bytes, começa com {r.content[:40]!r}). Link: {link}")
    try:
        leitor = pypdf.PdfReader(io.BytesIO(r.content))
        texto = "\n".join(p.extract_text() or "" for p in leitor.pages).strip()
    except pypdf.errors.PdfReadError as e:
        raise ErroTCM(f"{FONTES['tcmjuris']['nome']}: o PDF de {document_id} não pôde ser lido ({e}). "
                      f"Link: {link}") from e
    saida = {"total": 1, "registros": [{"document_id": document_id, "pdf": link, "texto": texto}]}
    if not texto:
        saida["aviso_texto"] = (f"o PDF não tem texto extraível (provavelmente digitalizado): leia pelo link {link}")
    return saida
