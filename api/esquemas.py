"""Formatos de resposta da API (Pydantic).

Valores em dinheiro saem como texto ("4500.00"), não como número: JSON não tem
tipo decimal, e um float poderia virar 4499.999999. Quem consome a API converte
para o tipo decimal da sua linguagem.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from conciliacao.modelos import Status


class _DosDataclasses(BaseModel):
    # Permite montar a resposta direto dos objetos do motor (dataclasses).
    model_config = ConfigDict(from_attributes=True)


class LancamentoSistemaSaida(_DosDataclasses):
    id: str
    data: date
    descricao: str
    categoria: str
    valor: Decimal
    documento: str


class LancamentoBancoSaida(_DosDataclasses):
    id: str
    data: date
    historico: str
    valor: Decimal
    documento: str


def codigo(status: Status) -> str:
    """Status.SO_NO_BANCO -> 'so_no_banco'. Código estável para quem programa
    contra a API; o texto em português pode mudar sem quebrar ninguém."""
    return status.name.lower()


CodigoStatus = Literal[tuple(codigo(s) for s in Status)]


class ItemSaida(_DosDataclasses):
    status: CodigoStatus
    regra: str
    observacao: str
    diferenca: Decimal = Field(description="Banco menos sistema; zero quando falta um dos lados.")
    sistema: LancamentoSistemaSaida | None
    banco: LancamentoBancoSaida | None

    @field_validator("status", mode="before")
    @classmethod
    def _status_como_codigo(cls, status: Status | str) -> str:
        return codigo(status) if isinstance(status, Status) else status

    @computed_field(description="Situação em português, para mostrar na tela.")
    @property
    def status_descricao(self) -> str:
        return Status[self.status.upper()].value


class Prova(BaseModel):
    saldo_banco: Decimal
    so_sistema: Decimal
    so_banco: Decimal
    dif_casados: Decimal
    saldo_ajustado: Decimal
    saldo_sistema: Decimal
    saldo_final_informado: Decimal | None
    diferenca_extrato: Decimal | None


class Conferencia(BaseModel):
    nivel: str = Field(description="ok, erro ou aviso")
    mensagem: str


def _em_utc(momento: datetime) -> datetime:
    # O SQLite devolve a data sem fuso; tudo é gravado em UTC.
    return momento if momento.tzinfo else momento.replace(tzinfo=timezone.utc)


class ResultadoConciliacao(BaseModel):
    """O que o motor calculou. É isto que fica guardado em JSON no banco."""
    indice_conciliacao: Decimal = Field(description="De 0 a 1.")
    resumo: dict[str, int] = Field(description="Quantidade de itens por código de situação.")
    conferencia: Conferencia
    prova: Prova
    itens: list[ItemSaida]


class Conciliacao(ResultadoConciliacao):
    id: int
    criada_em: datetime

    _utc = field_validator("criada_em")(_em_utc)


class ConciliacaoResumo(BaseModel):
    """Uma linha da listagem do histórico, sem os itens."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    criada_em: datetime
    arquivo_sistema: str
    arquivo_extrato: str
    saldo_inicial: Decimal
    saldo_final_extrato: Decimal | None
    indice_conciliacao: Decimal
    nivel_conferencia: str = Field(description="ok, erro ou aviso")
    itens_para_tratar: int = Field(description="Divergentes + só no sistema + só no extrato.")

    _utc = field_validator("criada_em")(_em_utc)


class Erro(BaseModel):
    detail: str
