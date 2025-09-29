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
# CORREÇÃO: Utiliza URL pública fornecida pelo usuário para maior estabilidade.
LOGO_DOCEBELLA_FILENAME = "logo_docebella.jpg"
LOGO_DOCEBELLA_URL = "https://imgur.com/a/je4YIoi"


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
    
    /* --- Estilo dos Cards de Produto (Mais Vendidos / Ofertas) --- */
    .product-card {
        background-color: white;
        border-radius: 10px;
        padding: 15px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
        text-align: center;
        height: 100%;
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
    .buy-button > button {
        background-color: #E91E63; /* Cor Pink de Destaque */
        color: white;
        font-weight: bold;
        border-radius: 20px;
        border: none;
        padding: 8px 15px;
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
    
    </style>
""", unsafe_allow_html=True)


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

        if 'streamlit' in globals():
            st.write("Debug API ZXing:", codigos)

        if not codigos and 'streamlit' in globals():
            st.warning("⚠️ API ZXing não retornou nenhum código válido. Tente novamente ou use uma imagem mais clara.")

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
ARQ_LOCAL = "livro_caixa.csv"
PATH_DIVIDAS = CSV_PATH
ARQ_COMPRAS = "historico_compras.csv"
ARQ_PROMOCOES = "promocoes.csv" # Novo arquivo para promoções
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
    df_temp = df.copy()
    for col in df_temp.select_dtypes(include=['datetime64[ns]']).columns:
        df_temp[col] = df_temp[col].astype(str)
    try:
        return hashlib.md5(df_temp.to_json().encode('utf-8')).hexdigest()
    except Exception:
        return "error" 

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

def save_csv_github(df: pd.DataFrame, file_path: str, commit_message: str):
    """Função dummy para simular o salvamento no GitHub."""
    # A implementação real foi omitida para simplificar o código
    return True

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

def salvar_historico_no_github(df: pd.DataFrame, commit_message: str):
    return True

@st.cache_data(show_spinner="Carregando dados...")
def carregar_livro_caixa():
    url_raw = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/{PATH_DIVIDAS}"
    df = load_csv_github(url_raw)
    if df is None or df.empty:
        try:
            df = pd.read_csv(ARQ_LOCAL, dtype=str)
        except Exception:
            df = pd.DataFrame(columns=COLUNAS_PADRAO)
    if df.empty:
        df = pd.DataFrame(columns=COLUNAS_PADRAO)
    for col in COLUNAS_PADRAO:
        if col not in df.columns:
            df[col] = "Realizada" if col == "Status" else "" 
    if 'RecorrenciaID' not in df.columns:
        df['RecorrenciaID'] = ''
    cols_to_return = COLUNAS_PADRAO + ["RecorrenciaID"]
    return df[[col for col in cols_to_return if col in df.columns]]

def salvar_dados_no_github(df: pd.DataFrame, commit_message: str):
    return True

@st.cache_data(show_spinner=False)
def processar_dataframe(df):
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
        # MANTEMOS COMO DATE PARA EXIBIÇÃO NO ESTOQUE, MAS CONVERTEMOS PARA DATETIME/TIMESTAMP
        # PONTUALMENTE NA GESTAO_PROMOCOES PARA OPERAÇÕES DE COMPARAÇÃO NO PANDAS.
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
    """Calcula os produtos mais vendidos (por quantidade de itens vendidos)."""
    
    # 1. Filtra apenas as transações de Entrada (vendas) que foram Realizadas
    df_vendas = df_movimentacoes[
        (df_movimentacoes["Tipo"] == "Entrada") & 
        (df_movimentacoes["Status"] == "Realizada") &
        (df_movimentacoes["Produtos Vendidos"].notna()) &
        (df_movimentacoes["Produtos Vendidos"] != "")
    ].copy()

    if df_vendas.empty:
        return pd.DataFrame(columns=["Produto_ID", "Quantidade Total Vendida"])

    vendas_list = []
    
    # 2. Desempacota o JSON de Produtos Vendidos
    for produtos_json in df_vendas["Produtos Vendidos"]:
        try:
            try:
                produtos = json.loads(produtos_json)
            except json.JSONDecodeError:
                produtos = ast.literal_eval(produtos_json)
            
            if isinstance(produtos, list):
                for item in produtos:
                    if item.get("Produto_ID"):
                         vendas_list.append({
                            "Produto_ID": str(item["Produto_ID"]),
                            "Quantidade": to_float(item.get("Quantidade", 0))
                        })
        except:
            continue
            
    df_vendas_detalhada = pd.DataFrame(vendas_list)
    
    if df_vendas_detalhada.empty:
        return pd.DataFrame(columns=["Produto_ID", "Quantidade Total Vendida"])

    # 3. Soma as quantidades por Produto_ID
    df_mais_vendidos = df_vendas_detalhada.groupby("Produto_ID")["Quantidade"].sum().reset_index()
    df_mais_vendidos.rename(columns={"Quantidade": "Quantidade Total Vendida"}, inplace=True)
    df_mais_vendidos.sort_values(by="Quantidade Total Vendida", ascending=False, inplace=True)
    
    return df_mais_vendidos

# ==============================================================================
# 1. PÁGINA DE APRESENTAÇÃO (HOMEPAGE)
# ==============================================================================

def homepage():
    
    # --- 1. Carrega dados e calcula métricas ---
    produtos_df = inicializar_produtos()
    df_movimentacoes = carregar_livro_caixa()
    
    # Produtos novos (últimos 3 cadastrados com estoque > 0)
    produtos_novos = produtos_df[produtos_df['Quantidade'] > 0].sort_values(by='ID', ascending=False).head(3)
    
    # Produtos mais vendidos (Top 4)
    df_mais_vendidos_id = get_most_sold_products(df_movimentacoes)
    
    # Filtra os 4 produtos mais vendidos, garantindo que existam no df_produtos
    top_4_ids = df_mais_vendidos_id["Produto_ID"].head(4).tolist()
    produtos_mais_vendidos = produtos_df[produtos_df["ID"].isin(top_4_ids)].set_index("ID").loc[top_4_ids].reset_index()
    
    # Produtos em Oferta: Preço no Cartão (PrecoCartao) < Preço à Vista (PrecoVista)
    # Garante que os valores sejam convertidos para float antes da comparação
    produtos_oferta = produtos_df.copy()
    produtos_oferta['PrecoVista_f'] = pd.to_numeric(produtos_oferta['PrecoVista'], errors='coerce').fillna(0)
    produtos_oferta['PrecoCartao_f'] = pd.to_numeric(produtos_oferta['PrecoCartao'], errors='coerce').fillna(0)
    
    produtos_oferta = produtos_oferta[
        (produtos_oferta['PrecoVista_f'] > 0) & # Preço à vista deve ser > 0
        (produtos_oferta['PrecoCartao_f'] < produtos_oferta['PrecoVista_f']) # Promoção é se o preço no cartão for menor que o à vista
    ].sort_values(by='Nome').head(4)


    
    # --- 2. Conteúdo Estático (Título e Loja Física) ---
    st.markdown('<h1 class="homepage-title">Doce&Bella! 🌸</h1>', unsafe_allow_html=True)
    st.markdown('<p class="homepage-subtitle">Seu parceiro de gestão e beleza!</p>', unsafe_allow_html=True)
    st.info("Esta é a página de apresentação da sua loja virtual, simulando o layout que você enviou. Use os botões no topo para acessar a Gestão Financeira.")

    col_img, col_text = st.columns([1, 2])
    with col_img:
        st.image("https://placehold.co/300x200/F48FB1/880E4F?text=Loja+Física", use_column_width=True)
    with col_text:
        st.markdown('<h2 style="color: #E91E63;">Loja Física</h2>', unsafe_allow_html=True)
        st.markdown("""
        Prefere ver tudo de pertinho? 
        Vem nos visitar e garanta seus produtos na hora, com aquele atendimento que você já ama.
        """)
        st.button("📍 VER TUDO", key="home_ver_tudo", type="secondary")

    st.markdown("---")


    # ==================================================
    # 3. SEÇÃO MAIS VENDIDOS (Top 4, baseado na imagem)
    # ==================================================
    st.markdown('<h2 style="color: #888; text-align: center; margin-bottom: 30px;">Mais Vendidos</h2>', unsafe_allow_html=True)
    
    if produtos_mais_vendidos.empty:
        st.info("Não há dados de vendas suficientes (Entradas Realizadas) para determinar os produtos mais vendidos.")
    else:
        # Colunas para exibir os cards
        cols_mais_vendidos = st.columns(len(produtos_mais_vendidos))
        
        for i, row in produtos_mais_vendidos.iterrows():
            with cols_mais_vendidos[i]:
                # Busca a quantidade total vendida para este produto
                vendas_count = df_mais_vendidos_id[df_mais_vendidos_id["Produto_ID"] == row["ID"]]["Quantidade Total Vendida"].iloc[0] if not df_mais_vendidos_id.empty else 0
                
                # Prepara dados do produto
                nome_produto = row['Nome']
                descricao = row['Marca'] if row['Marca'] else row['Categoria']
                preco_vista = to_float(row.get('PrecoVista', 0))
                preco_cartao = to_float(row.get('PrecoCartao', 0)) # Preço final (padrão)
                
                # Preço a exibir (usando o preço de cartão como principal)
                preco_exibido = preco_cartao
                
                # Imagem do produto
                foto_url = row.get("FotoURL") if row.get("FotoURL") else f"https://placehold.co/150x150/F48FB1/880E4F?text={row['Nome'].replace(' ', '+')}"

                # Renderiza o Card
                st.markdown('<div class="product-card">', unsafe_allow_html=True)
                st.image(foto_url, width=150)
                st.markdown(f'<p style="font-size: 0.9em; height: 40px;">{nome_produto} - {descricao}</p>', unsafe_allow_html=True)
                
                # Preços (simulação simples)
                st.markdown(f'<p style="margin: 5px 0 15px;">'
                            f'<span class="price-promo">R$ {preco_exibido:,.2f}</span>'
                            f'</p>', unsafe_allow_html=True)

                # Botão de Compra Simulado
                st.button("COMPRAR", key=f"comprar_mais_vendido_{i}", use_container_width=True, type="secondary")
                st.markdown('</div>', unsafe_allow_html=True)
                st.caption(f"Vendas: {int(vendas_count)}")
                
    st.markdown("---")
    
    
    # ==================================================
    # 4. SEÇÃO NOSSAS OFERTAS (Top 4 em promoção)
    # ==================================================
    st.markdown('<div class="offer-section">', unsafe_allow_html=True)
    st.markdown('<div class="megaphone-icon">📢</div>', unsafe_allow_html=True) # Ícone de megafone simulado
    st.markdown('<h2 class="offer-title">Nossas Ofertas</h2>', unsafe_allow_html=True)

    if produtos_oferta.empty:
        st.info("Nenhum produto em promoção registrado no momento. Ajuste o Preço no Cartão (PrecoCartao) para ser menor que o Preço à Vista (PrecoVista) para criar uma oferta.")
    else:
        cols_ofertas = st.columns(len(produtos_oferta))
        
        for i, row in produtos_oferta.iterrows():
            with cols_ofertas[i]:
                nome_produto = row['Nome']
                descricao = row['Marca'] if row['Marca'] else row['Categoria']
                preco_vista_original = row['PrecoVista_f'] # Preço maior (original)
                preco_cartao_promo = row['PrecoCartao_f']  # Preço menor (promoção)
                
                # Calcula o desconto
                desconto = 1 - (preco_cartao_promo / preco_vista_original)
                desconto_percent = round(desconto * 100)
                
                foto_url = row.get("FotoURL") if row.get("FotoURL") else f"https://placehold.co/150x150/E91E63/FFFFFF?text={row['Nome'].replace(' ', '+')}"

                # Renderiza o Card de Oferta
                st.markdown('<div class="product-card">', unsafe_allow_html=True)
                st.image(foto_url, width=150)
                st.markdown(f'<p style="font-size: 0.9em; height: 40px;">{nome_produto} - {descricao}</p>', unsafe_allow_html=True)
                
                # Preços com Desconto
                st.markdown(f'<p style="margin: 5px 0 15px;">'
                            f'<span class="price-original">R$ {preco_vista_original:,.2f}</span>'
                            f'<span class="price-promo">R$ {preco_cartao_promo:,.2f}</span>'
                            f'</p>', unsafe_allow_html=True)

                st.markdown(f'<p style="color: #E91E63; font-weight: bold; font-size: 0.8em; margin-top: -10px;">{desconto_percent}% OFF</p>', unsafe_allow_html=True)


                # Botão de Compra Simulado
                st.button("COMPRAR", key=f"comprar_oferta_{i}", use_container_width=True, type="secondary")
                st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True) # Fecha offer-section

    st.markdown("---")
    
    # ==================================================
    # 5. SEÇÃO NOSSAS NOVIDADES (Últimos 3 produtos - Mantido)
    # ==================================================
    st.markdown('<h2 style="color: #E91E63; text-align: center;">Nossas Novidades</h2>', unsafe_allow_html=True)
    
    card1, card2, card3 = st.columns(3)
    cards = [card1, card2, card3]
    
    if produtos_novos.empty:
        st.info("Não há produtos cadastrados no estoque para exibir como novidades.")
    
    for i, row in produtos_novos.iterrows():
        if i < len(cards):
            card = cards[i]
            
            foto_url = row.get("FotoURL") if row.get("FotoURL") else f"https://placehold.co/400x400/FFC1E3/E91E63?text={row['Nome'].replace(' ', '+')}"
            
            with card:
                st.markdown('<div class="insta-card">', unsafe_allow_html=True)
                st.markdown(f'<div class="insta-header">✨ Doce&Bella - Novidade</div>', unsafe_allow_html=True)
                
                try:
                    st.image(foto_url, use_column_width=True)
                except:
                     st.image(f"https://placehold.co/400x400/FFC1E3/E91E63?text=Erro+Foto", use_container_width=True)
                     
                
                preco_vista = to_float(row.get('PrecoVista', 0))
                descricao = f"R$ {preco_vista:,.2f}" if preco_vista > 0 else "Preço não disponível"
                
                st.markdown(f"""
                <p><strong>{row['Nome']} ({row['Marca']})</strong></p>
                <p>✨ Estoque: {row['Quantidade']}</p>
                <p>💸 {descricao}</p>
                </div>""", unsafe_allow_html=True)

    for i in range(len(produtos_novos), 3):
        card = cards[i]
        with card:
            st.markdown('<div class="insta-card">', unsafe_allow_html=True)
            st.markdown(f'<div class="insta-header">🛒 Doce&Bella</div>', unsafe_allow_html=True)
            st.image("https://placehold.co/400x400/F48FB1/880E4F?text=Espaço+Disponível", use_column_width=True)
            st.markdown("""
            <p>Em breve, mais novidades e produtos incríveis para você!</p>
            </div>""", unsafe_allow_html=True)
        
# ==============================================================================
# 2. PÁGINAS DE GESTÃO (LIVRO CAIXA, PRODUTOS, COMPRAS, PROMOÇÕES)
# ==============================================================================

def gestao_promocoes():
    """Página de gerenciamento de promoções (Bloco inserido pelo usuário)."""
    
    # Inicializa ou carrega o estado de produtos e promoções
    produtos = inicializar_produtos()
    
    if "promocoes" not in st.session_state:
        st.session_state.promocoes = carregar_promocoes()
    
    promocoes_df = st.session_state.promocoes
    
    # Processa o DataFrame de promoções (normaliza datas e filtra expiradas)
    promocoes = norm_promocoes(promocoes_df.copy())
    
    # Recarrega as vendas para a lógica de produtos parados
    # Nota: Em um ambiente real, 'vendas' viria do Livro Caixa (Entradas Realizadas)
    df_movimentacoes = carregar_livro_caixa()
    vendas = df_movimentacoes[df_movimentacoes["Tipo"] == "Entrada"].copy()
    
    # --- PRODUTOS COM VENDA (para análise de inatividade) ---
    vendas_list = []
    for produtos_json in vendas["Produtos Vendidos"].dropna():
        try:
            items = ast.literal_eval(produtos_json)
            for item in items:
                # O valor da coluna "Data" no Livro Caixa é um objeto date (string formatada em YYYY-MM-DD),
                # precisamos garantir que ele se torne um objeto date/datetime aqui.
                vendas_list.append({
                    "Data": parse_date_yyyy_mm_dd(vendas[vendas["Produtos Vendidos"] == produtos_json]["Data"].iloc[0]), 
                    "IDProduto": str(item.get("Produto_ID"))
                })
        except:
            continue
            
    vendas_flat = pd.DataFrame(vendas_list).dropna(subset=["IDProduto"])
    

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
                        if save_csv_github(st.session_state.promocoes, ARQ_PROMOCOES, "Atualizando promoções"):
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

                if save_csv_github(st.session_state.promocoes, ARQ_PROMOCOES, "Criando promoções automáticas de produtos parados"):
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
                    df = parse_date_yyyy_mm_dd(linha_original["DataFim"]) or (date.today() + timedelta(days=7))
                    data_fim_e = st.date_input("Término", value=df, key=f"promo_edit_fim_{promo_id_selecionado}")
                
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
                            if save_csv_github(promocoes_df, ARQ_PROMOCOES, f"Editando promoção ID {promo_id_selecionado}"):
                                carregar_promocoes.clear()
                                st.success("Promoção atualizada!")
                                st.rerun()  # 🔑 atualização imediata

                with col_btn_delete:
                    if st.button("🗑️ Excluir Promoção", key=f"promo_btn_del_{promo_id_selecionado}", type="primary", use_container_width=True):
                        st.session_state.promocoes = promocoes_df[promocoes_df["ID"].astype(str) != promo_id_selecionado]
                        if save_csv_github(st.session_state.promocoes, ARQ_PROMOCOES, f"Excluindo promoção ID {promo_id_selecionado}"):
                            carregar_promocoes.clear()
                            st.warning(f"Promoção {promo_id_selecionado} excluída!")
                            st.rerun()  # 🔑 atualização imediata
        else:
            st.info("Selecione uma promoção para ver as opções de edição e exclusão.")


def gestao_produtos():
    # ... (Conteúdo completo da função Gestão de Produtos)
    
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
                    var_preco_vista = st.text_input(f"Preço à Vista variação {i+1}", value="0,00", key=f"var_pv_{i}")
                    
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
                produtos_filtrados = produtos.copy()

            if "PaiID" not in produtos_filtrados.columns:
                produtos_filtrados["PaiID"] = None

        # --- Lista de produtos com agrupamento por Pai e Variações ---
        st.markdown("### Lista de produtos")

        if produtos_filtrados.empty:
            st.info("Nenhum produto encontrado.")
        else:
            produtos_filtrados["Quantidade"] = pd.to_numeric(produtos_filtrados["Quantidade"], errors='coerce').fillna(0).astype(int)
            produtos_pai = produtos_filtrados[produtos_filtrados["PaiID"].isnull()]
            produtos_filho = produtos_filtrados[produtos_filtrados["PaiID"].notnull()]
            
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
    # ... (Conteúdo completo da função Histórico de Compras)
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
                index=0, 
                key="select_compra_operacao"
            )
            
            original_idx_selecionado = opcoes_compra_operacao.get(compra_selecionada_str)
            item_selecionado_str = compra_selecionada_str
            
            if original_idx_selecionado is not None:
                
                col_edit, col_delete = st.columns(2)

                if col_edit.button(f"✏️ Editar: {item_selecionado_str}", type="secondary", use_container_width=True):
                    st.session_state.edit_compra_idx = original_idx_selecionado
                    st.rerun()

                if col_delete.button(f"🗑️ Excluir: {item_selecionado_str}", type="primary", use_container_width=True):
                    st.session_state.df_compras = st.session_state.df_compras.drop(original_idx_selecionado, errors='ignore')
                    
                    if salvar_historico_no_github(st.session_state.df_compras, f"Exclusão da compra {item_selecionado_str}"):
                        st.cache_data.clear()
                        st.rerun()
            else:
                st.info("Selecione um item no menu acima para editar ou excluir.")

def livro_caixa():
    # ... (Conteúdo completo da função Livro Caixa)
    st.header("📘 Livro Caixa - Gerenciamento de Movimentações") # Mantém o st.header para o título da seção

    produtos = inicializar_produtos() 

    if "df" not in st.session_state: st.session_state.df = carregar_livro_caixa()
    if 'RecorrenciaID' not in st.session_state.df.columns: st.session_state.df['RecorrenciaID'] = ''
    if "produtos" not in st.session_state: st.session_state.produtos = produtos
    if "lista_produtos" not in st.session_state: st.session_state.lista_produtos = []
    if "edit_id" not in st.session_state: st.session_state.edit_id = None
    if "operacao_selecionada" not in st.session_state: st.session_state.operacao_selecionada = "Editar" 

    df_dividas = st.session_state.df
    df_exibicao = processar_dataframe(df_dividas)

    produtos_para_venda = produtos[produtos["PaiID"].notna() | produtos["PaiID"].isnull()].copy()
    opcoes_produtos = [""] + produtos_para_venda.apply(
        lambda row: f"{row.ID} | {row.Nome} ({row.Marca}) | Estoque: {row.Quantidade}", axis=1
    ).tolist()
    OPCAO_MANUAL = "Adicionar Item Manual (Sem Controle de Estoque)"
    opcoes_produtos.append(OPCAO_MANUAL)

    def extrair_id_do_nome(opcoes_str):
        if ' | ' in opcoes_str: return opcoes_str.split(' | ')[0]
        return None
        
    if "input_nome_prod_manual" not in st.session_state: st.session_state.input_nome_prod_manual = ""
    if "input_qtd_prod_manual" not in st.session_state: st.session_state.input_qtd_prod_manual = 1.0
    if "input_preco_prod_manual" not in st.session_state: st.session_state.input_preco_prod_manual = 0.01
    if "input_custo_prod_manual" not in st.session_state: st.session_state.input_custo_prod_manual = 0.00
    if "input_produto_selecionado" not in st.session_state: st.session_state.input_produto_selecionado = ""

    edit_mode = st.session_state.edit_id is not None
    movimentacao_para_editar = None

    default_loja = LOJAS_DISPONIVEIS[0]
    default_data = datetime.now().date()
    default_cliente = ""
    default_valor = 0.01
    default_forma = "Dinheiro"
    default_tipo = "Entrada"
    default_produtos_json = ""
    default_categoria = CATEGORIAS_SAIDA[0]
    default_status = "Realizada" 
    default_data_pagamento = None 

    if edit_mode:
        original_idx_to_edit = st.session_state.edit_id
        linha_df_exibicao = df_exibicao[df_exibicao['original_index'] == original_idx_to_edit]

        if not linha_df_exibicao.empty:
            movimentacao_para_editar = linha_df_exibicao.iloc[0]
            default_loja = movimentacao_para_editar['Loja']
            default_data = movimentacao_para_editar['Data'] if pd.notna(movimentacao_para_editar['Data']) else datetime.now().date()
            default_cliente = movimentacao_para_editar['Cliente']
            default_valor = abs(movimentacao_para_editar['Valor']) if movimentacao_para_editar['Valor'] != 0 else 0.01 
            default_forma = movimentacao_para_editar['Forma de Pagamento']
            default_tipo = movimentacao_para_editar['Tipo']
            default_produtos_json = movimentacao_para_editar['Produtos Vendidos'] if pd.notna(movimentacao_para_editar['Produtos Vendidos']) else ""
            default_categoria = movimentacao_para_editar['Categoria']
            default_status = movimentacao_para_editar['Status'] 
            default_data_pagamento = movimentacao_para_editar['Data Pagamento'] if pd.notna(movimentacao_para_editar['Data Pagamento']) else (movimentacao_para_editar['Data'] if movimentacao_para_editar['Status'] == 'Realizada' else None) 
            
            if default_tipo == "Entrada" and default_produtos_json:
                try:
                    try:
                        produtos_list = json.loads(default_produtos_json)
                    except json.JSONDecodeError:
                        produtos_list = ast.literal_eval(default_produtos_json)

                    for p in produtos_list:
                        p['Quantidade'] = float(p.get('Quantidade', 0))
                        p['Preço Unitário'] = float(p.get('Preço Unitário', 0))
                        p['Custo Unitário'] = float(p.get('Custo Unitário', 0))
                        p['Produto_ID'] = str(p.get('Produto_ID', ''))
                    st.session_state.lista_produtos = [p for p in produtos_list if p['Quantidade'] > 0] 
                except:
                    st.session_state.lista_produtos = []
            elif default_tipo == "Saída":
                st.session_state.lista_produtos = []
            
            st.sidebar.warning(f"Modo EDIÇÃO: Movimentação ID {movimentacao_para_editar['ID Visível']}")
            
        else:
            st.session_state.edit_id = None
            edit_mode = False
            st.sidebar.info("Movimentação não encontrada, saindo do modo de edição.")
            st.rerun() 


    with st.sidebar:
        st.header("Nova Movimentação" if not edit_mode else "Editar Movimentação Existente")
        
        tipo = st.radio("Tipo", ["Entrada", "Saída"], index=0 if default_tipo == "Entrada" else 1, key="input_tipo", disabled=edit_mode)
        
        is_recorrente = False
        status_selecionado = default_status
        data_primeira_parcela = date.today().replace(day=1) + timedelta(days=32)
        valor_parcela = default_valor
        nome_despesa_recorrente = default_cliente
        num_parcelas = 1
        
        valor_calculado = 0.0
        produtos_vendidos_json = ""
        categoria_selecionada = ""
        
        if tipo == "Entrada":
            st.markdown("#### 🛍️ Detalhes dos Produtos (Entrada)")
            
            if st.session_state.lista_produtos:
                df_produtos = pd.DataFrame(st.session_state.lista_produtos)
                df_produtos['Quantidade'] = pd.to_numeric(df_produtos['Quantidade'], errors='coerce').fillna(0)
                df_produtos['Preço Unitário'] = pd.to_numeric(df_produtos['Preço Unitário'], errors='coerce').fillna(0.0)
                df_produtos['Custo Unitário'] = pd.to_numeric(df_produtos['Custo Unitário'], errors='coerce').fillna(0.0)
                
                valor_calculado = (df_produtos['Quantidade'] * df_produtos['Preço Unitário']).sum()
                
                produtos_para_json = df_produtos[['Produto_ID', 'Produto', 'Quantidade', 'Preço Unitário', 'Custo Unitário']].to_dict('records')
                produtos_vendidos_json = json.dumps(produtos_para_json)
                
                st.success(f"Soma Total da Venda Calculada: R$ {valor_calculado:,.2f}")

            with st.expander("➕ Adicionar/Limpar Lista de Produtos", expanded=True):
                with st.container():
                    st.markdown("##### Produtos Atuais:")
                    if st.session_state.lista_produtos:
                        df_exibicao_produtos = pd.DataFrame(st.session_state.lista_produtos)
                        st.dataframe(df_exibicao_produtos[['Produto', 'Quantidade', 'Preço Unitário']], use_container_width=True, hide_index=True)
                    else:
                        st.info("Lista de produtos vazia.")

                    produto_selecionado = st.selectbox(
                        "Selecione o Produto (ID | Nome)", 
                        opcoes_produtos, 
                        key="input_produto_selecionado",
                        index=opcoes_produtos.index(st.session_state.input_produto_selecionado) if st.session_state.input_produto_selecionado in opcoes_produtos else 0
                    )
                    
                    
                    if produto_selecionado == OPCAO_MANUAL:
                        nome_produto_manual = st.text_input(
                            "Nome do Produto (Manual)", 
                            value=st.session_state.input_nome_prod_manual,
                            key="input_nome_prod_manual"
                        )
                        quantidade_manual = st.number_input(
                            "Qtd Manual", 
                            min_value=0.01, 
                            value=st.session_state.input_qtd_prod_manual, 
                            step=1.0, 
                            key="input_qtd_prod_manual"
                        )
                        preco_unitario_manual = st.number_input(
                            "Preço Unitário (R$)", 
                            min_value=0.01, 
                            format="%.2f", 
                            value=st.session_state.input_preco_prod_manual,
                            key="input_preco_prod_manual"
                        )
                        custo_unitario_manual = st.number_input(
                            "Custo Unitário (R$)", 
                            min_value=0.00, 
                            value=st.session_state.input_custo_prod_manual,
                            format="%.2f", 
                            key="input_custo_prod_manual"
                        )
                        
                        if st.button(
                            "Adicionar Manual", 
                            key="adicionar_item_manual_button", 
                            use_container_width=True,
                            on_click=callback_adicionar_manual,
                            args=(nome_produto_manual, quantidade_manual, preco_unitario_manual, custo_unitario_manual),
                            help="Adicionar Item Manual à Lista de Venda" 
                        ):
                            st.rerun() 

                    
                    elif produto_selecionado != "":
                        produto_id_selecionado = extrair_id_do_nome(produto_selecionado) 
                        produto_row_completa = produtos_para_venda[produtos_para_venda["ID"] == produto_id_selecionado]
                        
                        if not produto_row_completa.empty:
                            produto_data = produto_row_completa.iloc[0]
                            nome_produto = produto_data['Nome']
                            # Nota: Aqui estamos usando o PrecoVista como preço base
                            preco_sugerido = produto_data['PrecoVista'] 
                            custo_unit = produto_data['PrecoCusto']
                            estoque_disp = produto_data['Quantidade']

                            col_p1, col_p2 = st.columns(2)
                            with col_p1:
                                quantidade_input = st.number_input("Qtd", min_value=1, value=1, step=1, max_value=int(estoque_disp) if estoque_disp > 0 else 1, key="input_qtd_prod_edit")
                            with col_p2:
                                # O preço já será ajustado pelo callback
                                preco_unitario_input = st.number_input("Preço Unitário (R$)", min_value=0.01, format="%.2f", value=float(preco_sugerido), key="input_preco_prod_edit")
                            
                            st.caption(f"Custo Unitário: R$ {custo_unit:,.2f}")

                            if st.button(
                                "Adicionar Item", 
                                key="adicionar_item_button", 
                                use_container_width=True,
                                # Chama o callback, que aplicará o desconto se houver promoção
                                on_click=callback_adicionar_estoque,
                                args=(produto_id_selecionado, nome_produto, quantidade_input, preco_unitario_input, custo_unit, estoque_disp),
                                help="Adicionar Item do Estoque à Lista de Venda"
                            ):
                                st.rerun()
                        
                    
                    if st.button("Limpar Lista", key="limpar_lista_button", type="secondary", use_container_width=True, help="Limpa todos os produtos da lista de venda"):
                        st.session_state.lista_produtos = []
                        st.rerun()
            
            valor_input_manual = st.number_input(
                "Valor Total (R$)", 
                value=valor_calculado if valor_calculado > 0.0 else default_valor,
                min_value=0.01, 
                format="%.2f",
                disabled=(valor_calculado > 0.0), 
                key="input_valor_entrada"
            )
            valor_final_movimentacao = valor_calculado if valor_calculado > 0.0 else valor_input_manual

            status_selecionado = st.radio(
                "Status", 
                ["Realizada", "Pendente"], 
                index=0 if default_status == "Realizada" else 1, 
                key="input_status_global",
                disabled=edit_mode
            )

            
        else: # Tipo é Saída
            st.markdown("#### Opções de Saída")
            
            if not edit_mode:
                is_recorrente = st.checkbox("🔄 Cadastrar como Despesa Recorrente (Parcelas)", key="input_is_recorrente")
            
            default_select_index = 0
            custom_desc_default = ""
            
            if default_categoria in CATEGORIAS_SAIDA:
                default_select_index = CATEGORIAS_SAIDA.index(default_categoria)
            elif default_categoria.startswith("Outro: "):
                default_select_index = CATEGORIAS_SAIDA.index("Outro/Diversos") if "Outro/Diversos" in CATEGORIAS_SAIDA else 0
                custom_desc_default = default_categoria.replace("Outro: ", "")
            
            st.markdown("#### ⚙️ Centro de Custo (Saída)")
            categoria_selecionada = st.selectbox("Categoria de Gasto", 
                                                    CATEGORIAS_SAIDA, 
                                                    index=default_select_index,
                                                    key="input_categoria_saida",
                                                    disabled=is_recorrente and not edit_mode)

            if categoria_selecionada == "Outro/Diversos" and not (is_recorrente and not edit_mode):
                descricao_personalizada = st.text_input("Especifique o Gasto", 
                                                        value=custom_desc_default, 
                                                        key="input_custom_category")
                if descricao_personalizada:
                    categoria_selecionada = f"Outro: {descricao_personalizada}"
                    
            if is_recorrente and not edit_mode:
                st.markdown("##### 🧾 Detalhes da Recorrência")
                
                nome_despesa_recorrente = st.text_input("Nome da Despesa Recorrente (Ex: Aluguel, Financiamento)", 
                                                        value=default_cliente if default_cliente else "", 
                                                        key="input_nome_despesa_recorrente")
                
                col_rec1, col_rec2 = st.columns(2)
                with col_rec1:
                    num_parcelas = st.number_input("Quantidade de Parcelas", min_value=1, value=12, step=1, key="input_num_parcelas")
                with col_rec2:
                    valor_parcela = st.number_input("Valor de Cada Parcela (R$)", min_value=0.01, format="%.2f", value=default_valor, key="input_valor_parcela")
                
                data_primeira_parcela = st.date_input("Data de Vencimento da 1ª Parcela", 
                                                      value=date.today().replace(day=1) + timedelta(days=32),
                                                      key="input_data_primeira_parcela")
                
                st.checkbox("🚩 Despesa Fixa (Terá avisos mensais no painel)", value=True, disabled=True)
                
                valor_final_movimentacao = float(valor_parcela)
                
                status_selecionado = "Pendente" 
                st.caption(f"Status forçado para **Pendente**. Serão geradas {int(num_parcelas)} parcelas de R$ {valor_final_movimentacao:,.2f}.")
                
            else:
                status_selecionado = st.radio(
                    "Status", 
                    ["Realizada", "Pendente"], 
                    index=0 if default_status == "Realizada" else 1, 
                    key="input_status_global",
                    disabled=edit_mode
                )

                valor_input_manual = st.number_input(
                    "Valor (R$)", 
                    value=default_valor, 
                    min_value=0.01, 
                    format="%.2f", 
                    key="input_valor_saida"
                )
                valor_final_movimentacao = valor_input_manual


        data_pagamento_final = None 

        if status_selecionado == "Pendente" and not (is_recorrente and not edit_mode):
            data_prevista_existe = pd.notna(default_data_pagamento) and (default_data_pagamento is not None)
            st.markdown("##### 🗓️ Previsão de Pagamento")
            data_status_opcoes = ["Com Data Prevista", "Sem Data Prevista"]
            data_status_key = "input_data_status_previsto_global" 
            
            default_data_status_index = 0
            if edit_mode and default_status == "Pendente":
                data_status_previsto_str = "Com Data Prevista" if data_prevista_existe else "Sem Data Prevista"
                default_data_status_index = data_status_opcoes.index(data_status_previsto_str) if data_status_previsto_str in data_status_opcoes else 0
            elif data_status_key in st.session_state:
                default_data_status_index = data_status_opcoes.index(st.session_state[data_status_key]) if st.session_state[data_status_key] in data_status_opcoes else 0


            data_status_selecionado_previsto = st.radio(
                "Essa pendência tem data prevista?",
                options=data_status_opcoes,
                index=default_data_status_index,
                key=data_status_key, 
                horizontal=True,
                disabled=edit_mode and default_status == "Pendente" and data_prevista_existe
            )
            
            if data_status_selecionado_previsto == "Com Data Prevista":
                prev_date_value = default_data_pagamento if data_prevista_existe and edit_mode else date.today() 
                
                data_prevista_pendente = st.date_input(
                    "Selecione a Data Prevista", 
                    value=prev_date_value, 
                    key="input_data_pagamento_prevista_global"
                )
                data_pagamento_final = data_prevista_pendente
            else:
                data_pagamento_final = None
        
        elif status_selecionado == "Pendente" and is_recorrente and not edit_mode:
            data_pagamento_final = data_primeira_parcela
            st.markdown(f"##### 🗓️ 1ª Parcela Vence em: **{data_pagamento_final.strftime('%d/%m/%Y')}**")

        with st.form("form_movimentacao_sidebar", clear_on_submit=not edit_mode):
            
            loja_selecionada = st.selectbox("Loja Responsável", 
                                                 LOJAS_DISPONIVEIS, 
                                                 index=LOJAS_DISPONIVEIS.index(default_loja) if default_loja in LOJAS_DISPONIVEIS else 0,
                                                 key="input_loja_form",
                                                 disabled=is_recorrente and not edit_mode)
                                                 
            data_input = st.date_input("Data da Transação (Lançamento)", value=default_data, key="input_data_form", disabled=is_recorrente and not edit_mode)
            
            default_cliente_form = nome_despesa_recorrente if is_recorrente and not edit_mode else default_cliente
            
            cliente = st.text_input("Nome do Cliente (ou Descrição)", 
                                    value=default_cliente_form, 
                                    key="input_cliente_form",
                                    disabled=is_recorrente and not edit_mode)
                                    
            forma_pagamento = st.selectbox("Forma de Pagamento", 
                                                 FORMAS_PAGAMENTO, 
                                                 index=FORMAS_PAGAMENTO.index(default_forma) if default_forma in FORMAS_PAGAMENTO else 0,
                                                 key="input_forma_pagamento_form",
                                                 disabled=status_selecionado == "Pendente" and not edit_mode)

            if status_selecionado == "Realizada":
                 data_pagamento_final = data_input
            elif status_selecionado == "Pendente" and data_pagamento_final is None:
                forma_pagamento = "Pendente" 
            elif status_selecionado == "Pendente" and is_recorrente:
                 forma_pagamento = "Pendente" 
            
            st.caption(f"Valor Final da Movimentação: R$ {valor_final_movimentacao:,.2f}")


            if edit_mode:
                col_save, col_cancel = st.columns(2)
                with col_save:
                    enviar = st.form_submit_button("💾 Salvar", type="primary", use_container_width=True, help="Salvar Edição")
                with col_cancel:
                    cancelar = st.form_submit_button("❌ Cancelar", type="secondary", use_container_width=True, help="Cancelar Edição")
            else:
                label_btn = "Adicionar Recorrência e Salvar" if is_recorrente else "Adicionar e Salvar"
                enviar = st.form_submit_button(label_btn, type="primary", use_container_width=True, help=label_btn)
                cancelar = False 

            if enviar:
                if valor_final_movimentacao <= 0 and not is_recorrente:
                    st.error("O valor deve ser maior que R$ 0,00.")
                elif valor_parcela <= 0 and is_recorrente:
                    st.error("O valor da parcela deve ser maior que R$ 0,00.")
                elif tipo == "Saída" and not is_recorrente and categoria_selecionada == "Outro/Diversos": 
                    st.error("Por favor, especifique o 'Outro/Diversos' para Saída.")
                elif is_recorrente and not edit_mode and not nome_despesa_recorrente:
                    st.error("O nome da Despesa Recorrente é obrigatório.")
                else:
                    valor_armazenado = valor_final_movimentacao if tipo == "Entrada" else -valor_final_movimentacao
                    
                    if edit_mode:
                        original_row = df_dividas.loc[st.session_state.edit_id]
                        if original_row["Status"] == "Realizada" and status_selecionado == "Pendente" and original_row["Tipo"] == "Entrada":
                            try:
                                produtos_vendidos_antigos = ast.literal_eval(original_row['Produtos Vendidos'])
                                for item in produtos_vendidos_antigos:
                                    if item.get("Produto_ID"): ajustar_estoque(item["Produto_ID"], item["Quantidade"], "creditar")
                            except: pass
                            
                        elif original_row["Status"] == "Realizada" and status_selecionado == "Realizada" and original_row["Tipo"] == "Entrada":
                            try:
                                produtos_vendidos_antigos = ast.literal_eval(original_row['Produtos Vendidos'])
                                for item in produtos_vendidos_antigos:
                                    if item.get("Produto_ID"): ajustar_estoque(item["Produto_ID"], item["Quantidade"], "creditar")
                            except: pass
                            
                            if produtos_vendidos_json:
                                produtos_vendidos_novos = json.loads(produtos_vendidos_json)
                                for item in produtos_vendidos_novos:
                                    if item.get("Produto_ID"): ajustar_estoque(item["Produto_ID"], item["Quantidade"], "debitar")
                            
                            if salvar_produtos_no_github(st.session_state.produtos, "Ajuste de estoque por edição de venda"):
                                inicializar_produtos.clear()
                                st.cache_data.clear()
                                
                        elif not edit_mode and tipo == "Entrada" and status_selecionado == "Realizada" and st.session_state.lista_produtos:
                            if produtos_vendidos_json:
                                produtos_vendidos_novos = json.loads(produtos_vendidos_json)
                                for item in produtos_vendidos_novos:
                                    if item.get("Produto_ID"): ajustar_estoque(item["Produto_ID"], item["Quantidade"], "debitar")
                            if salvar_produtos_no_github(st.session_state.produtos, "Débito de estoque por nova venda"):
                                inicializar_produtos.clear()
                                st.cache_data.clear()

                    novas_movimentacoes = []
                    if is_recorrente and not edit_mode:
                        num_parcelas_int = int(num_parcelas)
                        valor_parcela_float = float(valor_parcela)
                        recorrencia_seed = f"{nome_despesa_recorrente}{data_primeira_parcela}{num_parcelas_int}{valor_parcela_float}{categoria_selecionada}{loja_selecionada}"
                        recorrencia_id = hashlib.md5(recorrencia_seed.encode('utf-8')).hexdigest()[:10]
                        
                        for i in range(1, num_parcelas_int + 1):
                            data_vencimento_parcela = add_months(data_primeira_parcela, i - 1)
                            nova_linha_parcela = {
                                "Data": data_input, 
                                "Loja": loja_selecionada, 
                                "Cliente": f"{nome_despesa_recorrente} (Parc. {i}/{num_parcelas_int})",
                                "Valor": -valor_parcela_float,
                                "Forma de Pagamento": "Pendente", 
                                "Tipo": "Saída",
                                "Produtos Vendidos": "",
                                "Categoria": categoria_selecionada,
                                "Status": "Pendente",
                                "Data Pagamento": data_vencimento_parcela, 
                                "RecorrenciaID": recorrencia_id
                            }
                            novas_movimentacoes.append(nova_linha_parcela)
                        
                        st.session_state.df = pd.concat([df_dividas, pd.DataFrame(novas_movimentacoes)], ignore_index=True)
                        commit_msg = f"Cadastro de Dívida Recorrente ({num_parcelas_int} parcelas)"
                        
                    else:
                        nova_linha_data = {
                            "Data": data_input,
                            "Loja": loja_selecionada, 
                            "Cliente": cliente,
                            "Valor": valor_armazenado, 
                            "Forma de Pagamento": forma_pagamento,
                            "Tipo": tipo,
                            "Produtos Vendidos": produtos_vendidos_json,
                            "Categoria": categoria_selecionada,
                            "Status": status_selecionado, 
                            "Data Pagamento": data_pagamento_final,
                            "RecorrenciaID": ""
                        }
                        
                        if edit_mode:
                            st.session_state.df.loc[st.session_state.edit_id] = pd.Series(nova_linha_data)
                            commit_msg = COMMIT_MESSAGE_EDIT
                        else:
                            st.session_state.df = pd.concat([df_dividas, pd.DataFrame([nova_linha_data])], ignore_index=True)
                            commit_msg = COMMIT_MESSAGE
                    
                    salvar_dados_no_github(st.session_state.df, commit_msg)
                    st.session_state.edit_id = None
                    st.session_state.lista_produtos = [] 
                    st.cache_data.clear()
                    st.rerun()


            if cancelar:
                st.session_state.edit_id = None
                st.session_state.lista_produtos = []
                st.rerun()


    tab_mov, tab_rel = st.tabs(["📋 Movimentações e Resumo", "📈 Relatórios e Filtros"])


    with tab_mov:
        hoje = date.today()
        primeiro_dia_mes = hoje.replace(day=1)
        if hoje.month == 12: proximo_mes = hoje.replace(year=hoje.year + 1, month=1, day=1)
        else: proximo_mes = hoje.replace(month=hoje.month + 1, day=1)
        ultimo_dia_mes = proximo_mes - timedelta(days=1)

        df_mes_atual_realizado = df_exibicao[
            (df_exibicao["Data"] >= primeiro_dia_mes) &
            (df_exibicao["Data"] <= ultimo_dia_mes) &
            (df_exibicao["Status"] == "Realizada")
        ]
        
        st.subheader(f"📊 Resumo Financeiro Geral - Mês de {primeiro_dia_mes.strftime('%m/%Y')}")

        total_entradas, total_saidas, saldo = calcular_resumo(df_mes_atual_realizado)

        col1, col2, col3 = st.columns(3)
        col1.metric("Total de Entradas", f"R$ {total_entradas:,.2f}")
        col2.metric("Total de Saídas", f"R$ {total_saidas:,.2f}")
        delta_saldo = f"R$ {saldo:,.2f}"
        col3.metric("💼 Saldo Final (Realizado)", f"R$ {saldo:,.2f}", delta=delta_saldo if saldo != 0 else None, delta_color="normal")

        st.markdown("---")
        
        hoje_date = date.today()
        df_pendente_alerta = df_exibicao[
            (df_exibicao["Status"] == "Pendente") & 
            (pd.notna(df_exibicao["Data Pagamento"]))
        ].copy()

        df_pendente_alerta["Data Pagamento"] = pd.to_datetime(df_pendente_alerta["Data Pagamento"], errors='coerce').dt.date
        df_pendente_alerta.dropna(subset=["Data Pagamento"], inplace=True)
        
        df_vencidas = df_pendente_alerta[
            df_pendente_alerta["Data Pagamento"] <= hoje_date
        ]

        contas_a_receber_vencidas = df_vencidas[df_vencidas["Tipo"] == "Entrada"]["Valor"].abs().sum()
        contas_a_pagar_vencidas = df_vencidas[df_vencidas["Tipo"] == "Saída"]["Valor"].abs().sum()
        
        num_receber = df_vencidas[df_vencidas["Tipo"] == "Entrada"].shape[0]
        num_pagar = df_vencidas[df_vencidas["Tipo"] == "Saída"].shape[0] 

        if num_receber > 0 or num_pagar > 0:
            alert_message = "### ⚠️ DÍVIDAS PENDENTES VENCIDAS (ou Vencendo Hoje)!"
            if num_receber > 0:
                alert_message += f"\n\n💸 **{num_receber} Contas a Receber** (Total: R$ {contas_a_receber_vencidas:,.2f})"
            if num_pagar > 0:
                alert_message += f"\n\n💰 **{num_pagar} Contas a Pagar** (Total: R$ {contas_a_pagar_vencidas:,.2f})"
            
            st.error(alert_message)
            st.caption("Acesse a aba **Relatórios e Filtros > Dívidas Pendentes** para concluir essas transações.")
            st.markdown("---")
        
        st.subheader(f"🏠 Resumo Rápido por Loja (Mês de {primeiro_dia_mes.strftime('%m/%Y')} - Realizado)")
        
        df_resumo_loja = df_mes_atual_realizado.groupby('Loja')['Valor'].agg(['sum', lambda x: x[x >= 0].sum(), lambda x: abs(x[x < 0].sum())]).reset_index()
        df_resumo_loja.columns = ['Loja', 'Saldo', 'Entradas', 'Saídas']
        
        if not df_resumo_loja.empty:
            cols_loja = st.columns(min(4, len(df_resumo_loja.index))) 
            
            for i, row in df_resumo_loja.iterrows():
                if i < len(cols_loja):
                    cols_loja[i].metric(
                        label=f"{row['Loja']}",
                        value=f"R$ {row['Saldo']:,.2f}",
                        delta=f"E: R$ {row['Entradas']:,.2f} | S: R$ {row['Saídas']:,.2f}",
                        delta_color="off" 
                    )
        else:
            st.info("Nenhuma movimentação REALIZADA registrada neste mês.")
        
        st.markdown("---")
        
        st.subheader("📋 Tabela de Movimentações")
        
        if df_exibicao.empty:
            st.info("Nenhuma movimentação registrada ainda.")
        else:
            col_f1, col_f2, col_f3 = st.columns(3)
            
            min_date = df_exibicao["Data"].min() if pd.notna(df_exibicao["Data"].min()) else hoje
            max_date = df_exibicao["Data"].max() if pd.notna(df_exibicao["Data"].max()) else hoje
            
            with col_f1:
                filtro_data_inicio = st.date_input("De", value=min_date, key="quick_data_ini")
            with col_f2:
                filtro_data_fim = st.date_input("Até", value=max_date, key="quick_data_fim")
            with col_f3:
                tipos_unicos = ["Todos"] + df_exibicao["Tipo"].unique().tolist()
                filtro_tipo = st.selectbox("Filtrar por Tipo", options=tipos_unicos, key="quick_tipo")

            df_filtrado_rapido = df_exibicao.copy()
            
            df_filtrado_rapido = df_filtrado_rapido[
                (df_filtrado_rapido["Data"] >= filtro_data_inicio) &
                (df_filtrado_rapido["Data"] <= filtro_data_fim)
            ]

            if filtro_tipo != "Todos":
                df_filtrado_rapido = df_filtrado_rapido[df_filtrado_rapido["Tipo"] == filtro_tipo]

            df_para_mostrar = df_filtrado_rapido.copy()
            df_para_mostrar['Produtos Resumo'] = df_para_mostrar['Produtos Vendidos'].apply(format_produtos_resumo)
            
            colunas_tabela = ['ID Visível', 'Data', 'Loja', 'Cliente', 'Categoria', 'Valor', 'Forma de Pagamento', 'Tipo', 'Status', 'Data Pagamento', 'Produtos Resumo', 'Saldo Acumulado']
            
            df_styling = df_para_mostrar[colunas_tabela + ['Cor_Valor']].copy()
            styled_df = df_styling.style.apply(highlight_value, axis=1)
            styled_df = styled_df.hide(subset=['Cor_Valor'], axis=1)

            st.dataframe(
                styled_df,
                use_container_width=True,
                column_config={
                    "Valor": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f"),
                    "Saldo Acumulado": st.column_config.NumberColumn("Saldo Acumulado (R$)", format="R$ %.2f"),
                    "Produtos Resumo": st.column_config.TextColumn("Detalhe dos Produtos"),
                    "Categoria": "Categoria (C. Custo)",
                    "Data Pagamento": st.column_config.DateColumn("Data Pagt. Previsto/Real", format="DD/MM/YYYY")
                },
                height=400,
                selection_mode='disabled',
                key='movimentacoes_table_styled_display_only'
            )


            st.markdown("---")
            st.markdown("### Operações de Edição e Exclusão")
            
            if df_para_mostrar.empty:
                st.info("Nenhuma movimentação disponível para edição/exclusão com os filtros aplicados.")
            else:
                opcoes_movimentacao_operacao = {
                    f"ID {row['ID Visível']} | {row['Data'].strftime('%d/%m/%Y')} | {row['Cliente']} | R$ {abs(row['Valor']):,.2f}": row['original_index']
                    for index, row in df_para_mostrar.iterrows()
                }
                opcoes_keys = ["Selecione uma movimentação..."] + list(opcoes_movimentacao_operacao.keys())

                movimentacao_selecionada_str = st.selectbox(
                    "Selecione o item para Editar ou Excluir:",
                    options=opcoes_keys,
                    index=0,
                    key="select_movimentacao_operacao_lc"
                )

                original_idx_selecionado = opcoes_movimentacao_operacao.get(movimentacao_selecionada_str)
                item_selecionado_str = movimentacao_selecionada_str

                if original_idx_selecionado is not None and movimentacao_selecionada_str != "Selecione uma movimentação...":
                    row = df_exibicao[df_exibicao['original_index'] == original_idx_selecionado].iloc[0]

                    if row['Tipo'] == 'Entrada' and row['Produtos Vendidos'] and pd.notna(row['Produtos Vendidos']):
                        st.markdown("#### Detalhes dos Produtos Selecionados")
                        try:
                            try:
                                produtos = json.loads(row['Produtos Vendidos'])
                            except json.JSONDecodeError:
                                produtos = ast.literal_eval(row['Produtos Vendidos'])

                            df_detalhe = pd.DataFrame(produtos)
                            for col in ['Quantidade', 'Preço Unitário', 'Custo Unitário']:
                                df_detalhe[col] = pd.to_numeric(df_detalhe[col], errors='coerce').fillna(0)

                            df_detalhe['Total Venda'] = df_detalhe['Quantidade'] * df_detalhe['Preço Unitário']
                            df_detalhe['Total Custo'] = df_detalhe['Quantidade'] * df_detalhe['Custo Unitário']
                            df_detalhe['Lucro Bruto'] = df_detalhe['Total Venda'] - df_detalhe['Total Custo']

                            st.dataframe(
                                df_detalhe,
                                hide_index=True,
                                use_container_width=True,
                                column_config={
                                    "Produto": "Produto",
                                    "Quantidade": st.column_config.NumberColumn("Qtd"),
                                    "Preço Unitário": st.column_config.NumberColumn("Preço Un.", format="R$ %.2f"),
                                    "Custo Unitário": st.column_config.NumberColumn("Custo Un.", format="R$ %.2f"),
                                    "Total Venda": st.column_config.NumberColumn("Total Venda", format="R$ %.2f"),
                                    "Total Custo": st.column_config.NumberColumn("Total Custo", format="R$ %.2f"),
                                    "Lucro Bruto": st.column_config.NumberColumn("Lucro Bruto", format="R$ %.2f", help="Venda - Custo")
                                },
                                column_order=("Produto", "Quantidade", "Preço Unitário", "Custo Unitário", "Total Venda", "Total Custo", "Lucro Bruto")
                            ) 
                        
                        except Exception as e:
                            st.error(f"Erro ao processar detalhes dos produtos: {e}")

                        st.markdown("---")


                    col_op_1, col_op_2 = st.columns(2)

                    if col_op_1.button(f"✏️ Editar: {item_selecionado_str}", key=f"edit_mov_{original_idx_selecionado}", use_container_width=True, type="secondary"):
                        st.session_state.edit_id = original_idx_selecionado
                        st.session_state.lista_produtos = []
                        st.rerun()

                    if col_op_2.button(f"🗑️ Excluir: {item_selecionado_str}", key=f"del_mov_{original_idx_selecionado}", use_container_width=True, type="primary"):
                        if row['Status'] == 'Realizada' and row['Tipo'] == 'Entrada':
                            try:
                                produtos_vendidos_antigos = ast.literal_eval(row['Produtos Vendidos'])
                                for item in produtos_vendidos_antigos:
                                    if item.get("Produto_ID"): ajustar_estoque(item["Produto_ID"], item["Quantidade"], "creditar")
                                if salvar_produtos_no_github(st.session_state.produtos, "Reversão de estoque por exclusão de venda"):
                                    inicializar_produtos.clear()
                            except: pass

                        st.session_state.df = st.session_state.df.drop(row['original_index'], errors='ignore')

                        if salvar_dados_no_github(st.session_state.df, COMMIT_MESSAGE_DELETE):
                            st.cache_data.clear()
                            st.rerun()
                else:
                    st.info("Selecione uma movimentação no menu acima para ver detalhes e opções de edição/exclusão.")


    with tab_rel:
        st.subheader("📈 Relatórios Anuais e Mensais")

        df_anual = df_exibicao[df_exibicao['Status'] == 'Realizada'].copy()
        df_anual['Ano'] = pd.to_datetime(df_anual['Data'], errors='coerce').dt.year.fillna(0).astype(int)
        df_anual = df_anual[df_anual['Ano'] > 0]

        if not df_anual.empty:
            df_resumo_anual = df_anual.groupby('Ano')['Valor'].agg(['sum', lambda x: x[x >= 0].sum(), lambda x: abs(x[x < 0].sum())]).reset_index()
            df_resumo_anual.columns = ['Ano', 'Saldo', 'Entradas', 'Saídas']
            df_resumo_anual.sort_values(by='Ano', ascending=False, inplace=True)

            st.markdown("##### Resumo Anual (Realizado)")
            st.dataframe(df_resumo_anual, hide_index=True, use_container_width=True)

            fig_anual = px.bar(df_resumo_anual, x='Ano', y=['Entradas', 'Saídas'], title="Entradas vs. Saídas por Ano", labels={'value': 'Valor (R$)', 'variable': 'Tipo'}, barmode='group')
            st.plotly_chart(fig_anual, use_container_width=True)
            
        else: st.info("Dados insuficientes para gerar relatório anual.")

        st.markdown("---")
        
        st.subheader("🚩 Dívidas Pendentes (A Pagar e A Receber)")
        
        df_pendentes = df_exibicao[df_exibicao["Status"] == "Pendente"].copy()
        
        if df_pendentes.empty:
            st.info("Parabéns! Não há dívidas pendentes registradas.")
        else:
            df_pendentes["Data Pagamento"] = pd.to_datetime(df_pendentes["Data Pagamento"], errors='coerce').dt.date
            df_pendentes_ordenado = df_pendentes.sort_values(by=["Data Pagamento", "Tipo", "Data"], ascending=[True, True, True]).reset_index(drop=True)
            df_pendentes_ordenado['Dias Até/Atraso'] = df_pendentes_ordenado['Data Pagamento'].apply(
                lambda x: (x - hoje_date).days if pd.notna(x) else float('inf') 
            )
            
            total_receber = df_pendentes_ordenado[df_pendentes_ordenado["Tipo"] == "Entrada"]["Valor"].abs().sum()
            total_pagar = df_pendentes_ordenado[df_pendentes_ordenado["Tipo"] == "Saída"]["Valor"].abs().sum()
            
            col_res_1, col_res_2 = st.columns(2)
            col_res_1.metric("Total a Receber", f"R$ {total_receber:,.2f}")
            col_res_2.metric("Total a Pagar", f"R$ {total_pagar:,.2f}")
            
            st.markdown("---")
            
            def highlight_pendentes(row):
                dias = row['Dias Até/Atraso']
                if dias < 0: return ['background-color: #fcece9' if col in ['Status', 'Data Pagamento'] else '' for col in row.index]
                elif dias <= 7: return ['background-color: #fffac9' if col in ['Status', 'Data Pagamento'] else '' for col in row.index]
                return ['' for col in row.index]

            with st.form("form_concluir_divida"):
                st.markdown("##### ✅ Concluir Dívida Pendente")
                
                opcoes_pendentes = {
                    f"ID {row['ID Visível']} | {row['Tipo']} | R$ {row['Valor'] if row['Tipo'] == 'Entrada' else abs(row['Valor']):,.2f} | Venc.: {row['Data Pagamento'].strftime('%d/%m/%Y') if pd.notna(row['Data Pagamento']) else 'S/ Data'} | {row['Cliente']}": row['original_index']
                    for index, row in df_pendentes_ordenado.iterrows()
                }
                opcoes_keys = [""] + list(opcoes_pendentes.keys())
                
                divida_selecionada_str = st.selectbox("Selecione a Dívida para Concluir:", options=opcoes_keys, key="select_divida_concluir")
                
                original_idx_concluir = opcoes_pendentes.get(divida_selecionada_str)

                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    data_conclusao = st.date_input("Data Real da Conclusão", value=hoje_date, key="data_conclusao_divida")
                with col_c2:
                    forma_pagt_concluir = st.selectbox("Forma de Pagamento (Realizada)", FORMAS_PAGAMENTO, key="forma_pagt_concluir")

                concluir = st.form_submit_button("✅ Concluir Selecionada", use_container_width=True, type="primary")

                if concluir and original_idx_concluir is not None:
                    idx_original = df_pendentes.loc[df_pendentes['original_index'] == original_idx_concluir].index[0]
                    row_data = st.session_state.df.loc[idx_original].copy()
                    
                    st.session_state.df.loc[idx_original, 'Status'] = 'Realizada'
                    st.session_state.df.loc[idx_original, 'Data'] = data_conclusao
                    st.session_state.df.loc[idx_original, 'Data Pagamento'] = data_conclusao
                    st.session_state.df.loc[idx_original, 'Forma de Pagamento'] = forma_pagt_concluir
                    
                    if row_data["Tipo"] == "Entrada" and row_data["Produtos Vendidos"]:
                        try:
                            produtos_vendidos = ast.literal_eval(row_data['Produtos Vendidos'])
                            for item in produtos_vendidos:
                                if item.get("Produto_ID"): ajustar_estoque(item["Produto_ID"], item["Quantidade"], "debitar")
                            if salvar_produtos_no_github(st.session_state.produtos, f"Débito de estoque por conclusão de venda {row_data['Cliente']}"): inicializar_produtos.clear()
                        except: st.warning("⚠️ Venda concluída, mas falha no débito do estoque (JSON inválido).")
                    
                    if salvar_dados_no_github(st.session_state.df, COMMIT_MESSAGE_DEBT_REALIZED):
                        st.cache_data.clear()
                        st.rerun()
                elif concluir: st.warning("Selecione uma dívida válida para concluir.")

            st.markdown("---")

            st.markdown("##### Tabela Detalhada de Dívidas Pendentes")
            df_para_mostrar_pendentes = df_pendentes_ordenado.copy()
            df_para_mostrar_pendentes['Status Vencimento'] = df_para_mostrar_pendentes['Dias Até/Atraso'].apply(
                lambda x: f"Atrasado {-x} dias" if x < 0 else (f"Vence em {x} dias" if x > 0 else "Vence Hoje")
            )
            df_styling_pendentes = df_para_mostrar_pendentes.style.apply(highlight_pendentes, axis=1)

            st.dataframe(df_styling_pendentes, use_container_width=True, hide_index=True)


# ==============================================================================
# ESTRUTURA PRINCIPAL E NAVEGAÇÃO SUPERIOR
# ==============================================================================

PAGINAS = {
    "Home": homepage,
    "Livro Caixa": livro_caixa,
    "Produtos": gestao_produtos,
    "Promoções": gestao_promocoes, # NOVA PÁGINA
    "Histórico de Compra": historico_compras
}

if "pagina_atual" not in st.session_state:
    st.session_state.pagina_atual = "Home"


# --- Renderiza o Header e a Navegação no Topo ---

def render_header():
    """Renderiza o header customizado com a navegação em botões."""
    
    col_logo, col_nav = st.columns([1, 4])
    
    with col_logo:
        # AQUI É A LINHA CORRIGIDA: usa o placeholder que é uma URL válida.
        st.image(LOGO_DOCEBELLA_URL, width=150)
        
    with col_nav:
        cols_botoes = st.columns([1] * len(PAGINAS))
        
        # Cria a lista de páginas na ordem desejada
        paginas_ordenadas = ["Home", "Livro Caixa", "Produtos", "Promoções", "Histórico de Compra"]
        
        for i, nome in enumerate(paginas_ordenadas):
            if nome in PAGINAS:
                is_active = st.session_state.pagina_atual == nome
                
                # Ajusta o estilo do botão para parecer um item de navegação
                button_style = "color: white; font-weight: bold; border: none; background: none; cursor: pointer; padding: 10px 5px;"
                if is_active:
                    button_style += "border-bottom: 3px solid #FFCDD2; /* Linha de destaque rosa claro */"
                
                # Usando st.markdown e st.button em combinação para obter o efeito de botão customizado.
                if cols_botoes[i].button(nome, key=f"nav_{nome}", use_container_width=True, help=f"Ir para {nome}"):
                    st.session_state.pagina_atual = nome
                    st.rerun()

# O Streamlit nativamente não permite HTML/Markdown fora do corpo principal
# Simulamos o Header customizado no topo da página
with st.container():
    st.markdown('<div class="header-container">', unsafe_allow_html=True)
    render_header()
    st.markdown('</div>', unsafe_allow_html=True)


# --- RENDERIZAÇÃO DO CONTEÚDO DA PÁGINA ---
PAGINAS[st.session_state.pagina_atual]()

# --- Exibe/Oculta o Sidebar do Formulário ---
# A sidebar só é necessária para o formulário de Adicionar/Editar Movimentação (Livro Caixa)
if st.session_state.pagina_atual != "Livro Caixa":
    st.sidebar.empty() # Remove o conteúdo do sidebar se não for Livro Caixa




