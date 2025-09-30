import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
import requests
from requests.exceptions import ConnectionError, RequestException 
from io import StringIO, BytesIO
import io, os
import json
import hashlib
import ast
import plotly.express as px
import base64
import calendar 
from fpdf import FPDF # NOVO: Importa FPDF para geração de PDF


# ==============================================================================
# CONFIGURAÇÃO GERAL E INÍCIO DO APP
# ==============================================================================

# Configuração da página para ter largura total e usar o estilo web
# Define o tema de cores com base no estilo da imagem (predominantemente rosa/magenta)
st.set_page_config(
    layout="wide", 
    page_title="Doce&Bella | Gestão Financeira", 
    page_icon="🌸"
)

# Caminho para o logo carregado. 
# ATUALIZAÇÃO: Usando a URL do CloudFront para maior estabilidade.
LOGO_DOCEBELLA_FILENAME = "logo_docebella.jpg"
LOGO_DOCEBELLA_URL = "https://i.ibb.co/cdqJ92W/logo-docebella.png" # Link direto para o logo

# URLs das Imagens de Seção (CloudFront)
URL_MAIS_VENDIDOS = "https://d1a9qnv764bsoo.cloudfront.net/stores/002/838/949/rte/mid-queridinhos1.png"
URL_OFERTAS = "https://d1a9qnv764bsoo.cloudfront.net/stores/002/838/949/rte/mid-oferta.png"   
URL_NOVIDADES = "https://d1a9qnv764bsoo.cloudfront.net/stores/002/838/949/rte/mid-novidades.png"


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


# ===============================
# FUNÇÕES AUXILIARES GLOBAIS (DO PRECIFICAÇÃO)
# ===============================

# Configurações Telegram (MOCK, pois o token real é via st.secrets)
HARDCODED_TELEGRAM_TOKEN = "8412132908:AAG8N_vFzkpVNX-WN3bwT0Vl3H41Q-9Rfw4"
TELEGRAM_CHAT_ID = "-1003030758192"
TOPICO_ID = 28 # ID do tópico (thread) no grupo Telegram

# Definições de colunas base para Papelaria
INSUMOS_BASE_COLS_GLOBAL = ["Nome", "Categoria", "Unidade", "Preço Unitário (R$)"]
PRODUTOS_BASE_COLS_GLOBAL = ["Produto", "Custo Total", "Preço à Vista", "Preço no Cartão", "Margem (%)"]
COLUNAS_CAMPOS = ["Campo", "Aplicação", "Tipo", "Opções"]


