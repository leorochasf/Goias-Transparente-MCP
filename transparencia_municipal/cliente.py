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
from datetime import datetime

import requests

from .plataformas import plataforma_pelo_endereco, reconhecer

UA_FERRAMENTA = ("Goias-Transparente-MCP/0.5 "
                 "(+https://github.com/leorochasf/Goias-Transparente-MCP)")
UA_NAVEGADOR = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

#: nome amigável → módulo da API. A ação é `<modulo>_<sufixo>/listar`, e o sufixo (`frl` ou `cnt`) varia
#: por portal e por módulo. Com o sufixo errado o portal responde total 0, sem erro (medido em 04/11/2026).
MODULOS = {
    "folha": "servidores",
    "despesas": "despesas",
    "contratos": "contratos",
    "licitacoes": "licitacoes",
    "receitas": "receitas",
    "diarias": "diarias",
}
SUFIXOS = ("frl", "cnt")
#: o que a página inicial de cada portal ensinou nesta execução (endereço → {"plataforma", "sufixos"}); evita reler a
#: página a cada consulta
_SUFIXOS_APRENDIDOS: dict[str, dict] = {}
#: (endereço, módulo) → sufixo com que a API NucleoGov serve um módulo `mg`/`centi`, ou None; evita sondar a cada consulta
_API_SONDADA: dict[tuple[str, str], str | None] = {}
#: `fonte` dos registros que vêm da API NucleoGov; os traduzidos de outro sistema trazem a sua
FONTE = "NucleoGov"
#: "sufixos" de módulos que a página do portal mostra, mas que a API NucleoGov não serve
EXTERNOS = {"mg": "da Megasoft embutida no NucleoGov", "centi": "da contabilidade Centi integrada ao NucleoGov"}
#: origem do portal `*.megasofttransparencia.com.br`, que vai inteiro pela Megasoft de domínio próprio
PROPRIA = "da Megasoft de domínio próprio"
#: origem das câmaras Ortrel (página inicial com `/src/main.jsx`), que vão inteiras pelo encaixe Ortrel
ORTREL = "do sistema Ortrel"
#: origem das diárias dos portais NucleoGov, que têm encaixe próprio (os campos mudam de portal para portal)
NUCLEOGOV = "do NucleoGov"
#: módulos que um encaixe pode ler; o encaixe que não tem a função recusa o módulo (`ModuloNaoSuportado`)
LIDOS_POR_ACESSO = ("folha", "despesas", "receitas", "contratos", "licitacoes", "diarias", "legislacao",
                    "detalhe_servidor")
#: módulos cujos registros da API NucleoGov ganham `fonte` (os demais saem como sempre saíram, sem a chave)
COM_FONTE_NA_API = ("folha", "despesas")


#: tipo de ato → código no módulo `atos` (conferido em Senador Canedo, 04/11/2026)
TIPOS_ATO = {"DECRETO": 1, "PORTARIA": 2, "RESOLUCAO": 3}


def _tipo_nome(tipo):
    """O tipo de ato em maiúsculas e sem cedilha nem til: "Resolução" → "RESOLUCAO"."""
    return str(tipo).strip().upper().replace("Ç", "C").replace("Ã", "A").replace("Õ", "O")


def _tipo_ato(tipo):
    """Aceita nome (decreto, Resolução...) ou código numérico e devolve o código."""
    v = str(tipo).strip()
    if v.isdigit():
        return int(v)
    chave = _tipo_nome(v)
    if chave not in TIPOS_ATO:
        raise ValueError(f"tipo: use {', '.join(TIPOS_ATO)} ou o código numérico (recebido: {tipo!r})")
    return TIPOS_ATO[chave]


class ErroPortal(RuntimeError):
    """Falha ao falar com o portal. A mensagem sempre diz o que aconteceu."""


class ModuloNaoSuportado(ErroPortal):
    """O portal mostra o módulo, mas ele vem de outra plataforma que a API NucleoGov não serve."""


class PortalBloqueou(ErroPortal):
    """O portal recusou a requisição (403) — em geral, por não vir de um navegador."""


