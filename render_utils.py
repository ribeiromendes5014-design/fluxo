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

    # Adiciona CSS customizado (Mantido o bloco de estilo que você forneceu no código principal)
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
    
    /* Remove a Sidebar do Streamlit padrão, pois usaremos a navegação customizada no topo */
    [data-testid="stSidebar"] {
        width: 350px; 
    }
    
    /* Estilo para a homepage */
    .homepage-title {
        color: #E91E63;
        font-size: 3em;
        font-weight: 700;
        text-shadow: 2px 2px #fbcfe8; /* Sombra suave rosa claro */
    }
    .homepage-subtitle {
        color: #880E4F;
        font-size: 1.5em;
        margin-top: -10px;
        margin-bottom: 20px;
    }

    /* Estilo para simular os cards de redes sociais (Novidades) */
    .insta-card {
        background-color: white;
        border-radius: 15px;
        overflow: hidden;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
        padding: 15px;
        height: 100%;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }
    .insta-header {
        display: flex;
        align-items: center;
        font-weight: bold;
        color: #E91E63;
        margin-bottom: 10px;
    }
    
    /* --- Estilo dos Cards de Produto (Para dentro do carrossel) --- */
    .product-card {
        background-color: white;
        border-radius: 10px;
        padding: 15px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
        text-align: center;
        height: 100%;
        width: 250px; /* Largura Fixa para o Card no Carrossel */
        flex-shrink: 0; /* Impede o encolhimento */
        margin-right: 15px; /* Espaçamento entre os cards */
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        transition: transform 0.2s;
    }
    .product-card:hover {
        transform: translateY(-5px);
    }
    .product-card img {
        height: 150px;
        object-fit: contain;
        margin: 0 auto 10px;
        border-radius: 5px;
    }
    .price-original {
        color: #888;
        text-decoration: line-through;
        font-size: 0.85em;
        margin-right: 5px;
    }
    .price-promo {
        color: #E91E63;
        font-weight: bold;
        font-size: 1.2em;
    }
    /* CORREÇÃO: CSS para o botão em HTML */
    .buy-button {
        background-color: #E91E63;
        color: white;
        font-weight: bold;
        border-radius: 20px;
        border: none;
        padding: 8px 15px;
        cursor: pointer;
        width: 100%;
        margin-top: 10px; /* Adiciona margem para separação */
    }
    
    /* --- Estilo da Seção de Ofertas (Fundo Rosa) --- */
    .offer-section {
        background-color: #F8BBD0; /* Rosa mais claro para o fundo */
        padding: 40px 20px;
        border-radius: 15px;
        margin-top: 40px;
        text-align: center;
    }
    .offer-title {
        color: #E91E63;
        font-size: 2.5em;
        font-weight: 700;
        margin-bottom: 20px;
    }
    .megaphone-icon {
        color: #E91E63;
        font-size: 3em;
        margin-bottom: 10px;
        display: inline-block;
    }

    /* --- CLASSES PARA CARROSSEL HORIZONTAL --- */
    /* Contêiner que controla a barra de rolagem e centraliza o conteúdo */
    .carousel-outer-container {
        width: 100%;
        overflow-x: auto;
        padding-bottom: 20px; 
    }
    
    /* Wrapper interno que força o alinhamento horizontal e permite centralização */
    .product-wrapper {
        display: flex; /* FORÇA OS CARDS A FICAREM LADO A LADO */
        flex-direction: row;
        justify-content: flex-start; 
        gap: 15px;
        padding: 0 50px; 
        min-width: fit-content; 
        margin: 0 auto; 
    }
    
    /* Classe para controlar o tamanho das imagens de título */
    .section-header-img {
        max-width: 400px; 
        height: auto;
        display: block;
        margin: 0 auto 10px; 
    }

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
