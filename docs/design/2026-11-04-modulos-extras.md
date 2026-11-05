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

Medida ao vivo em 04/11/2026: 85 consultas, uma por vez, com pausa de 1 s. Cerca de 30 delas foram arquivos JS
estáticos; as outras foram consultas de dados. Nenhum nome de pessoa foi impresso nem gravado. Onde esta seção
contradiz "Fatos conhecidos", **vale esta seção**.

### A. Megasoft própria (Corumbaíba)

Valem para todas as consultas abaixo a senha pública, os cabeçalhos e a resposta `{paginaAtual, registros, total}` de
sempre. Os filtros e os caminhos saíram dos módulos do site, carregados sob demanda. O mapa dos módulos está em
`runtime-es2015.<hash>.js`; os módulos são `17-…js` (receitas e despesas), `10-…js` (órgãos e servidores) e `14-…js`
(contratos e licitações). O caminho da API é o `super(e,"/<caminho>")` do serviço, que **nem sempre é igual à rota** da
tela: a rota `procedimentos-licitatorios` usa o serviço `procedimento-licitatorio`.

- **Receitas.**
  - **O fato conhecido está errado.** `GET receitas-e-despesas/receita/paginado` **ignora `dataInicial`/`dataFinal`**.
    Pedi 09/2025 e vieram 2.105 linhas, de **2016 a 2027**, todas com `chave.mes = "12"` (fechamentos anuais).
  - **Consulta certa:** `GET receitas-e-despesas/receita/receitas-pelo-tipo-de-natureza-detalhada/paginado`.
    - Filtros da tela: `ano` (obrigatório), `mes` (`"09"`), `codigoDoOrgao` (opcional), `codigoDaFonte` e `covid19`.
      Sem `codigoDoOrgao`, vêm todas as entidades: 9 órgãos (Câmara, Prefeitura, fundos, RPPS).
    - Em 09/2025 vieram 184 linhas, todas com `chave` 2025/09.
    - Campos: `chave {codigoDaReceita, ano, mes, codigoDoOrgao}`, `orgaoUnidadeGestora`, `fonteDaReceita`, `receita`,
      `naturezaDaReceita`, `origemDoRecurso`, `valorOrcado`, `arrecadacao` (a do mês), `valorAcumulado` (o do ano até
      o mês) e `ano`.
  - **Totais:** `…/receitas-pelo-tipo-de-natureza-totalizada/paginado` devolve uma linha por órgão (9). A soma da
    detalhada bate ao centavo com a totalizada: arrecadação R$ 9.535.298,53, acumulado R$ 68.626.088,98 e orçado
    R$ 107.380.000,00.
- **Diárias:** `GET orgaos-e-servidores/diaria/paginado`, com `dataInicial`, `dataFinal` e `data`.
  - **O que `data` faz:** na tela, `data` é um botão de escolha. `1` recorta pela data de saída e `2`, pela de chegada.
  - **Com `data=1`,** o 1º trimestre de 2025 deu 394 diárias, nenhuma com saída fora do período.
  - **Sem `data`,** vieram 390, uma com saída fora do período: o recorte usa outra data, e qual não foi conferido.
  - A soma de `valorDaDiaria` com `data=1` deu R$ 191.880,00.
  - **Campos (corrigidos):** `codigoDaViagem`, **`matriculaDoFuncionario`** (não `matricula`), `nomeDoFuncionario`
    (pessoa), `cargoDoFuncionario`, `destino`, `codigoDaLiquidacao`, `numeroDaLiquidacao`, `dataDaSaida`,
    `dataDaChegada` (dd/mm/aaaa), `valorDaDiaria`, `numeroDeDiarias` e `motivoDaViagem`.
  - A tela também mostra `portaria`.
- **Detalhe do servidor:** `GET orgaos-e-servidores/servidor/detalhe`, com `matricula`, `mes` (`"09"`), `ano` e
  `mesInteger`. A matrícula veio da folha de 09/2025.
  - **Vêm `decreto` e `dataDecreto`**, preenchidos, com a data em dd/mm/aaaa.
  - **Outros campos:** `mesAno`, `matricula`, `cpf`, `nome`, `orgao`, `cargo`, `cargoRec`, `dataAdmissao`,
    `departamento`, `tipoDeVinculo`, `classificacao`, `nivel`, `cargaHoraria`, `situacao`, `localDeTrabalho`,
    `categoriaDoTrabalhadorNoESocial`, `mes` e `ano`.
  - **Listas (`{total, registros, paginaAtual}`):** `ferias`, `licenca` (`descricao`, `historico`, `tipoDeLicenca`,
    `dataDeAfastamento`, `dataDeRetorno`), `vidaFuncionalDisposicao` e os movimentos. Os movimentos são
    `movimentoVencimentos`, `movimento13Salario`, `movimentoFerias`, `movimentoComplementar`,
    `movimentoSessoesExtraordinarias` e `movimentoRescisao`, cada um com o `somatorio…` correspondente
    (`somatorioProventos`, `somatorioDescontos`, `totalLiquido`).
  - **Rubricas: confirmado que não existem.** `movimentoVencimentos` traz um único evento, "Outras Remunerações"
    (`nome` é o nome do evento, não o da pessoa), com `existeConcessaoDeVerba: false`, em 09/2025 e em 12/2024.
  - **13º:** a resposta separa `movimento13Salario`, mas ele veio vazio em 12/2024 nessa matrícula. Onde fica o 13º
    continua sem resposta: foi uma amostra só.
  - **Concessão de verbas:** a tela chama `orgaos-e-servidores/servidor/concessao-de-verbas` (`ano`, `mes`,
    `codigoDoEvento`, `matricula`) só quando `existeConcessaoDeVerba` é verdadeiro. Não foi testada.
