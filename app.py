# app.py

import streamlit as st

# 1. Importa a configuração global e o CSS
from constants_and_css import render_global_config, render_custom_header

# 2. Importa as funções de cada página da pasta pages
from pages.homepage import homepage
from pages.livro_caixa import livro_caixa
from pages.gestao_produtos import gestao_produtos
from pages.gestao_promocoes import gestao_promocoes
from pages.historico_compras import historico_compras
from pages.precificacao import precificacao_completa
from pages.cashback_system import cashback_system # <<< NOVO: Importa a função da nova página

# --- 1. CONFIGURAÇÃO INICIAL ---
render_global_config() 

# --- 2. MAPA DE PÁGINAS ---
PAGINAS = {
    "Home": homepage,
    "Livro Caixa": livro_caixa,
    "Precificação": precificacao_completa,
    "Produtos": gestao_produtos,
    "Promoções": gestao_promocoes,
    "Histórico de Compra": historico_compras,
    "Cashback": cashback_system, # <<< NOVO: Adiciona a nova página ao mapa
}

# --- 3. NAVEGAÇÃO ---
if "pagina_atual" not in st.session_state:
    st.session_state.pagina_atual = "Home"

# NOVO: Adiciona "Cashback" à lista ordenada (posicione onde desejar)
paginas_ordenadas = ["Home", "Livro Caixa", "Precificação", "Cashback", "Produtos", "Promoções", "Histórico de Compra"] 
render_custom_header(paginas_ordenadas, PAGINAS)

# 4. Renderiza a página
PAGINAS[st.session_state.pagina_atual]()
