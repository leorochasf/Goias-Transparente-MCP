"""Acórdão do TCM-GO pelo número do processo ou do acórdão (TCMJuris simulado no formato real). Offline.

Descoberta F (docs/design/2026-11-04-modulos-extras.md): os filtros `numero_processo_filtro` e `numero_acordao_filtro`
aceitam parte do número ("começa com", sem os zeros à esquerda); sem o ano, vêm todos os anos. Só a conferência
campo a campo, de número e ano, prova o resultado.
"""
import json
from urllib.parse import parse_qs, urlparse

import anyio
import pytest
import responses
from mcp import Client

from transparencia_municipal import cli, servidor_mcp, tcm
from transparencia_municipal.tcm import ClienteTCM

BUSCAR = f"{tcm.FONTES['tcmjuris']['base']}/v1/acordao/jurisprudencia/buscar"


def _item(processo, acordao, n):
    return {"document_id": f"doc-{n}", "numero_processo": processo, "numero_acordao": acordao, "ano_votacao": 2024,
            "data_sessao": "01/02/2024", "assunto": "Contas", "macro_assunto": "x", "resultado": "Regular",
            "conselheiro_relator": "Relator Fictício", "entidade_fiscalizada": "Câmara", "orgao_julgador": "Pleno",
            "ementa": "Resumo escrito por IA.", "tipo_processo": "Simples"}


def _resposta(itens):
    return {"success": True, "data": itens, "busca_id": "b1",
            "pagination": {"page": 1, "page_size": 100, "total_items": len(itens), "total_pages": 1,
                           "has_next": False, "has_prev": False}}


def _simular(por_processo, por_acordao):
    """O TCMJuris: uma lista para o filtro de processo, outra para o de acórdão."""
    def callback(requisicao):
        q = {k: v[0] for k, v in parse_qs(urlparse(requisicao.url).query).items()}
        itens = por_processo if "numero_processo_filtro" in q else por_acordao if "numero_acordao_filtro" in q else []
        return 200, {}, json.dumps(_resposta(itens))
    responses.add_callback(responses.GET, BUSCAR, callback=callback, content_type="application/json")


def _pedidos():
    return [{k: v[0] for k, v in parse_qs(urlparse(c.request.url).query).items()} for c in responses.calls]


@pytest.fixture
def cliente():
    return ClienteTCM(pausa=0)


@responses.activate
def test_numero_completo_busca_nos_dois_filtros_e_confere_numero_e_ano(cliente):
    _simular([_item("10175/23", "07286/24", 1), _item("10175/24", "00001/25", 2)], [])
    r = cliente.acordaos(numero="10175/23")
    assert [x["document_id"] for x in r["registros"]] == ["doc-1"] and r["total"] == 1
    assert r["registros"][0]["casou_com"] == "processo"
    assert {p.get("numero_processo_filtro") or p.get("numero_acordao_filtro") for p in _pedidos()} == {"10175/23"}
    assert "1 resultado" in r["aviso_numero"] and "outro número" in r["aviso_numero"]


@responses.activate
def test_numero_do_acordao_com_ano_de_quatro_digitos_e_zero_a_esquerda(cliente):
    _simular([], [_item("10175/23", "07286/24", 1)])
    r = cliente.acordaos(numero=" 7286/2024 ")
    assert r["registros"][0]["casou_com"] == "acordao" and "aviso_numero" not in r
    assert _pedidos()[1]["numero_acordao_filtro"] == "07286/24"


@responses.activate
def test_numero_sem_ano_traz_todos_os_anos_e_avisa(cliente):
    anos = [_item(f"0{n}/2{n}", f"07286/2{n}", n) for n in range(5)]
    _simular([], anos + [_item("1/20", "72861/25", 9)])  # "começa com": 72861 não é 7286
    r = cliente.acordaos(numero="7286")
    assert r["total"] == 5 and "doc-9" not in [x["document_id"] for x in r["registros"]]
    assert "sem o ano" in r["aviso_numero"] and "5 anos" in r["aviso_numero"]
    assert _pedidos()[0]["numero_processo_filtro"] == "7286"


@responses.activate
def test_o_mesmo_acordao_achado_pelos_dois_filtros_vem_uma_vez(cliente):
    item = _item("07286/24", "07286/24", 1)
    _simular([item], [item])
    r = cliente.acordaos(numero="07286/24")
    assert r["total"] == 1 and r["registros"][0]["casou_com"] == "processo e acordao"


@responses.activate
def test_numero_combina_com_os_outros_filtros(cliente):
    _simular([], [])
    cliente.acordaos(numero="10175/23", ano=2024, maximo=5)
    assert all(p["ano_votacao"] == "2024" for p in _pedidos())


@pytest.mark.parametrize("numero", ["abc", "10175/2", "10175-23", ""])
def test_numero_fora_do_formato_e_recusado_sem_consultar(cliente, numero):
    with pytest.raises(ValueError, match="NNNNN/AA"):
        cliente.acordaos(numero=numero)


@responses.activate
def test_mcp_acordaos_tcm_por_numero_de_ponta_a_ponta(monkeypatch):
    monkeypatch.setattr(servidor_mcp, "_tcm", lambda: ClienteTCM(pausa=0))
    _simular([_item("10175/23", "07286/24", 1)], [])

    async def rodar():
        async with Client(servidor_mcp.mcp) as c:
            r = await c.call_tool("acordaos_tcm", {"numero": "10175/23"})
            return json.loads(r.content[0].text)
    r = anyio.run(rodar)
    assert r["total"] == 1 and r["registros"][0]["numero_processo"] == "10175/23"
    assert r["aviso_fonte"] == tcm.AVISO_ACORDAOS


@responses.activate
def test_cli_tcm_acordaos_por_numero_mostra_o_aviso(capsys):
    _simular([], [_item("1/20", "07286/20", 1), _item("1/22", "07286/22", 2)])
    cli.main(["--pausa", "0", "tcm-acordaos", "--numero", "7286"])
    texto = capsys.readouterr().out
    assert "AVISO: número sem o ano" in texto and "2 registros no TCM-GO" in texto
