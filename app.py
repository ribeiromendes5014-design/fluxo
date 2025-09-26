import streamlit as st
import pandas as pd
from datetime import datetime
import requests
from io import StringIO
# Importa a biblioteca PyGithub para um gerenciamento de persistência mais fácil
from github import Github 

# ==================== CONFIGURAÇÕES DO APLICATIVO ====================
# Certifique-se de que os segredos do Streamlit (secrets.toml) contenham:
# GITHUB_TOKEN, REPO_OWNER, REPO_NAME, CSV_PATH, e opcionalmente BRANCH.

# Configurações do GitHub (adaptadas para PyGithub)
TOKEN = st.secrets["GITHUB_TOKEN"]
OWNER = st.secrets["REPO_OWNER"]
REPO_NAME = st.secrets["REPO_NAME"] # Renomeado para clareza
CSV_PATH = st.secrets["CSV_PATH"]
COMMIT_MESSAGE = "Atualiza livro caixa via Streamlit"
COMMIT_MESSAGE_DELETE = "Exclui movimentações do livro caixa" 
BRANCH = st.secrets.get("BRANCH", "main")

# ==================== FUNÇÕES DE INTERAÇÃO COM O GITHUB ====================

@st.cache_data(show_spinner="Carregando dados do GitHub...")
def carregar_dados_do_github():
    """
    Carrega o arquivo CSV do GitHub.
    Usa a URL raw, pois o carregamento por token é mais complexo e não
    necessário para este caso, mas mantive a detecção de 404.
    """
    url_raw = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/{CSV_PATH}"
    try:
        response = requests.get(url_raw)
        response.raise_for_status()
        # Se não houver problema, carrega o DataFrame
        df = pd.read_csv(StringIO(response.text), parse_dates=["Data"])
        # Garante a coluna 'Data' como datetime para futuras comparações
        df['Data'] = pd.to_datetime(df['Data'], errors='coerce').dt.date
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

# ========================================================
# FUNÇÃO DE SALVAMENTO COM PyGithub (Similar ao seu loja.py)
# ========================================================
def salvar_dados_no_github(df: pd.DataFrame, commit_message: str):
    """
    Salva o DataFrame CSV no GitHub usando a biblioteca PyGithub.
    Essa função lida com a criação e atualização do arquivo (commit).
    """
    # ⚠️ Converte a coluna 'Data' para string no formato YYYY-MM-DD para salvar
    df_temp = df.copy()
    if 'Data' in df_temp.columns:
        # Tenta formatar datas que são objetos date/datetime para string
        df_temp['Data'] = df_temp['Data'].apply(
            lambda x: x.strftime('%Y-%m-%d') if pd.notnull(x) and hasattr(x, 'strftime') else x
        )
        
    try:
        g = Github(TOKEN)
        repo = g.get_user(OWNER).get_repo(REPO_NAME)
        
        # Converte o DataFrame para string CSV
        csv_string = df_temp.to_csv(index=False)

        # 1. Tenta obter o conteúdo atual do arquivo (para pegar o SHA)
        try:
            contents = repo.get_contents(CSV_PATH, ref=BRANCH)
            sha = contents.sha
            # 2. Atualiza o arquivo (PUT)
            repo.update_file(CSV_PATH, commit_message, csv_string, sha, branch=BRANCH)
            st.success("📁 Dados salvos (atualizados) no GitHub com sucesso!")
        except Exception as e:
            # 3. Cria o arquivo (POST, se falhar ao obter SHA ou arquivo não existe)
            if "Not Found" in str(e) or sha is None:
                 repo.create_file(CSV_PATH, commit_message, csv_string, branch=BRANCH)
                 st.success("📁 Dados salvos (criados) no GitHub com sucesso!")
            else:
                 raise e # Se for outro erro, levanta a exceção

        return True

    except Exception as e:
        st.error(f"❌ Erro ao salvar no GitHub: {e}")
        return False

# ==================== INTERFACE STREAMLIT ====================
st.title("📘 Livro Caixa - Streamlit + GitHub (PyGithub)")

# Usando st.session_state para gerenciar o DataFrame
if "df" not in st.session_state:
    st.session_state.df = carregar_dados_do_github()

# --- Formulário de Nova Movimentação na barra lateral ---
st.sidebar.header("Nova Movimentação")
with st.sidebar.form("form_movimentacao"):
    data_input = st.date_input("Data", datetime.now().date())
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
        # A coluna 'Valor' é o valor em si
        novo_valor = valor 
        
        nova_linha = {
            "Data": data_input, # Salva como objeto date
            "Cliente": cliente,
            # Se for Saída, o valor é armazenado negativamente para o cálculo do saldo
            "Valor": novo_valor if tipo == "Entrada" else -novo_valor, 
            "Forma de Pagamento": forma_pagamento,
            "Tipo": tipo
        }
        st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([nova_linha])], ignore_index=True)
        if salvar_dados_no_github(st.session_state.df, COMMIT_MESSAGE):
            # Limpa o cache para forçar o recarregamento dos dados
            st.cache_data.clear()
            st.rerun()

