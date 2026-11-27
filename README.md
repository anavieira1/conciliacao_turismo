# Conciliação Bancária — Agência de Turismo

Compara os lançamentos do sistema da agência com o extrato bancário, casa os itens
e explica cada diferença (taxa de cartão, pendências, tarifas, divergências).

## Rodar no computador

```bash
pip install -r requirements.txt
streamlit run app.py      # versão web, abre no navegador
python main.py            # versão terminal
```

## Rodar os testes

```bash
pip install -r requirements-dev.txt
python -m pytest
```

## Conferência do extrato

Informe na barra lateral o **saldo final impresso no extrato do banco**. O app
compara esse valor com `saldo inicial + soma das linhas do arquivo` e avisa se
o extrato exportado veio incompleto.

## Formato dos arquivos (CSV separado por `;`)

**Sistema:** `id;data;descricao;tipo;categoria;valor;documento`
(`tipo` = RECEITA ou DESPESA, valor sempre positivo)

**Extrato:** `id;data;historico;valor;documento`
(valor negativo = saída)

Datas em `2026-11-02` ou `02/11/2026`; valores em `1234.50` ou `1.234,50`.
Modelos para baixar ficam na barra lateral do app.

## Publicar na nuvem (Streamlit Community Cloud — grátis)

1. **GitHub:** crie uma conta em github.com e um repositório **privado**
   (ex.: `conciliacao-turismo`). Envie esta pasta para ele (veja abaixo).
2. **Streamlit:** entre em share.streamlit.io com a conta do GitHub.
3. Clique em **Create app**, escolha o repositório,
   branch `main` e arquivo `app.py`.
4. Em **Advanced settings**: Python 3.12 e, em **Secrets**, cole:
   ```toml
   SENHA_APP = "uma-senha-forte"
   ```
5. **Deploy.** Em ~2 minutos o app fica em `https://<nome>.streamlit.app`.
6. Apps de repositório privado já nascem privados. Em **Share** (canto superior
   direito do app), convide só os e-mails da equipe financeira.

### Enviar a pasta para o GitHub

```bash
git init
git add .
git commit -m "Conciliação bancária"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/conciliacao-turismo.git
git push -u origin main
```

Depois disso, cada `git push` atualiza o app na nuvem sozinho.

## Segurança

- Repositório **privado** + app **privado** + **senha** = três camadas.
- **Nunca** coloque extratos reais na pasta `dados/` nem no GitHub: envie-os
  só pela tela do app. Eles ficam na memória durante o uso e não são gravados.
- `secrets.toml` e `saida/` já estão no `.gitignore`.
