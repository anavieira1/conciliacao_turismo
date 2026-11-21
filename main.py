"""Ponto de entrada: python main.py"""
import sys
from decimal import Decimal
from pathlib import Path

from conciliacao.leitura import ler_extrato, ler_sistema
from conciliacao.motor import conciliar
from conciliacao.relatorio import exportar_csv, imprimir

BASE = Path(__file__).parent
EMPRESA = "Horizonte Viagens & Turismo"
PERIODO = "01/11/2026 a 20/11/2026"
SALDO_INICIAL = Decimal("15000.00")  # mesmo saldo de abertura no banco e no sistema


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # acentos no terminal do Windows

    sistema = ler_sistema(BASE / "dados" / "lancamentos_sistema.csv")
    banco = ler_extrato(BASE / "dados" / "extrato_bancario.csv")

    itens = conciliar(sistema, banco)

    imprimir(EMPRESA, PERIODO, SALDO_INICIAL, sistema, banco, itens)
    saida = BASE / "saida" / "resultado_conciliacao.csv"
    exportar_csv(itens, saida)
    print(f"\nResultado detalhado exportado em: {saida.relative_to(BASE)}")


if __name__ == "__main__":
    main()
