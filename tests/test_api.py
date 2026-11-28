"""Testes da API: chamam os endpoints como um cliente HTTP faria."""
from pathlib import Path

from api import main

DADOS = Path(__file__).parent.parent / "dados"
CABECALHO_EXTRATO = "id;data;historico;valor;documento\n"


def arquivos(sistema: bytes | None = None, extrato: bytes | None = None):
    return {
        "sistema": ("sistema.csv", sistema or (DADOS / "lancamentos_sistema.csv").read_bytes(), "text/csv"),
        "extrato": ("extrato.csv", extrato or (DADOS / "extrato_bancario.csv").read_bytes(), "text/csv"),
    }


def test_saude(cliente):
    resposta = cliente.get("/saude")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}


def test_concilia_os_dados_de_exemplo(cliente):
    resposta = cliente.post("/conciliacoes", files=arquivos(),
                            data={"saldo_inicial": "15000.00", "saldo_final_extrato": "32047.75"})
    assert resposta.status_code == 201
    corpo = resposta.json()

    assert corpo["resumo"] == {
        "conciliado": 7,
        "conciliado_taxa": 2,
        "divergente": 1,
        "so_no_sistema": 2,
        "so_no_banco": 3,
    }
    assert corpo["indice_conciliacao"] == "0.8333"
    assert corpo["conferencia"]["nivel"] == "ok"
    assert corpo["prova"]["saldo_sistema"] == "36210.00"
    assert len(corpo["itens"]) == 15


def test_dinheiro_sai_como_texto_para_nao_perder_centavos(cliente):
    corpo = cliente.post("/conciliacoes", files=arquivos(), data={"saldo_inicial": "15000"}).json()
    taxa = next(i for i in corpo["itens"] if i["status"] == "conciliado_taxa")
    assert taxa["sistema"]["valor"] == "6200.00"
    assert taxa["banco"]["valor"] == "6014.00"
    assert taxa["diferenca"] == "-186.00"


def test_item_so_no_extrato_vem_sem_o_lado_do_sistema(cliente):
    corpo = cliente.post("/conciliacoes", files=arquivos(), data={"saldo_inicial": "15000"}).json()
    iof = next(i for i in corpo["itens"] if i["banco"] and i["banco"]["historico"] == "IOF")
    assert iof["status"] == "so_no_banco"
    assert iof["status_descricao"] == "Só no extrato"
    assert iof["sistema"] is None


def test_sem_saldo_final_a_conferencia_e_um_aviso(cliente):
    corpo = cliente.post("/conciliacoes", files=arquivos(), data={"saldo_inicial": "15000"}).json()
    assert corpo["conferencia"]["nivel"] == "aviso"
    assert corpo["prova"]["diferenca_extrato"] is None


def test_extrato_incompleto_e_detectado(cliente):
    linhas = (DADOS / "extrato_bancario.csv").read_bytes().splitlines(keepends=True)
    corpo = cliente.post(
        "/conciliacoes", files=arquivos(extrato=b"".join(linhas[:6])),
        data={"saldo_inicial": "15000", "saldo_final_extrato": "32047.75"},
    ).json()
    assert corpo["conferencia"]["nivel"] == "erro"


def test_csv_invalido_devolve_422_dizendo_qual_arquivo_e_qual_linha(cliente):
    extrato = (CABECALHO_EXTRATO + "B1;2026-11-02;PIX;R$ 10,00;\n").encode()
    resposta = cliente.post("/conciliacoes", files=arquivos(extrato=extrato),
                            data={"saldo_inicial": "15000"})
    assert resposta.status_code == 422
    assert resposta.json()["detail"] == "extrato: linha 2: valor inválido 'R$ 10,00'"


def test_falta_um_arquivo_devolve_422(cliente):
    resposta = cliente.post("/conciliacoes", files={"sistema": arquivos()["sistema"]},
                            data={"saldo_inicial": "15000"})
    assert resposta.status_code == 422


def test_saldo_inicial_invalido_devolve_422(cliente):
    resposta = cliente.post("/conciliacoes", files=arquivos(), data={"saldo_inicial": "abc"})
    assert resposta.status_code == 422


def test_arquivo_grande_demais_devolve_413(cliente, monkeypatch):
    monkeypatch.setattr(main, "LIMITE_BYTES", 100)
    resposta = cliente.post("/conciliacoes", files=arquivos(), data={"saldo_inicial": "15000"})
    assert resposta.status_code == 413
    assert "sistema" in resposta.json()["detail"]
