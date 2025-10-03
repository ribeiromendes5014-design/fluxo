# pages/cashback_system.py (SISTEMA DE CASHBACK - LÓGICA RESTAURADA)

# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from datetime import date, datetime
import requests
from io import StringIO
import io, os
import base64
import pytz

# Tenta importar PyGithub para persistência.
try:
    from github import Github
except ImportError:
    # Classe dummy para evitar crash se PyGithub não estiver instalado
    class Github:
        def __init__(self, token): pass
        def get_repo(self, repo_name): return self
        def get_contents(self, path, ref): return type('Contents', (object,), {'sha': 'dummy_sha'})
        def update_file(self, path, msg, content, sha, branch): pass
        def create_file(self, path, msg, content, sha, branch): pass

# --- Nomes dos arquivos CSV e Configuração ---
CLIENTES_CSV = 'clientes_cash.csv'
LANÇAMENTOS_CSV = 'lancamentos.csv'
PRODUTOS_TURBO_CSV = 'produtos_turbo.csv'
BONUS_INDICACAO_PERCENTUAL = 0.03 # 3% para o indicador
CASHBACK_INDICADO_PRIMEIRA_COMPRA = 0.05 # 5% para o indicado (na primeira compra)

# Configuração do logo para o novo layout
LOGO_DOCEBELLA_URL = "https://i.ibb.co/fYCWBKTm/Logo-Doce-Bella-Cosm-tico.png"

# --- Definição dos Níveis ---
NIVEIS = {
    'Prata': {
        'min_gasto': 0.00, 'max_gasto': 200.00, 'cashback_normal': 0.03,
        'cashback_turbo': 0.03, 'proximo_nivel': 'Ouro'
    },
    'Ouro': {
        'min_gasto': 200.01, 'max_gasto': 1000.00, 'cashback_normal': 0.07,
        'cashback_turbo': 0.10, 'proximo_nivel': 'Diamante'
    },
    'Diamante': {
        'min_gasto': 1000.01, 'max_gasto': float('inf'), 'cashback_normal': 0.15,
        'cashback_turbo': 0.20, 'proximo_nivel': 'Max'
    }
}

# --- Configuração de Persistência (Puxa do st.secrets) ---
try:
    TOKEN = st.secrets["GITHUB_TOKEN"]
    REPO_FULL = st.secrets["REPO_NAME"]
    if "/" in REPO_FULL:
        REPO_OWNER, REPO_NAME = REPO_FULL.split("/")
    else:
        REPO_OWNER = st.secrets["REPO_OWNER"]
        REPO_NAME = REPO_FULL
    BRANCH = st.secrets.get("BRANCH", "main")
    PERSISTENCE_MODE = "GITHUB"
except KeyError:
    PERSISTENCE_MODE = "LOCAL"

if PERSISTENCE_MODE == "GITHUB":
    URL_BASE_REPOS = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{BRANCH}/"

# --- Configuração e Função do Telegram ---
try:
    TELEGRAM_BOT_ID = st.secrets["telegram"]["BOT_ID"]
    TELEGRAM_CHAT_ID = st.secrets["telegram"]["CHAT_ID"]
    TELEGRAM_THREAD_ID = st.secrets["telegram"].get("MESSAGE_THREAD_ID")
    TELEGRAM_ENABLED = True
except KeyError:
    TELEGRAM_ENABLED = False

def enviar_mensagem_telegram(mensagem: str):
    if not TELEGRAM_ENABLED: return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_ID}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': mensagem, 'parse_mode': 'Markdown'}
    if TELEGRAM_THREAD_ID: payload['message_thread_id'] = TELEGRAM_THREAD_ID
    try:
        requests.post(url, data=payload, timeout=5)
    except requests.exceptions.RequestException as e:
        print(f"Erro ao enviar para o Telegram: {e}")

# --- Funções de Persistência, Salvamento e Carregamento ---

def load_csv_github(url: str) -> pd.DataFrame | None:
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return pd.read_csv(StringIO(response.text), dtype=str)
    except Exception:
        return None

def salvar_dados_no_github(df: pd.DataFrame, file_path: str, commit_message: str):
    if PERSISTENCE_MODE != "GITHUB": return False
    df_temp = df.copy()
    for col in ['Data', 'Data Início', 'Data Fim']:
        if col in df_temp.columns:
            df_temp[col] = pd.to_datetime(df_temp[col], errors='coerce').apply(lambda x: x.strftime('%Y-%m-%d') if pd.notna(x) else '')
    try:
        g = Github(TOKEN)
        repo = g.get_repo(f"{REPO_OWNER}/{REPO_NAME}")
        csv_string = df_temp.to_csv(index=False, encoding="utf-8-sig")
        try:
            contents = repo.get_contents(file_path, ref=BRANCH)
            repo.update_file(contents.path, commit_message, csv_string, contents.sha, branch=BRANCH)
            st.toast(f"✅ Arquivo {file_path} atualizado no GitHub.")
        except Exception:
            repo.create_file(file_path, commit_message, csv_string, branch=BRANCH)
            st.toast(f"✅ Arquivo {file_path} criado no GitHub.")
        return True
    except Exception as e:
        st.error(f"❌ ERRO CRÍTICO ao salvar '{file_path}' no GitHub.")
        error_message = str(e)
        if hasattr(e, 'data') and 'message' in e.data: error_message = f"{e.status} - {e.data['message']}"
        st.error(f"Detalhes: {error_message}")
        print(f"--- ERRO DETALHADO GITHUB [{file_path}] ---\n{repr(e)}\n-----------------------------------------")
        return False

