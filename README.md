# Goias-Transparente-MCP

Pergunte em português quanto sua prefeitura pagou, a quem e por quê.

Este projeto liga um assistente de IA (Claude, ChatGPT, Cursor e outros que falam **MCP**) ao
**Portal da Transparência do seu município**. Também funciona como programa de linha de comando,
para quem quer só baixar a planilha.

Cobre a plataforma **NucleoGov**, usada pela maioria dos municípios de Goiás e por municípios de
outros estados. São os portais no padrão `acessoainformacao.<municipio>.go.gov.br`. Também lê a **Megasoft**
(embutida no NucleoGov ou no domínio próprio `<municipio>.megasofttransparencia.com.br`), a contabilidade **Centi**
(veja **Megasoft e Centi**) e as câmaras no sistema **Ortrel** (veja **Ortrel**). Para Goiás há um catálogo dos
portais de prefeituras e câmaras (veja **Municípios de Goiás**) e os processos e acórdãos do Tribunal de Contas dos
Municípios (veja **TCM-GO**).

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
| **Licitações e dispensas** | *Liste as dispensas de licitação de 2025.* (o ano só na Megasoft e no Ortrel) |
| **Receitas** | *Quanto o município arrecadou de IPTU em março de 2025?* (um mês por vez) |
| **Diárias de viagem** | *Quantas diárias o motorista da Saúde recebeu no 1º trimestre de 2025, e para onde foi?* |
| **Detalhe do servidor** | *Por qual decreto e desde quando essa matrícula ocupa o cargo?* (Megasoft de domínio próprio) |
| **Legislação** | *Qual decreto criou o cargo de assessor especial?* |
| **Processos no TCM-GO** | *Que processos de contas a Prefeitura de Posse tem no TCM, e em que fase estão?* |
| **Processo pelo número** | *Em que pé está o processo 00131/19 do TCM?* |
| **Acórdãos do TCM-GO** | *Há acórdão com imputação de débito para Trindade desde 2020?* |
| **Acórdão pelo número** | *O que decidiu o acórdão 07286/24?* (número do processo ou do acórdão) |
| **Texto de um acórdão** | *O que esse acórdão decidiu? Cite o trecho.* (lê o PDF original) |

## Instalação

```bash
git clone https://github.com/leorochasf/Goias-Transparente-MCP
cd Goias-Transparente-MCP
pip install -e .
```

A instalação cria dois comandos: `goias-transparente`, a linha de comando, e `goias-transparente-mcp`, o servidor
para o assistente de IA. Eles fazem o mesmo que `python -m transparencia_municipal.cli` e
`python -m transparencia_municipal.servidor_mcp`, usados nos exemplos abaixo.

Python 3.10 ou mais novo.

### Como assistente de IA (MCP)

No arquivo de configuração do seu cliente MCP:

```json
{
  "mcpServers": {
    "goias-transparente": {
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

python -m transparencia_municipal.cli --portal https://acessoainformacao.posse.go.gov.br \
    --navegador --csv diarias.csv diarias --de 2025-01-01 --ate 2025-03-31 --busca goiania

python -m transparencia_municipal.cli --portal https://corumbaiba.megasofttransparencia.com.br \
    licitacoes --dispensas --ano 2025

python -m transparencia_municipal.cli --portal https://corumbaiba.megasofttransparencia.com.br \
    detalhe-servidor --matricula 12345 --ano 2025 --mes 9

python -m transparencia_municipal.cli --portal https://acessoainformacao.posse.go.gov.br \
    --navegador receitas --ano 2025 --mes 9
```

Consultas: `folha`, `despesas`, `contratos`, `licitacoes`, `receitas`, `diarias`, `detalhe-servidor`, `legislacao`
e as do TCM-GO (`tcm-processos`, `tcm-acordaos`, `tcm-acordao`); `... <consulta> --help` mostra as opções de cada
uma. Os avisos da resposta (ressalvas do portal, leitura incompleta) saem em linhas `AVISO:`; nas receitas da Centi,
as somas por órgão saem logo abaixo do total.

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

Muitos portais de Goiás mostram módulos de outros sistemas. O projeto escolhe o caminho sozinho, pelo endereço e
pelo menu do portal, e entrega os registros no mesmo formato. Cada registro dos sistemas traduzidos traz o campo
`fonte`, que diz de onde veio: `NucleoGov`, `NucleoGov (sistema de gestão)`, `Megasoft`, `Centi` ou `Ortrel`.

