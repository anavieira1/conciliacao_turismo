"""Testes da prova da conciliação e da exportação."""
from decimal import Decimal
from pathlib import Path

import pytest

from conciliacao.leitura import ler_extrato, ler_sistema
from conciliacao.motor import conciliar
from conciliacao.relatorio import brl, calcular_prova, gerar_csv, mensagem_conferencia

DADOS = Path(__file__).parent.parent / "dados"
SALDO_INICIAL = Decimal("15000.00")
SALDO_FINAL_DO_BANCO = Decimal("32047.75")


@pytest.fixture
def exemplo():
    sistema = ler_sistema(DADOS / "lancamentos_sistema.csv")
    banco = ler_extrato(DADOS / "extrato_bancario.csv")
    return sistema, banco


def prova(sistema, banco, saldo_final=None):
    return calcular_prova(SALDO_INICIAL, sistema, banco, conciliar(sistema, banco), saldo_final)


def test_extrato_completo_passa_na_conferencia(exemplo):
    p = prova(*exemplo, SALDO_FINAL_DO_BANCO)
    assert p["diferenca_extrato"] == 0
    assert mensagem_conferencia(p)[0] == "ok"


def test_extrato_com_linhas_faltando_e_detectado(exemplo):
    # Antes: a prova comparava o arquivo com ele mesmo e dava "fechada" sempre.
    sistema, banco = exemplo
    p = prova(sistema, banco[:5], SALDO_FINAL_DO_BANCO)
    assert p["diferenca_extrato"] != 0
    nivel, texto = mensagem_conferencia(p)
    assert nivel == "erro"
    assert "Faltam linhas" in texto


def test_sem_saldo_final_informado_pede_o_dado_em_vez_de_aprovar(exemplo):
    p = prova(*exemplo)
    assert p["diferenca_extrato"] is None
    assert mensagem_conferencia(p)[0] == "aviso"


def test_extrato_ajustado_chega_ao_saldo_do_sistema(exemplo):
    p = prova(*exemplo, SALDO_FINAL_DO_BANCO)
    assert p["saldo_ajustado"] == p["saldo_sistema"]


@pytest.mark.parametrize("valor, esperado", [
    (Decimal("1234.5"), "R$ 1.234,50"),
    (Decimal("-89.9"), "-R$ 89,90"),
    (Decimal("0"), "R$ 0,00"),
])
def test_brl(valor, esperado):
    assert brl(valor) == esperado


def test_csv_exportado_abre_certo_no_excel_brasileiro(exemplo):
    sistema, banco = exemplo
    conteudo = gerar_csv(conciliar(sistema, banco))
    assert conteudo.startswith("﻿".encode())  # BOM: Excel reconhece UTF-8
    texto = conteudo.decode("utf-8-sig")
    assert texto.splitlines()[0].startswith("status;regra;")
    assert "4500,00" in texto
