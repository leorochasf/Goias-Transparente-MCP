"""Consulta ao Portal da Transparência de municípios (plataforma NucleoGov)."""
from .cliente import ErroPortal, Portal, PortalBloqueou
from .tcm import ClienteTCM, ErroTCM

__all__ = ["Portal", "ErroPortal", "PortalBloqueou", "ClienteTCM", "ErroTCM"]
__version__ = "0.6.0"