- **Contratos:** `contratos-convenios-e-licitacoes/contrato/paginado`.
  - **Só aceita POST,** com corpo JSON `{pagina, tamanhoDaPagina, <filtros>}`. Com GET, responde 405.
  - **Filtros da tela:** `codigoDoOrgao`, `ano`, `mes`, `numeroEAnoDaLicitacao`, `numeroDoContrato`,
    `nomeDoFornecedor`, `cpfOuCnpjDoFornecedor`, `objeto`, `covid19`, `dataDoContrato`, `periodoDeVigencia`,
    `situacaoDoContrato`, `valor`, `aditivoEApostilamentoDoContrato`, `fiscalDoContrato` e
    `anoDoAditivoOuApostilamento`.
  - **Filtros de período (`DATE_DE_ATE`)** viram dois parâmetros, `<nome>Inicial` e `<nome>Final`, em dd/mm/aaaa.
  - **Ano e mês respeitados:**
    - `ano=2025` trouxe 344 contratos, todos com `data` e `exercicioAno` de 2025, e 344 `codigo` distintos;
    - `ano=2025, mes="03"` trouxe 17, exatamente os 17 de março que estavam na lista do ano.
  - **Campos:** `codigo`, `numero`, `modalidade`, `numeroEAnoDaLicitacao`, `data`, `vigencia`, `nomeDoOrgao`,
    `cpfOuCnpjDoFornecedor`, `nomeDoFornecedor`, `objeto`, `valor`, `nomeDoFiscalDoContrato` (pessoa),
    `exercicioAno`, `situacao` e `finalidade`.
  - **Todas as entidades:** os contratos vêm de 5 órgãos ou mais (fundos, Prefeitura e Câmara), com `nomeDoOrgao`
    preenchido.
  - **Armadilha:** fornecedor pessoa física em 124 dos 344, que têm CPF.
  - Não foi testado se o filtro de CPF ou CNPJ funciona.
- **Licitações e dispensas:** `contratos-convenios-e-licitacoes/procedimento-licitatorio/paginado`, só com POST, como
  nos contratos.
  - **Não existe serviço `dispensas-inexigibilidades`.** As duas telas usam o mesmo serviço, com
    **`tipoDeConsultaDeModalidade`**: `1` são as licitações e `2`, as dispensas e inexigibilidades.
  - **Período:** `dataDePublicacaoInicial` e `dataDePublicacaoFinal` (dd/mm/aaaa). Os outros intervalos seguem o mesmo
    padrão: `dataDeAbertura…`, `dataDeJulgamento…`, `dataDeHomologacao…` e `dataDoFimDoRecebimento…`.
  - **Outros filtros:** `codigoDoOrgao`, `objeto`, `numeroDoProcesso`, `naturezaDoProcedimento` e `covid19`.
  - **1º trimestre de 2025, nenhuma data de publicação fora:**
    - tipo `1`: 9 registros (pregão, concorrência, chamamento, adesão a ata);
    - tipo `2`: 153 (129 dispensas, 23 inexigibilidades, 1 chamamento).
  - **Conferência:** sem tipo e sem período, vieram 2.406 registros, de 2013 a 2026, com todas as modalidades e 9
    órgãos. Desses, 161 foram publicados no 1º trimestre de 2025. A soma 9 + 153 dá 162: o chamamento sai nos dois
    tipos.
  - **Campos:** `codigo`, `numeroAno`, `modalidade`, `situacao`, `dataDePublicacao`, `dataDeJulgamento`,
    `valorVencedorTotal`, `historico` e `orgao`.
  - **Armadilhas:**
    - o mesmo chamamento vem nos dois tipos;
    - a tela sempre manda o tipo: sem ele, vem tudo, de todos os anos.
- **Existem e não foram testados:** `ata-de-registro-de-preco`, `fiscais-de-contratos`, `convenio`,
  `ordem-de-fornecimento`, `obra` e `aviso-de-intencao-de-registro-de-precos`.

### B. Megasoft embutida (Aruanã)

- **Identificação:** a página inicial e a API recusam a identificação do projeto (403). Com a de navegador, respondem.
- **Menus `mg*`:** `mgreceitas`, `mgdespesas`, `mgpagamentos`, `mgservidores`, `mgconvenios` e `mgobras`.
- **Menus `*_mg`, controlados pelo NucleoGov:** `licitacoes_mg`, `licitacoes_abertas_mg`, `licitacoes_fd_mg`,
  `dispensas_mg`, `contratos_mg`, `fiscais_contratos_mg`, `ordem_cronologica_pagamentos_mg`, `divida_ativa_mg`,
  `balancos_mg`, `rgf_mg`, `rreo_mg` e `planejamento_mg`.
