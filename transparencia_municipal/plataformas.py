"""Qual plataforma um portal usa: pelo endereço e, quando ele não basta, pela página inicial (sondagem).

Conhecimento medido em 04/11/2026; ver docs/design/2026-11-05-nucleogov-goias.md.
"""
from __future__ import annotations

import re

MODULOS_NUCLEOGOV = ("servidores", "despesas", "receitas", "contratos", "licitacoes", "diarias")


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
        # `mgservidores`, `mgdespesas`...: o módulo vem da Megasoft embutida no NucleoGov (ex.: Abadia de Goiás,
        # 04/11/2026). Sufixo "mg" = módulo que a API NucleoGov não serve (responderia zero, sem erro).
        megasoft = re.findall(rf"\bmg({'|'.join(MODULOS_NUCLEOGOV)})\b", low)
        for modulo in megasoft:
            sufixos.setdefault(modulo, "mg")
        # `cntdespesas`, `cntreceitas`: o módulo vem da contabilidade Centi integrada ao NucleoGov (Posse, 04/11/2026);
        # a API NucleoGov não o serve. Não confundir com `servidores_cnt`, que é módulo NucleoGov comum.
        for modulo in re.findall(rf"\bcnt({'|'.join(MODULOS_NUCLEOGOV)})\b", low):
            sufixos.setdefault(modulo, "centi")
        # `contratos_mg`, `licitacoes_mg`: módulos do NucleoGov com os dados da Megasoft (Aruanã, 04/11/2026), lidos pelo
        # encaixe da Megasoft embutida; `sgdiarias`: as diárias do NucleoGov nesses portais (não existe `mgdiarias`)
        for modulo in re.findall(rf"\b({'|'.join(MODULOS_NUCLEOGOV)})_mg\b", low):
            sufixos.setdefault(modulo, "mg")
        if re.search(r"\bsgdiarias\b", low) and sufixos.get("diarias") in (None, "mg"):
            sufixos["diarias"] = "sg"  # o `sgdiarias` foi medido; o `mgdiarias`, não
        # `sgservidores`, `sgdespesas`...: o sistema de gestão integrado ao NucleoGov (Anápolis, 05/11/2026); a API
        # NucleoGov comum (`servidores_frl`...) responde zero, sem erro, nesses portais
        for modulo in re.findall(r"\bsg(servidores|despesas|receitas|contratos|licitacoes)\b", low):
            sufixos.setdefault(modulo, "sg")
        return {"plataforma": "nucleogov-megasoft" if megasoft else "nucleogov", "sufixos": sufixos}
    if "/src/main.jsx" in low:
        return {"plataforma": "ortrel", "sufixos": {}}
    return {"plataforma": None, "sufixos": {}}
