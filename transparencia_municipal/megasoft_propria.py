"""Acesso à Megasoft de domínio próprio (`*.megasofttransparencia.com.br`). Encaixe do ticket 02; único arquivo dele.

O `Portal` manda para cá o portal inteiro, só pelo endereço. Por enquanto, recusa.
Contrato dos encaixes (o mesmo em megasoft_embutida.py e centi.py):
- devolve {"total": <total anunciado pelo sistema>, "registros": [<até `maximo` registros traduzidos>]};
- registros traduzidos pela `traducao_megasoft` (folha: `linha_da_folha`; despesas: `despesa`), cada um com `fonte`;
- leitura que não fecha (registros lidos ≠ total, com `maximo` suficiente) devolve o que leu e o total anunciado:
  quem lê o mês declara "incompleta"; nunca devolver total 0 para esconder falha;
- `cnpj` (já 00.000.000/0000-00) é filtrado aqui sobre os registros do período, mesmo se o sistema filtrar;
- erro de rede ou resposta inesperada: `ErroPortal`, com mensagem que diga o que houve;
- pausa `portal.pausa` entre páginas; identificação `portal.user_agent`; sessão `portal.sessao`.
"""
from __future__ import annotations

from .cliente import PROPRIA, recusa


def folha(portal, *, ano, mes, busca, maximo, progresso=None):
    """Linhas da folha de `mes`/`ano` (int; `mes` None = o portal decide). `busca`: nome do servidor ou None.

    `progresso(lidas, total)`, se dado, é chamado depois de cada página (a leitura do mês avisa o assistente).
    """
    raise recusa(portal, "folha", PROPRIA)


def despesas(portal, *, de, ate, cnpj, busca, maximo):
    """Empenhos de `de` a `ate` (dd/mm/aaaa). `cnpj` formatado ou None; `busca`: nome do fornecedor ou None."""
    raise recusa(portal, "despesas", PROPRIA)
