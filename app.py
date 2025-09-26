import streamlit as st
import pandas as pd
from datetime import datetime
import requests
from io import StringIO
import io, os
# Importa a biblioteca PyGithub para gerenciamento de persistência
from github import Github 

# IMPORTANTE: Você precisa ter a biblioteca 'PyGithub' instalada. 
# Adicione 'PyGithub' ao seu requirements.txt.

# ==================== CONFIGURAÇÕES DO APLICATIVO ====================
# As variáveis de token e repositório são carregadas dos segredos do Streamlit.
# Garanta que suas credenciais estejam seguras no secrets.toml
try:
    TOKEN = st.secrets["GITHUB_TOKEN"]
    OWNER = st.secrets["REPO_OWNER"]
    REPO_NAME = st.secrets["REPO_NAME"] 
    CSV_PATH = st.secrets["CSV_PATH"]
    BRANCH = st.secrets.get("BRANCH", "main")
except KeyError:
    st.error("Por favor, configure as chaves 'GITHUB_TOKEN', 'REPO_OWNER', 'REPO_NAME' e 'CSV_PATH' no seu secrets.toml.")
    st.stop() # Interrompe o aplicativo se as chaves essenciais não existirem

COMMIT_MESSAGE = "Atualiza livro caixa via Streamlit" 
COMMIT_MESSAGE_DELETE = "Exclui movimentações do livro caixa" 

ARQ_LOCAL = "livro_caixa.csv"
COLUNAS_PADRAO = ["Data", "Cliente", "Valor", "Forma de Pagamento", "Tipo"]

# ========================================================
# FUNÇÕES DE PERSISTÊNCIA (adaptadas do loja.py)
# ========================================================
def ensure_csv(path: str, columns: list) -> pd.DataFrame:
    """Garante que o CSV exista localmente com as colunas corretas."""
    try:
        df = pd.read_csv(path, dtype=str)
    except Exception:
        df = pd.DataFrame(columns=columns)
        df.to_csv(path, index=False)
    for c in columns:
        if c not in df.columns:
            df[c] = ""
    return df[columns]

def load_csv_github(path: str) -> pd.DataFrame | None:
    """Carrega CSV de repositório privado do GitHub (via token)."""
    try:
        g = Github(TOKEN)
        repo = g.get_user(OWNER).get_repo(REPO_NAME)
        contents = repo.get_contents(path, ref=BRANCH)
        return pd.read_csv(io.StringIO(contents.decoded_content.decode()), dtype=str)
    except Exception as e:
        st.warning(f"Falha ao carregar do GitHub privado: {e}")
        return None

def load_csv_from_url(url: str) -> pd.DataFrame | None:
    """Carrega CSV de repositório público (URL raw)."""
    try:
        return pd.read_csv(url, dtype=str)
    except Exception as e:
        st.warning(f"Falha ao carregar do GitHub público (URL): {e}")
        return None

def carregar_livro_caixa():
    """Orquestra o carregamento: GitHub privado → público → local"""
    # 1. GitHub privado
    df = load_csv_github(CSV_PATH)
    if df is not None:
        return df
    
    # 2. GitHub público (raw)
    url_raw = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/{CSV_PATH}"
    df = load_csv_from_url(url_raw)
    if df is not None:
        return df
    
    # 3. Local (fallback)
    return ensure_csv(ARQ_LOCAL, COLUNAS_PADRAO)

# ========================================================
# FUNÇÃO DE SALVAMENTO (adaptada do loja.py)
# ========================================================
def salvar_dados_no_github(df: pd.DataFrame, commit_message: str):
    """Salva o DataFrame CSV no GitHub e também localmente (backup)."""
    # Backup local
    df.to_csv(ARQ_LOCAL, index=False)

    # Prepara DataFrame para envio ao GitHub
    df_temp = df.copy()
    if 'Data' in df_temp.columns:
        df_temp['Data'] = df_temp['Data'].apply(
            lambda x: x.strftime('%Y-%m-%d') if pd.notnull(x) and hasattr(x, 'strftime') else x
        )

    try:
        g = Github(TOKEN)
        repo = g.get_user(OWNER).get_repo(REPO_NAME)
        csv_string = df_temp.to_csv(index=False)

        try:
            contents = repo.get_contents(CSV_PATH, ref=BRANCH)
            repo.update_file(contents.path, commit_message, csv_string, contents.sha, branch=BRANCH)
            st.success("📁 Dados salvos (atualizados) no GitHub com sucesso!")
        except Exception:
            repo.create_file(CSV_PATH, commit_message, csv_string, branch=BRANCH)
            st.success("📁 Dados salvos (criados) no GitHub com sucesso!")

        return True

    except Exception as e:
        st.error(f"❌ Erro ao salvar no GitHub: {e}")
        return False

# ==================== INTERFACE STREAMLIT ====================
st.set_page_config(layout="wide", page_title="Livro Caixa")
st.title("📘 Livro Caixa - Gerenciamento de Movimentações")

# Usando st.session_state para gerenciar o DataFrame
if "df" not in st.session_state:
    st.session_state.df = carregar_livro_caixa()

# --- Formulário de Nova Movimentação na barra lateral ---
st.sidebar.header("Nova Movimentação")
with st.sidebar.form("form_movimentacao"):
    data_input = st.date_input("Data", datetime.now().date())
    cliente = st.text_input("Nome do Cliente (ou Descrição)")
    valor = st.number_input("Valor (R$)", min_value=0.01, format="%.2f")
    forma_pagamento = st.selectbox("Forma de Pagamento", ["Dinheiro", "Cartão", "PIX", "Transferência", "Outro"])
    tipo = st.radio("Tipo", ["Entrada", "Saída"])
    enviar = st.form_submit_button("Adicionar Movimentação")

