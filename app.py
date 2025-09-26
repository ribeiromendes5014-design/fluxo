import streamlit as st
import pandas as pd
from datetime import datetime
import requests
from io import StringIO
import base64

# ==================== CONFIGURAÇÕES DO APLICATIVO ====================
# As variáveis de token e repositório são carregadas dos segredos do Streamlit.
# Isso garante que suas credenciais permaneçam seguras.
TOKEN = st.secrets["GITHUB_TOKEN"]
OWNER = st.secrets["REPO_OWNER"]
REPO = st.secrets["REPO_NAME"]
CSV_PATH = st.secrets["CSV_PATH"]
COMMIT_MESSAGE = "Atualiza livro caixa via Streamlit" # Mensagem de commit padrão para adições
COMMIT_MESSAGE_DELETE = "Exclui movimentações do livro caixa" # Mensagem de commit para exclusões
# 'main' é a branch padrão, mas pode ser configurada nos segredos
BRANCH = st.secrets.get("BRANCH", "main")

# Cabeçalhos de autenticação para as requisições à API do GitHub
HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

# ==================== FUNÇÕES DE INTERAÇÃO COM O GITHUB ====================
@st.cache_data(show_spinner="Carregando dados do GitHub...")
def carregar_dados_do_github():
    """
    Carrega o arquivo CSV do GitHub usando a URL de conteúdo bruto.
    Essa abordagem é ideal para arquivos públicos.
    """
    url_raw = f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{BRANCH}/{CSV_PATH}"
    try:
        response = requests.get(url_raw)
        response.raise_for_status()
        df = pd.read_csv(StringIO(response.text), parse_dates=["Data"])
        return df
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            st.info("Arquivo CSV não encontrado no GitHub. Criando um novo DataFrame localmente.")
            return pd.DataFrame(columns=["Data", "Cliente", "Valor", "Forma de Pagamento", "Tipo"])
        else:
            st.error(f"Erro HTTP ao carregar dados do GitHub: {e}")
            return pd.DataFrame(columns=["Data", "Cliente", "Valor", "Forma de Pagamento", "Tipo"])
    except Exception as e:
        st.error(f"Ocorreu um erro inesperado ao carregar os dados: {e}")
        return pd.DataFrame(columns=["Data", "Cliente", "Valor", "Forma de Pagamento", "Tipo"])

def salvar_dados_no_github(df, commit_message=COMMIT_MESSAGE):
    """
    Converte o DataFrame para CSV, codifica em Base64 e salva no GitHub.
    Obtém o SHA atual do arquivo para evitar conflitos.
    """
    url_api = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{CSV_PATH}"
    
    # 1. Obtém o SHA atual do arquivo para evitar conflitos
    try:
        response_sha = requests.get(url_api, headers=HEADERS)
        response_sha.raise_for_status()
        sha = response_sha.json()["sha"]
    except Exception as e:
        st.warning("Não foi possível obter o SHA do arquivo. Tentando criar um novo.")
        sha = None

    # 2. Converte o DataFrame para string CSV e codifica em Base64
    csv_string = df.to_csv(index=False)
    csv_encoded = base64.b64encode(csv_string.encode()).decode()
    
    # 3. Prepara e envia o payload
    payload = {
        "message": commit_message,
        "content": csv_encoded,
        "branch": BRANCH,
    }
    if sha:
        payload["sha"] = sha
    
    try:
        response = requests.put(url_api, headers=HEADERS, json=payload)
        response.raise_for_status()
        if response.status_code in [200, 201]:
            st.success("📁 Dados salvos no GitHub com sucesso!")
            return True
        else:
            st.error(f"Erro ao salvar no GitHub. Código de status: {response.status_code}")
            st.code(response.json())
            return False
            
    except requests.exceptions.RequestException as e:
        st.error(f"Erro de requisição ao salvar no GitHub: {e}")
        return False

# ==================== INTERFACE STREAMLIT ====================
st.title("📘 Livro Caixa - Streamlit + GitHub")

# Usando st.session_state para gerenciar o DataFrame
if "df" not in st.session_state:
    st.session_state.df = carregar_dados_do_github()

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
        st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([nova_linha])], ignore_index=True)

# --- Botão para Salvar no GitHub ---
if st.button("Salvar no GitHub"):
    if salvar_dados_no_github(st.session_state.df, COMMIT_MESSAGE):
        st.cache_data.clear()
        st.rerun()
    else:
        st.error("Falha ao salvar as alterações. Verifique os logs.")

# --- Exibição e Análises dos Dados ---
st.subheader("📊 Movimentações Registradas")
if st.session_state.df.empty:
    st.info("Nenhuma movimentação registrada ainda.")
else:
    df_exibicao = st.session_state.df.copy()
    df_exibicao = df_exibicao.sort_values(by="Data", ascending=False)
    st.dataframe(df_exibicao, use_container_width=True)

    st.markdown("---")
    st.markdown("### 🗑️ Excluir Movimentações")
    opcoes_exclusao = {
        f"ID: {row.name} - Data: {row['Data'].strftime('%d/%m/%Y') if pd.notnull(row['Data']) else 'Data inválida'} - {row['Cliente']} - R$ {row['Valor']:,.2f}": row.name
        for _, row in st.session_state.df.iterrows()
    }
    movimentacoes_a_excluir_str = st.multiselect(
        "Selecione as movimentações que deseja excluir:",
        options=list(opcoes_exclusao.keys())
    )
    indices_a_excluir = [opcoes_exclusao[s] for s in movimentacoes_a_excluir_str]

    if st.button("Excluir Selecionadas"):
        if indices_a_excluir:
            st.session_state.df = st.session_state.df.drop(indices_a_excluir)
            st.warning("Movimentações excluídas. Clique em 'Salvar no GitHub' para confirmar.")
        else:
            st.warning("Selecione pelo menos uma movimentação para excluir.")

    st.markdown("---")
    st.markdown("### 💰 Resumo Financeiro")
    total_entradas = df_exibicao[df_exibicao["Tipo"] == "Entrada"]["Valor"].sum()
    total_saidas = df_exibicao[df_exibicao["Tipo"] == "Saída"]["Valor"].sum()
    saldo = df_exibicao["Valor"].sum()

    col1, col2, col3 = st.columns(3)
    col1.metric("Total de Entradas", f"R$ {total_entradas:,.2f}")
    col2.metric("Total de Saídas", f"R$ {abs(total_saidas):,.2f}")
    col3.metric("💼 Saldo Final", f"R$ {saldo:,.2f}", delta_color="normal")

    st.markdown("---")
    st.markdown("### 📅 Filtrar por Período")
    col_data_inicial, col_data_final = st.columns(2)
    with col_data_inicial:
        data_inicial = st.date_input("Data Inicial", value=df_exibicao["Data"].min())
    with col_data_final:
        data_final = st.date_input("Data Final", value=df_exibicao["Data"].max())

    if data_inicial and data_final:
        df_filtrado = df_exibicao[
            (df_exibicao["Data"] >= pd.to_datetime(data_inicial)) &
            (df_exibicao["Data"] <= pd.to_datetime(data_final))
        ]
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