- **Diárias:** o menu é **`sgdiarias`**, do próprio NucleoGov. Não existe `mgdiarias`.
- **Contratos e licitações:** também não existem `mgcontratos` nem `mglicitacoes`.
- **Receitas:** `acao = megasoft/receitas`, controller `receitas/receitas_mega`. Também há
  `megasoft/receitasTotalizadas`, que devolve só três somas, e `megasoft/complementosFiltrosReceitas`.
  - **Filtros:** `ano`, `mes` (`"09"`), `pagina`, `tamanhoDaPagina`, `ordenacao: {}` e `codigoDoOrgao`. A tela preenche
    `codigoDoOrgao` com o órgão principal; sem ele, vêm todas as entidades.
  - **Resposta:** `{total, registros, paginaAtual, ano, mes}`, com os campos da detalhada da Megasoft própria.
  - Em 09/2025 vieram 133 linhas, de 9 órgãos, todas com `chave` 2025/09.
- **Contratos:** `acao = contratos_mg/listar`, controller `contrato/contratos_mg`.
  - **Filtros:** `ano` (ano do contrato), `mes`, `data_inicial`, `data_final`, `orgao`, `numero`, `objeto`,
    `nome_contratado`, `cgc_contratado`, `licitacao`, `situacao`, `valor`, `possui_aditivo`, `ano_aditivo`,
    `coronavirus` e `txtbusca`.
  - **Resposta:** `{dados, total, ano, sg_contratos_ocultar_alertas}`. Com `ano=2025`, vieram 245 de 245, todos com
    `ano` 2025, de 6 órgãos.
  - **Campos:** `id`, `label`, `orgao` (código), `licitacao_id`, `licitacao_label`, `licitacao_label_short`,
    `licitacao_url`, `numero`, `ano`, `situacao`, `data_publicacao`, `data_firmatura`, `inicio_vigencia`,
    `fim_vigencia`, `fornecedor_nome`, `fornecedor_cpfcnpj`, `objeto`, `fiscal_contrato` (pessoa), `periodo`, `valor`,
    `valor_executado` e `saldo`.
    - Os valores vêm como texto, no formato "501.902,40", e as datas, em dd/mm/aaaa.
    - Também vêm `local_da_execucao`, `numero_colare`, `data_colare`, `coronavirus` e `anexos`.
  - **Armadilha:** fornecedor pessoa física em 40 dos 245.
- **Licitações e dispensas:** `acao = licitacoes_mg/listarCidadao`, controller `licitacao/licitacoes_mg`.
  - **Filtros:** `ano`, `numero`, `modalidade`, `situacao`, `orgao`, `descricao`, `datapub_min`/`datapub_max`,
    `dataaber_min`/`dataaber_max`, `valor_estimado_*`, `valor_vencedor_*` e `coronavirus`. A tela também manda
    `dispensas`, `fracassadas_desertas` e `abertas`.
  - **Com `ano=2025`:**
    - com `dispensas` falso, vieram 40 licitações;
    - com `dispensas` verdadeiro, vieram 1.078 (1.020 dispensas, 50 inexigibilidades, 8 chamamentos).
  - **Resposta:** `{dados, total, modalidades_permitidas, situacoes_permitidas, ano}`.
  - **Campos:** `chave`, `label`, `modalidade`, `situacao`, `orgao`, `numero`, `ano`, `data_publicacao`,
    `data_julgamento`, `data_homologacao`, `data_abertura`, `data_protocolo`, `valor_vencedor_total` e `descricao`.
  - **Armadilhas:**
    - **período por data falha:** `datapub_min`/`datapub_max` em aaaa-mm-dd devolveu `error` "Houve um problema com a
      requisição", com total 0, e o formato dd/mm/aaaa não foi testado;
    - **`ano` é o ano da licitação:** 5 das 1.078 têm publicação em 2024;
    - **os 8 chamamentos vêm nas duas listas.**
- **Diárias:** `acao = sgdiarias/listar`, controller `diarias/sgdiarias`.
  - **Filtros:** `datamin`/`datamax` em aaaa-mm-dd, `orgao`, `cargo`, `favorecido`, `destino`, `cidade`, `quantidade`,
    `valmin`/`valmax`, `descricao` e `txtbusca`. A tela também tem `ano` e `mes` e manda `limit`.
  - No 1º trimestre de 2025 vieram 646 diárias, todas com `data_inicio` dentro do período e só uma com `data_fim` fora,
    em 4 órgãos.
  - **Campos:** `tabela`, `orgao_nome`, `orgao_id`, `orgao`, `favorecido` (pessoa), `cargo`, `data_inicio`, `data_fim`
    (aaaa-mm-dd), `data_liquidacao`, `destino`, `cidade`, `quantidade`, `valor` (texto, "87.16"), `numero_processo`,
    `numero_empenho`, `descricao`, `anexos`, `chave` e `total`.
  - **Armadilha:** `total` em cada linha é a **contagem** da consulta ("646"), não dinheiro.

### C. Centi (Posse)

