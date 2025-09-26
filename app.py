import streamlit as st
import pandas as pd
from datetime import datetime
import requests
import base64
import io

# ==================== CONFIGURAÇÕES DO APLICATIVO ====================
# As variáveis de token e repositório são carregadas dos segredos do Streamlit.
# Isso garante que suas credenciais permaneçam seguras.
TOKEN = st.secrets["GITHUB_TOKEN"]
OWNER = st.secrets["REPO_OWNER"]
REPO = st.secrets["REPO_NAME"]
CSV_PATH = st.secrets["CSV_PATH"]
COMMIT_MESSAGE = st.secrets["COMMIT_MESSAGE"]
# 'main' é a branch padrão, mas pode ser configurada nos segredos
BRANCH = st.secrets.get("BRANCH", "main")

# Cabeçalhos de autenticação para as requisições à API do GitHub
HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

# ==================== FUNÇÕES DE INTERAÇÃO COM O GITHUB ====================
@st.cache_data
def carregar_dados_do_github():
    """
    Carrega o arquivo CSV do GitHub, decodifica o conteúdo e retorna um DataFrame.
    Também retorna o SHA do arquivo para futura atualização.
    """
    url = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{CSV_PATH}?ref={BRANCH}"
    
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()  # Lança um erro para códigos de status HTTP ruins (4xx ou 5xx)
        
        content = response.json()
        decoded_content = base64.b64decode(content["content"]).decode("utf-8")
        # Usa io.StringIO, que é a forma correta de ler strings em memória com pandas
        df = pd.read_csv(io.StringIO(decoded_content), parse_dates=["Data"])
        
        sha = content["sha"]
        return df, sha
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            st.info("Arquivo CSV não encontrado no GitHub. Criando um novo DataFrame localmente.")
            # Retorna um DataFrame vazio se o arquivo não existir
            return pd.DataFrame(columns=["Data", "Cliente", "Valor", "Forma de Pagamento", "Tipo"]), None
        else:
            st.error(f"Erro HTTP ao carregar dados do GitHub: {e}")
            return pd.DataFrame(columns=["Data", "Cliente", "Valor", "Forma de Pagamento", "Tipo"]), None
    except Exception as e:
        st.error(f"Ocorreu um erro inesperado ao carregar os dados: {e}")
        return pd.DataFrame(columns=["Data", "Cliente", "Valor", "Forma de Pagamento", "Tipo"]), None

def salvar_dados_no_github(df, sha=None):
    """
    Converte o DataFrame para CSV, codifica em Base64 e salva no GitHub.
    Usa o SHA para atualizar o arquivo existente.
    """
    # Converte o DataFrame para string CSV
    csv_string = df.to_csv(index=False)
    # Codifica a string CSV em Base64
    csv_encoded = base64.b64encode(csv_string.encode()).decode()
    
    url = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{CSV_PATH}"

    payload = {
        "message": COMMIT_MESSAGE,
        "content": csv_encoded,
        "branch": BRANCH,
    }

    if sha:
        # O SHA é necessário para que a API do GitHub saiba qual versão do arquivo atualizar
        payload["sha"] = sha

    try:
        response = requests.put(url, headers=HEADERS, json=payload)
        response.raise_for_status()
        
        if response.status_code in [200, 201]:
            st.success("📁 Dados salvos no GitHub com sucesso!")
        else:
            st.error(f"Erro ao salvar no GitHub. Código de status: {response.status_code}")
            st.code(response.json())
            
    except requests.exceptions.RequestException as e:
        st.error(f"Erro de requisição ao salvar no GitHub: {e}")
        st.code(response.json())


# ==================== INTERFACE STREAMLIT ====================
st.title("📘 Livro Caixa - Streamlit + GitHub")