# --- Exibição e Análises dos Dados ---
st.subheader("📊 Movimentações Registradas")
if st.session_state.df.empty:
    st.info("Nenhuma movimentação registrada ainda.")
else:
    df_exibicao = st.session_state.df.copy()
    
    # Garante a ordenação pela coluna 'Data'
    try:
        df_exibicao["Data"] = pd.to_datetime(df_exibicao["Data"], errors='coerce').dt.date
        df_exibicao = df_exibicao.sort_values(by="Data", ascending=False)
    except Exception:
        st.warning("Erro ao tentar converter coluna 'Data'. Verifique a integridade do CSV.")
        
    st.dataframe(df_exibicao, use_container_width=True)

    st.markdown("---")
    st.markdown("### 🗑️ Excluir Movimentações")
    # Cria a lista de opções para multiselect
    opcoes_exclusao = {
        f"ID: {index} - Data: {row['Data'].strftime('%d/%m/%Y') if pd.notnull(row['Data']) else 'Inválida'} - {row['Cliente']} - R$ {row['Valor']:,.2f}": index
        for index, row in st.session_state.df.iterrows()
    }
    movimentacoes_a_excluir_str = st.multiselect(
        "Selecione as movimentações que deseja excluir:",
        options=list(opcoes_exclusao.keys())
    )
    indices_a_excluir = [opcoes_exclusao[s] for s in movimentacoes_a_excluir_str]

    if st.button("Excluir Selecionadas"):
        if indices_a_excluir:
            # ⚠️ Usa st.session_state.df (original) para o drop pelo índice
            st.session_state.df = st.session_state.df.drop(indices_a_excluir)
            if salvar_dados_no_github(st.session_state.df, COMMIT_MESSAGE_DELETE):
                st.cache_data.clear()
                st.rerun()
        else:
            st.warning("Selecione pelo menos uma movimentação para excluir.")

    st.markdown("---")
    st.markdown("### 💰 Resumo Financeiro")
    
    # Cálculo do saldo usando a coluna 'Valor' (que já armazena Saídas como negativo)
    total_entradas = df_exibicao[df_exibicao["Tipo"] == "Entrada"]["Valor"].sum()
    # O valor absoluto é usado para mostrar apenas o total das saídas
    total_saidas = abs(df_exibicao[df_exibicao["Tipo"] == "Saída"]["Valor"].sum()) 
    saldo = df_exibicao["Valor"].sum()

    col1, col2, col3 = st.columns(3)
    col1.metric("Total de Entradas", f"R$ {total_entradas:,.2f}")
    col2.metric("Total de Saídas", f"R$ {total_saidas:,.2f}")
    col3.metric("💼 Saldo Final", f"R$ {saldo:,.2f}", delta_color="normal")

    st.markdown("---")
    st.markdown("### 📅 Filtrar por Período")
    col_data_inicial, col_data_final = st.columns(2)
    
    # As datas máximas/mínimas precisam ser formatadas como date para o date_input
    data_minima = df_exibicao["Data"].min() if not df_exibicao.empty else datetime.now().date()
    data_maxima = df_exibicao["Data"].max() if not df_exibicao.empty else datetime.now().date()
    
    with col_data_inicial:
        data_inicial = st.date_input("Data Inicial", value=data_minima, key="data_ini")
    with col_data_final:
        data_final = st.date_input("Data Final", value=data_maxima, key="data_fim")

    if data_inicial and data_final:
        # Garante que as datas de comparação estejam no formato datetime.date
        data_inicial_dt = pd.to_datetime(data_inicial).date()
        data_final_dt = pd.to_datetime(data_final).date()
        
        df_filtrado = df_exibicao[
            (df_exibicao["Data"] >= data_inicial_dt) &
            (df_exibicao["Data"] <= data_final_dt)
        ]
        
        if df_filtrado.empty:
            st.warning("Não há movimentações para o período selecionado.")
        else:
            st.dataframe(df_filtrado, use_container_width=True)

            # Recálculo do resumo para o período filtrado
            entradas_filtro = df_filtrado[df_filtrado["Tipo"] == "Entrada"]["Valor"].sum()
            saidas_filtro = abs(df_filtrado[df_filtrado["Tipo"] == "Saída"]["Valor"].sum())
            saldo_filtro = df_filtrado["Valor"].sum()

            st.markdown("#### 💼 Resumo do Período Filtrado")
            col1_f, col2_f, col3_f = st.columns(3)
            col1_f.metric("Entradas", f"R$ {entradas_filtro:,.2f}")
            col2_f.metric("Saídas", f"R$ {saidas_filtro:,.2f}")
            col3_f.metric("Saldo", f"R$ {saldo_filtro:,.2f}")
