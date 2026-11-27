"""Leitura dos arquivos CSV de entrada."""
from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, TypeVar, Union

from .modelos import LancamentoBanco, LancamentoSistema

# Aceita um caminho no disco (uso pelo terminal) ou o conteúdo em bytes
# de um arquivo enviado pelo navegador (uso pelo app web).
Fonte = Union[Path, bytes]

COLUNAS_SISTEMA = {"id", "data", "descricao", "tipo", "categoria", "valor", "documento"}
COLUNAS_EXTRATO = {"id", "data", "historico", "valor", "documento"}


class ErroDeArquivo(ValueError):
    """Arquivo de entrada fora do formato esperado."""


def _ler_csv(fonte: Fonte, colunas: set[str]) -> list[dict[str, str]]:
    if isinstance(fonte, Path):
        texto = fonte.read_text(encoding="utf-8-sig")
    else:
        try:
            texto = fonte.decode("utf-8-sig")
        except UnicodeDecodeError:
            texto = fonte.decode("latin-1")  # CSV salvo pelo Excel no Windows
    linhas = list(csv.DictReader(io.StringIO(texto), delimiter=";"))
    faltando = colunas - set(linhas[0].keys() if linhas else [])
    if faltando:
        raise ErroDeArquivo(f"Colunas ausentes: {', '.join(sorted(faltando))}")
    return linhas


def _decimal(texto: str) -> Decimal:
    """Aceita '1234.50' e também '1.234,50' (formato brasileiro do Excel)."""
    original = texto
    texto = texto.strip()
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        valor = Decimal(texto)
    except InvalidOperation:
        # InvalidOperation NÃO herda de ValueError: sem isto, o app quebrava.
        raise ValueError(f"valor inválido '{original.strip()}'") from None
    if not valor.is_finite():  # Decimal aceita 'NaN' e 'Infinity'
        raise ValueError(f"valor inválido '{original.strip()}'")
    return valor


def _data(texto: str) -> date:
    """Aceita '2026-11-02' e '02/11/2026'."""
    texto = texto.strip()
    if "/" in texto:
        dia, mes, ano = texto.split("/")
        return date(int(ano), int(mes), int(dia))
    return date.fromisoformat(texto)


T = TypeVar("T")


def _converter(linhas: list[dict[str, str]], converter: Callable[[dict[str, str]], T]) -> list[T]:
    """Converte cada linha e, se der erro, diz em qual linha do arquivo foi."""
    resultado = []
    for numero, linha in enumerate(linhas, start=2):  # linha 1 é o cabeçalho
        try:
            resultado.append(converter(linha))
        except (ValueError, AttributeError) as erro:
            # AttributeError: linha com colunas a menos (campo vem como None)
            motivo = erro if isinstance(erro, ValueError) else "faltam colunas"
            raise ErroDeArquivo(f"linha {numero}: {motivo}") from erro
    return resultado


def _linha_sistema(linha: dict[str, str]) -> LancamentoSistema:
    """O sistema guarda valores positivos + tipo (RECEITA/DESPESA).
    Aqui convertemos para valor com sinal, igual ao extrato."""
    tipo = linha["tipo"].strip().upper()
    if tipo not in {"RECEITA", "DESPESA"}:
        raise ValueError(f"tipo deve ser RECEITA ou DESPESA, veio '{linha['tipo']}'")
    valor = _decimal(linha["valor"])
    return LancamentoSistema(
        id=linha["id"],
        data=_data(linha["data"]),
        descricao=linha["descricao"],
        categoria=linha["categoria"],
        valor=-valor if tipo == "DESPESA" else valor,
        documento=linha["documento"].strip(),
    )


def _linha_extrato(linha: dict[str, str]) -> LancamentoBanco:
    return LancamentoBanco(
        id=linha["id"],
        data=_data(linha["data"]),
        historico=linha["historico"],
        valor=_decimal(linha["valor"]),
        documento=linha["documento"].strip(),
    )


def ler_sistema(caminho: Fonte) -> list[LancamentoSistema]:
    return _converter(_ler_csv(caminho, COLUNAS_SISTEMA), _linha_sistema)


def ler_extrato(caminho: Fonte) -> list[LancamentoBanco]:
    return _converter(_ler_csv(caminho, COLUNAS_EXTRATO), _linha_extrato)
