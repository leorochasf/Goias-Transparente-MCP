"""Monta o catálogo de portais de Goiás. Roda à mão, fora do pacote.

  python scripts/catalogo_go.py candidatos --respostas respostas_GO.csv   # endereços por órgão (offline)
  python scripts/catalogo_go.py sondar                                    # uma visita por endereço, 1 s de pausa
  python scripts/catalogo_go.py conferir --municipios "Posse,Trindade"     # conferência ao vivo da amostra
  python scripts/catalogo_go.py conferir --plataformas nucleogov --fatia 1/2 --saida conferencias-frente2.json
  python scripts/catalogo_go.py juntar conferencias-frente1.json conferencias-frente2.json  # no conferencias.json
  python scripts/catalogo_go.py tcm                                       # listas de municípios do TCM-GO (2 consultas)
  python scripts/catalogo_go.py montar                                    # grava transparencia_municipal/catalogo_go.json

Fonte: dados abertos do Radar da Transparência Pública (Atricon), ciclo 2025,
https://radardatransparencia.atricon.org.br/dados/dados_pntp_2025.zip — o arquivo `respostas_<UF>.csv`.
Os arquivos intermediários ficam em scripts/_catalogo/ (fora do git).
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import sys
import time
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from transparencia_municipal.cliente import UA_NAVEGADOR  # noqa: E402
from transparencia_municipal.cliente import Portal  # noqa: E402
from transparencia_municipal.conferencia import conferir as conferir_portal  # noqa: E402
from transparencia_municipal.plataformas import _host, plataforma_pelo_endereco, reconhecer  # noqa: E402

TRABALHO = RAIZ / "scripts" / "_catalogo"
CANDIDATOS = TRABALHO / "candidatos.json"
SONDAGEM = TRABALHO / "sondagem.jsonl"
CONFERENCIAS = TRABALHO / "conferencias.json"
LISTAS_TCM = TRABALHO / "tcm_listas.json"
CATALOGO = RAIZ / "transparencia_municipal" / "catalogo_go.json"
COLUNAS_LINK = ("link_avaliacao", "link_validacao", "link_revisao")
MAX_MUNICIPIOS_POR_HOST = 2  # host em mais municípios é do Estado ou de terceiros, não do órgão


def _orgao(entidade):
    return "camara" if "mara" in entidade.lower() else "prefeitura"


def candidatos(args):
    csv.field_size_limit(10**9)
    por_orgao = collections.defaultdict(collections.Counter)
    municipios_do_host = collections.defaultdict(set)
    nomes = {}
    with open(args.respostas, encoding="utf-8", errors="ignore") as f:
        for r in csv.DictReader(f):
            chave = (r["ibge"], _orgao(r["entidade_nome"]))
            nomes[chave] = {"ibge": r["ibge"], "municipio": r["municipio_nome"], "orgao": chave[1],
                            "entidade": r["entidade_nome"]}
            for c in COLUNAS_LINK:
                for h in re.findall(r"https?://([A-Za-z0-9.-]+)", r.get(c) or ""):
                    h = _host(h)
                    if h.endswith((".go.gov.br", ".go.leg.br", ".megasofttransparencia.com.br")):
                        por_orgao[chave][h] += 1
                        municipios_do_host[h].add(r["ibge"])
    saida = []
    for chave, hosts in sorted(por_orgao.items()):
        proprios = [h for h, _ in hosts.most_common() if len(municipios_do_host[h]) <= MAX_MUNICIPIOS_POR_HOST]
        saida.append({**nomes[chave], "hosts": proprios})
    TRABALHO.mkdir(exist_ok=True)
    CANDIDATOS.write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")
    unicos = {h for o in saida for h in o["hosts"]}
    print(f"{len(saida)} órgãos, {len(unicos)} endereços a sondar -> {CANDIDATOS}")


def sondar(args):
    orgaos = json.loads(CANDIDATOS.read_text(encoding="utf-8"))
    feitos = set()
    if SONDAGEM.exists():
        feitos = {json.loads(ln)["host"] for ln in SONDAGEM.read_text(encoding="utf-8").splitlines() if ln}
    fila = _fila(orgaos, _sondados())
    if args.refazer:  # sondar de novo os endereços que a sondagem anterior classificou assim
        anteriores = _sondados()
        feitos = {h for h in feitos if (anteriores.get(h) or {}).get("plataforma") != args.refazer}
    fila = sorted(fila - feitos)
    print(f"{len(fila)} endereços a sondar ({len(feitos)} já feitos)", flush=True)
    sessao = requests.Session()
    sessao.headers["User-Agent"] = UA_NAVEGADOR
    with SONDAGEM.open("a", encoding="utf-8") as saida:
        for i, host in enumerate(fila, 1):
            if plataforma_pelo_endereco(host) == "megasoft":
                linha = {"host": host, "status": None, **reconhecer("", host)}
            else:
                try:
                    r = sessao.get(f"https://{host}/", timeout=args.timeout)
                    linha = {"host": host, "status": r.status_code, "final": _host(r.url),
                             **reconhecer(r.text if r.status_code == 200 else "", host)}
                except requests.RequestException as e:
                    linha = {"host": host, "status": None, "erro": type(e).__name__, "plataforma": None, "sufixos": {}}
                time.sleep(args.pausa)
            saida.write(json.dumps(linha, ensure_ascii=False) + "\n")
            saida.flush()
            if i % 50 == 0:
                print(f"  {i}/{len(fila)}", flush=True)


PREFIXO_PORTAL = "acessoainformacao."


def _derivados(orgao, sondados):
    """`acessoainformacao.` + o site institucional que a sondagem viu feito pela NucleoGov, quando a origem não trouxe
    o portal (Cumari, Inhumas, Nova Crixás...: o site não serve a API e responde 404; conferência geral, 05/11/2026)."""
    return [PREFIXO_PORTAL + h for h in orgao["hosts"]
            if not plataforma_pelo_endereco(h) and str((sondados.get(h) or {}).get("plataforma") or "").startswith(
                "nucleogov") and PREFIXO_PORTAL + h not in orgao["hosts"]]


def _fila(orgaos, sondados):
    """Endereços a sondar. Órgão com portal reconhecível pelo endereço: basta esse portal (aprende sufixos e a
    variante Megasoft); o site oficial só é sondado quando o órgão não tem portal reconhecível. Mais os portais
    derivados dos sites institucionais já sondados (rode o `sondar` de novo depois da 1ª vez)."""
    fila = set()
    for o in orgaos:
        reconheciveis = [h for h in o["hosts"] if plataforma_pelo_endereco(h)]
        fila.update(reconheciveis or o["hosts"])
        fila.update(_derivados(o, sondados))
    return fila


def _sondados():
    if not SONDAGEM.exists():
        return {}
    return {x["host"]: x for x in map(json.loads, SONDAGEM.read_text(encoding="utf-8").splitlines()) if x}


#: plataformas que o `Portal` lê (a Megasoft embutida e a Centi entram pelo portal NucleoGov)
CONFERIVEIS = ("nucleogov", "nucleogov-megasoft", "megasoft", "ortrel")
#: as que aceitam a identificação da ferramenta (os portais NucleoGov respondem 403 a ela)
SEM_NAVEGADOR = ("megasoft", "ortrel")
PREFERENCIA = ("nucleogov", "nucleogov-megasoft", "ortrel", "megasoft")


def _portal_escolhido(orgao, sondados):
    """O portal do órgão no catálogo: o que a sondagem viu no ar antes do só reconhecido pelo endereço; entre eles, o
    portal `acessoainformacao.` antes do site institucional, e a plataforma na ordem de PREFERENCIA. Devolve (host, plataforma, sondagem); sem plataforma, (host ou None, None, ...)."""
    opcoes = []
    derivados = _derivados(orgao, sondados)
    for h in orgao["hosts"] + derivados:
        s = sondados.get(h) or {}
        plataforma = s.get("plataforma") or (plataforma_pelo_endereco(h) if h not in derivados else None)
        if plataforma:
            confirmado = bool(s.get("plataforma"))  # a sondagem viu a marca da plataforma no ar
            # entre os confirmados, o portal da transparência (`acessoainformacao.`) vence o site institucional
            # que também mostra a marca NucleoGov (Abadia de Goiás, conferência geral de 05/11/2026)
            portal = bool(plataforma_pelo_endereco(h))
            opcoes.append((not confirmado, not portal, PREFERENCIA.index(plataforma), h, plataforma, s))
    if opcoes:
        return min(opcoes)[3:]
    primeiro = (orgao["hosts"] or [None])[0]
    return primeiro, None, sondados.get(primeiro or "") or {}


def _selecionar(orgaos, sondados, *, municipios=None, todos=False, plataformas=None, fatia=None):
    """Os órgãos a conferir, como (órgão, host, plataforma), em ordem alfabética de município.

    `municipios`: só esses; `todos` ou `plataformas` sem `municipios`: todos os órgãos com plataforma.
    `fatia` (k, n): a k-ésima de n partes contíguas da lista já filtrada; as n partes cobrem a lista sem repetir.
    """
    from transparencia_municipal.folha_leve import _comparavel
    alvo = {_comparavel(m) for m in municipios} if municipios else None
    selecao = []
    for o in orgaos:
        if alvo is not None and _comparavel(o["municipio"]) not in alvo:
            continue
        host, plataforma, _ = _portal_escolhido(o, sondados)  # o mesmo que o `montar` grava
        if alvo is None and not plataforma:
            continue
        if plataformas and plataforma not in plataformas:
            continue
        selecao.append((o, host, plataforma))
    selecao.sort(key=lambda x: (_comparavel(x[0]["municipio"]), x[0]["orgao"], x[1] or ""))
    if fatia:
        k, n = fatia
        selecao = selecao[(k - 1) * len(selecao) // n:k * len(selecao) // n]
    return selecao


def _fatia(texto):
    """'1/2' → (1, 2)."""
    try:
        k, n = map(int, texto.split("/"))
    except ValueError:
        raise argparse.ArgumentTypeError(f"fatia {texto!r}: use k/n, por exemplo 1/2") from None
    if not 1 <= k <= n:
        raise argparse.ArgumentTypeError(f"fatia {texto!r}: k vai de 1 a n")
    return k, n


def _plataformas(texto):
    nomes = [p.strip() for p in texto.split(",") if p.strip()]
    desconhecidas = [p for p in nomes if p not in PREFERENCIA]
    if desconhecidas or not nomes:
        raise argparse.ArgumentTypeError(f"plataforma desconhecida {desconhecidas}; use {', '.join(PREFERENCIA)}")
    return nomes


def _no_trabalho(nome):
    """Arquivo de saída: nome relativo fica em scripts/_catalogo/; caminho absoluto fica onde está."""
    return TRABALHO / nome


def conferir(args):
    selecao = _selecionar(json.loads(CANDIDATOS.read_text(encoding="utf-8")), _sondados(),
                          municipios=args.municipios, todos=args.todos, plataformas=args.plataformas, fatia=args.fatia)
    saida = _no_trabalho(args.saida)
    feitas = json.loads(saida.read_text(encoding="utf-8")) if saida.exists() else {}
    print(f"{len(selecao)} órgãos selecionados; {sum(1 for _, h, _ in selecao if h in feitas)} já conferidos "
          f"em {saida.name}", flush=True)
    for o, host, plataforma in selecao:
        rotulo = f"{o['municipio']} ({o['orgao']})"
        if plataforma not in CONFERIVEIS:
            print(f"{rotulo}: plataforma {plataforma or 'desconhecida'}, que a conferência não lê; fica de fora",
                  flush=True)
            continue
        if host in feitas:  # retomada
            continue
        # a câmara Ortrel é reconhecida pelo catálogo, como no MCP; a Megasoft, pelo endereço
        portal = Portal(f"https://{host}", navegador=plataforma not in SEM_NAVEGADOR,
                        plataforma="ortrel" if plataforma == "ortrel" else None)
        r = conferir_portal(portal, ano=args.ano, mes=args.mes)
        r["sufixos"] = portal.sufixos or {}
        feitas[host] = r
        saida.parent.mkdir(parents=True, exist_ok=True)
        saida.write_text(json.dumps(feitas, ensure_ascii=False, indent=1), encoding="utf-8")
        ruins = {k: v for k, v in r["filtros"].items() if v != "ok"}
        print(f"{rotulo} {host} [{plataforma}]: {'tudo ok' if not ruins else ruins}", flush=True)
        time.sleep(args.pausa)


def juntar(args):
    """Junta as saídas das frentes no conferencias.json. Endereço repetido: fica a conferência mais recente; na mesma
    data (sem hora), a do arquivo juntado, que é a rodada posterior."""
    junto = json.loads(CONFERENCIAS.read_text(encoding="utf-8")) if CONFERENCIAS.exists() else {}
    novas = substituidas = mantidas = 0
    for nome in args.arquivos:
        for host, r in json.loads(_no_trabalho(nome).read_text(encoding="utf-8")).items():
            antiga = junto.get(host)
            if antiga is None:
                novas += 1
            elif r["data"] >= antiga["data"]:
                substituidas += 1
            else:
                mantidas += 1
                continue
            junto[host] = r
    CONFERENCIAS.write_text(json.dumps(junto, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{novas} novas, {substituidas} atualizadas, {mantidas} mantidas (a antiga era mais recente); "
          f"{len(junto)} endereços -> {CONFERENCIAS}")


def tcm(args):
    """As listas oficiais de municípios das duas fontes do TCM-GO: `/listar-campo` do eSiproc e `/filtros` do TCMJuris."""
    from transparencia_municipal.tcm import FONTES, ClienteTCM
    cliente = ClienteTCM(pausa=args.pausa)
    listas = {fonte: cliente.lista_oficial(fonte) for fonte in FONTES}
    TRABALHO.mkdir(exist_ok=True)
    LISTAS_TCM.write_text(json.dumps({"data": time.strftime("%Y-%m-%d"), **listas}, ensure_ascii=False, indent=0),
                          encoding="utf-8")
    print(f"eSiproc: {len(listas['esiproc'])} municípios; TCMJuris: {len(listas['tcmjuris'])} -> {LISTAS_TCM}")


def _nomes_tcm(municipios):
    """município do catálogo → {"esiproc": nome, "tcmjuris": valor}; sem casamento exato único, None (a verificar)."""
    from transparencia_municipal.tcm import casar
    if not LISTAS_TCM.exists():  # sem as listas, o montar gravaria o catálogo sem a ponte com o TCM, em silêncio
        raise SystemExit(f"falta {LISTAS_TCM}: rode antes `python scripts/catalogo_go.py tcm`")
    listas = json.loads(LISTAS_TCM.read_text(encoding="utf-8"))
    saida = {}
    for m in municipios:
        saida[m] = {}
        for fonte in ("esiproc", "tcmjuris"):
            achado = casar(m, [n for n, _ in listas[fonte]])
            saida[m][fonte] = dict(map(tuple, listas[fonte]))[achado] if achado else None
    for fonte in ("esiproc", "tcmjuris"):
        sem = sorted(m for m, x in saida.items() if not x[fonte])
        print(f"TCM {fonte}: {len(saida) - len(sem)} de {len(saida)} municípios casaram"
              + (f"; a verificar: {', '.join(sem)}" if sem else ""))
    return saida


def montar(args):
    """Um registro por órgão: o portal preferido, a plataforma, os sufixos e a conferência, se houver."""
    sondados, conferencias = _sondados(), (json.loads(CONFERENCIAS.read_text(encoding="utf-8"))
                                           if CONFERENCIAS.exists() else {})
    catalogo = []
    orgaos = json.loads(CANDIDATOS.read_text(encoding="utf-8"))
    nomes_tcm = _nomes_tcm(sorted({o["municipio"] for o in orgaos}))
    for o in orgaos:
        host, plataforma, s = _portal_escolhido(o, sondados)
        origem = ("sondagem" if s.get("plataforma") else "endereco") if plataforma else None
        conferencia = conferencias.get(host)
        # só a conferência grava sufixos: ela aprende com o código atual (módulos Megasoft e Centi inclusive).
        # Sem conferência, o cliente lê a página inicial na primeira consulta.
        sufixos = (conferencia or {}).pop("sufixos", None) or {}
        catalogo.append({
            "ibge": o["ibge"], "municipio": o["municipio"], "orgao": o["orgao"],
            "portal": f"https://{host}" if host else None, "plataforma": plataforma, "origem": origem,
            "sufixos": sufixos, "outros_enderecos": [h for h in o["hosts"] if h != host],
            "conferencia": conferencia,
            "tcm": nomes_tcm[o["municipio"]],
        })
    CATALOGO.write_text(json.dumps(catalogo, ensure_ascii=False, indent=0), encoding="utf-8")
    contagem = collections.Counter(x["plataforma"] for x in catalogo)
    print(f"{len(catalogo)} órgãos -> {CATALOGO.name}: {dict(contagem)}; "
          f"conferidos: {sum(1 for x in catalogo if x['conferencia'])}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="passo", required=True)
    s = sub.add_parser("candidatos")
    s.add_argument("--respostas", required=True)
    s = sub.add_parser("sondar")
    s.add_argument("--pausa", type=float, default=1.0)
    s.add_argument("--timeout", type=int, default=20)
    s.add_argument("--refazer", help="plataforma cujos endereços devem ser sondados de novo")
    s = sub.add_parser("conferir")
    s.add_argument("--municipios", type=lambda t: t.split(","), help="nomes separados por vírgula")
    s.add_argument("--todos", action="store_true", help="todos os órgãos do catálogo com plataforma")
    s.add_argument("--plataformas", type=_plataformas, help=f"separadas por vírgula, entre {', '.join(PREFERENCIA)}")
    s.add_argument("--fatia", type=_fatia, help="k/n: a k-ésima de n partes, em ordem alfabética de município")
    s.add_argument("--saida", default=CONFERENCIAS.name, help="arquivo desta frente, em scripts/_catalogo/")
    s.add_argument("--ano", type=int, default=2025)
    s.add_argument("--mes", type=int, default=6)
    s.add_argument("--pausa", type=float, default=2.0)
    s = sub.add_parser("juntar")
    s.add_argument("arquivos", nargs="+", help="saídas das frentes, em scripts/_catalogo/")
    s = sub.add_parser("tcm")
    s.add_argument("--pausa", type=float, default=1.0)
    sub.add_parser("montar")
    a = p.parse_args()
    if a.passo == "conferir" and not (a.municipios or a.todos or a.plataformas):
        p.error("conferir: diga --municipios, --todos ou --plataformas")
    {"candidatos": candidatos, "sondar": sondar, "conferir": conferir, "juntar": juntar, "tcm": tcm,
     "montar": montar}[a.passo](a)


if __name__ == "__main__":
    main()