| Sistema | Onde aparece | Folha | Despesas | Receitas | Diárias | Contratos | Licitações | Detalhe do servidor |
|---|---|---|---|---|---|---|---|---|
| Megasoft embutida | menus `mg*`, `*_mg`, `sgdiarias` de um portal NucleoGov | sim | sim | sim | sim (`sgdiarias`; `mgdiarias` é recusado) | sim | sim, por ano | não tem |
| Megasoft de domínio próprio | `<municipio>.megasofttransparencia.com.br` | sim | sim | sim | sim | sim | sim | sim |
| Centi | menus `cntdespesas`, `cntreceitas` de um portal NucleoGov | não tem | sim | sim, por órgão | não tem | não tem | não tem | não tem |
| Sistema de gestão (SG) do NucleoGov | menus `sgservidores`, `sgdespesas`, `sgreceitas` de um portal NucleoGov | sim | sim, os empenhos (sem liquidado e pago) | sim, todos os órgãos juntos | `sgdiarias`, como na Megasoft embutida | recusado (não medido) | recusado (não medido) | não tem |

O que o sistema não tem ou o projeto não lê (legislação da Megasoft, aditivos fora do NucleoGov) é **recusado com
aviso**, em vez de responder "zero". Contratos e licitações saem com os **nomes de campo do NucleoGov** em todo
sistema: `numero`, `ano`, `orgao`/`orgao_nome`, `objeto`, `fornecedor_nome`, `fornecedor_cpfcnpj`, `valor`,
`data_firmatura`, `fim_vigencia`, `fiscal_contrato` nos contratos; `numero`, `label` (número/ano), `modalidade`,
`situacao`, `orgao`, `descricao`, `data_publicacao` nas licitações. As diárias e as receitas traduzidas têm nomes
comuns próprios (`favorecido`, `destino`, `motivo`, `data_saida`, `quantidade`, `valor`; `codigo`, `receita`,
`fonte_recurso`, `valor_arrecadado_mes`).

- **Receitas.** Megasoft (as duas): um mês, com todas as entidades juntas (Câmara, Prefeitura, fundos, RPPS); cada
  linha é conferida no mês pedido, e linha de outro mês é erro, não mistura. Centi: um órgão por vez (o projeto lê
  todos e junta); vêm as contas **analíticas e as sintéticas**, marcadas no campo `analitica` (só as `true` podem
  ser somadas; somar as sintéticas conta em dobro). A resposta traz `somas_por_orgao`, a soma das analíticas de cada
  órgão no mês inteiro. A **Câmara não vem** nas receitas da Centi (Posse, 09/2025). No acumulado do ano, a soma das
  analíticas do Poder Executivo de Posse ficou R$ 334.029,19 acima da conta do topo; a resposta avisa, sem explicar.
- **Diárias.** Cada sistema publica campos diferentes; o projeto os traduz e diz nas `ressalvas` o que falta.
  Valor vazio quer dizer que o portal não publicou o valor, **não que foi zero**. Medido no 1º trimestre de 2025:
  Megasoft própria (Corumbaíba) com um só valor por viagem, que parece o total e não o unitário; Megasoft embutida
  (Aruanã) com o total da linha e 3 linhas com quantidade absurda (657437); a busca (`--busca`) é feita pelo projeto
  sobre o período inteiro, exceto na embutida, cujo filtro do portal funciona.
- **Contratos.** Ano conferido em cada contrato. Megasoft embutida: a busca procura **só no objeto** (a busca livre
  do portal zera a resposta) e `orgao` é o código do órgão. Aditivos: recusados na Megasoft (aparecem só dentro do
  contrato).
- **Licitações.** Megasoft própria: `--ano` é o ano da data de publicação. Megasoft embutida: só filtra **por ano**,
  e é o ano da licitação (o período por data dá erro no portal); os chamamentos públicos vêm nas licitações e nas
  dispensas.
- **Detalhe do servidor** (`detalhe_servidor`, `detalhe-servidor`): na Megasoft de domínio próprio, que não
  publica as rubricas da folha, é o que há no lugar: cargo, vínculo, **decreto de nomeação e a data dele**, data
  de admissão, licenças, férias e os movimentos do mês. As listas internas vêm de 5 em 5 (a resposta avisa quando
  vem cortada), e a matrícula vem da folha.

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
  previdência). A despesa Megasoft faz o mesmo, e as receitas e os contratos também. Cada registro traz o campo
  `orgao` (nos contratos, `orgao_nome`), e o assistente avisa quando a resposta mistura órgãos: some só os do órgão
  que interessa.
