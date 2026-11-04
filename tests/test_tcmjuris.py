"""TCMJuris do TCM-GO (acórdãos e leitura do PDF), com a fonte simulada no formato real. Offline."""
import json
import sys
from urllib.parse import parse_qs, urlparse

import anyio
import pytest
import responses
from mcp import Client

from transparencia_municipal import servidor_mcp, tcm
from transparencia_municipal.tcm import ClienteTCM, ErroTCM

TCMJURIS = tcm.FONTES["tcmjuris"]["base"]
BUSCAR = f"{TCMJURIS}/v1/acordao/jurisprudencia/buscar"
PDF = f"{TCMJURIS}/v1/acordao/jurisprudencia/pdf"
DOC = "e7910cb6-8dba-362b-a950-93727d848b66"


def _item(n, **campos):
    """Um item de `data[]` como o TCMJuris devolve (chaves medidas ao vivo em 04/11/2026)."""
    return {"document_id": f"0000000{n}-0000-3000-a000-000000000000", "numero_processo": f"0050{n}/25",
            "numero_acordao": f"0673{n}/26", "ano_votacao": 2026, "data_sessao": "17/09/2026",
            "assunto": "Balancete Semestral", "macro_assunto": "Prestações e Tomadas de Contas",
            "resultado": "Regular", "conselheiro_relator": "Relator Fictício", "conselheiro_revisor": "",
            "entidade_fiscalizada": "Câmara Municipal de Caldazinha", "orgao_julgador": "2ª Câmara",
            "ementa": "Resumo escrito por IA.", "ods_principais": [], "arquivo_pdf": f"0067{n}.pdf",
            "resumo_completo_total": "", "resumo_completo_total_estruturado": "", "relevancia_score": None,
            "tipo_decisao": "Acórdão", "tipo_processo": "Simples", **campos}


def _pagina(itens, *, page, page_size, total, busca_id="b1"):
    paginas = -(-total // page_size)
    return {"success": True, "data": itens, "busca_id": busca_id, "execution_time_ms": 12.0,
            "termos_tesauro_aplicados": [], "timestamp": "2026-11-04T10:00:00",
            "pagination": {"page": page, "page_size": page_size, "total_items": total, "total_pages": paginas,
                           "has_next": page < paginas, "has_prev": page > 1}}


def _pedidos():
    """Os parâmetros de cada chamada a /buscar, um valor por chave."""
    return [{k: v[0] for k, v in parse_qs(urlparse(c.request.url).query).items()}
            for c in responses.calls if "/buscar" in c.request.url]


def _pdf(texto=None):
    """Um PDF mínimo e válido; com `texto`, uma página com essa linha em Helvetica."""
    conteudo = f"BT /F1 12 Tf 72 720 Td ({texto}) Tj ET".encode() if texto else b""
    objetos = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
               b"/Resources << /Font << /F1 5 0 R >> >> >>",
               b"<< /Length %d >>\nstream\n" % len(conteudo) + conteudo + b"\nendstream",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    saida, posicoes = bytearray(b"%PDF-1.4\n"), []
    for i, obj in enumerate(objetos, 1):
        posicoes.append(len(saida))
        saida += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(saida)
    saida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1)
    saida += b"".join(b"%010d 00000 n \n" % p for p in posicoes)
    saida += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objetos) + 1, xref)
    return bytes(saida)


@pytest.fixture
def cliente():
    return ClienteTCM(pausa=0)


# --- busca -----------------------------------------------------------------------------------------------------------

@responses.activate
def test_envia_os_filtros_com_os_nomes_do_tcmjuris(cliente):
    responses.get(BUSCAR, json=_pagina([_item(1)], page=1, page_size=100, total=1))
    cliente.acordaos("Caldazinha", texto='"tomada de contas especial"', assunto="Balancete Semestral", ano=2023,
                     relator="Relator Fictício")
    assert _pedidos() == [{"municipio": "CALDAZINHA", "texto": '"tomada de contas especial"',
                           "assunto": "Balancete Semestral", "ano_votacao": "2023", "conselheiro": "Relator Fictício",
                           "page": "1", "page_size": "100"}]


@responses.activate
def test_filtro_nao_pedido_nao_vai_na_consulta(cliente):
    responses.get(BUSCAR, json=_pagina([_item(1)], page=1, page_size=100, total=1))
    cliente.acordaos(texto="imputação de débito")
    assert _pedidos() == [{"texto": "imputação de débito", "page": "1", "page_size": "100"}]


