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
    CSV_PATH = st.secrets["livro_caixa"]["CSV_PATH"]
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

# ==================== FUNÇÕES DE CONFIGURAÇÃO DO APP ====================

def render_global_config():
    """Define a configuração da página e injeta o CSS customizado."""
    st.set_page_config(
        layout="wide", 
        page_title="Doce&Bella | Gestão Financeira", 
        page_icon="🌸"
    )

    # Adiciona CSS customizado
    st.markdown("""
        <style>
        # ... (todo o seu CSS aqui dentro) ...
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