def recusa(portal, nome, origem):
    """A recusa de um módulo que o sistema não tem ou que este projeto não lê. `origem`: EXTERNOS, PROPRIA ou ORTREL."""
    modulo = MODULOS.get(nome, nome)
    if origem in (PROPRIA, ORTREL):
        return ModuloNaoSuportado(f"{portal.url} é portal {origem}: o módulo {modulo} "
                                  "ainda não é suportado por este projeto.")
    return ModuloNaoSuportado(f"em {portal.url}, o módulo {modulo} vem {origem}, ainda não suportada: "
                              "a API NucleoGov não traz nenhum registro desse módulo (responderia zero, sem aviso).")


AVISO_DIARIAS = ("Cada portal publica as diárias com campos e datas diferentes; o projeto os traduz para nomes comuns. "
                 "Valor vazio quer dizer que o portal não publicou o valor, não que ele foi zero. As diárias trazem "
                 "nomes de pessoas: use para apuração, não para montar dossiê.")
AVISO_DETALHE = ("A Megasoft não publica as rubricas da folha (tudo cai em \"Outras Remunerações\"). No lugar, o "
                 "detalhe traz cargo, vínculo, decreto de nomeação e a data dele, licenças, férias e os movimentos do mês.")


def marcas_em_texto(r, maximo):
    """As marcas da resposta de um encaixe, em texto (`aviso_total`, `aviso_leitura`).

    `total_e_piso`: o total é piso. `incompleta`: a leitura parou antes do total. Vieram menos registros do que o
    `maximo` e o total permitem, sem marca: também é leitura incompleta, e é dita.
    """
    avisos, lidos, total = {}, len(r.get("registros") or []), r.get("total") or 0
    if r.get("total_e_piso"):
        avisos["aviso_total"] = f"o sistema informa {total} ou mais: o total é um piso, não o número exato"
    motivo = r.get("incompleta")
    if not motivo and not r.get("total_e_piso") and lidos < min(maximo, total):
        motivo = "a fonte parou antes do total"
    if motivo:
        avisos["aviso_leitura"] = (f"leitura incompleta ({motivo}): vieram {lidos} de {total} registros; "
                                   "tente de novo ou refine os filtros")
    return avisos


def ainda_nao_disponivel(portal, modulo, origem):
    """O que um encaixe responde enquanto o ticket dele não chega. `modulo`: o nome legível ("receitas")."""
    return ModuloNaoSuportado(f"em {portal.url}, o módulo {modulo} {origem} ainda não está disponível neste projeto.")


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


def _dia(valor, *, campo):
    """Como `_data_br`, mas devolve a data (`datetime.date`); data inexistente (31/02) é recusada."""
    texto = _data_br(valor, campo=campo)
    try:
        return datetime.strptime(texto, "%d/%m/%Y").date()
    except ValueError:
        raise ValueError(f"{campo}: data inexistente (recebido: {valor!r})") from None


