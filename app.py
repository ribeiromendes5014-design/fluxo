# app.py (Versão Corrigida e Completa)

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
from pages.cashback_system import cashback_system

# --- 1. CONFIGURAÇÃO INICIAL ---
render_global_config() 

# --- 2. MAPA DE PÁGINAS ---
# DICIONÁRIO DE PÁGINAS (ESSENCIAL)
# Esta era a parte que estava faltando.
# Ele conecta o nome da página (string) à sua função importada.
PAGINAS = {
    "Home": homepage,
    "Livro Caixa": livro_caixa,
    "Precificação": precificacao_completa,
    "Cashback": cashback_system,
    "Produtos": gestao_produtos,
    "Promoções": gestao_promocoes,
    "Histórico de Compra": historico_compras,
}

# LISTA ORDENADA PARA EXIBIÇÃO
# Define a ordem em que os botões aparecerão no cabeçalho.
paginas_ordenadas = [
    "Home", 
    "Livro Caixa", 
    "Precificação", 
    "Cashback", 
    "Produtos", 
    "Promoções", 
    "Histórico de Compra"
] 

# --- 3. NAVEGAÇÃO E HEADER ---
if "pagina_atual" not in st.session_state:
    st.session_state.pagina_atual = "Home"

# Renderiza o cabeçalho usando a lista e o dicionário
render_custom_header(paginas_ordenadas, PAGINAS)

# --- 4. RENDERIZAÇÃO DO CONTEÚDO ---
# Executa a função da página atual que está armazenada no dicionário PAGINAS
PAGINAS[st.session_state.pagina_atual]()
