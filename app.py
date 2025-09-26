import streamlit as st
import pandas as pd
from datetime import datetime
import requests
from io import StringIO
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

# ==================== FUNÇÕES DE INTERAÇÃO COM O GITHUB ====================

@st.cache_data(show_spinner="Carregando dados do GitHub...")
def carregar_dados_do_github():
    """
    Carrega o arquivo CSV do GitHub usando a URL de conteúdo bruto.
    Essa abordagem é padrão e evita o uso da API do GitHub para leitura, 
    o que é mais eficiente para arquivos públicos ou lidos via URL raw.
    """
    url_raw = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/{CSV_PATH}"
    try:
        response = requests.get(url_raw)
        response.raise_for_status() # Levanta um erro para códigos de status HTTP ruins (4xx ou 5xx)
        
        # Se a resposta for bem-sucedida, carrega o DataFrame
        df = pd.read_csv(StringIO(response.text))
        
        # Garante a coluna 'Data' no formato datetime.date para facilitar comparações
        if 'Data' in df.columns:
            # Converte a coluna para datetime e depois para date object
            df['Data'] = pd.to_datetime(df['Data'], errors='coerce').dt.date
        
        # Garante as colunas necessárias para um novo arquivo, se o CSV estiver vazio
        required_cols = ["Data", "Cliente", "Valor", "Forma de Pagamento", "Tipo"]
        for col in required_cols:
            if col not in df.columns:
                df[col] = None 
                
        return df
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            st.info("Arquivo CSV não encontrado no GitHub. Criando um novo DataFrame localmente.")
            # Retorna um DataFrame vazio com as colunas corretas e tipos esperados
            return pd.DataFrame(columns=["Data", "Cliente", "Valor", "Forma de Pagamento", "Tipo"])
        else:
            st.error(f"Erro HTTP ao carregar dados do GitHub: {e}")
            return pd.DataFrame(columns=["Data", "Cliente", "Valor", "Forma de Pagamento", "Tipo"])
    except Exception as e:
        st.error(f"Ocorreu um erro inesperado ao carregar os dados: {e}")
        return pd.DataFrame(columns=["Data", "Cliente", "Valor", "Forma de Pagamento", "Tipo"])

# ========================================================
# FUNÇÃO DE SALVAMENTO COM PyGithub (Pegando o melhor do loja.py)
# ========================================================
def salvar_dados_no_github(df: pd.DataFrame, commit_message: str):
    """
    Salva o DataFrame CSV no GitHub usando a biblioteca PyGithub.
    Lida com a obtenção do SHA e a criação/atualização do arquivo (commit).
    """
    # Cria uma cópia temporária do DataFrame para manipulação antes de salvar
    df_temp = df.copy()
    
    # Prepara a coluna 'Data' para o salvamento em CSV (string YYYY-MM-DD)
    if 'Data' in df_temp.columns:
        # Tenta formatar objetos date/datetime para string
        df_temp['Data'] = df_temp['Data'].apply(
            lambda x: x.strftime('%Y-%m-%d') if pd.notnull(x) and hasattr(x, 'strftime') else x
        )
        
    try:
        g = Github(TOKEN)
        # Tenta obter o repositório
        repo = g.get_user(OWNER).get_repo(REPO_NAME)
        
        # Converte o DataFrame para string CSV
        csv_string = df_temp.to_csv(index=False)

        # 1. Tenta obter o conteúdo atual do arquivo (para pegar o SHA)
        sha = None
        try:
            contents = repo.get_contents(CSV_PATH, ref=BRANCH)
            sha = contents.sha
            # 2. Atualiza o arquivo (PUT)
            repo.update_file(CSV_PATH, commit_message, csv_string, sha, branch=BRANCH)
            st.success("📁 Dados salvos (atualizados) no GitHub com sucesso!")
        except Exception as e:
            # Se 'Not Found' ou SHA for None (arquivo não existe)
            if "Not Found" in str(e) or sha is None:
                 repo.create_file(CSV_PATH, commit_message, csv_string, branch=BRANCH)
                 st.success("📁 Dados salvos (criados) no GitHub com sucesso!")
            else:
                 # Se for outro erro, levanta a exceção
                 raise e 

        return True

    except Exception as e:
        st.error(f"❌ Erro ao salvar no GitHub: {e}")
        st.error("Verifique se seu 'GITHUB_TOKEN' tem permissões de escrita ('repo' scope) e se o nome do repositório/proprietário está correto.")
        return False

# ==================== INTERFACE STREAMLIT ====================
st.set_page_config(layout="wide", page_title="Livro Caixa")
st.title("📘 Livro Caixa - Gerenciamento de Movimentações")

# Usando st.session_state para gerenciar o DataFrame
if "df" not in st.session_state:
    st.session_state.df = carregar_dados_do_github()

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
        # Armazena Saída como valor negativo para facilitar o cálculo do Saldo
        valor_armazenado = valor if tipo == "Entrada" else -valor
        
        nova_linha = {
            "Data": data_input, # Objeto date
            "Cliente": cliente,
            "Valor": valor_armazenado, 
            "Forma de Pagamento": forma_pagamento,
            "Tipo": tipo
        }
        
        # Concatena a nova linha e salva o estado
        st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([nova_linha])], ignore_index=True)
        
        # Tenta salvar no GitHub
        if salvar_dados_no_github(st.session_state.df, COMMIT_MESSAGE):
            # Limpa o cache para garantir que o próximo carregamento pegue o novo CSV
            st.cache_data.clear()
            st.rerun()

