"""Folha leve: emagrecer, filtrar e resumir linhas da folha. Sem rede; exemplos e contas feitos à mão."""
import pytest

from transparencia_municipal.folha_leve import filtrar, linha_leve, resumir


def _linha(**campos):
    """Linha da folha no formato do portal (Senador Canedo, 04/11/2026), com nomes fictícios."""
    base = {
        "nome": "FULANO DE TAL", "matricula": "1001", "cpf": "***.123.456-**",
        "cargo": "ASSESSOR ESPECIAL", "lotacao": "SECRETARIA MUNICIPAL DE SAÚDE",
        "vinculo": "03 - COMISSIONADO", "tipo_folha": "Folha Mensal",
        "data_admissao": "2021-01-04", "data_demissao": None, "carga_horaria": 40,
        "total_proventos": "3.000,00", "total_desconto": "450,00", "total_liquido": "2.550,00",
        "orgao": "PREFEITURA MUNICIPAL", "orgao_id": 1, "codigo": "77", "registro": "x",
        "referencia": "Março/2025", "lotacao_codigo": "12", "vinculo_codigo": "03",
        "salario_base": None, "carga_horaria_mensal": 200, "ano": "2025", "mes": "03",
        "lista_proventos": [{"evento": "001", "nome": "VENCIMENTO", "valor": "2.500,00", "tipo": "Provento"},
                            {"evento": "120", "nome": "GRATIFICAÇÃO", "valor": "500,00", "tipo": "Provento"}],
        "lista_descontos": [{"evento": "900", "nome": "INSS", "valor": "450,00", "tipo": "Desconto"}],
        "eventos": [{"evento": "001", "nome": "VENCIMENTO", "valor": "2500.00", "tipo": "Provento"}],
    }
    return {**base, **campos}


def test_linha_leve_guarda_identificacao_e_valores_e_descarta_o_resto():
    assert linha_leve(_linha()) == {
        "nome": "FULANO DE TAL", "matricula": "1001", "cpf": "***.123.456-**",
        "cargo": "ASSESSOR ESPECIAL", "lotacao": "SECRETARIA MUNICIPAL DE SAÚDE",
        "vinculo": "03 - COMISSIONADO", "tipo_pagamento": "Folha Mensal",
        "data_admissao": "2021-01-04", "data_demissao": None, "carga_horaria": 40,
        "bruto": "3.000,00", "descontos": "450,00", "liquido": "2.550,00",
    }


def test_linha_leve_com_rubricas_traz_proventos_e_descontos_das_listas():
    leve = linha_leve(_linha(), rubricas=True)
    assert leve["rubricas"] == [
        {"codigo": "001", "nome": "VENCIMENTO", "valor": "2.500,00", "tipo": "Provento"},
        {"codigo": "120", "nome": "GRATIFICAÇÃO", "valor": "500,00", "tipo": "Provento"},
        {"codigo": "900", "nome": "INSS", "valor": "450,00", "tipo": "Desconto"},
    ]


def test_filtro_de_linhas_leves_contem_texto_sem_distinguir_maiuscula_nem_acento_e_combina():
    linhas = [
        linha_leve(_linha(matricula="1", vinculo="03 - COMISSIONADO", lotacao="SECRETARIA MUNICIPAL DE SAÚDE")),
        linha_leve(_linha(matricula="2", vinculo="28 - COMISSIONADO - SAUDE", lotacao="FUNDO MUNICIPAL DE SAUDE")),
        linha_leve(_linha(matricula="3", vinculo="18 - COMISSIONADO - SOCIAL", lotacao="SECRETARIA DE ASSISTÊNCIA SOCIAL")),
        linha_leve(_linha(matricula="4", vinculo="02 - Concursado", lotacao="SECRETARIA MUNICIPAL DE SAÚDE")),
    ]
    assert [x["matricula"] for x in filtrar(linhas, vinculo="comissionado")] == ["1", "2", "3"]
    assert [x["matricula"] for x in filtrar(linhas, vinculo="Comissionado", lotacao="saude")] == ["1", "2"]
    assert [x["matricula"] for x in filtrar(linhas, cargo="assessor", tipo_pagamento="mensal")] == ["1", "2", "3", "4"]
    assert filtrar(linhas, tipo_pagamento="13") == []
    assert filtrar(linhas) == linhas


def _mes_de_exemplo():
    """Contas à mão. Folha Mensal: SAÚDE 3.000,00 + 2.000,50 = 5.000,50 bruto (2.550,00 + 1.800,25 = 4.350,25
    líquido); EDUCAÇÃO 1.518,00 (1.357,35) e uma linha sem valor. A matrícula 1 também recebe 13º."""
    def leve(mat, lotacao, tipo, bruto, liquido):
        return linha_leve(_linha(matricula=mat, lotacao=lotacao, tipo_folha=tipo,
                                 total_proventos=bruto, total_liquido=liquido))
    return [
        leve("1", "SAÚDE", "Folha Mensal", "3.000,00", "2.550,00"),
        leve("1", "SAÚDE", "Fechamento 13º Salário", "1.500,00", "1.300,00"),
        leve("2", "SAÚDE", "Folha Mensal", "2.000,50", "1.800,25"),
        leve("3", "EDUCAÇÃO", "Folha Mensal", "1.518,00", "1.357,35"),
        leve("4", "EDUCAÇÃO", "Folha Mensal", None, ""),
        leve("5", "EDUCAÇÃO", "Rescisão", "900,00", "900,00"),
    ]


def test_resumo_soma_so_a_folha_mensal_e_conta_os_outros_tipos_a_parte():
    assert resumir(_mes_de_exemplo(), "lotacao") == {
        "agrupar_por": "lotacao",
        "por_tipo_de_pagamento": {
            "Folha Mensal": {
                "linhas": 4, "matriculas": 4, "bruto": 6518.50, "liquido": 5707.60,
                "grupos": [
                    {"grupo": "SAÚDE", "linhas": 2, "matriculas": 2, "bruto": 5000.50, "liquido": 4350.25},
                    {"grupo": "EDUCAÇÃO", "linhas": 2, "matriculas": 2, "bruto": 1518.00, "liquido": 1357.35},
                ],
            },
        },
        "linhas_sem_valor": 1,
        "fora_do_resumo": {"Fechamento 13º Salário": 1, "Rescisão": 1},
    }


def test_resumo_com_todos_os_tipos_separa_cada_tipo_e_nao_soma_13_ao_salario():
    r = resumir(_mes_de_exemplo(), "lotacao", todos_os_tipos=True)
    assert list(r["por_tipo_de_pagamento"]) == ["Folha Mensal", "Fechamento 13º Salário", "Rescisão"]
    assert r["por_tipo_de_pagamento"]["Folha Mensal"]["bruto"] == 6518.50
    decimo = r["por_tipo_de_pagamento"]["Fechamento 13º Salário"]
    assert (decimo["linhas"], decimo["matriculas"], decimo["bruto"]) == (1, 1, 1500.00)
    assert r["fora_do_resumo"] == {}


def test_resumo_recusa_agrupamento_desconhecido_listando_as_opcoes():
    with pytest.raises(ValueError, match="cargo, lotacao ou vinculo"):
        resumir(_mes_de_exemplo(), "secretaria")
