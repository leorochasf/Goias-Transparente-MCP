"""Conferência: mede ao vivo se um portal respeita cada filtro que o cliente manda (NucleoGov, Megasoft, Centi).

Os exemplos saem do próprio portal: o CNPJ é um fornecedor das despesas dele, os órgãos são os da folha dele.
O portal ignora filtro desconhecido em silêncio (docs/portal-nucleogov.md), e por isso cada filtro é conferido
nos dados que voltam. Resultado de cada filtro: ok, falhou, sem_dados ou erro.
"""
from __future__ import annotations

import calendar
import re
import time
from collections import Counter
from datetime import date, datetime

from .cliente import FONTE, ModuloNaoSuportado

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


def _mes_mais_recente_da_folha(p, ano_atual):
    """Sem `mes`, o portal devolve o mês mais recente do ano (docs/portal-nucleogov.md)."""
    for ano in (ano_atual, ano_atual - 1):
        try:
            regs = p.folha(ano, maximo=1)["registros"]
        except ValueError:  # a Megasoft embutida só lê a folha com o mês
            return None
        if regs:
            return int(regs[0]["ano"]), int(regs[0]["mes"])
    return None


def _folha(p, ano, mes, contexto):
    base, nota = p.folha(ano, mes, maximo=100), None
    if not base["registros"]:  # muitos portais só publicam os meses recentes da folha
        recente = _mes_mais_recente_da_folha(p, contexto["ano_atual"])
        if not recente:
            return "sem_dados", f"folha de {mes:02d}/{ano} vazia, e nenhuma folha recente"
        nota = (f"a folha de {mes:02d}/{ano} está vazia; conferida em {recente[1]:02d}/{recente[0]}, "
                "o mês mais recente publicado")
        ano, mes = recente
        base = p.folha(ano, mes, maximo=100)
    contexto["folha"], contexto["folha_ref"] = base, (ano, mes)
    regs = base["registros"]
    if not regs:
        return "sem_dados", f"folha de {mes:02d}/{ano} vazia"
    fora = [(x.get("ano"), x.get("mes")) for x in regs if (int(x.get("ano") or 0), int(x.get("mes") or 0)) != (ano, mes)]
    return ("falhou", f"pediu {mes:02d}/{ano}, vieram {sorted(set(fora))}") if fora else ("ok", nota)


def _folha_orgaos(p, ano, mes, contexto):
    ano, mes = contexto.get("folha_ref", (ano, mes))
    regs = contexto["folha"]["registros"] if "folha" in contexto else p.folha(ano, mes, maximo=100)["registros"]
    outra = next((x["fonte"] for x in regs if x.get("fonte", FONTE) != FONTE), None)
    if outra:
        return "sem_dados", f"a folha vem da {outra}: a sondagem de órgãos escondidos é só do NucleoGov"
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


def _mes_inteiro(ano, mes):
    """O 1º e o último dia do mês. A Centi devolve o período inteiro numa resposta só: um mês por vez."""
    return date(ano, mes, 1), date(ano, mes, calendar.monthrange(ano, mes)[1])


def _despesas_periodo(p, ano, mes, contexto):
    de, ate = _mes_inteiro(ano, mes)
    r = p.despesas(de.isoformat(), ate.isoformat(), maximo=20)
    contexto["despesas"] = r
    datas = [_data(x.get("data")) for x in r["registros"]]
    if not datas:
        return "sem_dados", f"nenhuma despesa em {mes:02d}/{ano}"
    fora = sorted({d.isoformat() for d in datas if d and not de <= d <= ate})
    return ("falhou", f"pediu {de}..{ate}, vieram {fora[:5]}") if fora else ("ok", None)


def _despesas_cnpj(p, ano, mes, contexto):
    regs = contexto["despesas"]["registros"] if "despesas" in contexto else []
    cnpjs = Counter(x.get("cpf_cnpj") for x in regs if len(_digitos(x.get("cpf_cnpj"))) == 14)
    if not cnpjs:
        return "sem_dados", f"nenhum CNPJ nas despesas de {mes:02d}/{ano}"
    cnpj = cnpjs.most_common(1)[0][0]
    de, ate = _mes_inteiro(ano, mes)
    r = p.despesas(de.isoformat(), ate.isoformat(), cnpj, maximo=20)
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


def _ano_do_ato(x):
    """O campo `ano`; sem ele (6 portais em 04/11/2026), o ano da data de publicação."""
    if x.get("ano"):
        return str(x["ano"])
    data = _data(x.get("data_publicacao") or x.get("data"))
    return str(data.year) if data else None


def _legislacao_ano(p, ano, mes, contexto):
    todos = contexto.get("decretos") or p.legislacao("DECRETO", maximo=20)
    do_ano = p.legislacao("DECRETO", ano=ano, maximo=20)
    if not do_ano["registros"]:
        return "sem_dados", f"nenhum decreto de {ano}"
    fora = sorted({_ano_do_ato(x) for x in do_ano["registros"] if _ano_do_ato(x) != str(ano)}, key=str)
    if fora:
        return "falhou", f"pediu {ano}, vieram {fora}"
    if do_ano["total"] >= todos["total"] and {_ano_do_ato(x) for x in todos["registros"]} != {str(ano)}:
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
    hoje = hoje or date.today().isoformat()
    ano_atual = int(hoje[:4]) if hoje[:4].isdigit() else date.today().year
    filtros, detalhes, contexto = {}, {}, {"ano_atual": ano_atual}
    for i, (nome, verificar) in enumerate(VERIFICACOES.items()):
        if i:
            time.sleep(pausa)
        try:
            filtros[nome], detalhe = verificar(portal, ano, mes, contexto)
        except ModuloNaoSuportado as e:
            filtros[nome], detalhe = "nao_suportado", str(e)
        except Exception as e:  # noqa: BLE001 - o portal pode falhar de qualquer jeito; registra e segue
            filtros[nome], detalhe = "erro", f"{type(e).__name__}: {e}"
        if detalhe:
            detalhes[nome] = detalhe
    return {"data": hoje, "referencia": f"{mes:02d}/{ano}",
            "filtros": filtros, "detalhes": detalhes}
