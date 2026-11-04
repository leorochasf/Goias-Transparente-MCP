"""Cliente do TCM-GO (Tribunal de Contas dos Municípios de Goiás): processos (eSiproc) e acórdãos (TCMJuris).

Separado do `Portal`, que é de portal municipal. Aqui fica a parte comum às duas fontes: a identificação do projeto,
a pausa entre chamadas, os erros claros, o teto de chamadas por consulta e o nome do município em cada fonte.
As consultas de cada fonte ficam em `esiproc.py` e `tcmjuris.py`. Desenho: docs/design/2026-11-04-tcm-go.md.
"""
from __future__ import annotations

import difflib
import re
import time
import unicodedata
from dataclasses import dataclass, field

import requests

from . import catalogo
from .cliente import UA_FERRAMENTA, ErroPortal

FONTES = {
    "esiproc": {"nome": "TCM-GO eSiproc", "base": "https://virtual.tcmgo.tc.br/eSiproc/api/elastic",
                "referer": "https://virtual.tcmgo.tc.br/processo-eletronico/"},
    "tcmjuris": {"nome": "TCM-GO TCMJuris", "base": "https://virtual.tcmgo.tc.br/jurisprudencia/api",
                 "referer": "https://virtual.tcmgo.tc.br/jurisprudencia/"},
}

AVISO_GERAL = ("Dado público do TCM-GO, lido na hora. Confira na fonte antes de usar em peça, denúncia ou matéria.")
AVISO_PROCESSOS = ("O índice de processos do TCM-GO não é histórico: exercícios antigos, processos físicos e de cobrança "
                   "podem faltar. Não achar um processo não prova que ele não existe.")
AVISO_ENVOLVIDOS = ("Os envolvidos aparecem como o TCM-GO os mostra: use para apuração, não para montar dossiê "
                    "de pessoas.")
AVISO_ACORDAOS = ("O TCMJuris só cobre acórdãos julgados desde 2020: não achar um acórdão não prova que não houve "
                  "julgamento. A ementa é resumo gerado por IA, não escrito pelo tribunal: cite pelo PDF "
                  "(ler_acordao_tcm).")
INSTALAR_PDF = 'pip install "goias-transparente-mcp[pdf]"'

#: nome completo → nome que o TCMJuris encurta (tira "de Goiás"). Conferidos em 04/11/2026: são as 7 sobras
#: das listas oficiais, uma para uma, depois do casamento exato. Valem nos dois sentidos.
APELIDOS = {
    "ALTO PARAISO DE GOIAS": "ALTO PARAISO",
    "CAMPESTRE DE GOIAS": "CAMPESTRE",
    "DIVINOPOLIS DE GOIAS": "DIVINOPOLIS",
    "NOVA IGUACU DE GOIAS": "NOVA IGUACU",
    "OURO VERDE DE GOIAS": "OURO VERDE",
    "TAQUARAL DE GOIAS": "TAQUARAL",
    "TEREZOPOLIS DE GOIAS": "TEREZOPOLIS",
}
_CANONICO = {curto: completo for completo, curto in APELIDOS.items()}

#: fonte → lista oficial de municípios lida nesta execução: [(nome para casar, nome a usar na fonte)]
_LISTAS: dict[str, list[tuple[str, str]]] = {}


class ErroTCM(ErroPortal):
    """Falha ao falar com o TCM-GO. A mensagem sempre diz qual fonte e o que aconteceu."""


class TetoAtingido(ErroTCM):
    """A consulta chegou ao teto de chamadas. O módulo da fonte devolve o que leu e marca a leitura incompleta."""


class MunicipioNaoEncontrado(ValueError):
    """O nome não casa exatamente com a lista oficial da fonte. A mensagem traz os mais parecidos."""


def _chave(nome):
    """Maiúsculas, sem acento, sem apóstrofo, espaços simples; apelido do TCMJuris vira o nome completo."""
    v = unicodedata.normalize("NFKD", str(nome))
    v = "".join(c for c in v if not unicodedata.combining(c))
    v = " ".join(re.sub(r"['’`´]", "", v.upper()).split())
    return _CANONICO.get(v, v)


def casar(municipio, nomes):
    """O único nome de `nomes` igual a `municipio` depois de normalizar; None se nenhum ou mais de um."""
    alvo = _chave(municipio)
    achados = [n for n in nomes if _chave(n) == alvo]
    return achados[0] if len(achados) == 1 else None