# --- Formulário de Nova Movimentação na barra lateral ---
st.sidebar.header("Nova Movimentação")
with st.sidebar.form("form_movimentacao"):
    data = st.date_input("Data", datetime.today())
    cliente = st.text_input("Nome do Cliente")
    valor = st.number_input("Valor (R$)", min_value=0.0, format="%.2f")
    forma_pagamento = st.selectbox("Forma de Pagamento", ["Dinheiro", "Cartão", "PIX", "Transferência"])
    tipo = st.radio("Tipo", ["Entrada", "Saída"])
    enviar = st.form_submit_button("Adicionar Movimentação")

# --- Lógica principal ---
# Carrega os dados do GitHub ao iniciar o aplicativo
df, sha = carregar_dados_do_github()

# Se o botão do formulário foi clicado, processa a nova movimentação
if enviar:
    if not cliente or valor <= 0:
        st.sidebar.warning("Por favor, preencha o nome do cliente e o valor corretamente.")
    else:
        nova_linha = {
            "Data": pd.to_datetime(data),
            "Cliente": cliente,
            "Valor": valor if tipo == "Entrada" else -valor,
            "Forma de Pagamento": forma_pagamento,
            "Tipo": tipo
        }
        
        # Adiciona a nova linha ao DataFrame existente
        df_atualizado = pd.concat([df, pd.DataFrame([nova_linha])], ignore_index=True)
        
        # Salva o DataFrame atualizado no GitHub
        salvar_dados_no_github(df_atualizado, sha)
        
        st.success("Movimentação adicionada com sucesso!")
        st.rerun() # Reruns the app to show the updated table

# --- Exibição e Análises dos Dados ---
st.subheader("📊 Movimentações Registradas")
if df.empty:
    st.info("Nenhuma movimentação registrada ainda.")
else:
    # Ordena o DataFrame pela data de forma decrescente
    df_exibicao = df.sort_values(by="Data", ascending=False).reset_index(drop=True)
    st.dataframe(df_exibicao, use_container_width=True)

    # Resumo Financeiro
    st.markdown("### 💰 Resumo Financeiro")
    total_entradas = df_exibicao[df_exibicao["Tipo"] == "Entrada"]["Valor"].sum()
    total_saidas = df_exibicao[df_exibicao["Tipo"] == "Saída"]["Valor"].sum()
    saldo = df_exibicao["Valor"].sum()

    col1, col2, col3 = st.columns(3)
    col1.metric("Total de Entradas", f"R$ {total_entradas:,.2f}")
    col2.metric("Total de Saídas", f"R$ {abs(total_saidas):,.2f}")
    col3.metric("💼 Saldo Final", f"R$ {saldo:,.2f}", delta_color="normal")

    # Filtro por Data
    st.markdown("---")
    st.markdown("### 📅 Filtrar por Período")
    col_data_inicial, col_data_final = st.columns(2)
    with col_data_inicial:
        data_inicial = st.date_input("Data Inicial", value=df_exibicao["Data"].min())
    with col_data_final:
        data_final = st.date_input("Data Final", value=df_exibicao["Data"].max())

    if data_inicial and data_final:
        df_filtrado = df_exibicao[(df_exibicao["Data"] >= pd.to_datetime(data_inicial)) & (df_exibicao["Data"] <= pd.to_datetime(data_final))]
        
        if df_filtrado.empty:
            st.warning("Não há movimentações para o período selecionado.")
        else:
            st.dataframe(df_filtrado, use_container_width=True)

            entradas_filtro = df_filtrado[df_filtrado["Tipo"] == "Entrada"]["Valor"].sum()
            saidas_filtro = df_filtrado[df_filtrado["Tipo"] == "Saída"]["Valor"].sum()
            saldo_filtro = df_filtrado["Valor"].sum()
            
            st.markdown("#### 💼 Resumo do Período Filtrado")
            col1_f, col2_f, col3_f = st.columns(3)
            col1_f.metric("Entradas", f"R$ {entradas_filtro:,.2f}")
            col2_f.metric("Saídas", f"R$ {abs(saidas_filtro):,.2f}")
            col3_f.metric("Saldo", f"R$ {saldo_filtro:,.2f}")
