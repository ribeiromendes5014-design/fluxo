# constants_and_css.py

import streamlit as st
from datetime import datetime, timedelta, date
import calendar
import pandas as pd
import json
import hashlib

# ==================== CONSTANTES DE NEGÓCIO E ARQUIVOS ====================
FATOR_CARTAO = 0.8872
LOJAS_DISPONIVEIS = ["Doce&bella", "Papelaria", "Fotografia", "Outro"]
CATEGORIAS_SAIDA = ["Aluguel", "Salários/Pessoal", "Marketing/Publicidade", "Fornecedores/Matéria Prima", "Despesas Fixas", "Impostos/Taxas", "Outro/Diversos", "Não Categorizado"]
FORMAS_PAGAMENTO = ["Dinheiro", "Cartão", "PIX", "Transferência", "Outro"]
COLUNAS_PADRAO = ["Data", "Loja", "Cliente", "Valor", "Forma de Pagamento", "Tipo", "Produtos Vendidos", "Categoria", "Status", "Data Pagamento"]
COLUNAS_PADRAO_COMPLETO = COLUNAS_PADRAO + ["RecorrenciaID", "TransacaoPaiID"]
COLUNAS_COMPLETAS_PROCESSADAS = COLUNAS_PADRAO + ["ID Visível", "original_index", "Data_dt", "Saldo Acumulado", "Cor_Valor"]
COLUNAS_PRODUTOS = [
    "ID", "Nome", "Marca", "Categoria", "Quantidade", "PrecoCusto", 
    "PrecoVista", "PrecoCartao", "Validade", "FotoURL", "CodigoBarras", "PaiID"
]
COLUNAS_COMPRAS = ["Data", "Produto", "Quantidade", "Valor Total", "Cor", "FotoURL"] 

# GITHUB SECRETS (mantido o bloco try/except)
try:
    TOKEN = st.secrets["GITHUB_TOKEN"]
    OWNER = st.secrets["REPO_OWNER"]
    REPO_NAME = st.secrets["REPO_NAME"]
    CSV_PATH = st.secrets["CSV_PATH"] 
    BRANCH = st.secrets.get("BRANCH", "main")
    GITHUB_TOKEN = TOKEN
    GITHUB_REPO = f"{OWNER}/{REPO_NAME}"
    GITHUB_BRANCH = BRANCH
except KeyError:
    TOKEN = "TOKEN_FICTICIO"
    OWNER = "user"
    REPO_NAME = "repo_default"
    CSV_PATH = "contas_a_pagar_receber.csv"
    BRANCH = "main"
    GITHUB_TOKEN = TOKEN
    GITHUB_REPO = f"{OWNER}/{REPO_NAME}"
    GITHUB_BRANCH = BRANCH

# Caminhos dos arquivos no repositório
URL_BASE_REPOS = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/"
ARQ_PRODUTOS = "produtos_estoque.csv"
ARQ_LOCAL = "livro_caixa.csv"
PATH_DIVIDAS = CSV_PATH
ARQ_COMPRAS = "historico_compras.csv"
ARQ_PROMOCOES = "promocoes.csv" 
COMMIT_MESSAGE = "Atualiza livro caixa via Streamlit (com produtos/categorias)"
COMMIT_MESSAGE_DELETE = "Exclui movimentações do livro caixa"
COMMIT_MESSAGE_EDIT = "Edita movimentação via Streamlit"
COMMIT_MESSAGE_DEBT_REALIZED = "Conclui dívidas pendentes"
COMMIT_MESSAGE_PROD = "Atualização automática de estoque/produtos"

LOGO_DOCEBELLA_URL = "https://i.ibb.co/cdqJ92W/logo_docebella.png"
URL_MAIS_VENDIDOS = "https://d1a9qnv764bsoo.cloudfront.net/stores/002/838/949/rte/mid-queridinhos1.png"
URL_OFERTAS = "https://d1a9qnv764bsoo.cloudfront.net/stores/002/838/949/rte/mid-oferta.png"   
URL_NOVIDADES = "https://d1a9qnv764bsoo.cloudfront.net/stores/002/838/949/rte/mid-novidades.png"


# ==================== FUNÇÕES DE CONFIGURAÇÃO DO APP ====================

