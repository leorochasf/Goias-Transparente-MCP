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
        else:
            todas = [x for x in todas if de <= "-".join(reversed(x["data"].split("/"))) <= ate]
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

    def diarias(self, de, ate, busca=None, *, maximo=200):
        todas = [{"data_saida": "10/01/2025"}] * 3 + [{"data_saida": "05/02/2025"}] * 2
        if "diarias_periodo" not in self.ignora:
            todas = [x for x in todas if de <= "-".join(reversed(x["data_saida"].split("/"))) <= ate]
        return self._r(todas)

    def contratos(self, ano=None, tipo="contrato", busca=None, *, maximo=200):
        todos = [{"ano": a} for a in (2024, 2025, 2025)]
        if ano and "contratos_ano" not in self.ignora:
            todos = [x for x in todos if x["ano"] == ano]
        return self._r(todos)

    def licitacoes(self, busca=None, *, dispensas=False, ano=None, maximo=200):
        todas = [{"data_publicacao": f"01/03/{a}"} for a in (2024, 2025)]
        if ano and "licitacoes_ano" not in self.ignora:
            todas = [x for x in todas if x["data_publicacao"].endswith(str(ano))]
        return self._r(todas)


def test_portal_que_respeita_tudo_sai_todo_ok():
    r = conferir(PortalDeMentira(), ano=2025, mes=1, hoje="2026-11-05", pausa=0)
    assert r["data"] == "2026-11-05" and r["referencia"] == "01/2025"
    assert r["filtros"] == {
        "folha_mes": "ok", "folha_orgaos": "ok", "despesas_periodo": "ok", "despesas_cnpj": "ok",
        "receitas_mes": "ok", "legislacao_tipo": "ok", "legislacao_ano": "ok",
        "diarias_periodo": "ok", "contratos_ano": "ok", "licitacoes_ano": "ok",
    }


def test_cada_filtro_ignorado_aparece_como_falhou_sem_derrubar_os_outros():
    ignorados = ("folha_mes", "despesas_periodo", "despesas_cnpj", "receitas_mes", "legislacao_ano",
                 "diarias_periodo", "contratos_ano", "licitacoes_ano")
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


def test_folha_de_outro_sistema_nao_sonda_orgaos_e_sai_sem_dados_com_nota():
    """A Megasoft não tem `orgao_id`: a sondagem de órgãos escondidos é do NucleoGov e não pode sair `falhou`."""
    class Megasoft(PortalDeMentira):
        def folha(self, ano, mes=None, busca=None, *, maximo=200):
            return self._r([{"ano": ano, "mes": f"{mes:02d}", "fonte": "Megasoft"}] * 5)

        def consultar(self, *a, **k):
            raise AssertionError("não sonda a API NucleoGov")
    r = conferir(Megasoft(), ano=2025, mes=1, hoje="x", pausa=0)
    assert r["filtros"]["folha_mes"] == "ok"
    assert r["filtros"]["folha_orgaos"] == "sem_dados" and "Megasoft" in r["detalhes"]["folha_orgaos"]


def test_despesas_sao_conferidas_no_mes_de_referencia():
    """A Centi devolve o período inteiro numa resposta só: a conferência pede um mês por vez."""
    pedidos = []

    class Registra(PortalDeMentira):
        def despesas(self, de, ate, busca=None, *, maximo=200):
            pedidos.append((de, ate))
            return super().despesas(de, ate, busca, maximo=maximo)
    r = conferir(Registra(), ano=2025, mes=2, hoje="x", pausa=0)
    assert set(pedidos) == {("2025-02-01", "2025-02-28")}
    assert r["filtros"]["despesas_periodo"] == "ok" and r["filtros"]["despesas_cnpj"] == "ok"


def test_folha_vazia_num_sistema_que_exige_o_mes_sai_sem_dados_e_nao_erro():
    """A Megasoft embutida recusa a folha sem mês (ValueError): sem o mês mais recente, não há o que conferir."""
    class ExigeMes(PortalDeMentira):
        def folha(self, ano, mes=None, busca=None, *, maximo=200):
            if mes is None:
                raise ValueError("informe o mês")
            return self._r([])
    r = conferir(ExigeMes(), ano=2025, mes=6, hoje="2026-11-05", pausa=0)
    assert r["filtros"]["folha_mes"] == "sem_dados"


def test_diarias_sao_conferidas_no_mes_de_referencia():
    pedidos = []

    class Registra(PortalDeMentira):
        def diarias(self, de, ate, busca=None, *, maximo=200):
            pedidos.append((de, ate, maximo))
            return super().diarias(de, ate, busca, maximo=maximo)
    r = conferir(Registra(), ano=2025, mes=2, hoje="x", pausa=0)
    assert pedidos == [("2025-02-01", "2025-02-28", 20)] and r["filtros"]["diarias_periodo"] == "ok"