# --- Exibição e Análises dos Dados ---
st.subheader("📊 Movimentações Registradas")

if st.session_state.df.empty:
    st.info("Nenhuma movimentação registrada ainda.")
else:
    df_exibicao = st.session_state.df.copy()
    
    # 1. Garante que a coluna 'Data' é date e ordena
    try:
        # Primeiro, trata possíveis nulos ou erros de conversão
        df_exibicao["Data"] = pd.to_datetime(df_exibicao["Data"], errors='coerce').dt.date
        df_exibicao = df_exibicao.sort_values(by="Data", ascending=False).reset_index(drop=True)
        # Adiciona um ID de visualização
        df_exibicao.insert(0, 'ID Visível', df_exibicao.index + 1)
        
    except Exception:
        st.error("Erro ao processar a coluna 'Data'. Verifique o formato do CSV.")
        
    # Colunas a serem exibidas no Dataframe
    colunas_para_mostrar = ['ID Visível', 'Data', 'Cliente', 'Valor', 'Forma de Pagamento', 'Tipo']
    
    # Formatação condicional para o valor
    def color_valor(val):
        """Colorir o valor com base no tipo (Entrada/Saída)"""
        # A coluna Tipo é usada para colorir, mas o valor exibido é o 'Valor'
        color = 'green' if val > 0 else 'red'
        return f'color: {color}'

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
    
    # --- RESUMO E SALDO ---
    total_entradas = df_exibicao[df_exibicao["Tipo"] == "Entrada"]["Valor"].sum()
    # Usa abs() para mostrar Saídas como um valor positivo no resumo
    total_saidas = abs(df_exibicao[df_exibicao["Tipo"] == "Saída"]["Valor"].sum()) 
    saldo = df_exibicao["Valor"].sum()

    col1, col2, col3 = st.columns(3)
    col1.metric("Total de Entradas", f"R$ {total_entradas:,.2f}")
    col2.metric("Total de Saídas", f"R$ {total_saidas:,.2f}")
    
    # Exibe Saldo com delta para indicar se está positivo/negativo
    delta_saldo = f"R$ {saldo:,.2f}"
    col3.metric(
        "💼 Saldo Final", 
        f"R$ {saldo:,.2f}", 
        delta=delta_saldo if saldo != 0 else None, 
        delta_color="normal"
    )

    st.markdown("---")

    # --- EXCLUSÃO ---
    st.markdown("### 🗑️ Excluir Movimentações")
    
    # Cria uma lista de chaves de DataFrame original (índices) para mapear a seleção
    # Usa o 'ID Visível' para seleção, mas o drop será feito no índice original
    opcoes_exclusao = {
        f"ID {row['ID Visível']} | {row['Data'].strftime('%d/%m/%Y')} | {row['Cliente']} | R$ {row['Valor']:,.2f}": row.name 
        for index, row in df_exibicao.iterrows()
    }
    
    movimentacoes_a_excluir_str = st.multiselect(
        "Selecione as movimentações que deseja excluir:",
        options=list(opcoes_exclusao.keys()),
        key="multi_excluir"
    )
    
    # Mapeia as strings selecionadas de volta para os índices originais do DataFrame
    indices_a_excluir = [opcoes_exclusao[s] for s in movimentacoes_a_excluir_str]

    if st.button("Excluir Selecionadas e Salvar no GitHub", type="primary"):
        if indices_a_excluir:
            # Drop dos índices originais no DataFrame da sessão
            st.session_state.df = st.session_state.df.drop(indices_a_excluir)
            
            # Tenta salvar no GitHub
            if salvar_dados_no_github(st.session_state.df, COMMIT_MESSAGE_DELETE):
                st.cache_data.clear() # Limpa o cache após a gravação
                st.rerun()
        else:
            st.warning("Selecione pelo menos uma movimentação para excluir.")

    st.markdown("---")

    # --- FILTRAGEM ---
    st.markdown("### 📅 Filtrar por Período")
    col_data_inicial, col_data_final = st.columns(2)
    
    # As datas máximas/mínimas precisam ser formatadas como date
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
        ].copy() # Cópia para evitar SettingWithCopyWarning
        
        if df_filtrado.empty:
            st.warning("Não há movimentações para o período selecionado.")
        else:
            st.markdown("#### Movimentações no Período Selecionado")
            st.dataframe(df_filtrado[colunas_para_mostrar], use_container_width=True)

            # Recálculo do resumo para o período filtrado
            entradas_filtro = df_filtrado[df_filtrado["Tipo"] == "Entrada"]["Valor"].sum()
            saidas_filtro = abs(df_filtrado[df_filtrado["Tipo"] == "Saída"]["Valor"].sum())
            saldo_filtro = df_filtrado["Valor"].sum()

            st.markdown("#### 💰 Resumo do Período")
            col1_f, col2_f, col3_f = st.columns(3)
            col1_f.metric("Entradas", f"R$ {entradas_filtro:,.2f}")
            col2_f.metric("Saídas", f"R$ {saidas_filtro:,.2f}")
            col3_f.metric("Saldo", f"R$ {saldo_filtro:,.2f}")
