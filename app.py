# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
import requests
from requests.exceptions import ConnectionError, RequestException 
from io import StringIO
import io, os
import json
import hashlib
import ast
import plotly.express as px
import base64
import calendar 

# ==============================================================================
# CONFIGURAÇÃO GERAL E INÍCIO DO APP (Mantido)
# ==============================================================================

st.set_page_config(
    layout="wide", 
    page_title="Doce&Bella | Gestão Financeira", 
    page_icon="🌸"
)

LOGO_DOCEBELLA_URL = "https://i.ibb.co/cdqJ92W/logo_docebella.png"
URL_MAIS_VENDIDOS = "https://d1a9qnv764bsoo.cloudfront.net/stores/002/838/949/rte/mid-queridinhos1.png"
URL_OFERTAS = "https://d1a9qnv764bsoo.cloudfront.net/stores/002/838/949/rte/mid-oferta.png"   
URL_NOVIDADES = "https://d1a9qnv764bsoo.cloudfront.net/stores/002/838/949/rte/mid-novidades.png"

st.markdown("""
    <style>
    /* Estilos CSS (sem alterações) */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stApp { background-color: #f7f7f7; }
    div.header-container { padding: 10px 0; background-color: #E91E63; color: white; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); display: flex; justify-content: space-between; align-items: center; width: 100%; }
    .nav-button-group { display: flex; gap: 20px; align-items: center; padding-right: 20px; }
    [data-testid="stSidebar"] { width: 350px; }
    .homepage-title { color: #E91E63; font-size: 3em; font-weight: 700; text-shadow: 2px 2px #fbcfe8; }
    .homepage-subtitle { color: #880E4F; font-size: 1.5em; margin-top: -10px; margin-bottom: 20px; }
    .insta-card { background-color: white; border-radius: 15px; overflow: hidden; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1); padding: 15px; height: 100%; display: flex; flex-direction: column; justify-content: space-between; }
    .insta-header { display: flex; align-items: center; font-weight: bold; color: #E91E63; margin-bottom: 10px; }
    .product-card { background-color: white; border-radius: 10px; padding: 15px; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08); text-align: center; height: 100%; width: 250px; flex-shrink: 0; margin-right: 15px; display: flex; flex-direction: column; justify-content: space-between; transition: transform 0.2s; }
    .product-card:hover { transform: translateY(-5px); }
    .product-card img { height: 150px; object-fit: contain; margin: 0 auto 10px; border-radius: 5px; }
    .price-original { color: #888; text-decoration: line-through; font-size: 0.85em; margin-right: 5px; }
    .price-promo { color: #E91E63; font-weight: bold; font-size: 1.2em; }
    .buy-button { background-color: #E91E63; color: white; font-weight: bold; border-radius: 20px; border: none; padding: 8px 15px; cursor: pointer; width: 100%; margin-top: 10px; }
    .offer-section { background-color: #F8BBD0; padding: 40px 20px; border-radius: 15px; margin-top: 40px; text-align: center; }
    .offer-title { color: #E91E63; font-size: 2.5em; font-weight: 700; margin-bottom: 20px; }
    .megaphone-icon { color: #E91E63; font-size: 3em; margin-bottom: 10px; display: inline-block; }
    .carousel-outer-container { width: 100%; overflow-x: auto; padding-bottom: 20px; }
    .product-wrapper { display: flex; flex-direction: row; justify-content: flex-start; gap: 15px; padding: 0 50px; min-width: fit-content; margin: 0 auto; }
    .section-header-img { max-width: 400px; height: auto; display: block; margin: 0 auto 10px; }
    </style>
""", unsafe_allow_html=True)

# --- Funções e Constantes de Persistência ---

try:
    from github import Github
except ImportError:
    class Github:
        def __init__(self, token): pass
        def get_repo(self, repo_name): return self
        def update_file(self, path, msg, content, sha, branch): pass
        def create_file(self, path, msg, content, branch): pass

