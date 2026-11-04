# mcp-transparencia-municipal

Pergunte em português quanto sua prefeitura pagou, a quem e por quê.

Este projeto liga um assistente de IA (Claude, ChatGPT, Cursor e outros que falam **MCP**) ao
**Portal da Transparência do seu município**. Também funciona como programa de linha de comando,
para quem quer só baixar a planilha.

Cobre a plataforma **NucleoGov**, usada pela maioria dos municípios de Goiás e por municípios de
outros estados. São os portais no padrão `acessoainformacao.<municipio>.go.gov.br`. Folha e despesas
também saem da **Megasoft** (embutida no NucleoGov ou no domínio próprio `<municipio>.megasofttransparencia.com.br`)
e da contabilidade **Centi** (veja **Megasoft e Centi**). Para Goiás há um catálogo dos portais de prefeituras e
câmaras (veja **Municípios de Goiás**).

> Dado público, lido na hora, sem cadastro e sem senha (Lei 12.527/2011). Nada é armazenado.
> **Confira no portal antes de usar em peça, denúncia ou matéria:** o portal pode estar
> desatualizado, incompleto ou fora do ar, e isso não aparece no resultado.

## O que dá para perguntar

| Consulta | Exemplo de pergunta |
|---|---|
| **Folha de pagamento** | *Quanto ganhou o servidor Fulano de Tal em março de 2025, e de quê?* (a busca é por nome) |
| **Folha: listas** | *Quem são os comissionados da Secretaria de Saúde em março de 2025?* |
| **Folha: contagens e custos** | *Quantos comissionados há por secretaria, e quanto custam por mês?* |
| **Despesas (empenhos)** | *Quanto o município pagou para o CNPJ 00.000.000/0001-00 no ano passado?* |
| **Contratos e aditivos** | *Quais contratos foram assinados em 2025 com a palavra "locação"?* |
| **Licitações e dispensas** | *Liste as dispensas de licitação do município.* |
| **Receitas** | *Quanto o município arrecadou de IPTU em março de 2025?* (um mês por vez) |
| **Legislação** | *Qual decreto criou o cargo de assessor especial?* |

## Instalação

```bash
pip install -e .          # dentro da pasta do projeto
```

Python 3.10 ou mais novo.

### Como assistente de IA (MCP)

No arquivo de configuração do seu cliente MCP:

```json
{
  "mcpServers": {
    "transparencia-municipal": {
      "command": "python",
      "args": ["-m", "transparencia_municipal.servidor_mcp"],
      "env": {
        "TRANSPARENCIA_PORTAL": "https://acessoainformacao.senadorcanedo.go.gov.br",
        "TRANSPARENCIA_NAVEGADOR": "1"
      }
    }
  }
}
```

`TRANSPARENCIA_PORTAL` é o portal padrão; você pode apontar outro em cada pergunta.
Sobre o `TRANSPARENCIA_NAVEGADOR`, leia a seção **O 403** abaixo antes de ligar.

### Como linha de comando

```bash
python -m transparencia_municipal.cli --portal https://acessoainformacao.senadorcanedo.go.gov.br \
    --navegador --csv folha-marco.csv folha --ano 2025 --mes 3

python -m transparencia_municipal.cli --portal https://acessoainformacao.senadorcanedo.go.gov.br \
    --navegador --csv empenhos.csv despesas --de 2025-01-01 --ate 2025-12-31 --busca "23.910.014/0001-48"
```

As opções `--navegador`, `--csv`, `--json`, `--maximo` e `--pausa` valem para qualquer consulta e
vêm **antes** do nome da consulta (`folha`, `despesas`...).

### Como biblioteca

```python
from transparencia_municipal import Portal

portal = Portal("https://acessoainformacao.senadorcanedo.go.gov.br", navegador=True)
folha = portal.folha(2025, 3, maximo=1000)
print(folha["total"], "servidores na folha de março")

empenhos = portal.despesas("2025-01-01", "2025-12-31", busca="23.910.014/0001-48")
print(empenhos["total"], "empenhos para esse fornecedor")
```

## O 403

Os portais NucleoGov **recusam com HTTP 403 quem se identifica como programa**. O dado é público
por lei; o bloqueio é técnico, não jurídico — a mesma consulta funciona quando o pedido se
apresenta como navegador.

Este projeto **se identifica honestamente por padrão** e, ao levar 403, explica o que houve em vez
de contornar em silêncio. Quem quiser insistir usa `--navegador` (ou `navegador=True`, ou
`TRANSPARENCIA_NAVEGADOR=1`) e faz isso **conscientemente**: essa opção declara ao servidor um
navegador que não existe.