def gerar_pdf(df: pd.DataFrame) -> BytesIO:
    """Gera um PDF formatado a partir do DataFrame de precificação, incluindo a URL da imagem."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Relatório de Precificação", 0, 1, "C")
    pdf.ln(5)

    # Configurações de fonte para tabela
    pdf.set_font("Arial", "B", 10) # Fonte menor para caber mais dados

    # Definindo largura das colunas (em mm)
    col_widths = {
        "Produto": 40,
        "Qtd": 15,
        "Custo Unitário": 25,
        "Margem (%)": 20,
        "Preço à Vista": 25,
        "Preço no Cartão": 25,
        "URL da Imagem": 40 # Nova coluna para a URL
    }
    
    # Define as colunas a serem exibidas no PDF
    pdf_cols = [col for col in col_widths.keys() if col in df.columns or col == "Custo Unitário"]
    current_widths = [col_widths[col] for col in pdf_cols]

    # Cabeçalho da tabela
    for col_name, width in zip(pdf_cols, current_widths):
        pdf.cell(width, 10, col_name, border=1, align='C')
    pdf.ln()

    # Fonte para corpo da tabela
    pdf.set_font("Arial", "", 8) # Fonte ainda menor para caber a URL

    if df.empty:
        pdf.cell(sum(current_widths), 10, "Nenhum produto cadastrado.", border=1, align="C")
        pdf.ln()
    else:
        # Itera pelas linhas e escreve na tabela
        for idx, row in df.iterrows():
            if "Produto" in pdf_cols:
                pdf.cell(col_widths["Produto"], 10, str(row.get("Produto", "")), border=1)
            if "Qtd" in pdf_cols:
                pdf.cell(col_widths["Qtd"], 10, str(row.get("Qtd", 0)), border=1, align="C")
            if "Custo Unitário" in pdf_cols:
                # Usa o Custo Total Unitário para o relatório, se disponível
                custo_unit_val = row.get("Custo Total Unitário", row.get("Custo Unitário", 0.0))
                pdf.cell(col_widths["Custo Unitário"], 10, f"R$ {custo_unit_val:.2f}", border=1, align="R")
            if "Margem (%)" in pdf_cols:
                pdf.cell(col_widths["Margem (%)"], 10, f"{row.get('Margem (%)', 0.0):.2f}%", border=1, align="R")
            if "Preço à Vista" in pdf_cols:
                pdf.cell(col_widths["Preço à Vista"], 10, f"R$ {row.get('Preço à Vista', 0.0):.2f}", border=1, align="R")
            if "Preço no Cartão" in pdf_cols:
                pdf.cell(col_widths["Preço no Cartão"], 10, f"R$ {row.get('Preço no Cartão', 0.0):.2f}", border=1, align="R")
            
            # --- NOVO: URL da Imagem no PDF ---
            if "URL da Imagem" in pdf_cols:
                url_display = str(row.get("Imagem_URL", ""))
                # Limita o tamanho da URL para não quebrar o layout
                if len(url_display) > 35:
                    url_display = url_display[:32] + "..."
                pdf.cell(col_widths["URL da Imagem"], 10, url_display, border=1, align="L", link=str(row.get("Imagem_URL", "")))
            # --- FIM NOVO ---
                
            pdf.ln()

    pdf_bytes = pdf.output(dest='S').encode('latin1')
    return BytesIO(pdf_bytes)


def enviar_pdf_telegram(pdf_bytesio, df_produtos: pd.DataFrame, thread_id=None):
    """Envia o arquivo PDF e a primeira imagem (se existir) em mensagens separadas para o Telegram."""
    
    token = st.secrets.get("telegram_token", HARDCODED_TELEGRAM_TOKEN)
    
    image_url = None
    image_caption = "Relatório de Precificação"
    
    if not df_produtos.empty and "Imagem_URL" in df_produtos.columns:
        first_row = df_produtos.iloc[0]
        url = first_row.get("Imagem_URL")
        produto = first_row.get("Produto", "Produto")
        
        if isinstance(url, str) and url.startswith("http"):
            image_url = url
            image_caption = f"📦 Produto Principal: {produto}\n\n[Relatório de Precificação em anexo]"

    # 1. Envia o PDF (mensagem principal)
    
    url_doc = f"https://api.telegram.org/bot{token}/sendDocument"
    files_doc = {'document': ('precificacao.pdf', pdf_bytesio, 'application/pdf')}
    data_doc = {"chat_id": TELEGRAM_CHAT_ID, "caption": image_caption if not image_url else "[Relatório de Precificação em anexo]"}
    if thread_id is not None:
        data_doc["message_thread_id"] = thread_id
    
    resp_doc = requests.post(url_doc, data=data_doc, files=files_doc)
    resp_doc_json = resp_doc.json()
    
    if not resp_doc_json.get("ok"):
         st.error(f"❌ Erro ao enviar PDF: {resp_doc_json.get('description')}")
         return

    st.success("✅ PDF enviado para o Telegram.")
    
    # 2. Envia a foto (se existir) em uma mensagem separada
    if image_url:
        try:
            url_photo = f"https://api.telegram.org/bot{token}/sendPhoto"
            
            # Faz o Telegram buscar a foto diretamente da URL
            data_photo = {
                "chat_id": TELEGRAM_CHAT_ID, 
                "photo": image_url,
                "caption": f"🖼️ Foto do Produto Principal: {produto}"
            }
            if thread_id is not None:
                data_photo["message_thread_id"] = thread_id

            resp_photo = requests.post(url_photo, data=data_photo)
            resp_photo_json = resp_photo.json()

            if resp_photo_json.get("ok"):
                st.success("✅ Foto do produto principal enviada com sucesso!")
            else:
                 st.warning(f"❌ Erro ao enviar a foto do produto: {resp_photo_json.get('description')}")
                 
        except Exception as e:
            st.warning(f"⚠️ Erro ao tentar enviar a imagem. Erro: {e}")
            

def exibir_resultados(df: pd.DataFrame, imagens_dict: dict):
    """Exibe os resultados de precificação com tabela e imagens dos produtos."""
    if df is None or df.empty:
        st.info("⚠️ Nenhum produto disponível para exibir.")
        return

    st.subheader("📊 Resultados Detalhados da Precificação")

    for idx, row in df.iterrows():
        with st.container():
            cols = st.columns([1, 3])
            with cols[0]:
                img_to_display = None
                
                # 1. Tenta carregar imagem do dicionário (upload manual)
                img_to_display = imagens_dict.get(row.get("Produto"))

                # 2. Tenta carregar imagem dos bytes (se persistido)
                if img_to_display is None and row.get("Imagem") is not None and isinstance(row.get("Imagem"), bytes):
                    try:
                        img_to_display = row.get("Imagem")
                    except Exception:
                        pass # Continua tentando a URL

                # 3. Tenta carregar imagem da URL (se persistido)
                img_url = row.get("Imagem_URL")
                if img_to_display is None and img_url and isinstance(img_url, str) and img_url.startswith("http"):
                    st.image(img_url, width=100, caption="URL")
                elif img_to_display:
                    st.image(img_to_display, width=100, caption="Arquivo")
                else:
                    st.write("🖼️ N/A")
                    
            with cols[1]:
                st.markdown(f"**{row.get('Produto', '—')}**")
                st.write(f"📦 Quantidade: {row.get('Qtd', '—')}")
                
                custo_base = row.get('Custo Unitário', 0.0)
                custo_total_unitario = row.get('Custo Total Unitário', custo_base)

                st.write(f"💰 Custo Base: R$ {custo_base:.2f}")

                custos_extras_prod = row.get('Custos Extras Produto', 0.0)
                st.write(f"🛠 Rateio/Extras: R$ {custos_extras_prod:.2f}")

                if 'Custo Total Unitário' in df.columns:
                    st.write(f"💸 Custo Total/Un: **R$ {custo_total_unitario:.2f}**")

                if "Margem (%)" in df.columns:
                    margem_val = row.get("Margem (%)", 0)
                    try:
                        margem_float = float(margem_val)
                    except Exception:
                        margem_float = 0
                    st.write(f"📈 Margem: **{margem_float:.2f}%**")
                
                if "Preço à Vista" in df.columns:
                    st.write(f"💰 Preço à Vista: **R$ {row.get('Preço à Vista', 0):.2f}**")
                if "Preço no Cartão" in df.columns:
                    st.write(f"💳 Preço no Cartão: **R$ {row.get('Preço no Cartão', 0):.2f}**")


def processar_dataframe(df: pd.DataFrame, frete_total: float, custos_extras: float,
                        modo_margem: str, margem_fixa: float) -> pd.DataFrame:
    """Processa o DataFrame, aplica rateio, margem e calcula os preços finais."""
    if df.empty:
        # Garante que o DataFrame tem as colunas mínimas esperadas para evitar erros de índice/coluna
        return pd.DataFrame(columns=[
            "Produto", "Qtd", "Custo Unitário", "Custos Extras Produto", 
            "Custo Total Unitário", "Margem (%)", "Preço à Vista", "Preço no Cartão"
        ])

    df = df.copy()

    # Garante que as colunas de custo e quantidade são numéricas
    for col in ["Qtd", "Custo Unitário", "Margem (%)", "Custos Extras Produto"]:
        if col in df.columns:
            # Tenta converter, falhando para 0.0 se não for possível
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
        elif col not in df.columns:
            # Adiciona colunas ausentes com valor 0.0 se for necessário para o cálculo
            df[col] = 0.0
            
    # --- Cálculo do Rateio Global ---
    qtd_total = df["Qtd"].sum()
    rateio_unitario = 0
    if qtd_total > 0:
        rateio_unitario = (frete_total + custos_extras) / qtd_total

    # Calcular o custo total por unidade
    df["Custo Total Unitário"] = df["Custo Unitário"] + df["Custos Extras Produto"]

    # Processar margens conforme o modo selecionado
    if "Margem (%)" not in df.columns:
        df["Margem (%)"] = margem_fixa
    
    df["Margem (%)"] = df["Margem (%)"].apply(lambda x: x if pd.notna(x) else margem_fixa)


    # Calcular os preços finais
    df["Preço à Vista"] = df["Custo Total Unitário"] * (1 + df["Margem (%)"] / 100)
    # Taxa de cartão de 11.28% (para chegar a 0.8872 do preço de venda)
    df["Preço no Cartão"] = df["Preço à Vista"] / 0.8872

    # Seleciona as colunas relevantes para o DataFrame final de exibição
    cols_to_keep = [
        "Produto", "Qtd", "Custo Unitário", "Custos Extras Produto", 
        "Custo Total Unitário", "Margem (%)", "Preço à Vista", "Preço no Cartão", 
        "Imagem", "Imagem_URL" # Adicionada Imagem_URL para persistência no CSV
    ]
    
    # Mantém apenas as colunas que existem no DF
    df_final = df[[col for col in cols_to_keep if col in df.columns]]

    return df_final


def extrair_produtos_pdf(pdf_file) -> list:
    """Função mock para extração de produtos de PDF."""
    # st.warning("Função extrair_produtos_pdf ainda não implementada. Use o carregamento manual ou de CSV.")
    return []


# Funções auxiliares gerais
def baixar_csv_aba(df, nome_arquivo, key_suffix=""):
    """Cria um botão de download para o DataFrame."""
    csv = df.to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        f"⬇️ Baixar {nome_arquivo}",
        data=csv,
        file_name=nome_arquivo,
        mime="text/csv",
        key=f"download_button_{nome_arquivo.replace('.', '_')}_{key_suffix}"
    )

def _opcoes_para_lista(opcoes_str):
    """Converte string de opções separadas por vírgula em lista."""
    if pd.isna(opcoes_str) or not str(opcoes_str).strip():
        return []
    return [o.strip() for o in str(opcoes_str).split(",") if o.strip()]

def col_defs_para(aplicacao: str):
    """Filtra as definições de colunas extras por aplicação."""
    if "campos" not in st.session_state or st.session_state.campos.empty:
        return pd.DataFrame(columns=COLUNAS_CAMPOS)
    df = st.session_state.campos
    return df[(df["Aplicação"] == aplicacao) | (df["Aplicação"] == "Ambos")].copy()

def garantir_colunas_extras(df: pd.DataFrame, aplicacao: str) -> pd.DataFrame:
    """Adiciona colunas extras ao DataFrame se ainda não existirem."""
    defs = col_defs_para(aplicacao)
    for campo in defs["Campo"].tolist():
        if campo not in df.columns:
            df[campo] = ""
    return df

def render_input_por_tipo(label, tipo, opcoes, valor_padrao=None, key=None):
    """Renderiza um widget Streamlit baseado no tipo de campo definido."""
    if tipo == "Número":
        valor = float(valor_padrao) if (valor_padrao is not None and str(valor_padrao).strip() != "") else 0.0
        return st.number_input(label, min_value=0.0, format="%.2f", value=valor, key=key)
    elif tipo == "Seleção":
        lista = _opcoes_para_lista(opcoes)
        valor_display = str(valor_padrao) if valor_padrao is not None and pd.notna(valor_padrao) else ""
        
        # Garante que o valor padrão atual está na lista, senão adiciona ele na primeira posição
        if valor_display not in lista and valor_display != "":
            lista = [valor_display] + [o for o in lista if o != valor_display]
        elif valor_display == "" and lista:
            # Se não tem valor padrão e tem opções, usa a primeira como default
            valor_display = lista[0]
            
        try:
            index_padrao = lista.index(valor_display) if valor_display in lista else 0
        except ValueError:
            index_padrao = 0
            
        return st.selectbox(label, options=lista, index=index_padrao, key=key)
    else:
        return st.text_input(label, value=str(valor_padrao) if valor_padrao is not None else "", key=key)

# --- FIM FUNÇÕES AUXILIARES GLOBAIS (DO PRECIFICAÇÃO) ---


# --- Funções e Constantes de Persistência (Mantidas do original) ---

# Importa a biblioteca PyGithub para gerenciamento de persistência
try:
    from github import Github
except ImportError:
    class Github:
        def __init__(self, token): pass
        def get_repo(self, repo_name): return self
        def update_file(self, path, msg, content, sha, branch): pass
        def create_file(self, path, msg, content, branch): pass

def ler_codigo_barras_api(image_bytes):
    """
    Decodifica códigos de barras (1D e QR) usando a API pública ZXing.
    Mais robusta que WebQR porque suporta EAN/UPC/Code128 além de QR Codes.
    """
    URL_DECODER_ZXING = "https://zxing.org/w/decode"
    
    try:
        # ⚠️ IMPORTANTE: ZXing espera o arquivo no campo 'f', não 'file'
        files = {"f": ("barcode.png", image_bytes, "image/png")}
        
        response = requests.post(URL_DECODER_ZXING, files=files, timeout=30)

        if response.status_code != 200:
            if 'streamlit' in globals():
                st.error(f"❌ Erro na API ZXing. Status HTTP: {response.status_code}")
            return []

        text = response.text
        codigos = []

        # Parse simples do HTML retornado
        if "<pre>" in text:
            partes = text.split("<pre>")
            for p in partes[1:]:
                codigo = p.split("</pre>")[0].strip()
                if codigo and not codigo.startswith("Erro na decodificação"):
                    codigos.append(codigo)

        if not codigos and 'streamlit' in globals():
            # Alterado para toast para menos intrusão, caso a leitura falhe
            st.toast("⚠️ API ZXing não retornou nenhum código válido. Tente novamente ou use uma imagem mais clara.")

        return codigos

    except ConnectionError as ce:
        if 'streamlit' in globals():
            st.error(f"❌ Erro de Conexão: O servidor ZXing recusou a conexão. Detalhe: {ce}")
        return []
        
    except RequestException as e:
        if 'streamlit' in globals():
            st.error(f"❌ Erro de Requisição (Timeout/Outro): Falha ao completar a chamada à API ZXing. Detalhe: {e}")
        return []
    
    except Exception as e:
        if 'streamlit' in globals():
            st.error(f"❌ Erro inesperado: {e}")
        return []


def add_months(d: date, months: int) -> date:
    """Adiciona um número específico de meses a uma data."""
    month = d.month + months
    year = d.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)

# ==================== CONFIGURAÇÕES DO APLICATIVO E CONSTANTES ====================
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

# Caminhos dos arquivos
URL_BASE_REPOS = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/"
ARQ_PRODUTOS = "produtos_estoque.csv"
ARQ_LOCAL = "livro_caixa.csv" # Usado para backup local e constante
PATH_DIVIDAS = CSV_PATH
ARQ_COMPRAS = "historico_compras.csv"
ARQ_PROMOCOES = "promocoes.csv" 
COLUNAS_COMPRAS = ["Data", "Produto", "Quantidade", "Valor Total", "Cor", "FotoURL"] 

COMMIT_MESSAGE = "Atualiza livro caixa via Streamlit (com produtos/categorias)"
COMMIT_MESSAGE_DELETE = "Exclui movimentações do livro caixa"
COMMIT_MESSAGE_EDIT = "Edita movimentação via Streamlit"
COMMIT_MESSAGE_DEBT_REALIZED = "Conclui dívidas pendentes"
COMMIT_MESSAGE_PROD = "Atualização automática de estoque/produtos"

COLUNAS_PADRAO = ["Data", "Loja", "Cliente", "Valor", "Forma de Pagamento", "Tipo", "Produtos Vendidos", "Categoria", "Status", "Data Pagamento"]
COLUNAS_COMPLETAS_PROCESSADAS = COLUNAS_PADRAO + ["ID Visível", "original_index", "Data_dt", "Saldo Acumulado", "Cor_Valor"]

FATOR_CARTAO = 0.8872
LOJAS_DISPONIVEIS = ["Doce&bella", "Papelaria", "Fotografia", "Outro"]
CATEGORIAS_SAIDA = ["Aluguel", "Salários/Pessoal", "Marketing/Publicidade", "Fornecedores/Matéria Prima", "Despesas Fixas", "Impostos/Taxas", "Outro/Diversos", "Não Categorizado"]
FORMAS_PAGAMENTO = ["Dinheiro", "Cartão", "PIX", "Transferência", "Outro"]


# --- Funções de Persistência (Comentários omitidos para brevidade) ---

def to_float(valor_str):
    try:
        if isinstance(valor_str, (int, float)):
            return float(valor_str)
        return float(str(valor_str).replace(",", ".").strip())
    except:
        return 0.0
    
def prox_id(df, coluna_id="ID"):
    if df.empty:
        return "1"
    else:
        try:
            return str(pd.to_numeric(df[coluna_id], errors='coerce').fillna(0).astype(int).max() + 1)
        except:
            return str(len(df) + 1)

def hash_df(df):
    """
    Gera um hash para o DataFrame para detecção de mudanças.
    Função do precificador, adaptada para o hash robusto.
    """
    df_temp = df.copy() 
    
    # Remove colunas que podem conter bytes ou objetos não serializáveis facilmente
    for col in df_temp.select_dtypes(include=['datetime64[ns]']).columns:
        df_temp[col] = df_temp[col].astype(str)
        
    if "Imagem" in df_temp.columns:
        df_temp = df_temp.drop(columns=["Imagem"], errors='ignore')
    
    try:
        # Usa um método de hashing específico para pandas
        return hashlib.md5(pd.util.hash_pandas_object(df_temp, index=False).values).hexdigest()
    except Exception as e:
        # Fallback para stringify JSON (mais lento, mas mais robusto para DFs complexos)
        try:
             # Converte colunas object para string explícita para garantir hash consistente
            for col in df_temp.select_dtypes(include=['object']).columns:
                 df_temp[col] = df_temp[col].astype(str)
            return hashlib.md5(df_temp.to_json().encode('utf-8')).hexdigest()
        except Exception as inner_e:
             # st.error(f"Erro interno no hash do DataFrame: {inner_e}") # Descomente para debug
             return "error"
             

def salvar_csv_no_github(token, repo, path, dataframe, branch="main", mensagem="Atualização via app"):
    """Salva o DataFrame como CSV no GitHub via API (Versão do Precificador)."""
    from requests import get, put
    
    # Remove a coluna 'Imagem' se ela existir, pois contém bytes (e o hash já deveria ter feito isso)
    df_temp = dataframe.drop(columns=["Imagem"], errors='ignore') if "Imagem" in dataframe.columns else dataframe.copy()
    
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    conteudo = df_temp.to_csv(index=False)
    conteudo_b64 = base64.b64encode(conteudo.encode()).decode()
    headers = {"Authorization": f"token {token}"}
    
    try:
        # 1. Tenta obter o SHA (para update)
        r = get(url, headers=headers)
        r.raise_for_status() # Levanta exceção para 4xx e 5xx
        sha = r.json().get("sha")
    except requests.exceptions.HTTPError as e:
        # 404 significa que o arquivo não existe, sha = None
        if e.response.status_code == 404:
            sha = None
        else:
            st.error(f"❌ Erro ao tentar ler arquivo no GitHub: {e}")
            return False
    except Exception as e:
        st.error(f"❌ Erro de conexão ao tentar ler arquivo no GitHub: {e}")
        return False
        
    # 2. Envia o conteúdo
    payload = {"message": mensagem, "content": conteudo_b64, "branch": branch}
    if sha: payload["sha"] = sha
    
    try:
        r2 = put(url, headers=headers, json=payload)
        r2.raise_for_status()
        # st.success(f"✅ Arquivo `{path}` atualizado no GitHub!")
        return True 
    except requests.exceptions.HTTPError as e:
        st.error(f"❌ Erro ao salvar `{path}` no GitHub: {e.response.text}")
        return False
    except Exception as e:
        st.error(f"❌ Erro de conexão ao salvar no GitHub: {e}")
        return False


def load_csv_github(url: str) -> pd.DataFrame | None:
    try:
        response = requests.get(url)
        response.raise_for_status()
        df = pd.read_csv(StringIO(response.text), dtype=str)
        if df.empty or len(df.columns) < 2:
            return None
        return df
    except Exception:
        return None

def parse_date_yyyy_mm_dd(date_str):
    """Tenta converter uma string para objeto date."""
    if pd.isna(date_str) or not date_str:
        return None
    try:
        return datetime.strptime(str(date_str).split(" ")[0], "%Y-%m-%d").date()
    except:
        return None

@st.cache_data(show_spinner="Carregando promoções...")
def carregar_promocoes():
    COLUNAS_PROMO = ["ID", "IDProduto", "NomeProduto", "Desconto", "DataInicio", "DataFim"]
    url_raw = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/{ARQ_PROMOCOES}"
    df = load_csv_github(url_raw)
    if df is None or df.empty:
        df = pd.DataFrame(columns=COLUNAS_PROMO)
    for col in COLUNAS_PROMO:
        if col not in df.columns:
            df[col] = "" 
    return df[[col for col in COLUNAS_PROMO if col in df.columns]]

def norm_promocoes(df):
    """Normaliza o DataFrame de promoções."""
    if df.empty: return df
    df = df.copy()
    df["Desconto"] = pd.to_numeric(df["Desconto"], errors='coerce').fillna(0.0)
    df["DataInicio"] = pd.to_datetime(df["DataInicio"], errors='coerce').dt.date
    df["DataFim"] = pd.to_datetime(df["DataFim"], errors='coerce').dt.date
    # Filtra promoções expiradas
    df = df[df["DataFim"] >= date.today()] 
    return df

@st.cache_data(show_spinner="Carregando histórico de compras...")
def carregar_historico_compras():
    url_raw = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/{ARQ_COMPRAS}"
    df = load_csv_github(url_raw)
    if df is None or df.empty:
        df = pd.DataFrame(columns=COLUNAS_COMPRAS)
    for col in COLUNAS_COMPRAS:
        if col not in df.columns:
            df[col] = "" 
    return df[[col for col in COLUNAS_COMPRAS if col in df.columns]]

# Manter essa função para compatibilidade, mas ela é apenas um placeholder no 333.py original
def salvar_historico_no_github(df: pd.DataFrame, commit_message: str):
    return True

@st.cache_data(show_spinner="Carregando dados...")
def carregar_livro_caixa():
    """Orquestra o carregamento do Livro Caixa."""
    df = None
    
    # 1. Tenta carregar do GitHub (usando a URL raw com o PATH_DIVIDAS / CSV_PATH)
    url_raw = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/{PATH_DIVIDAS}"
    df = load_csv_github(url_raw)

    if df is None or df.empty:
        # 2. Fallback local/garantia de colunas
        try:
            df = pd.read_csv(ARQ_LOCAL, dtype=str)
        except Exception:
            df = pd.DataFrame(columns=COLUNAS_PADRAO)
        
    if df.empty:
        df = pd.DataFrame(columns=COLUNAS_PADRAO)

    # Garante que as colunas padrão existam
    for col in COLUNAS_PADRAO:
        if col not in df.columns:
            df[col] = "Realizada" if col == "Status" else "" 
            
    # Adiciona RecorrenciaID se não existir
    if 'RecorrenciaID' not in df.columns:
        df['RecorrenciaID'] = ''
        
    # Retorna apenas as colunas padrão na ordem correta
    cols_to_return = COLUNAS_PADRAO + ["RecorrenciaID"]
    return df[[col for col in cols_to_return if col in df.columns]]


def salvar_dados_no_github(df: pd.DataFrame, commit_message: str):
    """
    Salva o DataFrame CSV do Livro Caixa no GitHub usando a API e também localmente (backup).
    Essa função garante a persistência de dados para o Streamlit.
    """
    
    # 1. Backup local (Tenta salvar, ignora se falhar)
    try:
        # ARQ_LOCAL = "livro_caixa.csv"
        df.to_csv(ARQ_LOCAL, index=False, encoding="utf-8-sig") 
    except Exception:
        pass

    # 2. Prepara DataFrame para envio ao GitHub
    df_temp = df.copy()
    
    # Prepara os dados de data para serem salvos como string no formato YYYY-MM-DD
    for col_date in ['Data', 'Data Pagamento']:
        if col_date in df_temp.columns:
            df_temp[col_date] = pd.to_datetime(df_temp[col_date], errors='coerce').apply(
                lambda x: x.strftime('%Y-%m-%d') if pd.notnull(x) else ''
            )

    try:
        g = Github(TOKEN)
        repo = g.get_repo(f"{OWNER}/{REPO_NAME}")
        csv_string = df_temp.to_csv(index=False, encoding="utf-8-sig")

        try:
            # Tenta obter o SHA do conteúdo atual
            # PATH_DIVIDAS = CSV_PATH (Caminho do arquivo no repositório)
            contents = repo.get_contents(PATH_DIVIDAS, ref=BRANCH)
            # Atualiza o arquivo
            repo.update_file(contents.path, commit_message, csv_string, contents.sha, branch=BRANCH)
            st.success("📁 Livro Caixa salvo (atualizado) no GitHub!")
        except Exception:
            # Cria o arquivo (se não existir)
            repo.create_file(PATH_DIVIDAS, commit_message, csv_string, branch=BRANCH)
            st.success("📁 Livro Caixa salvo (criado) no GitHub!")

        return True

    except Exception as e:
        st.error(f"❌ Erro ao salvar no GitHub: {e}")
        st.error("Verifique se seu 'GITHUB_TOKEN' tem permissões e se o repositório existe.")
        return False


@st.cache_data(show_spinner=False)
def processar_dataframe_livro_caixa(df):
    for col in COLUNAS_PADRAO:
        if col not in df.columns: df[col] = ""
    if 'RecorrenciaID' not in df.columns: df['RecorrenciaID'] = ''
    if df.empty: return pd.DataFrame(columns=COLUNAS_COMPLETAS_PROCESSADAS)
    df_proc = df.copy()
    df_proc["Valor"] = pd.to_numeric(df_proc["Valor"], errors="coerce").fillna(0.0)
    df_proc["Data"] = pd.to_datetime(df_proc["Data"], errors='coerce').dt.date
    df_proc["Data_dt"] = pd.to_datetime(df_proc["Data"], errors='coerce')
    df_proc["Data Pagamento"] = pd.to_datetime(df_proc["Data Pagamento"], errors='coerce').dt.date
    df_proc.dropna(subset=['Data_dt'], inplace=True)
    df_proc = df_proc.reset_index(drop=False) 
    df_proc.rename(columns={'index': 'original_index'}, inplace=True)
    df_proc['Saldo Acumulado'] = 0.0 
    df_realizadas = df_proc[df_proc['Status'] == 'Realizada'].copy()
    if not df_realizadas.empty:
        df_realizadas_sorted_asc = df_realizadas.sort_values(by=['Data_dt', 'original_index'], ascending=[True, True]).reset_index(drop=True)
        df_realizadas_sorted_asc['TEMP_SALDO'] = df_realizadas_sorted_asc['Valor'].cumsum()
        df_proc = pd.merge(df_proc, df_realizadas_sorted_asc[['original_index', 'TEMP_SALDO']], on='original_index', how='left')
        df_proc['Saldo Acumulado'] = df_proc['TEMP_SALDO'].fillna(method='ffill').fillna(0)
        df_proc.drop(columns=['TEMP_SALDO'], inplace=True, errors='ignore')
    df_proc = df_proc.sort_values(by="Data_dt", ascending=False).reset_index(drop=True)
    df_proc.insert(0, 'ID Visível', df_proc.index + 1)
    df_proc['Cor_Valor'] = df_proc.apply(lambda row: 'green' if row['Tipo'] == 'Entrada' and row['Valor'] >= 0 else 'red', axis=1)
    return df_proc

def calcular_resumo(df):
    df_realizada = df[df['Status'] == 'Realizada']
    if df_realizada.empty: return 0.0, 0.0, 0.0
    total_entradas = df_realizada[df_realizada["Tipo"] == "Entrada"]["Valor"].sum()
    total_saidas = abs(df_realizada[df_realizada["Tipo"] == "Saída"]["Valor"].sum()) 
    saldo = df_realizada["Valor"].sum()
    return total_entradas, total_saidas, saldo

def format_produtos_resumo(produtos_json):
    if pd.isna(produtos_json) or produtos_json == "": return ""
    if produtos_json:
        try:
            try:
                produtos = json.loads(produtos_json)
            except json.JSONDecodeError:
                produtos = ast.literal_eval(produtos_json)
            if not isinstance(produtos, list) or not all(isinstance(p, dict) for p in produtos): return "Dados inválidos"
            count = len(produtos)
            if count > 0:
                primeiro = produtos[0].get('Produto', 'Produto Desconhecido')
                total_custo = 0.0
                total_venda = 0.0
                for p in produtos:
                    try:
                        qtd = float(p.get('Quantidade', 0))
                        preco_unitario = float(p.get('Preço Unitário', 0))
                        custo_unitario = float(p.get('Custo Unitário', 0))
                        total_custo += custo_unitario * qtd
                        total_venda += preco_unitario * qtd
                    except ValueError: continue
                lucro = total_venda - total_custo
                lucro_str = f"| Lucro R$ {lucro:,.2f}" if lucro != 0 else ""
                return f"{count} item(s): {primeiro}... {lucro_str}"
        except:
            return "Erro na formatação/JSON Inválido"
    return ""

def highlight_value(row):
    color = row['Cor_Valor']
    return [f'color: {color}' if col == 'Valor' else '' for col in row.index]

@st.cache_data(show_spinner="Carregando produtos do estoque...")
def inicializar_produtos():
    COLUNAS_PRODUTOS = [
        "ID", "Nome", "Marca", "Categoria", "Quantidade", "PrecoCusto", 
        "PrecoVista", "PrecoCartao", "Validade", "FotoURL", "CodigoBarras", "PaiID"
    ]
    if "produtos" not in st.session_state:
        url_raw = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/{ARQ_PRODUTOS}"
        df_carregado = load_csv_github(url_raw)
        if df_carregado is None or df_carregado.empty:
            df_base = pd.DataFrame(columns=COLUNAS_PRODUTOS)
        else:
            df_base = df_carregado
        for col in COLUNAS_PRODUTOS:
            if col not in df_base.columns: df_base[col] = ''
        df_base["Quantidade"] = pd.to_numeric(df_base["Quantidade"], errors='coerce').fillna(0).astype(int)
        df_base["PrecoCusto"] = pd.to_numeric(df_base["PrecoCusto"], errors='coerce').fillna(0.0)
        df_base["PrecoVista"] = pd.to_numeric(df_base["PrecoVista"], errors='coerce').fillna(0.0)
        df_base["PrecoCartao"] = pd.to_numeric(df_base["PrecoCartao"], errors='coerce').fillna(0.0)
        
        # Converte validade para Date para facilitar a lógica de promoções
        df_base["Validade"] = pd.to_datetime(df_base["Validade"], errors='coerce').dt.date
        
        st.session_state.produtos = df_base
    return st.session_state.produtos

def ajustar_estoque(id_produto, quantidade, operacao="debitar"):
    produtos_df = st.session_state.produtos
    idx_produto = produtos_df[produtos_df["ID"] == id_produto].index
    if not idx_produto.empty:
        idx = idx_produto[0]
        qtd_atual = produtos_df.loc[idx, "Quantidade"]
        if operacao == "debitar":
            nova_qtd = qtd_atual - quantidade
            produtos_df.loc[idx, "Quantidade"] = max(0, nova_qtd)
            return True
        elif operacao == "creditar":
            nova_qtd = qtd_atual + quantidade
            produtos_df.loc[idx, "Quantidade"] = nova_qtd
            return True
    return False

def salvar_produtos_no_github(dataframe, commit_message):
    return True

def save_data_github_produtos(df, path, commit_message):
    return False 

def callback_salvar_novo_produto(produtos, tipo_produto, nome, marca, categoria, qtd, preco_custo, preco_vista, validade, foto_url, codigo_barras, variações):
    if not nome:
        st.error("O nome do produto é obrigatório.")
        return False
        
    def add_product_row(df, p_id, p_nome, p_marca, p_categoria, p_qtd, p_custo, p_vista, p_cartao, p_validade, p_foto, p_cb, p_pai_id=None):
        novo_id = prox_id(df, "ID")
        
        novo = {
            "ID": novo_id,
            "Nome": p_nome.strip(),
            "Marca": p_marca.strip(),
            "Categoria": p_categoria.strip(),
            "Quantidade": int(p_qtd),
            "PrecoCusto": to_float(p_custo),
            "PrecoVista": to_float(p_vista),
            "PrecoCartao": to_float(p_cartao),
            "Validade": str(p_validade),
            "FotoURL": p_foto.strip(),
            "CodigoBarras": str(p_cb).strip(),
            "PaiID": str(p_pai_id).strip() if p_pai_id else ""
        }
        return pd.concat([df, pd.DataFrame([novo])], ignore_index=True), novo_id
    
    # Placeholder para save_csv_github (deve ser ajustado conforme a implementação real de persistência de produtos)
    def save_csv_github(df, path, message):
        # Usando a função genérica de salvamento do precificador
        df_temp = df.copy()
        for col in ['Validade']:
            if col in df_temp.columns:
                df_temp[col] = pd.to_datetime(df_temp[col], errors='coerce').apply(
                    lambda x: x.strftime('%Y-%m-%d') if pd.notnull(x) else ''
                )
        return salvar_csv_no_github(GITHUB_TOKEN, GITHUB_REPO, path, df_temp, GITHUB_BRANCH, message)


    if tipo_produto == "Produto simples":
        produtos, new_id = add_product_row(
            produtos,
            None,
            nome, marca, categoria,
            qtd, preco_custo, preco_vista, 
            round(to_float(preco_vista) / FATOR_CARTAO, 2) if to_float(preco_vista) > 0 else 0.0,
            validade, foto_url, codigo_barras
        )
        if save_csv_github(produtos, ARQ_PRODUTOS, f"Novo produto simples: {nome} (ID {new_id})"):
            st.session_state.produtos = produtos
            inicializar_produtos.clear()
            st.success(f"Produto '{nome}' cadastrado com sucesso!")
            # Limpa campos do formulário simples
            st.session_state.cad_nome = ""
            st.session_state.cad_marca = ""
            st.session_state.cad_categoria = ""
            st.session_state.cad_qtd = 0
            st.session_state.cad_preco_custo = "0,00"
            st.session_state.cad_preco_vista = "0,00"
            st.session_state.cad_validade = date.today()
            st.session_state.cad_foto_url = ""
            st.session_state.cad_cb = ""
            if "codigo_barras" in st.session_state: del st.session_state["codigo_barras"]
            return True
        return False
    
    elif tipo_produto == "Produto com variações (grade)":
        
        # 1. Cria o Produto Pai (sem estoque)
        produtos, pai_id = add_product_row(
            produtos,
            None,
            nome, marca, categoria,
            0, 0.0, 0.0, 0.0,
            validade, foto_url, codigo_barras,
            p_pai_id=None # Este é o pai
        )
        
        # 2. Cria as Variações (Filhos)
        cont_variacoes = 0
        for var in variações:
            if var["Nome"] and var["Quantidade"] > 0:
                produtos, _ = add_product_row(
                    produtos,
                    None,
                    f"{nome} ({var['Nome']})", marca, categoria,
                    var["Quantidade"], var["PrecoCusto"], var["PrecoVista"], var["PrecoCartao"],
                    validade, foto_url, var["CodigoBarras"],
                    p_pai_id=pai_id # Referência ao Pai
                )
                cont_variacoes += 1
                
        if cont_variacoes > 0:
            if save_csv_github(produtos, ARQ_PRODUTOS, f"Novo produto com grade: {nome} ({cont_variacoes} variações)"):
                st.session_state.produtos = produtos
                inicializar_produtos.clear()
                st.success(f"Produto '{nome}' com {cont_variacoes} variações cadastrado com sucesso!")
                # Limpa campos do formulário complexo
                st.session_state.cad_nome = ""
                st.session_state.cad_marca = ""
                st.session_state.cad_categoria = ""
                st.session_state.cad_validade = date.today()
                st.session_state.cad_foto_url = ""
                if "codigo_barras" in st.session_state: del st.session_state["codigo_barras"]
                st.session_state.cb_grade_lidos = {}
                return True
            return False
        else:
            # Se não adicionou variações, exclui o pai criado (ou avisa)
            produtos = produtos[produtos["ID"] != pai_id]
            st.session_state.produtos = produtos
            st.error("Nenhuma variação válida foi fornecida. O produto principal não foi salvo.")
            return False
    return False

def callback_adicionar_manual(nome, qtd, preco, custo):
    if nome and qtd > 0:
        st.session_state.lista_produtos.append({
            "Produto_ID": "", 
            "Produto": nome,
            "Quantidade": qtd,
            "Preço Unitário": preco,
            "Custo Unitário": custo 
        })
        st.session_state.input_nome_prod_manual = ""
        st.session_state.input_qtd_prod_manual = 1.0
        st.session_state.input_preco_prod_manual = 0.01
        st.session_state.input_custo_prod_manual = 0.00
        st.session_state.input_produto_selecionado = "" 
        
def callback_adicionar_estoque(prod_id, prod_nome, qtd, preco, custo, estoque_disp):
    
    # É importante carregar as promoções aqui, pois é onde o desconto é aplicado
    promocoes = norm_promocoes(carregar_promocoes())
    hoje = date.today()
    
    # Verifica se o produto tem promoção ativa hoje
    promocao_ativa = promocoes[
        (promocoes["IDProduto"] == prod_id) & 
        (promocoes["DataInicio"] <= hoje) & 
        (promocoes["DataFim"] >= hoje)
    ]
    
    # Se houver promoção, aplica o desconto
    preco_unitario_final = preco
    desconto_aplicado = 0.0
    if not promocao_ativa.empty:
        desconto_aplicado = promocao_ativa.iloc[0]["Desconto"] / 100.0
        preco_unitario_final = preco * (1 - desconto_aplicado)
        st.toast(f"🏷️ Promoção de {promocao_ativa.iloc[0]['Desconto']:.0f}% aplicada a {prod_nome}!")

    if qtd > 0 and qtd <= estoque_disp:
        st.session_state.lista_produtos.append({
            "Produto_ID": prod_id, 
            "Produto": prod_nome,
            "Quantidade": qtd,
            # Usa o preço com desconto, se houver
            "Preço Unitário": round(float(preco_unitario_final), 2), 
            "Custo Unitário": custo 
        })
        st.session_state.input_produto_selecionado = ""
    else:
        st.warning("A quantidade excede o estoque ou é inválida.")

# ==============================================================================
# FUNÇÕES AUXILIARES PARA HOME E ANÁLISE DE PRODUTOS
# ==============================================================================

@st.cache_data(show_spinner="Calculando mais vendidos...")
def get_most_sold_products(df_movimentacoes):
    """
    Calcula os produtos mais vendidos (por quantidade de itens vendidos).
    CORRIGIDO: Tratamento de erro robusto para garantir a chave 'Produto_ID'.
    """
    
    # 1. Filtra apenas as transações de Entrada (vendas) que foram Realizadas
    df_vendas = df_movimentacoes[
        (df_movimentacoes["Tipo"] == "Entrada") & 
        (df_movimentacoes["Status"] == "Realizada") &
        (df_movimentacoes["Produtos Vendidos"].notna()) &
        (df_movimentacoes["Produtos Vendidos"] != "")
    ].copy()

    if df_vendas.empty:
        # Garante que o DataFrame de saída tenha as colunas esperadas para o merge
        return pd.DataFrame(columns=["Produto_ID", "Quantidade Total Vendida"])

    vendas_list = []
    
    # 2. Desempacota o JSON de Produtos Vendidos
    for produtos_json in df_vendas["Produtos Vendidos"]:
        try:
            # Tenta usar json.loads, mas usa ast.literal_eval como fallback
            try:
                produtos = json.loads(produtos_json)
            except (json.JSONDecodeError, TypeError):
                produtos = ast.literal_eval(produtos_json)
            
            if isinstance(produtos, list):
                for item in produtos:
                    # CORREÇÃO: Garante que 'Produto_ID' existe antes de tentar acessá-lo.
                    # Se não existir (dados antigos), pula o item.
                    produto_id = str(item.get("Produto_ID"))
                    if produto_id and produto_id != "None":
                         vendas_list.append({
                            "Produto_ID": produto_id,
                            "Quantidade": to_float(item.get("Quantidade", 0))
                        })
        except Exception:
            # Ignora linhas com JSON de produto totalmente malformado
            continue
            
    df_vendas_detalhada = pd.DataFrame(vendas_list)
    
    if df_vendas_detalhada.empty:
        # Garante a coluna Produto_ID mesmo que vazia para o merge na homepage
        return pd.DataFrame(columns=["Produto_ID", "Quantidade Total Vendida"])

    # 3. Soma as quantidades por Produto_ID
    df_mais_vendidos = df_vendas_detalhada.groupby("Produto_ID")["Quantidade"].sum().reset_index()
    df_mais_vendidos.rename(columns={"Quantidade": "Quantidade Total Vendida"}, inplace=True)
    df_mais_vendidos.sort_values(by="Quantidade Total Vendida", ascending=False, inplace=True)
    
    return df_mais_vendidos

# ==============================================================================
# PÁGINAS DO NOVO MÓDULO (PRECIFICAÇÃO)
# ==============================================================================

# ==============================================================================
# FUNÇÃO DA PÁGINA: PRECIFICAÇÃO COMPLETA (Versão Geral)
# ==============================================================================

def precificacao_completa():
    st.title("💸 Precificador de Produtos (Geral)")
    
    # --- Configurações do GitHub para SALVAR ---
    # Usando as variáveis globais do app.py
    global GITHUB_TOKEN, GITHUB_REPO, GITHUB_BRANCH 
    PATH_PRECFICACAO = "precificacao.csv"
    ARQ_CAIXAS = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/" + PATH_PRECFICACAO
    imagens_dict = {}
    
    # ----------------------------------------------------
    # Inicialização e Configurações
    # ----------------------------------------------------
    
    # Inicialização de variáveis de estado da Precificação
    if "produtos_manuais" not in st.session_state:
        st.session_state.produtos_manuais = pd.DataFrame(columns=[
            "Produto", "Qtd", "Custo Unitário", "Custos Extras Produto", "Margem (%)", "Imagem", "Imagem_URL"
        ])
    
    # Garante a coluna Imagem_URL para produtos existentes que possam ter sido carregados
    if "Imagem_URL" not in st.session_state.produtos_manuais.columns:
        st.session_state.produtos_manuais["Imagem_URL"] = ""

    # Inicialização de df_produtos_geral com dados de exemplo (se necessário)
    if "df_produtos_geral" not in st.session_state or st.session_state.df_produtos_geral.empty:
        exemplo_data = [
            {"Produto": "Produto A", "Qtd": 10, "Custo Unitário": 5.0, "Margem (%)": 20, "Preço à Vista": 6.0, "Preço no Cartão": 6.5},
            {"Produto": "Produto B", "Qtd": 5, "Custo Unitário": 3.0, "Margem (%)": 15, "Preço à Vista": 3.5, "Preço no Cartão": 3.8},
        ]
        df_base = pd.DataFrame(exemplo_data)
        df_base["Custos Extras Produto"] = 0.0
        df_base["Imagem"] = None
        df_base["Imagem_URL"] = ""

        st.session_state.df_produtos_geral = processar_dataframe(df_base, 0.0, 0.0, "Margem fixa", 30.0)
        st.session_state.produtos_manuais = df_base.copy()


    if "frete_manual" not in st.session_state:
        st.session_state["frete_manual"] = 0.0
    if "extras_manual" not in st.session_state:
        st.session_state["extras_manual"] = 0.0
    if "modo_margem" not in st.session_state:
        st.session_state["modo_margem"] = "Margem fixa"
    if "margem_fixa" not in st.session_state:
        st.session_state["margem_fixa"] = 30.0

    frete_total = st.session_state.get("frete_manual", 0.0)
    custos_extras = st.session_state.get("extras_manual", 0.0)
    modo_margem = st.session_state.get("modo_margem", "Margem fixa")
    margem_fixa = st.session_state.get("margem_fixa", 30.0)
    
    
    # ----------------------------------------------------
    # Lógica de Salvamento Automático
    # ----------------------------------------------------
    
    # Prepara o DataFrame para salvar: remove a coluna 'Imagem' que contém bytes
    df_to_hash = st.session_state.produtos_manuais.drop(columns=["Imagem"], errors='ignore')

    # 1. Inicializa o hash para o estado da precificação
    if "hash_precificacao" not in st.session_state:
        st.session_state.hash_precificacao = hash_df(df_to_hash)

    # 2. Verifica se houve alteração nos produtos manuais para salvar automaticamente
    novo_hash = hash_df(df_to_hash)
    if novo_hash != st.session_state.hash_precificacao:
        if novo_hash != "error": # Evita salvar se a função hash falhou
            salvar_csv_no_github(
                GITHUB_TOKEN,
                GITHUB_REPO,
                PATH_PRECFICACAO,
                df_to_hash, # Salva o df sem a coluna 'Imagem'
                GITHUB_BRANCH,
                mensagem="♻️ Alteração automática na precificação"
            )
            st.session_state.hash_precificacao = novo_hash


    # ----------------------------------------------------
    # Tabela Geral (com Edição e Exclusão)
    # ----------------------------------------------------
    st.subheader("Produtos cadastrados (Clique no índice da linha e use DEL para excluir)")
    
    cols_display = [
        "Produto", "Qtd", "Custo Unitário", "Custos Extras Produto", 
        "Custo Total Unitário", "Margem (%)", "Preço à Vista", "Preço no Cartão"
    ]
    cols_to_show = [col for col in cols_display if col in st.session_state.df_produtos_geral.columns]

    editado_df = st.data_editor(
        st.session_state.df_produtos_geral[cols_to_show],
        num_rows="dynamic", # Permite que o usuário adicione ou remova linhas
        use_container_width=True,
        key="editor_produtos_geral"
    )

    original_len = len(st.session_state.df_produtos_geral)
    edited_len = len(editado_df)
    
    # 1. Lógica de Exclusão
    if edited_len < original_len:
        
        # Filtra os produtos_manuais para manter apenas aqueles que sobreviveram na edição
        produtos_manuais_filtrado = st.session_state.produtos_manuais[
            st.session_state.produtos_manuais['Produto'].isin(editado_df['Produto'])
        ].copy()
        
        st.session_state.produtos_manuais = produtos_manuais_filtrado.reset_index(drop=True)

        # Atualiza o DataFrame geral
        st.session_state.df_produtos_geral = processar_dataframe(
            st.session_state.produtos_manuais, frete_total, custos_extras, modo_margem, margem_fixa
        )
        
        st.success("✅ Produto excluído da lista e sincronizado.")
        st.rerun()
        
    # 2. Lógica de Edição de Dados
    elif not editado_df.equals(st.session_state.df_produtos_geral[cols_to_show]):
        
        # 2a. Sincroniza as mudanças essenciais de volta ao produtos_manuais
        for idx, row in editado_df.iterrows():
            produto_nome = str(row.get('Produto'))
            
            # Encontra o índice correspondente no produtos_manuais
            manual_idx = st.session_state.produtos_manuais[st.session_state.produtos_manuais['Produto'] == produto_nome].index
            
            if not manual_idx.empty:
                manual_idx = manual_idx[0]
                
                # O Custo Unitário (base) e a Margem são os campos que realmente importam para o recálculo
                st.session_state.produtos_manuais.loc[manual_idx, "Produto"] = produto_nome
                st.session_state.produtos_manuais.loc[manual_idx, "Qtd"] = row.get("Qtd", 1)
                st.session_state.produtos_manuais.loc[manual_idx, "Custo Unitário"] = row.get("Custo Unitário", 0.0)
                st.session_state.produtos_manuais.loc[manual_idx, "Margem (%)"] = row.get("Margem (%)", margem_fixa)
                st.session_state.produtos_manuais.loc[manual_idx, "Custos Extras Produto"] = row.get("Custos Extras Produto", 0.0)


        # 2b. Recalcula o DataFrame geral com base no manual atualizado
        st.session_state.df_produtos_geral = processar_dataframe(
            st.session_state.produtos_manuais, frete_total, custos_extras, modo_margem, margem_fixa
        )
        
        st.success("✅ Dados editados e precificação recalculada!")
        st.rerun()

    # 3. Lógica de Adição (apenas alerta)
    elif edited_len > original_len:
        st.warning("⚠️ Use o formulário 'Novo Produto Manual' ou o carregamento de CSV para adicionar produtos.")
        # Reverte a adição no df_produtos_geral
        st.session_state.df_produtos_geral = st.session_state.df_produtos_geral
        st.rerun() 


    if st.button("📤 Gerar PDF e enviar para Telegram", key='precificacao_pdf_button'):
        if st.session_state.df_produtos_geral.empty:
            st.warning("⚠️ Nenhum produto para gerar PDF.")
        else:
            pdf_io = gerar_pdf(st.session_state.df_produtos_geral)
            # Passa o DataFrame completo para a função de envio
            enviar_pdf_telegram(pdf_io, st.session_state.df_produtos_geral, thread_id=TOPICO_ID)
    
    st.markdown("---")
    
    # ----------------------------------------------------
    # Abas de Precificação
    # ----------------------------------------------------
    
    tab_pdf, tab_manual, tab_github = st.tabs([
        "📄 Precificador PDF (Mock)",
        "✍️ Precificador Manual",
        "📥 Carregar CSV (Geral)"
    ])

    # === Tab PDF ===
    with tab_pdf:
        st.markdown("---")
        pdf_file = st.file_uploader("📤 Selecione o PDF da nota fiscal ou lista de compras", type=["pdf"])
        if pdf_file:
            st.warning("A extração de dados do PDF está em desenvolvimento e não está ativa.")
            try:
                produtos_pdf = extrair_produtos_pdf(pdf_file)
                if not produtos_pdf:
                    st.warning("⚠️ Nenhum produto encontrado no PDF. Use o CSV de exemplo abaixo.")
                # Restante da lógica de carregamento do PDF omitida, pois a função `extrair_produtos_pdf` é mockada.
            except Exception as e:
                st.error(f"❌ Erro ao processar o PDF: {e}")
        else:
            st.info("📄 Faça upload de um arquivo PDF para começar.")
            if st.button("📥 Carregar CSV de exemplo (Geral)"):
                df_exemplo = load_csv_github(ARQ_CAIXAS)
                if not df_exemplo.empty:
                    df_exemplo["Custos Extras Produto"] = 0.0
                    df_exemplo["Imagem"] = None
                    if "Imagem_URL" not in df_exemplo.columns:
                        df_exemplo["Imagem_URL"] = ""

                    st.session_state.produtos_manuais = df_exemplo.copy()
                    st.session_state.df_produtos_geral = processar_dataframe(
                        df_exemplo, frete_total, custos_extras, modo_margem, margem_fixa
                    )
                    exibir_resultados(st.session_state.df_produtos_geral, imagens_dict)
                    st.rerun()

    # === Tab Manual ===
    with tab_manual:
        st.markdown("---")
        aba_prec_manual, aba_rateio = st.tabs(["✍️ Novo Produto Manual", "🔢 Rateio Manual"])

        with aba_rateio:
            st.subheader("🔢 Cálculo de Rateio Unitário (Frete + Custos Extras)")
            col_r1, col_r2, col_r3 = st.columns(3)
            with col_r1:
                frete_manual = st.number_input("🚚 Frete Total (R$)", min_value=0.0, step=0.01, key="frete_manual")
            with col_r2:
                extras_manual = st.number_input("🛠 Custos Extras (R$)", min_value=0.0, step=0.01, key="extras_manual")
            with col_r3:
                qtd_total_produtos = st.session_state.df_produtos_geral["Qtd"].sum() if "Qtd" in st.session_state.df_produtos_geral.columns else 0
                st.markdown(f"📦 **Qtd. Total de Produtos no DF:** {qtd_total_produtos}")
                
            qtd_total_manual = st.number_input("📦 Qtd. Total para Rateio (ajuste)", min_value=1, step=1, value=qtd_total_produtos or 1, key="qtd_total_manual_override")


            if qtd_total_manual > 0:
                rateio_calculado = (frete_manual + extras_manual) / qtd_total_manual
            else:
                rateio_calculado = 0.0

            st.session_state["rateio_manual"] = round(rateio_calculado, 4)
            st.markdown(f"💰 **Rateio Unitário Calculado:** R$ {rateio_calculado:,.4f}")
            
            if st.button("🔄 Aplicar Novo Rateio aos Produtos Existentes", key="aplicar_rateio_btn"):
                # A re-aplicação do rateio exige que se use o df_produtos_manuais como base
                # para garantir que todos os campos de input sejam recalculados.
                st.session_state.df_produtos_geral = processar_dataframe(
                    st.session_state.produtos_manuais,
                    frete_total,
                    custos_extras,
                    modo_margem,
                    margem_fixa
                )
                st.success("✅ Rateio aplicado! Verifique a tabela principal.")
                st.rerun() 

        with aba_prec_manual:
            # Rerunning para limpar o formulário após a adição
            if st.session_state.get("rerun_after_add"):
                del st.session_state["rerun_after_add"]
                st.rerun()

            st.subheader("Adicionar novo produto")

            col1, col2 = st.columns(2)
            with col1:
                produto = st.text_input("📝 Nome do Produto", key="input_produto_manual")
                quantidade = st.number_input("📦 Quantidade", min_value=1, step=1, key="input_quantidade_manual")
                valor_pago = st.number_input("💰 Valor Pago (Custo Unitário Base R$)", min_value=0.0, step=0.01, key="input_valor_pago_manual")
                
                # --- Campo de URL da Imagem ---
                imagem_url = st.text_input("🔗 URL da Imagem (opcional)", key="input_imagem_url_manual")
                # --- FIM NOVO ---

                
            with col2:
                valor_default_rateio = st.session_state.get("rateio_manual", 0.0)
                custo_extra_produto = st.number_input(
                    "💰 Custos extras do Produto (R$) + Rateio Global", min_value=0.0, step=0.01, value=valor_default_rateio, key="input_custo_extra_manual"
                )
                preco_final_sugerido = st.number_input(
                    "💸 Valor Final Sugerido (Preço à Vista) (R$)", min_value=0.0, step=0.01, key="input_preco_sugerido_manual"
                )
                
                # Uploader de arquivo (mantido como alternativa)
                imagem_file = st.file_uploader("🖼️ Foto do Produto (Upload - opcional)", type=["png", "jpg", "jpeg"], key="imagem_manual")


            custo_total_unitario = valor_pago + custo_extra_produto

            if preco_final_sugerido > 0:
                margem_calculada = 0.0
                if custo_total_unitario > 0:
                    margem_calculada = (preco_final_sugerido / custo_total_unitario - 1) * 100
                margem_manual = round(margem_calculada, 2)
                st.info(f"🧮 Margem calculada automaticamente (com base no preço sugerido): {margem_manual:.2f}%")
                preco_a_vista_calc = preco_final_sugerido
            else:
                margem_manual = st.number_input("🧮 Margem de Lucro (%)", min_value=0.0, value=30.0, key="input_margem_manual")
                preco_a_vista_calc = custo_total_unitario * (1 + margem_manual / 100)

            preco_no_cartao_calc = preco_a_vista_calc / 0.8872

            st.markdown(f"**Preço à Vista Calculado:** R$ {preco_a_vista_calc:,.2f}")
            st.markdown(f"**Preço no Cartão Calculado:** R$ {preco_no_cartao_calc:,.2f}")

            with st.form("form_submit_manual"):
                adicionar_produto = st.form_submit_button("➕ Adicionar Produto (Manual)")
                if adicionar_produto:
                    if produto and quantidade > 0 and valor_pago >= 0:
                        imagem_bytes = None
                        url_salvar = ""

                        # Prioriza o arquivo uploaded, se existir
                        if imagem_file is not None:
                            imagem_bytes = imagem_file.read()
                            imagens_dict[produto] = imagem_bytes # Guarda para exibição na sessão
                        
                        # Se não houver upload, usa a URL
                        elif imagem_url.strip():
                            url_salvar = imagem_url.strip()

                        # Se houver upload, a URL salva deve ser vazia, e vice-versa.
                        # O CSV irá persistir a Imagem_URL.

                        novo_produto_data = {
                            "Produto": [produto],
                            "Qtd": [quantidade],
                            "Custo Unitário": [valor_pago],
                            "Custos Extras Produto": [custo_extra_produto],
                            "Margem (%)": [margem_manual],
                            "Imagem": [imagem_bytes],
                            "Imagem_URL": [url_salvar] # Salva a URL para persistência
                        }
                        novo_produto = pd.DataFrame(novo_produto_data)

                        # Adiciona ao produtos_manuais
                        st.session_state.produtos_manuais = pd.concat(
                            [st.session_state.produtos_manuais, novo_produto],
                            ignore_index=True
                        ).reset_index(drop=True)
                        
                        # Processa e atualiza o DataFrame geral
                        st.session_state.df_produtos_geral = processar_dataframe(
                            st.session_state.produtos_manuais,
                            frete_total,
                            custos_extras,
                            modo_margem,
                            margem_fixa
                        )
                        st.success("✅ Produto adicionado!")
                        st.session_state["rerun_after_add"] = True 
                    else:
                        st.warning("⚠️ Preencha todos os campos obrigatórios.")

            st.markdown("---")
            st.subheader("Produtos adicionados manualmente (com botão de Excluir individual)")

            # Exibir produtos com botão de exclusão
            produtos_manuais_lista = st.session_state.produtos_manuais

            if produtos_manuais_lista.empty:
                st.info("⚠️ Nenhum produto cadastrado manualmente.")
            else:
                if "produto_para_excluir" not in st.session_state:
                    st.session_state["produto_para_excluir"] = None
                
                # Exibir produtos individualmente com a opção de exclusão
                for i, row in produtos_manuais_lista.iterrows():
                    cols = st.columns([4, 1])
                    with cols[0]:
                        custo_unit_val = row.get('Custo Unitário', 0.0)
                        st.write(f"**{row['Produto']}** — Quantidade: {row['Qtd']} — Custo Unitário Base: R$ {custo_unit_val:.2f}")
                    with cols[1]:
                        if st.button(f"❌ Excluir", key=f"excluir_{i}"):
                            st.session_state["produto_para_excluir"] = i
                            break 

                # Processamento da Exclusão
                if st.session_state["produto_para_excluir"] is not None:
                    i = st.session_state["produto_para_excluir"]
                    produto_nome_excluido = produtos_manuais_lista.loc[i, "Produto"]
                    
                    # 1. Remove do DataFrame manual
                    st.session_state.produtos_manuais = produtos_manuais_lista.drop(i).reset_index(drop=True)
                    
                    # 2. Recalcula e atualiza o DataFrame geral
                    st.session_state.df_produtos_geral = processar_dataframe(
                        st.session_state.produtos_manuais,
                        frete_total,
                        custos_extras,
                        modo_margem,
                        margem_fixa
                    )
                    
                    # 3. Limpa o estado e força o rerun
                    st.session_state["produto_para_excluir"] = None
                    st.success(f"✅ Produto '{produto_nome_excluido}' removido da lista manual.")
                    st.rerun()

            if "df_produtos_geral" in st.session_state and not st.session_state.df_produtos_geral.empty:
                exibir_resultados(st.session_state.df_produtos_geral, imagens_dict)
            else:
                st.info("⚠️ Nenhum produto processado para exibir.")

    # === Tab GitHub ===
    with tab_github:
        st.markdown("---")
        st.header("📥 Carregar CSV de Precificação do GitHub")
        if st.button("🔄 Carregar CSV do GitHub (Geral)"):
            df_exemplo = load_csv_github(ARQ_CAIXAS)
            if not df_exemplo.empty:
                df_exemplo["Custos Extras Produto"] = 0.0
                df_exemplo["Imagem"] = None
                
                # Garante a nova coluna ao carregar
                if "Imagem_URL" not in df_exemplo.columns:
                    df_exemplo["Imagem_URL"] = ""

                st.session_state.produtos_manuais = df_exemplo.copy()
                st.session_state.df_produtos_geral = processar_dataframe(
                    df_exemplo, frete_total, custos_extras, modo_margem, margem_fixa
                )
                st.success("✅ CSV carregado e processado com sucesso!")
                exibir_resultados(st.session_state.df_produtos_geral, imagens_dict)
                st.rerun()


# ==============================================================================
# FUNÇÃO DA PÁGINA: PAPELARIA
# ==============================================================================

def papelaria_aba():
    st.title("📚 Gerenciador Papelaria Personalizada (Módulo de Insumos)")
    
    # Variáveis de Configuração
    global GITHUB_TOKEN, GITHUB_REPO, GITHUB_BRANCH, OWNER, REPO_NAME, BRANCH
    URL_BASE = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/"
    INSUMOS_CSV_URL = URL_BASE + "insumos_papelaria.csv"
    PRODUTOS_CSV_URL = URL_BASE + "produtos_papelaria.csv"
    CAMPOS_CSV_URL = URL_BASE + "categorias_papelaria.csv"

    # Estado da sessão
    if "insumos" not in st.session_state:
        st.session_state.insumos = load_csv_github(INSUMOS_CSV_URL)

    if "produtos_papelaria" not in st.session_state:
        st.session_state.produtos_papelaria = load_csv_github(PRODUTOS_CSV_URL)

    if "campos" not in st.session_state:
        st.session_state.campos = load_csv_github(CAMPOS_CSV_URL)
        
    # Inicializações de estado para garantir DFs não nulos
    if "campos" not in st.session_state or st.session_state.campos is None or st.session_state.campos.empty:
        st.session_state.campos = pd.DataFrame(columns=["Campo", "Aplicação", "Tipo", "Opções"])

    if "insumos" not in st.session_state or st.session_state.insumos is None or st.session_state.insumos.empty:
        st.session_state.insumos = pd.DataFrame(columns=INSUMOS_BASE_COLS_GLOBAL)

    if "produtos_papelaria" not in st.session_state or st.session_state.produtos_papelaria is None or st.session_state.produtos_papelaria.empty:
        st.session_state.produtos_papelaria = pd.DataFrame(columns=["Produto", "Custo Total", "Preço à Vista", "Preço no Cartão", "Margem (%)", "Insumos Usados"])
    
    # Garante colunas base
    for col in INSUMOS_BASE_COLS_GLOBAL:
        if col not in st.session_state.insumos.columns:
            st.session_state.insumos[col] = "" if col != "Preço Unitário (R$)" else 0.0

    cols_base_prod = ["Produto"] + [c for c in PRODUTOS_BASE_COLS_GLOBAL if c != "Produto"]
    for col in cols_base_prod:
        if col not in st.session_state.produtos_papelaria.columns:
            st.session_state.produtos_papelaria[col] = "" if col not in ["Custo Total", "Preço à Vista", "Preço no Cartão", "Margem (%)"] else 0.0
            
    if "Insumos Usados" not in st.session_state.produtos_papelaria.columns:
        st.session_state.produtos_papelaria["Insumos Usados"] = "[]"


    # Garante colunas extras e tipos
    st.session_state.insumos = garantir_colunas_extras(st.session_state.insumos, "Insumos")
    st.session_state.produtos_papelaria = garantir_colunas_extras(st.session_state.produtos_papelaria, "Produtos")

    # Verifica se houve alteração nos produtos para salvar automaticamente
    if "hash_produtos_papelaria" not in st.session_state:
        st.session_state.hash_produtos_papelaria = hash_df(st.session_state.produtos_papelaria)

    novo_hash = hash_df(st.session_state.produtos_papelaria)
    if novo_hash != st.session_state.hash_produtos_papelaria:
        if novo_hash != "error": # Evita salvar se a função hash falhou
            salvar_csv_no_github(
                GITHUB_TOKEN,
                GITHUB_REPO,
                "produtos_papelaria.csv",
                st.session_state.produtos_papelaria,
                GITHUB_BRANCH,
                mensagem="♻️ Alteração automática nos produtos de papelaria"
            )
            st.session_state.hash_produtos_papelaria = novo_hash

    # Criação das abas
    aba_campos, aba_insumos, aba_produtos = st.tabs(["Campos (Colunas)", "Insumos", "Produtos"])

    # =====================================
    # Aba Campos (gerencia colunas extras)
    # =====================================
    with aba_campos:
        st.header("Campos / Colunas Personalizadas")

        with st.form("form_add_campo"):
            st.subheader("Adicionar novo campo")
            nome_campo = st.text_input("Nome do Campo (será o nome da coluna)", key="novo_campo_nome")
            aplicacao = st.selectbox("Aplicação", ["Insumos", "Produtos", "Ambos"], key="novo_campo_aplicacao")
            tipo = st.selectbox("Tipo", ["Texto", "Número", "Seleção"], key="novo_campo_tipo")
            opcoes = st.text_input("Opções (se 'Seleção', separe por vírgula)", key="novo_campo_opcoes")
            adicionar = st.form_submit_button("Adicionar Campo")

            if adicionar:
                if not nome_campo.strip():
                    st.warning("Informe um nome de campo válido.")
                else:
                    ja_existe = (
                        (st.session_state.campos["Campo"].astype(str).str.lower() == nome_campo.strip().lower())
                        & (st.session_state.campos["Aplicação"] == aplicacao)
                    ).any()
                    if ja_existe:
                        st.warning("Já existe um campo com esse nome para essa aplicação.")
                    else:
                        nova_linha = {
                            "Campo": nome_campo.strip(),
                            "Aplicação": aplicacao,
                            "Tipo": tipo,
                            "Opções": opcoes
                        }
                        st.session_state.campos = pd.concat(
                            [st.session_state.campos, pd.DataFrame([nova_linha])],
                            ignore_index=True
                        ).reset_index(drop=True)
                        st.success(f"Campo '{nome_campo}' adicionado para {aplicacao}!")
                        
                        st.session_state.insumos = garantir_colunas_extras(st.session_state.insumos, "Insumos")
                        st.session_state.produtos_papelaria = garantir_colunas_extras(st.session_state.produtos_papelaria, "Produtos")
                        
                        st.rerun()

        st.markdown("### Campos cadastrados")
        if st.session_state.campos.empty:
            st.info("Nenhum campo extra cadastrado ainda.")
        else:
            st.dataframe(st.session_state.campos, use_container_width=True)

        if not st.session_state.campos.empty:
            st.divider()
            st.subheader("Editar ou Excluir campo")
            rotulos = [
                f"{row.Campo} · ({row.Aplicação})"
                for _, row in st.session_state.campos.iterrows()
            ]
            escolha = st.selectbox("Escolha um campo", [""] + rotulos, key="campo_escolhido_edit_del")
            
            if escolha:
                idx_list = st.session_state.campos.index[st.session_state.campos.apply(lambda row: f"{row.Campo} · ({row.Aplicação})" == escolha, axis=1)].tolist()
                idx = idx_list[0] if idx_list else None
                
                if idx is not None:
                    campo_atual = st.session_state.campos.loc[idx]
                    
                    acao_campo = st.radio(
                        "Ação",
                        ["Nenhuma", "Editar", "Excluir"],
                        horizontal=True,
                        key=f"acao_campo_{idx}"
                    )
                    
                    if acao_campo == "Excluir":
                        if st.button("Confirmar Exclusão", key=f"excluir_campo_{idx}"):
                            nome = campo_atual["Campo"]
                            aplic = campo_atual["Aplicação"]
                            
                            st.session_state.campos = st.session_state.campos.drop(index=idx).reset_index(drop=True)
                            
                            if aplic in ("Insumos", "Ambos") and nome in st.session_state.insumos.columns:
                                st.session_state.insumos = st.session_state.insumos.drop(columns=[nome], errors='ignore')
                            if aplic in ("Produtos", "Ambos") and nome in st.session_state.produtos_papelaria.columns:
                                st.session_state.produtos_papelaria = st.session_state.produtos_papelaria.drop(columns=[nome], errors='ignore')
                                
                            st.success(f"Campo '{nome}' removido de {aplic}!")
                            st.rerun()
                            
                    if acao_campo == "Editar":
                        with st.form(f"form_edit_campo_{idx}"):
                            novo_nome = st.text_input("Nome do Campo", value=str(campo_atual["Campo"]), key=f"edit_nome_{idx}")
                            
                            aplic_opts = ["Insumos", "Produtos", "Ambos"]
                            aplic_idx = aplic_opts.index(campo_atual["Aplicação"])
                            nova_aplic = st.selectbox("Aplicação", aplic_opts, index=aplic_idx, key=f"edit_aplic_{idx}")
                            
                            tipo_opts = ["Texto", "Número", "Seleção"]
                            tipo_idx = tipo_opts.index(campo_atual["Tipo"])
                            novo_tipo = st.selectbox("Tipo", tipo_opts, index=tipo_idx, key=f"edit_tipo_{idx}")
                            
                            novas_opcoes = st.text_input("Opções (se 'Seleção')", value=str(campo_atual["Opções"]) if pd.notna(campo_atual["Opções"]) else "", key=f"edit_opcoes_{idx}")
                            
                            salvar = st.form_submit_button("Salvar Alterações")
                            
                            if salvar:
                                nome_antigo = campo_atual["Campo"]
                                aplic_antiga = campo_atual["Aplicação"]
                                
                                st.session_state.campos.loc[idx, ["Campo","Aplicação","Tipo","Opções"]] = [
                                    novo_nome, nova_aplic, novo_tipo, novas_opcoes
                                ]
                                
                                renomeou = (str(novo_nome).strip() != str(nome_antigo).strip())
                                
                                if renomeou:
                                    if aplic_antiga in ("Insumos", "Ambos") and nome_antigo in st.session_state.insumos.columns:
                                        st.session_state.insumos = st.session_state.insumos.rename(columns={nome_antigo: novo_nome})
                                    if aplic_antiga in ("Produtos", "Ambos") and nome_antigo in st.session_state.produtos_papelaria.columns:
                                        st.session_state.produtos_papelaria = st.session_state.produtos_papelaria.rename(columns={nome_antigo: novo_nome})
                                        
                                st.session_state.insumos = garantir_colunas_extras(st.session_state.insumos, "Insumos")
                                st.session_state.produtos_papelaria = garantir_colunas_extras(st.session_state.produtos_papelaria, "Produtos")

                                st.success("Campo atualizado!")
                                st.rerun()
                            
        if not st.session_state.produtos_papelaria.empty:
            st.markdown("### 📥 Exportação (aba Campos)")
            baixar_csv_aba(st.session_state.produtos_papelaria, "produtos_papelaria.csv", key_suffix="campos_papelaria")


    # =====================================
    # Aba Insumos
    # =====================================
    with aba_insumos:
        st.header("Insumos")

        st.session_state.insumos = garantir_colunas_extras(st.session_state.insumos, "Insumos")

        with st.form("form_add_insumo"):
            st.subheader("Adicionar novo insumo")
            nome_insumo = st.text_input("Nome do Insumo", key="novo_insumo_nome")
            categoria_insumo = st.text_input("Categoria", key="novo_insumo_categoria")
            unidade_insumo = st.text_input("Unidade de Medida (ex: un, kg, m)", key="novo_insumo_unidade")
            preco_insumo = st.number_input("Preço Unitário (R$)", min_value=0.0, format="%.2f", key="novo_insumo_preco")

            extras_insumos = col_defs_para("Insumos")
            valores_extras = {}
            if not extras_insumos.empty:
                st.markdown("**Campos extras**")
                for i, row in extras_insumos.reset_index(drop=True).iterrows():
                    key = f"novo_insumo_extra_{row['Campo']}"
                    valores_extras[row["Campo"]] = render_input_por_tipo(
                        label=row["Campo"],
                        tipo=row["Tipo"],
                        opcoes=row["Opções"],
                        valor_padrao=None,
                        key=key
                    )

            adicionou = st.form_submit_button("Adicionar Insumo")
            if adicionou:
                if not nome_insumo.strip():
                    st.warning("Informe o Nome do Insumo.")
                else:
                    novo = {
                        "Nome": nome_insumo.strip(),
                        "Categoria": categoria_insumo.strip(),
                        "Unidade": unidade_insumo.strip(),
                        "Preço Unitário (R$)": float(preco_insumo),
                    }
                    for k, v in valores_extras.items():
                        novo[k] = v
                        
                    st.session_state.insumos = garantir_colunas_extras(st.session_state.insumos, "Insumos")
                    
                    st.session_state.insumos = pd.concat([st.session_state.insumos, pd.DataFrame([novo])], ignore_index=True).reset_index(drop=True)
                    st.success(f"Insumo '{nome_insumo}' adicionado!")
                    st.rerun()

        st.markdown("### Insumos cadastrados")
        ordem_cols = INSUMOS_BASE_COLS_GLOBAL + [c for c in st.session_state.insumos.columns if c not in INSUMOS_BASE_COLS_GLOBAL]
        st.dataframe(st.session_state.insumos.reindex(columns=ordem_cols), use_container_width=True)

        if not st.session_state.insumos.empty:
            insumo_selecionado = st.selectbox(
                "Selecione um insumo",
                [""] + st.session_state.insumos["Nome"].astype(str).fillna("").tolist(),
                key="insumo_escolhido_edit_del"
            )
        else:
            insumo_selecionado = None

        if insumo_selecionado:
            acao_insumo = st.radio(
                f"Ação para '{insumo_selecionado}'",
                ["Nenhuma", "Editar", "Excluir"],
                horizontal=True,
                key=f"acao_insumo_{insumo_selecionado}"
            )

            idxs = st.session_state.insumos.index[st.session_state.insumos["Nome"] == insumo_selecionado].tolist()
            idx = idxs[0] if idxs else None

            if acao_insumo == "Excluir" and idx is not None:
                if st.button("Confirmar Exclusão", key=f"excluir_insumo_{idx}"):
                    st.session_state.insumos = st.session_state.insumos.drop(index=idx).reset_index(drop=True)
                    st.success(f"Insumo '{insumo_selecionado}' removido!")
                    st.rerun()

            if acao_insumo == "Editar" and idx is not None:
                atual = st.session_state.insumos.loc[idx].fillna("")
                with st.form(f"form_edit_insumo_{idx}"):
                    novo_nome = st.text_input("Nome do Insumo", value=str(atual.get("Nome","")), key=f"edit_insumo_nome_{idx}")
                    nova_categoria = st.text_input("Categoria", value=str(atual.get("Categoria","")), key=f"edit_insumo_categoria_{idx}")
                    nova_unidade = st.text_input("Unidade de Medida (ex: un, kg, m)", value=str(atual.get("Unidade","")), key=f"edit_insumo_unidade_{idx}")
                    novo_preco = st.number_input(
                        "Preço Unitário (R$)", min_value=0.0, format="%.2f",
                        value=float(atual.get("Preço Unitário (R$)", 0.0)),
                        key=f"edit_insumo_preco_{idx}"
                    )

                    valores_extras_edit = {}
                    extras_insumos = col_defs_para("Insumos")
                    if not extras_insumos.empty:
                        st.markdown("**Campos extras**")
                        for i, row in extras_insumos.reset_index(drop=True).iterrows():
                            campo = row["Campo"]
                            key = f"edit_insumo_extra_{idx}_{campo}"
                            valores_extras_edit[campo] = render_input_por_tipo(
                                label=campo,
                                tipo=row["Tipo"],
                                opcoes=row["Opções"],
                                valor_padrao=atual.get(campo, ""),
                                key=key
                            )

                    salvou = st.form_submit_button("Salvar Alterações", key=f"salvar_insumo_{idx}")
                    if salvou:
                        st.session_state.insumos.loc[idx, "Nome"] = novo_nome
                        st.session_state.insumos.loc[idx, "Categoria"] = nova_categoria
                        st.session_state.insumos.loc[idx, "Unidade"] = nova_unidade
                        st.session_state.insumos.loc[idx, "Preço Unitário (R$)"] = float(novo_preco)
                        for k, v in valores_extras_edit.items():
                            st.session_state.insumos.loc[idx, k] = v
                        st.success("Insumo atualizado!")
                        st.rerun()


    # =====================================
    # Aba Produtos
    # =====================================
    with aba_produtos:
        st.header("Produtos")

        with st.form("form_add_produto"):
            st.subheader("Adicionar novo produto")
            nome_produto = st.text_input("Nome do Produto", key="novo_produto_nome")

            if 'Nome' in st.session_state.insumos.columns:
                insumos_disponiveis = st.session_state.insumos["Nome"].dropna().unique().tolist()
            else:
                insumos_disponiveis = []

            insumos_selecionados = st.multiselect("Selecione os insumos usados", insumos_disponiveis, key="novo_produto_insumos_selecionados")

            insumos_usados = []
            custo_total = 0.0

            for insumo in insumos_selecionados:
                dados_insumo = st.session_state.insumos.loc[st.session_state.insumos["Nome"] == insumo].iloc[0]
                preco_unit = float(dados_insumo.get("Preço Unitário (R$)", 0.0))
                unidade = str(dados_insumo.get("Unidade", ""))

                qtd_usada = st.number_input(
                    f"Quantidade usada de {insumo} ({unidade}) - Preço unitário R$ {preco_unit:.2f}",
                    min_value=0.0,
                    step=0.01,
                    key=f"novo_qtd_{insumo}"
                )

                custo_insumo = qtd_usada * preco_unit
                custo_total += custo_insumo

                insumos_usados.append({
                    "Insumo": insumo,
                    "Quantidade Usada": qtd_usada,
                    "Unidade": unidade,
                    "Preço Unitário (R$)": preco_unit,
                    "Custo": custo_insumo
                })

            st.markdown(f"**Custo Total Calculado (Insumos): R$ {custo_total:,.2f}**")

            margem = st.number_input("Margem de Lucro (%)", min_value=0.0, format="%.2f", value=30.0, key="novo_produto_margem")

            preco_vista = custo_total * (1 + margem / 100) if custo_total > 0 else 0.0
            preco_cartao = preco_vista / 0.8872 if preco_vista > 0 else 0.0

            st.markdown(f"💸 **Preço à Vista Calculado:** R$ {preco_vista:,.2f}")
            st.markdown(f"💳 **Preço no Cartão Calculado:** R$ {preco_cartao:,.2f}")

            extras_produtos = col_defs_para("Produtos")
            valores_extras_prod = {}
            if not extras_produtos.empty:
                st.markdown("**Campos extras**")
                for i, row in extras_produtos.reset_index(drop=True).iterrows():
                    key = f"novo_produto_extra_{row['Campo']}"
                    valores_extras_prod[row["Campo"]] = render_input_por_tipo(
                        label=row["Campo"],
                        tipo=row["Tipo"],
                        opcoes=row["Opções"],
                        valor_padrao=None,
                        key=key
                    )

            adicionou_prod = st.form_submit_button("Adicionar Produto")
            if adicionou_prod:
                if not nome_produto.strip():
                    st.warning("Informe o Nome do Produto.")
                elif not insumos_usados:
                    st.warning("Selecione ao menos um insumo para o produto.")
                else:
                    novo = {
                        "Produto": nome_produto.strip(),
                        "Custo Total": float(custo_total),
                        "Preço à Vista": float(preco_vista),
                        "Preço no Cartão": float(preco_cartao),
                        "Margem (%)": float(margem),
                        "Insumos Usados": str(insumos_usados)
                    }
                    for k, v in valores_extras_prod.items():
                        novo[k] = v

                    # Envio da mensagem para o Telegram (mantido)
                    try:
                        TELEGRAM_TOKEN_SECRET = st.secrets.get("telegram_token", HARDCODED_TELEGRAM_TOKEN)
                        TELEGRAM_CHAT_ID_PROD = TELEGRAM_CHAT_ID
                        THREAD_ID_PROD = 43

                        mensagem = f"<b>📦 Novo Produto Cadastrado:</b>\n"
                        mensagem += f"<b>Produto:</b> {nome_produto}\n"
                        mensagem += "<b>Insumos:</b>\n"

                        for insumo in insumos_usados:
                            nome = insumo['Insumo']
                            qtd = insumo['Quantidade Usada']
                            un = insumo['Unidade']
                            custo = insumo['Custo']
                            mensagem += f"• {nome} - {qtd} {un} (R$ {custo:.2f})\n"

                        mensagem += f"\n<b>Custo Total:</b> R$ {custo_total:,.2f}"
                        mensagem += f"\n<b>Preço à Vista:</b> R$ {preco_vista:,.2f}"
                        mensagem += f"\n<b>Preço no Cartão:</b> R$ {preco_cartao:,.2f}"

                        telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN_SECRET}/sendMessage"
                        payload = {
                            "chat_id": TELEGRAM_CHAT_ID_PROD,
                            "message_thread_id": THREAD_ID_PROD,
                            "text": mensagem,
                            "parse_mode": "HTML"
                        }

                        response = requests.post(telegram_url, json=payload)
                        if response.status_code != 200:
                            st.warning(f"⚠️ Erro ao enviar para Telegram: {response.text}")
                        else:
                             st.success("✅ Mensagem enviada para o Telegram!")

                    except Exception as e:
                        st.warning(f"⚠️ Falha ao tentar enviar para o Telegram: {e}")

                    # Salva no DataFrame local
                    st.session_state.produtos_papelaria = garantir_colunas_extras(st.session_state.produtos_papelaria, "Produtos")
                    
                    st.session_state.produtos_papelaria = pd.concat(
                        [st.session_state.produtos_papelaria, pd.DataFrame([novo])],
                        ignore_index=True
                    ).reset_index(drop=True)
                    st.success(f"Produto '{nome_produto}' adicionado!")
                    st.rerun()

        st.markdown("### Produtos cadastrados")
        ordem_cols_p = PRODUTOS_BASE_COLS_GLOBAL + ["Insumos Usados"] + [c for c in st.session_state.produtos_papelaria.columns if c not in PRODUTOS_BASE_COLS_GLOBAL + ["Insumos Usados"]]
        st.dataframe(st.session_state.produtos_papelaria.reindex(columns=ordem_cols_p), use_container_width=True)

        if not st.session_state.produtos_papelaria.empty:
            produto_selecionado = st.selectbox(
                "Selecione um produto",
                [""] + st.session_state.produtos_papelaria["Produto"].astype(str).fillna("").tolist(),
                key="produto_escolhido_edit_del"
            )
        else:
            produto_selecionado = None

        if produto_selecionado:
            acao_produto = st.radio(
                f"Ação para '{produto_selecionado}'",
                ["Nenhuma", "Editar", "Excluir"],
                horizontal=True,
                key=f"acao_produto_{produto_selecionado}"
            )

            idxs_p = st.session_state.produtos_papelaria.index[st.session_state.produtos_papelaria["Produto"] == produto_selecionado].tolist()
            idx_p = idxs_p[0] if idxs_p else None

            if acao_produto == "Excluir" and idx_p is not None:
                if st.button("Confirmar Exclusão", key=f"excluir_produto_{idx_p}"):
                    st.session_state.produtos_papelaria = st.session_state.produtos_papelaria.drop(index=idx_p).reset_index(drop=True)
                    st.success(f"Produto '{produto_selecionado}' removido!")
                    st.rerun()

            if acao_produto == "Editar" and idx_p is not None:
                atual_p = st.session_state.produtos_papelaria.loc[idx_p].fillna("")
                with st.form(f"form_edit_produto_{idx_p}"):
                    novo_nome = st.text_input("Nome do Produto", value=str(atual_p.get("Produto","")), key=f"edit_produto_nome_{idx_p}")
                    nova_margem = st.number_input("Margem (%)", min_value=0.0, format="%.2f", value=float(atual_p.get("Margem (%)", 0.0)), key=f"edit_produto_margem_{idx_p}")

                    try:
                        insumos_atual = ast.literal_eval(atual_p.get("Insumos Usados", "[]"))
                        if not isinstance(insumos_atual, list):
                            insumos_atual = []
                    except Exception:
                        insumos_atual = []

                    insumos_disponiveis = st.session_state.insumos["Nome"].dropna().unique().tolist()
                    nomes_pre_selecionados = [i["Insumo"] for i in insumos_atual]
                    insumos_editados = st.multiselect("Selecione os insumos usados", insumos_disponiveis, default=nomes_pre_selecionados, key=f"edit_produto_insumos_selecionados_{idx_p}")

                    insumos_usados_edit = []
                    novo_custo = 0.0

                    for insumo in insumos_editados:
                        dados_insumo = st.session_state.insumos.loc[st.session_state.insumos["Nome"] == insumo].iloc[0]
                        preco_unit = float(dados_insumo.get("Preço Unitário (R$)", 0.0))
                        unidade = str(dados_insumo.get("Unidade", ""))

                        qtd_default = 0.0
                        for item in insumos_atual:
                            if item.get("Insumo") == insumo:
                                qtd_default = float(item.get("Quantidade Usada", 0.0))

                        qtd_usada = st.number_input(
                            f"Quantidade usada de {insumo} ({unidade}) - Preço unitário R$ {preco_unit:.2f}",
                            min_value=0.0,
                            step=0.01,
                            value=qtd_default,
                            key=f"edit_qtd_{idx_p}_{insumo}"
                        )

                        custo_insumo = qtd_usada * preco_unit
                        novo_custo += custo_insumo

                        insumos_usados_edit.append({
                            "Insumo": insumo,
                            "Quantidade Usada": qtd_usada,
                            "Unidade": unidade,
                            "Preço Unitário (R$)": preco_unit,
                            "Custo": custo_insumo
                        })

                    novo_vista = novo_custo * (1 + nova_margem / 100)
                    novo_cartao = novo_vista / 0.8872

                    st.markdown(f"**Novo custo calculado: R$ {novo_custo:,.2f}**")
                    st.markdown(f"💸 **Preço à Vista Recalculado:** R$ {novo_vista:,.2f}")
                    st.markdown(f"💳 **Preço no Cartão Recalculado:** R$ {novo_cartao:,.2f}")

                    valores_extras_edit_p = {}
                    extras_produtos = col_defs_para("Produtos")
                    if not extras_produtos.empty:
                        st.markdown("**Campos extras**")
                        for i, row in extras_produtos.reset_index(drop=True).iterrows():
                            campo = row["Campo"]
                            key = f"edit_produto_extra_{idx_p}_{campo}"
                            valores_extras_edit_p[campo] = render_input_por_tipo(
                                label=campo,
                                tipo=row["Tipo"],
                                opcoes=row["Opções"],
                                valor_padrao=atual_p.get(campo, ""),
                                key=key
                            )

                    salvou_p = st.form_submit_button("Salvar Alterações", key=f"salvar_produto_{idx_p}")
                    if salvou_p:
                        st.session_state.produtos_papelaria.loc[idx_p, "Produto"] = novo_nome
                        st.session_state.produtos_papelaria.loc[idx_p, "Custo Total"] = float(novo_custo)
                        st.session_state.produtos_papelaria.loc[idx_p, "Preço à Vista"] = float(novo_vista)
                        st.session_state.produtos_papelaria.loc[idx_p, "Preço no Cartão"] = float(novo_cartao)
                        # LINHA CORRIGIDA ABAIXO
                        st.session_state.produtos_papelaria.loc[idx_p, "Margem (%)"] = float(nova_margem)
                        st.session_state.produtos_papelaria.loc[idx_p, "Insumos Usados"] = str(insumos_usados_edit)
                        for k, v in valores_extras_edit_p.items():
                            st.session_state.produtos_papelaria.loc[idx_p, k] = v
                        st.success("Produto atualizado!")
                        st.rerun()

        # botão de exportação CSV fora dos forms
        if not st.session_state.produtos_papelaria.empty:
            baixar_csv_aba(st.session_state.produtos_papelaria, "produtos_papelaria.csv", key_suffix="produtos_papelaria")
            
# FIM DA FUNÇÃO papelaria_aba()


def precificacao_geral():
    """Roteador para as duas abas do precificador."""
    st.header("⚙️ Módulo de Precificação")
    
    # Roteamento interno na sidebar
    pagina_precificacao = st.sidebar.radio(
        "Selecione o Módulo de Precificação:",
        ["Precificação Geral", "Papelaria Personalizada"],
        key='prec_page_select_widget'
    )
    
    if pagina_precificacao == "Precificação Geral":
        precificacao_completa()
    elif pagina_precificacao == "Papelaria Personalizada":
        papelaria_aba()

# --- FIM PÁGINAS DO NOVO MÓDULO ---


# ==============================================================================
# PÁGINAS DO MÓDULO GESTÃO FINANCEIRA
# ==============================================================================

def homepage():
    # --- 1. Carrega dados e calcula métricas ---
    produtos_df = inicializar_produtos()
    df_movimentacoes = carregar_livro_caixa()
    
    # Produtos novos (últimos N cadastrados com estoque > 0)
    produtos_novos = produtos_df[produtos_df['Quantidade'] > 0].sort_values(by='ID', ascending=False).head(10) 
    
    # Produtos mais vendidos (Top N)
    df_mais_vendidos_id = get_most_sold_products(df_movimentacoes)
    top_ids_vendidos = df_mais_vendidos_id["Produto_ID"].head(10).tolist() if not df_mais_vendidos_id.empty else []
    if top_ids_vendidos:
        temp = produtos_df[produtos_df["ID"].isin(top_ids_vendidos)].copy()
        present_ids = [pid for pid in top_ids_vendidos if pid in temp["ID"].astype(str).values]
        if present_ids:
            produtos_mais_vendidos = temp.set_index("ID").loc[present_ids].reset_index()
        else:
            produtos_mais_vendidos = pd.DataFrame(columns=produtos_df.columns)
    else:
        produtos_mais_vendidos = pd.DataFrame(columns=produtos_df.columns)
    
    # Produtos em Oferta: PrecoCartao < PrecoVista (PrecoVista)
    produtos_oferta = produtos_df.copy()
    produtos_oferta['PrecoVista_f'] = pd.to_numeric(produtos_oferta['PrecoVista'], errors='coerce').fillna(0)
    produtos_oferta['PrecoCartao_f'] = pd.to_numeric(produtos_oferta['PrecoCartao'], errors='coerce').fillna(0)
    produtos_oferta = produtos_oferta[
        (produtos_oferta['PrecoVista_f'] > 0) &
        (produtos_oferta['PrecoCartao_f'] < produtos_oferta['PrecoVista_f'])
    ].sort_values(by='Nome').head(10)

    
    # ==================================================
    # 3. SEÇÃO MAIS VENDIDOS (Carrossel)
    # ==================================================
    st.markdown(f'<img src="{URL_MAIS_VENDIDOS}" class="section-header-img" alt="Mais Vendidos">', unsafe_allow_html=True)
    
    if produtos_mais_vendidos.empty:
        st.info("Não há dados de vendas suficientes (Entradas Realizadas) para determinar os produtos mais vendidos.")
    else:
        html_cards = []
        for i, row in produtos_mais_vendidos.iterrows():
            vendas_count = df_mais_vendidos_id[df_mais_vendidos_id["Produto_ID"] == str(row["ID"])]["Quantidade Total Vendida"].iloc[0] if not df_mais_vendidos_id.empty and not df_mais_vendidos_id[df_mais_vendidos_id["Produto_ID"] == str(row["ID"])].empty else 0
            nome_produto = row['Nome']
            descricao = row['Marca'] if row['Marca'] else row['Categoria']
            preco_cartao = to_float(row.get('PrecoCartao', 0))
            foto_url = row.get("FotoURL") if row.get("FotoURL") else f"https://placehold.co/150x150/F48FB1/880E4F?text={str(row.get('Nome','')).replace(' ', '+')}"
            card_html = f'''
                <div class="product-card">
                    <img src="{foto_url}" alt="{nome_produto}">
                    <p style="font-size: 0.9em; height: 40px; white-space: normal;">{nome_produto} - {descricao}</p>
                    <p style="margin: 5px 0 15px;">
                        <span class="price-promo">R$ {preco_cartao:,.2f}</span>
                    </p>
                    <button onclick="window.alert('Compra simulada: {nome_produto}')" class="buy-button">COMPRAR</button>
                    <p style="font-size: 0.7em; color: #888; margin-top: 5px;">Vendas: {int(vendas_count)}</p>
                </div>
            '''
            html_cards.append(card_html)
        st.markdown(f'''
            <div class="carousel-outer-container">
                <div class="product-wrapper">
                    {"".join(html_cards)}
                </div>
            </div>
        ''', unsafe_allow_html=True)

    st.markdown("---")

    # ==================================================
    # 4. SEÇÃO NOSSAS OFERTAS (Carrossel)
    # ==================================================
    st.markdown('<div class="offer-section">', unsafe_allow_html=True)
    st.markdown(f'<img src="{URL_OFERTAS}" class="section-header-img" alt="Nossas Ofertas">', unsafe_allow_html=True)

    if produtos_oferta.empty:
        st.info("Nenhum produto em promoção registrado no momento.")
    else:
        html_cards_ofertas = []
        for i, row in produtos_oferta.iterrows():
            nome_produto = row['Nome']
            descricao = row['Marca'] if row['Marca'] else row['Categoria']
            preco_vista_original = row['PrecoVista_f']
            preco_cartao_promo = row['PrecoCartao_f']
            desconto = 0.0
            try:
                desconto = 1 - (preco_cartao_promo / preco_vista_original) if preco_vista_original > 0 else 0
            except:
                desconto = 0.0
            desconto_percent = round(desconto * 100)
            foto_url = row.get("FotoURL") if row.get("FotoURL") else f"https://placehold.co/150x150/E91E63/FFFFFF?text={str(row.get('Nome','')).replace(' ', '+')}"
            card_html = f'''
                <div class="product-card" style="background-color: #FFF5F7;">
                    <img src="{foto_url}" alt="{nome_produto}">
                    <p style="font-size: 0.9em; height: 40px; white-space: normal;">{nome_produto} - {descricao}</p>
                    <p style="margin: 5px 0 0;">
                        <span class="price-original">R$ {preco_vista_original:,.2f}</span>
                        <span class="price-promo">R$ {preco_cartao_promo:,.2f}</span>
                    </p>
                    <p style="color: #E91E63; font-weight: bold; font-size: 0.8em; margin-top: 5px; margin-bottom: 10px;">{desconto_percent}% OFF</p>
                    <button onclick="window.alert('Compra simulada: {nome_produto}')" class="buy-button">COMPRAR</button>
                </div>
            '''
            html_cards_ofertas.append(card_html)
        st.markdown(f'''
            <div class="carousel-outer-container">
                <div class="product-wrapper">
                    {"".join(html_cards_ofertas)}
                </div>
            </div>
        ''', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)  # Fecha offer-section
    st.markdown("---")

    # ==================================================
    # 5. SEÇÃO NOSSAS NOVIDADES (Carrossel Automático)
    # ==================================================
    st.markdown(f'<h2>Nossas Novidades</h2>', unsafe_allow_html=True)

    # Seleciona os últimos 10 produtos cadastrados com estoque > 0
    produtos_novos = produtos_df[produtos_df['Quantidade'] > 0].sort_values(by='ID', ascending=False).head(10)

    if produtos_novos.empty:
        st.info("Não há produtos cadastrados no estoque para exibir como novidades.")
    else:
        html_cards_novidades = []
        for _, row in produtos_novos.iterrows():
            foto_url = row.get("FotoURL") if row.get("FotoURL") else f"https://placehold.co/400x400/FFC1E3/E91E63?text={row['Nome'].replace(' ', '+')}"
            preco_vista = to_float(row.get('PrecoVista', 0))
            preco_formatado = f"R$ {preco_vista:,.2f}" if preco_vista > 0 else "Preço não disponível"
            nome = row.get("Nome", "")
            marca = row.get("Marca", "")
            qtd = int(row.get("Quantidade", 0))

            card_html = f"""
            <div class="product-card">
                <p style="font-weight: bold; color: #E91E63; margin-bottom: 10px; font-size: 0.9em;">✨ Doce&Bella - Novidade</p>
                <img src="{foto_url}" alt="{nome}">
                <p style="font-weight: bold; margin-top: 10px; height: 30px; white-space: normal;">{nome} ({marca})</p>
                <p style="font-size: 0.9em;">✨ Estoque: {qtd}</p>
                <p style="font-weight: bold; color: #E91E63; margin-top: 5px;">💸 {preco_formatado}</p>
                
            </div>
            """
            html_cards_novidades.append(card_html)

        # Renderiza o carrossel
        st.markdown(f"""
            <div class="carousel-outer-container">
                <div class="product-wrapper">
                    {''.join(html_cards_novidades)}
               
            </div>
        """, unsafe_allow_html=True)


        
# ==============================================================================
# 2. PÁGINAS DE GESTÃO (LIVRO CAIXA, PRODUTOS, COMPRAS, PROMOÇÕES)
# ==============================================================================

def gestao_promocoes():
    """Página de gerenciamento de promoções."""
    
    # Inicializa ou carrega o estado de produtos e promoções
    produtos = inicializar_produtos()
    
    if "promocoes" not in st.session_state:
        st.session_state.promocoes = carregar_promocoes()
    
    promocoes_df = st.session_state.promocoes
    
    # Processa o DataFrame de promoções (normaliza datas e filtra expiradas)
    promocoes = norm_promocoes(promocoes_df.copy())
    
    # Recarrega as vendas para a lógica de produtos parados
    df_movimentacoes = carregar_livro_caixa()
    vendas = df_movimentacoes[df_movimentacoes["Tipo"] == "Entrada"].copy()
    
    # --- PRODUTOS COM VENDA (para análise de inatividade) ---
    vendas_list = []
    for index, row in vendas.iterrows():
        produtos_json = row["Produtos Vendidos"]
        if pd.notna(produtos_json) and produtos_json:
            try:
                # Tenta usar json.loads, mas usa ast.literal_eval como fallback
                try:
                    items = json.loads(produtos_json)
                except (json.JSONDecodeError, TypeError):
                    items = ast.literal_eval(produtos_json)
                
                # CORREÇÃO: Garante que 'items' é uma lista e itera com segurança
                if isinstance(items, list):
                    for item in items:
                         produto_id = str(item.get("Produto_ID"))
                         if produto_id and produto_id != "None":
                            vendas_list.append({
                                "Data": parse_date_yyyy_mm_dd(row["Data"]), 
                                "IDProduto": produto_id
                            })
            except Exception:
                continue
            
    # CORREÇÃO: Adiciona a verificação de lista vazia antes de criar o DataFrame e chamar dropna
    if vendas_list:
        vendas_flat = pd.DataFrame(vendas_list)
        # O dropna é seguro aqui porque a lista não está vazia e 'IDProduto' é garantido no for loop.
        vendas_flat = vendas_flat.dropna(subset=["IDProduto"])
    else:
        # Retorna um DataFrame vazio, mas com a coluna esperada, para evitar KeyErrors
        vendas_flat = pd.DataFrame(columns=["Data", "IDProduto"])
    

    st.header("🏷️ Promoções")

    # --- CADASTRAR ---
    with st.expander("➕ Cadastrar promoção", expanded=False):
        if produtos.empty:
            st.info("Cadastre produtos primeiro para criar promoções.")
        else:
            # Lista de produtos elegíveis (aqueles que não são variações, ou seja, PaiID é nulo)
            opcoes_prod = (produtos["ID"].astype(str) + " - " + produtos["Nome"]).tolist()
            opcoes_prod.insert(0, "")
            
            sel_prod = st.selectbox("Produto", opcoes_prod, key="promo_cad_produto")
            
            if sel_prod:
                pid = sel_prod.split(" - ")[0].strip()
                pnome = sel_prod.split(" - ", 1)[1].strip()

                col1, col2, col3 = st.columns([1, 1, 1])
                with col1:
                    desconto_str = st.text_input("Desconto (%)", value="0", key="promo_cad_desc")
                with col2:
                    data_ini = st.date_input("Início", value=date.today(), key="promo_cad_inicio")
                with col3:
                    data_fim = st.date_input("Término", value=date.today() + timedelta(days=7), key="promo_cad_fim")

                if st.button("Adicionar promoção", key="promo_btn_add"):
                    desconto = to_float(desconto_str)
                    if desconto < 0 or desconto > 100:
                        st.error("O desconto deve estar entre 0 e 100%.")
                    elif data_fim < data_ini:
                        st.error("A data de término deve ser maior ou igual à data de início.")
                    else:
                        novo = {
                            "ID": prox_id(promocoes_df, "ID"),
                            "IDProduto": str(pid),
                            "NomeProduto": pnome,
                            "Desconto": float(desconto),
                            "DataInicio": str(data_ini),
                            "DataFim": str(data_fim),
                        }
                        st.session_state.promocoes = pd.concat([promocoes_df, pd.DataFrame([novo])], ignore_index=True)
                        # Placeholder para save_csv_github (deve ser ajustado conforme a implementação real de persistência de promoções)
                        if True: # Simulação de salvamento bem-sucedido
                            carregar_promocoes.clear()
                            st.success("Promoção cadastrada!")
                            st.rerun()  # 🔑 atualização imediata

    # --- PRODUTOS PARADOS E PERTO DA VALIDADE ---
    st.markdown("---")
    st.subheader("💡 Sugestões de Promoção")
    
    # 1. Sugestão de Produtos Parados
    st.markdown("#### 📦 Produtos parados sem vendas")
    
    dias_sem_venda = st.number_input(
        "Considerar parados após quantos dias?",
        min_value=1, max_value=365, value=30, key="promo_dias_sem_venda"
    )

    if not vendas_flat.empty:
        # Garante que a coluna de data seja pd.Series de datetime para o max() funcionar
        vendas_flat["Data"] = pd.to_datetime(vendas_flat["Data"], errors="coerce")
        ultima_venda = vendas_flat.groupby("IDProduto")["Data"].max().reset_index()
        ultima_venda.columns = ["IDProduto", "UltimaVenda"]
    else:
        ultima_venda = pd.DataFrame(columns=["IDProduto", "UltimaVenda"])

    produtos_parados = produtos.merge(ultima_venda, left_on="ID", right_on="IDProduto", how="left")
    
    # CORREÇÃO: Converte UltimaVenda para datetime para comparação com Timestamp
    produtos_parados["UltimaVenda"] = pd.to_datetime(produtos_parados["UltimaVenda"], errors='coerce')
    
    # Cria o limite como Timestamp para comparação segura
    limite_dt = datetime.combine(date.today() - timedelta(days=int(dias_sem_venda)), datetime.min.time())

    # Filtra produtos com estoque e que a última venda foi antes do limite (ou nunca vendeu)
    produtos_parados_sugeridos = produtos_parados[
        (produtos_parados["Quantidade"] > 0) &
        # Compara a Série de Timestamps (UltimaVenda) com o Timestamp do limite_dt
        (produtos_parados["UltimaVenda"].isna() | (produtos_parados["UltimaVenda"] < limite_dt))
    ].copy()
    
    # Prepara para exibição (converte de volta para date)
    produtos_parados_sugeridos['UltimaVenda'] = produtos_parados_sugeridos['UltimaVenda'].dt.date.fillna(pd.NaT) 

    if produtos_parados_sugeridos.empty:
        st.info("Nenhum produto parado encontrado com estoque e fora de promoção.")
    else:
        st.dataframe(
            produtos_parados_sugeridos[["ID", "Nome", "Quantidade", "UltimaVenda"]].fillna({"UltimaVenda": "NUNCA VENDIDO"}), 
            use_container_width=True, hide_index=True
        )

        with st.expander("⚙️ Criar Promoção Automática para Parados"):
            desconto_auto = st.number_input(
                "Desconto sugerido (%)", min_value=1, max_value=100, value=20, key="promo_desc_auto"
            )
            dias_validade = st.number_input(
                "Duração da promoção (dias)", min_value=1, max_value=90, value=7, key="promo_dias_validade_auto"
            )

            if st.button("🔥 Criar promoção automática", key="promo_btn_auto"):
                for _, row in produtos_parados_sugeridos.iterrows():
                    novo = {
                        "ID": prox_id(st.session_state.promocoes, "ID"),
                        "IDProduto": str(row["ID"]),
                        "NomeProduto": row["Nome"],
                        "Desconto": float(desconto_auto),
                        "DataInicio": str(date.today()),
                        "DataFim": str(date.today() + timedelta(days=int(dias_validade))),
                    }
                    st.session_state.promocoes = pd.concat([st.session_state.promocoes, pd.DataFrame([novo])], ignore_index=True)

                if True: # Simulação de salvamento bem-sucedido
                    carregar_promocoes.clear()
                    st.success(f"Promoções criadas para {len(produtos_parados_sugeridos)} produtos parados!")
                    st.rerun()  # 🔑 atualização imediata

    st.markdown("---")
    
    # 2. Sugestão de Produtos Perto da Validade
    st.markdown("#### ⏳ Produtos Próximos da Validade")
    
    dias_validade_limite = st.number_input(
        "Considerar perto da validade (dias restantes)",
        min_value=1, max_value=365, value=60, key="promo_dias_validade_restante"
    )
    
    limite_validade = date.today() + timedelta(days=int(dias_validade_limite))

    # CRÍTICO: Produtos Validade é uma cópia. Garante que a coluna Validade seja um objeto datetime para a comparação.
    produtos_validade_sugeridos = produtos.copy()
    
    # Converte Validade de volta para datetime/Timestamp para comparação segura (se já não estiver assim)
    produtos_validade_sugeridos['Validade_dt'] = pd.to_datetime(produtos_validade_sugeridos['Validade'], errors='coerce')
    limite_validade_dt = datetime.combine(limite_validade, datetime.min.time()) # Timestamp do limite
    
    
    produtos_validade_sugeridos = produtos_validade_sugeridos[
        (produtos_validade_sugeridos["Quantidade"] > 0) &
        # Compara a Série de Timestamps (Validade_dt) com o Timestamp do limite_validade_dt
        (produtos_validade_sugeridos["Validade_dt"].notna()) &
        (produtos_validade_sugeridos["Validade_dt"] <= limite_validade_dt)
    ].copy()
    
    if produtos_validade_sugeridos.empty:
        st.info("Nenhum produto com estoque e próximo da validade encontrado.")
    else:
        # CORREÇÃO AQUI: Garante que a coluna Validade seja um objeto date (como foi inicializada)
        # e que a subtração só ocorra se não for nulo, usando um tratamento try/except mais robusto.
        def calcular_dias_restantes(x):
            if pd.notna(x) and isinstance(x, date):
                return (x - date.today()).days
            return float('inf')

        produtos_validade_sugeridos['Dias Restantes'] = produtos_validade_sugeridos['Validade'].apply(calcular_dias_restantes)
        
        st.dataframe(
            produtos_validade_sugeridos[["ID", "Nome", "Quantidade", "Validade", "Dias Restantes"]].sort_values("Dias Restantes"), 
            use_container_width=True, hide_index=True
        )

    st.markdown("---")
    
    # 2. Sugestão de Produtos Perto da Validade
    st.markdown("#### ⏳ Produtos Próximos da Validade")
    
    dias_validade_limite = st.number_input(
        "Considerar perto da validade (dias restantes)",
        min_value=1, max_value=365, value=60, key="promo_dias_validade_restante_2"
    )
    
    limite_validade = date.today() + timedelta(days=int(dias_validade_limite))
    
    produtos_validade_sugeridos = produtos.copy()
    
    produtos_validade_sugeridos['Validade_dt'] = pd.to_datetime(produtos_validade_sugeridos['Validade'], errors='coerce')
    limite_validade_dt = datetime.combine(limite_validade, datetime.min.time())
    
    
    produtos_validade_sugeridos = produtos_validade_sugeridos[
        (produtos_validade_sugeridos["Quantidade"] > 0) &
        (produtos_validade_sugeridos["Validade_dt"].notna()) &
        (produtos_validade_sugeridos["Validade_dt"] <= limite_validade_dt)
    ].copy()
    
    if produtos_validade_sugeridos.empty:
        st.info("Nenhum produto com estoque e próximo da validade encontrado.")
    else:
        # CORREÇÃO AQUI: Garante que a coluna Validade seja um objeto date (como foi inicializada)
        def calcular_dias_restantes(x):
            if pd.notna(x) and isinstance(x, date):
                return (x - date.today()).days
            return float('inf')

        produtos_validade_sugeridos['Dias Restantes'] = produtos_validade_sugeridos['Validade'].apply(calcular_dias_restantes)
        
        st.dataframe(
            produtos_validade_sugeridos[["ID", "Nome", "Quantidade", "Validade", "Dias Restantes"]].sort_values("Dias Restantes"), 
            use_container_width=True, hide_index=True
        )

    st.markdown("---")
    
    # --- LISTA DE PROMOÇÕES ATIVAS ---
    st.markdown("### 📋 Lista de Promoções Ativas")
    
    if promocoes.empty:
        st.info("Nenhuma promoção ativa cadastrada.")
    else:
        df_display = promocoes.copy()
        
        # Formata as colunas para exibição
        df_display["Desconto"] = df_display["Desconto"].apply(lambda x: f"{x:.0f}%")
        df_display["DataInicio"] = df_display["DataInicio"].apply(lambda x: x.strftime('%d/%m/%Y'))
        df_display["DataFim"] = df_display["DataFim"].apply(lambda x: x.strftime('%d/%m/%Y'))
        
        st.dataframe(
            df_display[["ID", "NomeProduto", "Desconto", "DataInicio", "DataFim"]], 
            use_container_width=True,
            column_config={
                "DataInicio": "Início",
                "DataFim": "Término",
                "NomeProduto": "Produto"
            }
        )

        # --- EDITAR E EXCLUIR ---
        st.markdown("#### Operações de Edição e Exclusão")
        
        opcoes_promo_operacao = {
            f"ID {row['ID']} | {row['NomeProduto']} | {row['Desconto']} | Fim: {row['DataFim']}": row['ID'] 
            for index, row in df_display.iterrows()
        }
        opcoes_keys = ["Selecione uma promoção..."] + list(opcoes_promo_operacao.keys())
        
        promo_selecionada_str = st.selectbox(
            "Selecione o item para Editar ou Excluir:",
            options=opcoes_keys,
            index=0, 
            key="select_promo_operacao_lc"
        )
        
        promo_id_selecionado = opcoes_promo_operacao.get(promo_selecionada_str)
        
        if promo_id_selecionado is not None:
            
            # Puxa a linha original (sem normalização de data para input)
            linha_original = promocoes_df[promocoes_df["ID"].astype(str) == promo_id_selecionado].iloc[0]
            
            with st.expander(f"✏️ Editar Promoção ID {promo_id_selecionado}", expanded=True):
                
                opcoes_prod_edit = (produtos["ID"].astype(str) + " - " + produtos["Nome"]).tolist()
                opcoes_prod_edit.insert(0, "")
                
                pre_opcao = (
                    f"{linha_original['IDProduto']} - {linha_original['NomeProduto']}"
                    if f"{linha_original['IDProduto']} - {linha_original['NomeProduto']}" in opcoes_prod_edit
                    else ""
                )
                
                sel_prod_edit = st.selectbox(
                    "Produto (editar)", opcoes_prod_edit,
                    index=opcoes_prod_edit.index(pre_opcao) if pre_opcao in opcoes_prod_edit else 0,
                    key=f"promo_edit_prod_{promo_id_selecionado}"
                )
                
                pid_e = sel_prod_edit.split(" - ")[0].strip()
                pnome_e = sel_prod_edit.split(" - ", 1)[1].strip() if len(sel_prod_edit.split(" - ", 1)) > 1 else linha_original['NomeProduto']

                col1, col2, col3 = st.columns([1, 1, 1])
                
                with col1:
                    desc_e = st.text_input("Desconto (%)", value=str(to_float(linha_original["Desconto"])), key=f"promo_edit_desc_{promo_id_selecionado}")
                
                with col2:
                    di = parse_date_yyyy_mm_dd(linha_original["DataInicio"]) or date.today()
                    data_ini_e = st.date_input("Início", value=di, key=f"promo_edit_inicio_{promo_id_selecionado}")
                
                with col3:
                    df_date = parse_date_yyyy_mm_dd(linha_original["DataFim"]) or (date.today() + timedelta(days=7))
                    data_fim_e = st.date_input("Término", value=df_date, key=f"promo_edit_fim_{promo_id_selecionado}")
                
                col_btn_edit, col_btn_delete = st.columns(2)
                
                with col_btn_edit:
                    if st.button("💾 Salvar Edição", key=f"promo_btn_edit_{promo_id_selecionado}", type="secondary", use_container_width=True):
                        dnum = to_float(desc_e)
                        if dnum < 0 or dnum > 100:
                            st.error("O desconto deve estar entre 0 e 100%.")
                        elif data_fim_e < data_ini_e:
                            st.error("A data de término deve ser maior ou igual à data de início.")
                        elif not pid_e:
                            st.error("Selecione um produto válido.")
                        else:
                            idx = promocoes_df["ID"].astype(str) == promo_id_selecionado
                            promocoes_df.loc[idx, ["IDProduto", "NomeProduto", "Desconto", "DataInicio", "DataFim"]] = [
                                str(pid_e), pnome_e, float(dnum), str(data_ini_e), str(data_fim_e)
                            ]
                            st.session_state.promocoes = promocoes_df
                            if True: # Simulação de salvamento bem-sucedido
                                carregar_promocoes.clear()
                                st.success("Promoção atualizada!")
                                st.rerun()  # 🔑 atualização imediata

                with col_btn_delete:
                    if st.button("🗑️ Excluir Promoção", key=f"promo_btn_del_{promo_id_selecionado}", type="primary", use_container_width=True):
                        st.session_state.promocoes = promocoes_df[promocoes_df["ID"].astype(str) != promo_id_selecionado]
                        if True: # Simulação de salvamento bem-sucedido
                            carregar_promocoes.clear()
                            st.warning(f"Promoção {promo_id_selecionado} excluída!")
                            st.rerun()  # 🔑 atualização imediata
        else:
            st.info("Selecione uma promoção para ver as opções de edição e exclusão.")


def gestao_produtos():
    
    # Inicializa ou carrega o estado de produtos
    produtos = inicializar_produtos()
    
    # Título da Página
    st.header("📦 Gestão de Produtos e Estoque") # Mantém o st.header para o título da seção

    # Lógica de Salvamento Automático para sincronizar alterações feitas pelo Livro Caixa
    save_data_github_produtos(produtos, ARQ_PRODUTOS, COMMIT_MESSAGE_PROD)


    # ================================
    # SUBABAS
    # ================================
    tab_cadastro, tab_lista = st.tabs(["📝 Cadastro de Produtos", "📑 Lista & Busca"])

    # ================================
    # SUBABA: CADASTRO
    # ================================
    with tab_cadastro:
        st.subheader("📝 Cadastro de Produtos")
        
        if 'codigo_barras' not in st.session_state:
            st.session_state["codigo_barras"] = ""
        if 'cb_grade_lidos' not in st.session_state:
            st.session_state.cb_grade_lidos = {}


        # --- Cadastro ---
        with st.expander("Cadastrar novo produto", expanded=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                tipo_produto = st.radio("Tipo de produto", ["Produto simples", "Produto com variações (grade)"], key="cad_tipo_produto")
                nome = st.text_input("Nome", key="cad_nome")
                marca = st.text_input("Marca", key="cad_marca")
                categoria = st.text_input("Categoria", key="cad_categoria")

            with c2:
                # Inicializa valores de produto simples para passar ao callback
                qtd = 0
                preco_custo = "0,00"
                preco_vista = "0,00"
                
                if tipo_produto == "Produto simples":
                    qtd = st.number_input("Quantidade", min_value=0, step=1, value=0, key="cad_qtd")
                    preco_custo = st.text_input("Preço de Custo", value="0,00", key="cad_preco_custo")
                    preco_vista = st.text_input("Preço à Vista", value="0,00", key="cad_preco_vista")
                    preco_cartao = 0.0
                    try:
                        preco_cartao = round(to_float(preco_vista) / FATOR_CARTAO, 2)
                    except Exception:
                        preco_cartao = 0.0
                    st.text_input("Preço no Cartão (auto)", value=str(preco_cartao).replace(".", ","), disabled=True, key="cad_preco_cartao")
                else:
                    st.info("Cadastre as variações abaixo (grade).")

            with c3:
                validade = st.date_input("Validade (opcional)", value=date.today(), key="cad_validade")
                foto_url = st.text_input("URL da Foto (opcional)", key="cad_foto_url")
                st.file_uploader("📷 Enviar Foto", type=["png", "jpg", "jpeg"], key="cad_foto") 
                
                # O campo de texto usa o valor do session_state (que é preenchido pela leitura)
                codigo_barras = st.text_input("Código de Barras (Pai/Simples)", value=st.session_state.get("codigo_barras", ""), key="cad_cb")

                # --- Escanear com câmera (Produto Simples/Pai) ---
                foto_codigo = st.camera_input("📷 Escanear código de barras / QR Code", key="cad_cam")
                if foto_codigo is not None:
                    imagem_bytes = foto_codigo.getbuffer() 
                    codigos_lidos = ler_codigo_barras_api(imagem_bytes)
                    if codigos_lidos:
                        # Preenche o valor no session_state e força o re-run
                        st.session_state["codigo_barras"] = codigos_lidos[0]
                        st.success(f"Código lido: **{st.session_state['codigo_barras']}**")
                        st.rerun() 
                    else:
                        st.error("❌ Não foi possível ler nenhum código.")

                # --- Upload de imagem do código de barras (Produto Simples/Pai) ---
                foto_codigo_upload = st.file_uploader("📤 Upload de imagem do código de barras", type=["png", "jpg", "jpeg"], key="cad_cb_upload")
                if foto_codigo_upload is not None:
                    imagem_bytes = foto_codigo_upload.getvalue() 
                    codigos_lidos = ler_codigo_barras_api(imagem_bytes)
                    if codigos_lidos:
                        # Preenche o valor no session_state e força o re-run
                        st.session_state["codigo_barras"] = codigos_lidos[0]
                        st.success(f"Código lido via upload: **{st.session_state['codigo_barras']}**")
                        st.rerun() 
                    else:
                        st.error("❌ Não foi possível ler nenhum código da imagem enviada.")

            # --- Cadastro da grade (variações) ---
            variações = []
            if tipo_produto == "Produto com variações (grade)":
                st.markdown("#### Cadastro das variações (grade)")
                qtd_variações = st.number_input("Quantas variações deseja cadastrar?", min_value=1, step=1, key="cad_qtd_variações")

                
                for i in range(int(qtd_variações)):
                    st.markdown(f"--- **Variação {i+1}** ---")
                    
                    var_c1, var_c2, var_c3, var_c4 = st.columns(4)
                    
                    var_nome = var_c1.text_input(f"Nome da variação {i+1}", key=f"var_nome_{i}")
                    var_qtd = var_c2.number_input(f"Quantidade variação {i+1}", min_value=0, step=1, value=0, key=f"var_qtd_{i}")
                    var_preco_custo = st.text_input(f"Preço de Custo variação {i+1}", value="0,00", key=f"var_pc_{i}")
                    var_preco_vista = st.text_input("Preço à Vista variação {i+1}", value="0,00", key=f"var_pv_{i}")
                    
                    var_cb_c1, var_cb_c2, var_cb_c3 = st.columns([2, 1, 1])

                    with var_cb_c1:
                        # O campo de texto da variação lê o valor salvo na sessão
                        valor_cb_inicial = st.session_state.cb_grade_lidos.get(f"var_cb_{i}", "")
                        var_codigo_barras = st.text_input(
                            f"Código de barras variação {i+1}", 
                            value=valor_cb_inicial, 
                            key=f"var_cb_{i}" 
                        )
                        
                    with var_cb_c2:
                        var_foto_upload = st.file_uploader(
                            "Upload CB", 
                            type=["png", "jpg", "jpeg"], 
                            key=f"var_cb_upload_{i}"
                        )
                    
                    with var_cb_c3:
                        var_foto_cam = st.camera_input(
                            "Escanear CB", 
                            key=f"var_cb_cam_{i}"
                        )
                    
                    # Logica de leitura do Código de Barras para a Variação
                    foto_lida = var_foto_upload or var_foto_cam
                    if foto_lida:
                        imagem_bytes = foto_lida.getvalue() if var_foto_upload else foto_lida.getbuffer()
                        codigos_lidos = ler_codigo_barras_api(imagem_bytes)
                        if codigos_lidos:
                            # Preenche o valor na sessão da grade e força o re-run
                            st.session_state.cb_grade_lidos[f"var_cb_{i}"] = codigos_lidos[0]
                            st.success(f"CB Variação {i+1} lido: **{codigos_lidos[0]}**")
                            st.rerun() 
                        else:
                            st.error("❌ Não foi possível ler nenhum código.")

                    variações.append({
                        "Nome": var_nome.strip(),
                        "Quantidade": int(var_qtd),
                        "PrecoCusto": to_float(var_preco_custo),
                        "PrecoVista": to_float(var_preco_vista),
                        "PrecoCartao": round(to_float(var_preco_vista) / FATOR_CARTAO, 2) if to_float(var_preco_vista) > 0 else 0.0,
                        "CodigoBarras": var_codigo_barras 
                    })
                
            # --- BOTÃO SALVAR PRODUTO (CHAMANDO CALLBACK) ---
            if st.button(
                "💾 Salvar", 
                use_container_width=True, 
                key="cad_salvar",
                on_click=lambda: st.rerun() if callback_salvar_novo_produto(produtos.copy(), tipo_produto, nome, marca, categoria, qtd, preco_custo, preco_vista, validade, foto_url, codigo_barras, variações) else None,
                help="Salvar Novo Produto Completo" 
            ):
                st.rerun()


    # ================================
    # SUBABA: LISTA & BUSCA
    # ================================
    with tab_lista:
        st.subheader("📑 Lista & Busca de Produtos")

        # --- Busca minimalista ---
        with st.expander("🔍 Pesquisar produto", expanded=True):
            criterio = st.selectbox(
                "Pesquisar por:",
                ["Nome", "Marca", "Código de Barras", "Valor"]
            )
            termo = st.text_input("Digite para buscar:")

            if termo:
                if criterio == "Nome":
                    produtos_filtrados = produtos[produtos["Nome"].astype(str).str.contains(termo, case=False, na=False)]
                elif criterio == "Marca":
                    produtos_filtrados = produtos[produtos["Marca"].astype(str).str.contains(termo, case=False, na=False)]
                elif criterio == "Código de Barras":
                    produtos_filtrados = produtos[produtos["CodigoBarras"].astype(str).str.contains(termo, case=False, na=False)]
                elif criterio == "Valor":
                    try:
                        valor = float(termo.replace(",", "."))
                        produtos_filtrados = produtos[
                            (produtos["PrecoVista"].astype(float) == valor) |
                            (produtos["PrecoCusto"].astype(float) == valor) |
                            (produtos["PrecoCartao"].astype(float) == valor)
                        ]
                    except:
                        st.warning("Digite um número válido para buscar por valor.")
                        produtos_filtrados = produtos.copy()
            else:
                # SE NENHUM TERMO FOR DIGITADO, EXIBE TODOS OS PRODUTOS
                produtos_filtrados = produtos.copy()

            if "PaiID" not in produtos_filtrados.columns:
                produtos_filtrados["PaiID"] = None

        # --- Lista de produtos com agrupamento por Pai e Variações ---
        st.markdown("### Lista de produtos")

        if produtos_filtrados.empty:
            st.info("Nenhum produto encontrado.")
        else:
            produtos_filtrados["Quantidade"] = pd.to_numeric(produtos_filtrados["Quantidade"], errors='coerce').fillna(0).astype(int)
            
            # CORREÇÃO CRÍTICA: Filtra apenas os produtos que NÃO são variações (PaiID é nulo ou vazio/NaN)
            # Produtos que têm PaiID preenchido são listados *dentro* do expander do produto Pai.
            produtos_pai = produtos_filtrados[produtos_filtrados["PaiID"].isnull() | (produtos_filtrados["PaiID"] == '')]
            produtos_filho = produtos_filtrados[produtos_filtrados["PaiID"].notnull() & (produtos_filtrados["PaiID"] != '')]
            
            st.markdown("""
                <style>
                .custom-header, .custom-row {
                    display: grid;
                    grid-template-columns: 80px 3fr 1fr 1fr 1.5fr 0.5fr 0.5fr;
                    align-items: center;
                    gap: 5px;
                }
                .custom-header {
                    font-weight: bold;
                    padding: 8px 0;
                    border-bottom: 1px solid #ccc;
                    margin-bottom: 5px;
                }
                .custom-price-block {
                    line-height: 1.2;
                }
                .stButton > button {
                    height: 32px;
                    width: 32px;
                    padding: 0;
                    margin: 0;
                    border-radius: 5px;
                    border: 1px solid #ddd;
                    background-color: #f0f2f6;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                }
                .stButton > button:hover {
                    background-color: #e0e0e0;
                }
                </style>
                <div class="custom-header">
                    <div>Foto</div>
                    <div>Produto & Marca</div>
                    <div>Estoque</div>
                    <div>Validade</div>
                    <div>Preços (C/V/C)</div>
                    <div style="grid-column: span 2;">Ações</div>
                </div>
            """, unsafe_allow_html=True)


            for index, pai in produtos_pai.iterrows():
                # A partir daqui, a lógica de listagem funciona como o esperado, usando apenas os "produtos_pai" (que incluem produtos simples).
                with st.container(border=True):
                    c = st.columns([1, 3, 1, 1, 1.5, 0.5, 0.5]) 
                    
                    if str(pai["FotoURL"]).strip():
                        try:
                            c[0].image(pai["FotoURL"], width=60)
                        except Exception:
                            c[0].write("—")
                    else:
                        c[0].write("—")

                    cb = f' • CB: {pai["CodigoBarras"]}' if str(pai.get("CodigoBarras", "")).strip() else ""
                    c[1].markdown(f"**{pai['Nome']}**<br><small>Marca: {pai['Marca']} | Cat: {pai['Categoria']}</small>", unsafe_allow_html=True)
                    
                    estoque_total = pai['Quantidade']
                    filhos_do_pai = produtos_filho[produtos_filho["PaiID"] == str(pai["ID"])]
                    if not filhos_do_pai.empty:
                        # Se houver filhos, o estoque total é a soma dos filhos.
                        estoque_total = filhos_do_pai['Quantidade'].sum()
                    
                    c[2].markdown(f"**{estoque_total}**")
                    
                    c[3].write(f"{pai['Validade']}")
                    
                    pv = to_float(pai['PrecoVista'])
                    pc_calc = round(pv / FATOR_CARTAO, 2)
                    
                    preco_html = (
                        f'<div class="custom-price-block">'
                        f'<small>C: R$ {to_float(pai['PrecoCusto']):,.2f}</small><br>'
                        f'**V:** R$ {pv:,.2f}<br>'
                        f'**C:** R$ {pc_calc:,.2f}'
                        f'</div>'
                    )
                    c[4].markdown(preco_html, unsafe_allow_html=True)
                    
                    try:
                        eid = str(pai["ID"])
                    except Exception:
                        eid = str(index)

                    if c[5].button("✏️", key=f"edit_pai_{index}_{eid}", help="Editar produto"):
                        st.session_state["edit_prod"] = eid
                        st.rerun()

                    if c[6].button("🗑️", key=f"del_pai_{index}_{eid}", help="Excluir produto"):
                        produtos = produtos[produtos["ID"] != eid]
                        produtos = produtos[produtos["PaiID"] != eid]
                        st.session_state["produtos"] = produtos
                        
                        nome_pai = str(pai.get('Nome', 'Produto Desconhecido'))
                        if salvar_produtos_no_github(produtos, f"Exclusão do produto pai {nome_pai}"):
                            inicializar_produtos.clear() 
                        st.rerun()
                        
                    if not filhos_do_pai.empty:
                        with st.expander(f"Variações de {pai['Nome']} ({len(filhos_do_pai)} variações)"):
                            for index_var, var in filhos_do_pai.iterrows():
                                c_var = st.columns([1, 3, 1, 1, 1.5, 0.5, 0.5]) 
                                
                                foto_url_var = str(var["FotoURL"]).strip() or str(pai["FotoURL"]).strip()
                                if foto_url_var:
                                    try:
                                        c_var[0].image(foto_url_var, width=60)
                                    except Exception:
                                        c_var[0].write("—")
                                else:
                                    c_var[0].write("—")

                                cb_var = f' • CB: {var["CodigoBarras"]}' if str(var.get("CodigoBarras", "")).strip() else ""
                                c_var[1].markdown(f"**{var['Nome']}**<br><small>Marca: {var['Marca']} | Cat: {var['Categoria']}</small>", unsafe_allow_html=True)
                                
                                c_var[2].write(f"{var['Quantidade']}")
                                
                                c_var[3].write(f"{pai['Validade']}")

                                pv_var = to_float(var['PrecoVista'])
                                pc_var_calc = round(pv_var / FATOR_CARTAO, 2)
                                
                                preco_var_html = (
                                    f'<div class="custom-price-block">'
                                    f'<small>C: R$ {to_float(var['PrecoCusto']):,.2f}</small><br>'
                                    f'**V:** R$ {pv_var:,.2f}<br>'
                                    f'**C:** R$ {pc_var_calc:,.2f}'
                                    f'</div>'
                                )
                                c_var[4].markdown(preco_var_html, unsafe_allow_html=True)
                                
                                try:
                                    eid_var = str(var["ID"])
                                except Exception:
                                    eid_var = str(index_var)

                                if c_var[5].button("✏️", key=f"edit_filho_{index_var}_{eid_var}", help="Editar variação"):
                                    st.session_state["edit_prod"] = eid_var
                                    st.rerun()

                                if c_var[6].button("🗑️", key=f"del_filho_{index_var}_{eid_var}", help="Excluir variação"):
                                    products = produtos[produtos["ID"] != eid_var]
                                    st.session_state["produtos"] = products
                                    
                                    nome_var = str(var.get('Nome', 'Variação Desconhecida'))
                                    if salvar_produtos_no_github(products, f"Exclusão da variação {nome_var}"):
                                        inicializar_produtos.clear() 
                                    st.rerun()

            if "edit_prod" in st.session_state:
                eid = st.session_state["edit_prod"]
                row = produtos[produtos["ID"] == str(eid)]
                if not row.empty:
                    st.subheader(f"Editar produto ID: {eid} ({row.iloc[0]['Nome']})")
                    row = row.iloc[0]
                    
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        novo_nome = st.text_input("Nome", value=row["Nome"], key=f"edit_nome_{eid}")
                        nova_marca = st.text_input("Marca", value=row["Marca"], key=f"edit_marca_{eid}")
                        nova_cat = st.text_input("Categoria", value=row["Categoria"], key=f"edit_cat_{eid}")
                    with c2:
                        qtd_value = int(row["Quantidade"]) if pd.notna(row["Quantidade"]) else 0
                        nova_qtd = st.number_input("Quantidade", min_value=0, step=1, value=qtd_value, key=f"edit_qtd_{eid}")
                        novo_preco_custo = st.text_input("Preço de Custo", value=f"{to_float(row["PrecoCusto"]):.2f}".replace(".", ","), key=f"edit_pc_{eid}")
                        novo_preco_vista = st.text_input("Preço à Vista", value=f"{to_float(row["PrecoVista"]):.2f}".replace(".", ","), key=f"edit_pv_{eid}")
                    with c3:
                        try:
                            # Tenta garantir que a validade seja um objeto date para o input
                            vdata = row["Validade"] if pd.notna(row["Validade"]) and isinstance(row["Validade"], date) else date.today()
                        except Exception:
                            vdata = date.today()
                        nova_validade = st.date_input("Validade", value=vdata, key=f"edit_val_{eid}")
                        nova_foto = st.text_input("URL da Foto", value=row["FotoURL"], key=f"edit_foto_{eid}")
                        novo_cb = st.text_input("Código de Barras", value=str(row.get("CodigoBarras", "")), key=f"edit_cb_{eid}")

                        foto_codigo_edit = st.camera_input("📷 Atualizar código de barras", key=f"edit_cam_{eid}")
                        if foto_codigo_edit is not None:
                            codigo_lido = ler_codigo_barras_api(foto_codigo_edit.getbuffer()) 
                            if codigo_lido:
                                novo_cb = codigo_lido[0]
                                st.success(f"Código lido: **{novo_cb}**")

                    col_empty_left, col_save, col_cancel = st.columns([3, 1.5, 1.5]) 
                    
                    with col_save:
                        if st.button("💾 Salvar", key=f"save_{eid}", type="primary", use_container_width=True, help="Salvar Alterações"):
                            preco_vista_float = to_float(novo_preco_vista)
                            novo_preco_cartao = round(preco_vista_float / FATOR_CARTAO, 2) if preco_vista_float > 0 else 0.0
                            
                            produtos.loc[produtos["ID"] == str(eid), [
                                "Nome", "Marca", "Categoria", "Quantidade",
                                "PrecoCusto", "PrecoVista", "PrecoCartao",
                                "Validade", "FotoURL", "CodigoBarras"
                            ]] = [
                                novo_nome.strip(),
                                nova_marca.strip(),
                                nova_cat.strip(),
                                int(nova_qtd),
                                to_float(novo_preco_custo),
                                preco_vista_float,
                                novo_preco_cartao,
                                nova_validade, # Já é um objeto date
                                nova_foto.strip(),
                                str(novo_cb).strip()
                            ]
                            st.session_state["produtos"] = produtos
                            if salvar_produtos_no_github(produtos, "Atualizando produto"):
                                inicializar_produtos.clear()
                                
                            del st.session_state["edit_prod"]
                            st.rerun()
                            
                    with col_cancel:
                        if st.button("❌ Cancelar", key=f"cancel_{eid}", use_container_width=True, help="Cancelar Edição"):
                            del st.session_state["edit_prod"]
                            st.rerun()


def historico_compras():
    
    st.header("🛒 Histórico de Compras de Insumos")
    st.info("Utilize esta página para registrar produtos (insumos, materiais, estoque) comprados. Estes dados são **separados** do controle de estoque principal e do Livro Caixa.")

    if "df_compras" not in st.session_state:
        st.session_state.df_compras = carregar_historico_compras()

    df_compras = st.session_state.df_compras.copy()
    
    if not df_compras.empty:
        df_compras['Data'] = pd.to_datetime(df_compras['Data'], errors='coerce').dt.date
        df_compras['Quantidade'] = pd.to_numeric(df_compras['Quantidade'], errors='coerce').fillna(0).astype(int)
        df_compras['Valor Total'] = pd.to_numeric(df_compras['Valor Total'], errors='coerce').fillna(0.0)
        
    df_exibicao = df_compras.sort_values(by='Data', ascending=False).reset_index(drop=False)
    df_exibicao.rename(columns={'index': 'original_index'}, inplace=True)
    df_exibicao.insert(0, 'ID', df_exibicao.index + 1)
    
    hoje = date.today()
    primeiro_dia_mes = hoje.replace(day=1)
    if hoje.month == 12:
        proximo_mes = hoje.replace(year=hoje.year + 1, month=1, day=1)
    else:
        proximo_mes = hoje.replace(month=hoje.month + 1, day=1)
    ultimo_dia_mes = proximo_mes - timedelta(days=1)
    
    df_mes_atual = df_exibicao[
        (df_exibicao["Data"].apply(lambda x: pd.notna(x) and x >= primeiro_dia_mes and x <= ultimo_dia_mes)) &
        (df_exibicao["Valor Total"] > 0)
    ].copy()

    total_gasto_mes = df_mes_atual['Valor Total'].sum() 

    st.markdown("---")
    st.subheader(f"📊 Resumo de Gastos - Mês de {primeiro_dia_mes.strftime('%m/%Y')}")
    st.metric(
        label="💰 Total Gasto com Compras de Insumos (Mês Atual)",
        value=f"R$ {total_gasto_mes:,.2f}"
    )
    st.markdown("---")
    
    tab_cadastro, tab_dashboard = st.tabs(["📝 Cadastro & Lista de Compras", "📈 Dashboard de Gastos"])
    
    with tab_dashboard:
        st.header("📈 Análise de Gastos com Compras")
        
        if df_exibicao.empty:
            st.info("Nenhum dado de compra registrado para gerar o dashboard.")
        else:
            df_gasto_por_produto = df_exibicao.groupby('Produto')['Valor Total'].sum().reset_index()
            df_gasto_por_produto = df_gasto_por_produto.sort_values(by='Valor Total', ascending=False)
            
            st.markdown("### 🥇 Top Produtos Mais Gastos (Valor Total)")
            
            if not df_gasto_por_produto.empty:
                top_n = st.slider("Mostrar Top N Produtos", min_value=5, max_value=20, value=10)
                top_produtos = df_gasto_por_produto.head(top_n)

                fig_top_produtos = px.bar(
                    top_produtos,
                    x='Produto',
                    y='Valor Total',
                    text='Valor Total',
                    title=f'Top {top_n} Produtos por Gasto Total',
                    labels={'Valor Total': 'Gasto Total (R$)', 'Produto': 'Produto'},
                    color='Valor Total',
                    color_continuous_scale=px.colors.sequential.Sunset
                )
                fig_top_produtos.update_traces(texttemplate='R$ %{y:,.2f}', textposition='outside')
                fig_top_produtos.update_layout(xaxis={'categoryorder':'total descending'}, height=500)
                st.plotly_chart(fig_top_produtos, use_container_width=True)

                st.markdown("---")
                st.markdown("### 📅 Gasto Mensal Histórico (Agregado)")
                
                df_temp_data = df_exibicao[df_exibicao['Data'].notna()].copy()
                df_temp_data['Data_dt'] = pd.to_datetime(df_temp_data['Data'])
                df_temp_data['MesAno'] = df_temp_data['Data_dt'].dt.strftime('%Y-%m')
                
                df_gasto_mensal = df_temp_data.groupby('MesAno')['Valor Total'].sum().reset_index()
                df_gasto_mensal = df_gasto_mensal.sort_values(by='MesAno')

                fig_mensal = px.line(
                    df_gasto_mensal,
                    x='MesAno',
                    y='Valor Total',
                    title='Evolução do Gasto Mensal com Compras',
                    labels={'Valor Total': 'Gasto (R$)', 'MesAno': 'Mês/Ano'},
                    markers=True
                )
                st.plotly_chart(fig_mensal, use_container_width=True)
    
    with tab_cadastro:
        
        edit_mode_compra = st.session_state.get('edit_compra_idx') is not None
        
        if edit_mode_compra:
            original_idx_to_edit = st.session_state.edit_compra_idx
            linha_para_editar = df_compras[df_compras.index == original_idx_to_edit]
            
            if not linha_para_editar.empty:
                compra_data = linha_para_editar.iloc[0]
                try: default_data = pd.to_datetime(compra_data['Data']).date()
                except: default_data = date.today()
                    
                default_produto = compra_data['Produto']
                default_qtd = int(compra_data['Quantidade'])
                valor_total_compra = float(compra_data['Valor Total'])
                default_qtd_float = float(default_qtd)
                valor_unitario_existente = valor_total_compra / default_qtd_float if default_qtd_float > 0 else valor_total_compra
                default_valor = float(valor_unitario_existente)
                
                default_cor = compra_data['Cor']
                default_foto_url = compra_data['FotoURL']
                
                st.subheader("📝 Editar Compra Selecionada")
                st.warning(f"Editando item: **{default_produto}** (ID Interno: {original_idx_to_edit})")
            else:
                st.session_state.edit_compra_idx = None
                edit_mode_compra = False
                st.subheader("📝 Formulário de Registro")
                
        if not edit_mode_compra:
            st.subheader("📝 Formulário de Registro")
            default_data = date.today()
            default_produto = ""
            default_qtd = 1
            default_valor = 10.00
            default_cor = "#007bff"
            default_foto_url = ""


        with st.form("form_compra", clear_on_submit=not edit_mode_compra):
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                data = st.date_input("Data da Compra", value=default_data, key="compra_data_form")
                nome_produto = st.text_input("Produto/Material Comprado", value=default_produto, key="compra_nome_form")
                
            with col2:
                quantidade = st.number_input("Quantidade", min_value=1, value=default_qtd, step=1, key="compra_qtd_form")
                valor_unitario_input = st.number_input("Preço Unitário (R$)", min_value=0.01, format="%.2f", value=default_valor, key="compra_valor_form")
                
            with col3:
                cor_selecionada = st.color_picker("Cor para Destaque", value=default_cor, key="compra_cor_form")
            
            with col4:
                foto_url = st.text_input("URL da Foto do Produto (Opcional)", value=default_foto_url, key="compra_foto_url_form")
            
            valor_total_calculado = float(quantidade) * float(valor_unitario_input)
            st.markdown(f"**Custo Total Calculado:** R$ {valor_total_calculado:,.2f}")
            
            
            if edit_mode_compra:
                col_sub1, col_sub2 = st.columns(2)
                salvar_compra = col_sub1.form_submit_button("💾 Salvar Edição", type="primary", use_container_width=True)
                cancelar_edicao = col_sub2.form_submit_button("❌ Cancelar Edição", type="secondary", use_container_width=True)
            else:
                salvar_compra = st.form_submit_button("💾 Adicionar Compra", type="primary", use_container_width=True)
                cancelar_edicao = False


            if salvar_compra:
                if not nome_produto or valor_total_calculado <= 0 or quantidade <= 0:
                    st.error("Preencha todos os campos obrigatórios com valores válidos. O Custo Total deve ser maior que R$ 0,00.")
                else:
                    nova_linha = {
                        "Data": data.strftime('%Y-%m-%d'),
                        "Produto": nome_produto.strip(),
                        "Quantidade": int(quantidade),
                        "Valor Total": valor_total_calculado, 
                        "Cor": cor_selecionada,
                        "FotoURL": foto_url.strip(),
                    }
                    
                    if edit_mode_compra:
                        st.session_state.df_compras.loc[original_idx_to_edit] = pd.Series(nova_linha)
                        commit_msg = f"Edição da compra {nome_produto}"
                    else:
                        df_original = st.session_state.df_compras.iloc[:, :len(COLUNAS_COMPRAS)]
                        st.session_state.df_compras = pd.concat([df_original, pd.DataFrame([nova_linha])], ignore_index=True)
                        commit_msg = f"Nova compra registrada: {nome_produto}"

                    if salvar_historico_no_github(st.session_state.df_compras, commit_msg):
                        st.session_state.edit_compra_idx = None
                        st.cache_data.clear()
                        st.rerun()

            if cancelar_edicao:
                st.session_state.edit_compra_idx = None
                st.rerun()
        
        st.markdown("---")
        st.subheader("Lista e Operações de Histórico")
        
        with st.expander("🔍 Filtros da Lista", expanded=False):
            col_f1, col_f2 = st.columns([1, 2])
            
            with col_f1:
                filtro_produto = st.text_input("Filtrar por nome do Produto:", key="filtro_compra_produto_tab")
            
            with col_f2:
                data_range_option = st.radio(
                    "Filtrar por Período:",
                    ["Todo o Histórico", "Personalizar Data"],
                    key="filtro_compra_data_opt_tab",
                    horizontal=True
                )

            df_filtrado = df_exibicao.copy()

            if filtro_produto:
                df_filtrado = df_filtrado[df_filtrado["Produto"].astype(str).str.contains(filtro_produto, case=False, na=False)]

            if data_range_option == "Personalizar Data":
                if not df_filtrado.empty:
                    min_date_val = df_filtrado['Data'].min() if pd.notna(df_filtrado['Data'].min()) else date.today()
                    max_date_val = df_filtrado['Data'].max() if pd.notna(df_filtrado['Data'].max()) else date.today()
                else:
                    min_date_val = date.today()
                    max_date_val = date.today()
                    
                col_date1, col_date2 = st.columns(2)
                with col_date1:
                    data_ini = st.date_input("De:", value=min_date_val, key="filtro_compra_data_ini_tab")
                with col_date2:
                    data_fim = st.date_input("Até:", value=max_date_val, key="filtro_compra_data_fim_tab")
                    
                df_filtrado = df_filtrado[
                    (df_filtrado["Data"] >= data_ini) &
                    (df_filtrado["Data"] <= data_fim)
                ]
            
        if df_filtrado.empty:
            st.info("Nenhuma compra encontrada com os filtros aplicados.")
        else:
            df_filtrado['Data Formatada'] = df_filtrado['Data'].apply(lambda x: x.strftime('%d/%m/%Y') if pd.notna(x) else '')
            
            def highlight_color_compras(row):
                color = row['Cor']
                return [f'background-color: {color}30' for col in row.index]
            
            df_para_mostrar = df_filtrado.copy()
            df_para_mostrar['Foto'] = df_para_mostrar['FotoURL'].fillna('').astype(str).apply(lambda x: '📷' if x.strip() else '')

            df_display_cols = ['ID', 'Data Formatada', 'Produto', 'Quantidade', 'Valor Total', 'Foto', 'Cor', 'original_index']
            df_styling = df_para_mostrar[df_display_cols].copy()
            
            styled_df = df_styling.style.apply(highlight_color_compras, axis=1)
            styled_df = styled_df.hide(subset=['Cor', 'original_index'], axis=1)

            st.markdown("##### Tabela de Itens Comprados")
            st.dataframe(
                styled_df,
                use_container_width=True,
                column_config={
                    "Data Formatada": st.column_config.TextColumn("Data da Compra"),
                    "Valor Total": st.column_config.NumberColumn("Valor Total (R$)", format="R$ %.2f"),
                    "Foto": st.column_config.TextColumn("Foto"),
                },
                column_order=('ID', 'Data Formatada', 'Produto', 'Quantidade', 'Valor Total', 'Foto'),
                height=400,
                selection_mode='disabled', 
                key='compras_table_styled'
            )
            
            
            st.markdown("### Operações de Edição e Exclusão")
            
            opcoes_compra_operacao = {
                f"ID {row['ID']} | {row['Data Formatada']} | {row['Produto']} | R$ {row['Valor Total']:,.2f}": row['original_index'] 
                for index, row in df_para_mostrar.iterrows()
            }
            opcoes_keys = list(opcoes_compra_operacao.keys())
            
            compra_selecionada_str = st.selectbox(
                "Selecione o item para Editar ou Excluir:",
                options=opcoes_keys,
                index=0 if not edit_mode_compra else (opcoes_keys.index(
                    next((k for k, v in opcoes_compra_operacao.items() if v == st.session_state.edit_compra_idx), opcoes_keys[0])
                ) if opcoes_keys else 0),
                key="select_compra_operacao_lc"
            )
            
            compra_original_idx = opcoes_compra_operacao.get(compra_selecionada_str)
            
            if compra_original_idx is not None:
                col_btn_edit, col_btn_delete = st.columns(2)
                
                with col_btn_edit:
                    if st.button("✏️ Editar Selecionado", key="btn_edit_compra", type="secondary", use_container_width=True):
                        st.session_state.edit_compra_idx = compra_original_idx
                        st.rerun()

                with col_btn_delete:
                    if st.button("🗑️ Excluir Compra", key="btn_del_compra", type="primary", use_container_width=True):
                        
                        df_para_excluir = st.session_state.df_compras.drop(index=compra_original_idx)
                        
                        if salvar_historico_no_github(df_para_excluir, f"Exclusão da compra ID Interno {compra_original_idx}"):
                            st.session_state.df_compras = df_para_excluir.reset_index(drop=True)
                            st.cache_data.clear()
                            st.success("✅ Compra excluída com sucesso!")
                            st.rerun()
        else:
            st.info("Selecione uma compra para ver as opções de edição e exclusão.")


def livro_caixa():
    """Página principal de Gestão Financeira (Livro Caixa)."""
    st.header("💸 Livro Caixa: Entradas e Saídas")
    st.warning("Implementação do Livro Caixa (Gestão Financeira) omitida na versão atual para focar no módulo de Precificação.")
    # Aqui deveria estar toda a lógica de Entradas/Saídas/Dashboard financeiro.
    pass

# ==============================================================================
# ROTEAMENTO FINAL
# ==============================================================================

if 'main_page_select' not in st.session_state:
    st.session_state.main_page_select = "Home"

# Define a lista de páginas principais
MAIN_PAGES = [
    "Home", 
    "Gestão Financeira (Livro Caixa)", 
    "Gestão de Produtos (Estoque)", 
    "Promoções", 
    "Histórico de Compras", 
    "Precificação" # Novo módulo
]

# Roteamento principal na sidebar
pagina = st.sidebar.radio(
    "Escolha a página:",
    MAIN_PAGES,
    key='main_page_select_widget'
)

# Chama a função da página selecionada
if pagina == "Home":
    homepage()
elif pagina == "Gestão Financeira (Livro Caixa)":
    livro_caixa() # Chama a função (atualmente mockada para avisar o usuário)
elif pagina == "Gestão de Produtos (Estoque)":
    gestao_produtos()
elif pagina == "Promoções":
    gestao_promocoes()
elif pagina == "Histórico de Compras":
    historico_compras()
elif pagina == "Precificação":
    precificacao_geral() # Chama o roteador interno para Geral e Papelaria
