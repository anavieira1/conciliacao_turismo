# Conciliação Bancária para Agência de Turismo

[![testes](https://github.com/anavieira1/conciliacao_turismo/actions/workflows/testes.yml/badge.svg)](https://github.com/anavieira1/conciliacao_turismo/actions/workflows/testes.yml)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue)

Ferramenta em Python que compara os lançamentos do sistema financeiro de uma
agência de turismo com o extrato do banco, casa cada item e **explica cada
diferença**: taxa da maquininha de cartão, pagamento ainda não compensado,
tarifa bancária não registrada ou valor divergente.

## O problema

No fim do mês, o financeiro precisa provar que o saldo do banco bate com o do
sistema. Na prática, isso é feito à mão no Excel, linha por linha:

- vendas no cartão caem no banco **com desconto da adquirente**, então o valor
  nunca bate exatamente;
- pagamentos compensam **dias depois** do lançamento;
- tarifas, IOF e depósitos não identificados aparecem **só no extrato**.

Este projeto automatiza esse trabalho e entrega a lista do que precisa de ação.

![App de conciliação bancária com indicadores, conferência do extrato e prova da conciliação](docs/app.png)

## O que ele faz

Com os dados de exemplo (12 lançamentos no sistema, 13 no extrato):

| Situação                        | Itens | O que o financeiro faz              |
|---------------------------------|:-----:|-------------------------------------|
| Conciliado                      | 7     | Nada                                |
| Conciliado c/ taxa de cartão    | 2     | Lançar a taxa (3%) como despesa     |
| Divergente (valor diferente)    | 1     | Verificar com o cliente os R$ 90 a menos |
| Só no sistema                   | 2     | Aguardar compensação                |
| Só no extrato                   | 3     | Registrar tarifa, IOF e identificar depósito |

O mesmo motor de conciliação é usado por três portas de entrada:

- uma **API REST** (FastAPI), para outros sistemas enviarem os arquivos e
  receberem o resultado em JSON, com **histórico salvo em PostgreSQL**;
- um **app web** (Streamlit), com upload dos CSVs, indicadores, filtro e
  download do resultado para Excel;
- uma **versão de terminal**.

## Como a conciliação funciona

```mermaid
flowchart LR
    A[CSV do sistema] --> L[leitura.py<br/>valida e normaliza]
    B[CSV do extrato] --> L
    L --> M[motor.py<br/>regras de casamento]
    M --> R[relatorio.py<br/>prova + CSV]
    R --> P[api/<br/>FastAPI]
    R --> W[app.py<br/>Streamlit]
    R --> T[main.py<br/>terminal]
    P --> D[(PostgreSQL<br/>histórico)]
```

As regras são aplicadas em ordem ([motor.py](conciliacao/motor.py)):

1. **Por documento** (PIX, TED, boleto, cartão), a chave mais confiável.
   - Valor igual → conciliado.
   - Venda no cartão que entrou até 5% menor → conciliado com taxa da adquirente.
   - Qualquer outra diferença → divergente.
2. **Por valor + data**, para lançamentos sem documento: mesmo valor com até
   3 dias de diferença, escolhendo a data mais próxima.
3. **O que sobrar** vira pendência, com uma sugestão do que fazer.

No fim, a **prova da conciliação** parte do saldo do banco e chega ao saldo do
sistema somando cada diferença explicada. O app também confere o saldo final
impresso no extrato contra a soma das linhas do arquivo, para detectar um
extrato exportado incompleto.

## Decisões técnicas

- **`Decimal` em vez de `float` para dinheiro.** `0.1 + 0.2` não dá `0.3` em
  float; em conciliação, um centavo de erro quebra a prova.
- **Motor sem dependência de interface.** `conciliacao/` não importa Streamlit
  nem FastAPI, então a mesma lógica serve à API, ao app, ao terminal e aos
  testes. A API foi adicionada sem mudar uma regra do motor.
- **Dinheiro como texto no JSON** (`"4500.00"`). JSON não tem tipo decimal, e
  um número de ponto flutuante poderia virar `4499.999999`.
- **Códigos estáveis na API** (`so_no_banco`) separados do texto da tela
  (`"Só no extrato"`), para o texto poder mudar sem quebrar quem integra.
- **Histórico como "foto" da conciliação.** Uma conciliação feita não muda:
  colunas de resumo servem à listagem, e o resultado completo fica em `JSONB`.
  Isso evita espalhar cada item por outra tabela só para remontá-lo depois.
  Dinheiro no banco é `NUMERIC(14,2)`, nunca `float`.
- **Mesmo código para PostgreSQL e SQLite** (SQLAlchemy 2.0). O banco vem da
  variável `DATABASE_URL`; sem ela, a API usa um arquivo SQLite para rodar no
  computador sem instalar nada.
- **Modelos imutáveis** (`dataclass(frozen=True)`) e `Enum` para os status:
  nenhum lançamento é alterado no meio do processo.
- **Entrada do mundo real:** aceita `1.234,50` e `1234.50`, `02/11/2026` e
  `2026-11-02`, e CSV salvo pelo Excel em latin-1. Erros de formato viram uma
  mensagem com o número da linha, não um traceback.
- **Saída pronta para o Excel brasileiro:** CSV com `;`, vírgula decimal e BOM.

## Testes

52 testes com pytest cobrem as regras de casamento, a leitura dos arquivos, a
prova da conciliação, os endpoints da API (sucesso, CSV inválido, arquivo
faltando e arquivo grande demais) e o histórico (salvar, buscar, paginar, 404,
centavos intactos na ida e volta do banco).

Cada teste começa com um banco vazio. No computador é um SQLite em memória; no
GitHub Actions, a cada pull request, os mesmos testes rodam contra um
**PostgreSQL 17 de verdade**.

```bash
pip install -r requirements-dev.txt
python -m pytest
```

Escrever os testes revelou dois bugs, corrigidos com teste de regressão:

- **A prova da conciliação nunca falhava.** O saldo do banco e o do sistema
  eram calculados a partir das mesmas linhas, então a "diferença não
  explicada" era sempre zero, mesmo com metade do extrato faltando. A correção
  compara com o saldo final impresso pelo banco.
- **Um valor como `R$ 100,00` derrubava o app.** `decimal.InvalidOperation`
  não herda de `ValueError` e escapava do tratamento de erro.

## Rodar no computador

```bash
pip install -r requirements.txt
uvicorn api.main:app --reload   # API em http://localhost:8000/docs
streamlit run app.py            # app web, abre no navegador
python main.py                  # versão terminal
```

O histórico da API fica em `saida/historico.db` (SQLite). Para usar
PostgreSQL, defina o endereço antes de iniciar a API:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://usuario:senha@localhost:5432/conciliacao"
```

## API

A documentação interativa (Swagger) fica em `/docs`: dá para enviar os
arquivos e ver a resposta pelo próprio navegador.

| Método | Rota                   | O que faz                                              |
|--------|------------------------|--------------------------------------------------------|
| GET    | `/saude`               | Verifica se a API está no ar                           |
| POST   | `/conciliacoes`        | Recebe os dois CSVs, salva e devolve a conciliação (201) |
| GET    | `/conciliacoes`        | Histórico, mais recente primeiro (`?limite=20&inicio=0`) |
| GET    | `/conciliacoes/{id}`   | Uma conciliação completa do histórico (404 se não existe) |

```bash
curl -X POST http://localhost:8000/conciliacoes   -F "sistema=@dados/lancamentos_sistema.csv"   -F "extrato=@dados/extrato_bancario.csv"   -F saldo_inicial=15000   -F saldo_final_extrato=32047.75
```

Resposta (resumida):

```json
{
  "id": 1,
  "criada_em": "2026-11-27T20:15:03.512Z",
  "indice_conciliacao": "0.8333",
  "resumo": {"conciliado": 7, "conciliado_taxa": 2, "divergente": 1,
             "so_no_sistema": 2, "so_no_banco": 3},
  "conferencia": {"nivel": "ok", "mensagem": "Extrato completo: ..."},
  "prova": {"saldo_banco": "32047.75", "saldo_sistema": "36210.00", "...": "..."},
  "itens": [
    {
      "status": "conciliado_taxa",
      "status_descricao": "Conciliado c/ taxa de cartão",
      "regra": "documento",
      "diferenca": "-186.00",
      "observacao": "Taxa da adquirente de 3.00% - lançar como despesa financeira",
      "sistema": {"id": "S02", "valor": "6200.00", "...": "..."},
      "banco": {"id": "B03", "valor": "6014.00", "...": "..."}
    }
  ]
}
```

Erros seguem os códigos HTTP: `422` quando um CSV está fora do formato (a
mensagem diz qual arquivo e qual linha) e `413` para arquivo acima de 10 MB.

## Formato dos arquivos (CSV separado por `;`)

**Sistema:** `id;data;descricao;tipo;categoria;valor;documento`
(`tipo` = RECEITA ou DESPESA, valor sempre positivo)

**Extrato:** `id;data;historico;valor;documento`
(valor negativo = saída)

Modelos para baixar ficam na barra lateral do app. Os dados em `dados/` são
fictícios.

## Estrutura

```
conciliacao/
  modelos.py     lançamentos e resultado (dataclasses + Enum)
  leitura.py     leitura e validação dos CSVs
  motor.py       regras de casamento
  relatorio.py   prova da conciliação, relatório e CSV
api/
  main.py        endpoints (FastAPI)
  esquemas.py    formato das respostas (Pydantic)
  banco.py       conexão com o banco (DATABASE_URL)
  tabelas.py     tabela do histórico (SQLAlchemy)
app.py           interface web (Streamlit)
main.py          versão de terminal
tests/           testes com pytest
```

## Próximos passos

- [x] API REST com FastAPI usando o mesmo motor
- [x] Histórico de conciliações em PostgreSQL
- [ ] Docker e deploy da API
- [ ] Migrações do banco com Alembic
- [ ] Importar extrato em OFX, o formato padrão dos bancos

## Publicar na nuvem (Streamlit Community Cloud)

1. Entre em share.streamlit.io com a conta do GitHub e clique em **Create app**.
2. Escolha este repositório, branch `main` e arquivo `app.py`.
3. Em **Advanced settings**, use Python 3.12 e, em **Secrets**, cole:
   ```toml
   SENHA_APP = "uma-senha-forte"
   ```
4. Clique em **Deploy**. Cada `git push` na `main` atualiza o app.

## Segurança

- Com `SENHA_APP` configurada, o app pede senha antes de mostrar qualquer dado
  (comparação com `hmac.compare_digest`, resistente a ataque de tempo).
- **Nunca** coloque extratos reais em `dados/` nem no GitHub: envie-os só pela
  tela do app. Eles ficam na memória durante o uso e não são gravados.
- `secrets.toml` e `saida/` estão no `.gitignore`.