O caminho limpo, se você vai usar muito ou de forma institucional, é **pedir acesso formal ao
município pela Lei de Acesso à Informação** — inclusive a liberação do acesso automatizado. Órgão
público tem dever de transparência ativa, e o pedido costuma ser mais rápido que a discussão.

## Uso responsável

- **Uma consulta por vez, com pausa** (1 segundo por padrão). Não aumente o ritmo: portal de
  município roda em infraestrutura modesta e derrubá-lo prejudica o cidadão que precisa dele.
- **Não republique dado pessoal.** A folha traz nomes de servidores: publicidade da remuneração
  é uma coisa, montar dossiê de pessoa é outra.
- **Este projeto não contorna captcha, não usa certificado digital e não faz login.** Só lê o que
  o portal já mostra a qualquer visitante.

## Legislação

A consulta lê o módulo `atos` do portal e não precisa mais de apelido do município:

```bash
python -m transparencia_municipal.cli --portal https://acessoainformacao.senadorcanedo.go.gov.br \
    --navegador legislacao --tipo DECRETO --busca cargo
```

- `--tipo`: `DECRETO` (padrão), `PORTARIA` ou `RESOLUCAO` — ou o código numérico do portal
  (1, 2 e 3, respectivamente).
- `--busca` procura a palavra na ementa. `--ano` restringe o ano (em Senador Canedo, 04/11/2026:
  1.201 decretos de 2025, de 3.905 no total).

Por que mudou: em Senador Canedo (04/11/2026) o caminho antigo, `atos_pf_senador_canedo/listar`,
voltava **vazio** — inclusive na tela "Decretos" do próprio site —, enquanto o módulo `atos`
trazia 3.905 decretos e 1.051 portarias. Se em outro portal o resultado vier zerado, o caminho
antigo continua acessível pela biblioteca: `Portal.consultar("atos_pf_<apelido>/listar", {"tipo": "DECRETO"})`.

**Leis** ficam em outro módulo, `leis/listar`, e não entram nesta consulta; leia com
`Portal.consultar("leis/listar")`.

## Folha no assistente de IA

Um mês de folha tem milhares de linhas, e cada uma traz o detalhe das rubricas. Inteira, a folha não
cabe na memória de um assistente. Por isso o servidor MCP entrega a folha **leve** em três ferramentas:

- `consultar_folha`: busca pelo nome, rápida. Com até 10 linhas, traz as rubricas (proventos e descontos).
- `listar_folha`: filtra o mês por cargo, lotação, vínculo ou tipo de pagamento. Devolve até 300 linhas
  e sempre diz quantas casaram com o filtro.
- `resumir_folha`: por cargo, lotação ou vínculo, conta linhas e matrículas e soma bruto e líquido, sem nomes.

Listar e resumir leem o **mês inteiro** do portal, com pausa entre as páginas. Em Senador Canedo, isso dá
uns 9 minutos na primeira pergunta (medido em 04/11/2026). A leitura fica guardada **só na memória**, enquanto o servidor estiver
aberto, e as perguntas seguintes sobre o mesmo mês saem na hora. **13º e rescisão nunca são somados ao
salário do mês.** O resumo separa por tipo de pagamento. A linha de comando e a biblioteca continuam
devolvendo a folha completa. Na folha da Megasoft o 13º não aparece (veja **Megasoft e Centi**).

## Megasoft e Centi

Muitos portais de Goiás mostram folha e despesas de outros sistemas. O projeto escolhe o caminho sozinho, pelo
endereço e pelo menu do portal, e entrega os registros no mesmo formato. Cada registro de folha e de despesas traz
o campo `fonte`, que diz de onde veio: `NucleoGov`, `Megasoft` ou `Centi`.

| Sistema | Onde aparece | Folha | Despesas |
|---|---|---|---|
| Megasoft embutida | menu `mg*` de um portal NucleoGov | sim | sim |
| Megasoft de domínio próprio | `<municipio>.megasofttransparencia.com.br` | sim | sim |
| Centi | menu `cntdespesas` de um portal NucleoGov | não tem | sim |

Receitas, contratos, licitações, diárias e legislação desses sistemas **seguem recusados com aviso**, em vez de
responder "zero".

- **A senha pública da Megasoft de domínio próprio.** A API desse portal pede uma senha (um `tokenPortal`). Ela
  não exige cadastro nem login: o portal a entrega a qualquer visitante em
  `GET <portal>/api/configuracao/carregamento-inicial`, que é a primeira coisa que o navegador faz ao abrir o site.
  O projeto faz o mesmo, **identificando-se honestamente** como ferramenta (o portal aceita), guarda a senha só na
  memória enquanto o programa roda e pede outra quando ela vence (cerca de 24 h).
