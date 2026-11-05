# Como o portal NucleoGov se comporta de verdade

Medido ao vivo em Senador Canedo (`acessoainformacao.senadorcanedo.go.gov.br`), 04/11/2026.
Outros municípios podem variar, e o próprio portal muda sem aviso. O teste `tests/test_ao_vivo.py`
reconfere os filtros abaixo. Rode-o depois de mudar uma consulta e antes de cada versão.

## Pedido

`POST {portal}/api/{acao}` com o formulário `multi_request=true&params={"<id>": {filtros...,
"limit": "<offset>, <n>", "acao": "<acao>"}}`. A resposta vem como `{"<id>": {"dados": [...], "total": N}}`.

Sem User-Agent de navegador, o portal devolve **403**. Veja a seção "O 403" do README.

## Filtro respeitado, filtro ignorado

O portal **ignora em silêncio** um filtro que não conhece: devolve dados, só que errados. Por isso,
toda consulta nova precisa de uma chamada ao vivo que mostre o total mudando e os registros obedecendo ao filtro.

| Consulta | Funciona | Ignorado ou armadilha |
|---|---|---|
| Despesas `despesas_frl/listar` | `datamin`/`datamax`; `txtbusca` acha **nome** do fornecedor; `cpf_cnpj` formatado (`00.000.000/0000-00`) acha CNPJ | CNPJ em `txtbusca` volta 0 |
| Receitas | `ano` + `mes` | `datamin`/`datamax` ignorados: volta o mês corrente |
| Legislação `atos/buscaAvancada` | `tipo` 1 = decreto, 2 = portaria, 3 = resolução; `search` (palavra na ementa); `ano` | `atos_pf_<municipio>/listar` volta vazio (até na tela do site) |
| Leis `leis/listar` | lista tudo (41 em Senador Canedo) | ignora busca |
| Folha | `ano` + `mes`; busca só por **nome** | sem `mes`, volta só o mês mais recente do ano |
| Diárias `diarias_<sufixo>/listar` | `datamin`/`datamax` (aaaa-mm-dd), pela saída; `orgao` (Posse) | `txtbusca` volta 0 com palavra presente (Posse, Senador Canedo); sem `orgao`, alguns portais trazem só o órgão principal |
| Contratos `contratos_<sufixo>/listar` | `tipo` contrato/aditivo; `ano` (Alexânia, `contratos_cnt`: 798 de 6.989, todos de 2025) | `anobase` é ignorado (`contratos_frl` de Alexânia: 147 com e sem ele): até a v0.5.0 o projeto o mandava, e o ano dos contratos vinha de todos os anos |
| Licitações `licitacoes_<sufixo>/listar` | `dispensas`, `txtbusca` | o `ano` não foi medido e é recusado pelo projeto |

## Diárias (04/11/2026)

Medidas no 1º trimestre de 2025 em Posse (`diarias_cnt`) e Senador Canedo (`diarias_frl`); o teste ao vivo é
`tests/test_ao_vivo_diarias_nucleogov.py`.

- **Campos diferentes por portal.** Posse: `orgao_nome`, `data_inicio`/`data_fim`, `valor` e `quantidade` inteiros
  (`valor` é o total da viagem), `destino` em texto livre e `cidade` padronizada, `id_empenho` como chave interna.
  Senador Canedo: `orgao`, `data_saida`/`data_chegada`, e `valor`, `quantidade`, `cargo`, `data_chegada` vazios nas
  115; `destino` é `" - "` nas 115. O projeto traduz para nomes comuns e diz o que veio vazio.
- **Órgãos.** Posse: 64 diárias, todas do Poder Executivo; a resposta traz `orgao_principal: "3"`, e o filtro
  `orgao` é respeitado (os outros códigos deram 0). Senador Canedo: 115 diárias de **6 órgãos**,
  `orgao_principal: null`.
- **Busca.** `txtbusca` respondeu 0 nos dois portais com palavras presentes em 39 (Posse, destino) e 96 (Senador
  Canedo, motivo) linhas. O projeto lê o período inteiro e filtra.
- **Período respeitado** nas saídas dos dois portais; uma `data_fim` passa do período em Posse.

