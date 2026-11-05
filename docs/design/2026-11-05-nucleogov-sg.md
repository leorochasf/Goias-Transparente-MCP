# Sistema de gestão (SG) no NucleoGov e o portal certo no catálogo (05/11/2026)

## Problema

A conferência geral de Goiás (04 e 05/11/2026) achou duas classes de "zero silencioso" e endereço errado:

1. **Portais NucleoGov com o sistema de gestão integrado (SG).** Em 24 prefeituras (Anápolis, Caldas Novas, Formosa,
   Goianésia, Valparaíso...) a folha, as despesas e as receitas voltavam vazias e só a legislação respondia. O menu
   desses portais aponta `sgservidores`, `sgdespesas`, `sgreceitas`, `sgcontratos` e `sglicitacoes`; a API NucleoGov
   comum (`servidores_frl`, `despesas_frl`...) responde zero, sem erro. Anápolis, 06/2025: 7.604 servidores e 4.698
   movimentos de despesa que a ferramenta dizia não existir.
2. **32 endereços do catálogo que não respondem.** Três causas:
   - entre o site institucional e o portal, ambos com a marca NucleoGov, vencia o site pela ordem alfabética
     (Abadia de Goiás, Abadiânia);
   - a origem (Radar da Transparência) só trouxe o site institucional, feito pela NucleoGov, e não o portal
     `acessoainformacao.` + o mesmo endereço (Cumari, Inhumas, Nova Crixás, Piracanjuba...);
   - o resto: portal `acessoainformacao.*` que recusa ou não conecta, e Goiânia (o catálogo aponta o site da Saúde).

## Descoberta (Anápolis, 05/11/2026; cerca de 40 consultas, pausa de 1,5 s, identificação de navegador)

- A página do módulo carrega o controlador `cidadao/controller/<area>/sg<modulo>` do NucleoGov
  (`static.nucleogov.com.br`), que pede `Req.setRequest('sg<modulo>', 'listar', filtro)`: a ação é
  `sg<modulo>/listar`, no envelope `multi_request` de sempre, paginada pelo `limit` do envelope.
- **Folha** (`sgservidores/listar`): `ano` + `mes` respeitados (06/2025: 7.604; 03/2025: 7.033). Páginas de 1.000
  lidas sem repetir nem perder (7.604 chaves distintas em 8 páginas). `orgao` filtra (16: 1.933, todas do Fundo
  Municipal de Saúde); sem filtro vêm todos os órgãos, e o principal vem com `orgao` vazio. Tipo "Folha Normal".
  Campos: `nome`, `cpf_mascarado`, `matricula`, `cargo`, `funcao`, `lotacao`, `local_trabalho`, `vinculo`,
  `data_admissao` (aaaa-mm-dd), `proventos`/`descontos`/`liquido` (ponto decimal), `tipo`, `ano`, `mes`.
- **Despesas** (`sgdespesas/listar`): uma linha por **movimento** (`movimento` Empenho, Liquidação, Pagamento; `tipo`
  0, 1, 2). 06/2025: 4.698 movimentos de 2.001 empenhos. `tipo` 0 traz só os empenhos (1.419). `ano` +
  `datamin`/`datamax` (aaaa-mm-dd) recortam pela data (776 movimentos de 01 a 10/06); `periodo_inicial`/
  `periodo_final` dão zero. **Só com `ano`, o portal devolve o mês mais recente** (11/2026). `cpf_cnpj` filtra (45 de
  45). Valores no formato brasileiro; os da linha são os do momento do movimento (o empenho traz liquidado e pago
  zerados, e o pagamento de julho traz o acumulado). O CNPJ vem formatado; **o CPF de pessoa física vem completo**.
- **Receitas** (`sgreceitas/listar`): `ano` + `mes`; todos os órgãos juntos (16 em 06/2025); `orgao` filtra. Conta
  sem movimento no mês vem com `mes` nulo e arrecadação zero (83 de 393). Campos: `codigo`, `descricao`,
  `orgao_nome`, `valor_orcado`, `arrecadacao` (mês), `valor_arrecado_periodo` (acumulado).