- **Identificação:** como já se sabia, Posse recusa a identificação do projeto (403). Com a de navegador, responde.
- **Receitas (`cntreceitas`, controller `receitas/receitas_centi`):** `POST {portal}/api/centi`, num formulário simples.
  - **Filtros:** `acao=receitas`, `ano`, `mes` (`"09"`) e **`orgao` (obrigatório)**. Sem `orgao`, a resposta traz
    `error` "Campo(s) obrigatório(s)… Orgao (long)".
  - **Órgãos:** vêm de `acao = sgcenti/listarOrgaos`, no envelope NucleoGov: 13 órgãos, e o principal é o 3 (Poder
    Executivo). Não há `id_orgao=0` aqui: cada órgão é lido em separado.
  - **Outros filtros da tela:** `origem`, `especie`, `desdobramento`, `tipo`, `categoria_economica`,
    `prevmin`/`prevmax`, `arrmin`/`arrmax` e `txtbusca`.
  - **Resposta:** `{dados, ano, mes, lista_categoria_economica, lista_origem, lista_especie, lista_desdobramento,
    lista_tipo, error}`.
  - Em 09/2025, órgão 3, vieram 246 linhas, todas de 2025, `mes` "Setembro" e órgão Poder Executivo.
    `TotalRegistros` vale 246 em todas.
  - **Campos:** `CodigoElemento`, `DescricaoElemento`, `CodigoFonte`, `Fonte`, `Destinacao`, `Especificacao`,
    `ValorOrcado`, `PrevisaoAtualizada`, `ValoReceitaAcumuladoMes` (a do mês), `ValoReceitaAcumulado`,
    `DiferencaPositiva`, `DiferencaNegativa`, `Id`, `Ano`, `Orgao`, `TotalRegistros`, `TipoConta`, `mes` e
    `nat_categoria_economica`/`origem`/`especie`/`desdobramento`/`tipo`. Os valores vêm como texto, no formato
    "12.856.885,70".
  - **Armadilha: `TipoConta`.**
    - `2` são as contas sintéticas (171), que agregam as outras. Somar tudo conta em dobro.
    - `1` são as analíticas (72). A soma delas no mês, R$ 11.626.838,01, **bate ao centavo** com as raízes:
      1.0.0.0.00.0.0 menos a dedução 91.0.0.0.00.0.0, mais a 2.0.0.0.00.0.0, que é zero.
    - No acumulado, as analíticas passam das raízes em R$ 334.029,19, e a diferença não foi explicada.
    - `0` são 3 linhas, sem valor no mês.
- **Ações da biblioteca Centi (`cidadao/requisicoes/centi.js`):** `orgaos`, `funcoes`, `receitas`,
  `receitasMovimento`, `receitas_covid`, `empenhos`, `empenhos_covid`, `licitacoes`, `contratos`, `servidores`,
  `servidores_campos`, `diarias`, `emitir_lista_diarias`, `obras`, `duodecimo`, `repasses`, `balancete_mensal`,
  `rel_rreo`, `rel_gestao_fiscal`, `planejamento` e `balanco_geral_anual`. Só `receitas` e `empenhos` foram testadas.
- **Menus `cnt*` de Posse:**
  - **Da Centi:**
    - `cntreceitas`: receitas, acima;
    - `cntdespesas`: empenhos, que o projeto já lê;
    - `cntrepasses`: Transferências Concedidas, controller `repasses/repasses_centi`.
  - **Pelo nome, relatórios fiscais; não foram abertos:** `balancoscnt`, `rgfscnt`, `rreoscnt`, `planejamentocnt` e
    `balancetemensalcnt`.
  - **Módulos NucleoGov com sufixo `cnt`, não da Centi:** `servidores_cnt`, `licitacoes_cnt`, `licitacoes_abertas_cnt`,
    `licitacoes_fd_cnt`, `dispensas_cnt`, `contratos_cnt`, `aditivos_cnt`, `ordem_cronologica_pagamentos_cnt` e
    `diarias_cnt`.

### D. Diárias no NucleoGov

- **Ação:** `acao = diarias_<sufixo>/listar`, no envelope de sempre. O sufixo varia: `diarias_cnt` em Posse,
  `diarias_frl` em Senador Canedo.
- **Filtros (controller `diarias/diarias_cnt`):** `datamin`/`datamax` em aaaa-mm-dd, `orgao`, `cargo`, `favorecido`,
  `destino`, `cidade`, `motivo`, `quantidade`, `valmin`/`valmax`, `txtbusca` e `periodo…`/`chegada_…`.
- **Identificação:** os dois portais recusam a do projeto (403). Com a de navegador, respondem.
- **Posse (`diarias_cnt`), 1º trimestre de 2025:**
  - 64 diárias, nenhuma com `data_inicio` fora do período e uma com `data_fim` fora;
  - **todas do órgão principal:** a resposta traz `orgao_principal: 3` e só o Poder Executivo veio. Sem `orgao`, o
    portal aplica o órgão principal; não foi testado como pedir os outros;
  - **resposta:** `{dados, total, orgao_principal, data_min, data_max}`;
  - **campos:** `id`, `id_empenho`, `id_orgao`, `orgao_nome`, `favorecido` (pessoa), `cargo`, `destino`, `cidade`,
    `valor` (inteiro), `data_inicio`/`data_fim` (dd/mm/aaaa), `quantidade` e `descricao`.