# --- Lógica principal ---
if enviar:
    if not cliente or valor <= 0:
        st.sidebar.warning("Por favor, preencha a descrição/cliente e o valor corretamente.")
    else:
        valor_armazenado = valor if tipo == "Entrada" else -valor
        nova_linha = {
            "Data": data_input,
            "Cliente": cliente,
            "Valor": valor_armazenado, 
            "Forma de Pagamento": forma_pagamento,
            "Tipo": tipo
        }
        st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([nova_linha])], ignore_index=True)
        
        if salvar_dados_no_github(st.session_state.df, COMMIT_MESSAGE):
            st.cache_data.clear()
            st.rerun()

# --- Exibição e Análises dos Dados ---
st.subheader("📊 Movimentações Registradas")

if st.session_state.df.empty:
    st.info("Nenhuma movimentação registrada ainda.")
else:
    df_exibicao = st.session_state.df.copy()

# Converte coluna Valor para número
df_exibicao["Valor"] = pd.to_numeric(df_exibicao["Valor"], errors="coerce").fillna(0.0)

try:
    df_exibicao["Data"] = pd.to_datetime(df_exibicao["Data"], errors='coerce').dt.date
    df_exibicao = df_exibicao.sort_values(by="Data", ascending=False).reset_index(drop=True)
    df_exibicao.insert(0, 'ID Visível', df_exibicao.index + 1)
except Exception:
    st.error("Erro ao processar a coluna 'Data'. Verifique o formato do CSV.")

        
    colunas_para_mostrar = ['ID Visível', 'Data', 'Cliente', 'Valor', 'Forma de Pagamento', 'Tipo']

    st.dataframe(
        df_exibicao[colunas_para_mostrar], 
        use_container_width=True,
        column_config={
            "Valor": st.column_config.NumberColumn(
                "Valor (R$)",
                format="R$ %.2f",
            ),
        },
        height=300
    )

    st.markdown("---")
    
    total_entradas = df_exibicao[df_exibicao["Tipo"] == "Entrada"]["Valor"].sum()
    total_saidas = abs(df_exibicao[df_exibicao["Tipo"] == "Saída"]["Valor"].sum()) 
    saldo = df_exibicao["Valor"].sum()

    col1, col2, col3 = st.columns(3)
    col1.metric("Total de Entradas", f"R$ {total_entradas:,.2f}")
    col2.metric("Total de Saídas", f"R$ {total_saidas:,.2f}")
    delta_saldo = f"R$ {saldo:,.2f}"
    col3.metric("💼 Saldo Final", f"R$ {saldo:,.2f}", delta=delta_saldo if saldo != 0 else None, delta_color="normal")

    st.markdown("---")

    # --- EXCLUSÃO ---
    st.markdown("### 🗑️ Excluir Movimentações")
    opcoes_exclusao = {
        f"ID {row['ID Visível']} | {row['Data'].strftime('%d/%m/%Y')} | {row['Cliente']} | R$ {row['Valor']:,.2f}": row.name 
        for index, row in df_exibicao.iterrows()
    }
    movimentacoes_a_excluir_str = st.multiselect(
        "Selecione as movimentações que deseja excluir:",
        options=list(opcoes_exclusao.keys()),
        key="multi_excluir"
    )
    indices_a_excluir = [opcoes_exclusao[s] for s in movimentacoes_a_excluir_str]

    if st.button("Excluir Selecionadas e Salvar no GitHub", type="primary"):
        if indices_a_excluir:
            st.session_state.df = st.session_state.df.drop(indices_a_excluir)
            if salvar_dados_no_github(st.session_state.df, COMMIT_MESSAGE_DELETE):
                st.cache_data.clear()
                st.rerun()
        else:
            st.warning("Selecione pelo menos uma movimentação para excluir.")

    st.markdown("---")

    # --- FILTRAGEM ---
    st.markdown("### 📅 Filtrar por Período")
    col_data_inicial, col_data_final = st.columns(2)
    data_minima = df_exibicao["Data"].min() if not df_exibicao.empty else datetime.now().date()
    data_maxima = df_exibicao["Data"].max() if not df_exibicao.empty else datetime.now().date()
    
    with col_data_inicial:
        data_inicial = st.date_input("Data Inicial", value=data_minima, key="data_ini")
    with col_data_final:
        data_final = st.date_input("Data Final", value=data_maxima, key="data_fim")

    if data_inicial and data_final:
        data_inicial_dt = pd.to_datetime(data_inicial).date()
        data_final_dt = pd.to_datetime(data_final).date()
        
        df_filtrado = df_exibicao[
            (df_exibicao["Data"] >= data_inicial_dt) &
            (df_exibicao["Data"] <= data_final_dt)
        ].copy()
        
        if df_filtrado.empty:
            st.warning("Não há movimentações para o período selecionado.")
        else:
            st.markdown("#### Movimentações no Período Selecionado")
            st.dataframe(df_filtrado[colunas_para_mostrar], use_container_width=True)

            entradas_filtro = df_filtrado[df_filtrado["Tipo"] == "Entrada"]["Valor"].sum()
            saidas_filtro = abs(df_filtrado[df_filtrado["Tipo"] == "Saída"]["Valor"].sum())
            saldo_filtro = df_filtrado["Valor"].sum()

            st.markdown("#### 💰 Resumo do Período")
            col1_f, col2_f, col3_f = st.columns(3)
            col1_f.metric("Entradas", f"R$ {entradas_filtro:,.2f}")
            col2_f.metric("Saídas", f"R$ {saidas_filtro:,.2f}")
            col3_f.metric("Saldo", f"R$ {saldo_filtro:,.2f}")