def render_global_config():
    """Define a configuração da página e injeta o CSS customizado."""
    st.set_page_config(
        layout="wide", 
        page_title="Doce&Bella | Gestão Financeira", 
        page_icon="🌸"
    )

    # Adiciona CSS para simular a navegação no topo e o tema pink/magenta
    st.markdown("""
        <style>
        /* 1. Oculta o menu padrão do Streamlit e o footer */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        
        /* 2. Estilo Global e Cor de Fundo do Header (simulando a barra superior) */
        .stApp {
            background-color: #f7f7f7; /* Fundo mais claro */
        }
        
        /* 3. Container customizado do Header (cor Magenta da Loja) */
        div.header-container {
            padding: 10px 0;
            background-color: #E91E63; /* Cor Magenta Forte */
            color: white;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            display: flex;
            justify-content: space-between;
            align-items: center;
            width: 100%;
        }
        
        /* 4. Estilo dos botões/abas de Navegação (dentro do header) */
        .nav-button-group {
            display: flex;
            gap: 20px;
            align-items: center;
            padding-right: 20px;
        }
        
        /* CORREÇÃO CRÍTICA: Garante que o texto dentro dos botões do Streamlit não quebre */
        .stButton > button {
            white-space: nowrap !important; /* MANTÉM O TEXTO EM UMA ÚNICA LINHA */
            overflow: hidden !important;
            text-overflow: ellipsis !important;
        }
        
        /* Oculta a Sidebar */
        [data-testid="stSidebar"] {
            visibility: hidden; 
            width: 0px !important; 
        }

        /* ---------------------------------------------------- */
        /* CORREÇÕES FINAIS: OCULTAR BOTÕES PADRÃO DO STREAMLIT */
        /* ---------------------------------------------------- */
        
        /* OCULTA O MENU SUPERIOR (GITHUB/FORK E 3 PONTOS) */
        [data-testid="stToolbar"] {
            display: none !important; 
            height: 0px !important;
        }
        
        /* OCULTA O BOTÃO DE AÇÃO/DEPLOY (COROA/FEEDBACK NO CANTO INFERIOR) */
        /* Usa o seletor universal para todos os botões de ação fixos */
        .stActionButton {
            display: none !important;
        }
        
        /* Estilos adicionais para o corpo do app (mantidos) */
        .homepage-title { color: #E91E63; font-size: 3em; font-weight: 700; text-shadow: 2px 2px #fbcfe8; }
        .homepage-subtitle { color: #880E4F; font-size: 1.5em; margin-top: -10px; margin-bottom: 20px; }
        .insta-card { background-color: white; border-radius: 15px; overflow: hidden; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1); padding: 15px; height: 100%; display: flex; flex-direction: column; justify-content: space-between; }
        .insta-header { display: flex; align-items: center; font-weight: bold; color: #E91E63; margin-bottom: 10px; }
        .product-card { background-color: white; border-radius: 10px; padding: 15px; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08); text-align: center; height: 100%; width: 250px; flex-shrink: 0; margin-right: 15px; display: flex; flex-direction: column; justify-content: space-between; transition: transform 0.2s; }
        .product-card:hover { transform: translateY(-5px); }
        .buy-button { background-color: #E91E63; color: white; font-weight: bold; border-radius: 20px; border: none; padding: 8px 15px; cursor: pointer; width: 100%; margin-top: 10px; }
        .carousel-outer-container { width: 100%; overflow-x: auto; padding-bottom: 20px; }
        .product-wrapper { display: flex; flex-direction: row; justify-content: flex-start; gap: 15px; padding: 0 50px; min-width: fit-content; margin: 0 auto; }
        .section-header-img { max-width: 400px; height: auto; display: block; margin: 0 auto 10px; }

        </style>
    """, unsafe_allow_html=True)


def render_header(paginas_ordenadas, paginas_map):
    """Renderiza o header customizado com a navegação em botões."""
    
    col_logo, col_nav = st.columns([1, 5.5])
    
    with col_logo:
        st.image(LOGO_DOCEBELLA_URL, width=150)
        
    with col_nav:
        cols_botoes = st.columns([1] * len(paginas_ordenadas))
        
        for i, nome in enumerate(paginas_ordenadas):
            if nome in paginas_map:
                is_active = st.session_state.pagina_atual == nome
                
                if cols_botoes[i].button(
                    nome, 
                    key=f"nav_{nome}", 
                    use_container_width=True, 
                    type="primary" if is_active else "secondary" 
                ):
                    st.session_state.pagina_atual = nome
                    st.rerun()

def render_custom_header(paginas_ordenadas, paginas_map):
    """Renderiza o container do header com o CSS injetado."""
    with st.container():
        st.markdown('<div class="header-container">', unsafe_allow_html=True)
        render_header(paginas_ordenadas, paginas_map)
        st.markdown('</div>', unsafe_allow_html=True)
