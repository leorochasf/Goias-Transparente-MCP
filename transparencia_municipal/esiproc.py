"""eSiproc do TCM-GO: os processos eletrônicos de um município. Desenho: docs/design/2026-11-04-tcm-go.md.

Encaixe do `ClienteTCM`: o cliente já resolveu o município e zerou o teto de chamadas.
"""
from __future__ import annotations

import re

from .tcm import FONTES, ErroTCM, TetoAtingido

#: o `/pesquisar` só aceita o corpo com TODAS estas chaves em `filtros` (`null` nas não usadas); parcial dá HTTP 400
CHAVES_FILTROS = (
    "municipio.keyword", "unidade_gestora.keyword", "relator.keyword", "regiao.keyword", "tipo_protocolo.keyword",
    "tags.nome.keyword", "area.keyword", "ano_competencia", "periodo_competencia.keyword", "lotacao.keyword",
    "envolvidos.situacao.keyword", "envolvidos.tipo_envolvimento.keyword", "range.data_protocolo.gte",
    "range.data_protocolo.lte", "finalizado.keyword")
_NUMERO = re.compile(r"^\s*(\d{1,5})\s*/\s*(\d{2}|\d{4})\s*$")
_CAMPOS = (("numero", "numero"), ("municipio", "municipio"), ("codigo_ibge", "codigo_ibge"),
           ("unidade_gestora", "unidade_gestora"), ("tipo", "tipo_protocolo"), ("ano_competencia", "ano_competencia"),
           ("mes_competencia", "mes_competencia"), ("periodo_competencia", "periodo_competencia"),
           ("relator", "relator"), ("fase", "st_fase"))
_DATAS = ("data_protocolo", "data_criacao", "data_ultima_tramitacao", "data_finalizacao")


def numero_no_filtro(numero):
    """`NNNNN/AA` (ou `/AAAA`) → `000NNNNN.20AA`, o começo do número no eSiproc (o filtro é "contém")."""
    m = _NUMERO.match(str(numero))
    if not m:
        raise ValueError(f"número de processo {numero!r} fora do formato NNNNN/AA (ex.: 00131/19)")
    ano = m[2] if len(m[2]) == 4 else f"20{m[2]}"
    return f"{int(m[1]):08d}.{ano}"


def processos(cliente, *, municipio, tipo, ano, finalizado, relator, numero, maximo) -> dict:
    """Processos do município. Devolve {"total", "registros"} (veja o ticket 01, seção Comments)."""
    filtros = dict.fromkeys(CHAVES_FILTROS)
    filtros.update({"municipio.keyword": municipio, "tipo_protocolo.keyword": tipo, "ano_competencia": ano,
                    "relator.keyword": relator,
                    "finalizado.keyword": None if finalizado is None else ("SIM" if finalizado else "NÃO")})
    like = {"numero.keyword": numero_no_filtro(numero)} if numero else None
    registros, vistos, total, piso, deslocamento = [], set(), 0, False, 0
    while len(registros) < maximo:
        corpo = {"numero": None, "termo": None, "filtros": filtros, "filtrosLike": like, "filtrosLikeNested": None,
                 "pagina": deslocamento, "filtroPeriodoJulgamento": {"inicio": None, "fim": None}}
        try:
            d = cliente.json("esiproc", "POST", "/pesquisar", corpo=corpo)
        except TetoAtingido:
            return _saida(total, registros, piso, incompleta=f"teto de {cliente.teto} chamadas atingido")
        hits, total, piso = _ler(d)
        if not hits:
            break
        for h in hits:
            s = h.get("_source") or {}
            if s.get("numero") not in vistos and len(registros) < maximo:
                vistos.add(s.get("numero"))
                registros.append(_registro(s))
        deslocamento += len(hits)
        if not piso and deslocamento >= total:
            break
    return _saida(total, registros, piso)


def _ler(d):
    """(hits, total, total é piso) de uma resposta do `/pesquisar`. Resposta incompleta ou estranha é erro."""
    nome = FONTES["esiproc"]["nome"]
    if d.get("timed_out") or (d.get("_shards") or {}).get("failed"):
        raise ErroTCM(f"{nome} devolveu resposta incompleta (timed_out ou shards com falha): repita mais tarde")
    try:
        hits, t = d["hits"]["hits"], d["hits"]["total"]
        total, relacao = int(t["value"]), t["relation"]
        if not isinstance(hits, list):
            raise TypeError
    except (KeyError, TypeError, ValueError) as e:
        raise ErroTCM(f"{nome} devolveu a busca de processos num formato inesperado") from e
    return hits, total, relacao == "gte"


def _registro(s):
    r = {chave: s.get(campo) for chave, campo in _CAMPOS}
    r["finalizado"] = {"SIM": True, "NÃO": False}.get(s.get("finalizado"))
    r["passo"] = s.get("passo")
    r.update({d: s.get(d) for d in _DATAS})
    r["decisoes"] = [{"nome": x.get("nome"), "data": x.get("data_criacao")} for x in s.get("decisoes") or []]
    r["envolvidos"] = [{"nome": x.get("nome"), "tipo_envolvimento": x.get("tipo_envolvimento"),
                        "tipo_pessoa": x.get("tipo_pessoa")} for x in s.get("envolvidos") or []]
    r["fonte"] = FONTES["esiproc"]["nome"]
    return r


def _saida(total, registros, piso, incompleta=None):
    saida = {"total": total, "registros": registros}
    if piso:
        saida["total_e_piso"] = True
    if incompleta:
        saida["incompleta"] = incompleta
    return saida
