# app.py (Versão Corrigida com a nova estrutura)

import streamlit as st

# 1. Importa a configuração global e o CSS (não muda)
from constants_and_css import render_global_config
# A função do header agora pode estar em ui_components.py ou constants_and_css.py
# Se você separou, use a linha abaixo, senão, mantenha a original.
# from ui_components import render_custom_header
from constants_and_css import render_custom_header

# 2. Importa as funções de cada página (sem o "pages.")
from homepage import homepage
from livro_caixa import livro_caixa
from gestao_produtos import gestao_produtos
from gestao_promocoes import gestao_promocoes
from historico_compras import historico_compras
from precificacao import precificacao_completa
from cashback_system import cashback_system

# --- 1. CONFIGURAÇÃO INICIAL ---
render_global_config()

# --- 2. MAPA DE PÁGINAS ---
PAGINAS = {
    "Home": homepage,
    "Livro Caixa": livro_caixa,
    "Precificação": precificacao_completa,
    "Cashback": cashback_system,
    "Produtos": gestao_produtos,
    "Promoções": gestao_promocoes,
    "Histórico de Compra": historico_compras,
}

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

render_custom_header(paginas_ordenadas, PAGINAS)

# --- 4. RENDERIZAÇÃO DO CONTEÚDO ---
PAGINAS[st.session_state.pagina_atual]()
