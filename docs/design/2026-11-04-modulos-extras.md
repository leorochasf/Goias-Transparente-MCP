# Módulos extras: receitas, diárias, contratos, licitações, detalhe do servidor, Ortrel e acórdão por número

Aprovado em 04/11/2026, depois da v0.5.0. Termos em `CONTEXT.md`.

## Decisões

1. **Rubricas da folha Megasoft.** O portal não abre a folha por rubrica. Medição anterior: tudo cai em "outras
   remunerações", com `existeConcessaoDeVerba: false`. No lugar, entra o **detalhe do servidor**: cargo, vínculo,
   **decreto de nomeação e a data dele**, licenças, férias e total de vencimentos. A descoberta confirma ao vivo que as
   rubricas não existem.
2. **Módulos.** Receitas, diárias, contratos e licitações entram em cada sistema (Megasoft própria, Megasoft embutida,
   Centi) **onde a descoberta achar a consulta e ela passar na conferência**. O que não for achado continua recusado
   com aviso.
3. **Diárias:** ferramenta nova, `consultar_diarias`, para o NucleoGov e a Megasoft.
4. **Ortrel** (4 câmaras no catálogo): folha e legislação, que já são conhecidas; despesas, se a descoberta achar.
5. **Acórdão por número:** `acordaos_tcm` ganha `numero`, que aceita o número do processo ou do acórdão. O resultado é
   conferido campo a campo, porque o filtro do TCM aceita partes do número.
6. **Processo de trabalho:** três ondas no Elyra.
   - **Onda 0:** descoberta. Só lê e mede, com poucas consultas por portal, e grava os fatos neste desenho.
   - **Revisão do Orquestrador**, com confirmação rápida do usuário.
   - **Onda 1:** um agente por sistema, em paralelo.
   - **Onda 2:** fechamento.

## Fatos conhecidos (medição anterior; reconferir ao vivo)

### Megasoft própria (`GET {portal}/api/<caminho>` com a senha pública e o `cliente-integrado`)

- **Receitas:** `receitas-e-despesas/receita/paginado`.
  - Filtros `dataInicial` e `dataFinal` em dd/mm/aaaa; página de até 100.
  - Campos: `receita`, `naturezaDaReceita`, `fonteDaReceita`, `valorOrcado`, `arrecadacao`, `valorAcumulado`.
  - Traz só categorias específicas, não a receita total.
- **Diárias:** `orgaos-e-servidores/diaria/paginado`, com **`data=1` obrigatório** (sem ele, a janela não é recortada),
  mais `dataInicial` e `dataFinal`.
  - O recorte é pela `dataDaSaida`.
  - Campos: `matricula`, `nomeDoFuncionario`, `cargoDoFuncionario`, `destino`, `dataDaSaida`, `dataDaChegada`,
    `valorDaDiaria`, `numeroDeDiarias`, `motivoDaViagem`.
- **Detalhe do servidor:** `orgaos-e-servidores/servidor/detalhe`.
  - Filtros: `matricula`, `mes` (MM), `ano`, `mesInteger`.
  - Campos: `mesAno`, `matricula`, `cargo`, `tipoDeVinculo`, `decreto`, `dataDecreto`, `somatorioMovimentoVencimentos`;
    também órgão, classificação, nível, licenças e férias.
- **Última competência:** `orgaos-e-servidores/servidor/data-ultimo-registro` devolve um valor solto, como `"31/07/2026"`.
- **Contratos e licitações: não validados.**
  - Candidatos no bundle do site, com pares `rotaPai`/`rotaFilho` em `main-es2015.<hash>.js`:
    `contratos-convenios-e-licitacoes/contrato/paginado`, `procedimentos-licitatorios`, `dispensas-inexigibilidades`,
    `ata-de-registro-de-preco`.
  - Alguns módulos só aceitam POST, com os filtros no corpo JSON.
- **Armadilhas:**
  - páginas pequenas perdem e repetem registros;
  - o filtro `ano` é ignorado no empenho;
  - `tipoDoDocumento` não filtra na legislação.

### Megasoft embutida (multi_request, `acao = megasoft/...`)

- **Conhecidas:** `megasoft/servidores`, `megasoft/empenhos` (com `codigoDoOrgao` opcional; sem ele, nem todas as
  entidades vêm garantidas) e `megasoft/servidoresDetalhe` (só o nome).
- **Receitas, contratos, licitações e diárias:** não mapeados. Descobrir com `window.CALL_JS` e `setRequest` nas páginas
  `mg*` (ex.: `mgreceitas`, `mgdiarias`).

### Centi (`POST {portal}/api/centi`)

- **Conhecida:** só `acao=empenhos`. As ações `pagamentos`, `liquidacoes` e `ordem_cronologica_pagamentos` respondem
  "Ação não encontrada".
- **Receitas** (menu `cntreceitas`): não mapeadas. Descobrir pela página.

### Ortrel (câmaras `transparencia.*.go.leg.br`)

- **Reconhecimento:** a página inicial tem `/src/main.jsx`.
- **API e token:** `GET {portal}/src/services/api.js`, de onde saem `"API_URL"` e `"VITE_FIXED_TOKEN"`.
  - Cabeçalhos: `Origin: {portal}`, `Referer: {portal}/` e `Authorization: Bearer {token}`, quando houver token.
- **Folha:** `GET {API_URL}/api/dados/rh/folha_de_pagamento?limit=100000&page=1` traz a chave `folhaPagamento`, com a
  **série histórica inteira** numa chamada.
  - Campo de vínculo: `tipo_vinculo`. Competência: `ano`/`mes`.
- **Legislação:** `GET {API_URL}/api/dados/legislacao/leis_municipais?limit=1000&page=N`, paginando por `totalPages`.
  - Campos: `nome_ato`, `descricao`, `ano`, `midia_arquivo_assinado` (o PDF).
  - Há registros repetidos com `ano` diferente.
- **Despesas:** não mapeadas. A única câmara Ortrel registrada é a de Cidade Ocidental; o catálogo tem 4 órgãos `ortrel`.

### TCMJuris

- `buscar` aceita `numero_processo_filtro` e `numero_acordao_filtro`, ambos com **parte do número** (ex.: `10175/23`).
  Só a conferência campo a campo prova o resultado.

## Descoberta (onda 0)

A preencher pelo agente de descoberta.