def salvar_dados():
    if PERSISTENCE_MODE == "GITHUB":
        salvar_dados_no_github(st.session_state.clientes, CLIENTES_CSV, "AUTOSAVE: Clientes")
        salvar_dados_no_github(st.session_state.lancamentos, LANÇAMENTOS_CSV, "AUTOSAVE: Lançamentos")
        salvar_dados_no_github(st.session_state.produtos_turbo, PRODUTOS_TURBO_CSV, "AUTOSAVE: Produtos Turbo")
    else:
        st.session_state.clientes.to_csv(CLIENTES_CSV, index=False)
        st.session_state.lancamentos.to_csv(LANÇAMENTOS_CSV, index=False)
        st.session_state.produtos_turbo.to_csv(PRODUTOS_TURBO_CSV, index=False)
    st.cache_data.clear()

@st.cache_data(show_spinner="Carregando dados dos arquivos...")
def carregar_dados():
    def carregar_dados_do_csv(file_path, df_columns):
        df = pd.DataFrame(columns=df_columns)
        if PERSISTENCE_MODE == "GITHUB":
            url_raw = f"{URL_BASE_REPOS}{file_path}"
            df_carregado = load_csv_github(url_raw)
            if df_carregado is not None: df = df_carregado
        elif os.path.exists(file_path):
            try: df = pd.read_csv(file_path, dtype=str)
            except pd.errors.EmptyDataError: pass
        for col in df_columns:
            if col not in df.columns: df[col] = ""
        if 'Cashback Disponível' in df.columns: df['Cashback Disponível'] = df['Cashback Disponível'].fillna('0.0')
        if 'Gasto Acumulado' in df.columns: df['Gasto Acumulado'] = df['Gasto Acumulado'].fillna('0.0')
        if 'Nivel Atual' in df.columns: df['Nivel Atual'] = df['Nivel Atual'].fillna('Prata')
        if 'Indicado Por' in df.columns: df['Indicado Por'] = df['Indicado Por'].fillna('')
        if 'Primeira Compra Feita' in df.columns: df['Primeira Compra Feita'] = df['Primeira Compra Feita'].fillna('False')
        if 'Venda Turbo' in df.columns: df['Venda Turbo'] = df['Venda Turbo'].fillna('Não')
        return df[df_columns]

    CLIENTES_COLS = ['Nome', 'Apelido/Descrição', 'Telefone', 'Cashback Disponível', 'Gasto Acumulado', 'Nivel Atual', 'Indicado Por', 'Primeira Compra Feita']
    df_clientes = carregar_dados_do_csv(CLIENTES_CSV, CLIENTES_COLS)
    df_clientes['Cashback Disponível'] = pd.to_numeric(df_clientes['Cashback Disponível'], errors='coerce').fillna(0.0)
    df_clientes['Gasto Acumulado'] = pd.to_numeric(df_clientes['Gasto Acumulado'], errors='coerce').fillna(0.0)
    df_clientes['Primeira Compra Feita'] = df_clientes['Primeira Compra Feita'].astype(str).str.lower().map({'true': True, 'false': False}).fillna(False).astype(bool)
    df_clientes['Nivel Atual'] = df_clientes['Nivel Atual'].fillna('Prata')

    LANÇAMENTOS_COLS = ['Data', 'Cliente', 'Tipo', 'Valor Venda/Resgate', 'Valor Cashback', 'Venda Turbo']
    df_lancamentos = carregar_dados_do_csv(LANÇAMENTOS_CSV, LANÇAMENTOS_COLS)
    if not df_lancamentos.empty:
        df_lancamentos['Data'] = pd.to_datetime(df_lancamentos['Data'], errors='coerce').dt.date
        df_lancamentos['Venda Turbo'] = df_lancamentos['Venda Turbo'].astype(str).replace({'True': 'Sim', 'False': 'Não', '': 'Não'}).fillna('Não')

    PRODUTOS_TURBO_COLS = ['Nome Produto', 'Data Início', 'Data Fim', 'Ativo']
    df_produtos_turbo = carregar_dados_do_csv(PRODUTOS_TURBO_CSV, PRODUTOS_TURBO_COLS)
    if not df_produtos_turbo.empty:
        df_produtos_turbo['Data Início'] = pd.to_datetime(df_produtos_turbo['Data Início'], errors='coerce')
        df_produtos_turbo['Data Fim'] = pd.to_datetime(df_produtos_turbo['Data Fim'], errors='coerce')
        df_produtos_turbo['Ativo'] = df_produtos_turbo['Ativo'].astype(str).str.lower().map({'true': True, 'false': False}).fillna(False).astype(bool)

    return df_clientes, df_lancamentos, df_produtos_turbo

