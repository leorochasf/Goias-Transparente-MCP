"""Tradução Megasoft → formato do projeto. Sem rede, sem estado.

Vale para a Megasoft embutida no NucleoGov e para a de domínio próprio: os campos são os mesmos (medido em
04/11/2026; ver docs/design/2026-11-04-megasoft-centi.md). A folha sai com os nomes de campo do NucleoGov, para que a
linha leve, a leitura do mês e o resumo funcionem sem mudança; as despesas, no formato de despesas do projeto.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from .cliente import _cnpj

FONTE = "Megasoft"

#: Aruanã, 11 e 12/2025 (04/11/2026): a listagem da folha não tem campo de tipo de pagamento, nenhuma matrícula veio
#: duas vezes no mês e o 13º não está nela, nem somado nos proventos de dezembro (mediana 12/11 por matrícula: 1,00).
#: `situacao` é a situação funcional; `situacaoPagamento`, PAGO/NÃO PAGO. O rótulo leva "mensal" para o resumo contar
#: a linha, e diz o que falta.
TIPO_PAGAMENTO = "Mensal (a listagem da Megasoft não traz 13º; rescisão não vem separada)"


def _br(valor):
    """3512.4 → '3.512,40', como o NucleoGov escreve valores. Vazio ou ilegível → None."""
    try:
        d = Decimal(str(valor)).quantize(Decimal("0.01")) if valor not in (None, "") else None
    except InvalidOperation:
        return None
    return None if d is None else f"{d:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _data(valor):
    """'15/01/2025' fica; '2025-01-15' ou '2025-01-15T00:00:00' vira '15/01/2025'."""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(valor or ""))
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else valor


def linha_da_folha(reg):
    """Uma linha da listagem `servidor/paginado` (própria) ou `megasoft/servidores` (embutida)."""
    matricula = reg.get("matricula")
    return {
        "nome": reg.get("nome"), "matricula": None if matricula is None else str(matricula), "cpf": reg.get("cpf"),
        "cargo": reg.get("cargo"), "lotacao": reg.get("departamento"), "vinculo": reg.get("tipoDeVinculo"),
        "tipo_folha": TIPO_PAGAMENTO, "data_admissao": reg.get("dataAdmissao"),
        "data_demissao": reg.get("dataExoneracao"), "carga_horaria": reg.get("cargaHoraria"),
        "total_proventos": _br(reg.get("proventos")), "total_desconto": _br(reg.get("descontos")),
        "total_liquido": _br(reg.get("totalLiquido")), "ano": reg.get("ano"), "mes": reg.get("mes"),
        "situacao": reg.get("situacao"), "situacao_pagamento": reg.get("situacaoPagamento"), "fonte": FONTE,
    }


#: o empenho traz o documento no início de `cnpjENomeDoFornecedor` ("25.107.525/0001-51/NOME"); a máscara tem "/"
_DOCUMENTO = re.compile(r"\s*(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}|[\dX*]{3}\.?[\dX*]{3}\.?[\dX*]{3}-?[\dX*]{2})"
                        r"\s*[/-]?\s*(.*)", re.S)


def despesa(reg):
    """Um empenho da listagem `empenho/paginado` (própria) ou `megasoft/empenhos` (embutida).

    Os valores são os totais (`valorTotalDo...`), que a Megasoft dá ao lado do valor e da anulação. `orgao`: a listagem
    traz o Município, a Câmara e os fundos juntos (Aruanã: 9 entidades).
    """
    composto = str(reg.get("cnpjENomeDoFornecedor") or "")
    m = _DOCUMENTO.match(composto)
    documento, resto = (m.group(1), m.group(2).strip()) if m else (None, composto.strip())
    return {
        "empenho": reg.get("codigo"), "data": _data(reg.get("data")),
        "cpf_cnpj": (_cnpj(documento) or documento) if documento else None,
        "fornecedor": reg.get("nomeDoFornecedor") or resto or None,
        "valor_empenhado": _br(reg.get("valorTotalDoEmpenho")),
        "valor_liquidado": _br(reg.get("valorTotalDaLiquidacao")),
        "valor_pago": _br(reg.get("valorTotalDoPagamento")),
        "historico": reg.get("historico"), "orgao": reg.get("codigoENomeDoOrgao") or None, "fonte": FONTE,
    }


# ── módulos extras da Megasoft de domínio próprio (ticket 02; Corumbaíba, 04/11/2026) ──────────────────────────────

def _texto(valor):
    """Número ou texto → texto; vazio → None."""
    return None if valor in (None, "") else str(valor)


def _quantidade(valor):
    """2.0 → '2'; 1.5 → '1,5' (meia diária). Vazio → None."""
    if valor in (None, ""):
        return None
    try:
        d = Decimal(str(valor)).normalize()
    except InvalidOperation:
        return str(valor)
    return f"{d:f}".replace(".", ",")


def receita(reg):
    """Uma linha de `receita/receitas-pelo-tipo-de-natureza-detalhada/paginado`, com os nomes comuns de receitas.

    `analitica` None: a Megasoft não diz se a conta é sintética (na medição, a soma das linhas bateu ao centavo com a
    consulta totalizada por órgão).
    """
    chave = reg.get("chave") or {}
    natureza = str(reg.get("naturezaDaReceita") or "")
    mes = chave.get("mes")
    return {
        "orgao": reg.get("orgaoUnidadeGestora") or None, "codigo": natureza.split(" - ")[0].strip() or None,
        "receita": reg.get("receita") or None, "fonte_recurso": reg.get("fonteDaReceita") or None,
        "valor_orcado": _br(reg.get("valorOrcado")), "valor_previsto_atualizado": None,
        "valor_arrecadado_mes": _br(reg.get("arrecadacao")), "valor_arrecadado_ate_mes": _br(reg.get("valorAcumulado")),
        "ano": chave.get("ano", reg.get("ano")), "mes": int(mes) if str(mes or "").isdigit() else None,
        "analitica": None, "fonte": FONTE,
    }


def diaria(reg):
    """Uma linha de `orgaos-e-servidores/diaria/paginado`, com os nomes comuns de diárias.

    `valorDaDiaria` é um só valor por viagem e vai em `valor` (ver a ressalva do encaixe); a listagem não traz órgão.
    """
    return {
        "favorecido": reg.get("nomeDoFuncionario") or None, "matricula": _texto(reg.get("matriculaDoFuncionario")),
        "cargo": reg.get("cargoDoFuncionario") or None, "orgao": None, "destino": reg.get("destino") or None,
        "motivo": reg.get("motivoDaViagem") or None, "data_saida": _data(reg.get("dataDaSaida")) or None,
        "data_chegada": _data(reg.get("dataDaChegada")) or None, "quantidade": _quantidade(reg.get("numeroDeDiarias")),
        "valor": _br(reg.get("valorDaDiaria")), "valor_unitario": None,
        "empenho": _texto(reg.get("numeroDaLiquidacao") or reg.get("codigoDaLiquidacao")), "fonte": FONTE,
    }


def _licitacao_do_contrato(valor):
    """`numeroEAnoDaLicitacao` vem como número colado ao ano (3162025 → '316/2025'); outro formato fica como veio."""
    v = _texto(valor)
    if v and re.fullmatch(r"\d+(19|20)\d{2}", v) and len(v) > 4:
        return f"{v[:-4]}/{v[-4:]}"
    return v


def contrato(reg):
    """Um contrato de `contrato/paginado` (POST)."""
    documento = reg.get("cpfOuCnpjDoFornecedor") or None
    return {
        "id": reg.get("codigo"), "numero": _texto(reg.get("numero")), "modalidade": reg.get("modalidade") or None,
        "licitacao": _licitacao_do_contrato(reg.get("numeroEAnoDaLicitacao")),
        "data_firmatura": _data(reg.get("data")) or None, "fim_vigencia": _data(reg.get("vigencia")) or None,
        "orgao_nome": reg.get("nomeDoOrgao") or None,
        "fornecedor_cpfcnpj": (_cnpj(documento) or documento) if documento else None,
        "fornecedor_nome": reg.get("nomeDoFornecedor") or None, "objeto": reg.get("objeto") or None,
        "valor": _br(reg.get("valor")), "fiscal_contrato": reg.get("nomeDoFiscalDoContrato") or None,
        "ano": reg.get("exercicioAno"), "situacao": reg.get("situacao") or None,
        "finalidade": reg.get("finalidade") or None, "fonte": FONTE,
    }


def licitacao(reg):
    """Uma licitação, dispensa ou inexigibilidade de `procedimento-licitatorio/paginado` (POST).

    `label` é o número com o ano ("24/2025") e `numero`, a parte antes da barra, como no NucleoGov.
    """
    label = _texto(reg.get("numeroAno"))
    return {
        "id": reg.get("codigo"), "numero": label.split("/")[0] if label else None, "label": label,
        "modalidade": reg.get("modalidade") or None,
        "situacao": reg.get("situacao") or None, "data_publicacao": _data(reg.get("dataDePublicacao")) or None,
        "data_julgamento": _data(reg.get("dataDeJulgamento")) or None,
        "valor_vencedor": _br(reg.get("valorVencedorTotal")),
        "descricao": reg.get("historico") or None, "orgao": reg.get("orgao") or None, "fonte": FONTE,
    }


#: listas de movimentos do detalhe → (nome no projeto, somatório correspondente)
MOVIMENTOS = {"movimentoVencimentos": "vencimentos", "movimento13Salario": "13_salario", "movimentoFerias": "ferias",
              "movimentoComplementar": "complementar", "movimentoSessoesExtraordinarias": "sessoes_extraordinarias",
              "movimentoRescisao": "rescisao"}


def _registros(lista):
    """Os registros de uma lista do detalhe (`{total, registros, paginaAtual}`)."""
    return (lista.get("registros") or []) if isinstance(lista, dict) else []


def detalhe_servidor(reg):
    """O detalhe de `orgaos-e-servidores/servidor/detalhe`: cargo, vínculo, decreto e data, licenças, férias e os
    movimentos do mês (eventos e somatórios). Sem rubricas: a Megasoft põe tudo num evento só."""
    movimentos = {}
    for campo, nome in MOVIMENTOS.items():
        eventos = _registros(reg.get(campo))
        if not eventos:
            continue
        soma = reg.get("somatorioM" + campo[1:]) or {}
        movimentos[nome] = {
            "eventos": [{"evento": x.get("nome"), "proventos": _br(x.get("proventos")),
                         "descontos": _br(x.get("descontos"))} for x in eventos],
            "total_proventos": _br(soma.get("somatorioProventos")),
            "total_descontos": _br(soma.get("somatorioDescontos")), "total_liquido": _br(soma.get("totalLiquido"))}
    return {
        "matricula": _texto(reg.get("matricula")), "nome": reg.get("nome") or None, "cargo": reg.get("cargo") or None,
        "vinculo": reg.get("tipoDeVinculo") or None, "decreto": reg.get("decreto") or None,
        "data_decreto": _data(reg.get("dataDecreto")) or None, "data_admissao": _data(reg.get("dataAdmissao")) or None,
        "lotacao": reg.get("departamento") or None, "local_trabalho": reg.get("localDeTrabalho") or None,
        "orgao": reg.get("orgao") or None, "situacao": reg.get("situacao") or None,
        "carga_horaria": reg.get("cargaHoraria"), "classificacao": reg.get("classificacao") or None,
        "nivel": reg.get("nivel") or None, "categoria_esocial": reg.get("categoriaDoTrabalhadorNoESocial") or None,
        "licencas": [{"tipo": x.get("tipoDeLicenca"), "descricao": x.get("descricao"), "historico": x.get("historico"),
                      "data_afastamento": _data(x.get("dataDeAfastamento")),
                      "data_retorno": _data(x.get("dataDeRetorno"))} for x in _registros(reg.get("licenca"))],
        "ferias": _registros(reg.get("ferias")), "disposicao": _registros(reg.get("vidaFuncionalDisposicao")),
        "movimentos": movimentos, "ano": reg.get("ano"), "mes": reg.get("mes"), "fonte": FONTE,
    }