## Formatos dos campos

- Despesas: `data` vem como `dd/mm/aaaa`; `cpf_cnpj` vem formatado.
- Receitas: `mes` sem zero (`"3"`); `valor_total_arrecadado_mes` vem como texto em reais (`"183.487,22"`).
- Folha: `mes` com zero (`"03"`); CPF mascarado. Linhas de 13º e de rescisão vêm junto no mesmo
  mês, com a matrícula repetida. O campo `tipo_folha` as distingue: `Folha Mensal`, `Fechamento 13º Salário`
  ou `Rescisão`.
- Folha, rubricas: `lista_proventos` + `lista_descontos` somam exatamente `total_proventos` e
  `total_desconto`. Há também `eventos` (39% do peso da linha),
  com as rubricas em outro formato numérico; não conferido se bate. A folha leve não o usa.
- Legislação: `tipo` vem como texto (`"1"`), e `ano` também.

## Tamanho

A folha é pesada: 100 servidores dão cerca de 330 mil caracteres (uns 83 mil tokens). Mandar a
folha inteira para um assistente de IA estoura o contexto dele.

## Outras cidades de Goiás (conferência de 04/11/2026)

A conferência (`transparencia_municipal/conferencia.py`, rodada por `scripts/catalogo_go.py conferir`) mediu os
32 órgãos de 16 municípios. O resultado de cada portal fica no catálogo (`catalogo_go.json`). A 4ª rodada (04/11/2026)
passou pelos caminhos da Megasoft (embutida e própria) e da Centi:
- folha (mês) e despesas (período e CNPJ) `ok` em 29 órgãos, entre eles Posse (Centi), Aruanã (Megasoft embutida),
  Corumbaíba e Alto Paraíso (Megasoft própria), antes recusados;
- fora do NucleoGov, a sondagem de órgãos escondidos sai `sem_dados`, e receitas e legislação da Megasoft própria,
  `nao_suportado`;
- `erro` só onde não há API: Nova Crixás e a Câmara de Orizona (`/api/` responde 404); a Câmara de Pirenópolis não
  publica folha nem despesas. A Câmara de Alto Paraíso, cujo endereço NucleoGov não resolve, é conferida pelo portal
  Megasoft próprio dela.
As despesas são conferidas no mês de referência (a Centi devolve o período inteiro numa resposta só). Dez órgãos
NucleoGov e Megasoft embutida foram medidos antes dessa mudança, no 1º trimestre.

- **Sufixo do módulo por portal.** A ação é `<modulo>_frl/listar` ou `<modulo>_cnt/listar`. **Com o sufixo errado o
  portal responde total 0, sem erro.** Chapadão do Céu: `servidores_frl` dá 0 e `servidores_cnt` dá 224. Um sufixo
  que não existe responde `[]`. O cliente aprende o sufixo na página inicial; quando não acha, tenta `frl` e depois `cnt`.
- **Módulos de outros sistemas.** Na página inicial, `mgservidores`, `mgdespesas` e `mgreceitas` indicam a Megasoft
  embutida; `cntdespesas` e `cntreceitas` indicam a contabilidade Centi. A API NucleoGov às vezes serve o módulo
  mesmo assim (Alexânia sim, Posse não), então uma consulta sem filtro decide, uma vez por endereço. Se ela volta
  vazia, folha e despesas vão pela Megasoft embutida ou pela Centi (seção seguinte); os outros módulos são recusados
  (`ModuloNaoSuportado`). Na amostra:
  - despesas pela API NucleoGov só na Prefeitura de Alexânia;
  - folha da Megasoft embutida em 10 órgãos.
- **Órgãos escondidos na folha.** Sem o filtro `orgao`, a folha trouxe um órgão só em 6 prefeituras:

  | Prefeitura | Órgão que vem sem filtro | Órgãos que só aparecem com filtro |
  |---|---|---|
  | Trindade | 3 | 5, 6, 7, 8 e 10 |
  | Guapó | 3 | 4, 5 e 8 |
  | Itapuranga | 3 | 4, 6 e 8 |
  | Pirenópolis | 3 | 4, 6 e 7 |
  | Posse | 3 | 5 |
  | São Miguel do Araguaia | 1 | 3 e 4 |

  Em Senador Canedo a folha sem filtro já mistura os órgãos (o código é `001`). A leitura do mês sonda os
  códigos de 1 a 15.
