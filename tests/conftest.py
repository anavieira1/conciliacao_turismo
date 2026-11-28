"""Preparação comum aos testes da API.

Cada teste ganha um banco vazio. Por padrão é um SQLite em memória (não precisa
instalar nada). No GitHub Actions a variável TEST_DATABASE_URL aponta para um
PostgreSQL de verdade, então os mesmos testes rodam contra ele.
"""
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.banco import obter_sessao
from api.main import app
from api.tabelas import Base


@pytest.fixture
def engine_de_teste():
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        engine = create_engine(url)
    else:
        # Em memória, todas as conexões precisam ser a mesma, senão cada uma
        # enxergaria um banco vazio diferente.
        engine = create_engine("sqlite://", poolclass=StaticPool,
                               connect_args={"check_same_thread": False})
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def cliente(engine_de_teste):
    sessao_de_teste = sessionmaker(engine_de_teste)

    def obter_sessao_de_teste():
        with sessao_de_teste() as sessao:
            yield sessao

    app.dependency_overrides[obter_sessao] = obter_sessao_de_teste
    # Sem "with": o ciclo de vida da API (que cria tabelas no banco real) não roda.
    yield TestClient(app)
    app.dependency_overrides.clear()