@responses.activate
def test_cada_acordao_traz_os_campos_da_spec_com_a_ementa_marcada_como_ia(cliente):
    responses.get(BUSCAR, json=_pagina([_item(1)], page=1, page_size=100, total=1))
    r = cliente.acordaos("Caldazinha")
    assert r["total"] == 1 and r["municipio_tcm"] == "CALDAZINHA"
    assert r["registros"] == [{
        "document_id": "00000001-0000-3000-a000-000000000000", "numero_processo": "00501/25",
        "numero_acordao": "06731/26", "data_sessao": "17/09/2026", "ano": 2026, "assunto": "Balancete Semestral",
        "macro_assunto": "Prestações e Tomadas de Contas", "resultado": "Regular",
        "entidade_fiscalizada": "Câmara Municipal de Caldazinha", "orgao_julgador": "2ª Câmara",
        "tipo_processo": "Simples", "relator": "Relator Fictício", "ementa_ia": "Resumo escrito por IA.",
        "fonte": "TCM-GO TCMJuris"}]
    assert "ementa" not in r["registros"][0]


@responses.activate
def test_pagina_com_o_busca_id_ate_o_maximo_sem_repetidos(cliente):
    # a fonte pode mandar menos que o page_size e repetir um item na virada da página
    responses.get(BUSCAR, json=_pagina([_item(1), _item(2)], page=1, page_size=2, total=7, busca_id="abc"))
    responses.get(BUSCAR, json=_pagina([_item(2), _item(3)], page=2, page_size=2, total=7, busca_id="abc"))
    responses.get(BUSCAR, json=_pagina([_item(4), _item(5)], page=3, page_size=2, total=7, busca_id="abc"))
    r = cliente.acordaos("Caldazinha", maximo=4)
    assert [x["numero_acordao"] for x in r["registros"]] == ["06731/26", "06732/26", "06733/26", "06734/26"]
    assert r["total"] == 7 and "incompleta" not in r
    pedidos = _pedidos()
    assert [p["page"] for p in pedidos] == ["1", "2", "3"] and {p["page_size"] for p in pedidos} == {"4"}
    assert "busca_id" not in pedidos[0] and pedidos[1]["busca_id"] == pedidos[2]["busca_id"] == "abc"


@responses.activate
def test_maximo_atingido_na_primeira_pagina_nao_pede_a_segunda(cliente):
    responses.get(BUSCAR, json=_pagina([_item(1), _item(2)], page=1, page_size=2, total=5))
    r = cliente.acordaos("Caldazinha", maximo=2)
    assert len(r["registros"]) == 2 and r["total"] == 5 and len(responses.calls) == 1
    assert _pedidos()[0]["page_size"] == "2"


@responses.activate
def test_para_quando_a_fonte_diz_que_nao_ha_proxima_pagina(cliente):
    responses.get(BUSCAR, json=_pagina([_item(1), _item(2)], page=1, page_size=100, total=2))
    r = cliente.acordaos("Caldazinha", maximo=500)
    assert len(r["registros"]) == 2 and len(responses.calls) == 1


@responses.activate
def test_teto_de_chamadas_devolve_o_lido_e_marca_leitura_incompleta(cliente):
    cliente.teto = 2
    for p in (1, 2, 3):  # um por página, para chegar ao teto
        responses.get(BUSCAR, json=_pagina([_item(p)], page=p, page_size=1, total=9))
    r = cliente.acordaos("Caldazinha", maximo=9)
    assert len(r["registros"]) == 2 and r["total"] == 9 and len(responses.calls) == 2
    assert "teto" in r["incompleta"] and "incompleta" in r["aviso_leitura"]


@responses.activate
@pytest.mark.parametrize("corpo", [
    {"success": False, "data": [], "pagination": {"total_items": 0}},
    {"success": True, "pagination": {"total_items": 0}},
    {"success": True, "data": [], "detail": "erro"},
    {"detail": "manutenção"},
])
def test_resposta_sem_success_data_e_pagination_e_erro_nunca_lista_vazia(cliente, corpo):
    responses.get(BUSCAR, json=corpo)
    with pytest.raises(ErroTCM, match="TCMJuris"):
        cliente.acordaos("Caldazinha")