def test_encaixe_que_recusa_o_filtro_ignorado_sai_falhou_e_nao_erro():
    """Os encaixes conferem o filtro e levantam ErroPortal ("fora do período", "de outro ano"): é o filtro que falhou."""
    from transparencia_municipal.cliente import ErroPortal

    class Guardado(PortalDeMentira):
        def diarias(self, *a, **k):
            raise ErroPortal("x devolveu 3 diárias com saída fora do período pedido: o recorte não foi respeitado")

        def contratos(self, ano=None, *a, **k):
            if ano:
                raise ErroPortal("x devolveu 2 contratos de outro ano ao pedir 2025: o filtro de ano não foi respeitado")
            return super().contratos(*a, **k)

        def receitas(self, *a, **k):
            raise ErroPortal("x devolveu receitas de outro mês (3 de 9 linhas) ao pedir 01/2025")
    r = conferir(Guardado(), ano=2025, mes=1, hoje="x", pausa=0)
    assert {k: r["filtros"][k] for k in ("diarias_periodo", "contratos_ano", "receitas_mes")} == {
        "diarias_periodo": "falhou", "contratos_ano": "falhou", "receitas_mes": "falhou"}
    assert "outro ano" in r["detalhes"]["contratos_ano"]


def test_licitacoes_sem_filtro_de_ano_medido_saem_nao_suportado():
    """Na API NucleoGov o `ano` das licitações é recusado (ValueError): não é erro do portal."""
    class NucleoGov(PortalDeMentira):
        def licitacoes(self, busca=None, *, dispensas=False, ano=None, maximo=200):
            if ano:
                raise ValueError("ano: o filtro de ano das licitações não foi medido nos portais NucleoGov")
            return super().licitacoes(maximo=maximo)
    r = conferir(NucleoGov(), ano=2025, mes=1, hoje="x", pausa=0)
    assert r["filtros"]["licitacoes_ano"] == "nao_suportado" and "não foi medido" in r["detalhes"]["licitacoes_ano"]


def test_ano_das_licitacoes_pelo_campo_ano_ou_pela_data_do_protocolo():
    """A embutida dá `ano` (o da licitação, que pode ter sido publicada no ano anterior); o Ortrel, sem publicação, o
    protocolo."""
    class Variado(PortalDeMentira):
        def licitacoes(self, busca=None, *, dispensas=False, ano=None, maximo=200):
            todas = [{"ano": 2025, "data_publicacao": "20/12/2024"}, {"data_protocolo": "02/01/2025"},
                     {"ano": 2024}]
            return self._r([x for x in todas if not ano or x.get("ano", 2025) == ano])
    assert conferir(Variado(), ano=2025, mes=1, hoje="x", pausa=0)["filtros"]["licitacoes_ano"] == "ok"


def test_contratos_de_um_ano_so_quando_todos_sao_de_um_ano_e_o_total_nao_diz_nada():
    """Se o total com ano não é menor que sem ano, mas todos os contratos do portal são daquele ano, não é falha."""
    class UmAnoSo(PortalDeMentira):
        def contratos(self, ano=None, tipo="contrato", busca=None, *, maximo=200):
            return self._r([{"ano": 2025}] * 3)
    assert conferir(UmAnoSo(), ano=2025, mes=1, hoje="x", pausa=0)["filtros"]["contratos_ano"] == "ok"


def test_contratos_com_total_igual_ao_sem_ano_e_anos_misturados_falham():
    class Ignora(PortalDeMentira):
        def contratos(self, ano=None, tipo="contrato", busca=None, *, maximo=200):
            todos = [{"ano": 2025}] * 20 + [{"ano": 2024}] * 5
            return {"total": 25, "registros": todos[:maximo] if ano else todos[-maximo:]}
    r = conferir(Ignora(), ano=2025, mes=1, hoje="x", pausa=0)
    assert r["filtros"]["contratos_ano"] == "falhou" and "não é menor" in r["detalhes"]["contratos_ano"]


def test_parametro_que_o_projeto_recusa_sai_nao_suportado():
    """O Ortrel só publica leis: o projeto recusa DECRETO (ValueError) antes de consultar; não é erro do portal."""
    class Ortrel(PortalDeMentira):
        def legislacao(self, *a, **k):
            raise ValueError("as câmaras Ortrel publicam só leis")
    r = conferir(Ortrel(), ano=2025, mes=1, hoje="x", pausa=0)
    assert r["filtros"]["legislacao_tipo"] == r["filtros"]["legislacao_ano"] == "nao_suportado"
    assert r["detalhes"]["legislacao_tipo"] == "as câmaras Ortrel publicam só leis"
