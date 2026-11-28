"""API REST da conciliação bancária.

Rodar localmente:   uvicorn api.main:app --reload
Documentação:       http://localhost:8000/docs
"""
from __future__ import annotations

from collections import Counter
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from conciliacao.leitura import ErroDeArquivo, ler_extrato, ler_sistema
from conciliacao.modelos import Status
from conciliacao.motor import conciliar
from conciliacao.relatorio import calcular_prova, indice_conciliacao, mensagem_conferencia

from . import banco
from .esquemas import (
    Conciliacao, ConciliacaoResumo, Erro, ItemSaida, ResultadoConciliacao, codigo,
)
from .tabelas import Base, ConciliacaoSalva

LIMITE_BYTES = 10 * 1024 * 1024  # 10 MB por arquivo, igual ao app web
PARA_TRATAR = (Status.DIVERGENTE, Status.SO_NO_SISTEMA, Status.SO_NO_BANCO)

Sessao = Annotated[Session, Depends(banco.obter_sessao)]


@asynccontextmanager
async def ciclo_de_vida(_app: FastAPI) -> AsyncIterator[None]:
    # Cria a tabela se ainda não existir. Quando o esquema começar a mudar,
    # o próximo passo é trocar isto por migrações com Alembic.
    Base.metadata.create_all(banco.engine)
    yield


app = FastAPI(
    lifespan=ciclo_de_vida,
    title="API de Conciliação Bancária",
    version="1.0.0",
    description=(
        "Recebe os lançamentos do sistema financeiro e o extrato bancário em CSV "
        "(separados por `;`), casa cada item e explica cada diferença."
    ),
)


async def _ler_upload(arquivo: UploadFile, nome: str) -> bytes:
    conteudo = await arquivo.read(LIMITE_BYTES + 1)
    if len(conteudo) > LIMITE_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE,
                            f"{nome}: arquivo maior que 10 MB")
    return conteudo


@app.get("/saude", tags=["infra"])
def saude() -> dict[str, str]:
    """Usado por monitoramento e pelo Docker para saber se a API está no ar."""
    return {"status": "ok"}


@app.post(
    "/conciliacoes",
    response_model=Conciliacao,
    status_code=status.HTTP_201_CREATED,
    tags=["conciliação"],
    responses={
        413: {"model": Erro, "description": "Arquivo maior que 10 MB"},
        422: {"model": Erro, "description": "CSV fora do formato esperado"},
    },
)
async def criar_conciliacao(
    sessao: Sessao,
    resposta: Response,
    sistema:Annotated[UploadFile, File(description="Lançamentos do sistema (.csv)")],
    extrato: Annotated[UploadFile, File(description="Extrato bancário (.csv)")],
    # Os exemplos são os valores dos dados de exemplo. Sem eles, o Swagger
    # preenche os campos com 0 e envia "saldo final = 0" sem a pessoa perceber.
    saldo_inicial: Annotated[Decimal, Form(
        description="Saldo de abertura, igual no banco e no sistema", examples=["15000.00"])],
    saldo_final_extrato: Annotated[Decimal | None, Form(
        description="Saldo final impresso no extrato, para conferir se o arquivo está completo",
        examples=["32047.75"])] = None,
) -> Conciliacao:
    """Concilia os dois arquivos, guarda no histórico e devolve o resultado item a item."""
    conteudo_sistema = await _ler_upload(sistema, "sistema")
    conteudo_extrato = await _ler_upload(extrato, "extrato")

    # Cada arquivo é lido separado para o erro dizer qual deles está com problema.
    try:
        lanc_sistema = ler_sistema(conteudo_sistema)
    except ErroDeArquivo as erro:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"sistema: {erro}") from erro
    try:
        lanc_banco = ler_extrato(conteudo_extrato)
    except ErroDeArquivo as erro:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"extrato: {erro}") from erro

    itens = conciliar(lanc_sistema, lanc_banco)
    prova = calcular_prova(saldo_inicial, lanc_sistema, lanc_banco, itens, saldo_final_extrato)
    nivel, mensagem = mensagem_conferencia(prova)
    contagem = Counter(i.status for i in itens)

    resultado = ResultadoConciliacao(
        indice_conciliacao=indice_conciliacao(itens, len(lanc_sistema)).quantize(Decimal("0.0001")),
        resumo={codigo(s): contagem.get(s, 0) for s in Status},
        conferencia={"nivel": nivel, "mensagem": mensagem},
        prova=prova,
        itens=[ItemSaida.model_validate(i) for i in itens],
    )

    salva = ConciliacaoSalva(
        criada_em=datetime.now(timezone.utc),
        arquivo_sistema=(sistema.filename or "")[:255],
        arquivo_extrato=(extrato.filename or "")[:255],
        saldo_inicial=saldo_inicial,
        saldo_final_extrato=saldo_final_extrato,
        indice_conciliacao=resultado.indice_conciliacao,
        nivel_conferencia=nivel,
        itens_para_tratar=sum(contagem[s] for s in PARA_TRATAR),
        resultado=resultado.model_dump(mode="json"),
    )
    sessao.add(salva)
    sessao.commit()

    resposta.headers["Location"] = f"/conciliacoes/{salva.id}"
    return _montar(salva)


@app.get("/conciliacoes", response_model=list[ConciliacaoResumo], tags=["histórico"])
def listar_conciliacoes(
    sessao: Sessao,
    limite: Annotated[int, Query(ge=1, le=100, description="Quantas trazer")] = 20,
    inicio: Annotated[int, Query(ge=0, description="Quantas pular (paginação)")] = 0,
) -> list[ConciliacaoSalva]:
    """Histórico, da mais recente para a mais antiga, sem os itens."""
    consulta = (select(ConciliacaoSalva)
                .order_by(ConciliacaoSalva.id.desc())
                .limit(limite).offset(inicio))
    return list(sessao.scalars(consulta))


@app.get(
    "/conciliacoes/{conciliacao_id}",
    response_model=Conciliacao,
    tags=["histórico"],
    responses={404: {"model": Erro, "description": "Conciliação não encontrada"}},
)
def obter_conciliacao(conciliacao_id: int, sessao: Sessao) -> Conciliacao:
    """Uma conciliação do histórico, completa, como foi devolvida ao ser criada."""
    salva = sessao.get(ConciliacaoSalva, conciliacao_id)
    if salva is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conciliação não encontrada")
    return _montar(salva)


def _montar(salva: ConciliacaoSalva) -> Conciliacao:
    return Conciliacao.model_validate(
        {**salva.resultado, "id": salva.id, "criada_em": salva.criada_em})