- **Senador Canedo (`diarias_frl`), 1º trimestre de 2025:**
  - 115 diárias, todas com `data_saida` e `data_empenho` dentro do período, em 4 órgãos (fundos e Prefeitura);
  - **resposta:** `{dados, total, orgao_principal: null, anobase}`;
  - **campos:** `id`, `orgao`, `orgao_id`, `favorecido` (pessoa), `data_saida` (dd/mm/aaaa), `data_chegada`,
    `data_empenho` (aaaa-mm-dd), `destino`, `quantidade`, `valor`, `descricao`, `descricao_produto`, `anobase` e `cargo`;
  - **armadilha: sem valor.** `valor`, `quantidade`, `cargo`, `data_chegada` e `descricao_produto` vieram **vazios nas
    115**: o portal não publica o valor das diárias.
- **Armadilhas:**
  - **campos diferentes por portal:** cada portal traz campos e formatos de data diferentes;
  - **sufixo:** o sufixo errado volta zero sem erro, como nos outros módulos.

### E. Ortrel (as 4 câmaras)

- **Todas no mesmo modo:** as 4 servem o site em modo de desenvolvimento do Vite (`/@vite/client`, `/src/main.jsx`;
  `"DEV": true` no `api.js`).
- **API e token:** o `api.js` traz `API_URL` e um `VITE_FIXED_TOKEN` preenchido.
  - O endereço é `https://api.<domínio do portal>`:
    - `api.transparencia.cidadeocidental.go.leg.br`;
    - `api.transparencia.luziania.go.leg.br`;
    - `api.transparencia.saojoaodalianca.go.leg.br`;
    - `api.transparencia.camaravalparaiso.go.gov.br`.
  - Valparaíso é `.go.gov.br`.
- **Onde estão os caminhos:** as páginas não trazem os caminhos. Eles ficam nos ganchos
  `/src/hooks/<tema>/use<Tema>Query.js`; a lista de páginas está em `/src/App.jsx`.
- **Só Cidade Ocidental foi medida.** Nas outras três, só o `api.js` foi lido.
- **Folha:** `GET /api/dados/rh/folha_de_pagamento?limit=100000&page=1`.
  - **Série inteira numa chamada:** 6.046 linhas (14 MB), de 01/2021 a 10/2026, 70 competências, até 137 linhas por
    mês. As 6.046 combinações de (matrícula, ano, mês) são distintas.
  - **Resposta:** `{folhaPagamento, PagamentosPaginados (cópia), totalPages}`.
  - **Campos:** `matricula`, `nome`, `cpf`, `cargo`, `situacao`, `data_admissao`, `proventos`, `descontos`,
    `total_liquido` (texto, "14452.33"), `departamento`, `situacao_pagamento`, `ano` (inteiro), `mes` ("10"),
    `orgao`, **`decreto` e `data_decreto` (preenchidos nas 6.046)**, `tipo_vinculo`, `nivel`, `carga_horaria`,
    `jornada_semanal`, `categoria_esocial`, `cargo_rec`, `itens_total_proventos`, `itens_total_descontos` e
    **`itens`**.
  - **`tipo_vinculo`** vem por extenso, no texto do eSocial. Exemplos: "SERVIDOR PUBLICO NAOEFETIVO DEMISSIVEL AD
    NUTUM…" (4.244), "AGENTE POLITICO" (993), "SERVIDOR REGIDO PELO REGIME JURIDICO UNICO… REGIME PROPRIO…" (717),
    "DISPOSIÇÃO - RECEBIDOS COM ONUS" (42), "COMISSAO" (24).
  - **Rubricas existem no Ortrel.** `itens` é um JSON em texto, com `nome_item`, `tipo` (Proventos/Descontos),
    `provento`, `desconto`, `ano` e `mes`.
    - São 68 rubricas distintas, como "SALARIO BASE", "INSS", "AUXILIO ALIMENTACAO" e "GRATIFICACAO DE
      TITULARIDADE 10%".
    - Ano e mês dos itens batem com os da linha em todas as linhas.
  - **Armadilha:** a soma dos proventos dos `itens` bate com `proventos` em só **3.914 das 6.046** linhas. A diferença
    não foi investigada; usar `proventos` como o valor da linha.
- **Legislação:** `GET /api/dados/legislacao/leis_municipais?limit=1000&page=1`.
  - Vieram 1.515 linhas numa página, apesar do `limit=1000`, com `totalPages: 1`.
  - **Resposta:** `{leisMunicipais, leisMunicipaisPaginados (cópia), totalPages}`.
  - **Campos:** `id`, `codigo`, `tipo` (só "Lei"), `numero`, `ano` (1991 a 2026; um vazio), `data_publicacao`,
    `nome_ato`, `descricao`, `nome_arquivo`, `caminho_arquivo` e `midia_arquivo_assinado` (PDF, presente em 1.510).
  - **Armadilha:** 217 pares (tipo, número) se repetem, com `id` distintos. É o "repetido com ano diferente" já
    conhecido.