def ler_codigo_barras_api(image_bytes):
    URL_DECODER_ZXING = "https://zxing.org/w/decode"
    try:
        files = {"f": ("barcode.png", image_bytes, "image/png")}
        response = requests.post(URL_DECODER_ZXING, files=files, timeout=30)
        if response.status_code != 200:
            if 'streamlit' in globals(): st.error(f"❌ Erro na API ZXing. Status HTTP: {response.status_code}")
            return []
        text = response.text
        codigos = []
        if "<pre>" in text:
            partes = text.split("<pre>")
            for p in partes[1:]:
                codigo = p.split("</pre>")[0].strip()
                if codigo and not codigo.startswith("Erro na decodificação"): codigos.append(codigo)
        if not codigos and 'streamlit' in globals():
            st.toast("⚠️ API ZXing não retornou nenhum código válido.")
        return codigos
    except (ConnectionError, RequestException) as e:
        if 'streamlit' in globals(): st.error(f"❌ Erro de Conexão/Requisição: {e}")
        return []
    except Exception as e:
        if 'streamlit' in globals(): st.error(f"❌ Erro inesperado: {e}")
        return []

def add_months(d: date, months: int) -> date:
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
except KeyError:
    TOKEN, OWNER, REPO_NAME, CSV_PATH, BRANCH = "TOKEN_FICTICIO", "user", "repo_default", "contas_a_pagar_receber.csv", "main"

GITHUB_TOKEN = TOKEN
GITHUB_REPO = f"{OWNER}/{REPO_NAME}"
GITHUB_BRANCH = BRANCH

# Caminhos dos arquivos
ARQ_CLIENTES = "clientes.csv" # NOVO ARQUIVO DE CLIENTES
ARQ_PRODUTOS = "produtos_estoque.csv"
ARQ_LOCAL = "livro_caixa.csv"
PATH_DIVIDAS = CSV_PATH
ARQ_COMPRAS = "historico_compras.csv"
ARQ_PROMOCOES = "promocoes.csv" 
COLUNAS_COMPRAS = ["Data", "Produto", "Quantidade", "Valor Total", "Cor", "FotoURL"] 

COMMIT_MESSAGE = "Atualiza livro caixa via Streamlit (com produtos/categorias)"
COMMIT_MESSAGE_DELETE = "Exclui movimentações do livro caixa"
COMMIT_MESSAGE_EDIT = "Edita movimentação via Streamlit"
COMMIT_MESSAGE_DEBT_REALIZED = "Conclui dívidas pendentes"
COMMIT_MESSAGE_PROD = "Atualização automática de estoque/produtos"

# COLUNAS ATUALIZADAS PARA INCLUIR ClientID
COLUNAS_PADRAO = ["Data", "Loja", "Cliente", "ClientID", "Valor", "Forma de Pagamento", "Tipo", "Produtos Vendidos", "Categoria", "Status", "Data Pagamento"]
COLUNAS_PADRAO_COMPLETO = COLUNAS_PADRAO + ["RecorrenciaID", "TransacaoPaiID"]
COLUNAS_COMPLETAS_PROCESSADAS = COLUNAS_PADRAO + ["ID Visível", "original_index", "Data_dt", "Saldo Acumulado", "Cor_Valor"]

FATOR_CARTAO = 0.8872
LOJAS_DISPONIVEIS = ["Doce&bella", "Papelaria", "Fotografia", "Outro"]
CATEGORIAS_SAIDA = ["Aluguel", "Salários/Pessoal", "Marketing/Publicidade", "Fornecedores/Matéria Prima", "Despesas Fixas", "Impostos/Taxas", "Outro/Diversos", "Não Categorizado"]
FORMAS_PAGAMENTO = ["Dinheiro", "Cartão", "PIX", "Transferência", "Outro"]

# --- Funções de Persistência ---

