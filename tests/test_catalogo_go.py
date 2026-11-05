"""Script do catálogo, passos `conferir` e `juntar`: seleção dos órgãos, saída por frente, retomada. Offline."""
import argparse
import importlib.util
import json
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("catalogo_go", RAIZ / "scripts" / "catalogo_go.py")
catalogo_go = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(catalogo_go)


def _orgao(municipio, orgao, host):
    return {"ibge": "52", "municipio": municipio, "orgao": orgao, "entidade": "", "hosts": [host] if host else []}


#: órgãos fora da ordem alfabética, com acento, cada plataforma e um sem portal
ORGAOS = [
    _orgao("Posse", "prefeitura", "acessoainformacao.posse.go.gov.br"),
    _orgao("Posse", "camara", "acessoainformacao.posse.go.leg.br"),
    _orgao("Águas Lindas de Goiás", "prefeitura", "acessoainformacao.aguaslindasdegoias.go.gov.br"),
    _orgao("Caldazinha", "prefeitura", "acessoainformacao.caldazinha.go.gov.br"),
    _orgao("Corumbaíba", "prefeitura", "corumbaiba.megasofttransparencia.com.br"),
    _orgao("Cidade Ocidental", "camara", "cidadeocidental.go.leg.br"),
    _orgao("Aruanã", "prefeitura", "acessoainformacao.aruana.go.gov.br"),
    _orgao("Bela Vista de Goiás", "camara", "camarabelavista.go.leg.br"),  # sem plataforma
    _orgao("Trindade", "prefeitura", "acessoainformacao.trindade.go.gov.br"),
]
SONDADOS = {
    "acessoainformacao.caldazinha.go.gov.br": {"plataforma": "nucleogov-megasoft"},
    "cidadeocidental.go.leg.br": {"plataforma": "ortrel"},
    "camarabelavista.go.leg.br": {"plataforma": None},
}


def _municipios(selecao):
    return [(o["municipio"], o["orgao"]) for o, _, _ in selecao]


def test_todos_os_orgaos_com_plataforma_em_ordem_alfabetica_de_municipio():
    selecao = catalogo_go._selecionar(ORGAOS, SONDADOS, todos=True)
    assert _municipios(selecao) == [
        ("Águas Lindas de Goiás", "prefeitura"), ("Aruanã", "prefeitura"), ("Caldazinha", "prefeitura"),
        ("Cidade Ocidental", "camara"), ("Corumbaíba", "prefeitura"),
        ("Posse", "camara"), ("Posse", "prefeitura"), ("Trindade", "prefeitura")]
    assert ("Bela Vista de Goiás", "camara") not in _municipios(selecao)  # sem plataforma, fora


def test_filtro_por_plataforma_sozinho_vale_por_todos():
    selecao = catalogo_go._selecionar(ORGAOS, SONDADOS, plataformas=["megasoft", "ortrel"])
    assert [(o["municipio"], p) for o, _, p in selecao] == [("Cidade Ocidental", "ortrel"), ("Corumbaíba", "megasoft")]


def test_filtro_por_municipio_e_plataforma_juntos():
    selecao = catalogo_go._selecionar(ORGAOS, SONDADOS, municipios=["posse", "Caldazinha"], plataformas=["nucleogov"])
    assert _municipios(selecao) == [("Posse", "camara"), ("Posse", "prefeitura")]


@pytest.mark.parametrize("partes", [2, 3, 5])
def test_fatias_nao_repetem_nem_perdem_orgao(partes):
    filtro = {"plataformas": ["nucleogov", "nucleogov-megasoft"]}
    inteiro = catalogo_go._selecionar(ORGAOS, SONDADOS, **filtro)
    fatias = [catalogo_go._selecionar(ORGAOS, SONDADOS, fatia=(k, partes), **filtro) for k in range(1, partes + 1)]
    juntas = [host for f in fatias for _, host, _ in f]
    assert juntas == [host for _, host, _ in inteiro]  # mesma ordem, sem repetir nem perder
    assert max(map(len, fatias)) - min(map(len, fatias)) <= 1