- **Despesas (empenhos):** `GET /api/dados/despesas`. Achada e medida.
  - **Filtros da tela:** `page`, `limit`, `ano`, `mes`, `busca`, `fonte`, `orgao`, `grupo`, `modalidade`,
    `classificacao`, `categoria` e `elemento`. Os filtros possíveis vêm de `/api/dados/despesas/filtros`.
  - **Mês e ano respeitados:** `ano=2025&mes=3` deu 100 empenhos, todos com `data` em 2025-03.
  - **Teto de página:** a resposta veio com `limit: 100` e total 166 (`totalPages: 2`), mesmo pedindo `limit=1000`. É
    preciso paginar com `page`.
  - **Resposta:** `{despesas, despesasPaginados (cópia), total, page, limit, totalPages, totais}`, com
    `totais {totalEmpenho, totalLiquidado, totalPago}` em números.
  - **Campos:** `id_despesa`, `data` (aaaa-mm-dd), `fonte_recurso`, `nome_fornecedor`, `cpf_cnpj_mascarado`
    (`999******99`: o documento vem **mascarado**, então o filtro por CNPJ do projeto não serve aqui),
    `classificacao_orcamentaria`, `orgao_unidade_gestora`, `unidade`, `funcao`, `subfuncao`, `grupo_despesa`,
    `elemento_despesa`, `categoria_economica`, `tipo_empenho`, `valor_empenho`, `valor_liquidado`,
    `valor_total_pagamento` (texto, "200.00"), `modalidade`, `numero_ano_licitacao`, `numero_processo_licitatorio`,
    `bem_servico_prestado` e `liquidacoes_json`/`pagamentos_json`. Em `liquidacoes_json`, o JSON em texto traz
    `nr_liquidacao`, `documento`, `data_liquidacao`, `valor_liquidacao` e `historico`.
- **Diárias:** `GET /api/dados/rh/diarias?limit=1000`.
  - Vieram 6.098 linhas numa só chamada (3 MB), com `totalPages: 1`: **a série inteira**, com saídas de 2014 a 2026.
    Há datas espúrias (1899, 2010).
  - **Período:** a página não manda filtro de período. O recorte fica com o projeto.
  - **Campos:** `data_pagamento`, `nome_funcionario` (pessoa), `numero_diarias`, `valor_diaria`, `valor_total` (texto,
    "200.0000"), `cargo_funcionario`, `destino`, `data_saida`, `data_chegada` (aaaa-mm-dd), `natureza_despesa` e
    `Histórico` (com acento no nome da chave).
- **Contratos:** `GET /api/dados/todos-contratos`.
  - Vieram 213 contratos de uma vez, de 2018 a 2026, sem filtro.
  - **Resposta:** `{contratos, totalContratos, contratosAtivos, contratosEncerrados, totalPages}`.
  - **Campos:** `id`, `numero_contrato`, `modalidade`, `numero_e_ano_licitacao`, `numero_processo`, `data_assinatura`,
    `data_vigencia_fim`, `data_publicacao`, `periodo`, `codigo_orgao`, `nome_orgao`, `cnpj_fornecedor`,
    `nome_fornecedor`, `objeto`, `valor_contratado`, `valor_executado`, `valor_aditado`, `valor_total`, `saldo`,
    `nome_fiscal` (pessoa), `exercicio_ano`, `situacao`, `codigo_licitacao`, `numero_envio_colare` e `anexos`.
- **Licitações:** `GET /api/dados/licitacoes`, com timeout de 60 s na tela.
  - Vieram 595 registros de uma vez (3 MB), sem filtro, com publicação de 2020 a 2026; 15 vieram sem data.
  - **Resposta:** `{dados, dadosPaginados (cópia), totalPages}`.
  - **Modalidades:** dispensas (290), convites (265), inexigibilidades (21) e outras. As dispensas vêm junto.
  - **Campos:** `id_licitacao`, `numero_protocolo`, `numero_ano`, `modalidade_numero_ano`, `modalidade`, `situacao`,
    `data_protocolo`, `data_abertura`, `data_julgamento`, `data_homologacao`, `data_publicacao`, `valor_estimado`,
    `valor_vencedor`, `orgao`, `descricao`, `natureza_objeto`, `natureza_procedimento`, `colare_*`, `pncp_*` e
    `itens_vencedores` (JSON em texto).
  - **Anexos:** `/api/dados/licitacoes-anexos/{id}`.
- **Também existem, não testadas:** as páginas de receitas, cotas e gastos parlamentares, ordem cronológica,
  fiscais de contratos e plano anual (em `App.jsx`).

### F. TCMJuris

- **Número completo:** `numero_processo_filtro=10175/23` deu 1 resultado, o próprio processo, com o acórdão 07286/24.
- **Parte do número:** sem o ano, a busca devolve o número em **todos os anos**:
  - `numero_acordao_filtro=7286` deu 5: 07286/20, /22, /23, /24 e /25;
  - `numero_processo_filtro=10175` deu 3: 10175/20, /23 e /24.
  - O zero à esquerda não precisa ser digitado.