def to_float(valor_str):
    try:
        if isinstance(valor_str, (int, float)): return float(valor_str)
        return float(str(valor_str).replace(",", ".").strip())
    except: return 0.0
    
def prox_id(df, coluna_id="ID"):
    if df.empty: return "1"
    try: return str(pd.to_numeric(df[coluna_id], errors='coerce').fillna(0).astype(int).max() + 1)
    except: return str(len(df) + 1)

def hash_df(df):
    df_temp = df.copy()
    for col in df_temp.select_dtypes(include=['datetime64[ns]']).columns:
        df_temp[col] = df_temp[col].astype(str)
    try: return hashlib.md5(df_temp.to_json().encode('utf-8')).hexdigest()
    except Exception: return "error" 

def load_csv_github(url: str) -> pd.DataFrame | None:
    try:
        response = requests.get(url)
        response.raise_for_status()
        df = pd.read_csv(StringIO(response.text), dtype=str)
        if df.empty or len(df.columns) < 2: return None
        return df
    except Exception: return None

def parse_date_yyyy_mm_dd(date_str):
    if pd.isna(date_str) or not date_str: return None
    try: return datetime.strptime(str(date_str).split(" ")[0], "%Y-%m-%d").date()
    except: return None

@st.cache_data(show_spinner="Carregando clientes...")
def carregar_clientes():
    """Carrega o CSV de clientes do repositório."""
    COLUNAS_CLIENTES = ["ClientID", "Nome", "Sobrenome", "Telefone", "Observacao"]
    url_raw = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/{ARQ_CLIENTES}"
    df = load_csv_github(url_raw)
    
    if df is None or df.empty:
        df = pd.DataFrame(columns=COLUNAS_CLIENTES)
    
    for col in COLUNAS_CLIENTES:
        if col not in df.columns:
            df[col] = ""
    
    df['ClientID'] = df['ClientID'].astype(str)
    return df

@st.cache_data(show_spinner="Carregando promoções...")
def carregar_promocoes():
    COLUNAS_PROMO = ["ID", "IDProduto", "NomeProduto", "Desconto", "DataInicio", "DataFim"]
    url_raw = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/{ARQ_PROMOCOES}"
    df = load_csv_github(url_raw)
    if df is None or df.empty: df = pd.DataFrame(columns=COLUNAS_PROMO)
    for col in COLUNAS_PROMO:
        if col not in df.columns: df[col] = "" 
    return df[[col for col in COLUNAS_PROMO if col in df.columns]]

def norm_promocoes(df):
    if df.empty: return df
    df = df.copy()
    df["Desconto"] = pd.to_numeric(df["Desconto"], errors='coerce').fillna(0.0)
    df["DataInicio"] = pd.to_datetime(df["DataInicio"], errors='coerce').dt.date
    df["DataFim"] = pd.to_datetime(df["DataFim"], errors='coerce').dt.date
    df = df[df["DataFim"] >= date.today()] 
    return df

@st.cache_data(show_spinner="Carregando histórico de compras...")
def carregar_historico_compras():
    url_raw = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/{ARQ_COMPRAS}"
    df = load_csv_github(url_raw)
    if df is None or df.empty: df = pd.DataFrame(columns=COLUNAS_COMPRAS)
    for col in COLUNAS_COMPRAS:
        if col not in df.columns: df[col] = "" 
    return df[[col for col in COLUNAS_COMPRAS if col in df.columns]]

def salvar_historico_no_github(df: pd.DataFrame, commit_message: str):
    return True # Placeholder

@st.cache_data(show_spinner="Carregando dados...")
def carregar_livro_caixa():
    url_raw = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/{PATH_DIVIDAS}"
    df = load_csv_github(url_raw)
    if df is None or df.empty:
        try: df = pd.read_csv(ARQ_LOCAL, dtype=str)
        except Exception: df = pd.DataFrame(columns=COLUNAS_PADRAO)
    if df.empty: df = pd.DataFrame(columns=COLUNAS_PADRAO)
    for col in COLUNAS_PADRAO:
        if col not in df.columns: df[col] = "Realizada" if col == "Status" else "" 
    for col in ["RecorrenciaID", "TransacaoPaiID"]:
        if col not in df.columns: df[col] = ''
    return df[[col for col in COLUNAS_PADRAO_COMPLETO if col in df.columns]]