@responses.activate
def test_html_com_200_vira_erro(cliente):
    responses.get(BUSCAR, body="<html>manutenção</html>", content_type="text/html")
    with pytest.raises(ErroTCM, match="TCMJuris"):
        cliente.acordaos("Caldazinha")


def _filtros(*municipios):
    responses.get(f"{TCMJURIS}/v1/acordao/jurisprudencia/filtros", json={
        "success": True, "data": {"municipios": [{"nome": n, "valor": v} for n, v in municipios]}})


@responses.activate
def test_zero_com_nome_que_mudou_na_fonte_repete_com_o_valor_oficial_de_agora(cliente):
    # ao vivo, um `municipio` que o TCMJuris não conhece dá 200 com total 0, em silêncio
    responses.get(BUSCAR, json=_pagina([], page=1, page_size=100, total=0))
    _filtros(("Caldazinha", "CALDAZINHA NOVA"))
    responses.get(BUSCAR, json=_pagina([_item(1)], page=1, page_size=100, total=1))
    r = cliente.acordaos("Caldazinha")
    assert r["total"] == 1 and r["municipio_tcm"] == "CALDAZINHA NOVA"
    assert _pedidos()[-1]["municipio"] == "CALDAZINHA NOVA"


@responses.activate
def test_zero_com_municipio_que_saiu_da_lista_oficial_e_recusa_nunca_ausencia(cliente):
    responses.get(BUSCAR, json=_pagina([], page=1, page_size=100, total=0))
    _filtros(("Posse", "POSSE"))
    with pytest.raises(tcm.MunicipioNaoEncontrado):
        cliente.acordaos("Caldazinha")


@responses.activate
def test_zero_com_nome_conferido_na_lista_oficial_e_resposta_valida(cliente):
    responses.get(BUSCAR, json=_pagina([], page=1, page_size=100, total=0))
    _filtros(("Caldazinha", "CALDAZINHA"))
    r = cliente.acordaos("Caldazinha", ano=2020)
    assert r["total"] == 0 and r["registros"] == [] and len(responses.calls) == 2


@responses.activate
def test_fonte_que_para_antes_do_total_marca_leitura_incompleta(cliente):
    responses.get(BUSCAR, json={**_pagina([_item(1)], page=1, page_size=100, total=5),
                                "pagination": {"page": 1, "page_size": 100, "total_items": 5, "total_pages": 1,
                                               "has_next": False, "has_prev": False}})
    r = cliente.acordaos("Caldazinha")
    assert len(r["registros"]) == 1 and "antes do total" in r["incompleta"]


@pytest.mark.parametrize("maximo", [0, -5])
def test_maximo_menor_que_um_e_recusado_sem_consultar(cliente, maximo):
    with pytest.raises(ValueError, match="maximo"):
        cliente.acordaos("Caldazinha", maximo=maximo)


# --- leitura do PDF --------------------------------------------------------------------------------------------------

@responses.activate
def test_pdf_vira_texto_com_o_link_do_pdf(cliente):
    responses.get(f"{PDF}/{DOC}", body=_pdf("ACORDAO 06734/26 - Caldazinha"), content_type="application/pdf")
    r = cliente.ler_acordao(f" {DOC} ")
    assert r["total"] == 1 and "aviso_texto" not in r
    (reg,) = r["registros"]
    assert reg["document_id"] == DOC and reg["pdf"] == f"{PDF}/{DOC}"
    assert "ACORDAO 06734/26 - Caldazinha" in reg["texto"]


@responses.activate
def test_pdf_sem_texto_traz_aviso(cliente):
    responses.get(f"{PDF}/{DOC}", body=_pdf(), content_type="application/pdf")
    r = cliente.ler_acordao(DOC)
    assert r["registros"][0]["texto"] == ""
    assert "digitalizado" in r["aviso_texto"] and f"{PDF}/{DOC}" in r["aviso_texto"]


@responses.activate
def test_resposta_que_nao_e_pdf_vira_erro(cliente):
    responses.get(f"{PDF}/{DOC}", body="<html>manutenção</html>", content_type="text/html")
    with pytest.raises(ErroTCM, match="não é PDF"):
        cliente.ler_acordao(DOC)


