"""Cliente do Portal da Transparência de municípios na plataforma NucleoGov.

Somente leitura de dados públicos (Lei 12.527/2011). A API não pede cadastro nem senha:
é a mesma que a tela do portal usa quando você clica.

Padrão das chamadas:
    POST {portal}/api/{acao}
    corpo: multi_request=true & params={"<id>": {<filtros>, "limit": "<offset>, <n>", "acao": "<acao>"}}
    resposta: {"<id>": {"dados": [...], "total": N}}
"""
from __future__ import annotations

import json
import random
import re
import time
import urllib.parse
from dataclasses import dataclass, field

import requests

UA_FERRAMENTA = ("mcp-transparencia-municipal/0.2 "
                 "(+https://github.com/leorochasf/mcp-transparencia-municipal)")
UA_NAVEGADOR = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

#: nome amigável → (ação da API, campo de busca livre)
MODULOS = {
    "folha": "servidores_frl/listar",
    "despesas": "despesas_frl/listar",
    "contratos": "contratos_frl/listar",
    "licitacoes": "licitacoes_frl/listar",
    "receitas": "receitas_frl/listar",
}


#: tipo de ato → código no módulo `atos` (conferido em Senador Canedo, 04/11/2026)
TIPOS_ATO = {"DECRETO": 1, "PORTARIA": 2, "RESOLUCAO": 3}


def _tipo_ato(tipo):
    """Aceita nome (decreto, Resolução...) ou código numérico e devolve o código."""
    v = str(tipo).strip()
    if v.isdigit():
        return int(v)
    chave = v.upper().replace("Ç", "C").replace("Ã", "A").replace("Õ", "O")
    if chave not in TIPOS_ATO:
        raise ValueError(f"tipo: use {', '.join(TIPOS_ATO)} ou o código numérico (recebido: {tipo!r})")
    return TIPOS_ATO[chave]


class ErroPortal(RuntimeError):
    """Falha ao falar com o portal. A mensagem sempre diz o que aconteceu."""


class PortalBloqueou(ErroPortal):
    """O portal recusou a requisição (403) — em geral, por não vir de um navegador."""


def _data_br(valor, *, campo):
    """Aceita 2025-03-01, 01/03/2025 ou 2025-03 (vira o 1º dia) e devolve dd/mm/aaaa."""
    v = str(valor).strip()
    if re.fullmatch(r"\d{2}/\d{2}/\d{4}", v):
        return v
    m = re.fullmatch(r"(\d{4})-(\d{2})(?:-(\d{2}))?", v)
    if not m:
        raise ValueError(f"{campo}: use AAAA-MM-DD, AAAA-MM ou dd/mm/aaaa (recebido: {valor!r})")
    ano, mes, dia = m.group(1), m.group(2), m.group(3) or "01"
    return f"{dia}/{mes}/{ano}"


def _cnpj(texto):
    """Se o texto é só um CNPJ (14 dígitos, com ou sem pontuação), devolve 00.000.000/0000-00."""
    v = str(texto).strip()
    if not re.fullmatch(r"[\d./\- ]+", v):
        return None
    d = re.sub(r"\D", "", v)
    if len(d) != 14:
        return None
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


