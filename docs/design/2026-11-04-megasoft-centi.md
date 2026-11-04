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
7. De medições anteriores do autor, só o conhecimento das APIs; o código é escrito aqui.

## Fatos medidos (04/11/2026)

Medições dos tickets 01 a 04, ao vivo, com pausa de 1 s e sem gravar nomes. Detalhe do comportamento de cada sistema
em `docs/portal-nucleogov.md`, seção "Megasoft e Centi".

- **Megasoft própria** (Corumbaíba).
  - Senha: `GET {portal}/api/configuracao/carregamento-inicial` → campo `tokenPortal` (JWT), em 0,4 s, com o
    User-Agent honesto da ferramenta. O `exp` do JWT fica cerca de **24 h** depois da emissão. Senha ilegível dá
    **HTTP 500 "Token inválido"** (não 401). O projeto guarda a senha na memória do processo, por portal, e a
    renova uma vez no 401 ou no 500 "Token inválido".
  - Chamadas: `GET {portal}/api/{caminho}?pagina=&tamanhoDaPagina=` com `Authorization: Bearer <tokenPortal>` e
    `cliente-integrado: megasoft-portal-da-transparencia`; os dois cabeçalhos são obrigatórios.
    Resposta: `{paginaAtual, registros, total}`.
  - Folha: `orgaos-e-servidores/servidor/paginado` (`ano`, `mes` com dois dígitos). 822 linhas de 09/2025 numa
    página, 1,6 s; mês respeitado. `nome=` e `filtro=` **não filtram**: a busca por nome é feita pelo projeto.
  - Empenhos: `receitas-e-despesas/empenho/paginado` (`dataInicial`, `dataFinal` em dd/mm/aaaa). Período
    **respeitado** (1º tri/2025: 4.314, nenhuma data fora). `cnpjDoFornecedor` **filtra no servidor** (com ou sem
    pontuação); `cpfOuCnpjDoFornecedor` é ignorado. O projeto manda o filtro e confere cada registro.
- **Megasoft embutida** (Aruanã). Vai pela API NucleoGov do próprio portal, com o envelope `multi_request` e
  `acao = megasoft/servidores` ou `megasoft/empenhos`. A paginação usa `pagina` (começa em 1), `tamanhoDaPagina` e
  `ordenacao: {}`; a folha usa `mes` ("06"), `ano` e `mesInteger`. O `limit` do envelope é ignorado.
  - Os campos são os mesmos da Megasoft própria.
  - Período respeitado: 1º tri/2025, 1.694 de 1.694 dentro; o ano de 2025, 7.481, todos dentro. Folha de 11 e
    12/2025 só com o mês pedido.
  - Os empenhos da Prefeitura trazem 9 entidades (Município, Câmara, fundos), sem filtro.
- **As duas Megasoft.**
  - **A fronteira de página perde registros.** A listagem de empenhos ordena só por data: em páginas de 100,
    fevereiro/2025 deu 236 códigos repetidos (e 236 perdidos) na própria e 33 na embutida. Numa página de 5.000,
    nenhum. O projeto pede páginas de 5.000 e tira repetidos pelo `codigo` (empenho) e pela `chave` (folha); a
    embutida, com filtro, lê mês a mês. Leitura que não fecha sai **incompleta**; com filtro, falha.
  - **Totais:** `valorTotalDo... = valorDo... − anulação` em empenho, liquidação e pagamento (100 de 100 na própria,
    1.694 de 1.694 na embutida). A tradução usa os totais.
  - **13º e rescisão.** A listagem não tem campo de tipo de pagamento e nenhuma matrícula vem duas vezes no mês.
    **O 13º não está na listagem**, nem somado em dezembro: em Aruanã, a razão 12/11 dos proventos por matrícula
    teve mediana 1,00 (p10 0,98, p90 1,05), e a folha com `mes="13"` responde 0. Onde o 13º fica não foi achado. A
    rescisão não vem separada. Toda linha sai com o tipo de pagamento
    "Mensal (a listagem da Megasoft não traz 13º; rescisão não vem separada)".
  - Sem rubricas: a listagem traz só bruto, descontos e líquido.
- **Centi** (Posse). `POST {portal}/api/centi`, num formulário simples com os filtros zerados da página,
  `acao=empenhos`, `id_orgao=0`, `data_inicio` e `data_fim` (dd/mm/aaaa). A resposta é uma lista inteira, sem
  páginas; o total vem em `TotalRegistros`, repetido em todo registro.
  - `relatorioEmpenhos`, que a mesma página chama, devolve **só três somas**. `total_empenhado` = Σ(empenhado −
    anulação), ao centavo; `total_liquidado` e `total_pago` somam só os empenhos sem anulação.
  - Período respeitado (01/2025: 823; 02/2025: 1.129; nenhuma data fora).
  - O filtro `cpf_cnpj` da Centi devolve **lista vazia** para um CNPJ que tem empenhos: o projeto filtra o CNPJ e o
    nome do fornecedor.
  - **Resposta vazia espúria:** uma janela com empenhos voltou `[]` em 0,4 s e, repetida, respondeu. O projeto
    repete a lista vazia duas vezes antes de aceitá-la.
  - **`id_orgao=0` traz todas as entidades:** em 01/2025, Fundo de Saúde 426, Poder Executivo 259, Fundeb 36,
    FMAS 36, Poder Legislativo 36, FPPS 21. A despesa da Prefeitura inclui a da Câmara e a dos fundos.
  - Um mês: 2,2 a 2,7 s (1,3 MB).
- **Descoberta sem navegador.** A página traz `window.CALL_JS` (os controllers); o JS de cada um, em
  `static.nucleogov.com.br/res/js/<controller>.js`, mostra `setRequest("<modulo>", "<acao>", ...)`.

## Decisões tomadas na construção

- Registros de folha e despesas trazem `fonte`: `NucleoGov`, `Megasoft` ou `Centi`.
- Despesas da Megasoft e da Centi trazem `orgao` (`codigoENomeDoOrgao`; `OrgaoGestor`). O projeto mantém todas as
  entidades, porque é o que o portal mostra, e `consultar_despesas` avisa quando os empenhos devolvidos misturam
  órgãos.
- Num módulo `mg` ou `centi`, a API NucleoGov é sondada uma vez por endereço enquanto o processo vive.
- `valor_empenhado` é o empenhado menos a anulação nos três sistemas novos; liquidado e pago, como vêm.
- A sondagem de órgãos escondidos na folha é só do NucleoGov.

## Ainda não verificado

- Onde a Megasoft publica o 13º, e se a rescisão vem somada nos proventos do mês.
- Na Centi, se a anulação estorna liquidação e pagamento (há empenhos com empenhado = anulado = liquidado = pago).
- Na Centi, períodos maiores que um mês (tamanho e tempo), `id_orgao` diferente de 0 e o filtro `credor`.
- Validade real do `tokenPortal` (só o `exp` do JWT foi lido).
- O filtro `cnpjDoFornecedor` na Megasoft embutida (o projeto filtra sem ele).
