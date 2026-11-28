"""Testes do histórico: cada conciliação criada fica guardada no banco."""
from datetime import datetime
from pathlib import Path

DADOS = Path(__file__).parent.parent / "dados"


def conciliar(cliente, saldo_final: str | None = "32047.75", extrato: bytes | None = None):
    dados = {"saldo_inicial": "15000.00"}
    if saldo_final:
        dados["saldo_final_extrato"] = saldo_final
    arquivos = {
        "sistema": ("sistema_nov.csv", (DADOS / "lancamentos_sistema.csv").read_bytes(), "text/csv"),
        "extrato": ("extrato_nov.csv", extrato or (DADOS / "extrato_bancario.csv").read_bytes(),
                    "text/csv"),
    }
    return cliente.post("/conciliacoes", files=arquivos, data=dados)


def test_criar_devolve_201_com_id_data_e_endereco(cliente):
    resposta = conciliar(cliente)
    assert resposta.status_code == 201
    corpo = resposta.json()
    assert isinstance(corpo["id"], int)
    assert resposta.headers["location"] == f"/conciliacoes/{corpo['id']}"
    assert datetime.fromisoformat(corpo["criada_em"]).tzinfo is not None


def test_buscar_por_id_devolve_o_mesmo_resultado_da_criacao(cliente):
    criada = conciliar(cliente).json()
    buscada = cliente.get(f"/conciliacoes/{criada['id']}")
    assert buscada.status_code == 200
    assert buscada.json() == criada


def test_id_inexistente_devolve_404(cliente):
    resposta = cliente.get("/conciliacoes/999")
    assert resposta.status_code == 404
    assert resposta.json()["detail"] == "conciliação não encontrada"


def test_listagem_traz_o_resumo_da_mais_recente_para_a_mais_antiga(cliente):
    primeira = conciliar(cliente).json()
    segunda = conciliar(cliente, saldo_final=None).json()

    lista = cliente.get("/conciliacoes").json()

    assert [c["id"] for c in lista] == [segunda["id"], primeira["id"]]
    assert lista[1] == {
        "id": primeira["id"],
        "criada_em": primeira["criada_em"],
        "arquivo_sistema": "sistema_nov.csv",
        "arquivo_extrato": "extrato_nov.csv",
        "saldo_inicial": "15000.00",
        "saldo_final_extrato": "32047.75",
        "indice_conciliacao": "0.8333",
        "nivel_conferencia": "ok",
        "itens_para_tratar": 6,
    }
    assert lista[0]["saldo_final_extrato"] is None
    assert lista[0]["nivel_conferencia"] == "aviso"
    assert "itens" not in lista[0]  # a listagem é leve; os itens vêm no GET por id


def test_listagem_e_paginada(cliente):
    ids = [conciliar(cliente).json()["id"] for _ in range(3)]
    pagina = cliente.get("/conciliacoes", params={"limite": 2, "inicio": 1}).json()
    assert [c["id"] for c in pagina] == [ids[1], ids[0]]


def test_limite_fora_da_faixa_devolve_422(cliente):
    assert cliente.get("/conciliacoes", params={"limite": 0}).status_code == 422
    assert cliente.get("/conciliacoes", params={"limite": 101}).status_code == 422


def test_arquivo_invalido_nao_vai_para_o_historico(cliente):
    resposta = conciliar(cliente, extrato=b"id;data;historico;valor;documento\nB1;ontem;PIX;10;\n")
    assert resposta.status_code == 422
    assert cliente.get("/conciliacoes").json() == []


def test_centavos_sobrevivem_a_ida_e_volta_do_banco(cliente):
    criada = conciliar(cliente, saldo_final="32047.75").json()
    buscada = cliente.get(f"/conciliacoes/{criada['id']}").json()
    assert buscada["prova"]["saldo_final_informado"] == "32047.75"
    taxa = next(i for i in buscada["itens"] if i["status"] == "conciliado_taxa")
    assert taxa["diferenca"] == "-186.00"
