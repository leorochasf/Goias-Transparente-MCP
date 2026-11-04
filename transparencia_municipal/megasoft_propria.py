"""Acesso à Megasoft de domínio próprio (`*.megasofttransparencia.com.br`). Encaixe do ticket 02; único arquivo dele.

O `Portal` manda para cá o portal inteiro, só pelo endereço; aqui se leem folha e despesas.
Contrato dos encaixes (o mesmo em megasoft_embutida.py e centi.py):
- devolve {"total": <total anunciado pelo sistema>, "registros": [<até `maximo` registros traduzidos>]};
- registros traduzidos (Megasoft: `traducao_megasoft.linha_da_folha` e `despesa`; Centi: `centi.despesa`, com as
  mesmas chaves), cada um com `fonte`;
- leitura que não fecha (registros lidos ≠ total, com `maximo` suficiente) devolve o que leu e o total anunciado:
  quem lê o mês declara "incompleta"; nunca devolver total 0 para esconder falha;
- `cnpj` (já 00.000.000/0000-00) é filtrado aqui sobre os registros do período, mesmo se o sistema filtrar;
- erro de rede ou resposta inesperada: `ErroPortal`, com mensagem que diga o que houve;
- pausa `portal.pausa` entre páginas; identificação `portal.user_agent`; sessão `portal.sessao`.

Medido em Corumbaíba (04/11/2026):
- a senha pública (`tokenPortal`, JWT) sai de `/api/configuracao/carregamento-inicial`, sem login, e vale cerca de
  24 h; senha vencida dá 401 (AJE) e senha ilegível, 500 "Token inválido";
- a busca por nome (`nome`, `filtro`) não filtra no servidor: o nome é filtrado aqui;
- `cnpjDoFornecedor` filtra no servidor (597 de 4.314 no 1º trimestre de 2025), e o projeto confere mesmo assim;
- em páginas de 100 os empenhos repetem e perdem registros na fronteira (fevereiro/2025: 1.555 lidos, 1.319 códigos
  distintos); numa página de 5.000, os 1.555 vieram distintos. Por isso a página é grande e o código tira repetidos.
"""
from __future__ import annotations

import json
import sys
import time
import unicodedata

import requests

from . import traducao_megasoft
from .cliente import ErroPortal, PortalBloqueou

#: senha pública por portal, só na memória enquanto o processo estiver aberto
_SENHAS: dict[str, str] = {}
#: registros por página: grande, porque a fronteira de página repete e perde registros (ver acima)
TAMANHO = 5000
FOLHA = "orgaos-e-servidores/servidor/paginado"
EMPENHOS = "receitas-e-despesas/empenho/paginado"


def _senha(portal, *, renovar=False):
    if renovar or portal.url not in _SENHAS:
        endereco = f"{portal.url}/api/configuracao/carregamento-inicial"
        try:
            r = portal.sessao.get(endereco, timeout=portal.timeout, headers={"User-Agent": portal.user_agent})
            senha = r.json().get("tokenPortal") if r.status_code == 200 else None
        except (requests.RequestException, ValueError, AttributeError) as e:
            raise ErroPortal(f"não foi possível obter a senha pública de {portal.url}: {e}") from e
        if not senha:
            raise ErroPortal(f"{portal.url} não entregou a senha pública (HTTP {r.status_code} em "
                             "configuracao/carregamento-inicial)")
        _SENHAS[portal.url] = senha
    return _SENHAS[portal.url]


def _senha_recusada(r):
    """401 (senha vencida) ou 500 "Token inválido" (senha ilegível), como medido."""
    return r.status_code == 401 or (r.status_code == 500 and "Token" in r.text)