- **Folha só recente.** Em vários portais o mês 06/2025 veio vazio, mas o mês mais recente (10/2026) estava
  publicado. A conferência usa o mês mais recente.
- **Legislação sem `ano`.** Em 6 portais o campo `ano` vem vazio; o ano sai de `data_publicacao`.
- **Site oficial NucleoGov sem API.** `novacrixas.go.gov.br` e `camaradeorizona.go.gov.br` mostram páginas
  NucleoGov, mas `/api/` responde 404.
- **Paginação que falha no meio.** Na leitura do mês inteiro de Trindade (10/2026, 2.237 linhas sem filtro), uma
  página no meio voltou vazia e com total 0. Foi o offset 1800 numa leitura e o 1000 na outra; sozinha, a mesma
  página responde. O cliente usa o total da 1ª página e repete a página vazia esperando 2, 5 e 10 s. Se ainda
  faltar linha, a leitura sai como **incompleta**, nunca como "zero".
- **Rótulos do tipo de pagamento.** Senador Canedo: `Folha Mensal`, `Fechamento 13º Salário`, `Rescisão`.
  Trindade: `MENSAL`, `13º SALÁRIO ADIANTAMENTO`, `RESCISÃO`. O resumo trata como mensal todo rótulo com "mensal".
- **Trindade, 10/2026, com os órgãos escondidos:** 3.638 linhas, contra 2.237 sem filtro. Órgão 3: 2.237;
  órgão 5: 835; órgão 7: 496; órgão 8: 70.

## Megasoft e Centi (04/11/2026)

Módulos que não vêm pela API NucleoGov. Medido em Corumbaíba (Megasoft própria), Aruanã (Megasoft embutida)
e Posse (Centi); os desenhos são `docs/design/2026-11-04-megasoft-centi.md` (folha e despesas) e
`docs/design/2026-11-04-modulos-extras.md` (receitas, diárias, contratos, licitações e detalhe do servidor). Os
testes ao vivo `tests/test_ao_vivo_megasoft_propria*.py`, `tests/test_ao_vivo_megasoft_embutida*.py`,
`tests/test_ao_vivo_centi*.py` reconferem estes pontos.

| Sistema | Pedido | Funciona | Ignorado ou armadilha |
|---|---|---|---|
| Megasoft própria (`*.megasofttransparencia.com.br`) | `GET /api/<caminho>?pagina=&tamanhoDaPagina=` com `Authorization: Bearer <tokenPortal>` e `cliente-integrado: megasoft-portal-da-transparencia` | folha por `ano` + `mes` ("09"); empenhos por `dataInicial`/`dataFinal`; `cnpjDoFornecedor` filtra | `nome=` e `filtro=` não filtram a folha; `cpfOuCnpjDoFornecedor` é ignorado |
| Megasoft embutida (menu `mg*`) | API NucleoGov, `acao = megasoft/servidores` ou `megasoft/empenhos`, com `pagina` (começa em 1), `tamanhoDaPagina`, `ordenacao: {}` | folha por `ano` + `mes` ("12") + `mesInteger`; empenhos por `dataInicial`/`dataFinal` | o `limit` do envelope é ignorado; folha sem mês não é aceita pelo projeto |
| Centi (menu `cntdespesas`) | `POST /api/centi`, formulário simples, `acao=empenhos`, `id_orgao=0`, `data_inicio`/`data_fim` | período; lista inteira, sem páginas, com `TotalRegistros` | `cpf_cnpj` devolve lista vazia; `relatorioEmpenhos` só traz três somas |

Os módulos novos (04/11/2026):