def test_primeira_metade_e_a_do_comeco_do_alfabeto():
    filtro = {"plataformas": ["nucleogov", "nucleogov-megasoft"]}
    primeira = catalogo_go._selecionar(ORGAOS, SONDADOS, fatia=(1, 2), **filtro)
    segunda = catalogo_go._selecionar(ORGAOS, SONDADOS, fatia=(2, 2), **filtro)
    assert [o["municipio"] for o, _, _ in primeira] == ["Águas Lindas de Goiás", "Aruanã", "Caldazinha"]
    assert [o["municipio"] for o, _, _ in segunda] == ["Posse", "Posse", "Trindade"]


@pytest.mark.parametrize("texto", ["0/2", "3/2", "1", "a/b", "1/0"])
def test_fatia_invalida_e_recusada(texto):
    with pytest.raises(argparse.ArgumentTypeError):
        catalogo_go._fatia(texto)


def test_plataforma_desconhecida_e_recusada():
    with pytest.raises(argparse.ArgumentTypeError):
        catalogo_go._plataformas("nucleogov,nucelogov")


@pytest.fixture
def trabalho(tmp_path, monkeypatch):
    """O script lendo e gravando numa pasta temporária, com a conferência de cada portal simulada."""
    monkeypatch.setattr(catalogo_go, "TRABALHO", tmp_path)
    monkeypatch.setattr(catalogo_go, "CANDIDATOS", tmp_path / "candidatos.json")
    monkeypatch.setattr(catalogo_go, "SONDAGEM", tmp_path / "sondagem.jsonl")
    monkeypatch.setattr(catalogo_go, "CONFERENCIAS", tmp_path / "conferencias.json")
    monkeypatch.setattr(catalogo_go.time, "sleep", lambda s: None)
    (tmp_path / "candidatos.json").write_text(json.dumps(ORGAOS, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "sondagem.jsonl").write_text(
        "".join(json.dumps({"host": h, **s}) + "\n" for h, s in SONDADOS.items()), encoding="utf-8")
    return tmp_path


def _args(**kw):
    base = {"municipios": None, "todos": False, "plataformas": None, "fatia": None, "saida": "conferencias.json",
            "ano": 2025, "mes": 6, "pausa": 0}
    return argparse.Namespace(**{**base, **kw})


def _simular_conferencia(monkeypatch, saida):
    """Cada conferência simulada anota o que já estava gravado no arquivo de saída quando ela começou."""
    chamadas = []

    def falsa(portal, *, ano, mes):
        gravado = json.loads(saida.read_text(encoding="utf-8")) if saida.exists() else {}
        chamadas.append((portal.url, sorted(gravado)))
        return {"data": "2026-11-05", "referencia": f"{mes:02d}/{ano}", "filtros": {"folha_mes": "ok"}, "detalhes": {}}
    monkeypatch.setattr(catalogo_go, "conferir_portal", falsa)
    return chamadas


def test_conferir_grava_na_saida_da_frente_depois_de_cada_orgao_e_retoma(trabalho, monkeypatch):
    saida = trabalho / "conferencias-frente2.json"
    ja = {"data": "2026-11-04", "referencia": "06/2025", "filtros": {"folha_mes": "ok"}, "detalhes": {}}
    saida.write_text(json.dumps({"acessoainformacao.aguaslindasdegoias.go.gov.br": ja}), encoding="utf-8")
    chamadas = _simular_conferencia(monkeypatch, saida)

    catalogo_go.conferir(_args(plataformas=["nucleogov", "nucleogov-megasoft"], fatia=(1, 2),
                               saida="conferencias-frente2.json"))

    assert [url for url, _ in chamadas] == ["https://acessoainformacao.aruana.go.gov.br",
                                            "https://acessoainformacao.caldazinha.go.gov.br"]  # Águas Lindas pulada
    assert chamadas[1][1] == ["acessoainformacao.aguaslindasdegoias.go.gov.br",
                              "acessoainformacao.aruana.go.gov.br"]  # Aruanã já gravada antes de Caldazinha
    gravado = json.loads(saida.read_text(encoding="utf-8"))
    assert gravado["acessoainformacao.aguaslindasdegoias.go.gov.br"] == ja  # a retomada não refaz nem apaga
    assert len(gravado) == 3
    assert not (trabalho / "conferencias.json").exists()  # a frente não toca o arquivo comum


def test_conferir_sem_saida_usa_o_arquivo_comum(trabalho, monkeypatch):
    chamadas = _simular_conferencia(monkeypatch, trabalho / "conferencias.json")
    catalogo_go.conferir(_args(municipios=["Trindade"]))
    assert [url for url, _ in chamadas] == ["https://acessoainformacao.trindade.go.gov.br"]
    assert list(json.loads((trabalho / "conferencias.json").read_text(encoding="utf-8"))) == [
        "acessoainformacao.trindade.go.gov.br"]


def test_conferir_le_as_camaras_ortrel_pela_plataforma_do_catalogo(trabalho, monkeypatch):
    portais = []

    def falsa(portal, *, ano, mes):
        portais.append(portal)
        return {"data": "2026-11-05", "referencia": "06/2025", "filtros": {"folha_mes": "ok"}, "detalhes": {}}
    monkeypatch.setattr(catalogo_go, "conferir_portal", falsa)
    catalogo_go.conferir(_args(plataformas=["megasoft", "ortrel"]))
    assert [(x.url, x.plataforma, x.navegador) for x in portais] == [
        ("https://cidadeocidental.go.leg.br", "ortrel", False),
        ("https://corumbaiba.megasofttransparencia.com.br", None, False)]
    assert "cidadeocidental.go.leg.br" in json.loads((trabalho / "conferencias.json").read_text(encoding="utf-8"))


def _conf(data, filtro="ok"):
    return {"data": data, "referencia": "06/2025", "filtros": {"folha_mes": filtro}, "detalhes": {}, "sufixos": {}}


def test_juntar_acrescenta_e_so_substitui_pela_mais_recente(trabalho):
    comum = trabalho / "conferencias.json"
    comum.write_text(json.dumps({
        "a.go.gov.br": _conf("2026-11-01", "falhou"),
        "b.go.gov.br": _conf("2026-11-04", "ok"),
        "so-no-comum.go.gov.br": _conf("2026-10-01"),
    }), encoding="utf-8")
    (trabalho / "frente1.json").write_text(json.dumps({"a.go.gov.br": _conf("2026-11-05", "ok"),
                                                       "c.go.gov.br": _conf("2026-11-05")}), encoding="utf-8")
    (trabalho / "frente2.json").write_text(json.dumps({"b.go.gov.br": _conf("2026-11-03", "falhou")}), encoding="utf-8")

    catalogo_go.juntar(argparse.Namespace(arquivos=["frente1.json", str(trabalho / "frente2.json")]))

    junto = json.loads(comum.read_text(encoding="utf-8"))
    assert set(junto) == {"a.go.gov.br", "b.go.gov.br", "c.go.gov.br", "so-no-comum.go.gov.br"}
    assert junto["a.go.gov.br"]["data"] == "2026-11-05"  # mais recente substitui
    assert junto["b.go.gov.br"]["filtros"]["folha_mes"] == "ok"  # mais antiga não substitui
    assert junto["so-no-comum.go.gov.br"]["data"] == "2026-10-01"  # o que já estava fica


def test_juntar_na_mesma_data_fica_a_do_arquivo_juntado(trabalho):
    """A data não tem hora: no mesmo dia, a da frente é a rodada que veio depois."""
    (trabalho / "conferencias.json").write_text(json.dumps({"a.go.gov.br": _conf("2026-11-05", "falhou")}),
                                                encoding="utf-8")
    (trabalho / "frente.json").write_text(json.dumps({"a.go.gov.br": _conf("2026-11-05", "ok")}), encoding="utf-8")
    catalogo_go.juntar(argparse.Namespace(arquivos=["frente.json"]))
    junto = json.loads((trabalho / "conferencias.json").read_text(encoding="utf-8"))
    assert junto["a.go.gov.br"]["filtros"]["folha_mes"] == "ok"


def test_juntar_sem_o_arquivo_comum_cria_o_arquivo(trabalho):
    (trabalho / "frente.json").write_text(json.dumps({"a.go.gov.br": _conf("2026-11-05")}), encoding="utf-8")
    catalogo_go.juntar(argparse.Namespace(arquivos=["frente.json"]))
    assert list(json.loads((trabalho / "conferencias.json").read_text(encoding="utf-8"))) == ["a.go.gov.br"]
