"""Conferência: a rotina que mede se um portal respeita cada filtro. Offline, com um portal de mentira."""
from transparencia_municipal.conferencia import conferir

CNPJ_A, CNPJ_B = "11.111.111/0001-11", "22.222.222/0001-22"


class PortalDeMentira:
    """Respeita todos os filtros, salvo os listados em `ignora`. A folha tem os órgãos 001 e 002."""

    def __init__(self, ignora=(), folha_so_orgao_1=False):
        self.ignora, self.folha_so_orgao_1 = set(ignora), folha_so_orgao_1

    def _r(self, registros):
        return {"total": len(registros), "registros": registros[:20]}

    def folha(self, ano, mes=None, busca=None, *, maximo=200):
        mes_dado = mes if "folha_mes" not in self.ignora else 12
        linhas = [{"ano": str(ano), "mes": f"{mes_dado:02d}", "orgao_id": o} for o in ("001",) * 30 + ("002",) * 10]
        return self._r([x for x in linhas if not (self.folha_so_orgao_1 and x["orgao_id"] != "001")])

    def consultar(self, acao, filtros=None, *, maximo=200):
        assert acao.startswith("servidores_")
        orgao = filtros["orgao"]
        return self._r([{"orgao_id": orgao}] * {"001": 30, "002": 10}.get(orgao, 0))

    def despesas(self, de, ate, busca=None, *, maximo=200):
        todas = [{"data": "15/01/2025", "cpf_cnpj": CNPJ_A}] * 5 + [{"data": "20/02/2025", "cpf_cnpj": CNPJ_B}] * 3
        if "despesas_periodo" in self.ignora:
            todas += [{"data": "10/10/2026", "cpf_cnpj": CNPJ_B}]
        if busca and "despesas_cnpj" not in self.ignora:
            todas = [x for x in todas if x["cpf_cnpj"] == busca]
        return self._r(todas)

    def receitas(self, ano, mes, *, maximo=200):
        mes_dado = mes if "receitas_mes" not in self.ignora else 11
        return self._r([{"ano": str(ano), "mes": str(mes_dado)}] * 4)

    def legislacao(self, tipo="DECRETO", busca=None, *, ano=None, maximo=200):
        codigo = {"DECRETO": "1", "PORTARIA": "2"}[tipo]
        atos = [{"tipo": codigo, "ano": a} for a in ("2024", "2025", "2025")]
        if ano and "legislacao_ano" not in self.ignora:
            atos = [x for x in atos if x["ano"] == str(ano)]
        return self._r(atos)


def test_portal_que_respeita_tudo_sai_todo_ok():
    r = conferir(PortalDeMentira(), ano=2025, mes=1, hoje="2026-11-05", pausa=0)
    assert r["data"] == "2026-11-05" and r["referencia"] == "01/2025"
    assert r["filtros"] == {
        "folha_mes": "ok", "folha_orgaos": "ok", "despesas_periodo": "ok", "despesas_cnpj": "ok",
        "receitas_mes": "ok", "legislacao_tipo": "ok", "legislacao_ano": "ok",
    }


def test_cada_filtro_ignorado_aparece_como_falhou_sem_derrubar_os_outros():
    ignorados = ("folha_mes", "despesas_periodo", "despesas_cnpj", "receitas_mes", "legislacao_ano")
    r = conferir(PortalDeMentira(ignora=ignorados), ano=2025, mes=1, hoje="2026-11-05", pausa=0)
    assert {k for k, v in r["filtros"].items() if v == "falhou"} == set(ignorados)
    assert r["filtros"]["legislacao_tipo"] == "ok"


def test_folha_sem_filtro_que_esconde_um_orgao_falha():
    r = conferir(PortalDeMentira(folha_so_orgao_1=True), ano=2025, mes=1, hoje="2026-11-05", pausa=0)
    assert r["filtros"]["folha_orgaos"] == "falhou"
    assert "002" in r["detalhes"]["folha_orgaos"]


def test_modulo_que_quebra_vira_erro_e_os_outros_seguem():
    class Quebrado(PortalDeMentira):
        def receitas(self, *a, **k):
            raise RuntimeError("portal fora do ar")
    r = conferir(Quebrado(), ano=2025, mes=1, hoje="2026-11-05", pausa=0)
    assert r["filtros"]["receitas_mes"] == "erro" and "fora do ar" in r["detalhes"]["receitas_mes"]
    assert r["filtros"]["folha_mes"] == "ok"


def test_folha_vazia_no_mes_pedido_e_conferida_no_mes_mais_recente_publicado():
    class SoMesCorrente(PortalDeMentira):
        def folha(self, ano, mes=None, busca=None, *, maximo=200):
            if mes not in (None, 10) or ano != 2026:
                return self._r([])
            return self._r([{"ano": "2026", "mes": "10", "orgao_id": o} for o in ("001",) * 30 + ("002",) * 10])
    r = conferir(SoMesCorrente(), ano=2025, mes=6, hoje="2026-11-05", pausa=0)
    assert r["filtros"]["folha_mes"] == "ok" and r["filtros"]["folha_orgaos"] == "ok"
    assert "10/2026" in r["detalhes"]["folha_mes"]


def test_legislacao_sem_campo_ano_usa_a_data_de_publicacao():
    class SemAno(PortalDeMentira):
        def legislacao(self, tipo="DECRETO", busca=None, *, ano=None, maximo=200):
            codigo = {"DECRETO": "1", "PORTARIA": "2"}[tipo]
            atos = [{"tipo": codigo, "data_publicacao": d} for d in ("2024-05-02", "2025-07-29", "2025-08-01")]
            return self._r([x for x in atos if not ano or x["data_publicacao"].startswith(str(ano))])
    assert conferir(SemAno(), ano=2025, mes=1, hoje="x", pausa=0)["filtros"]["legislacao_ano"] == "ok"


def test_modulo_de_outra_plataforma_sai_como_nao_suportado():
    from transparencia_municipal.cliente import ModuloNaoSuportado

    class ComCenti(PortalDeMentira):
        def receitas(self, *a, **k):
            raise ModuloNaoSuportado("o módulo receitas vem da contabilidade Centi")
    r = conferir(ComCenti(), ano=2025, mes=1, hoje="x", pausa=0)
    assert r["filtros"]["receitas_mes"] == "nao_suportado" and "Centi" in r["detalhes"]["receitas_mes"]