- **O 13º fica fora da folha Megasoft.** A listagem da Megasoft não traz o 13º, nem separado nem somado ao
  salário de dezembro (medido em Aruanã, 11 e 12/2025), e não separa a rescisão. Cada linha sai com o tipo de
  pagamento "Mensal (a listagem da Megasoft não traz 13º; rescisão não vem separada)". A listagem também não traz
  rubricas: só bruto, descontos e líquido.
- **A Centi traz a Câmara e os fundos junto com a Prefeitura.** A consulta de despesas da Centi devolve todas as
  entidades do município (Poder Executivo, Poder Legislativo, fundos de saúde, educação, assistência e
  previdência). A despesa Megasoft faz o mesmo. Cada empenho traz o campo `orgao`, e o assistente avisa quando a
  resposta mistura órgãos: some só os do órgão que interessa.
- **Busca por CNPJ ou nome do fornecedor** é conferida pelo projeto, empenho por empenho: o filtro da Centi não
  funciona, e o da Megasoft embutida não foi medido. Por isso a busca lê o período inteiro, e pode demorar mais.
- **Leitura que não fecha não vira "zero".** A Megasoft pula registros quando a leitura vai em páginas pequenas; o
  projeto pede páginas grandes, tira os repetidos e confere o total. Se ainda faltar registro, a leitura sai como
  incompleta.

## Municípios de Goiás

O pacote traz um **catálogo de portais** com os 461 órgãos (prefeituras e câmaras) de Goiás que aparecem nos
dados abertos do Radar da Transparência Pública (Atricon, ciclo 2025,
[radardatransparencia.atricon.org.br](https://radardatransparencia.atricon.org.br/downloads.html)).
Para cada órgão o catálogo registra o portal e a plataforma. A plataforma foi confirmada por uma visita à
página inicial em 04/11/2026. No assistente, `encontrar_portal("Posse", "camara")` devolve o endereço.

Toda resposta diz a **situação do portal**:

- **conferido:** os filtros foram medidos ao vivo, com a data e o que falhou;
- **não conferido:** confira os números no próprio portal;
- **fora do catálogo.**

Em 04/11/2026 foram conferidos os órgãos de 16 municípios: Nova Crixás, Alto Paraíso de Goiás, Cristalina,
São Miguel do Araguaia, Trindade, Aruanã, Posse, Alexânia, Vianópolis, Orizona, Cocalzinho de Goiás, Itapuranga,
Goianápolis, Pirenópolis, Corumbaíba e Guapó. O resultado está em `docs/portal-nucleogov.md`.

O que vale saber antes de confiar num número:

- **Muitos portais NucleoGov puxam módulos de outros sistemas.** Despesas e receitas podem vir da
  contabilidade Centi, e folha, despesas e receitas podem vir da Megasoft embutida. Folha e despesas desses
  sistemas são lidas (veja **Megasoft e Centi**); os outros módulos são **recusados com aviso**, em vez de
  responder "zero". Na amostra, as despesas só vieram pela API NucleoGov na Prefeitura de Alexânia.
- **Em várias prefeituras a folha sem filtro esconde órgãos** (fundos, autarquias). As listas e o resumo da
  folha buscam esses órgãos um a um. A busca rápida por nome avisa quando o portal faz isso.
- **Muitos portais só publicam a folha dos meses recentes.** Um mês antigo pode vir vazio.

## Limites conhecidos

- **NucleoGov** inteiro. Da **Megasoft** (embutida e de domínio próprio) e da **Centi**, só folha e despesas;
  receitas, contratos, licitações e legislação delas são recusados com aviso. **Ortrel** (4 órgãos no catálogo)
  fica para depois e é recusado.
- Folha da Megasoft **sem 13º e sem rubricas**; a rescisão não vem separada.
- Despesas da Centi e da Megasoft **incluem Câmara e fundos**: confira o campo `orgao`.
- Os campos variam de município para município: cada prefeitura preenche o portal como quer.
- Sem paginação infinita: use `--maximo` para pedir mais que os 200 registros padrão.
- A busca livre (`--busca`) é a mesma caixinha do portal. **Na folha ela procura só por nome**:
  para filtrar por cargo ou lotação, traga o mês inteiro e filtre a planilha depois.
  **Nas despesas, um CNPJ** (com ou sem pontuação) não vai para a caixinha, que não o encontra:
  vai para o filtro de CNPJ do portal e traz só os empenhos daquele fornecedor.

## Licença

MIT. Use, altere e redistribua. Sem garantia de qualquer espécie: confira os dados na fonte.
