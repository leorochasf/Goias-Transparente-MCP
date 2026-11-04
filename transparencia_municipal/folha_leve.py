"""Folha leve para assistente de IA: emagrece, filtra e resume linhas da folha. Sem rede, sem estado.

Termos em CONTEXT.md; desenho em docs/design/2026-11-04-folha-leve.md.
"""
from __future__ import annotations

import unicodedata
from decimal import Decimal, InvalidOperation

AGRUPAMENTOS = ("cargo", "lotacao", "vinculo")

#: campo da linha leve → campo do portal
CAMPOS = {
    "nome": "nome", "matricula": "matricula", "cpf": "cpf",
    "cargo": "cargo", "lotacao": "lotacao", "vinculo": "vinculo", "tipo_pagamento": "tipo_folha",
    "data_admissao": "data_admissao", "data_demissao": "data_demissao", "carga_horaria": "carga_horaria",
    "bruto": "total_proventos", "descontos": "total_desconto", "liquido": "total_liquido",
    "orgao": "orgao_id",
}


def linha_leve(linha, *, rubricas=False):
    """A linha da folha sem o que só pesa. `rubricas=True` acrescenta proventos e descontos."""
    leve = {nosso: linha.get(do_portal) for nosso, do_portal in CAMPOS.items()}
    if rubricas:
        leve["rubricas"] = [
            {"codigo": r.get("evento"), "nome": r.get("nome"), "valor": r.get("valor"), "tipo": r.get("tipo")}
            for r in (linha.get("lista_proventos") or []) + (linha.get("lista_descontos") or [])
        ]
    return leve


def _comparavel(texto):
    sem_acento = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return sem_acento.casefold()


def filtrar(linhas, *, cargo=None, lotacao=None, vinculo=None, tipo_pagamento=None, nome=None):
    """Linhas leves cujo campo contém o texto pedido, sem distinguir maiúscula nem acento. Filtros se somam."""
    pedidos = {c: _comparavel(v) for c, v in (("cargo", cargo), ("lotacao", lotacao), ("vinculo", vinculo),
                                              ("tipo_pagamento", tipo_pagamento), ("nome", nome)) if v}
    return [x for x in linhas if all(v in _comparavel(x.get(c)) for c, v in pedidos.items())]


def _valor(texto):
    """'1.518,00' → Decimal('1518.00'); vazio ou ilegível → None."""
    v = str(texto or "").strip()
    if "," in v:
        v = v.replace(".", "").replace(",", ".")
    try:
        return Decimal(v) if v else None
    except InvalidOperation:
        return None


def _somar(linhas):
    bruto = liquido = Decimal(0)
    for x in linhas:
        b, liq = _valor(x.get("bruto")), _valor(x.get("liquido"))
        if b is not None and liq is not None:
            bruto, liquido = bruto + b, liquido + liq
    return {"linhas": len(linhas), "matriculas": len({x.get("matricula") for x in linhas}),
            "bruto": float(round(bruto, 2)), "liquido": float(round(liquido, 2))}


def _mensal(tipo):
    """"Folha Mensal" (Senador Canedo) ou "MENSAL" (Trindade): cada portal escreve de um jeito."""
    return "mensal" in _comparavel(tipo)


def resumir(linhas, agrupar_por, *, todos_os_tipos=False):
    """Resumo da folha: contagens e somas por grupo, separadas por tipo de pagamento, sem nomes.

    Por padrão só a Folha Mensal entra; as linhas dos outros tipos são contadas em `fora_do_resumo`.
    Linha com bruto ou líquido ilegível conta nas linhas, fica fora das somas e entra em `linhas_sem_valor`.
    """
    if agrupar_por not in AGRUPAMENTOS:
        raise ValueError(f"agrupar_por: use cargo, lotacao ou vinculo (recebido: {agrupar_por!r})")
    por_tipo, fora = {}, {}
    for x in linhas:
        tipo = x.get("tipo_pagamento") or "(sem tipo)"
        if todos_os_tipos or _mensal(tipo):
            por_tipo.setdefault(tipo, []).append(x)
        else:
            fora[tipo] = fora.get(tipo, 0) + 1
    resumo = {}
    for tipo, do_tipo in por_tipo.items():
        grupos = {}
        for x in do_tipo:
            grupos.setdefault(x.get(agrupar_por) or "(vazio)", []).append(x)
        linhas_grupos = [{"grupo": g, **_somar(gl)} for g, gl in grupos.items()]
        resumo[tipo] = {**_somar(do_tipo), "grupos": sorted(linhas_grupos, key=lambda g: -g["bruto"])}
    sem_valor = sum(1 for do_tipo in por_tipo.values() for x in do_tipo
                    if _valor(x.get("bruto")) is None or _valor(x.get("liquido")) is None)
    return {"agrupar_por": agrupar_por, "por_tipo_de_pagamento": resumo,
            "linhas_sem_valor": sem_valor, "fora_do_resumo": fora}
