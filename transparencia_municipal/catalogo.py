"""Catálogo de portais de Goiás: o portal de cada órgão, a plataforma e a situação da conferência.

Gerado por scripts/catalogo_go.py a partir dos dados abertos do Radar da Transparência Pública (Atricon).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .folha_leve import _comparavel
from .plataformas import _host

ARQUIVO = Path(__file__).with_name("catalogo_go.json")
NOMES_PLATAFORMA = {"megasoft": "Megasoft", "ortrel": "Ortrel", "nucleogov-megasoft": "NucleoGov com folha Megasoft",
                    "goiania": "sistemas próprios da Prefeitura de Goiânia (TransWeb e BSIT)"}


@lru_cache(maxsize=1)
def carregar():
    return json.loads(ARQUIVO.read_text(encoding="utf-8")) if ARQUIVO.exists() else []


def encontrar(municipio, orgao=None):
    """Órgãos do município (sem distinguir maiúscula nem acento); `orgao`: prefeitura ou camara."""
    nome = _comparavel(municipio)
    achados = [x for x in carregar() if _comparavel(x["municipio"]) == nome]
    if orgao:
        achados = [x for x in achados if _comparavel(x["orgao"]).startswith(_comparavel(orgao)[:4])]
    return achados


def por_portal(endereco):
    """O órgão dono deste endereço (o portal ou outro endereço conhecido dele), ou None."""
    host = _host(endereco)
    for x in carregar():
        if host == _host(x["portal"]) or host in {_host(h) for h in x.get("outros_enderecos", [])}:
            return x
    return None


def nome_do_orgao(x):
    return f"{'Prefeitura' if x['orgao'] == 'prefeitura' else 'Câmara'} de {x['municipio']}"


def situacao(x):
    """Frase curta para o assistente: conferido ou não, e o que falhou."""
    c = x.get("conferencia")
    if not c:
        return "portal não conferido: os filtros deste portal não foram medidos; confira os números no próprio portal"
    ruins = {k: v for k, v in c["filtros"].items() if v != "ok"}
    if not ruins:
        return f"conferido em {c['data']} (referência {c['referencia']}): todos os filtros respeitados"
    itens = "; ".join(f"{k}: {v}" + (f" ({c['detalhes'][k]})" if k in c.get("detalhes", {}) else "")
                      for k, v in ruins.items())
    return f"conferido em {c['data']} (referência {c['referencia']}), com ressalvas: {itens}"
