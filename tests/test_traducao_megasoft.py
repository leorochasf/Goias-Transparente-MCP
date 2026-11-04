"""Tradução Megasoft → formato do projeto. Offline; exemplos montados à mão no formato medido em Aruanã (04/11/2026).

A Megasoft embutida e a de domínio próprio têm os mesmos campos. Na listagem da folha não há campo de tipo de
pagamento: em 12/2025 cada matrícula veio uma vez só; `situacao` é Ativo/Inativo/Pensionista e `situacaoPagamento`
é PAGO/NÃO PAGO.
"""
from transparencia_municipal.folha_leve import filtrar, linha_leve, resumir
from transparencia_municipal.traducao_megasoft import TIPO_PAGAMENTO, despesa, linha_da_folha


def _servidor(**campos):
    return {"ano": 2025, "mes": "12", "mesAno": "12/2025", "matricula": 1234, "nome": "PESSOA EXEMPLO",
            "cpf": "XXX.456.789-XX", "cargo": "AGENTE ADMINISTRATIVO", "dataAdmissao": "01/02/2021",
            "departamento": "SMS - SECRETARIA MUNICIPAL DE SAÚDE", "tipoDeVinculo": "Comissionado",
            "cargaHoraria": 220, "proventos": 3512.4, "descontos": 402.75, "totalLiquido": 3109.65,
            "situacao": "Ativo", "situacaoPagamento": "PAGO", "chave": {"matricula": 1234, "mes": 12, "ano": 2025},
            **campos}


def _empenho(**campos):
    return {"codigo": 1500, "data": "15/01/2025", "cnpjENomeDoFornecedor": "25.107.525/0001-51/EMPRESA EXEMPLO LTDA",
            "nomeDoFornecedor": "EMPRESA EXEMPLO LTDA", "historico": "AQUISIÇÃO DE MATERIAL DE EXPEDIENTE",
            "valorDoEmpenho": 12000.5, "valorDaAnulacaoDoEmpenho": 0, "valorTotalDoEmpenho": 12000.5,
            "valorDaLiquidacao": 8000, "valorDaAnulacaoDaLiquidacao": 0, "valorTotalDaLiquidacao": 8000,
            "valorDoPagamento": 8000, "valorAnulacaoDoPagamento": 0, "valorTotalDoPagamento": 8000,
            "tipoDoEmpenho": "Ordinário", "faseDoEmpenho": "Pago",
            "codigoENomeDoOrgao": "02 - FUNDO MUNICIPAL DE SAÚDE", **campos}


def test_folha_vira_linha_leve_com_os_campos_do_projeto_e_a_fonte():
    assert linha_leve(linha_da_folha(_servidor())) == {
        "nome": "PESSOA EXEMPLO", "matricula": "1234", "cpf": "XXX.456.789-XX", "cargo": "AGENTE ADMINISTRATIVO",
        "lotacao": "SMS - SECRETARIA MUNICIPAL DE SAÚDE", "vinculo": "Comissionado", "tipo_pagamento": TIPO_PAGAMENTO,
        "data_admissao": "01/02/2021", "data_demissao": None, "carga_horaria": 220,
        "bruto": "3.512,40", "descontos": "402,75", "liquido": "3.109,65", "orgao": None, "fonte": "Megasoft"}


def test_folha_guarda_ano_mes_e_a_situacao_do_pagamento():
    linha = linha_da_folha(_servidor(situacao="Inativo", situacaoPagamento="NÃO PAGO"))
    assert (linha["ano"], linha["mes"]) == (2025, "12")
    assert (linha["situacao"], linha["situacao_pagamento"]) == ("Inativo", "NÃO PAGO")


def test_13_e_rescisao_nao_vem_separados_e_o_tipo_diz_isso():
    """Medido (Aruanã, 11 e 12/2025): a listagem não traz o 13º, nem somado em dezembro, e a rescisão não vem
    separada. A exoneração aparece só como data de demissão."""
    assert "mensal" in TIPO_PAGAMENTO.lower() and "rescis" in TIPO_PAGAMENTO.lower()
    assert "não traz 13º" in TIPO_PAGAMENTO
    exonerado = linha_leve(linha_da_folha(_servidor(matricula=77, dataExoneracao="15/12/2025")))
    assert exonerado["data_demissao"] == "15/12/2025" and exonerado["tipo_pagamento"] == TIPO_PAGAMENTO


def test_resumo_e_filtro_funcionam_sobre_a_folha_traduzida():
    linhas = [linha_leve(linha_da_folha(_servidor(matricula=1))),
              linha_leve(linha_da_folha(_servidor(matricula=2, tipoDeVinculo="Concursado", proventos=1518,
                                                  descontos=113.85, totalLiquido=1404.15))),
              linha_leve(linha_da_folha(_servidor(matricula=3, departamento="SME - SECRETARIA DE EDUCAÇÃO")))]
    assert [x["matricula"] for x in filtrar(linhas, vinculo="comissionado", lotacao="saude")] == ["1"]
    r = resumir(linhas, "lotacao")
    assert r["fora_do_resumo"] == {}
    mensal = r["por_tipo_de_pagamento"][TIPO_PAGAMENTO]
    assert (mensal["linhas"], mensal["matriculas"], mensal["bruto"], mensal["liquido"]) == (3, 3, 8542.8, 7623.45)


def test_valor_vazio_fica_sem_valor_em_vez_de_zero():
    assert linha_leve(linha_da_folha(_servidor(proventos=None)))["bruto"] is None


def test_despesa_vira_cnpj_formatado_fornecedor_data_valores_e_fonte():
    assert despesa(_empenho()) == {
        "empenho": 1500, "data": "15/01/2025", "cpf_cnpj": "25.107.525/0001-51", "fornecedor": "EMPRESA EXEMPLO LTDA",
        "valor_empenhado": "12.000,50", "valor_liquidado": "8.000,00", "valor_pago": "8.000,00",
        "historico": "AQUISIÇÃO DE MATERIAL DE EXPEDIENTE", "orgao": "02 - FUNDO MUNICIPAL DE SAÚDE",
        "fonte": "Megasoft"}


def test_despesa_formata_o_cnpj_sem_pontuacao_e_acha_o_fornecedor_no_campo_composto():
    d = despesa(_empenho(cnpjENomeDoFornecedor="25107525000151/EMPRESA EXEMPLO LTDA", nomeDoFornecedor=None))
    assert (d["cpf_cnpj"], d["fornecedor"]) == ("25.107.525/0001-51", "EMPRESA EXEMPLO LTDA")


def test_despesa_com_cpf_mascarado_mantem_a_mascara():
    d = despesa(_empenho(cnpjENomeDoFornecedor="XXX.456.789-XX/CREDOR PESSOA FÍSICA", nomeDoFornecedor=None))
    assert (d["cpf_cnpj"], d["fornecedor"]) == ("XXX.456.789-XX", "CREDOR PESSOA FÍSICA")


def test_despesa_usa_os_totais_ja_descontada_a_anulacao():
    d = despesa(_empenho(valorDoEmpenho=1000, valorDaAnulacaoDoEmpenho=200, valorTotalDoEmpenho=800))
    assert d["valor_empenhado"] == "800,00"


def test_despesa_com_data_iso_vira_dd_mm_aaaa():
    assert despesa(_empenho(data="2025-01-15T00:00:00"))["data"] == "15/01/2025"
