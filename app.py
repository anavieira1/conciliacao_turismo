"""App web da conciliação bancária.

Rodar localmente:   streamlit run app.py
"""
from __future__ import annotations

import hmac
from collections import Counter
from decimal import Decimal
from pathlib import Path

import streamlit as st

from conciliacao.leitura import ErroDeArquivo, ler_extrato, ler_sistema
from conciliacao.modelos import Status
from conciliacao.motor import conciliar
from conciliacao.relatorio import brl, calcular_prova, gerar_csv, linhas_resultado

BASE = Path(__file__).parent
EXEMPLO_SISTEMA = BASE / "dados" / "lancamentos_sistema.csv"
EXEMPLO_EXTRATO = BASE / "dados" / "extrato_bancario.csv"

st.set_page_config(page_title="Conciliação Bancária", page_icon="🧾", layout="wide")


# --- Senha (camada extra além da restrição de acesso do Streamlit Cloud) ------
def _senha_configurada() -> str | None:
    try:
        return st.secrets.get("SENHA_APP")
    except Exception:  # sem arquivo de secrets (ex.: rodando local)
        return None


def exigir_senha() -> None:
    senha = _senha_configurada()
    if not senha or st.session_state.get("autenticado"):
        return
    st.title("🔒 Conciliação Bancária")
    digitada = st.text_input("Senha de acesso", type="password")
    if digitada:
        if hmac.compare_digest(digitada, senha):
            st.session_state["autenticado"] = True
            st.rerun()
        st.error("Senha incorreta.")
    st.stop()


exigir_senha()

# --- Barra lateral: parâmetros e arquivos ------------------------------------
with st.sidebar:
    st.header("Parâmetros")
    empresa = st.text_input("Empresa", "Horizonte Viagens & Turismo")
    saldo_inicial = st.number_input(
        "Saldo inicial (igual no banco e no sistema)", value=15000.00, step=100.00, format="%.2f"
    )

    st.header("Arquivos")
    arq_sistema = st.file_uploader("Lançamentos do sistema (.csv)", type="csv")
    arq_extrato = st.file_uploader("Extrato bancário (.csv)", type="csv")
    usar_exemplo = st.checkbox("Usar dados de exemplo", value=not (arq_sistema and arq_extrato))

    st.divider()
    st.caption("Modelos de planilha (separador ';')")
    st.download_button("Modelo - sistema", EXEMPLO_SISTEMA.read_bytes(), "modelo_sistema.csv")
    st.download_button("Modelo - extrato", EXEMPLO_EXTRATO.read_bytes(), "modelo_extrato.csv")

st.title(f"🧾 Conciliação Bancária — {empresa}")

if usar_exemplo:
    fonte_sistema, fonte_extrato = EXEMPLO_SISTEMA, EXEMPLO_EXTRATO
    st.info("Mostrando dados de exemplo. Envie seus arquivos na barra lateral e desmarque "
            "'Usar dados de exemplo'.")
elif arq_sistema and arq_extrato:
    fonte_sistema, fonte_extrato = arq_sistema.getvalue(), arq_extrato.getvalue()
else:
    st.warning("Envie os dois arquivos (sistema e extrato) na barra lateral.")
    st.stop()

try:
    sistema = ler_sistema(fonte_sistema)
    banco = ler_extrato(fonte_extrato)
except (ErroDeArquivo, ValueError, KeyError) as erro:
    st.error(f"Não consegui ler os arquivos: {erro}. Confira se seguem o modelo.")
    st.stop()

itens = conciliar(sistema, banco)
prova = calcular_prova(Decimal(str(saldo_inicial)), sistema, banco, itens)

# --- Indicadores -------------------------------------------------------------
contagem = Counter(i.status for i in itens)
casados = sum(1 for i in itens if i.sistema and i.banco)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Índice de conciliação", f"{casados / max(len(sistema), 1):.1%}".replace(".", ","))
c2.metric("Saldo no extrato", brl(prova["saldo_banco"]))
c3.metric("Saldo no sistema", brl(prova["saldo_sistema"]))
c4.metric("Itens para tratar",
          contagem[Status.DIVERGENTE] + contagem[Status.SO_NO_SISTEMA] + contagem[Status.SO_NO_BANCO])

if prova["diferenca_final"] == 0:
    st.success("✔ Conciliação fechada: todas as diferenças entre banco e sistema estão explicadas.")
else:
    st.error(f"✘ Diferença não explicada de {brl(prova['diferenca_final'])}.")

# --- Prova e resumo ----------------------------------------------------------
col_prova, col_resumo = st.columns([3, 2])
with col_prova:
    st.subheader("Prova da conciliação")
    st.table([
        {"Item": "Saldo final segundo o EXTRATO", "Valor": brl(prova["saldo_banco"])},
        {"Item": "(+) Só no sistema (a compensar)", "Valor": brl(prova["so_sistema"])},
        {"Item": "(-) Só no extrato (a registrar)", "Valor": brl(-prova["so_banco"])},
        {"Item": "(-) Diferenças em itens casados", "Valor": brl(-prova["dif_casados"])},
        {"Item": "(=) Extrato ajustado", "Valor": brl(prova["saldo_ajustado"])},
        {"Item": "Saldo final segundo o SISTEMA", "Valor": brl(prova["saldo_sistema"])},
    ])
with col_resumo:
    st.subheader("Resumo por situação")
    st.table([{"Situação": s.value, "Itens": contagem.get(s, 0)} for s in Status])

# --- Detalhe -----------------------------------------------------------------
st.subheader("Detalhe")
filtro = st.multiselect("Filtrar por situação", [s.value for s in Status],
                        default=[s.value for s in Status])
linhas = [l for l in linhas_resultado(itens) if l["status"] in filtro]
st.dataframe(
    linhas, width="stretch", hide_index=True,
    column_config={
        "valor_sistema": st.column_config.NumberColumn("valor_sistema", format="R$ %.2f"),
        "valor_banco": st.column_config.NumberColumn("valor_banco", format="R$ %.2f"),
        "diferenca": st.column_config.NumberColumn("diferenca", format="R$ %.2f"),
    },
)

st.download_button("⬇️ Baixar resultado (CSV para Excel)", gerar_csv(itens),
                   "resultado_conciliacao.csv", mime="text/csv", type="primary")
