import streamlit as st
from constants_and_css import LOGO_DOCEBELLA_URL # Importa a constante que ele precisa

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
        # ... (todo o seu CSS aqui dentro, se houver) ...
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
