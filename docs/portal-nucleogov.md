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