def _mes_valido(mes):
    v = str(mes).strip()
    if not v.isdigit() or not 1 <= int(v) <= 12:
        raise ValueError(f"mes: use um número de 1 a 12 (recebido: {mes!r})")
    return int(v)


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
    sufixos: dict | None = None   # módulo → "frl"/"cnt"; None = aprender na página inicial
    plataforma: str | None = None  # do catálogo ("ortrel", "megasoft"...); None = pelo endereço ou pela página
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
        for campo in ("erro", "error"):  # `error`: a Megasoft embutida, com total 0 (licitações com período)
            motivo = bruto.get(campo) if isinstance(bruto, dict) else None
            if isinstance(motivo, str) and motivo.strip() and motivo.strip() != "null":
                raise ErroPortal(f"{self.url} recusou {acao}: {motivo}")
        registros = bruto.get("dados") or bruto.get("registros") or []
        return registros, int(bruto.get("total") or 0)

    def _descobrir(self):
        """Plataforma e sufixos que a página inicial anuncia (`servidores_cnt`, `/src/main.jsx`...). Sem página: nada."""
        nada = {"plataforma": None, "sufixos": {}}
        try:
            r = self.sessao.get(f"{self.url}/", timeout=self.timeout, headers={"User-Agent": self.user_agent})
        except requests.RequestException:
            return nada
        return reconhecer(r.text, self.url) if r.status_code == 200 else nada

    def _pagina_inicial(self):
        """O que a página inicial ensina, lido uma vez por endereço enquanto o processo vive."""
        if self.url not in _SUFIXOS_APRENDIDOS:
            _SUFIXOS_APRENDIDOS[self.url] = self._descobrir()
        return _SUFIXOS_APRENDIDOS[self.url]

    def _plataforma(self):
        """A do catálogo; senão a do endereço; senão a da página inicial; sem nenhuma, NucleoGov (como sempre foi)."""
        if self.plataforma is None:
            self.plataforma = (plataforma_pelo_endereco(self.url) or self._pagina_inicial()["plataforma"]
                               or "nucleogov")
        return self.plataforma

    def _sufixo(self, modulo):
        """O sufixo do módulo neste portal: o já sabido (catálogo, consulta anterior) ou o que a página anuncia.

        Módulo que os sufixos dados não têm (o catálogo é anterior a `sgdiarias` e `contratos_mg`): a página completa.
        """
        if self.sufixos is None:
            self.sufixos = self._pagina_inicial()["sufixos"]  # o mesmo dicionário: o aprendido vale para o próximo
        elif modulo not in self.sufixos:
            da_pagina = self._pagina_inicial()["sufixos"]
            if da_pagina is not self.sufixos:
                self.sufixos = {**da_pagina, **self.sufixos}  # o que já se sabia vale mais que a página
        return self.sufixos.get(modulo)

    def _api_serve(self, modulo):
        """O sufixo com que a API NucleoGov traz algum registro do módulo, sem filtro; None se nenhum.

        Lembrado por endereço enquanto o processo vive, se a API respondeu; erro em todos os sufixos não é lembrado.
        """
        chave = (self.url, modulo)
        if chave in _API_SONDADA:
            return _API_SONDADA[chave]
        respondeu = False
        for sufixo in SUFIXOS:
            try:
                total = self.consultar(f"{modulo}_{sufixo}/listar", {}, maximo=1)["total"]
            except PortalBloqueou:
                raise
            except ErroPortal:
                continue
            respondeu = True
            if total > 0:
                _API_SONDADA[chave] = sufixo
                return sufixo
        if respondeu:
            _API_SONDADA[chave] = None
        return None

    def _acesso(self, nome):
        """Ponto único da escolha do caminho de um módulo (`folha`, `diarias`, `detalhe_servidor`...) neste portal.

        None: API NucleoGov. Senão, a função do encaixe que lê o módulo:
        - Megasoft de domínio próprio (o endereço basta) e Ortrel (catálogo ou página inicial): o portal inteiro;
        - Megasoft embutida (menus `mg*`, `*_mg`; diárias em `sgdiarias`) e Centi (menus `cnt*`), módulo a módulo;
        - diárias de qualquer outro portal NucleoGov: o encaixe de diárias do NucleoGov.
        Módulo que o encaixe não lê é recusado (`ModuloNaoSuportado`).
        """
        # importados aqui: os encaixes importam do cliente
        from . import centi, diarias_nucleogov, megasoft_embutida, megasoft_propria, ortrel
        plataforma = self._plataforma()
        if plataforma in ("megasoft", "ortrel"):
            acesso, origem = {"megasoft": (megasoft_propria, PROPRIA), "ortrel": (ortrel, ORTREL)}[plataforma]
        else:
            modulo = MODULOS.get(nome)
            if modulo is None:
                return None
            externo = self._sufixo(modulo)
            if nome == "diarias":  # sem leitura genérica: os campos das diárias mudam de portal para portal
                acesso, origem = ((megasoft_embutida, EXTERNOS["mg"]) if externo == "sg"
                                  else (diarias_nucleogov, NUCLEOGOV))
            elif externo not in EXTERNOS:
                return None
            else:
                # o menu aponta outra plataforma, mas a API NucleoGov às vezes serve o módulo mesmo assim
                # (Alexânia sim, Posse não, em 04/11/2026): uma consulta sem filtro decide, uma vez por endereço
                sufixo = self._api_serve(modulo)
                if sufixo:
                    self.sufixos[modulo] = sufixo
                    return None
                acesso, origem = {"mg": megasoft_embutida, "centi": centi}[externo], EXTERNOS[externo]
        ler = getattr(acesso, nome, None) if nome in LIDOS_POR_ACESSO else None
        if ler is None:
            raise recusa(self, nome, origem)
        return ler

    def _consultar_modulo(self, nome, filtros, *, maximo, progresso=None, pedido=None):
        """Consulta um módulo pelo caminho deste portal.

        Outro sistema: a função do módulo de acesso recebe `pedido` (os argumentos já normalizados) e `maximo`.
        API NucleoGov: `filtros`, com o sufixo deste portal; sufixo desconhecido: `frl`; se der zero, `cnt`.
        """
        ler = self._acesso(nome)
        if ler:
            return ler(self, **(pedido or {}), maximo=maximo)
        r = self._consultar_api(MODULOS[nome], filtros, maximo=maximo, progresso=progresso)
        if nome in COM_FONTE_NA_API:  # folha e despesas podem vir de outro sistema: todo registro diz de onde veio
            for x in r["registros"]:
                x.setdefault("fonte", FONTE)
        return r

    def _consultar_api(self, modulo, filtros, *, maximo, progresso):
        if modulo in self.sufixos:
            return self.consultar(f"{modulo}_{self.sufixos[modulo]}/listar", filtros, maximo=maximo,
                                  progresso=progresso)
        zeros, erro = [], None
        for sufixo in SUFIXOS:
            try:
                r = self.consultar(f"{modulo}_{sufixo}/listar", filtros, maximo=maximo, progresso=progresso)
            except PortalBloqueou:
                raise
            except ErroPortal as e:  # sufixo inexistente responde `[]` (Alexânia, 04/11/2026)
                erro = erro or e
                continue
            if r["total"] > 0:
                self.sufixos[modulo] = sufixo
                return r
            zeros.append(r)
        if zeros:
            return zeros[0]
        raise erro

    def consultar(self, acao, filtros=None, *, maximo=200, progresso=None):
        """Pagina até `maximo` registros. Devolve {"total", "registros"}.

        `progresso(lidos, total)`, se dado, é chamado depois de cada página.
        """
        registros, total, offset = [], 0, 0
        while len(registros) < maximo:
            lote, total_da_pagina = self._pagina(acao, filtros, offset)
            for fator in (2, 5, 10):
                if not (offset and not lote and len(registros) < total):
                    break
                # página vazia antes do fim, com total 0, depois de várias páginas seguidas (Trindade, 04/11/2026:
                # parou em 1800 numa leitura e em 1000 na outra; sozinha, a mesma página responde): espera e repete
                time.sleep(self.pausa * fator)
                lote, total_da_pagina = self._pagina(acao, filtros, offset)
            # vale o total anunciado na 1ª página; quem lê confere se trouxe tudo
            total = total_da_pagina if not offset else total
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
        pedido = {"ano": int(ano), "mes": int(mes) if mes else None, "busca": busca, "progresso": progresso}
        return self._consultar_modulo("folha", f, maximo=maximo, progresso=progresso, pedido=pedido)

    def despesas(self, de, ate, busca=None, *, maximo=200):
        """Empenhos e pagamentos no período. `busca` aceita nome ou CNPJ do fornecedor.

        CNPJ (14 dígitos, com ou sem pontuação) vai no filtro próprio do portal, já no
        formato 00.000.000/0000-00: a busca livre não acha CNPJ. Outro texto vai na busca livre.
        """
        f = {"datamin": _data_br(de, campo="de"), "datamax": _data_br(ate, campo="ate")}
        cnpj = _cnpj(busca) if busca else None
        pedido = {"de": f["datamin"], "ate": f["datamax"], "cnpj": cnpj, "busca": None if cnpj else busca}
        if cnpj:
            f["cpf_cnpj"] = cnpj
        elif busca:
            f["txtbusca"] = busca
        return self._consultar_modulo("despesas", f, maximo=maximo, pedido=pedido)

    def contratos(self, ano=None, tipo="contrato", busca=None, *, maximo=200):
        """Contratos (tipo="contrato") ou aditivos (tipo="aditivo")."""
        f = {"tipo": tipo}
        if ano:
            f["ano"] = str(ano)  # `anobase` é ignorado (Alexânia, 04/11/2026)
        if busca:
            f["txtbusca"] = busca
        pedido = {"ano": int(ano) if ano else None, "tipo": tipo, "busca": busca}
        return self._consultar_modulo("contratos", f, maximo=maximo, pedido=pedido)

    def licitacoes(self, busca=None, *, dispensas=False, ano=None, maximo=200):
        """Licitações; dispensas=True traz dispensas e inexigibilidades.

        `ano` só onde o filtro foi medido (Megasoft, Ortrel): na API NucleoGov é recusado, porque o portal ignora
        filtro desconhecido em silêncio.
        """
        ler = self._acesso("licitacoes")
        if ler:
            return ler(self, busca=busca, dispensas=bool(dispensas), ano=int(ano) if ano else None, maximo=maximo)
        if ano:
            raise ValueError("ano: o filtro de ano das licitações não foi medido nos portais NucleoGov; "
                             "consulte sem ano (use a busca, ex.: o número do processo)")
        f = {"dispensas": 1 if dispensas else 0, "fracassadas_desertas": 0}
        if busca:
            f["txtbusca"] = busca
        return self._consultar_api(MODULOS["licitacoes"], f, maximo=maximo, progresso=None)

    def receitas(self, ano, mes, *, maximo=200):
        """Receitas de um mês. Para um período, chame uma vez por mês.

        Verificado em portal real: o filtro por datas (datamin/datamax) é ignorado
        e devolve sempre o mês corrente; só ano + mês são respeitados.
        """
        mes = _mes_valido(mes)
        return self._consultar_modulo("receitas", {"ano": str(ano), "mes": str(mes)}, maximo=maximo,
                                      pedido={"ano": int(ano), "mes": mes})

    def diarias(self, de, ate, busca=None, *, maximo=200):
        """Diárias de viagem a serviço, pela data de saída. `busca`: texto (nome, cargo, destino ou motivo).

        Cada sistema publica campos diferentes; o encaixe os traduz para os nomes comuns (ticket 01, `## Comments`).
        """
        inicio, fim = _dia(de, campo="de"), _dia(ate, campo="ate")
        if fim < inicio:
            raise ValueError(f"ate ({ate}) é anterior a de ({de})")
        return self._acesso("diarias")(self, de=inicio, ate=fim, busca=busca or None, maximo=maximo)

    def detalhe_servidor(self, matricula, ano, mes):
        """Cargo, vínculo, decreto de nomeação e data, licenças e movimentos de uma matrícula num mês.

        Só na Megasoft de domínio próprio, que não publica as rubricas da folha.
        """
        m = str(matricula or "").strip()
        if not m:
            raise ValueError("matricula: informe a matrícula do servidor (ela vem na folha)")
        mes = _mes_valido(mes)
        ler = self._acesso("detalhe_servidor")
        if ler is None:
            raise ModuloNaoSuportado(
                f"{self.url}: o detalhe do servidor só existe nos portais da Megasoft de domínio próprio "
                "(*.megasofttransparencia.com.br). Nos portais NucleoGov, a folha (consultar_folha) traz as rubricas.")
        return ler(self, matricula=m, ano=int(ano), mes=mes)

    def legislacao(self, tipo="DECRETO", busca=None, *, ano=None, maximo=200):
        """Decretos, portarias ou resoluções. `tipo`: DECRETO, PORTARIA, RESOLUCAO ou o código.

        `busca` procura palavra na ementa. Lê o módulo `atos` do portal: em Senador Canedo
        (04/11/2026) o antigo `atos_pf_<apelido>` estava vazio, inclusive na tela do site.
        """
        ler = self._acesso("legislacao")  # Ortrel: o encaixe; outro sistema sem legislação: recusa
        if ler:
            return ler(self, tipo=_tipo_nome(tipo), busca=busca, ano=int(ano) if ano else None, maximo=maximo)
        f = {"tipo": _tipo_ato(tipo)}
        if busca:
            f["search"] = busca
        if ano:
            f["ano"] = str(ano)
        return self.consultar("atos/buscaAvancada", f, maximo=maximo)