- **Busca por CNPJ ou nome do fornecedor** é conferida pelo projeto, empenho por empenho. O filtro de CNPJ da
  Centi não funciona; o da Megasoft de domínio próprio funciona e, mesmo assim, cada empenho é conferido; o da
  Megasoft embutida não foi medido. Por isso a busca lê o período inteiro (na Megasoft embutida, mês a mês) e pode
  demorar mais.
- **Leitura que não fecha não vira "zero".** A Megasoft pula registros quando a leitura vai em páginas pequenas; o
  projeto pede páginas grandes, tira os repetidos e confere o total. Se ainda faltar registro, a leitura sai como
  incompleta.

## Diárias nos portais NucleoGov

`consultar_diarias` (`diarias` na linha de comando) lê as diárias de todo portal NucleoGov, pela data de saída. Os
campos mudam de portal para portal e são traduzidos para os nomes comuns. Medido no 1º trimestre de 2025:

- **Posse:** 64 diárias, todas do órgão principal (Poder Executivo). Sem o filtro de órgão, alguns portais trazem só
  o órgão principal; a resposta avisa que as da Câmara e dos fundos podem não estar ali.
- **Senador Canedo:** 115 diárias de 6 órgãos, **sem valor, quantidade, cargo nem destino** publicados; a resposta
  diz isso.
- **A busca livre do portal não funciona nas diárias** (respondeu zero com palavras presentes): o projeto lê o
  período inteiro e procura no nome, cargo, destino e motivo.
- Saída fora do período pedido é erro, nunca resultado.

## Ortrel

Quatro câmaras de Goiás usam o sistema **Ortrel** (Cidade Ocidental, Luziânia, São João d'Aliança e Valparaíso de
Goiás, em `transparencia.<câmara>`). O projeto o reconhece pelo catálogo ou pela página inicial e lê:

| Módulo | Como vem | O que saber |
|---|---|---|
| Folha | a série inteira numa chamada (6.046 linhas em Cidade Ocidental); o projeto recorta o mês | **com rubricas** (proventos e descontos), **decreto e data do decreto** em cada linha; o 13º, as férias e a rescisão vêm como rubricas da linha do mês, não em linha própria; a soma das rubricas nem sempre bate com o bruto (vale o bruto) |
| Despesas | por mês, em páginas | **o CNPJ de empresa vem completo**, e a busca por CNPJ funciona; só o CPF de pessoa física vem mascarado |
| Contratos | todos de uma vez; o projeto filtra ano e busca | sem lista de aditivos: cada contrato traz `valor_aditado` e os anexos |
| Licitações | todas de uma vez; dispensas e inexigibilidades separadas pela modalidade | sem data de publicação, o ano é o do protocolo |
| Diárias | a série inteira; o projeto recorta pela saída | sem órgão nem empenho; há saídas improváveis (1899) |
| Legislação | só **leis** (`--tipo LEI`) | o mesmo número se repete em anos diferentes porque a numeração recomeçou: são leis diferentes |

Receitas e detalhe do servidor não existem no Ortrel e são recusados. O sistema roda em modo de desenvolvimento e
entrega a chave pública da API na própria página; o projeto a lê como o navegador lê, sem login.

## Municípios de Goiás

