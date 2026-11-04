# mcp-transparencia-municipal

Pergunte em português quanto sua prefeitura pagou, a quem e por quê.

Este projeto liga um assistente de IA (Claude, ChatGPT, Cursor e outros que falam **MCP**) ao
**Portal da Transparência do seu município**. Também funciona como programa de linha de comando,
para quem quer só baixar a planilha.

Cobre a plataforma **NucleoGov**, usada pela maioria dos municípios de Goiás e por municípios de
outros estados — os portais no padrão `acessoainformacao.<municipio>.go.gov.br`.

> Dado público, lido na hora, sem cadastro e sem senha (Lei 12.527/2011). Nada é armazenado.
> **Confira no portal antes de usar em peça, denúncia ou matéria:** o portal pode estar
> desatualizado, incompleto ou fora do ar, e isso não aparece no resultado.

## O que dá para perguntar

| Consulta | Exemplo de pergunta |
|---|---|
| **Folha de pagamento** | *Quanto ganhou o servidor Fulano de Tal em março de 2025?* (a busca é por nome) |
| **Despesas (empenhos)** | *Quanto o município pagou para o CNPJ 00.000.000/0001-00 no ano passado?* |
| **Contratos e aditivos** | *Quais contratos foram assinados em 2025 com a palavra "locação"?* |
| **Licitações e dispensas** | *Liste as dispensas de licitação do município.* |
| **Receitas** | *Quanto o município arrecadou de IPTU no primeiro trimestre?* |
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
    --navegador folha --ano 2025 --mes 3 --csv folha-marco.csv

python -m transparencia_municipal.cli --portal https://acessoainformacao.senadorcanedo.go.gov.br \
    --navegador despesas --de 2025-01-01 --ate 2025-12-31 --busca "23.910.014/0001-48" --csv empenhos.csv
```

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

## Legislação: o apelido do município

A consulta de leis e decretos usa um apelido interno do portal. Para descobrir o seu: abra
`{portal}/cidadao/legislacao/decretos_psc` no navegador, veja as chamadas de rede da página e leia
o campo `acao` — o apelido é o trecho depois de `atos_pf_` (ex.: `atos_pf_senador_canedo`).

## Limites conhecidos

- Só a plataforma **NucleoGov**. Megasoft e Ortrel, também comuns em Goiás, ficam para depois.
- Os campos variam de município para município: cada prefeitura preenche o portal como quer.
- Sem paginação infinita: use `--maximo` para pedir mais que os 200 registros padrão.
- A busca livre (`--busca`) é a mesma caixinha do portal. **Na folha ela procura só por nome**:
  para filtrar por cargo ou lotação, traga o mês inteiro e filtre a planilha depois.
  **Nas despesas, um CNPJ** (com ou sem pontuação) não vai para a caixinha, que não o encontra:
  vai para o filtro de CNPJ do portal e traz só os empenhos daquele fornecedor.

## Licença

MIT. Use, altere e redistribua. Sem garantia de qualquer espécie: confira os dados na fonte.
