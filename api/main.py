"""API REST da conciliação bancária.

Rodar localmente:   uvicorn api.main:app --reload
Documentação:       http://localhost:8000/docs
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status

from conciliacao.leitura import ErroDeArquivo, ler_extrato, ler_sistema
from conciliacao.modelos import Status
from conciliacao.motor import conciliar
from conciliacao.relatorio import calcular_prova, indice_conciliacao, mensagem_conferencia

from .esquemas import Conciliacao, Erro, ItemSaida, codigo

LIMITE_BYTES = 10 * 1024 * 1024  # 10 MB por arquivo, igual ao app web

app = FastAPI(
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
    tags=["conciliação"],
    responses={
        413: {"model": Erro, "description": "Arquivo maior que 10 MB"},
        422: {"model": Erro, "description": "CSV fora do formato esperado"},
    },
)
async def criar_conciliacao(
    sistema: Annotated[UploadFile, File(description="Lançamentos do sistema (.csv)")],
    extrato: Annotated[UploadFile, File(description="Extrato bancário (.csv)")],
    saldo_inicial: Annotated[Decimal, Form(description="Saldo de abertura, igual no banco e no sistema")],
    saldo_final_extrato: Annotated[
        Decimal | None, Form(description="Saldo final impresso no extrato, para conferir se o arquivo está completo")
    ] = None,
) -> Conciliacao:
    """Concilia os dois arquivos e devolve o resultado item a item."""
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

    return Conciliacao(
        indice_conciliacao=indice_conciliacao(itens, len(lanc_sistema)).quantize(Decimal("0.0001")),
        resumo={codigo(s): contagem.get(s, 0) for s in Status},
        conferencia={"nivel": nivel, "mensagem": mensagem},
        prova=prova,
        itens=[ItemSaida.model_validate(i) for i in itens],
    )