def salvar_dados_no_github(df: pd.DataFrame, commit_message: str):
    try: df.to_csv(ARQ_LOCAL, index=False, encoding="utf-8-sig") 
    except Exception: pass
    df_temp = df.copy()
    for col_date in ['Data', 'Data Pagamento']:
        if col_date in df_temp.columns:
            df_temp[col_date] = pd.to_datetime(df_temp[col_date], errors='coerce').apply(lambda x: x.strftime('%Y-%m-%d') if pd.notnull(x) else '')
    try:
        g = Github(TOKEN)
        repo = g.get_repo(f"{OWNER}/{REPO_NAME}")
        csv_string = df_temp.to_csv(index=False, encoding="utf-8-sig")
        try:
            contents = repo.get_contents(PATH_DIVIDAS, ref=BRANCH)
            repo.update_file(contents.path, commit_message, csv_string, contents.sha, branch=BRANCH)
            st.success("📁 Livro Caixa salvo (atualizado) no GitHub!")
        except Exception:
            repo.create_file(PATH_DIVIDAS, commit_message, csv_string, branch=BRANCH)
            st.success("📁 Livro Caixa salvo (criado) no GitHub!")
        return True
    except Exception as e:
        st.error(f"❌ Erro ao salvar no GitHub: {e}")
        return False

@st.cache_data(show_spinner=False)
def processar_dataframe(df):
    for col in COLUNAS_PADRAO_COMPLETO:
        if col not in df.columns: df[col] = ""
    if df.empty: return pd.DataFrame(columns=COLUNAS_COMPLETAS_PROCESSADAS)
    df_proc = df.copy()
    df_proc["Valor"] = pd.to_numeric(df_proc["Valor"], errors="coerce").fillna(0.0)
    df_proc["Data"] = pd.to_datetime(df_proc["Data"], errors='coerce').dt.date
    df_proc["Data_dt"] = pd.to_datetime(df_proc["Data"], errors='coerce')
    df_proc["Data Pagamento"] = pd.to_datetime(df_proc["Data Pagamento"], errors='coerce').dt.date
    df_proc.dropna(subset=['Data_dt'], inplace=True)
    df_proc = df_proc.reset_index(drop=False).rename(columns={'index': 'original_index'})
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

def calcular_valor_em_aberto(linha):
    try:
        if isinstance(linha, pd.DataFrame) and not linha.empty: valor_raw = pd.to_numeric(linha['Valor'].iloc[0], errors='coerce')
        elif isinstance(linha, pd.Series): valor_raw = pd.to_numeric(linha['Valor'], errors='coerce')
        else: return 0.0
        valor_float = float(valor_raw) if pd.notna(valor_raw) and not isinstance(valor_raw, pd.Series) else 0.0
        return round(abs(valor_float), 2)
    except Exception: return 0.0

def format_produtos_resumo(produtos_json):
    if pd.isna(produtos_json) or produtos_json == "": return ""
    try:
        try: produtos = json.loads(produtos_json)
        except json.JSONDecodeError: produtos = ast.literal_eval(produtos_json)
        if not isinstance(produtos, list) or not all(isinstance(p, dict) for p in produtos): return "Dados inválidos"
        count, primeiro = len(produtos), produtos[0].get('Produto', 'N/A')
        total_custo = sum(to_float(p.get('Custo Unitário', 0)) * to_float(p.get('Quantidade', 0)) for p in produtos)
        total_venda = sum(to_float(p.get('Preço Unitário', 0)) * to_float(p.get('Quantidade', 0)) for p in produtos)
        lucro = total_venda - total_custo
        lucro_str = f"| Lucro R$ {lucro:,.2f}" if lucro != 0 else ""
        return f"{count} item(s): {primeiro}... {lucro_str}"
    except: return "Erro na formatação"

