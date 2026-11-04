# NucleoGov em outras cidades de Goiás

Aprovado em 04/11/2026. Termos em `CONTEXT.md`. É a primeira de três frentes: NucleoGov em outras cidades, depois Megasoft, depois Ortrel.

## Decisões

1. O projeto aproveita de medições anteriores do autor só o **conhecimento** sobre as APIs, nunca código.
2. **Catálogo de portais** de Goiás (prefeituras e câmaras), feito com os dados abertos do Radar da Transparência
   Pública (Atricon). A plataforma se reconhece pelo endereço; o que o endereço não revela, uma **sondagem** de
   Goiás resolve (uma visita à página inicial de cada endereço, com 1 s de pausa).
3. **Conferência** ao vivo da amostra pedida pelo usuário. São os órgãos NucleoGov de 16 municípios: Nova Crixás,
   Alto Paraíso de Goiás, Cristalina, São Miguel do Araguaia, Trindade, Aruanã, Posse, Alexânia, Vianópolis, Orizona,
   Cocalzinho de Goiás, Itapuranga, Goianápolis, Pirenópolis, Corumbaíba e Guapó.
4. Quando um portal se comporta diferente, a diferença fica registrada no catálogo e a ferramenta avisa. O código
   só é adaptado se a mesma diferença se repetir em vários portais.
5. Ferramenta `encontrar_portal(municipio, orgao)`. As outras ferramentas passam a avisar a situação da conferência
   e recusam com clareza os portais de outras plataformas.

## Fatos medidos (04/11/2026) que mudam o cliente

- **Sufixo do módulo por portal.** Senador Canedo usa `_frl`; Chapadão do Céu e a Câmara de Posse usam `_cnt`. O
  sufixo aparece na página inicial (`servidores_cnt`), mas nem todo módulo aparece lá. Por isso o cliente usa o
  sufixo da página e, sem ele, tenta `_frl` e depois `_cnt`.
- **Órgãos da folha.** Numa medição anterior, em Chapadão do Céu a folha sem filtro trazia só o órgão 1, e os fundos só
  apareciam com `orgao` explícito. Em Senador Canedo a folha sem filtro mistura os órgãos 001, 002, 004 e 005, e
  `orgao=1` devolve zero, porque o portal usa o código "001". A conferência passa a checar se a folha sem
  filtro cobre os órgãos.
- **O site oficial pode ser o próprio NucleoGov.** É o caso da Prefeitura de Nova Crixás, em `novacrixas.go.gov.br`.
  O padrão `acessoainformacao.*` não basta.
- Câmaras aparecem tanto em `acessoainformacao.<cidade>.go.leg.br` quanto em `acessoainformacao.camara<cidade>.go.gov.br`.
- Megasoft se reconhece pelo domínio `*.megasofttransparencia.com.br`. Ortrel tem `/src/main.jsx` na página inicial.