- **"Contém" ou "começa com":** nas duas buscas, todos os resultados começam com a parte pedida. Uma parte do meio
  do número não foi testada.
- **Armadilha:** pedir o número sem o ano mistura acórdãos de anos diferentes. A conferência campo a campo
  (decisão 5) precisa comparar número **e** ano.

### Tabela-resumo

| Sistema | Receitas | Diárias | Contratos | Licitações | Detalhe do servidor | Folha | Legislação | Despesas |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Megasoft própria | achado e conferido | achado e conferido | achado e conferido | achado e conferido | achado com ressalva | já no projeto | já no projeto | já no projeto |
| Megasoft embutida | achado e conferido | achado e conferido | achado e conferido | achado com ressalva | não existe ou não achado | já no projeto | não medida nesta onda | já no projeto |
| Centi (Posse) | achado com ressalva | não existe ou não achado | não existe ou não achado | não existe ou não achado | não existe ou não achado | não existe ou não achado | não medida nesta onda | já no projeto |
| NucleoGov (diárias) | — | achado com ressalva | já no projeto | já no projeto | — | já no projeto | já no projeto | já no projeto |
| Ortrel (4 câmaras) | não medida nesta onda | achado com ressalva | achado e conferido | achado com ressalva | não existe ou não achado | achado e conferido | achado com ressalva | achado e conferido |

Na Megasoft própria e na embutida, as diárias são as da Megasoft na própria e as do `sgdiarias` do NucleoGov na
embutida. "Já no projeto" quer dizer que não foi remedido aqui. "—" quer dizer que o módulo não se aplica ao sistema.

Ressalvas da tabela:
- **Detalhe do servidor (Megasoft própria):** existe e traz decreto, data do decreto, vínculo, licenças e os
  movimentos. **Rubricas: não existem.** Onde fica o 13º continua sem resposta: o 13º veio vazio na amostra.
- **Licitações (Megasoft embutida):** o filtro de período por data deu erro; o `ano` funciona.
- **Detalhe do servidor (Megasoft embutida):** a única ação conhecida, `megasoft/servidoresDetalhe`, traz só o nome
  (medição anterior). Nenhuma outra foi achada nos menus.
- **Receitas (Centi):** o órgão é obrigatório, então é uma leitura por órgão. Em `TipoConta`, só as analíticas (`1`)
  podem ser somadas; o mês confere, e o acumulado tem diferença sem explicação.
- **Centi, outros módulos:** a biblioteca tem `licitacoes`, `contratos`, `diarias` e `servidores`, mas Posse usa os
  módulos NucleoGov `*_cnt` para licitações, contratos, diárias e folha; as ações da Centi não foram testadas.
- **Diárias (NucleoGov):** campos diferentes por portal. Em Posse, sem `orgao`, só vem o órgão principal. Em Senador
  Canedo, o valor vem vazio.
- **Diárias (Ortrel):** a série inteira, sem filtro de período, com datas espúrias.
- **Licitações (Ortrel):** tudo de uma vez; 15 vieram sem data de publicação.
- **Legislação (Ortrel):** 217 números repetidos.
- **Ortrel em geral:** só Cidade Ocidental foi medida; nas outras três, só a API e o token.
- **TCMJuris (fora da tabela, porque não tem esses módulos):** acórdão por número achado e conferido. Os dois filtros
  funcionam com o número completo (`10175/23`) ou com parte dele. A parte sem ano devolve todos os anos, e a
  ferramenta precisa conferir número e ano.

## O que a implementação mediu (ondas 1 e 2)

Medido ao vivo em 04/11/2026, com pausa de 1 s e sem gravar nomes de pessoas. Onde o fato contradiz a descoberta,
vale este.

### Correções à descoberta

- **Ortrel, despesas: o CNPJ vem completo.** A descoberta registrou o documento como mascarado. Só o **CPF de pessoa
  física** vem mascarado (`999******99`); o CNPJ de empresa vem inteiro (`00.000.000/0000-00`), e a busca por CNPJ
  funciona (Cidade Ocidental, 03/2025: 17 empenhos do CNPJ medido, todos dele).
- **Ortrel, legislação: os 217 "repetidos" são, quase todos, leis diferentes.** A numeração recomeçou ao longo dos
  anos (ex.: Lei 011/1993, Lei 011/1995 e Emenda à Lei Orgânica 011/2025). Repetição de verdade (mesmo número e
  mesmo ano no nome do ato): **1**. Outros 7 pares têm o mesmo número e a mesma ementa em anos diferentes; podem ser
  recadastro, mas não dá para afirmar, e a resposta os mantém com ressalva.
- **Diárias: Senador Canedo tem 6 órgãos** no 1º trimestre de 2025, não 4. A Megasoft embutida de Aruanã
  (`sgdiarias`) também: 6 órgãos, não 4.
- **O `txtbusca` das diárias não funciona no NucleoGov:** em Posse e Senador Canedo respondeu total 0 com palavras
  presentes em 39 e 96 linhas do trimestre. O projeto filtra a busca ele mesmo. Na Megasoft embutida (`sgdiarias`)
  ele funciona ("GOIANIA": 408 de 646, todas casando, sem acento casa com acento).
