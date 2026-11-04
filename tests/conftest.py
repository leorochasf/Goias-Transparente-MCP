import pytest

from transparencia_municipal import cliente
from transparencia_municipal.cliente import MODULOS, Portal


@pytest.fixture(autouse=True)
def _sufixo_frl_nos_testes_offline(request, monkeypatch):
    """Os testes simulam só a API. Sem isto, cada Portal visitaria a página inicial para aprender os sufixos.

    Testes marcados com `descobre_sufixos` (e o teste ao vivo) usam a descoberta de verdade.
    """
    cliente._SUFIXOS_APRENDIDOS.clear()  # o que um teste aprendeu não vaza para o próximo
    if "descobre_sufixos" in request.keywords or "ao_vivo" in request.keywords:
        return
    monkeypatch.setattr(Portal, "_descobrir_sufixos", lambda self: dict.fromkeys(MODULOS.values(), "frl"))


@pytest.fixture(autouse=True)
def _sem_internet_nos_testes_offline(request, monkeypatch):
    """Teste offline que tentar falar com um portal de verdade falha na hora (o `responses` ainda funciona)."""
    if "ao_vivo" in request.keywords:
        return
    import requests

    def recusar(self, requisicao, **kwargs):
        raise AssertionError(f"teste offline tentou acessar a internet: {requisicao.url}")
    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", recusar)
