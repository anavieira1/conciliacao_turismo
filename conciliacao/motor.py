"""Motor de conciliação: casa lançamentos do sistema com o extrato.

Regras, aplicadas em ordem:
  1. Por DOCUMENTO (PIX/TED/boleto/cartão): chave forte.
       - valor igual                      -> CONCILIADO
       - venda no cartão, banco recebeu até
         TAXA_CARTAO_MAX a menos          -> CONCILIADO_TAXA (taxa da adquirente)
       - qualquer outra diferença         -> DIVERGENTE
  2. Por VALOR + DATA (para quem não tem documento): mesmo valor e
     data dentro de TOLERANCIA_DIAS; escolhe a data mais próxima.
  3. O que sobrou vira pendência (SO_NO_SISTEMA / SO_NO_BANCO).
"""
from __future__ import annotations

from decimal import Decimal

from .modelos import ItemConciliacao, LancamentoBanco, LancamentoSistema, Status

TOLERANCIA_DIAS = 3
TAXA_CARTAO_MAX = Decimal("0.05")  # 5%


def _eh_venda_cartao(s: LancamentoSistema) -> bool:
    return s.documento.upper().startswith("CART") and s.valor > 0


def _comparar_por_documento(s: LancamentoSistema, b: LancamentoBanco) -> ItemConciliacao:
    diferenca = b.valor - s.valor
    if diferenca == 0:
        return ItemConciliacao(Status.CONCILIADO, s, b, regra="documento")

    if _eh_venda_cartao(s) and diferenca < 0 and -diferenca <= s.valor * TAXA_CARTAO_MAX:
        taxa = -diferenca / s.valor
        return ItemConciliacao(
            Status.CONCILIADO_TAXA, s, b, regra="documento",
            observacao=f"Taxa da adquirente de {taxa:.2%} - lançar como despesa financeira",
        )

    return ItemConciliacao(
        Status.DIVERGENTE, s, b, regra="documento",
        observacao="Valor recebido/pago difere do registrado - verificar com cliente/fornecedor",
    )


def conciliar(
    sistema: list[LancamentoSistema], banco: list[LancamentoBanco]
) -> list[ItemConciliacao]:
    resultado: list[ItemConciliacao] = []
    banco_livre: dict[str, LancamentoBanco] = {b.id: b for b in banco}
    sistema_pendente: list[LancamentoSistema] = []

    # --- Regra 1: casamento por documento ---------------------------------
    banco_por_doc = {b.documento: b for b in banco if b.documento}
    for s in sistema:
        b = banco_por_doc.get(s.documento) if s.documento else None
        if b and b.id in banco_livre:
            resultado.append(_comparar_por_documento(s, b))
            del banco_livre[b.id]
        else:
            sistema_pendente.append(s)

    # --- Regra 2: casamento por valor + data aproximada ---------------------
    ainda_pendente: list[LancamentoSistema] = []
    for s in sistema_pendente:
        candidatos = [
            b for b in banco_livre.values()
            if b.valor == s.valor and abs((b.data - s.data).days) <= TOLERANCIA_DIAS
        ]
        if candidatos:
            b = min(candidatos, key=lambda b: abs((b.data - s.data).days))
            dias = (b.data - s.data).days
            resultado.append(ItemConciliacao(
                Status.CONCILIADO, s, b, regra="valor+data",
                observacao=f"Casado por valor; compensou {dias:+d} dia(s) depois" if dias else "Casado por valor",
            ))
            del banco_livre[b.id]
        else:
            ainda_pendente.append(s)

    # --- Regra 3: pendências -----------------------------------------------
    for s in ainda_pendente:
        obs = ("Recebimento ainda não compensado" if s.valor > 0
               else "Pagamento ainda não debitado (ex.: cheque em trânsito)")
        resultado.append(ItemConciliacao(Status.SO_NO_SISTEMA, sistema=s, observacao=obs))

    for b in banco_livre.values():
        obs = ("Crédito sem lançamento - identificar origem" if b.valor > 0
               else "Débito sem lançamento - registrar no sistema (tarifa/imposto?)")
        resultado.append(ItemConciliacao(Status.SO_NO_BANCO, banco=b, observacao=obs))

    return resultado
