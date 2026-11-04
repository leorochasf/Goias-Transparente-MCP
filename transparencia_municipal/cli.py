"""Linha de comando, para quem não usa assistente de IA.

  python -m transparencia_municipal.cli --portal https://acessoainformacao.cidade.go.gov.br \
      --csv folha.csv folha --ano 2025 --mes 3 --busca "Fulano de Tal"
"""
from __future__ import annotations

import argparse
import csv
import json
import sys

from .cliente import ErroPortal, Portal

for _saida in (sys.stdout, sys.stderr):  # stderr: o erro sai por SystemExit
    try:
        _saida.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _gravar(registros, csv_saida, json_saida):
    if json_saida:
        with open(json_saida, "w", encoding="utf-8") as f:
            json.dump(registros, f, ensure_ascii=False, indent=1)
        print(f"{len(registros)} registros em {json_saida}")
    if csv_saida and registros:
        colunas = list({c: None for r in registros for c in r})
        with open(csv_saida, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=colunas, extrasaction="ignore")
            w.writeheader()
            w.writerows(registros)
        print(f"{len(registros)} registros em {csv_saida}")


def _parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--portal", required=True, help="https://acessoainformacao.<municipio>.go.gov.br")
    p.add_argument("--navegador", action="store_true",
                   help="identificar-se como navegador (ver README, seção 'O 403')")
    p.add_argument("--maximo", type=int, default=200, help="teto de registros (padrão 200)")
    p.add_argument("--pausa", type=float, default=1.0, help="segundos entre páginas (padrão 1)")
    p.add_argument("--csv"), p.add_argument("--json")
    sub = p.add_subparsers(dest="modulo", required=True)

    s = sub.add_parser("folha", help="servidores e remuneração")
    s.add_argument("--ano", type=int, required=True); s.add_argument("--mes", type=int)
    s.add_argument("--busca", help="nome do servidor (a folha não busca por cargo)")
    s = sub.add_parser("despesas", help="empenhos e pagamentos")
    s.add_argument("--de", required=True); s.add_argument("--ate", required=True)
    s.add_argument("--busca", help="nome ou CNPJ do fornecedor")
    s = sub.add_parser("contratos")
    s.add_argument("--ano", type=int); s.add_argument("--tipo", default="contrato",
                                                     choices=["contrato", "aditivo"])
    s.add_argument("--busca")
    s = sub.add_parser("licitacoes")
    s.add_argument("--dispensas", action="store_true"); s.add_argument("--busca")
    s = sub.add_parser("receitas", help="receitas de um mês (para um período, um mês por vez)")
    s.add_argument("--ano", type=int, required=True); s.add_argument("--mes", type=int, required=True)
    s = sub.add_parser("legislacao", help="decretos, portarias e resoluções")
    s.add_argument("--tipo", default="DECRETO", help="DECRETO (padrão), PORTARIA, RESOLUCAO ou o código")
    s.add_argument("--busca", help="palavra na ementa"); s.add_argument("--ano", type=int)
    return p


def main(argv=None):
    a = _parser().parse_args(argv)
    portal = Portal(a.portal, navegador=a.navegador, pausa=a.pausa)
    try:
        if a.modulo == "folha":
            r = portal.folha(a.ano, a.mes, a.busca, maximo=a.maximo)
        elif a.modulo == "despesas":
            r = portal.despesas(a.de, a.ate, a.busca, maximo=a.maximo)
        elif a.modulo == "contratos":
            r = portal.contratos(a.ano, a.tipo, a.busca, maximo=a.maximo)
        elif a.modulo == "licitacoes":
            r = portal.licitacoes(a.busca, dispensas=a.dispensas, maximo=a.maximo)
        elif a.modulo == "receitas":
            r = portal.receitas(a.ano, a.mes, maximo=a.maximo)
        else:
            r = portal.legislacao(a.tipo, a.busca, ano=a.ano, maximo=a.maximo)
    except (ErroPortal, ValueError) as e:
        raise SystemExit(f"ERRO: {e}")
    print(f"{r['total']} registros no portal; {len(r['registros'])} trazidos.")
    if not (a.csv or a.json):
        print(json.dumps(r["registros"][:5], ensure_ascii=False, indent=1))
        print("(mostrando até 5; use --csv ou --json para salvar tudo)")
    _gravar(r["registros"], a.csv, a.json)


if __name__ == "__main__":
    main()
