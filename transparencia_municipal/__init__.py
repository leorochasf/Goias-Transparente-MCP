"""Consulta ao Portal da Transparência de municípios (plataforma NucleoGov)."""
from .cliente import ErroPortal, Portal, PortalBloqueou

__all__ = ["Portal", "ErroPortal", "PortalBloqueou"]
__version__ = "0.3.0"
