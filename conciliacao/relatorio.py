"""Relatório no terminal + exportação CSV do resultado."""
from __future__ import annotations

import csv
import io
from collections import Counter
from decimal import Decimal
from pathlib import Path

from .modelos import ItemConciliacao, LancamentoBanco, LancamentoSistema, Status

LARGURA = 100


def brl(valor: Decimal) -> str:
    """Formata 1234.5 -> 'R$ 1.234,50' (sem depender de locale do SO)."""
    texto = f"{abs(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{'-' if valor < 0 else ''}R$ {texto}"


def _titulo(texto: str) -> None:
    print("\n" + "=" * LARGURA)
    print(texto)
    print("=" * LARGURA)


def calcular_prova(
    saldo_inicial: Decimal,
    sistema: list[LancamentoSistema],
    banco: list[LancamentoBanco],
    itens: list[ItemConciliacao],
) -> dict[str, Decimal]:
    """Parte do saldo do banco e chega ao saldo do sistema explicando cada diferença."""
    so_sistema = sum((i.sistema.valor for i in itens if i.status == Status.SO_NO_SISTEMA), Decimal(0))
    so_banco = sum((i.banco.valor for i in itens if i.status == Status.SO_NO_BANCO), Decimal(0))
    dif_casados = sum((i.diferenca for i in itens if i.sistema and i.banco), Decimal(0))

    saldo_banco = saldo_inicial + sum((b.valor for b in banco), Decimal(0))
    saldo_sistema = saldo_inicial + sum((s.valor for s in sistema), Decimal(0))
    saldo_ajustado = saldo_banco + so_sistema - so_banco - dif_casados

    return {
        "saldo_banco": saldo_banco,
        "so_sistema": so_sistema,
        "so_banco": so_banco,
        "dif_casados": dif_casados,
        "saldo_ajustado": saldo_ajustado,
        "saldo_sistema": saldo_sistema,
        "diferenca_final": saldo_ajustado - saldo_sistema,
    }


def imprimir(empresa: str, periodo: str, saldo_inicial: Decimal,
             sistema, banco, itens: list[ItemConciliacao]) -> None:
    _titulo(f"CONCILIAÇÃO BANCÁRIA - {empresa}  |  Período: {periodo}")

    # Resumo por status
    contagem = Counter(i.status for i in itens)
    print("\nRESUMO")
    for status in Status:
        print(f"  {status.value:<32} {contagem.get(status, 0):>3} item(ns)")
    total_sis = len(sistema)
    casados = sum(1 for i in itens if i.sistema and i.banco)
    print(f"  {'Índice de conciliação':<32} {casados / total_sis:>7.1%} dos lançamentos do sistema")

    # Detalhe
    _titulo("DETALHE")
    cab = f"{'Status':<29}{'Sist.':<6}{'Banco':<6}{'Data':<12}{'Descrição':<33}{'Valor':>14}"
    print(cab)
    print("-" * LARGURA)
    for i in sorted(itens, key=lambda i: list(Status).index(i.status)):
        ref = i.sistema or i.banco
        desc = i.sistema.descricao if i.sistema else i.banco.historico
        print(f"{i.status.value:<29}"
              f"{(i.sistema.id if i.sistema else '-'):<6}"
              f"{(i.banco.id if i.banco else '-'):<6}"
              f"{ref.data.strftime('%d/%m/%Y'):<12}"
              f"{desc[:31]:<33}"
              f"{brl(ref.valor):>14}")
        if i.diferenca:
            print(f"{'':<29}↳ diferença banco - sistema: {brl(i.diferenca)}")
        if i.observacao:
            print(f"{'':<29}↳ {i.observacao}")

    # Prova da conciliação
    p = calcular_prova(saldo_inicial, sistema, banco, itens)
    _titulo("PROVA DA CONCILIAÇÃO (do saldo do banco ao saldo do sistema)")
    linhas = [
        ("Saldo final segundo o EXTRATO", p["saldo_banco"]),
        ("(+) Lançamentos só no sistema (a compensar)", p["so_sistema"]),
        ("(-) Lançamentos só no extrato (a registrar)", -p["so_banco"]),
        ("(-) Diferenças em itens casados (taxas/diverg.)", -p["dif_casados"]),
        ("(=) Saldo do extrato ajustado", p["saldo_ajustado"]),
        ("Saldo final segundo o SISTEMA", p["saldo_sistema"]),
        ("Diferença não explicada", p["diferenca_final"]),
    ]
    for rotulo, valor in linhas:
        print(f"  {rotulo:<55}{brl(valor):>18}")
    ok = p["diferenca_final"] == 0
    print("\n  " + ("✔ Conciliação fechada: todas as diferenças estão explicadas."
                    if ok else "✘ ATENÇÃO: existe diferença não explicada!"))


def linhas_resultado(itens: list[ItemConciliacao]) -> list[dict[str, object]]:
    """Uma linha por item - usada no CSV e na tabela do app web."""
    linhas = []
    for i in sorted(itens, key=lambda i: list(Status).index(i.status)):
        s, b = i.sistema, i.banco
        linhas.append({
            "status": i.status.value,
            "regra": i.regra,
            "id_sistema": s.id if s else "",
            "id_banco": b.id if b else "",
            "data_sistema": s.data.strftime("%d/%m/%Y") if s else "",
            "data_banco": b.data.strftime("%d/%m/%Y") if b else "",
            "descricao_sistema": s.descricao if s else "",
            "historico_banco": b.historico if b else "",
            "valor_sistema": float(s.valor) if s else None,
            "valor_banco": float(b.valor) if b else None,
            "diferenca": float(i.diferenca),
            "observacao": i.observacao,
        })
    return linhas


def gerar_csv(itens: list[ItemConciliacao]) -> bytes:
    """CSV em ';' com vírgula decimal e BOM, para abrir certo no Excel brasileiro."""
    buffer = io.StringIO()
    linhas = linhas_resultado(itens)
    w = csv.DictWriter(buffer, fieldnames=list(linhas[0].keys()) if linhas else [], delimiter=";")
    w.writeheader()
    for linha in linhas:
        w.writerow({k: (f"{v:.2f}".replace(".", ",") if isinstance(v, float) else v)
                    for k, v in linha.items()})
    return buffer.getvalue().encode("utf-8-sig")


def exportar_csv(itens: list[ItemConciliacao], caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(gerar_csv(itens))
