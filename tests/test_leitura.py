"""Testes da leitura dos CSVs de entrada."""
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from conciliacao.leitura import ErroDeArquivo, _data, _decimal, ler_extrato, ler_sistema

DADOS = Path(__file__).parent.parent / "dados"

CABECALHO_SISTEMA = "id;data;descricao;tipo;categoria;valor;documento\n"
CABECALHO_EXTRATO = "id;data;historico;valor;documento\n"


@pytest.mark.parametrize("texto, esperado", [
    ("1234.50", Decimal("1234.50")),
    ("1.234,50", Decimal("1234.50")),
    ("-89,90", Decimal("-89.90")),
    (" 720.00 ", Decimal("720.00")),
])
def test_decimal_aceita_formato_americano_e_brasileiro(texto, esperado):
    assert _decimal(texto) == esperado


@pytest.mark.parametrize("texto", ["2026-11-02", "02/11/2026"])
def test_data_aceita_iso_e_brasileiro(texto):
    assert _data(texto) == date(2026, 11, 2)


def test_despesa_do_sistema_vira_valor_negativo():
    csv = CABECALHO_SISTEMA + "S1;2026-11-04;Hotel;DESPESA;hotel;2800.00;TED-1\n"
    (lanc,) = ler_sistema(csv.encode())
    assert lanc.valor == Decimal("-2800.00")


def test_csv_salvo_pelo_excel_em_latin1_e_lido():
    csv = CABECALHO_SISTEMA + "S1;2026-11-08;Comissão;RECEITA;comissao;720,00;\n"
    (lanc,) = ler_sistema(csv.encode("latin-1"))
    assert lanc.descricao == "Comissão"
    assert lanc.valor == Decimal("720.00")


def test_coluna_ausente_gera_erro_de_arquivo():
    with pytest.raises(ErroDeArquivo, match="documento"):
        ler_extrato(b"id;data;historico;valor\nB1;2026-11-02;PIX;10.00\n")


def test_arquivos_de_exemplo_sao_lidos():
    assert len(ler_sistema(DADOS / "lancamentos_sistema.csv")) == 12
    assert len(ler_extrato(DADOS / "extrato_bancario.csv")) == 13
