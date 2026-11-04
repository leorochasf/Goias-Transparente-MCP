"""TCMJuris do TCM-GO REAL: a busca respeita município e assunto, e o PDF de um acórdão vira texto.

Desligado por padrão; liga com `TRANSPARENCIA_AO_VIVO=1 pytest -m ao_vivo`. Duas consultas, com pausa de 1 s.
As asserções comparam só campos de filtro e o PDF, nem quando falham: nada de nome de pessoa sai na tela.
"""
import os

import pytest

from transparencia_municipal.tcm import ClienteTCM

pytestmark = [
    pytest.mark.ao_vivo,
    pytest.mark.skipif(os.environ.get("TRANSPARENCIA_AO_VIVO") != "1",
                       reason="consulta o TCM-GO real; ligue com TRANSPARENCIA_AO_VIVO=1"),
]

ASSUNTO = "Balancete Semestral"  # Caldazinha tinha 33 acórdãos desse assunto em 04/11/2026


def test_caldazinha_responde_acordaos_de_um_assunto_e_um_deles_e_lido_em_texto():
    cliente = ClienteTCM()
    # só valores derivados nas asserções: ao falhar, o pytest mostraria o registro ou o texto, com nomes de pessoas
    r = cliente.acordaos("Caldazinha", assunto=ASSUNTO, maximo=5)
    nome, total, n = r["municipio_tcm"], r["total"], len(r["registros"])
    assert nome == "CALDAZINHA" and total > 0 and n > 0
    assuntos = {x["assunto"] for x in r["registros"]}
    do_municipio = all("CALDAZINHA" in x["entidade_fiscalizada"].upper() for x in r["registros"])
    completos = all(x["ano"] >= 2020 and x["document_id"] and x["ementa_ia"] and x["fonte"] == "TCM-GO TCMJuris"
                    for x in r["registros"])
    assert assuntos == {ASSUNTO} and do_municipio and completos

    lido = cliente.ler_acordao(r["registros"][0]["document_id"])
    texto = lido["registros"][0]["texto"].lower()
    sem_aviso, tamanho = "aviso_texto" not in lido, len(texto)
    cita_tribunal, cita_municipio = "tribunal de contas dos munic" in texto, "caldazinha" in texto
    assert sem_aviso and tamanho > 1000
    assert cita_tribunal and cita_municipio
