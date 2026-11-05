"""Diárias dos portais NucleoGov (`diarias_cnt`/`diarias_frl`). Encaixe do ticket 05; único arquivo dele.

O `Portal` manda para cá as diárias de todo portal NucleoGov que não as tenha em `sgdiarias` (estas vão para a
Megasoft embutida). Interface, nomes comuns dos campos e marcas da resposta: ticket 01 dos módulos extras, seção
`## Comments`. Consultas medidas: docs/design/2026-11-04-modulos-extras.md, seção D da descoberta.

Medido ao vivo em 04/11/2026 (1º trimestre de 2025):
- `datamin`/`datamax` (aaaa-mm-dd) recortam pela data de saída (`data_inicio` em Posse, `data_saida` em Senador
  Canedo). Mesmo assim cada linha é conferida: saída fora do período é erro, nunca mistura.
- `txtbusca` responde zero mesmo com a palavra presente (nos dois portais): a busca é feita aqui, sobre o período
  inteiro.
- Posse: sem `orgao`, só vem o órgão principal (o filtro `orgao` é respeitado; os órgãos 1, 4 e 5 não tinham
  diárias). Não há sondagem dos outros órgãos: a resposta avisa em `ressalvas`.
- Senador Canedo: valor, quantidade, cargo e chegada vazios em todas; destino " - ".
"""
from __future__ import annotations

import sys
import unicodedata
from datetime import date, datetime

from .cliente import ErroPortal

FONTE = "NucleoGov"


def _texto(valor):
    """Texto limpo; vazio e o " - " que alguns portais põem no lugar do vazio viram None."""
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto if texto.strip(" -") else None


def _dia(valor):
    """dd/mm/aaaa, aaaa-mm-dd ou aaaa-mm-dd hh:mm:ss → `date`; outra coisa → None."""
    texto = _texto(valor)
    for formato, tamanho in (("%d/%m/%Y", 10), ("%Y-%m-%d", 10)):
        try:
            return datetime.strptime(texto[:tamanho], formato).date()
        except (TypeError, ValueError):
            continue
    return None


def _data(valor):
    """A data em dd/mm/aaaa; o que não for data sai como veio."""
    dia = _dia(valor)
    return dia.strftime("%d/%m/%Y") if dia else _texto(valor)


def _valor(valor):
    """1100 → "1.100,00"; texto já em reais fica como veio; vazio → None (nunca zero)."""
    if isinstance(valor, str):
        texto = _texto(valor)
        if texto is None or "," in texto:
            return texto
        try:
            valor = float(texto)
        except ValueError:
            return texto
    if valor is None:
        return None
    return f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _sem_acento(texto):
    return unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().upper()


def _destino(reg):
    """Posse dá o destino em texto livre e a `cidade` padronizada: junta os dois sem repetir a cidade."""
    destino, cidade = _texto(reg.get("destino")), _texto(reg.get("cidade"))
    if destino and cidade and _sem_acento(cidade) not in _sem_acento(destino):
        return f"{destino} ({cidade})"
    return destino or cidade


def _saida(reg):
    return reg.get("data_saida") or reg.get("data_inicio")


def diaria(reg):
    """Uma diária de Posse (`diarias_cnt`) ou de Senador Canedo (`diarias_frl`) com os nomes comuns.

    `empenho` fica None: `id_empenho` (Posse) é a chave interna do portal, não o número do empenho.
    """
    quantidade = reg.get("quantidade")
    return {
        "favorecido": _texto(reg.get("favorecido")),
        "matricula": None,
        "cargo": _texto(reg.get("cargo")),
        "orgao": _texto(reg.get("orgao_nome") or reg.get("orgao")),
        "destino": _destino(reg),
        "motivo": _texto(reg.get("descricao") or reg.get("motivo") or reg.get("descricao_produto")),
        "data_saida": _data(_saida(reg)),
        "data_chegada": _data(reg.get("data_chegada") or reg.get("data_fim")),
        "quantidade": _texto(quantidade),
        "valor": _valor(reg.get("valor")),
        "valor_unitario": None,
        "empenho": None,
        "fonte": FONTE,
    }


def _casa(registro, busca):
    alvo = _sem_acento(busca).strip()
    return any(alvo in _sem_acento(registro[c]) for c in ("favorecido", "cargo", "destino", "motivo"))


def _ressalvas(lidos):
    """O que quem lê precisa saber: valor não publicado e diárias de um órgão só (o principal, talvez)."""
    ressalvas = []
    sem_valor = sum(1 for x in lidos if x["valor"] is None)
    if lidos and sem_valor == len(lidos):
        ressalvas.append(f"o portal não publicou o valor de nenhuma das {len(lidos)} diárias lidas: valor vazio "
                         "não é zero")
    elif sem_valor:
        ressalvas.append(f"{sem_valor} de {len(lidos)} diárias vieram sem valor: valor vazio não é zero")
    vazios = [rotulo for chave, rotulo in (("quantidade", "quantidade"), ("cargo", "cargo"), ("destino", "destino"),
                                           ("data_chegada", "data de chegada"))
              if lidos and all(x[chave] is None for x in lidos)]
    if vazios:
        ressalvas.append(f"o portal deixou vazios, em todas as diárias lidas: {', '.join(vazios)}")
    orgaos = {x["orgao"] for x in lidos}
    principal = ("Em alguns portais NucleoGov a consulta sem o filtro de órgão traz só o órgão principal (medição "
                 "anterior: Posse); as diárias da Câmara e dos fundos podem não estar aqui")
    if not lidos:
        ressalvas.append(f"nenhuma diária veio no período. {principal}: o zero não garante que nenhum órgão pagou "
                         "diárias")
    elif len(orgaos) == 1:
        ressalvas.append(f"todas as diárias lidas são de um só órgão ({next(iter(orgaos)) or 'sem nome'}). "
                         f"{principal}")
    return ressalvas


def diarias(portal, *, de: date, ate: date, busca, maximo):
    """Diárias com saída de `de` a `ate` (`datetime.date`), com os nomes comuns de diárias. `busca`: texto ou None.

    Sem busca, lê até `maximo`. Com busca, lê o período inteiro e filtra aqui (o `txtbusca` do portal não funciona
    nas diárias): leitura incompleta vira `ErroPortal`, porque a contagem sairia errada.
    """
    filtros = {"datamin": de.isoformat(), "datamax": ate.isoformat()}
    r = portal._consultar_api("diarias", filtros, maximo=sys.maxsize if busca else maximo, progresso=None)
    brutos = r["registros"]
    if busca and len(brutos) < r["total"]:
        raise ErroPortal(f"a leitura das diárias de {portal.url} veio incompleta: {len(brutos)} de {r['total']}. "
                         "A busca é feita sobre o período inteiro e precisa de todas; tente de novo ou encurte o período")
    fora = sorted(d for d in (_dia(_saida(x)) for x in brutos) if d and not de <= d <= ate)
    if fora:
        raise ErroPortal(f"{portal.url} devolveu {len(fora)} diária(s) com saída fora do período pedido (de "
                         f"{fora[0]:%d/%m/%Y} a {fora[-1]:%d/%m/%Y}): o filtro de datas pode ter sido ignorado. "
                         "Nada foi devolvido, para não misturar períodos")
    lidos = [diaria(x) for x in brutos]
    registros = [x for x in lidos if _casa(x, busca)] if busca else lidos
    resposta = {"total": len(registros) if busca else r["total"], "registros": registros[:maximo]}
    ressalvas = _ressalvas(lidos)
    if ressalvas:
        resposta["ressalvas"] = ressalvas
    return resposta
