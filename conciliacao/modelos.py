"""Estruturas de dados usadas na conciliação."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum


class Status(str, Enum):
    CONCILIADO = "Conciliado"
    CONCILIADO_TAXA = "Conciliado c/ taxa de cartão"
    DIVERGENTE = "Divergente (valor diferente)"
    SO_NO_SISTEMA = "Só no sistema"
    SO_NO_BANCO = "Só no extrato"


@dataclass(frozen=True)
class LancamentoSistema:
    """Lançamento registrado no sistema financeiro da agência."""
    id: str
    data: date
    descricao: str
    categoria: str
    valor: Decimal      # positivo = entrada, negativo = saída
    documento: str      # pode ser vazio


@dataclass(frozen=True)
class LancamentoBanco:
    """Linha do extrato bancário."""
    id: str
    data: date
    historico: str
    valor: Decimal      # positivo = crédito, negativo = débito
    documento: str      # pode ser vazio


@dataclass
class ItemConciliacao:
    """Resultado de uma tentativa de casamento entre sistema e banco."""
    status: Status
    sistema: LancamentoSistema | None = None
    banco: LancamentoBanco | None = None
    regra: str = ""
    observacao: str = ""

    @property
    def diferenca(self) -> Decimal:
        """Banco - Sistema (só faz sentido quando os dois lados existem)."""
        if self.sistema and self.banco:
            return self.banco.valor - self.sistema.valor
        return Decimal("0")