def parecidos(municipio, nomes, n=5):
    alvo, por_chave = _chave(municipio), {}
    for nome in nomes:
        por_chave.setdefault(_chave(nome), nome)
    return [por_chave[c] for c in difflib.get_close_matches(alvo, list(por_chave), n=n, cutoff=0.6)]


@dataclass
class ClienteTCM:
    """O TCM-GO. Ex.: ClienteTCM().processos("Posse", ano=2024)."""

    pausa: float = 1.0       # segundos entre chamadas: uma consulta por vez, sem sobrecarregar o tribunal
    timeout: int = 60
    teto: int = 60           # chamadas por consulta; ao atingir, a leitura para e a resposta avisa
    sessao: requests.Session = field(default_factory=requests.Session, repr=False)
    _chamadas: int = field(default=0, repr=False)
    _ultima: float = field(default=0.0, repr=False)

    # --- rede ---------------------------------------------------------------------------------------------------

    def nova_consulta(self):
        """Zera a contagem de chamadas. As consultas públicas chamam isto sozinhas."""
        self._chamadas = 0

    def pedir(self, fonte, metodo, caminho, *, corpo=None, params=None) -> requests.Response:
        """Uma chamada a `FONTES[fonte]['base'] + caminho`, com pausa e teto. Só devolve resposta HTTP 200."""
        f = FONTES[fonte]
        if self._chamadas >= self.teto:
            raise TetoAtingido(f"{f['nome']}: a consulta chegou ao teto de {self.teto} chamadas")
        espera = self.pausa - (time.monotonic() - self._ultima)
        if espera > 0:
            time.sleep(espera)
        self._chamadas += 1
        headers = {"User-Agent": UA_FERRAMENTA, "Referer": f["referer"], "Accept": "application/json"}
        try:
            r = self.sessao.request(metodo, f"{f['base']}{caminho}", json=corpo, params=params, headers=headers,
                                    timeout=self.timeout)
        except requests.RequestException as e:
            raise ErroTCM(f"{f['nome']} não respondeu ({caminho}): {e}") from e
        finally:
            self._ultima = time.monotonic()
        if r.status_code != 200:
            raise ErroTCM(f"{f['nome']} respondeu HTTP {r.status_code} em {caminho}: {r.text[:200]}")
        return r

    def json(self, fonte, metodo, caminho, *, corpo=None, params=None) -> dict:
        """Como `pedir`, exigindo um objeto JSON. HTML ou corpo estranho com 200 é erro, nunca lista vazia."""
        r = self.pedir(fonte, metodo, caminho, corpo=corpo, params=params)
        try:
            dados = r.json()
        except ValueError:
            dados = None
        if not isinstance(dados, dict):
            raise ErroTCM(f"{FONTES[fonte]['nome']} devolveu resposta inesperada em {caminho} "
                          f"({len(r.content)} bytes, começa com {r.text[:80]!r})")
        return dados

    # --- município ----------------------------------------------------------------------------------------------

    def lista_oficial(self, fonte):
        """[(nome para casar, nome a usar na fonte)], lida na hora uma vez por execução."""
        if fonte not in _LISTAS:
            if fonte == "esiproc":
                d = self.json("esiproc", "POST", "/listar-campo", corpo={
                    "numero": None, "termo": None, "campo": "municipio.keyword", "filtros": {},
                    "filtrosLike": None, "filtrosLikeNested": None, "pagina": None,
                    "filtroPeriodoJulgamento": None})
                try:
                    lista = [(b["key"], b["key"]) for b in d["aggregations"]["distinct"]["buckets"]]
                except (KeyError, TypeError) as e:
                    raise ErroTCM("TCM-GO eSiproc devolveu a lista de municípios num formato inesperado") from e
            else:
                d = self.json("tcmjuris", "GET", "/v1/acordao/jurisprudencia/filtros")
                try:
                    lista = [(m["nome"], m["valor"]) for m in d["data"]["municipios"]]
                except (KeyError, TypeError) as e:
                    raise ErroTCM("TCM-GO TCMJuris devolveu a lista de municípios num formato inesperado") from e
            if not lista:
                raise ErroTCM(f"{FONTES[fonte]['nome']} devolveu a lista de municípios vazia")
            _LISTAS[fonte] = lista
        return _LISTAS[fonte]

    def municipio(self, fonte, municipio, *, na_hora=False):
        """O nome do município em uso na fonte ("esiproc" ou "tcmjuris").

        Primeiro o catálogo; se não estiver lá (ou `na_hora`), a lista oficial da fonte, lida na hora.
        Sem casamento exato, `MunicipioNaoEncontrado` com os nomes mais parecidos.
        """
        if not na_hora:
            alvo = _chave(municipio)
            for x in catalogo.carregar():
                nome = (x.get("tcm") or {}).get(fonte)
                if nome and _chave(x["municipio"]) == alvo:
                    return nome
        lista = self.lista_oficial(fonte)
        nomes = [n for n, _ in lista]
        achado = casar(municipio, nomes)
        if achado is None:
            sugestoes = parecidos(municipio, nomes)
            raise MunicipioNaoEncontrado(
                f"{municipio!r} não casa exatamente com nenhum município da lista oficial do {FONTES[fonte]['nome']}"
                + (f". Mais parecidos: {', '.join(sugestoes)}." if sugestoes else ".")
                + " Repita com o nome exato.")
        return dict(lista)[achado]

    # --- consultas ----------------------------------------------------------------------------------------------

    def processos(self, municipio=None, *, tipo=None, ano=None, finalizado=None, relator=None, numero=None,
                  maximo=100) -> dict:
        """Processos eletrônicos do eSiproc. `numero`: NNNNN/AA. Precisa de `municipio` ou de `numero`."""
        from . import esiproc
        if not municipio and not numero:
            raise ValueError("informe o municipio (ou o numero do processo, NNNNN/AA)")
        return self._consultar("esiproc", municipio, maximo, lambda nome: esiproc.processos(
            self, municipio=nome, tipo=tipo, ano=ano, finalizado=finalizado, relator=relator, numero=numero,
            maximo=maximo))

    def acordaos(self, municipio=None, *, texto=None, assunto=None, ano=None, relator=None, maximo=100) -> dict:
        """Acórdãos do TCMJuris (julgados desde 2020). Sem `municipio`, de todos os municípios."""
        from . import tcmjuris
        return self._consultar("tcmjuris", municipio, maximo, lambda nome: tcmjuris.acordaos(
            self, municipio=nome, texto=texto, assunto=assunto, ano=ano, relator=relator, maximo=maximo))

    def _consultar(self, fonte, municipio, maximo, consulta):
        """Resolve o município, consulta e desconfia do zero: as duas fontes respondem total 0, em silêncio, a um
        nome que não conhecem. Com zero, relê a lista oficial de agora; o nome mudou, repete com o novo; o município
        saiu da lista, `MunicipioNaoEncontrado`."""
        if maximo < 1:
            raise ValueError("maximo precisa ser 1 ou mais")
        self.nova_consulta()
        nome = self.municipio(fonte, municipio) if municipio else None
        r = consulta(nome)
        if nome and r["total"] == 0:
            _LISTAS.pop(fonte, None)
            oficial = self.municipio(fonte, municipio, na_hora=True)
            if oficial != nome:
                nome, r = oficial, consulta(oficial)
        if not (r.get("total_e_piso") or r.get("incompleta")) and len(r["registros"]) < min(maximo, r["total"]):
            r = {**r, "incompleta": f"a fonte parou de entregar antes do total ({r['total']})"}
        return _com_avisos(r, nome)

    def ler_acordao(self, document_id) -> dict:
        """O texto do PDF original de um acórdão (`document_id` vem de `acordaos`)."""
        from . import tcmjuris
        self.nova_consulta()
        return tcmjuris.ler_acordao(self, document_id=str(document_id).strip())


def _com_avisos(r, municipio_tcm):
    """Diz em texto o que o módulo da fonte sinalizou: total que é piso e leitura incompleta."""
    saida = dict(r)
    if municipio_tcm:
        saida["municipio_tcm"] = municipio_tcm
    if r.get("total_e_piso"):
        saida["aviso_total"] = (f"o TCM informa {r['total']} ou mais: o total é um piso, não o número exato")
    if r.get("incompleta"):
        saida["aviso_leitura"] = (f"leitura incompleta ({r['incompleta']}): vieram {len(r['registros'])} registros; "
                                  "refine os filtros")
    return saida
