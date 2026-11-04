# mcp-transparencia-municipal

- Preparar: `pip install -e ".[dev,mcp]"`. Conferir: `ruff check .` e `pytest` (offline).
- Antes de mexer numa consulta do `cliente.py`, leia `docs/portal-nucleogov.md`: o portal ignora
  filtro desconhecido em silêncio, e os testes offline não percebem.
- Depois de mudar uma consulta e antes de cada versão, rode `TRANSPARENCIA_AO_VIVO=1 pytest -m ao_vivo`
  (portal real, 7 consultas com pausa). Nomes de servidores da folha ficam fora da tela e dos arquivos.

## Agent skills

### Issue tracker

Specs e tickets em arquivos locais em `.scratch/<feature>/`, fora do git (privados). See `docs/agents/issue-tracker.md`.

### Triage labels

Os cinco papéis padrão, com os nomes padrão. See `docs/agents/triage-labels.md`.

### Domain docs

Contexto único: glossário em `CONTEXT.md` na raiz, ADRs em `docs/adr/`. See `docs/agents/domain.md`.