## Decisões

- Encaixe novo `sg.py`, no mesmo contrato dos outros (Megasoft embutida, Centi). O reconhecimento da página inicial
  marca o sufixo `sg` nos módulos com menu `sg<modulo>`, sem trocar o sufixo que outro menu já deu.
- **Folha:** nomes de campo do NucleoGov; "Folha Normal" sai como "Mensal (Folha Normal)" para o resumo contar;
  linha de outro mês é erro; a busca por nome é feita aqui, sobre o mês inteiro. Páginas de 1.000.
- **Despesas:** a lista traz os **empenhos emitidos no período** (`tipo` 0), mês a mês (`ano` + `datamin`/`datamax`),
  com o valor empenhado. Liquidado e pago ficam vazios, com ressalva: somar movimentos parciais daria número
  enganoso. Toda linha é conferida (empenho, data no período, CNPJ quando pedido); fora disso, erro.
- **Receitas:** nomes comuns de receitas; ressalva de que os órgãos vêm juntos; linha de outro mês é erro.
- **Contratos e licitações do SG:** não medidos; recusados com aviso (antes: zero calado).
- `sgdiarias` continua no encaixe em que já estava.
- **Catálogo:** entre endereços confirmados, vence o `acessoainformacao.`; site institucional com a marca NucleoGov
  gera o candidato `acessoainformacao.` + o mesmo endereço, sondado no passo `sondar`.
- Resposta da API fora do envelope `{dados, total}` vira `ErroPortal` ("resposta inesperada"), não `AttributeError`.

## Fora

- Contratos, licitações, detalhe do servidor e rubricas no SG.
- Liquidações e pagamentos por empenho no SG (exigiria ler os movimentos depois do período).
- Goiânia: a prefeitura não está em portal NucleoGov; o catálogo continua sem portal certo para ela.

## Segunda parte (05/11/2026): contratos, licitações, liquidado e pago, endereços conferidos

- **Medido em Anápolis:** `sgcontratos/listar` (ano 360 em 2025, 597 em 2024; `tipo` "Contrato" 138, "Aditivo" 87;
  `objeto` filtra); `sglicitacoes/listar` (ano 80 em 2025; `onlyDispensas` 129; `descricao` 44 de 44);
  `sgdespesas/relatorioTotais` (somas do período, aceita `cpf_cnpj`); movimentos de um fornecedor de 2025 até hoje
  numa leitura só = soma das leituras de 2025 e 2026 (1.962 + 1.341 = 3.303). O número do empenho recomeça a cada
  ano: os movimentos são agrupados pela `chave_empenho`.
- **Decisões (aprovadas pelo usuário):** contratos = todos os tipos menos aditivo (lidos inteiros e filtrados aqui);
  aditivos pelo filtro do portal; somas do período em toda consulta de despesas sem busca por nome; liquidado e pago
  até hoje só na busca por CNPJ (sem CNPJ seriam ~1.400 consultas num mês); movimento que não é empenho, liquidação
  nem pagamento deixa o empenho sem liquidado e pago, com ressalva.
- **Endereços conferidos à mão** no script do catálogo (`ENDERECOS_CONFERIDOS`): 7 câmaras migradas para `.go.leg.br`
  (Ceres, Formoso, Leopoldo de Bulhões, Petrolina, Piracanjuba, Taquaral, Vila Boa), a prefeitura de Morro Agudo
  (`acessoainformacao.morroagudo.go.gov.br`), a Câmara de Goiânia (`camaragoiania.nucleogov.com.br`) e a Prefeitura
  de Goiânia sem portal lido (sistema próprio `transweb`, fora). Câmara de Goianésia e Prefeitura de Terezópolis:
  nenhum endereço respondeu.
