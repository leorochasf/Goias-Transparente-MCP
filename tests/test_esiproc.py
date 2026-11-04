"""eSiproc do TCM-GO (processos), com a fonte simulada no formato real do `/pesquisar`. Offline."""
import json

import pytest
import responses

from transparencia_municipal import tcm
from transparencia_municipal.tcm import ClienteTCM, ErroTCM

PESQUISAR = f"{tcm.FONTES['esiproc']['base']}/pesquisar"
CHAVES_FILTROS = {
    "municipio.keyword", "unidade_gestora.keyword", "relator.keyword", "regiao.keyword", "tipo_protocolo.keyword",
    "tags.nome.keyword", "area.keyword", "ano_competencia", "periodo_competencia.keyword", "lotacao.keyword",
    "envolvidos.situacao.keyword", "envolvidos.tipo_envolvimento.keyword", "range.data_protocolo.gte",
    "range.data_protocolo.lte", "finalizado.keyword"}


def _fonte(n):
    """Um `_source` no formato real (campos e tipos medidos ao vivo); nomes de pessoas são fictícios."""
    return {
        "numero": f"{n:08d}.2023.001.4.14838.0223", "municipio": "NOVA CRIXÁS", "codigo_ibge": "14838",
        "id_municipio": 161, "unidade_gestora": "FUNDO MUNICIPAL DE SAÚDE", "tipo_protocolo": "Contas de Gestão",
        "ano_competencia": 2023, "mes_competencia": 12, "periodo_competencia": "Anual/2023",
        "relator": "CONSELHEIRO FICTÍCIO", "st_fase": "EM ANDAMENTO", "fase": "INSTRUÇÃO", "finalizado": "NÃO",
        "passo": "Análise técnica", "data_protocolo": "2024-04-30T10:00Z", "data_criacao": "2024-04-29T09:00Z",
        "data_ultima_tramitacao": "2024-09-01T12:00Z", "data_finalizacao": None,
        "decisoes": [{"id": 9, "nome": "Acórdão AC-CG 00123/24", "nome_arquivo": "ac.pdf", "id_ged": 77,
                      "data_criacao": "2024-08-20T15:00Z", "nome_envolvido": "FULANO FICTÍCIO",
                      "tipo_envolvido": "Gestor"}],
        "envolvidos": [{"id": 1, "nome": "FULANO FICTÍCIO", "tipo_envolvimento": "Gestor", "tipo_pessoa": "FÍSICA",
                        "situacao": "ATIVO", "data_inicio": "2024-04-30T10:00Z"}],
        "tags": [], "processo": "SIM"}


def _resposta(numeros, total, relation="eq", timed_out=False, falhas=0):
    return {"took": 5, "timed_out": timed_out, "isAdministrativo": False,
            "_shards": {"total": 1, "successful": 1 - falhas, "skipped": 0, "failed": falhas},
            "hits": {"total": {"value": total, "relation": relation}, "max_score": None,
                     "hits": [{"_index": "processo", "_id": str(n), "_score": None, "_source": _fonte(n)}
                              for n in numeros]}}


def _corpos():
    return [json.loads(c.request.body) for c in responses.calls]


@pytest.fixture
def cliente():
    return ClienteTCM(pausa=0)


@responses.activate
def test_corpo_leva_todas_as_chaves_de_filtros_com_os_filtros_combinados(cliente):
    responses.post(PESQUISAR, json=_resposta([1], 1))
    cliente.processos("nova crixas", tipo="Contas de Gestão", ano=2023, finalizado=False, relator="CONSELHEIRO X")
    corpo = _corpos()[0]
    assert set(corpo["filtros"]) == CHAVES_FILTROS
    usados = {k: v for k, v in corpo["filtros"].items() if v is not None}
    assert usados == {"municipio.keyword": "NOVA CRIXÁS", "tipo_protocolo.keyword": "Contas de Gestão",
                      "ano_competencia": 2023, "finalizado.keyword": "NÃO", "relator.keyword": "CONSELHEIRO X"}
    assert corpo["pagina"] == 0 and corpo["filtrosLike"] is None
    assert {"numero", "termo", "filtrosLikeNested", "filtroPeriodoJulgamento"} <= set(corpo)