@responses.activate
def test_pdf_inexistente_vira_erro_claro(cliente):
    responses.get(f"{PDF}/{DOC}", status=404, json={"detail": "PDF nao encontrado no servidor GED"})
    with pytest.raises(ErroTCM, match="404"):
        cliente.ler_acordao(DOC)


@responses.activate
def test_id_com_barra_nao_escapa_do_caminho_do_pdf(cliente):
    responses.get(f"{PDF}/..%2Ffiltros", body=_pdf("x"), content_type="application/pdf")
    cliente.ler_acordao("../filtros")
    assert responses.calls[0].request.url == f"{PDF}/..%2Ffiltros"


@responses.activate
def test_sem_a_biblioteca_de_pdf_erro_com_instrucao_e_link_sem_baixar(cliente, monkeypatch):
    monkeypatch.setitem(sys.modules, "pypdf", None)  # `import pypdf` passa a falhar
    with pytest.raises(ErroTCM) as e:
        cliente.ler_acordao(DOC)
    assert tcm.INSTALAR_PDF in str(e.value) and f"{PDF}/{DOC}" in str(e.value)
    assert len(responses.calls) == 0


# --- ponta a ponta: ferramentas MCP no mesmo processo e linha de comando ----------------------------------------------

def _chamar(ferramenta, **argumentos):
    async def rodar():
        async with Client(servidor_mcp.mcp) as c:
            r = await c.call_tool(ferramenta, argumentos)
            return json.loads(r.content[0].text)
    return anyio.run(rodar)


@responses.activate
def test_mcp_acordaos_tcm_de_ponta_a_ponta_com_os_avisos_fixos(monkeypatch):
    monkeypatch.setattr(servidor_mcp, "_tcm", lambda: ClienteTCM(pausa=0))
    responses.get(BUSCAR, json=_pagina([_item(1), _item(2)], page=1, page_size=100, total=2))
    r = _chamar("acordaos_tcm", municipio="caldazinha", assunto="Balancete Semestral")
    assert r["total"] == 2 and r["municipio_tcm"] == "CALDAZINHA"
    assert [x["ementa_ia"] for x in r["registros"]] == ["Resumo escrito por IA."] * 2
    assert r["aviso_fonte"] == tcm.AVISO_ACORDAOS and r["aviso"] == tcm.AVISO_GERAL
    assert _pedidos()[0]["municipio"] == "CALDAZINHA"


@responses.activate
def test_mcp_ler_acordao_tcm_de_ponta_a_ponta_com_os_avisos_fixos(monkeypatch):
    monkeypatch.setattr(servidor_mcp, "_tcm", lambda: ClienteTCM(pausa=0))
    responses.get(f"{PDF}/{DOC}", body=_pdf("ACORDAO 06734/26"), content_type="application/pdf")
    r = _chamar("ler_acordao_tcm", id=DOC)
    assert "ACORDAO 06734/26" in r["registros"][0]["texto"] and r["registros"][0]["pdf"] == f"{PDF}/{DOC}"
    assert r["aviso_fonte"] == tcm.AVISO_ACORDAOS and r["aviso"] == tcm.AVISO_GERAL


@responses.activate
def test_mcp_ler_acordao_sem_a_biblioteca_responde_erro_com_instrucao(monkeypatch):
    monkeypatch.setattr(servidor_mcp, "_tcm", lambda: ClienteTCM(pausa=0))
    monkeypatch.setitem(sys.modules, "pypdf", None)
    r = _chamar("ler_acordao_tcm", id=DOC)
    assert tcm.INSTALAR_PDF in r["erro"] and f"{PDF}/{DOC}" in r["erro"]
    assert r["aviso_fonte"] == tcm.AVISO_ACORDAOS


@responses.activate
def test_cli_tcm_acordaos_de_ponta_a_ponta(capsys, tmp_path):
    from transparencia_municipal import cli
    responses.get(BUSCAR, json=_pagina([_item(1)], page=1, page_size=100, total=1))
    saida = tmp_path / "a.json"
    cli.main(["--pausa", "0", "--json", str(saida), "tcm-acordaos", "--municipio", "Caldazinha", "--assunto",
              "Balancete Semestral"])
    assert tcm.AVISO_ACORDAOS in capsys.readouterr().out
    (reg,) = json.loads(saida.read_text(encoding="utf-8"))
    assert reg["ementa_ia"] == "Resumo escrito por IA." and reg["fonte"] == "TCM-GO TCMJuris"
