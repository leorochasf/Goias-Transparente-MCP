"""Servidor MCP: deixa um assistente de IA consultar o Portal da Transparência de um município.

Rodar:  python -m transparencia_municipal.servidor_mcp
Config: TRANSPARENCIA_PORTAL (portal padrão), TRANSPARENCIA_NAVEGADOR=1 (ver README, "O 403").
"""
from __future__ import annotations

import os

from mcp.server.mcpserver import MCPServer

from .cliente import ErroPortal, Portal

mcp = MCPServer("transparencia-municipal",
                instructions="Consulta dados públicos do Portal da Transparência de municípios brasileiros na plataforma NucleoGov: folha de pagamento, empenhos, contratos, licitações, receitas e legislação.")

AVISO = ("Dado público do Portal da Transparência do município (Lei 12.527/2011), lido na hora. "
         "Confira no portal antes de usar em peça, denúncia ou matéria.")


def _portal(url=None):
    endereco = url or os.getenv("TRANSPARENCIA_PORTAL")
    if not endereco:
        raise ValueError("Informe o portal (ex.: https://acessoainformacao.cidade.go.gov.br) "
                         "ou defina TRANSPARENCIA_PORTAL.")
    return Portal(endereco, navegador=os.getenv("TRANSPARENCIA_NAVEGADOR") == "1")


def _resposta(dados):
    return {**dados, "aviso": AVISO}


def _executar(funcao):
    try:
        return _resposta(funcao())
    except (ErroPortal, ValueError) as e:
        return {"erro": str(e)}


@mcp.tool()
def consultar_folha(ano: int, mes: int | None = None, busca: str | None = None,
                    portal: str | None = None, maximo: int = 100) -> dict:
    """Servidores e remuneração de um mês. `busca` filtra pelo NOME do servidor (não por cargo).

    Ex.: quanto ganhou Fulano de Tal em março. Para "quantos comissionados existem",
    traga o mês inteiro (maximo alto) e conte pelos campos cargo/lotacao dos registros.
    """
    return _executar(lambda: _portal(portal).folha(ano, mes, busca, maximo=maximo))


@mcp.tool()
def consultar_despesas(de: str, ate: str, busca: str | None = None,
                       portal: str | None = None, maximo: int = 100) -> dict:
    """Empenhos e pagamentos no período (datas AAAA-MM-DD). `busca` aceita nome ou CNPJ do fornecedor.

    CNPJ (com ou sem pontuação) traz só os empenhos daquele CNPJ; outro texto vai na busca livre.

    Ex.: quanto o município pagou à empresa tal em 2025.
    """
    return _executar(lambda: _portal(portal).despesas(de, ate, busca, maximo=maximo))


@mcp.tool()
def consultar_contratos(ano: int | None = None, tipo: str = "contrato", busca: str | None = None,
                        portal: str | None = None, maximo: int = 100) -> dict:
    """Contratos (tipo="contrato") ou aditivos (tipo="aditivo") do município."""
    return _executar(lambda: _portal(portal).contratos(ano, tipo, busca, maximo=maximo))


@mcp.tool()
def consultar_licitacoes(busca: str | None = None, dispensas: bool = False,
                         portal: str | None = None, maximo: int = 100) -> dict:
    """Licitações do município; dispensas=True traz dispensas e inexigibilidades."""
    return _executar(lambda: _portal(portal).licitacoes(busca, dispensas=dispensas, maximo=maximo))


@mcp.tool()
def consultar_receitas(de: str, ate: str, portal: str | None = None, maximo: int = 100) -> dict:
    """Receitas arrecadadas no período (datas AAAA-MM-DD)."""
    return _executar(lambda: _portal(portal).receitas(de, ate, maximo=maximo))


@mcp.tool()
def consultar_legislacao(municipio: str, tipo: str | None = None, busca: str | None = None,
                         portal: str | None = None, maximo: int = 100) -> dict:
    """Leis, decretos e portarias. `municipio` é o apelido do portal (ex.: senador_canedo).

    Como descobrir o apelido: README, seção "Legislação".
    """
    return _executar(lambda: _portal(portal).legislacao(municipio, tipo, busca, maximo=maximo))


def main():
    mcp.run()


if __name__ == "__main__":
    main()