@responses.activate
def test_finalizado_verdadeiro_vira_sim_e_none_nao_filtra(cliente):
    responses.post(PESQUISAR, json=_resposta([1], 1))
    cliente.processos("Nova Crixás", finalizado=True)
    cliente.processos("Nova Crixás")
    assert [c["filtros"]["finalizado.keyword"] for c in _corpos()] == ["SIM", None]


@responses.activate
def test_registro_traz_os_campos_da_spec_sem_o_nome_de_quem_assina_a_decisao(cliente):
    responses.post(PESQUISAR, json=_resposta([131], 1))
    r = cliente.processos("Nova Crixás", ano=2023)
    assert r["total"] == 1 and "total_e_piso" not in r
    assert r["registros"] == [{
        "numero": "00000131.2023.001.4.14838.0223", "municipio": "NOVA CRIXÁS", "codigo_ibge": "14838",
        "unidade_gestora": "FUNDO MUNICIPAL DE SAÚDE", "tipo": "Contas de Gestão", "ano_competencia": 2023,
        "mes_competencia": 12, "periodo_competencia": "Anual/2023", "relator": "CONSELHEIRO FICTÍCIO",
        "fase": "EM ANDAMENTO", "finalizado": False, "passo": "Análise técnica",
        "data_protocolo": "2024-04-30T10:00Z", "data_criacao": "2024-04-29T09:00Z",
        "data_ultima_tramitacao": "2024-09-01T12:00Z", "data_finalizacao": None,
        "decisoes": [{"nome": "Acórdão AC-CG 00123/24", "data": "2024-08-20T15:00Z"}],
        "envolvidos": [{"nome": "FULANO FICTÍCIO", "tipo_envolvimento": "Gestor", "tipo_pessoa": "FÍSICA"}],
        "fonte": "TCM-GO eSiproc"}]


@responses.activate
def test_pagina_e_deslocamento_e_os_repetidos_saem_pelo_numero(cliente):
    responses.post(PESQUISAR, json=_resposta(range(1, 11), 13))
    responses.post(PESQUISAR, json=_resposta([10, 11, 12, 13], 13))  # o 10 repete na virada da página
    r = cliente.processos("Nova Crixás", ano=2023)
    assert [c["pagina"] for c in _corpos()] == [0, 10]
    assert [x["numero"][:8] for x in r["registros"]] == [f"{n:08d}" for n in range(1, 14)]
    assert r["total"] == 13 and "incompleta" not in r


@responses.activate
def test_para_no_maximo_sem_ler_paginas_a_mais(cliente):
    responses.post(PESQUISAR, json=_resposta(range(1, 11), 126))
    r = cliente.processos("Nova Crixás", maximo=5)
    assert len(responses.calls) == 1 and len(r["registros"]) == 5 and r["total"] == 126
    assert "incompleta" not in r


@responses.activate
def test_pagina_vazia_antes_do_total_para_e_marca_leitura_incompleta(cliente):
    responses.post(PESQUISAR, json=_resposta(range(1, 11), 25))
    responses.post(PESQUISAR, json=_resposta([], 25))
    r = cliente.processos("Nova Crixás")
    assert len(responses.calls) == 2 and len(r["registros"]) == 10
    assert "antes do total" in r["incompleta"] and "vieram 10" in r["aviso_leitura"]


@responses.activate
def test_total_gte_e_dito_como_piso(cliente):
    responses.post(PESQUISAR, json=_resposta(range(1, 11), 10000, relation="gte"))
    r = cliente.processos("Nova Crixás", maximo=10)
    assert r["total"] == 10000 and r["total_e_piso"] is True
    assert "10000 ou mais" in r["aviso_total"]


def _lista_oficial(*nomes):
    responses.post(f"{tcm.FONTES['esiproc']['base']}/listar-campo", json={
        "took": 3, "timed_out": False, "_shards": {"total": 1, "successful": 1, "skipped": 0, "failed": 0},
        "hits": {"total": {"value": 10000, "relation": "gte"}, "hits": []},
        "aggregations": {"distinct": {"buckets": [{"key": n, "doc_count": 7} for n in nomes]}}})


@responses.activate
def test_zero_com_o_nome_conferido_na_lista_oficial_de_agora_e_resposta_valida(cliente):
    responses.post(PESQUISAR, json=_resposta([], 0))
    _lista_oficial("NOVA CRIXÁS", "POSSE")
    assert cliente.processos("Nova Crixás", ano=1990) == {"total": 0, "registros": [], "municipio_tcm": "NOVA CRIXÁS"}