# Funções de gestão de produtos, promoções, compras (sem alterações significativas)
# ... (O código das funções homepage, gestao_promocoes, relatorio_produtos, gestao_produtos, historico_compras foi omitido aqui por brevidade, pois não sofreu alterações críticas)
# --- As funções omitidas podem ser coladas aqui do arquivo original ---
def homepage():
    produtos_df = inicializar_produtos()
    df_movimentacoes = carregar_livro_caixa()
    produtos_novos = produtos_df[produtos_df['Quantidade'] > 0].sort_values(by='ID', ascending=False).head(10)
    df_mais_vendidos_id = get_most_sold_products(df_movimentacoes)
    top_ids_vendidos = df_mais_vendidos_id["Produto_ID"].head(10).tolist() if not df_mais_vendidos_id.empty else []
    if top_ids_vendidos:
        temp = produtos_df[produtos_df["ID"].isin(top_ids_vendidos)].copy()
        present_ids = [pid for pid in top_ids_vendidos if pid in temp["ID"].astype(str).values]
        produtos_mais_vendidos = temp.set_index("ID").loc[present_ids].reset_index() if present_ids else pd.DataFrame(columns=produtos_df.columns)
    else:
        produtos_mais_vendidos = pd.DataFrame(columns=produtos_df.columns)
    produtos_oferta = produtos_df.copy()
    produtos_oferta['PrecoVista_f'] = pd.to_numeric(produtos_oferta['PrecoVista'], errors='coerce').fillna(0)
    produtos_oferta['PrecoCartao_f'] = pd.to_numeric(produtos_oferta['PrecoCartao'], errors='coerce').fillna(0)
    produtos_oferta = produtos_oferta[(produtos_oferta['PrecoVista_f'] > 0) & (produtos_oferta['PrecoCartao_f'] < produtos_oferta['PrecoVista_f'])].sort_values(by='Nome').head(10)
    st.markdown(f'<img src="{URL_MAIS_VENDIDOS}" class="section-header-img" alt="Mais Vendidos">', unsafe_allow_html=True)
    if not produtos_mais_vendidos.empty:
        html_cards = []
        for _, row in produtos_mais_vendidos.iterrows():
            vendas_count = df_mais_vendidos_id[df_mais_vendidos_id["Produto_ID"] == str(row["ID"])]["Quantidade Total Vendida"].iloc[0] if not df_mais_vendidos_id[df_mais_vendidos_id["Produto_ID"] == str(row["ID"])].empty else 0
            foto_url = row.get("FotoURL") or f"https://placehold.co/150x150/F48FB1/880E4F?text={str(row.get('Nome','')).replace(' ', '+')}"
            html_cards.append(f'''<div class="product-card"><img src="{foto_url}" alt="{row['Nome']}"><p style="font-size: 0.9em; height: 40px; white-space: normal;">{row['Nome']} - {row['Marca'] or row['Categoria']}</p><p style="margin: 5px 0 15px;"><span class="price-promo">R$ {to_float(row.get('PrecoCartao', 0)):,.2f}</span></p><button class="buy-button">COMPRAR</button><p style="font-size: 0.7em; color: #888; margin-top: 5px;">Vendas: {int(vendas_count)}</p></div>''')
        st.markdown(f'<div class="carousel-outer-container"><div class="product-wrapper">{"".join(html_cards)}</div></div>', unsafe_allow_html=True)
    st.markdown("---")
    st.markdown('<div class="offer-section">', unsafe_allow_html=True)
    st.markdown(f'<img src="{URL_OFERTAS}" class="section-header-img" alt="Nossas Ofertas">', unsafe_allow_html=True)
    if not produtos_oferta.empty:
        html_cards_ofertas = []
        for _, row in produtos_oferta.iterrows():
            desconto = 1 - (row['PrecoCartao_f'] / row['PrecoVista_f']) if row['PrecoVista_f'] > 0 else 0
            foto_url = row.get("FotoURL") or f"https://placehold.co/150x150/E91E63/FFFFFF?text={str(row.get('Nome','')).replace(' ', '+')}"
            html_cards_ofertas.append(f'''<div class="product-card" style="background-color: #FFF5F7;"><img src="{foto_url}" alt="{row['Nome']}"><p style="font-size: 0.9em; height: 40px; white-space: normal;">{row['Nome']} - {row['Marca'] or row['Categoria']}</p><p style="margin: 5px 0 0;"><span class="price-original">R$ {row['PrecoVista_f']:,.2f}</span><span class="price-promo">R$ {row['PrecoCartao_f']:,.2f}</span></p><p style="color: #E91E63; font-weight: bold; font-size: 0.8em; margin-top: 5px; margin-bottom: 10px;">{round(desconto * 100)}% OFF</p><button class="buy-button">COMPRAR</button></div>''')
        st.markdown(f'<div class="carousel-outer-container"><div class="product-wrapper">{"".join(html_cards_ofertas)}</div></div>', unsafe_allow_html=True)
    st.markdown('</div>---', unsafe_allow_html=True)
    st.markdown(f'<h2>Nossas Novidades</h2>', unsafe_allow_html=True)
    if not produtos_novos.empty:
        html_cards_novidades = []
        for _, row in produtos_novos.iterrows():
            foto_url = row.get("FotoURL") or f"https://placehold.co/400x400/FFC1E3/E91E63?text={row['Nome'].replace(' ', '+')}"
            preco_vista = to_float(row.get('PrecoVista', 0))
            html_cards_novidades.append(f"""<div class="product-card"><p style="font-weight: bold; color: #E91E63; margin-bottom: 10px; font-size: 0.9em;">✨ Doce&Bella - Novidade</p><img src="{foto_url}" alt="{row.get('Nome', '')}"><p style="font-weight: bold; margin-top: 10px; height: 30px; white-space: normal;">{row.get('Nome', '')} ({row.get('Marca', '')})</p><p style="font-size: 0.9em;">✨ Estoque: {int(row.get('Quantidade', 0))}</p><p style="font-weight: bold; color: #E91E63; margin-top: 5px;">💸 {f"R$ {preco_vista:,.2f}" if preco_vista > 0 else "Preço não disponível"}</p></div>""")
        st.markdown(f"""<div class="carousel-outer-container"><div class="product-wrapper">{''.join(html_cards_novidades)}</div></div>""", unsafe_allow_html=True)

