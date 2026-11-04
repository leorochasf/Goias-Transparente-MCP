"""Monta o catálogo de portais de Goiás. Roda à mão, fora do pacote.

  python scripts/catalogo_go.py candidatos --respostas respostas_GO.csv   # endereços por órgão (offline)
  python scripts/catalogo_go.py sondar                                    # uma visita por endereço, 1 s de pausa
  python scripts/catalogo_go.py conferir --municipios "Posse,Trindade"     # conferência ao vivo da amostra
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


def _portal_nucleogov(orgao, sondados):
    """O endereço NucleoGov do órgão: o reconhecido pelo endereço ou o que a sondagem confirmou."""
    for h in orgao["hosts"]:
        plataforma = (sondados.get(h) or {}).get("plataforma") or plataforma_pelo_endereco(h)
        if plataforma in ("nucleogov", "nucleogov-megasoft"):
            return h, plataforma
    return None, None


def conferir(args):
    from transparencia_municipal.folha_leve import _comparavel
    alvo = {_comparavel(m) for m in args.municipios.split(",")}
    orgaos = [o for o in json.loads(CANDIDATOS.read_text(encoding="utf-8")) if _comparavel(o["municipio"]) in alvo]
    sondados = _sondados()
    feitas = json.loads(CONFERENCIAS.read_text(encoding="utf-8")) if CONFERENCIAS.exists() else {}
    for o in orgaos:
        host, plataforma = _portal_nucleogov(o, sondados)
        rotulo = f"{o['municipio']} ({o['orgao']})"
        if not host:
            print(f"{rotulo}: sem portal NucleoGov conhecido; fica de fora", flush=True)
            continue
        if host in feitas:
            continue
        portal = Portal(f"https://{host}", navegador=True)
        r = conferir_portal(portal, ano=args.ano, mes=args.mes)
        r["sufixos"] = portal.sufixos or {}
        feitas[host] = r
        CONFERENCIAS.write_text(json.dumps(feitas, ensure_ascii=False, indent=1), encoding="utf-8")
        ruins = {k: v for k, v in r["filtros"].items() if v != "ok"}
        print(f"{rotulo} {host} [{plataforma}]: {'tudo ok' if not ruins else ruins}", flush=True)
        time.sleep(args.pausa)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="passo", required=True)
    s = sub.add_parser("candidatos")
    s.add_argument("--respostas", required=True)
    s = sub.add_parser("sondar")
    s.add_argument("--pausa", type=float, default=1.0)
    s.add_argument("--timeout", type=int, default=20)
    s = sub.add_parser("conferir")
    s.add_argument("--municipios", required=True, help="nomes separados por vírgula")
    s.add_argument("--ano", type=int, default=2025)
    s.add_argument("--mes", type=int, default=6)
    s.add_argument("--pausa", type=float, default=2.0)
    a = p.parse_args()
    {"candidatos": candidatos, "sondar": sondar, "conferir": conferir}[a.passo](a)


if __name__ == "__main__":
    main()
