"""TCMJuris do TCM-GO: acórdãos julgados desde 2020 e o texto do PDF. Desenho: docs/design/2026-11-04-tcm-go.md.

Encaixe do `ClienteTCM`: o cliente já resolveu o município e zerou o teto de chamadas.
"""
from __future__ import annotations

import io
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


def acordaos(cliente, *, municipio, texto, assunto, ano, relator, maximo) -> dict:
    """Acórdãos. Devolve {"total", "registros"} (veja o ticket 01, seção Comments)."""
    filtros = {"texto": texto, "municipio": municipio, "assunto": assunto, "conselheiro": relator,
               "ano_votacao": ano}
    params = {k: v for k, v in filtros.items() if v not in (None, "")}
    params["page_size"] = max(1, min(POR_PAGINA, maximo))
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
    saida = {"total": total, "registros": registros[:maximo]}
    if incompleta:
        saida["incompleta"] = incompleta
    return saida


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
