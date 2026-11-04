# mcp-transparencia-municipal

- Preparar: `pip install -e ".[dev,mcp]"`. Conferir: `ruff check .` e `pytest` (offline).
- Antes de mexer numa consulta do `cliente.py`, leia `docs/portal-nucleogov.md`: o portal ignora
  filtro desconhecido em silêncio, e os testes offline não percebem.
- Depois de mudar uma consulta e antes de cada versão, rode `TRANSPARENCIA_AO_VIVO=1 pytest -m ao_vivo`
  (portal real, 7 consultas com pausa). Nomes de servidores da folha ficam fora da tela e dos arquivos.
