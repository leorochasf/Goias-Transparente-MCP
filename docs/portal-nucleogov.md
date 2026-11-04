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
órgãos NucleoGov de 16 municípios. O resultado de cada portal fica no catálogo (`catalogo_go.json`).

- **Sufixo do módulo por portal.** A ação é `<modulo>_frl/listar` ou `<modulo>_cnt/listar`. **Com o sufixo errado o
  portal responde total 0, sem erro.** Chapadão do Céu: `servidores_frl` dá 0 e `servidores_cnt` dá 224. Um sufixo
  que não existe responde `[]`. O cliente aprende o sufixo na página inicial; quando não acha, tenta `frl` e depois `cnt`.
- **Módulos de outros sistemas.** Na página inicial, `mgservidores`, `mgdespesas` e `mgreceitas` indicam a Megasoft
  embutida; `cntdespesas` e `cntreceitas` indicam a contabilidade Centi. A API NucleoGov às vezes serve o módulo
  mesmo assim (Alexânia sim, Posse não), então uma consulta sem filtro decide. Se ela volta vazia, o cliente recusa
  (`ModuloNaoSuportado`). Na amostra:
  - despesas pela API NucleoGov só na Prefeitura de Alexânia;
  - folha recusada (Megasoft embutida) em 10 órgãos.
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