- **Posse, diárias: o filtro `orgao` é respeitado** (3 → 64; 1, 4 e 5 → 0). No trimestre medido não havia diárias
  escondidas de outros órgãos.
- **Acórdão por número:** `7286` sem ano deu 10 resultados em 7 anos, não 5, porque o projeto busca nos dois filtros
  (processo e acórdão); os outros 5 são processos 7286/AA.

### Achados novos, por sistema

- **Megasoft própria (Corumbaíba):**
  - diárias: `valorDaDiaria` é um só valor por viagem e parece o total (4 diárias, R$ 350,00); vai em `valor`, com
    ressalva;
  - detalhe do servidor: o portal ignora `tamanhoDaPagina` e devolve as listas internas de 5 em 5; matrícula
    inexistente responde **HTTP 406** "Valor de chave não existe" (o projeto devolve total 0);
  - contratos: 3.005 sem ano, numa página de 5.000; aditivos só dentro do detalhe de cada contrato.
- **Megasoft embutida (Aruanã):**
  - contratos: **`txtbusca` zera a resposta**; `objeto` filtra; sem `ano`, vêm todos os anos; `orgao` só como código;
  - licitações: `error` "Houve um problema com a requisição" (total 0) no filtro de período. O cliente agora trata
    `error` como recusa, não como zero;
  - receitas: a mesma receita vem uma vez por fonte de recurso, com o mesmo código;
  - diárias: `valor` é o total da linha; 3 linhas com `quantidade` 657437.
- **Centi (Posse):** `listarOrgaos` devolve lista crua (13 órgãos, **sem a Câmara**); o filtro de órgão das receitas
  vale; um órgão veio vazio e, minutos depois, com 16 linhas (vazio passageiro, como nas despesas). No mês, a soma
  das analíticas do Poder Executivo bate ao centavo com a conta do topo; no acumulado, fica R$ 334.029,19 acima.
- **Ortrel (Cidade Ocidental):** a folha **não tem linha de 13º** (o 13º, as férias e a rescisão são rubricas da
  linha do mês); `situacao_pagamento` e `nivel` vêm sempre "Não Informado"; despesas por `ano`+`mes` respeitados.
- **NucleoGov, contratos: o ano ia num filtro ignorado.** O projeto mandava `anobase`, que o portal ignora:
  `contratos(2025)` trouxe contratos de 2026 em Posse, e a conferência (`contratos_ano`) marcou `falhou` em Alexânia.
  O filtro certo é `ano`. Alexânia: em `contratos_frl`, 147 sem filtro, 147 com `anobase` (de 2023 a 2025) e 34 com
  `ano`, todos de 2025; em `contratos_cnt` (o do catálogo), 6.989 sem filtro e 798 com `ano`, todos de 2025.
  Corrigido no fechamento, com teste ao vivo em Senador Canedo.

### Nomes unificados de contratos e licitações

Os nomes do NucleoGov valem para todo sistema (a API NucleoGov devolve os campos dela, sem tradução):

| Conceito | Contratos | Licitações |
|---|---|---|
| identificador interno | `id` | `chave` (a embutida também dá `chave`, crua, fora da tradução) |
| número | `numero` | `numero` (sem o ano) e `label` (número/ano) |
| ano | `ano` | `ano` onde o sistema dá (NucleoGov, embutida) |
| órgão | `orgao` = código, `orgao_nome` = nome | `orgao` = nome |
| objeto | `objeto` | `descricao` |
| fornecedor | `fornecedor_nome`, `fornecedor_cpfcnpj` | — |
| datas | `data_publicacao`, `data_firmatura`, `inicio_vigencia`, `fim_vigencia` | `data_publicacao`, `data_abertura` |
| valor | `valor` | `valor_estimado`, `valor_vencedor` |
| fiscal | `fiscal_contrato` | — |

Ficam com nome próprio, porque o NucleoGov não tem o conceito: `licitacao`, `modalidade`, `processo`, `finalidade`,
`valor_executado`, `saldo`, `valor_aditado`, `valor_total`, `anexos` (contratos); `data_julgamento`,
`data_homologacao`, `data_protocolo`, `protocolo`, `itens_vencedores` (licitações).

### Conferência dos módulos novos

`conferencia.py` ganhou `diarias_periodo` (saídas no mês de referência), `contratos_ano` e `licitacoes_ano` (cada
registro do ano pedido e o total com ano menor que sem ano). Quando o encaixe recusa uma resposta que ignorou o filtro
("fora do período", "de outro ano"), a conferência marca `falhou`; parâmetro que o projeto recusa (o ano das
licitações no NucleoGov, decreto no Ortrel) marca `nao_suportado`. O passo `conferir` do catálogo passou a ler o
Ortrel. Diárias sem nenhuma data de saída legível saem `sem_dados`, nunca `ok`; total com ano igual ao sem ano só
passa se a amostra sem ano for o portal inteiro e toda daquele ano.

Limite: no Ortrel, contratos, licitações e diárias vêm inteiros e o recorte por ano ou período é do projeto. Ali o
`ok` dessas três verificações confere o código do projeto, não um filtro do portal.
