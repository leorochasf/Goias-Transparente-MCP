"""Conferência: mede ao vivo se um portal NucleoGov respeita cada filtro que o cliente manda.

Os exemplos saem do próprio portal: o CNPJ é um fornecedor das despesas dele, os órgãos são os da folha dele.
O portal ignora filtro desconhecido em silêncio (docs/portal-nucleogov.md), e por isso cada filtro é conferido
nos dados que voltam. Resultado de cada filtro: ok, falhou, sem_dados ou erro.
"""
from __future__ import annotations

import re
import time
from collections import Counter
from datetime import date, datetime

ORGAOS_SONDADOS = range(1, 11)


def _data(texto):
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(texto)[:10], formato).date()
        except ValueError:
            pass
    return None


def _digitos(texto):
    return re.sub(r"\D", "", str(texto or ""))


def _folha(p, ano, mes, contexto):
    base = p.folha(ano, mes, maximo=100)
    contexto["folha"] = base
    regs = base["registros"]
    if not regs:
        return "sem_dados", f"folha de {mes:02d}/{ano} vazia"
    fora = [(x.get("ano"), x.get("mes")) for x in regs if (int(x.get("ano") or 0), int(x.get("mes") or 0)) != (ano, mes)]
    return ("falhou", f"pediu {mes:02d}/{ano}, vieram {sorted(set(fora))}") if fora else ("ok", None)


def _folha_orgaos(p, ano, mes, contexto):
    regs = contexto["folha"]["registros"] if "folha" in contexto else p.folha(ano, mes, maximo=100)["registros"]
    ids = {x.get("orgao_id") for x in regs if x.get("orgao_id")}
    if not ids:
        return "sem_dados", "a folha não traz orgao_id"
    if len(ids) > 1:
        return "ok", None
    unico = next(iter(ids))  # a 1ª página pode vir de um órgão só por causa da ordem: comparar totais
    sufixo = (getattr(p, "sufixos", None) or {}).get("servidores", "frl")

    def total_do_orgao(codigo):
        filtros = {"ano": str(ano), "mes": str(mes), "orgao": codigo}
        return p.consultar(f"servidores_{sufixo}/listar", filtros, maximo=1)["total"]

    total_sem_filtro = (contexto.get("folha") or {}).get("total") or len(regs)
    if total_sem_filtro > total_do_orgao(unico):
        return "ok", None
    escondidos = []
    for n in ORGAOS_SONDADOS:
        codigo = str(n).zfill(len(unico))
        if codigo == unico:
            continue
        total = total_do_orgao(codigo)
        if total == total_sem_filtro:
            return "sem_dados", "o portal ignora o filtro de órgão; não dá para conferir"
        if total > 0:
            escondidos.append(codigo)
    if escondidos:
        return "falhou", f"sem filtro só vem o órgão {unico}; com filtro aparecem {', '.join(escondidos)}"
    return "ok", None


def _despesas_periodo(p, ano, mes, contexto):
    de, ate = date(ano, 1, 1), date(ano, 3, 31)
    r = p.despesas(de.isoformat(), ate.isoformat(), maximo=20)
    contexto["despesas"] = r
    datas = [_data(x.get("data")) for x in r["registros"]]
    if not datas:
        return "sem_dados", "nenhuma despesa no 1º trimestre"
    fora = sorted({d.isoformat() for d in datas if d and not de <= d <= ate})
    return ("falhou", f"pediu {de}..{ate}, vieram {fora[:5]}") if fora else ("ok", None)


def _despesas_cnpj(p, ano, mes, contexto):
    regs = contexto["despesas"]["registros"] if "despesas" in contexto else []
    cnpjs = Counter(x.get("cpf_cnpj") for x in regs if len(_digitos(x.get("cpf_cnpj"))) == 14)
    if not cnpjs:
        return "sem_dados", "nenhum CNPJ nas despesas do 1º trimestre"
    cnpj = cnpjs.most_common(1)[0][0]
    r = p.despesas(f"{ano}-01-01", f"{ano}-03-31", cnpj, maximo=20)
    outros = sorted({x.get("cpf_cnpj") for x in r["registros"] if _digitos(x.get("cpf_cnpj")) != _digitos(cnpj)})
    if not r["registros"]:
        return "falhou", f"a busca por {cnpj}, que aparece nas despesas, voltou vazia"
    return ("falhou", f"buscou {cnpj}, vieram também {outros[:3]}") if outros else ("ok", None)


def _receitas(p, ano, mes, contexto):
    regs = p.receitas(ano, mes, maximo=20)["registros"]
    if not regs:
        return "sem_dados", f"receitas de {mes:02d}/{ano} vazias"
    fora = sorted({(x.get("ano"), x.get("mes")) for x in regs if (int(x.get("ano") or 0), int(x.get("mes") or 0)) != (ano, mes)})
    return ("falhou", f"pediu {mes:02d}/{ano}, vieram {fora[:5]}") if fora else ("ok", None)


def _legislacao_tipo(p, ano, mes, contexto):
    decretos, portarias = p.legislacao("DECRETO", maximo=20), p.legislacao("PORTARIA", maximo=20)
    contexto["decretos"] = decretos
    if not decretos["registros"]:
        return "sem_dados", "nenhum decreto"
    tipos = {x.get("tipo") for x in decretos["registros"]}, {x.get("tipo") for x in portarias["registros"]}
    ok = tipos[0] == {"1"} and tipos[1] <= {"2"}
    return ("ok", None) if ok else ("falhou", f"decretos com tipo {sorted(tipos[0])}, portarias com {sorted(tipos[1])}")


def _legislacao_ano(p, ano, mes, contexto):
    todos = contexto.get("decretos") or p.legislacao("DECRETO", maximo=20)
    do_ano = p.legislacao("DECRETO", ano=ano, maximo=20)
    if not do_ano["registros"]:
        return "sem_dados", f"nenhum decreto de {ano}"
    fora = sorted({x.get("ano") for x in do_ano["registros"] if str(x.get("ano")) != str(ano)})
    if fora:
        return "falhou", f"pediu {ano}, vieram {fora}"
    if do_ano["total"] >= todos["total"] and {str(x.get("ano")) for x in todos["registros"]} != {str(ano)}:
        return "falhou", f"o total com ano ({do_ano['total']}) não é menor que sem ano ({todos['total']})"
    return "ok", None


VERIFICACOES = {
    "folha_mes": _folha, "folha_orgaos": _folha_orgaos,
    "despesas_periodo": _despesas_periodo, "despesas_cnpj": _despesas_cnpj,
    "receitas_mes": _receitas, "legislacao_tipo": _legislacao_tipo, "legislacao_ano": _legislacao_ano,
}


def conferir(portal, *, ano, mes, hoje=None, pausa=1.0):
    """Confere os filtros de um portal num mês de referência. Uma verificação que quebra não derruba as outras.

    `pausa`: segundos entre as verificações (são umas 9 consultas por portal).
    """
    filtros, detalhes, contexto = {}, {}, {}
    for i, (nome, verificar) in enumerate(VERIFICACOES.items()):
        if i:
            time.sleep(pausa)
        try:
            filtros[nome], detalhe = verificar(portal, ano, mes, contexto)
        except Exception as e:  # noqa: BLE001 - o portal pode falhar de qualquer jeito; registra e segue
            filtros[nome], detalhe = "erro", f"{type(e).__name__}: {e}"
        if detalhe:
            detalhes[nome] = detalhe
    return {"data": hoje or date.today().isoformat(), "referencia": f"{mes:02d}/{ano}",
            "filtros": filtros, "detalhes": detalhes}
