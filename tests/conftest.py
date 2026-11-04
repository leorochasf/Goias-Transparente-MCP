import pytest

from transparencia_municipal.cliente import MODULOS, Portal


@pytest.fixture(autouse=True)
def _sufixo_frl_nos_testes_offline(request, monkeypatch):
    """Os testes simulam só a API. Sem isto, cada Portal visitaria a página inicial para aprender os sufixos.

    Testes marcados com `descobre_sufixos` (e o teste ao vivo) usam a descoberta de verdade.
    """
    if "descobre_sufixos" in request.keywords or "ao_vivo" in request.keywords:
        return
    monkeypatch.setattr(Portal, "_descobrir_sufixos", lambda self: dict.fromkeys(MODULOS.values(), "frl"))
