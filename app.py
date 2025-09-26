import streamlit as st
import pandas as pd
from datetime import datetime
import requests
import base64

# ==== CONFIGURAÇÃO A PARTIR DO SECRETS ====
TOKEN = st.secrets["GITHUB_TOKEN"]
OWNER = st.secrets["REPO_OWNER"]
REPO = st.secrets["REPO_NAME"]
CSV_PATH = st.secrets["CSV_PATH"]
COMMIT_MESSAGE = st.secrets["COMMIT_MESSAGE"]
BRANCH = st.secrets.get("BRANCH", "main")  # Padrão: main

HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

# ==== FUNÇÕES DE LEITURA E ESCRITA NO GITHUB ====
def carregar_dados():
    url = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{CSV_PATH}?ref={BRANCH}"
    response = requests.get(url, headers=HEADERS)

    if response.status_code == 200:
        content = response.json()
        decoded = base64.b64decode(content["content"]).decode("utf-8")
        df = pd.read_csv(pd.compat.StringIO(decoded), parse_dates=["Data"])
        sha = content["sha"]
        return df, sha
    else:
        # Arquivo não existe ainda, retorna vazio
        return pd.DataFrame(columns=["Data", "Cliente", "Valor", "Forma de Pagamento", "Tipo"]), None

def salvar_dados(df, sha=None):
    csv_encoded = base64.b64encode(df.to_csv(index=False).encode()).decode()
    url = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{CSV_PATH}"

    payload = {
        "message": COMMIT_MESSAGE,
        "content": csv_encoded,
        "branch": BRANCH,
    }

    if sha:
        payload["sha"] = sha  # necessário para sobrescrever o arquivo existente

    response = requests.put(url, headers=HEADERS, json=payload)

    if response.status_code in [200, 201]:
        st.success("📁 Dados salvos no GitHub com sucesso!")
    else:
        st.error("Erro ao salvar no GitHub.")
        st.code(response.json())

# ==== INTERFACE STREAMLIT ====
st.title("📘 Livro Caixa - Streamlit + GitHub")

st.sidebar.header("Nova Movimentação")

# Inputs do formulário
with st.sidebar.form("form_movimentacao"):
    data = st.date_input("Data", datetime.today())
    cliente = st.text_input("Nome do Cliente")
    valor = st.number_input("Valor (R$)", min_value=0.0, format="%.2f")
    forma_pagamento = st.selectbox("Forma de Pagamento", ["Dinheiro", "Cartão", "PIX", "Transferência"])
    tipo = st.radio("Tipo", ["Entrada", "Saída"])
    enviar = st.form_submit_button("Adicionar")

# Carrega os dados do GitHub
df, sha = carregar_dados()

# Se enviou o formulário, adiciona nova linha e salva no GitHub
if enviar:
    nova_linha = {
        "Data": pd.to_datetime(data),
        "Cliente": cliente,
        "Valor": valor if tipo == "Entrada" else -valor,
        "Forma de Pagamento": forma_pagamento,
        "Tipo": tipo
    }
    df = pd.concat([df, pd.DataFrame([nova_linha])], ignore_index=True)
    salvar_dados(df, sha)
    st.success("Movimentação adicionada com sucesso!")

# Mostrar dados em formato de tabela
st.subheader("📊 Movimentações")
if df.empty:
    st.info("Nenhuma movimentação registrada ainda.")
else:
    df = df.sort_values(by="Data", ascending=False)
    st.dataframe(df, use_container_width=True)

    # Cálculos
    total_entradas = df[df["Tipo"] == "Entrada"]["Valor"].sum()
    total_saidas = df[df["Tipo"] == "Saída"]["Valor"].sum()
    saldo = df["Valor"].sum()

    st.markdown("### 💰 Resumo Financeiro")
    col1, col2, col3 = st.columns(3)
    col1.metric("Total de Entradas", f"R$ {total_entradas:,.2f}")
    col2.metric("Total de Saídas", f"R$ {abs(total_saidas):,.2f}")
    col3.metric("💼 Saldo Final", f"R$ {saldo:,.2f}", delta_color="normal")

    # Filtro por data
    st.markdown("### 📅 Filtro por Data")
    data_inicial = st.date_input("Data Inicial", value=df["Data"].min() if not df.empty else datetime.today())
    data_final = st.date_input("Data Final", value=df["Data"].max() if not df.empty else datetime.today())

    if data_inicial and data_final:
        df_filtrado = df[(df["Data"] >= pd.to_datetime(data_inicial)) & (df["Data"] <= pd.to_datetime(data_final))]
        st.dataframe(df_filtrado, use_container_width=True)

        entradas_filtro = df_filtrado[df_filtrado["Tipo"] == "Entrada"]["Valor"].sum()
        saidas_filtro = df_filtrado[df_filtrado["Tipo"] == "Saída"]["Valor"].sum()
        saldo_filtro = df_filtrado["Valor"].sum()

        st.markdown("#### 💼 Resumo do Período")
        col1, col2, col3 = st.columns(3)
        col1.metric("Entradas", f"R$ {entradas_filtro:,.2f}")
        col2.metric("Saídas", f"R$ {abs(saidas_filtro):,.2f}")
        col3.metric("Saldo", f"R$ {saldo_filtro:,.2f}")
