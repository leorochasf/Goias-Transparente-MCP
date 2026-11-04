# Glossário

**Linha da folha**:
Um pagamento a uma matrícula, num mês, de um tipo de pagamento. Quem recebe salário e 13º no mesmo mês tem duas linhas (no NucleoGov; a listagem da Megasoft não traz o 13º).
_Evitar_: registro, servidor (quando se quer dizer a linha)

**Tipo de pagamento**:
A natureza da linha da folha: Folha Mensal, 13º ou Rescisão (campo `tipo_folha` do portal).
_Evitar_: tipo de folha

**Rubrica**:
Cada provento ou desconto que compõe uma linha da folha.
_Evitar_: evento

**Leitura do mês**:
A folha inteira de um mês, lida do portal página por página e guardada na memória do servidor MCP enquanto ele estiver aberto.
_Evitar_: cache, download

**Resumo da folha**:
Contagens e somas de linhas da folha por agrupamento (cargo, lotação ou vínculo), separadas por tipo de pagamento e sem nomes.
_Evitar_: relatório, estatística

**Órgão**:
A prefeitura ou a câmara de um município, cada um com seu portal da transparência. Nas despesas da Megasoft e da Centi, o campo `orgao` diz de quem é cada empenho: Prefeitura, Câmara ou fundo, que vêm juntos no mesmo portal.
_Evitar_: entidade, ente

**Fonte**:
O sistema de onde veio um registro de folha ou de despesas: NucleoGov, Megasoft (embutida no NucleoGov ou de domínio próprio) ou Centi.
_Evitar_: origem, plataforma (quando se quer dizer a fonte do registro)

**Catálogo de portais**:
A lista dos órgãos de Goiás, cada um com o endereço do portal, a plataforma e a situação da conferência.
_Evitar_: registro, lista de portais

**Sondagem**:
Uma visita à página inicial de um endereço para dizer qual plataforma ele usa.
_Evitar_: varredura, crawl

**Conferência**:
A medição ao vivo de um portal, com data, que diz quais filtros ele respeita.
_Evitar_: validação, teste