| Sistema e módulo | Pedido | Funciona | Ignorado ou armadilha |
|---|---|---|---|
| Megasoft própria, receitas | `receitas-e-despesas/receita/receitas-pelo-tipo-de-natureza-detalhada/paginado`, `ano` + `mes` ("09") | mês respeitado; todas as entidades juntas | `receita/paginado` ignora o período: nunca usado |
| Megasoft própria, diárias | `orgaos-e-servidores/diaria/paginado`, `data=1`, datas dd/mm/aaaa | período respeitado (394 de 394 no 1º tri/2025) | um só valor por viagem (parece o total); sem órgão |
| Megasoft própria, contratos e licitações | POST; contratos com `ano`; licitações com `tipoDeConsultaDeModalidade` 1/2 e `dataDePublicacaoInicial/Final` | ano conferido em cada registro | sem `tipoDeConsultaDeModalidade` vem tudo; GET dá 405 |
| Megasoft própria, detalhe do servidor | `orgaos-e-servidores/servidor/detalhe` | decreto, vínculo, licenças, movimentos | listas de 5 em 5 (`tamanhoDaPagina` ignorado); 406 para matrícula inexistente |
| Megasoft embutida, receitas | `acao = megasoft/receitas`, `ano`, `mes` ("09") | mês respeitado; 9 órgãos juntos | a mesma receita uma vez por fonte de recurso |
| Megasoft embutida, diárias | `acao = sgdiarias/listar`, `datamin`/`datamax`, `txtbusca` | período e `txtbusca` respeitados; página pelo `limit` | `quantidade` absurda em 3 linhas; algumas câmaras anunciam `mgdiarias`, não medido (recusado se a API NucleoGov não servir as diárias) |
| Megasoft embutida, contratos | `acao = contratos_mg/listar`, `ano`, `objeto` | `ano` e `objeto` | `txtbusca` zera; sem `ano`, todos os anos; `orgao` só código |
| Megasoft embutida, licitações | `acao = licitacoes_mg/listarCidadao`, `ano`, `dispensas`, `descricao` | `ano` (da licitação) | período por data: `error` com total 0 (o cliente trata como recusa) |
| Centi, receitas (menu `cntreceitas`) | `POST /api/centi`, `acao=receitas`, `orgao=<id>` de `sgcenti/listarOrgaos` | um órgão por resposta; mês respeitado | sem a Câmara; analíticas e sintéticas juntas (`TipoConta`); vazio passageiro |

- **Senha pública da Megasoft própria.** `GET {portal}/api/configuracao/carregamento-inicial` devolve o
  `tokenPortal`, sem login: é o que o navegador de qualquer visitante faz ao abrir o portal. O JWT vence em
  cerca de 24 h; vencida dá 401 e ilegível dá **500 "Token inválido"**.
- **A fronteira de página perde registros nas duas Megasoft.** A listagem de empenhos ordena só por data e, entre
  uma página e a seguinte, repete uns e pula outros (fevereiro/2025 em páginas de 100: 236 perdidos em Corumbaíba,
  33 em Aruanã). Páginas de 5.000 não perdem. O projeto pede páginas grandes, tira repetidos pelo `codigo`
  (empenho) e pela `chave` (folha) e confere com o `total`.
- **O 13º não está na listagem da folha Megasoft,** nem somado em dezembro (mediana da razão 12/11 dos proventos
  por matrícula: 1,00; `mes="13"` responde 0). A rescisão não vem separada, e a listagem não traz rubricas.
- **Totais da Megasoft:** `valorTotalDo... = valorDo... − anulação`, conferido em todos os empenhos medidos.
- **Período respeitado** nos três sistemas (nenhuma data fora em trimestres e meses inteiros).
- **Câmara e fundos junto com a Prefeitura.** A Centi com `id_orgao=0` traz todas as entidades (Posse, 01/2025:
  Fundo de Saúde, Poder Executivo, Fundeb, FMAS, Poder Legislativo, FPPS); os empenhos Megasoft de Aruanã trazem 9
  entidades. O projeto mantém tudo e leva o campo `orgao` em cada despesa.
- **Centi: vazio espúrio.** Uma janela com empenhos voltou `[]` em 0,4 s e, repetida, respondeu. O projeto repete
  a lista vazia duas vezes antes de aceitá-la.
- **Tempo:** folha Megasoft de um mês numa página, 1,6 a 3,2 s; empenhos de um trimestre, 0,4 a 3,7 s; Centi, um
  mês em 2,2 a 2,7 s.