def _pagina(portal, caminho, filtros, pagina, tamanho):
    """Uma página: (registros crus, total anunciado). Senha recusada: renova uma vez e repete."""
    consulta = {**filtros, "pagina": pagina, "tamanhoDaPagina": tamanho}
    for renovar in (False, True):
        cabecalhos = {"User-Agent": portal.user_agent, "Authorization": f"Bearer {_senha(portal, renovar=renovar)}",
                      "cliente-integrado": "megasoft-portal-da-transparencia"}
        try:
            r = portal.sessao.get(f"{portal.url}/api/{caminho}", params=consulta, headers=cabecalhos,
                                  timeout=portal.timeout)
        except requests.RequestException as e:
            raise ErroPortal(f"não foi possível falar com {portal.url}: {e}") from e
        if not _senha_recusada(r):
            break
    if r.status_code == 403:
        raise PortalBloqueou(f"{portal.url} respondeu 403 em {caminho}.")
    if r.status_code != 200:
        raise ErroPortal(f"{portal.url} respondeu HTTP {r.status_code} em {caminho}: {r.text[:200]}")
    try:
        corpo = r.json()
        registros, total = corpo["registros"], int(corpo["total"])
    except (ValueError, KeyError, TypeError) as e:
        raise ErroPortal(f"{portal.url} devolveu resposta inesperada em {caminho} "
                         f"({len(r.content)} bytes, começa com {r.text[:80]!r})") from e
    if not isinstance(registros, list):
        raise ErroPortal(f"{portal.url} devolveu `registros` que não é lista em {caminho}")
    return registros, total


def _ler(portal, caminho, filtros, *, chave, ate, progresso=None):
    """Lê página a página até ter `ate` registros distintos (pela `chave`; sem ela, pelo registro inteiro) ou acabar.
    Devolve (distintos, total)."""
    distintos, total, pagina = {}, 0, 1
    tamanho = min(TAMANHO, max(ate, 1))
    while True:
        lote, total_da_pagina = _pagina(portal, caminho, filtros, pagina, tamanho)
        total = total_da_pagina if pagina == 1 else total  # vale o total anunciado na 1ª página
        for reg in lote:
            distintos.setdefault(chave(reg) or json.dumps(reg, sort_keys=True), reg)
        if progresso:
            progresso(len(distintos), total)
        if len(lote) < tamanho or len(distintos) >= min(total, ate) or pagina * tamanho >= total:
            return list(distintos.values()), total
        pagina += 1
        time.sleep(portal.pausa)


def _simples(texto):
    """Sem acento e em maiúsculas, para a busca por nome."""
    return "".join(c for c in unicodedata.normalize("NFD", str(texto or "")) if not unicodedata.combining(c)).upper()


def _filtrado(regs, total, casa, onde):
    """Filtra pelo projeto. A leitura que não fechou não permite contar: falha em vez de devolver total menor."""
    if len(regs) != total:
        raise ErroPortal(f"a leitura de {onde} veio incompleta ({len(regs)} de {total} registros): "
                         "não dá para contar os que casam com a busca. Tente de novo.")
    return [x for x in regs if casa(x)]


def folha(portal, *, ano, mes, busca, maximo, progresso=None):
    """Linhas da folha de `mes`/`ano` (int; `mes` None = o portal decide). `busca`: nome do servidor ou None.

    `progresso(lidas, total)`, se dado, é chamado depois de cada página (a leitura do mês avisa o assistente).
    """
    filtros = {"ano": ano} if mes is None else {"ano": ano, "mes": f"{int(mes):02d}"}

    def chave(reg):
        return json.dumps(reg.get("chave"), sort_keys=True) if reg.get("chave") else reg.get("matricula")
    regs, total = _ler(portal, FOLHA, filtros, chave=chave, ate=sys.maxsize if busca else maximo,
                       progresso=progresso)
    linhas = [traducao_megasoft.linha_da_folha(x) for x in regs]
    if busca:
        alvo = _simples(busca)
        linhas = _filtrado(linhas, total, lambda x: alvo in _simples(x["nome"]), f"folha de {portal.url}")
        total = len(linhas)
    return {"total": total, "registros": linhas[:maximo]}


def despesas(portal, *, de, ate, cnpj, busca, maximo):
    """Empenhos de `de` a `ate` (dd/mm/aaaa). `cnpj` formatado ou None; `busca`: nome do fornecedor ou None."""
    filtros = {"dataInicial": de, "dataFinal": ate}
    if cnpj:
        filtros["cnpjDoFornecedor"] = cnpj
    regs, total = _ler(portal, EMPENHOS, filtros, chave=lambda reg: reg.get("codigo"),
                       ate=sys.maxsize if cnpj or busca else maximo)
    empenhos = [traducao_megasoft.despesa(x) for x in regs]
    if cnpj or busca:
        alvo = _simples(busca)
        casa = (lambda x: x["cpf_cnpj"] == cnpj) if cnpj else (lambda x: alvo in _simples(x["fornecedor"]))
        empenhos = _filtrado(empenhos, total, casa, f"despesas de {portal.url}")
        total = len(empenhos)
    return {"total": total, "registros": empenhos[:maximo]}
