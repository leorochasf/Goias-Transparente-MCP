# Folha leve para assistente de IA

Aprovado em 04/11/2026. Termos em `CONTEXT.md`.

## Problema

Em Senador Canedo, um mês da folha tem 8.577 linhas da folha. 100 linhas completas somam cerca de 216 mil
caracteres, e 66% disso são rubricas. O campo `eventos` sozinho é 39%. A ferramenta MCP
manda o assistente "trazer o mês inteiro e contar", o que é impossível: seriam uns 18 milhões de caracteres.

## Decisões

1. A folha responde três perguntas: uma pessoa (com rubricas), contagens e somas (resumo da folha, sem
   nomes) e listas filtradas (com nomes).
2. Listas e resumo usam a leitura do mês. São 86 páginas, cerca de 9 minutos com 1 s de pausa (medido: 548 s), guardadas na
   memória do servidor enquanto ele estiver aberto, nunca em disco. Durante a leitura vão avisos de progresso.
3. 13º e rescisão nunca se somam à Folha Mensal. O resumo separa por tipo de pagamento e, por padrão,
   resume só a Folha Mensal, contando à parte as linhas dos outros tipos.
4. Os nomes aparecem nas listas e na consulta por nome (nome, matrícula, CPF mascarado, como o portal
   mostra). O resumo não traz nomes.
5. Só o MCP emagrece. A CLI e a biblioteca continuam devolvendo a folha completa.
6. O resumo soma bruto (`total_proventos`) e líquido, e conta linhas e matrículas distintas.
7. O filtro de cargo, lotação e vínculo é "contém", sem distinguir maiúscula nem acento. Os filtros se combinam.
8. As listas trazem 100 linhas por padrão (no máximo 300) e sempre o total que casou com os filtros. Quando
   a lista é cortada, a ferramenta avisa.
9. Na consulta por nome, as rubricas vêm só quando há até 10 linhas.
10. O mês é obrigatório nas ferramentas de folha do MCP. Sem ele, o portal devolve o mês mais recente sem avisar.

## Peças

- `folha_leve.py` só faz contas, sem rede e sem estado:
  - `linha_leve(linha, rubricas=False)`;
  - `filtrar(linhas, cargo, lotacao, vinculo, tipo_pagamento)`;
  - `resumir(linhas, agrupar_por, todos_os_tipos=False)`.
  As rubricas saem de `lista_proventos` + `lista_descontos`, que somam exatamente o bruto e os descontos
  (100/100 numa amostra de 04/11/2026). O campo `eventos` vem em outro formato numérico, e não foi
  conferido se bate.
- `Portal.consultar(..., progresso=)` avisa a cada página.
- A leitura do mês fica no `servidor_mcp`, guardada por (portal, ano, mês). Ela só é guardada se trouxe
  todas as linhas que o portal anunciou.
- As ferramentas são `consultar_folha` (por nome, rápida), `listar_folha` e `resumir_folha`.

## Erros

- O portal cai no meio da leitura: a ferramenta devolve o erro dizendo até onde leu e não guarda nada.
- O mês vem vazio: a ferramenta diz que o portal não tem folha daquele mês.
- Agrupamento inválido: a mensagem lista as opções.
- Valor ilegível: a linha conta no total, e o resumo informa quantas linhas ficaram fora da soma.

## Testes

- Offline, com exemplos à mão: as três funções; matrícula com salário e 13º; a leitura guardada não chama
  o portal de novo; a falha não fica guardada; as ferramentas, por um cliente MCP em processo, incluindo os
  avisos de progresso.
- Ao vivo, no teste de fumaça: numa amostra, as rubricas somam o bruto.
- Uma leitura do mês inteiro, rodada uma vez à mão pelo Claude, para ver se a espera aguenta. Feita em 04/11/2026 por cliente MCP stdio: 548 s, 86 avisos, leitura completa; e pelo Claude Code 2.1.318 (sem ajuste de tempo limite): esperou 7 min 38 s e trouxe o resumo, com os mesmos números. O Claude Desktop não foi conferido.