# ... (demais funções como gestao_promocoes, gestao_produtos, etc. permanecem aqui) ...

def livro_caixa():
    
    st.header("📘 Livro Caixa - Gerenciamento de Movimentações") 

    # Carrega os dataframes necessários
    clientes_df = carregar_clientes()
    produtos = inicializar_produtos() 

    if "df" not in st.session_state: st.session_state.df = carregar_livro_caixa()
    for col in ['RecorrenciaID', 'TransacaoPaiID', 'ClientID']: # Garante ClientID
        if col not in st.session_state.df.columns: st.session_state.df[col] = ''
        
    # Inicialização de session_state (mantido)
    if "lista_produtos" not in st.session_state: st.session_state.lista_produtos = []
    if "edit_id" not in st.session_state: st.session_state.edit_id = None
    if "divida_a_quitar" not in st.session_state: st.session_state.divida_a_quitar = None 
    
    df_dividas = st.session_state.df
    df_exibicao = processar_dataframe(df_dividas)

    # ... (lógica de opções de produtos mantida) ...

    # --- CRIAÇÃO DAS ABAS ---
    tab_nova_mov, tab_mov, tab_rel = st.tabs(["📝 Nova Movimentação", "📋 Movimentações e Resumo", "📈 Relatórios e Filtros"])

    with tab_nova_mov:
        st.subheader("Nova Movimentação" if not st.session_state.get('edit_id') else "Editar Movimentação Existente")

        # ... (lógica de quitação rápida mantida, sem alterações) ...
        
        col_principal_1, col_principal_2 = st.columns([1, 1])
        with col_principal_1:
            tipo = st.radio("Tipo", ["Entrada", "Saída"], index=0, key="input_tipo", disabled=st.session_state.get('edit_id') is not None)
        
        # --- NOVA LÓGICA DE BUSCA E SELEÇÃO DE CLIENTE ---
        with col_principal_2:
            # Inicializa variáveis de estado para o fluxo de seleção
            if "cliente_pesquisado" not in st.session_state: st.session_state.cliente_pesquisado = ""
            if "clientes_encontrados" not in st.session_state: st.session_state.clientes_encontrados = None
            if "cliente_selecionado_id" not in st.session_state: st.session_state.cliente_selecionado_id = None

            nome_pesquisa = st.text_input("Digite o nome do cliente para buscar", key="input_cliente_busca")

            if st.button("Buscar Cliente", key="btn_buscar_cliente"):
                st.session_state.cliente_selecionado_id = None
                if nome_pesquisa.strip():
                    st.session_state.cliente_pesquisado = nome_pesquisa
                    clientes_encontrados_df = clientes_df[
                        clientes_df["Nome"].str.contains(nome_pesquisa, case=False, na=False)
                    ].copy()
                    st.session_state.clientes_encontrados = clientes_encontrados_df
                else:
                    st.session_state.clientes_encontrados = None
            
            if st.session_state.clientes_encontrados is not None:
                if st.session_state.clientes_encontrados.empty:
                    st.error(f"Nenhum cliente encontrado com o nome '{st.session_state.cliente_pesquisado}'.")
                
                elif len(st.session_state.clientes_encontrados) > 1:
                    st.warning("Foram encontrados múltiplos clientes. Selecione o correto:")
                    opcoes = { f"{row['Nome']} {row['Sobrenome']} (Tel: {row['Telefone'] or 'N/A'})": row['ClientID'] 
                               for _, row in st.session_state.clientes_encontrados.iterrows() }
                    cliente_escolhido_label = st.radio("Selecione o cliente:", options=opcoes.keys(), key="radio_cliente_selecao")

                    if st.button("Confirmar Cliente", key="btn_confirmar_cliente"):
                        st.session_state.cliente_selecionado_id = opcoes[cliente_escolhido_label]
                        st.rerun()

                else: # Apenas 1 encontrado
                    cliente_unico = st.session_state.clientes_encontrados.iloc[0]
                    st.session_state.cliente_selecionado_id = cliente_unico['ClientID']
                    st.session_state.clientes_encontrados = None 
                    st.rerun()

            # DEPOIS QUE UM CLIENTE É SELECIONADO, BUSCA AS DÍVIDAS DELE
            if st.session_state.cliente_selecionado_id:
                cliente_selecionado_info = clientes_df[clientes_df['ClientID'] == st.session_state.cliente_selecionado_id].iloc[0]
                st.info(f"Cliente em Foco: **{cliente_selecionado_info['Nome']} {cliente_selecionado_info['Sobrenome']}**")

                # A busca por dívidas agora usa o ClientID
                df_dividas_cliente = df_exibicao[
                    (df_exibicao["ClientID"].astype(str) == str(st.session_state.cliente_selecionado_id)) &
                    (df_exibicao["Status"] == "Pendente") &
                    (df_exibicao["Tipo"] == "Entrada")
                ].copy()

                if not df_dividas_cliente.empty:
                    total_divida = df_dividas_cliente["Valor"].abs().round(2).sum()
                    divida_mais_antiga = df_dividas_cliente.iloc[0]
                    st.warning(f"💰 Este cliente possui {len(df_dividas_cliente)} conta(s) em aberto, totalizando R$ {total_divida:,.2f}.")
                    # ... (lógica dos botões de quitar, adicionar à dívida, etc.) ...


        if tipo == "Entrada":
            # ... (lógica de adicionar produtos à venda, mantida) ...

            # NOVO: Desabilita o formulário se nenhum cliente for selecionado
            if not st.session_state.cliente_selecionado_id and not st.session_state.get('edit_id'):
                st.markdown("---")
                st.warning("⬅️ Por favor, busque e selecione um cliente para registrar uma nova venda.")
            else:
                # ... (resto do formulário de entrada, valor, status, etc.) ...
                
                # --- FORMULÁRIO DE DADOS GERAIS E BOTÃO SALVAR ---
                with st.form("form_movimentacao", clear_on_submit=not st.session_state.get('edit_id')):
                    # ... (campos do formulário: loja, data, forma de pagamento etc.) ...
                    
                    enviar = st.form_submit_button("💾 Adicionar e Salvar", type="primary", use_container_width=True)

                    if enviar:
                        # ... (lógica de validação) ...
                        
                        # ATUALIZAÇÃO NO SALVAMENTO
                        cliente_info_save = cliente_selecionado_info if st.session_state.cliente_selecionado_id else {'Nome': 'N/A', 'Sobrenome': ''}

                        nova_linha_data = {
                            "Data": data_input,
                            "Loja": loja_selecionada, 
                            "Cliente": f"{cliente_info_save['Nome']} {cliente_info_save['Sobrenome']}".strip(),
                            "ClientID": st.session_state.cliente_selecionado_id, # SALVA O ID
                            "Valor": valor_armazenado, 
                            "Forma de Pagamento": forma_pagamento,
                            "Tipo": tipo,
                            "Produtos Vendidos": produtos_vendidos_json,
                            "Categoria": categoria_selecionada,
                            "Status": status_selecionado, 
                            "Data Pagamento": data_pagamento_final
                            # ... (outros campos como RecorrenciaID)
                        }
                        
                        # ... (lógica de concatenação e salvamento no github) ...
                        salvar_dados_no_github(st.session_state.df, COMMIT_MESSAGE)
                        # Limpa estados para a próxima transação
                        st.session_state.cliente_selecionado_id = None
                        st.session_state.lista_produtos = []
                        st.cache_data.clear()
                        st.rerun()

        else: # Tipo Saída
            # ... (lógica de saída mantida) ...
            pass
    
    # ... (código das abas tab_mov e tab_rel, sem alterações críticas) ...


