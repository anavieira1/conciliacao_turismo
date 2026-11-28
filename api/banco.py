"""Conexão com o banco de dados onde fica o histórico das conciliações.

O endereço do banco vem da variável de ambiente DATABASE_URL, por exemplo:
    postgresql+psycopg://usuario:senha@localhost:5432/conciliacao

Sem ela, a API usa um arquivo SQLite em saida/historico.db, para rodar no
computador sem instalar nada. O código é o mesmo para os dois bancos.
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

ARQUIVO_SQLITE = Path(__file__).parent.parent / "saida" / "historico.db"


def criar_engine(url: str | None = None) -> Engine:
    url = url or os.environ.get("DATABASE_URL") or f"sqlite:///{ARQUIVO_SQLITE.as_posix()}"
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    # pool_pre_ping: testa a conexão antes de usar (o PostgreSQL pode ter reiniciado).
    return create_engine(url, pool_pre_ping=True)


engine = criar_engine()
SessaoLocal = sessionmaker(engine)


def obter_sessao() -> Iterator[Session]:
    """Uma sessão por requisição; o FastAPI fecha no fim. Os testes trocam esta
    função por outra que aponta para um banco de teste."""
    with SessaoLocal() as sessao:
        yield sessao
