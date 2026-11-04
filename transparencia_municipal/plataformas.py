"""Qual plataforma um portal usa: pelo endereço e, quando ele não basta, pela página inicial (sondagem).

Conhecimento medido em 04/11/2026; ver docs/design/2026-11-05-nucleogov-goias.md.
"""
from __future__ import annotations

import re

MODULOS_NUCLEOGOV = ("servidores", "despesas", "receitas", "contratos", "licitacoes")


def _host(endereco):
    host = re.sub(r"^https?://", "", str(endereco).strip().lower()).split("/")[0]
    return host[4:] if host.startswith("www.") else host


def plataforma_pelo_endereco(endereco):
    """'nucleogov', 'megasoft' ou None quando só a página inicial pode dizer."""
    host = _host(endereco)
    if host.endswith(".megasofttransparencia.com.br"):
        return "megasoft"
    if host.startswith("acessoainformacao."):
        return "nucleogov"
    return None


def reconhecer(html, endereco):
    """Plataforma e sufixos dos módulos (`servidores` → `cnt` ou `frl`) a partir da página inicial."""
    if plataforma_pelo_endereco(endereco) == "megasoft":
        return {"plataforma": "megasoft", "sufixos": {}}
    low = (html or "").lower()
    if "nucleogov" in low:
        sufixos = {}
        for modulo, sufixo in re.findall(rf"\b({'|'.join(MODULOS_NUCLEOGOV)})_(cnt|frl)\b", low):
            sufixos.setdefault(modulo, sufixo)
        # `mgservidores`: a folha vem da Megasoft embutida no NucleoGov (ex.: Caldazinha); o resto é NucleoGov
        return {"plataforma": "nucleogov-megasoft" if "mgservidores" in low else "nucleogov", "sufixos": sufixos}
    if "/src/main.jsx" in low:
        return {"plataforma": "ortrel", "sufixos": {}}
    return {"plataforma": None, "sufixos": {}}