@dataclass
class Portal:
    """Um portal municipal. Ex.: Portal("https://acessoainformacao.cidade.go.gov.br")."""

    url: str
    navegador: bool = False       # identificar-se como navegador (ver README, "O 403")
    pausa: float = 1.0            # segundos entre requisições — não sobrecarregue o portal
    por_pagina: int = 100
    timeout: int = 60
    sessao: requests.Session = field(default_factory=requests.Session, repr=False)

    def __post_init__(self):
        self.url = self.url.rstrip("/")
        if not self.url.startswith("http"):
            self.url = "https://" + self.url

    @property
    def user_agent(self):
        return UA_NAVEGADOR if self.navegador else UA_FERRAMENTA

    def _pagina(self, acao, filtros, offset):
        ident = "0-" + "".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=6))
        corpo = {**(filtros or {}), "limit": f"{offset}, {self.por_pagina}", "acao": acao}
        dados = urllib.parse.urlencode({
            "multi_request": "true",
            "params": json.dumps({ident: corpo}, ensure_ascii=False),
        }).encode("utf-8")
        try:
            r = self.sessao.post(
                f"{self.url}/api/{acao}", data=dados, timeout=self.timeout,
                headers={"User-Agent": self.user_agent, "X-Requested-With": "XMLHttpRequest",
                         "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
        except requests.RequestException as e:
            raise ErroPortal(f"não foi possível falar com {self.url}: {e}") from e
        if r.status_code == 403:
            raise PortalBloqueou(
                f"{self.url} respondeu 403 para um cliente que se identifica como ferramenta. "
                "O dado é público (Lei 12.527/2011), mas o portal filtra por User-Agent. "
                "Você pode repetir com navegador=True (CLI: --navegador), ciente de que isso "
                "declara ao servidor um navegador que não existe, ou pedir acesso formal ao município.")
        if r.status_code != 200:
            raise ErroPortal(f"{self.url} respondeu HTTP {r.status_code} em {acao}: {r.text[:200]}")
        try:
            bruto = r.json()[ident]
        except (ValueError, KeyError, TypeError) as e:
            raise ErroPortal(f"{self.url} devolveu resposta inesperada em {acao} "
                             f"({len(r.content)} bytes, começa com {r.text[:80]!r})") from e
        if isinstance(bruto, dict) and isinstance(bruto.get("erro"), str) and bruto["erro"]:
            raise ErroPortal(f"{self.url} recusou {acao}: {bruto['erro']}")
        registros = bruto.get("dados") or bruto.get("registros") or []
        return registros, int(bruto.get("total") or 0)

    def consultar(self, acao, filtros=None, *, maximo=200, progresso=None):
        """Pagina até `maximo` registros. Devolve {"total", "registros"}.

        `progresso(lidos, total)`, se dado, é chamado depois de cada página.
        """
        registros, total, offset = [], 0, 0
        while len(registros) < maximo:
            lote, total = self._pagina(acao, filtros, offset)
            registros += lote
            if progresso:
                progresso(len(registros), total)
            offset += self.por_pagina
            if len(lote) < self.por_pagina or offset >= total:
                break
            time.sleep(self.pausa)
        return {"total": total, "registros": registros[:maximo]}

    # ── atalhos por módulo ────────────────────────────────────────────────
    def folha(self, ano, mes=None, busca=None, *, maximo=200, progresso=None):
        """Servidores e remuneração de um mês. `busca` filtra pelo NOME do servidor.

        Verificado em portal real: a caixa de busca da folha não encontra por cargo
        nem por lotação — para filtrar por cargo, traga o mês e filtre os registros.
        """
        f = {"ano": str(ano)}
        if mes:
            f["mes"] = str(int(mes))
        if busca:
            f["txtbusca"] = busca
        return self.consultar(MODULOS["folha"], f, maximo=maximo, progresso=progresso)

    def despesas(self, de, ate, busca=None, *, maximo=200):
        """Empenhos e pagamentos no período. `busca` aceita nome ou CNPJ do fornecedor.

        CNPJ (14 dígitos, com ou sem pontuação) vai no filtro próprio do portal, já no
        formato 00.000.000/0000-00: a busca livre não acha CNPJ. Outro texto vai na busca livre.
        """
        f = {"datamin": _data_br(de, campo="de"), "datamax": _data_br(ate, campo="ate")}
        cnpj = _cnpj(busca) if busca else None
        if cnpj:
            f["cpf_cnpj"] = cnpj
        elif busca:
            f["txtbusca"] = busca
        return self.consultar(MODULOS["despesas"], f, maximo=maximo)

    def contratos(self, ano=None, tipo="contrato", busca=None, *, maximo=200):
        """Contratos (tipo="contrato") ou aditivos (tipo="aditivo")."""
        f = {"tipo": tipo}
        if ano:
            f["anobase"] = str(ano)
        if busca:
            f["txtbusca"] = busca
        return self.consultar(MODULOS["contratos"], f, maximo=maximo)

    def licitacoes(self, busca=None, *, dispensas=False, maximo=200):
        """Licitações; dispensas=True traz dispensas e inexigibilidades."""
        f = {"dispensas": 1 if dispensas else 0, "fracassadas_desertas": 0}
        if busca:
            f["txtbusca"] = busca
        return self.consultar(MODULOS["licitacoes"], f, maximo=maximo)

    def receitas(self, ano, mes, *, maximo=200):
        """Receitas de um mês. Para um período, chame uma vez por mês.

        Verificado em portal real: o filtro por datas (datamin/datamax) é ignorado
        e devolve sempre o mês corrente; só ano + mês são respeitados.
        """
        v = str(mes).strip()
        if not v.isdigit() or not 1 <= int(v) <= 12:
            raise ValueError(f"mes: use um número de 1 a 12 (recebido: {mes!r})")
        return self.consultar(MODULOS["receitas"], {"ano": str(ano), "mes": str(int(v))},
                              maximo=maximo)

    def legislacao(self, tipo="DECRETO", busca=None, *, ano=None, maximo=200):
        """Decretos, portarias ou resoluções. `tipo`: DECRETO, PORTARIA, RESOLUCAO ou o código.

        `busca` procura palavra na ementa. Lê o módulo `atos` do portal: em Senador Canedo
        (04/11/2026) o antigo `atos_pf_<apelido>` estava vazio, inclusive na tela do site.
        """
        f = {"tipo": _tipo_ato(tipo)}
        if busca:
            f["search"] = busca
        if ano:
            f["ano"] = str(ano)
        return self.consultar("atos/buscaAvancada", f, maximo=maximo)
