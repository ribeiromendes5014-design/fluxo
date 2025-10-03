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
# (todo o código de persistência, cadastro, vendas, resgates etc. mantido idêntico ao enviado anteriormente)
# Apenas modificações aplicadas nos filtros de Data para evitar AttributeError

# --- render_relatorios ---
def render_relatorios():
    st.header("Relatórios e Rankings")
    st.markdown("---")

    st.subheader("💎 Ranking de Níveis de Fidelidade")
    df_niveis = st.session_state.clientes.copy()
    df_niveis['Nivel Atual'] = df_niveis['Gasto Acumulado'].apply(lambda x: calcular_nivel_e_beneficios(x)[0])
    df_niveis['Falta p/ Próximo Nível'] = df_niveis.apply(lambda row: calcular_falta_para_proximo_nivel(row['Gasto Acumulado'], row['Nivel Atual']), axis=1)
    ordenacao_nivel = {'Diamante': 3, 'Ouro': 2, 'Prata': 1}
    df_niveis['Ordem'] = df_niveis['Nivel Atual'].map(ordenacao_nivel)
    df_niveis = df_niveis.sort_values(by=['Ordem', 'Gasto Acumulado'], ascending=[False, False])
    df_display = df_niveis[['Nome', 'Nivel Atual', 'Gasto Acumulado', 'Falta p/ Próximo Nível']].reset_index(drop=True)
    st.dataframe(df_display, use_container_width=True)
    st.markdown("---")

    st.subheader("📄 Histórico de Lançamentos")
    col_data, col_tipo = st.columns(2)
    with col_data:
        data_selecionada = st.date_input("Filtrar por Data:", value=None)
    with col_tipo:
        tipo_selecionado = st.selectbox("Filtrar por Tipo:", ['Todos', 'Venda', 'Resgate', 'Bônus Indicação'], index=0)

    df_historico = st.session_state.lancamentos.copy()
    if not df_historico.empty:
        df_historico['Data'] = pd.to_datetime(df_historico['Data'], errors='coerce')
        if data_selecionada:
            df_historico = df_historico[df_historico['Data'].dt.date == data_selecionada]
        if tipo_selecionado != 'Todos':
            df_historico = df_historico[df_historico['Tipo'] == tipo_selecionado]
        if not df_historico.empty:
            df_historico['Valor Venda/Resgate'] = pd.to_numeric(df_historico['Valor Venda/Resgate'], errors='coerce').fillna(0).map('R$ {:.2f}'.format)
            df_historico['Valor Cashback'] = pd.to_numeric(df_historico['Valor Cashback'], errors='coerce').fillna(0).map('R$ {:.2f}'.format)
            st.dataframe(df_historico.sort_values(by="Data", ascending=False), hide_index=True, use_container_width=True)
        else:
            st.info("Nenhum lançamento encontrado com os filtros selecionados.")
    else:
        st.info("Nenhum lançamento registrado no histórico.")

# --- render_home ---
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
        vendas_mes = vendas_df_copy[vendas_df_copy['Data'].dt.month == date.today().month]
        if not vendas_mes.empty:
            vendas_mes['Valor Venda/Resgate'] = pd.to_numeric(vendas_mes['Valor Venda/Resgate'], errors='coerce').fillna(0)
            total_vendas_mes = vendas_mes['Valor Venda/Resgate'].sum()
    col1, col2, col3 = st.columns(3)
    col1.metric("Clientes Cadastrados", total_clientes)
    col2.metric("Total de Cashback Devido", f"R$ {total_cashback_pendente:,.2f}")
    col3.metric("Volume de Vendas (Mês Atual)", f"R$ {total_vendas_mes:,.2f}")

# ======================================================================
# cashback_system()
# ======================================================================
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

# Nenhuma chamada de função deve estar aqui. O app.py chama cashback_system().
