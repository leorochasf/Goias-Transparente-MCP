"""TCMJuris do TCM-GO REAL: a busca respeita município e assunto, e o PDF de um acórdão vira texto.

Desligado por padrão; liga com `TRANSPARENCIA_AO_VIVO=1 pytest -m ao_vivo`. Duas consultas, com pausa de 1 s.
As asserções comparam só campos de filtro e o começo do PDF: nada de nome de pessoa sai na tela.
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
    r = cliente.acordaos("Caldazinha", assunto=ASSUNTO, maximo=5)
    assert r["municipio_tcm"] == "CALDAZINHA" and r["total"] > 0 and r["registros"]
    for x in r["registros"]:
        assert x["assunto"] == ASSUNTO and "CALDAZINHA" in x["entidade_fiscalizada"].upper()
        assert x["ano"] >= 2020 and x["document_id"] and x["ementa_ia"] and x["fonte"] == "TCM-GO TCMJuris"

    lido = cliente.ler_acordao(r["registros"][0]["document_id"])
    texto = lido["registros"][0]["texto"]
    assert "aviso_texto" not in lido and len(texto) > 1000
    assert "tribunal de contas dos munic" in texto.lower() and "caldazinha" in texto.lower()