# ... [O RESTO DO ARQUIVO CONTINUA IGUAL ATÉ O render_home]

def render_home():
    st.header("Seja Bem-Vinda ao Painel de Gestão de Cashback Doce&Bella!")
    st.markdown("---")

    total_clientes = len(st.session_state.clientes)
    total_cashback_pendente = st.session_state.clientes['Cashback Disponível'].sum()
    
    vendas_df = st.session_state.lancamentos[st.session_state.lancamentos['Tipo'] == 'Venda']
    
    total_vendas_mes = 0.0
    
    if not vendas_df.empty:
        vendas_df_copy = vendas_df.copy()
        vendas_df_copy['Data'] = pd.to_datetime(vendas_df_copy['Data'], errors='coerce')
        
        # CORREÇÃO: usar .dt.month em vez de apply com lambda
        vendas_mes = vendas_df_copy[vendas_df_copy['Data'].dt.month == date.today().month]
        
        if not vendas_mes.empty:
            vendas_mes['Valor Venda/Resgate'] = pd.to_numeric(vendas_mes['Valor Venda/Resgate'], errors='coerce').fillna(0)
            total_vendas_mes = vendas_mes['Valor Venda/Resgate'].sum()

    col1, col2, col3 = st.columns(3)
    
    col1.metric("Clientes Cadastrados", total_clientes)
    col2.metric("Total de Cashback Devido", f"R$ {total_cashback_pendente:,.2f}")
    col3.metric("Volume de Vendas (Mês Atual)", f"R$ {total_vendas_mes:,.2f}")

    st.markdown("---")
    st.markdown("### Próximos Passos Rápidos")
    
    col_nav1, col_nav2, col_nav3 = st.columns(3)
    
    if 'cashback_tab_atual' not in st.session_state:
        st.session_state.cashback_tab_atual = "Home"

    if col_nav1.button("▶️ Lançar Nova Venda", use_container_width=True):
        st.session_state.cashback_tab_atual = "Lançamento"
        st.rerun()
    
    if col_nav2.button("👥 Cadastrar Nova Cliente", use_container_width=True):
        st.session_state.cashback_tab_atual = "Cadastro"
        st.rerun()

    if col_nav3.button("📈 Ver Relatórios de Vendas", use_container_width=True):
        st.session_state.cashback_tab_atual = "Relatórios"
        st.rerun()

# ==============================================================================

def cashback_system():
    st.markdown("""
        <style>
        button[data-baseweb="tab"] {
            min-width: 150px !important;
            padding: 10px 20px !important;
            font-size: 16px !important;
            font-weight: bold !important;
        }
        div[role="tablist"] {
            border-bottom: 2px solid #E91E63;
        }
        </style>
    """, unsafe_allow_html=True)
    
    if 'editing_client' not in st.session_state: st.session_state.editing_client = False
    if 'deleting_client' not in st.session_state: st.session_state.deleting_client = False
    if 'valor_venda' not in st.session_state: st.session_state.valor_venda = 0.00
    if 'data_version' not in st.session_state: st.session_state.data_version = 0
    if 'clientes' not in st.session_state or 'cashback_tab_atual' not in st.session_state:
        st.session_state.clientes, st.session_state.lancamentos, st.session_state.produtos_turbo = carregar_dados()
        st.session_state.cashback_tab_atual = "Home"

    PAGINAS_INTERNAS = {
        "Home": render_home, "Lançamento": render_lancamento, "Cadastro": render_cadastro,
        "Produtos Turbo": render_produtos_turbo, "Relatórios": render_relatorios
    }
    
    tab_list = ["Home", "Lançamento", "Cadastro", "Produtos Turbo", "Relatórios"]
    
    default_index = tab_list.index(st.session_state.cashback_tab_atual) if st.session_state.cashback_tab_atual in tab_list else 0
    
    selected_tab_name = st.tabs(tab_list)

    with selected_tab_name[0]:
        PAGINAS_INTERNAS["Home"]()
    with selected_tab_name[1]:
        PAGINAS_INTERNAS["Lançamento"]()
    with selected_tab_name[2]:
        PAGINAS_INTERNAS["Cadastro"]()
    with selected_tab_name[3]:
        PAGINAS_INTERNAS["Produtos Turbo"]()
    with selected_tab_name[4]:
        PAGINAS_INTERNAS["Relatórios"]()
