"""Testes das regras de casamento do motor de conciliação."""
from datetime import date
from decimal import Decimal

from conciliacao.modelos import LancamentoBanco, LancamentoSistema, Status
from conciliacao.motor import conciliar


def sis(id, valor, documento="", dia=10):
    return LancamentoSistema(id, date(2026, 11, dia), f"lançamento {id}", "teste",
                             Decimal(valor), documento)


def banco(id, valor, documento="", dia=10):
    return LancamentoBanco(id, date(2026, 11, dia), f"histórico {id}", Decimal(valor), documento)


def unico(itens):
    assert len(itens) == 1
    return itens[0]


# --- Regra 1: documento -------------------------------------------------------

def test_mesmo_documento_e_mesmo_valor_concilia():
    item = unico(conciliar([sis("S1", "4500.00", "PIX-1")], [banco("B1", "4500.00", "PIX-1")]))
    assert item.status == Status.CONCILIADO
    assert item.regra == "documento"
    assert item.diferenca == 0


def test_venda_no_cartao_com_desconto_ate_5_porcento_e_taxa_da_adquirente():
    item = unico(conciliar([sis("S1", "6200.00", "CART-1")], [banco("B1", "6014.00", "CART-1")]))
    assert item.status == Status.CONCILIADO_TAXA
    assert item.diferenca == Decimal("-186.00")
    assert "3,00%" in item.observacao.replace(".", ",")


def test_venda_no_cartao_com_desconto_acima_de_5_porcento_e_divergente():
    item = unico(conciliar([sis("S1", "1000.00", "CART-1")], [banco("B1", "940.00", "CART-1")]))
    assert item.status == Status.DIVERGENTE


def test_pix_com_valor_diferente_e_divergente_mesmo_com_diferenca_pequena():
    item = unico(conciliar([sis("S1", "980.00", "PIX-5")], [banco("B1", "890.00", "PIX-5")]))
    assert item.status == Status.DIVERGENTE
    assert item.diferenca == Decimal("-90.00")


# --- Regra 2: valor + data ----------------------------------------------------

def test_sem_documento_casa_por_valor_dentro_da_tolerancia_de_dias():
    item = unico(conciliar([sis("S1", "-450.00", dia=10)], [banco("B1", "-450.00", dia=13)]))
    assert item.status == Status.CONCILIADO
    assert item.regra == "valor+data"
    assert "+3 dia" in item.observacao


def test_sem_documento_fora_da_tolerancia_vira_pendencia_dos_dois_lados():
    itens = conciliar([sis("S1", "-450.00", dia=10)], [banco("B1", "-450.00", dia=14)])
    assert {i.status for i in itens} == {Status.SO_NO_SISTEMA, Status.SO_NO_BANCO}


def test_entre_dois_candidatos_escolhe_a_data_mais_proxima():
    itens = conciliar(
        [sis("S1", "100.00", dia=10)],
        [banco("B_longe", "100.00", dia=12), banco("B_perto", "100.00", dia=11)],
    )
    casado = next(i for i in itens if i.sistema)
    assert casado.banco.id == "B_perto"


# --- Regra 3: pendências -----------------------------------------------------

def test_pendencias_recebem_a_observacao_certa():
    itens = conciliar(
        [sis("S1", "5300.00", "BOL-9"), sis("S2", "-610.00", "CHQ-1")],
        [banco("B1", "-89.90"), banco("B2", "1200.00")],
    )
    obs = {(i.sistema or i.banco).id: i.observacao for i in itens}
    assert "não compensado" in obs["S1"]
    assert "cheque" in obs["S2"]
    assert "tarifa" in obs["B1"]
    assert "identificar origem" in obs["B2"]


def test_nenhum_lancamento_se_perde_e_nenhum_e_usado_duas_vezes():
    sistema = [sis("S1", "100.00", "PIX-1"), sis("S2", "100.00"), sis("S3", "50.00")]
    extrato = [banco("B1", "100.00", "PIX-1"), banco("B2", "100.00"), banco("B3", "70.00")]
    itens = conciliar(sistema, extrato)

    ids_sis = [i.sistema.id for i in itens if i.sistema]
    ids_banco = [i.banco.id for i in itens if i.banco]
    assert sorted(ids_sis) == ["S1", "S2", "S3"]
    assert sorted(ids_banco) == ["B1", "B2", "B3"]