@responses.activate
def test_zero_com_nome_que_mudou_na_fonte_repete_com_o_nome_oficial_de_agora(cliente):
    # ao vivo, o eSiproc responde total 0, em silêncio, a uma grafia que não conhece ("NOVA CRIXAS" 0 x 126)
    responses.post(PESQUISAR, json=_resposta([], 0))
    _lista_oficial("NOVA  CRIXAS", "POSSE")
    responses.post(PESQUISAR, json=_resposta([1, 2], 2))
    r = cliente.processos("Nova Crixás")
    assert r["total"] == 2 and r["municipio_tcm"] == "NOVA  CRIXAS"
    assert _corpos()[-1]["filtros"]["municipio.keyword"] == "NOVA  CRIXAS"


@responses.activate
def test_zero_com_municipio_que_saiu_da_lista_oficial_e_recusa_nunca_ausencia(cliente):
    responses.post(PESQUISAR, json=_resposta([], 0))
    _lista_oficial("POSSE")
    with pytest.raises(tcm.MunicipioNaoEncontrado):
        cliente.processos("Nova Crixás")


@responses.activate
def test_zero_por_numero_sem_municipio_nao_consulta_a_lista(cliente):
    responses.post(PESQUISAR, json=_resposta([], 0))
    assert cliente.processos(numero="00131/19")["total"] == 0 and len(responses.calls) == 1


@pytest.mark.parametrize("maximo", [0, -1])
def test_maximo_menor_que_um_e_recusado_sem_consultar(cliente, maximo):
    with pytest.raises(ValueError, match="maximo"):
        cliente.processos("Nova Crixás", maximo=maximo)


@pytest.mark.parametrize("resposta", [_resposta([1], 1, timed_out=True), _resposta([1], 1, falhas=1)],
                         ids=["timed_out", "shards_failed"])
@responses.activate
def test_resposta_incompleta_da_fonte_e_erro_nunca_lista(cliente, resposta):
    responses.post(PESQUISAR, json=resposta)
    with pytest.raises(ErroTCM, match="eSiproc.*incompleta"):
        cliente.processos("Nova Crixás")


@responses.activate
def test_formato_estranho_e_erro(cliente):
    responses.post(PESQUISAR, json={"mensagem": "ok"})
    with pytest.raises(ErroTCM, match="eSiproc.*formato"):
        cliente.processos("Nova Crixás")


@responses.activate
def test_teto_de_chamadas_devolve_o_lido_e_marca_leitura_incompleta(cliente):
    cliente.teto = 2
    responses.post(PESQUISAR, json=_resposta(range(1, 11), 30))
    responses.post(PESQUISAR, json=_resposta(range(11, 21), 30))
    r = cliente.processos("Nova Crixás")
    assert len(r["registros"]) == 20 and r["total"] == 30
    assert "teto" in r["incompleta"] and "incompleta" in r["aviso_leitura"]


@responses.activate
def test_teto_antes_do_primeiro_registro_e_erro_nunca_zero(cliente):
    cliente.teto = 0
    with pytest.raises(tcm.TetoAtingido):
        cliente.processos("Nova Crixás")


@responses.activate
def test_numero_nnnnn_aa_vira_filtro_contem_sem_municipio(cliente):
    responses.post(PESQUISAR, json=_resposta([131], 1))
    r = cliente.processos(numero="131/19")
    corpo = _corpos()[0]
    assert corpo["filtrosLike"] == {"numero.keyword": "00000131.2019"}
    assert all(v is None for v in corpo["filtros"].values())
    assert "municipio_tcm" not in r and r["total"] == 1


@responses.activate
def test_numero_e_municipio_se_somam(cliente):
    responses.post(PESQUISAR, json=_resposta([19439], 1))
    cliente.processos("Nova Crixás", numero="19439/23")
    corpo = _corpos()[0]
    assert corpo["filtrosLike"] == {"numero.keyword": "00019439.2023"}
    assert corpo["filtros"]["municipio.keyword"] == "NOVA CRIXÁS"


@pytest.mark.parametrize("numero", ["abc", "131", "123456/19", "131/2019/1"])
def test_numero_fora_do_formato_e_recusado_sem_consultar(cliente, numero):
    with pytest.raises(ValueError, match="NNNNN/AA"):
        cliente.processos(numero=numero)
