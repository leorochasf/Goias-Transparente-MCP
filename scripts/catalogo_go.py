"""Monta o catálogo de portais de Goiás. Roda à mão, fora do pacote.

  python scripts/catalogo_go.py candidatos --respostas respostas_GO.csv   # endereços por órgão (offline)
  python scripts/catalogo_go.py sondar                                    # uma visita por endereço, 1 s de pausa
  python scripts/catalogo_go.py conferir --municipios "Posse,Trindade"     # conferência ao vivo da amostra
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
    # órgão com portal reconhecível pelo endereço: basta sondar esse portal (aprende sufixos e a variante
    # Megasoft); o site oficial só é sondado quando o órgão não tem portal reconhecível.
    fila = set()
    for o in orgaos:
        reconheciveis = [h for h in o["hosts"] if plataforma_pelo_endereco(h)]
        fila.update(reconheciveis or o["hosts"])
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


def _sondados():
    if not SONDAGEM.exists():
        return {}
    return {x["host"]: x for x in map(json.loads, SONDAGEM.read_text(encoding="utf-8").splitlines()) if x}


#: plataformas que o `Portal` lê (a Megasoft embutida e a Centi entram pelo portal NucleoGov)
CONFERIVEIS = ("nucleogov", "nucleogov-megasoft", "megasoft")
PREFERENCIA = ("nucleogov", "nucleogov-megasoft", "ortrel", "megasoft")


def _portal_escolhido(orgao, sondados):
    """O portal do órgão no catálogo: o que a sondagem viu no ar antes do só reconhecido pelo endereço; entre eles, a
    plataforma na ordem de PREFERENCIA. Devolve (host, plataforma, sondagem); sem plataforma, (host ou None, None, ...)."""
    opcoes = []
    for h in orgao["hosts"]:
        s = sondados.get(h) or {}
        plataforma = s.get("plataforma") or plataforma_pelo_endereco(h)
        if plataforma:
            confirmado = bool(s.get("plataforma"))  # a sondagem viu a marca da plataforma no ar
            opcoes.append((not confirmado, PREFERENCIA.index(plataforma), h, plataforma, s))
    if opcoes:
        return min(opcoes)[2:]
    primeiro = (orgao["hosts"] or [None])[0]
    return primeiro, None, sondados.get(primeiro or "") or {}


def conferir(args):
    from transparencia_municipal.folha_leve import _comparavel
    alvo = {_comparavel(m) for m in args.municipios.split(",")}
    orgaos = [o for o in json.loads(CANDIDATOS.read_text(encoding="utf-8")) if _comparavel(o["municipio"]) in alvo]
    sondados = _sondados()
    feitas = json.loads(CONFERENCIAS.read_text(encoding="utf-8")) if CONFERENCIAS.exists() else {}
    for o in orgaos:
        host, plataforma, _ = _portal_escolhido(o, sondados)  # o mesmo que o `montar` grava
        rotulo = f"{o['municipio']} ({o['orgao']})"
        if plataforma not in CONFERIVEIS:
            print(f"{rotulo}: sem portal NucleoGov nem Megasoft conhecido; fica de fora", flush=True)
            continue
        if host in feitas:
            continue
        portal = Portal(f"https://{host}", navegador=plataforma != "megasoft")  # a Megasoft aceita a ferramenta
        r = conferir_portal(portal, ano=args.ano, mes=args.mes)
        r["sufixos"] = portal.sufixos or {}
        feitas[host] = r
        CONFERENCIAS.write_text(json.dumps(feitas, ensure_ascii=False, indent=1), encoding="utf-8")
        ruins = {k: v for k, v in r["filtros"].items() if v != "ok"}
        print(f"{rotulo} {host} [{plataforma}]: {'tudo ok' if not ruins else ruins}", flush=True)
        time.sleep(args.pausa)


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
    s.add_argument("--municipios", required=True, help="nomes separados por vírgula")
    s.add_argument("--ano", type=int, default=2025)
    s.add_argument("--mes", type=int, default=6)
    s.add_argument("--pausa", type=float, default=2.0)
    s = sub.add_parser("tcm")
    s.add_argument("--pausa", type=float, default=1.0)
    sub.add_parser("montar")
    a = p.parse_args()
    {"candidatos": candidatos, "sondar": sondar, "conferir": conferir, "tcm": tcm, "montar": montar}[a.passo](a)


if __name__ == "__main__":
    main()
