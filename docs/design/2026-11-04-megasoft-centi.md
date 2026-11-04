# Megasoft (embutida e própria) e Centi

Aprovado em 04/11/2026. Termos em `CONTEXT.md`. É a frente seguinte à "NucleoGov em Goiás" (v0.3.0).

## Por quê

A conferência de 04/11/2026 mostrou que, em Goiás, folha e despesas raramente vêm pela API NucleoGov:
- Despesas pela API NucleoGov só vieram na Prefeitura de Alexânia; nos outros órgãos da amostra vêm da contabilidade
  **Centi** (menu `cntdespesas`) ou da **Megasoft embutida** (menu `mg*`).
- O catálogo tem 219 órgãos com Megasoft embutida e 30 com Megasoft de domínio próprio (`*.megasofttransparencia.com.br`).

## Decisões

1. Megasoft completa (embutida e própria) e Centi nesta mesma frente.
2. Primeiro **folha e despesas**. Receitas, contratos e diárias só depois, se a descoberta mostrar que são simples.
3. **Mesmo formato de saída** das ferramentas atuais: os registros são traduzidos para os campos que o projeto já usa
   (linha leve da folha; CNPJ, fornecedor, data e valores das despesas), com um campo `fonte` (NucleoGov, Megasoft
   ou Centi). As ferramentas do assistente não mudam; listas e resumo da folha passam a valer nesses portais.
4. **O cliente escolhe o caminho sozinho**, pelo que já descobre:
   - módulo `mg` → Megasoft pelo portal NucleoGov;
   - módulo `centi` → Centi;
   - portal `*.megasofttransparencia.com.br` → Megasoft própria.

   A recusa `ModuloNaoSuportado` fica só para o que não estiver coberto.
5. **Senha da Megasoft própria: automática**, documentada no README. Ela sai de um endereço público, sem login; é o
   que o navegador de qualquer visitante faz. O portal aceita a identificação honesta do projeto.
6. A mesma **conferência** na amostra das 16 cidades, incluindo os órgãos Megasoft e Centi.
7. Do AJE, só o conhecimento das APIs; o código é escrito aqui.

## Fatos medidos (04/11/2026)

- **Megasoft própria.**
  - Senha: `GET {portal}/api/configuracao/carregamento-inicial` → campo `tokenPortal` (JWT). Aceita o User-Agent da
    ferramenta.
  - Chamadas: `GET {portal}/api/{caminho}?pagina=&tamanhoDaPagina=` com `Authorization: Bearer <tokenPortal>` e
    `cliente-integrado: megasoft-portal-da-transparencia`; os dois cabeçalhos são obrigatórios.
  - Resposta: `{paginaAtual, registros, total}`.
  - Folha: `orgaos-e-servidores/servidor/paginado` (filtros `ano`, `mes`).
  - Empenhos: `receitas-e-despesas/empenho/paginado` (`dataInicial`, `dataFinal` em dd/mm/aaaa).
  - Corumbaíba respondeu.
- **Megasoft embutida.** Vai pela API NucleoGov do próprio portal, com o envelope `multi_request` e
  `acao = megasoft/servidores` ou `megasoft/empenhos`. A paginação usa `pagina`, `tamanhoDaPagina` e
  `ordenacao: {}`; a folha usa `mes` ("06"), `ano` e `mesInteger`.
  - Resultado em Aruanã: 664 linhas de folha (06/2025) e 1.694 empenhos (1º trimestre de 2025).
  - Os campos são os mesmos da Megasoft própria.
- **Centi.** `POST {portal}/api/centi`, num formulário simples com `acao=empenhos`, `id_orgao=0`, `data_inicio` e
  `data_fim` (dd/mm/aaaa). A resposta é uma lista inteira, sem páginas; o total vem em `TotalRegistros`.
  - Resultado em Posse: 823 empenhos em 01/2025.
  - A página do portal chama `centi/relatorioEmpenhos`; ainda não foi conferido se dá o mesmo resultado.
- **Descoberta sem navegador.** A página traz `window.CALL_JS` (os controllers); o JS de cada um, em
  `static.nucleogov.com.br/res/js/<controller>.js`, mostra `setRequest("<modulo>", "<acao>", ...)`.
- **Armadilha conhecida (AJE).** Na Megasoft, o filtro de fornecedor não filtra no servidor: o CNPJ tem de ser
  filtrado pelo projeto. Ainda a conferir ao vivo.

## Ainda não verificado

- Como a Megasoft marca 13º e rescisão na folha (`situacaoPagamento`?).
- Se o período das despesas da Megasoft e da Centi é respeitado.
- Quanto tempo vale o `tokenPortal`.