# ==============================================================================
# ESTRUTURA PRINCIPAL E NAVEGAÇÃO SUPERIOR
# ==============================================================================

PAGINAS = {
    "Home": homepage,
    "Livro Caixa": livro_caixa,
    # "Produtos": gestao_produtos,
    # "Promoções": gestao_promocoes,
    # "Histórico de Compra": historico_compras
}

if "pagina_atual" not in st.session_state:
    st.session_state.pagina_atual = "Home"

def render_header():
    col_logo, col_nav = st.columns([1, 4])
    with col_logo:
        st.image(LOGO_DOCEBELLA_URL, width=150)
    with col_nav:
        paginas_ordenadas = ["Home", "Livro Caixa", "Produtos", "Promoções", "Histórico de Compra"]
        cols_botoes = st.columns(len(paginas_ordenadas))
        for i, nome in enumerate(paginas_ordenadas):
            if nome in PAGINAS and cols_botoes[i].button(nome, key=f"nav_{nome}", use_container_width=True):
                st.session_state.pagina_atual = nome
                st.rerun()

with st.container():
    st.markdown('<div class="header-container">', unsafe_allow_html=True)
    render_header()
    st.markdown('</div>', unsafe_allow_html=True)

if st.session_state.pagina_atual in PAGINAS:
    PAGINAS[st.session_state.pagina_atual]()
