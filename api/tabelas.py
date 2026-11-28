"""Tabela do histórico de conciliações (SQLAlchemy).

Cada conciliação é guardada como uma "foto": as colunas de resumo servem para
listar e filtrar, e o resultado completo fica em JSON (JSONB no PostgreSQL).
Uma conciliação já feita não muda, então não há por que espalhar cada item em
outra tabela só para remontá-lo depois.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, DateTime, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

Dinheiro = Numeric(14, 2)  # nunca float: R$ 0,10 + R$ 0,20 tem que dar R$ 0,30


class Base(DeclarativeBase):
    pass


class ConciliacaoSalva(Base):
    __tablename__ = "conciliacoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    arquivo_sistema: Mapped[str] = mapped_column(String(255))
    arquivo_extrato: Mapped[str] = mapped_column(String(255))
    saldo_inicial: Mapped[Decimal] = mapped_column(Dinheiro)
    saldo_final_extrato: Mapped[Decimal | None] = mapped_column(Dinheiro)
    indice_conciliacao: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    nivel_conferencia: Mapped[str] = mapped_column(String(10))
    itens_para_tratar: Mapped[int]
    resultado: Mapped[dict[str, Any]] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