O pacote traz um **catálogo de portais** com os 461 órgãos (prefeituras e câmaras) de Goiás que aparecem nos
dados abertos do Radar da Transparência Pública (Atricon, ciclo 2025,
[radardatransparencia.atricon.org.br](https://radardatransparencia.atricon.org.br/downloads.html)).
Para cada órgão o catálogo registra o portal e a plataforma. A plataforma foi confirmada por uma visita à
página inicial em 04/11/2026. No assistente, `encontrar_portal("Posse", "camara")` devolve o endereço.

| Plataforma no catálogo | Órgãos |
|---|---|
| NucleoGov | 186 |
| NucleoGov com folha Megasoft (Megasoft embutida) | 221 |
| Megasoft de domínio próprio | 30 |
| Ortrel | 4 |
| Sem portal reconhecido | 20 |

Toda resposta diz a **situação do portal**:

- **conferido:** os filtros foram medidos ao vivo, com a data e o que falhou;
- **não conferido:** confira os números no próprio portal;
- **fora do catálogo.**

Em 04 e 05/11/2026 foram conferidos ao vivo **todos os 441 órgãos com plataforma reconhecida**. A conferência
passa pelos mesmos caminhos das consultas (NucleoGov, sistema de gestão do NucleoGov, Megasoft embutida e própria,
Centi, Ortrel) e mede folha, despesas, receitas, diárias, contratos, licitações e legislação. Folha do mês respeitada
em 408 órgãos; despesas do período em 413; busca por CNPJ em 407; legislação em 368; contratos por ano em 342;
receitas do mês em 236 (as câmaras quase não arrecadam); diárias em 173; licitações por ano em 164 (nos portais
NucleoGov o ano das licitações não é usado). 12 órgãos têm portal que não responde direito. O
resultado de cada órgão está no catálogo e o resumo em `docs/portal-nucleogov.md`.

O que vale saber antes de confiar num número:

- **Muitos portais NucleoGov puxam módulos de outros sistemas.** Despesas e receitas podem vir da
  contabilidade Centi, e folha, despesas, receitas, diárias, contratos e licitações podem vir da Megasoft embutida.
  Outros puxam folha, despesas e receitas do **sistema de gestão (SG)** do próprio NucleoGov (Anápolis, Caldas
  Novas, Formosa e cerca de 60 portais): a API comum responde "zero" neles. O projeto lê esses sistemas (veja
  **Megasoft e Centi**); o que não lê é **recusado com aviso**, em vez de responder "zero". Na amostra, as despesas só vieram pela API NucleoGov na Prefeitura de Alexânia.
- **Em várias prefeituras a folha sem filtro esconde órgãos** (fundos, autarquias). As listas e o resumo da
  folha buscam esses órgãos um a um. A busca rápida por nome avisa quando o portal faz isso.
- **Muitos portais só publicam a folha dos meses recentes.** Um mês antigo pode vir vazio.

## TCM-GO

O assistente também consulta o **Tribunal de Contas dos Municípios de Goiás**, em duas fontes públicas, sem login:
o **eSiproc** (processos eletrônicos) e o **TCMJuris** (acórdãos julgados desde 2020, com o PDF). O município é
indicado pelo nome comum ("Posse", "Nova Crixás"): o projeto usa o nome oficial de cada fonte, gravado no catálogo, e
**recusa com os nomes mais parecidos** quando o nome não casa, em vez de responder "zero processos".

| Ferramenta (MCP) | Comando | Exemplo de pergunta |
|---|---|---|
| `processos_tcm` | `tcm-processos` | *Quais processos de 2023 de Nova Crixás ainda não foram finalizados?* |
| `acordaos_tcm` | `tcm-acordaos` | *Há acórdão de Caldazinha sobre "tomada de contas especial"?* |
| `ler_acordao_tcm` | `tcm-acordao` | *Leia o acórdão e diga o que foi decidido.* |

```bash
python -m transparencia_municipal.cli --csv processos.csv tcm-processos --municipio "Nova Crixás" --ano 2023 --nao-finalizado

python -m transparencia_municipal.cli tcm-processos --numero 00131/19

python -m transparencia_municipal.cli --json acordaos.json tcm-acordaos --municipio Caldazinha --texto '"tomada de contas especial"'

python -m transparencia_municipal.cli tcm-acordaos --numero 07286/24

python -m transparencia_municipal.cli tcm-acordao DOCUMENT_ID_DO_ACORDAO
```

- `tcm-processos` filtra por `--tipo` (tipo de protocolo), `--ano` (competência), `--relator`, `--finalizado` ou
  `--nao-finalizado` e `--numero` (NNNNN/AA). Os `tcm-*` não usam `--portal`. No CSV, decisões e envolvidos saem em
  JSON dentro da célula.
- `tcm-acordaos` filtra por `--texto` (entre aspas para a expressão exata: sem aspas, as palavras são buscadas
  soltas; em 04/11/2026, "tomada de contas especial" deu 6.176 acórdãos sem aspas e 1.815 com aspas), `--assunto`, `--ano` (do julgamento) e `--relator`. O `document_id` de cada acórdão é o que o
  `tcm-acordao` lê.
- `tcm-acordaos --numero` (no assistente, `acordaos_tcm` com `numero`) aceita o número do **processo ou do
  acórdão**, `NNNNN/AA` ou `NNNNN` (zeros à esquerda opcionais). O filtro do TCM aceita partes do número, então o
  projeto confere número e ano de cada resultado; `casou_com` diz se casou com o processo, o acórdão ou os dois. Sem
  o ano, vêm todos os anos: `7286` deu 10 resultados em 7 anos (04/11/2026), e `aviso_numero` diz isso.
- Biblioteca: `from transparencia_municipal import ClienteTCM`, com `processos`, `acordaos` e `ler_acordao`, no
  formato `{"total", "registros"}` das outras consultas.

**Ler o PDF do acórdão** é opcional na instalação:

```bash
pip install -e ".[pdf]"
```

Sem ela, `ler_acordao_tcm` diz como instalar e devolve o link do PDF original.

**Os avisos que acompanham toda resposta:**

- **Ausência não é prova.** O índice de processos do TCM não é histórico: exercícios antigos, processos físicos e de
  cobrança podem faltar.
- **Os acórdãos começam em 2020.** Não achar um acórdão não prova que não houve julgamento antes.
- **A ementa é escrita por IA**, não pelo tribunal: vem no campo `ementa_ia`. Para citar, leia o PDF
  (`ler_acordao_tcm`).
- **Envolvidos** aparecem como o TCM os mostra, porque são dado público do processo: use para apuração, não para
  montar dossiê de pessoas.
- Quando o TCM informa "10 mil ou mais", a resposta diz que o total é um piso; quando a leitura para no teto de
  chamadas ou a fonte para de entregar antes do total, diz que veio incompleta. Resposta incompleta ou fora do ar
  do TCM é erro, nunca lista vazia.
- **Desconfiar do zero.** As duas fontes respondem "zero", sem aviso, a um nome de município que não conhecem. Diante
  de um zero, o projeto relê a lista oficial da fonte: se o nome mudou, repete com o nome novo; se o município saiu da
  lista, recusa.

**Limites do TCM-GO:**

- Só processos eletrônicos; as peças das decisões (os documentos) não são baixadas.
- Só acórdãos julgados, desde 2020. Filtros do TCMJuris como resultado e tipo de processo ainda não estão nas
  ferramentas.
- PDF digitalizado, sem texto, sai com aviso e o link.
- Uma consulta por vez, com pausa de 1 s e teto de 60 chamadas por consulta.

Em 04/11/2026 os nomes das 16 cidades da amostra (veja **Municípios de Goiás**) resolveram nas duas fontes, com os
processos e os acórdãos do município certo.

## Limites conhecidos

- **NucleoGov** inteiro. Da **Megasoft** e do **Ortrel**, tudo menos legislação da Megasoft, receitas do Ortrel e
  aditivos; da **Centi**, despesas e receitas (veja as seções acima). O que não é lido é recusado com aviso.
- **O ano das licitações** só filtra na Megasoft e no Ortrel; nos portais NucleoGov é recusado (o filtro não foi
  medido): use a busca.
- Folha da Megasoft **sem 13º e sem rubricas**; a rescisão não vem separada. No lugar das rubricas, o detalhe do
  servidor (só na Megasoft de domínio próprio).
- Despesas, receitas e contratos da Centi e da Megasoft **incluem Câmara e fundos**: confira o campo `orgao`.
- **Diárias:** valor vazio não é zero; cada portal publica campos diferentes (leia as `ressalvas`). Em alguns
  portais NucleoGov, sem o filtro de órgão, só vem o órgão principal.
- **Receitas da Centi:** some só as contas `analitica = true`; a Câmara não vem.
- Os campos variam de município para município: cada prefeitura preenche o portal como quer.
- Sem paginação infinita: use `--maximo` para pedir mais que os 200 registros padrão.
- A busca livre (`--busca`) é a mesma caixinha do portal. **Na folha ela procura só por nome**:
  para filtrar por cargo ou lotação, traga o mês inteiro e filtre a planilha depois.
  **Nas despesas, um CNPJ** (com ou sem pontuação) não vai para a caixinha, que não o encontra:
  no NucleoGov ele vai para o filtro de CNPJ do portal; na Megasoft e na Centi o projeto lê o período e
  separa os empenhos daquele fornecedor. Nos dois casos, só vêm os empenhos daquele CNPJ.

## Licença

MIT. Use, altere e redistribua. Sem garantia de qualquer espécie: confira os dados na fonte.
