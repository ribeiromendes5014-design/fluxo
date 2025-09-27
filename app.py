import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
import requests
from requests.exceptions import ConnectionError, RequestException # Importa exceções de rede
from io import StringIO
import io, os 
import json
import hashlib
import ast
import plotly.express as px
import base64 

# Importa a biblioteca PyGithub para gerenciamento de persistência
try:
    from github import Github 
except ImportError:
    # Fallback para ambientes que não permitem o import de PyGithub, mas a persistência falhará.
    class Github:
        def __init__(self, token): pass
        def get_repo(self, repo_name): return self 
        def update_file(self, path, msg, content, sha, branch): pass
        def create_file(self, path, msg, content, branch): pass

# =====================================
# Funções auxiliares (CORRIGIDO: Troca API ZXing por WebQR - JSON)
# =====================================

def ler_codigo_barras_api(image_bytes):
    """
    Tenta decodificar usando WebQR (QR Codes).
    Se falhar, usa ZXing (QR + códigos de barras lineares).
    Exibe o retorno cru das APIs para debug.
    """
    codigos = []

    # 1. Tenta com WebQR
    try:
        URL_DECODER_WEBQR = "https://api.qrserver.com/v1/read-qr-code/"
        files = {"file": ("barcode.png", image_bytes, "image/png")} 
        response = requests.post(URL_DECODER_WEBQR, files=files, timeout=30)

        if response.status_code == 200:
            data = response.json()
            if data and isinstance(data, list) and data[0].get('symbol'):
                for symbol in data[0]['symbol']:
                    if symbol['data'] is not None:
                        codigos.append(symbol['data'].strip())

            if 'streamlit' in globals():
                st.write("📡 Debug WebQR (resposta JSON):", data)

    except Exception as e:
        if 'streamlit' in globals():
            st.error(f"❌ Erro WebQR: {e}")

    # 2. Se nada foi encontrado → tenta ZXing
    if not codigos:
        try:
            url = "https://zxing.org/w/decode.jspx"
            files = {"file": ("barcode.png", image_bytes, "image/png")}
            resp = requests.post(url, files=files, timeout=30)

            if resp.status_code == 200:
                if 'streamlit' in globals():
                    st.write("📡 Debug ZXing (resposta HTML):")
                    st.code(resp.text[:1000])  # mostra só os primeiros 1000 caracteres p/ debug

                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "html.parser")
                pre = soup.find("pre")
                if pre:
                    codigos = [pre.get_text(strip=True)]

        except Exception as e:
            if 'streamlit' in globals():
                st.error(f"❌ Erro ZXing: {e}")

    if not codigos and 'streamlit' in globals():
        st.warning("⚠️ Nenhum código decodificado (verifique a imagem e o log acima).")

    return codigos




# ==================== CONFIGURAÇÕES DO APLICATIVO E CONSTANTES ====================
# As variáveis de token e repositório são carregadas dos segredos do Streamlit.
# Padronizando variáveis para seguir o fluxo do ff.py
try:
    TOKEN = st.secrets["GITHUB_TOKEN"]
    OWNER = st.secrets["REPO_OWNER"]
    REPO_NAME = st.secrets["REPO_NAME"]
    CSV_PATH = st.secrets["CSV_PATH"] # Caminho do livro caixa (contas_a_pagar_receber.csv)
    BRANCH = st.secrets.get("BRANCH", "main")
    
    # Mantendo variáveis auxiliares para compatibilidade externa
    GITHUB_TOKEN = TOKEN
    GITHUB_REPO = f"{OWNER}/{REPO_NAME}"
    GITHUB_BRANCH = BRANCH
    
except KeyError:
    # Fallback para execução local/debug (o salvamento no GitHub NÃO funcionará)
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
URL_PRODUTOS = URL_BASE_REPOS + ARQ_PRODUTOS
ARQ_LOCAL = "livro_caixa.csv"
PATH_DIVIDAS = CSV_PATH # Caminho do livro caixa

# Mensagens de Commit (do ff.py)
COMMIT_MESSAGE = "Atualiza livro caixa via Streamlit (com produtos/categorias)"
COMMIT_MESSAGE_DELETE = "Exclui movimentações do livro caixa"
COMMIT_MESSAGE_EDIT = "Edita movimentação via Streamlit"
COMMIT_MESSAGE_DEBT_REALIZED = "Conclui dívidas pendentes"
COMMIT_MESSAGE_PROD = "Atualização automática de estoque/produtos"

# Colunas padrão (do ff.py, com Status e Data Pagamento)
COLUNAS_PADRAO = ["Data", "Loja", "Cliente", "Valor", "Forma de Pagamento", "Tipo", "Produtos Vendidos", "Categoria", "Status", "Data Pagamento"]
COLUNAS_COMPLETAS_PROCESSADAS = COLUNAS_PADRAO + ["ID Visível", "original_index", "Data_dt", "Saldo Acumulado", "Cor_Valor"]


# Constantes para Produto
FATOR_CARTAO = 0.8872 # 1 - Taxa de 11.28% para cálculo do Preço no Cartão

# Constantes Livro Caixa
LOJAS_DISPONIVEIS = ["Doce&bella", "Papelaria", "Fotografia", "Outro"]
CATEGORIAS_SAIDA = ["Aluguel", "Salários/Pessoal", "Marketing/Publicidade", "Fornecedores/Matéria Prima", "Despesas Fixas", "Impostos/Taxas", "Outro/Diversos", "Não Categorizado"]
FORMAS_PAGAMENTO = ["Dinheiro", "Cartão", "PIX", "Transferência", "Outro"]


# ========================================================
# FUNÇÕES DE PERSISTÊNCIA (Adaptadas de ff.py)
# ========================================================

def to_float(valor_str):
    """Converte string com vírgula para float, ou retorna 0.0."""
    try:
        if isinstance(valor_str, (int, float)):
            return float(valor_str)
        return float(str(valor_str).replace(",", ".").strip())
    except:
        return 0.0

def prox_id(df, coluna_id="ID"):
    """Função auxiliar para criar um novo ID sequencial."""
    if df.empty:
        return "1"
    else:
        try:
            return str(pd.to_numeric(df[coluna_id], errors='coerce').fillna(0).astype(int).max() + 1)
        except:
            return str(len(df) + 1)

def hash_df(df):
    """Gera um hash para o DataFrame para detecção de mudanças."""
    df_temp = df.copy()
    for col in df_temp.select_dtypes(include=['datetime64[ns]']).columns:
        df_temp[col] = df_temp[col].astype(str)
    try:
        # Usa um hash mais simples e robusto
        return hashlib.md5(df_temp.to_json().encode('utf-8')).hexdigest()
    except Exception:
        return "error" 

def load_csv_github(url: str) -> pd.DataFrame | None:
    """Carrega um arquivo CSV diretamente do GitHub (URL raw)."""
    try:
        # Usa headers para evitar problemas de cache do GitHub, se possível
        response = requests.get(url)
        response.raise_for_status() # Lança erro para 4xx/5xx status codes
        
        df = pd.read_csv(StringIO(response.text), dtype=str)
        
        # Garante que, se o arquivo for lido, mas estiver quase vazio (apenas cabeçalhos), retorne None
        if df.empty or len(df.columns) < 2:
            return None
        return df
    except Exception:
        return None

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

    # Garante que as colunas padrão existam e preenche novas colunas com ""
    for col in COLUNAS_PADRAO:
        if col not in df.columns:
            # 'Status' padrão é 'Realizada'
            df[col] = "Realizada" if col == "Status" else "" 
            
    # Retorna apenas as colunas padrão na ordem correta
    return df[COLUNAS_PADRAO]

def salvar_dados_no_github(df: pd.DataFrame, commit_message: str):
    """Salva o DataFrame CSV no GitHub e também localmente (backup)."""
    
    # 1. Backup local (Tenta salvar, ignora se falhar)
    try:
        df.to_csv(ARQ_LOCAL, index=False)
    except Exception:
        pass

    # 2. Prepara DataFrame para envio ao GitHub
    df_temp = df.copy()
    
    # Prepara os dados para serem salvos como string (CSV)
    for col_date in ['Data', 'Data Pagamento']:
        if col_date in df_temp.columns:
            df_temp[col_date] = pd.to_datetime(df_temp[col_date], errors='coerce').apply(
                lambda x: x.strftime('%Y-%m-%d') if pd.notnull(x) else ''
            )

    try:
        g = Github(TOKEN)
        repo = g.get_repo(f"{OWNER}/{REPO_NAME}")
        csv_string = df_temp.to_csv(index=False)

        try:
            # Tenta obter o SHA do conteúdo atual
            contents = repo.get_contents(PATH_DIVIDAS, ref=BRANCH)
            # Atualiza o arquivo
            repo.update_file(contents.path, commit_message, csv_string, contents.sha, branch=BRANCH)
            st.success("📁 Livro Caixa salvo (atualizado) no GitHub!")
        except Exception:
            # Cria o arquivo 
            repo.create_file(PATH_DIVIDAS, commit_message, csv_string, branch=BRANCH)
            st.success("📁 Livro Caixa salvo (criado) no GitHub!")

        return True

    except Exception as e:
        st.error(f"❌ Erro ao salvar no GitHub: {e}")
        st.error("Verifique se seu 'GITHUB_TOKEN' tem permissões e se o repositório existe.")
        return False

# ==================== FUNÇÕES DE PROCESSAMENTO DE DADOS (ff.py) ====================

@st.cache_data(show_spinner=False)
def processar_dataframe(df):
    """
    Padroniza o DataFrame para uso na UI: conversão de tipos, cálculo de saldo acumulado e ordenação.
    Retorna o DataFrame processado.
    """
    if df.empty:
        return pd.DataFrame(columns=COLUNAS_COMPLETAS_PROCESSADAS)
        
    df_proc = df.copy()
    
    if 'Categoria' not in df_proc.columns:
        df_proc['Categoria'] = ""
    if 'Status' not in df_proc.columns: 
        df_proc['Status'] = "Realizada"
    if 'Data Pagamento' not in df_proc.columns:
        df_proc['Data Pagamento'] = pd.NaT 

    # Conversão de Valor
    df_proc["Valor"] = pd.to_numeric(df_proc["Valor"], errors="coerce").fillna(0.0)

    # Conversão de Data e Data Pagamento
    df_proc["Data"] = pd.to_datetime(df_proc["Data"], errors='coerce').dt.date
    df_proc["Data_dt"] = pd.to_datetime(df_proc["Data"], errors='coerce') # Data para ordenação
    
    df_proc["Data Pagamento"] = pd.to_datetime(df_proc["Data Pagamento"], errors='coerce').dt.date
    
    # Remove linhas onde a data de transação não pôde ser convertida
    df_proc.dropna(subset=['Data_dt'], inplace=True)
    
    # --- RESETAR O ÍNDICE E CALCULAR SALDO ACUMULADO ---
    
    df_proc = df_proc.reset_index(drop=False) 
    df_proc.rename(columns={'index': 'original_index'}, inplace=True)
    
    df_proc['Saldo Acumulado'] = 0.0 
    
    # Filtra o DataFrame para calcular o Saldo Acumulado APENAS com transações REALIZADAS
    df_realizadas = df_proc[df_proc['Status'] == 'Realizada'].copy()

    if not df_realizadas.empty:
        df_realizadas_sorted_asc = df_realizadas.sort_values(by=['Data_dt', 'original_index'], ascending=[True, True]).reset_index(drop=True)
        df_realizadas_sorted_asc['TEMP_SALDO'] = df_realizadas_sorted_asc['Valor'].cumsum()
        
        df_proc = pd.merge(
            df_proc, 
            df_realizadas_sorted_asc[['original_index', 'TEMP_SALDO']], 
            on='original_index', 
            how='left'
        )
        
        df_proc['Saldo Acumulado'] = df_proc['TEMP_SALDO'].fillna(method='ffill').fillna(0)
        df_proc.drop(columns=['TEMP_SALDO'], inplace=True, errors='ignore')


    # Retorna à ordenação para exibição (Data DESC)
    df_proc = df_proc.sort_values(by="Data_dt", ascending=False).reset_index(drop=True)
    df_proc.insert(0, 'ID Visível', df_proc.index + 1)
    
    
    # Adiciona a coluna de Cor para formatação condicional
    df_proc['Cor_Valor'] = df_proc.apply(lambda row: 'green' if row['Tipo'] == 'Entrada' and row['Valor'] >= 0 else 'red', axis=1)

    return df_proc

def calcular_resumo(df):
    """Calcula e retorna o resumo financeiro (Entradas, Saídas, Saldo) APENAS de transações Realizadas."""
    df_realizada = df[df['Status'] == 'Realizada']
    
    if df_realizada.empty:
        return 0.0, 0.0, 0.0
        
    total_entradas = df_realizada[df_realizada["Tipo"] == "Entrada"]["Valor"].sum()
    total_saidas = abs(df_realizada[df_realizada["Tipo"] == "Saída"]["Valor"].sum()) 
    saldo = df_realizada["Valor"].sum()
    return total_entradas, total_saidas, saldo

# Função para formatar a coluna 'Produtos Vendidos'
def format_produtos_resumo(produtos_json):
    if pd.isna(produtos_json) or produtos_json == "":
        return ""
    
    if produtos_json:
        try:
            produtos = json.loads(produtos_json)
            if not isinstance(produtos, list) or not all(isinstance(p, dict) for p in produtos):
                return "Dados inválidos"

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
                    except ValueError:
                        continue
                        
                lucro = total_venda - total_custo
                lucro_str = f"| Lucro R$ {lucro:,.2f}" if lucro != 0 else ""
                
                return f"{count} item(s): {primeiro}... {lucro_str}"
        except:
            return "Erro na formatação/JSON Inválido"
    return ""

# Função para aplicar o destaque condicional na coluna Valor
def highlight_value(row):
    """Função para aplicar o destaque condicional na coluna Valor."""
    color = row['Cor_Valor']
    return [f'color: {color}' if col == 'Valor' else '' for col in row.index]


# ==============================================================================
# LÓGICA DE ESTOQUE (USADA PELO LIVRO CAIXA)
# ==============================================================================

@st.cache_data(show_spinner="Carregando produtos do estoque...")
def inicializar_produtos():
    """Carrega ou inicializa o DataFrame de produtos."""
    COLUNAS_PRODUTOS = [
        "ID", "Nome", "Marca", "Categoria", "Quantidade", "PrecoCusto", 
        "PrecoVista", "PrecoCartao", "Validade", "FotoURL", "CodigoBarras", "PaiID"
    ]
    
    # Verifica se o DataFrame de produtos já está na sessão
    if "produtos" not in st.session_state:
        # Tenta carregar do GitHub
        url_raw = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/{ARQ_PRODUTOS}"
        df_carregado = load_csv_github(url_raw)
        
        if df_carregado is None or df_carregado.empty:
            df_base = pd.DataFrame(columns=COLUNAS_PRODUTOS)
        else:
            df_base = df_carregado
            
        # Garante a existência de todas as colunas
        for col in COLUNAS_PRODUTOS:
            if col not in df_base.columns:
                df_base[col] = ''
        
        # Garante tipos corretos
        df_base["Quantidade"] = pd.to_numeric(df_base["Quantidade"], errors='coerce').fillna(0).astype(int)
        df_base["PrecoCusto"] = pd.to_numeric(df_base["PrecoCusto"], errors='coerce').fillna(0.0)
        df_base["PrecoVista"] = pd.to_numeric(df_base["PrecoVista"], errors='coerce').fillna(0.0)
        df_base["PrecoCartao"] = pd.to_numeric(df_base["PrecoCartao"], errors='coerce').fillna(0.0)
        
        # Armazena o DataFrame na sessão
        st.session_state.produtos = df_base
            
    return st.session_state.produtos

def ajustar_estoque(id_produto, quantidade, operacao="debitar"):
    """Ajusta a quantidade no estoque do DataFrame e marca para salvamento."""
    
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
    """Salva o DataFrame CSV de PRODUTOS no GitHub via API."""
    repo = GITHUB_REPO
    token = GITHUB_TOKEN
    path = ARQ_PRODUTOS
    branch = GITHUB_BRANCH
    
    from requests import get, put
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    
    df_temp = dataframe.copy()
    
    # 1. Garante que o DataFrame não está vazio ANTES de tentar o to_csv
    if df_temp.empty:
        # Se for salvar um DF vazio, garante que as colunas sejam salvas
        csv_string = pd.DataFrame(columns=dataframe.columns).to_csv(index=False)
    else:
        for col in df_temp.select_dtypes(include=['datetime64[ns]']).columns:
            df_temp[col] = df_temp[col].dt.strftime('%Y-%m-%d').fillna('')
        csv_string = df_temp.to_csv(index=False)
        
    conteudo_b64 = base64.b64encode(csv_string.encode()).decode()
    headers = {"Authorization": f"token {token}"}
    
    r = get(url, headers=headers)
    sha = r.json().get("sha") if r.status_code == 200 else None
    payload = {"message": commit_message, "content": conteudo_b64, "branch": branch}
    if sha: payload["sha"] = sha
    r2 = put(url, headers=headers, json=payload)
    if r2.status_code in (200, 201):
        #st.success(f"✅ Arquivo `{path}` atualizado no GitHub!")
        return True
    else:
        st.error(f"❌ Erro ao salvar `{path}`: {r2.text}")
        return False

def save_data_github_produtos(df, path, commit_message):
    """Encapsula a lógica de persistência e hash para PRODUTOS."""
    novo_hash = hash_df(df)
    hash_key = f"hash_{path.replace('.', '_')}"
    
    if hash_key not in st.session_state:
        st.session_state[hash_key] = "initial"

    if novo_hash != st.session_state[hash_key] and novo_hash != "error":
        if salvar_produtos_no_github(df, commit_message):
            st.session_state[hash_key] = novo_hash
            return True
    return False


# ==============================================================================
# FUNÇÃO DA PÁGINA: GESTÃO DE PRODUTOS (ESTOQUE)
# ==============================================================================

def gestao_produtos():
    
    # Inicializa ou carrega o estado de produtos
    produtos = inicializar_produtos()
    
    # Título da Página
    st.header("📦 Gestão de Produtos e Estoque")

    # Lógica de Salvamento Automático para sincronizar alterações feitas pelo Livro Caixa
    # Esta linha é chamada APENAS para sincronizar alterações vindas de outras páginas (Livro Caixa)
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
                
                codigo_barras = st.text_input("Código de Barras (Pai/Simples)", value=st.session_state["codigo_barras"], key="cad_cb")

                # --- Escanear com câmera (Produto Simples/Pai) ---
                foto_codigo = st.camera_input("📷 Escanear código de barras / QR Code", key="cad_cam")
                if foto_codigo is not None:
                    # **CORREÇÃO:** Usa o getbuffer() para Streamlit Camera Input
                    imagem_bytes = foto_codigo.getbuffer() 
                    codigos_lidos = ler_codigo_barras_api(imagem_bytes)
                    if codigos_lidos:
                        st.session_state["codigo_barras"] = codigos_lidos[0]
                        st.success(f"Código lido: **{st.session_state['codigo_barras']}**")
                        # Força o Streamlit a atualizar para preencher o campo
                        st.rerun() 
                    else:
                        st.error("❌ Não foi possível ler nenhum código.")

                # --- Upload de imagem do código de barras (Produto Simples/Pai) ---
                foto_codigo_upload = st.file_uploader("📤 Upload de imagem do código de barras", type=["png", "jpg", "jpeg"], key="cad_cb_upload")
                if foto_codigo_upload is not None:
                    # **CORREÇÃO:** Usa o getvalue() para Streamlit File Uploader
                    imagem_bytes = foto_codigo_upload.getvalue() 
                    codigos_lidos = ler_codigo_barras_api(imagem_bytes)
                    if codigos_lidos:
                        st.session_state["codigo_barras"] = codigos_lidos[0]
                        st.success(f"Código lido via upload: **{st.session_state['codigo_barras']}**")
                        # Força o Streamlit a atualizar para preencher o campo
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
                    var_preco_custo = var_c3.text_input(f"Preço de custo variação {i+1}", value="0,00", key=f"var_pc_{i}")
                    var_preco_vista = var_c4.text_input(f"Preço à vista variação {i+1}", value="0,00", key=f"var_pv_{i}")
                    
                    var_cb_c1, var_cb_c2, var_cb_c3 = st.columns([2, 1, 1])

                    with var_cb_c1:
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
                    
                    # Checa qual input de imagem foi usado (Upload ou Câmera)
                    foto_lida = var_foto_upload or var_foto_cam
                    if foto_lida:
                        # **CORREÇÃO:** Usa getvalue() para upload e getbuffer() para camera input
                        imagem_bytes = foto_lida.getvalue() if var_foto_upload else foto_lida.getbuffer()
                        codigos_lidos = ler_codigo_barras_api(imagem_bytes)
                        if codigos_lidos:
                            # Armazena o código lido no estado de sessão da grade
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
                        "CodigoBarras": var_codigo_barras.strip() 
                    })

            if st.button("💾 Salvar Produto", use_container_width=True, key="cad_salvar"):
                if not nome.strip():
                    st.warning("⚠️ O nome do produto é obrigatório.")
                    
                novo_id = prox_id(produtos, "ID")
                
                if tipo_produto == "Produto simples":
                    novo = {
                        "ID": novo_id,
                        "Nome": nome.strip(),
                        "Marca": marca.strip(),
                        "Categoria": categoria.strip(),
                        "Quantidade": int(qtd),
                        "PrecoCusto": to_float(preco_custo),
                        "PrecoVista": to_float(preco_vista),
                        "PrecoCartao": round(to_float(preco_vista) / FATOR_CARTAO, 2) if to_float(preco_vista) > 0 else 0.0,
                        "Validade": str(validade),
                        "FotoURL": foto_url.strip(),
                        "CodigoBarras": codigo_barras.strip(),
                        "PaiID": None 
                    }
                    produtos = pd.concat([produtos, pd.DataFrame([novo])], ignore_index=True)
                else:
                    novo_pai = {
                        "ID": novo_id,
                        "Nome": nome.strip(),
                        "Marca": marca.strip(),
                        "Categoria": categoria.strip(),
                        "Quantidade": 0, 
                        "PrecoCusto": 0.0,
                        "PrecoVista": 0.0,
                        "PrecoCartao": 0.0,
                        "Validade": str(validade),
                        "FotoURL": foto_url.strip(),
                        "CodigoBarras": codigo_barras.strip(),
                        "PaiID": None
                    }
                    produtos = pd.concat([produtos, pd.DataFrame([novo_pai])], ignore_index=True)

                    for var in variações:
                        if var["Nome"] == "":
                            continue 
                        novo_filho = {
                            "ID": prox_id(produtos, "ID"),
                            "Nome": var["Nome"],
                            "Marca": marca.strip(),
                            "Categoria": categoria.strip(),
                            "Quantidade": var["Quantidade"],
                            "PrecoCusto": var["PrecoCusto"],
                            "PrecoVista": var["PrecoVista"],
                            "PrecoCartao": var["PrecoCartao"],
                            "Validade": str(validade),
                            "FotoURL": foto_url.strip(),
                            "CodigoBarras": var["CodigoBarras"],
                            "PaiID": novo_id 
                        }
                        produtos = pd.concat([produtos, pd.DataFrame([novo_filho])], ignore_index=True)

                st.session_state["produtos"] = produtos # Atualiza a sessão
                if 'cb_grade_lidos' in st.session_state:
                    del st.session_state.cb_grade_lidos 
                if 'codigo_barras' in st.session_state:
                    del st.session_state.codigo_barras 
                    
                # Força o salvamento e rerun
                if salvar_produtos_no_github(produtos, "Novo produto cadastrado"):
                    inicializar_produtos.clear() # Limpa o cache após criar
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
                        produtos_filtrados = produtos[produtos["PrecoVista"].astype(float) == valor]
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
            produtos_pai = produtos_filtrados[produtos_filtrados["PaiID"].isnull()]
            produtos_filho = produtos_filtrados[produtos_filtrados["PaiID"].notnull()]

            for index, pai in produtos_pai.iterrows():
                with st.container(border=True):
                    c = st.columns([1, 3, 1, 1, 1])
                    if str(pai["FotoURL"]).strip():
                        try:
                            c[0].image(pai["FotoURL"], width=80)
                        except Exception:
                            c[0].write("Sem imagem")
                    else:
                        c[0].write("—")

                    cb = f' • CB: {pai["CodigoBarras"]}' if str(pai.get("CodigoBarras", "")).strip() else ""
                    c[1].markdown(f"**{pai['Nome']}** \nMarca: {pai['Marca']} \nCat: {pai['Categoria']}{cb}")
                    
                    estoque_total = pai['Quantidade']
                    filhos_do_pai = produtos_filho[produtos_filho["PaiID"] == str(pai["ID"])]
                    if not filhos_do_pai.empty:
                        estoque_total = filhos_do_pai['Quantidade'].sum()
                    
                    c[2].markdown(f"**Estoque Total:** {estoque_total}")
                    c[3].write(f"Validade: {pai['Validade']}")
                    col_btn = c[4]

                    try:
                        eid = int(pai["ID"])
                    except Exception:
                        continue

                    acao = col_btn.selectbox(
                        "Ação",
                        ["Nenhuma", "✏️ Editar", "🗑️ Excluir"],
                        key=f"acao_pai_{index}_{eid}"
                    )

                    if acao == "✏️ Editar":
                        st.session_state["edit_prod"] = eid

                    if acao == "🗑️ Excluir":
                        if col_btn.button("Confirmar exclusão", key=f"conf_del_pai_{index}_{eid}"):
                            # Apaga o pai e os filhos
                            produtos = produtos[produtos["ID"] != str(eid)]
                            produtos = produtos[produtos["PaiID"] != str(eid)]

                            st.session_state["produtos"] = produtos
                            
                            # Tenta salvar imediatamente e limpa o cache
                            nome_pai = str(pai.get('Nome', 'Produto Desconhecido'))
                            
                            # Correção de robustez: Garante que o nome seja uma string válida
                            if nome_pai.lower() in ('nan', 'none', ''):
                                nome_pai = 'Produto Desconhecido'
                                
                            commit_msg_pai = f"Exclusão do produto pai {nome_pai}"

                            if salvar_produtos_no_github(produtos, commit_msg_pai):
                                inicializar_produtos.clear() # Limpa o cache para forçar o recarregamento do novo CSV
                                st.warning(f"Produto {nome_pai} e suas variações excluídas!")
                            else:
                                st.error("❌ Erro ao salvar a exclusão no GitHub. O produto pode reaparecer.")
                            
                            st.rerun()

                    if not filhos_do_pai.empty:
                        with st.expander(f"Variações de {pai['Nome']}"):
                            for index_var, var in filhos_do_pai.iterrows():
                                c_var = st.columns([1, 3, 1, 1, 1])
                                if str(var["FotoURL"]).strip():
                                    try:
                                        c_var[0].image(var["FotoURL"], width=60)
                                    except Exception:
                                        c_var[0].write("Sem imagem")
                                else:
                                    c_var[0].write("—")

                                cb_var = f' • CB: {var["CodigoBarras"]}' if str(var.get("CodigoBarras", "")).strip() else ""
                                c_var[1].markdown(f"**{var['Nome']}** \nMarca: {var['Marca']} \nCat: {var['Categoria']}{cb_var}")
                                c_var[2].write(f"Estoque: {var['Quantidade']}")
                                c_var[3].write(f"Preço V/C: R$ {var['PrecoVista']:.2f} / R$ {var['PrecoCartao']:.2f}")
                                col_btn_var = c_var[4]

                                try:
                                    eid_var = int(var["ID"])
                                except Exception:
                                    continue

                                acao_var = col_btn_var.selectbox(
                                    "Ação",
                                    ["Nenhuma", "✏️ Editar", "🗑️ Excluir"],
                                    key=f"acao_filho_{index_var}_{eid_var}"
                                )

                                if acao_var == "✏️ Editar":
                                    st.session_state["edit_prod"] = eid_var

                                if acao_var == "🗑️ Excluir":
                                    if col_btn_var.button("Confirmar exclusão", key=f"conf_del_filho_{index_var}_{eid_var}"):
                                        produtos = produtos[produtos["ID"] != str(eid_var)]
                                        st.session_state["produtos"] = produtos
                                        
                                        # Tenta salvar imediatamente e limpa o cache
                                        nome_var = str(var.get('Nome', 'Variação Desconhecida'))
                                        
                                        # Correção de robustez
                                        if nome_var.lower() in ('nan', 'none', ''):
                                            nome_var = 'Variação Desconhecida'
                                            
                                        commit_msg_var = f"Exclusão da variação {nome_var}"
                                        
                                        if salvar_produtos_no_github(produtos, "Novo produto cadastrado"):
                                            inicializar_produtos.clear() # Limpa o cache para forçar o recarregamento do novo CSV
                                            st.warning(f"Variação {nome_var} excluída!")
                                        else:
                                            st.error("❌ Erro ao salvar a exclusão no GitHub. O produto pode reaparecer.")

                                        st.rerun()

            # Editor inline (para pais e filhos)
            if "edit_prod" in st.session_state:
                eid = st.session_state["edit_prod"]
                row = produtos[produtos["ID"] == str(eid)]
                if not row.empty:
                    st.subheader("Editar produto")
                    row = row.iloc[0]
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        novo_nome = st.text_input("Nome", value=row["Nome"], key=f"edit_nome_{eid}")
                        nova_marca = st.text_input("Marca", value=row["Marca"], key=f"edit_marca_{eid}")
                        nova_cat = st.text_input("Categoria", value=row["Categoria"], key=f"edit_cat_{eid}")
                    with c2:
                        nova_qtd = st.number_input("Quantidade", min_value=0, step=1, value=int(row["Quantidade"]), key=f"edit_qtd_{eid}")
                        novo_preco_custo = st.text_input("Preço de Custo", value=str(row["PrecoCusto"]).replace(".", ","), key=f"edit_pc_{eid}")
                        novo_preco_vista = st.text_input("Preço à Vista", value=str(row["PrecoVista"]).replace(".", ","), key=f"edit_pv_{eid}")
                    with c3:
                        try:
                            vdata = datetime.strptime(str(row["Validade"] or date.today()), "%Y-%m-%d").date()
                        except Exception:
                            vdata = date.today()
                        nova_validade = st.date_input("Validade", value=vdata, key=f"edit_val_{eid}")
                        nova_foto = st.text_input("URL da Foto", value=row["FotoURL"], key=f"edit_foto_{eid}")
                        novo_cb = st.text_input("Código de Barras", value=str(row.get("CodigoBarras", "")), key=f"edit_cb_{eid}")

                        foto_codigo_edit = st.camera_input("📷 Atualizar código de barras", key=f"edit_cam_{eid}")
                        if foto_codigo_edit is not None:
                            # **CORREÇÃO:** Usa getbuffer() para camera input
                            codigo_lido = ler_codigo_barras_api(foto_codigo_edit.getbuffer()) 
                            if codigo_lido:
                                novo_cb = codigo_lido[0]
                                st.success(f"Código lido: **{novo_cb}**")

                    col_save, col_cancel = st.columns([1, 1])
                    with col_save:
                        if st.button("Salvar alterações", key=f"save_{eid}"):
                            
                            novo_preco_cartao = round(to_float(novo_preco_vista) / FATOR_CARTAO, 2) if to_float(novo_preco_vista) > 0 else 0.0

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
                                to_float(novo_preco_vista),
                                novo_preco_cartao,
                                str(nova_validade),
                                nova_foto.strip(),
                                str(novo_cb).strip()
                            ]
                            st.session_state["produtos"] = produtos
                            if salvar_produtos_no_github(produtos, ARQ_PRODUTOS, "Atualizando produto"):
                                inicializar_produtos.clear() # Limpa o cache após edição
                                
                            del st.session_state["edit_prod"]
                            st.rerun()
                            
                    with col_cancel:
                        if st.button("Cancelar edição", key=f"cancel_{eid}"):
                            del st.session_state["edit_prod"]
                            st.rerun()

# ==============================================================================
# FUNÇÃO DA PÁGINA: LIVRO CAIXA COMPLETO (BASEADO EM ff.py)
# ==============================================================================

def livro_caixa():
    #st.set_page_config(layout="wide", page_title="Livro Caixa", page_icon="📘") # REMOVIDO: Apenas uma chamada é permitida
    st.title("📘 Livro Caixa - Gerenciamento de Movimentações")

    # --- Inicialização e Constantes Locais ---
    # Acessa os produtos que podem ter sido alterados pela página 'Produtos'
    produtos = inicializar_produtos()

    # === Inicialização do Session State ===
    if "df" not in st.session_state:
        st.session_state.df = carregar_livro_caixa()

    if "lista_produtos" not in st.session_state:
        st.session_state.lista_produtos = []
        
    if "edit_id" not in st.session_state:
        st.session_state.edit_id = None
        
    if "operacao_selecionada" not in st.session_state:
        st.session_state.operacao_selecionada = "Editar" 

    df_dividas = st.session_state.df
    df_exibicao = processar_dataframe(df_dividas)

    # --- Preparação dos Produtos para a Venda (Entrada) ---
    produtos_para_venda = produtos[produtos["PaiID"].notna() | produtos["PaiID"].isnull()].copy()
    
    # Adiciona ID ao nome para facilitar o parse
    opcoes_produtos = [""] + produtos_para_venda.apply(
        lambda row: f"{row.ID} | {row.Nome} ({row.Marca}) | Estoque: {row.Quantidade}", axis=1
    ).tolist()
    
    # Adiciona a opção manual
    OPCAO_MANUAL = "Adicionar Item Manual (Sem Controle de Estoque)"
    opcoes_produtos.append(OPCAO_MANUAL)


    # Função para extrair ID do produto (melhorada)
    def extrair_id_do_nome(opcoes_str):
        if ' | ' in opcoes_str:
            return opcoes_str.split(' | ')[0]
        return None


    # =================================================================
    # LÓGICA DE CARREGAMENTO PARA EDIÇÃO
    # =================================================================
    edit_mode = st.session_state.edit_id is not None
    movimentacao_para_editar = None

    # Valores padrão do formulário (preenchidos com valores iniciais ou valores de edição)
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

    # Se estiver em modo de edição, carrega os dados
    if edit_mode:
        original_idx_to_edit = st.session_state.edit_id
        linha_df_exibicao = df_exibicao[df_exibicao['original_index'] == original_idx_to_edit]

        if not linha_df_exibicao.empty:
            movimentacao_para_editar = linha_df_exibicao.iloc[0]
            
            # Define os valores padrão para a edição
            default_loja = movimentacao_para_editar['Loja']
            default_data = movimentacao_para_editar['Data'] if pd.notna(movimentacao_para_editar['Data']) else datetime.now().date()
            default_cliente = movimentacao_para_editar['Cliente']
            default_valor = abs(movimentacao_para_editar['Valor']) if movimentacao_para_editar['Valor'] != 0 else 0.01 
            default_forma = movimentacao_para_editar['Forma de Pagamento']
            default_tipo = movimentacao_para_editar['Tipo']
            default_produtos_json = movimentacao_para_editar['Produtos Vendidos'] if pd.notna(movimentacao_para_editar['Produtos Vendidos']) else ""
            default_categoria = movimentacao_para_editar['Categoria']
            default_status = movimentacao_para_editar['Status'] 
            default_data_pagamento = movimentacao_para_editar['Data Pagamento'] if pd.notna(movimentacao_para_editar['Data Pagamento']) else None 
            
            # Carrega os produtos na lista de sessão (se for entrada)
            if default_tipo == "Entrada" and default_produtos_json:
                try:
                    produtos_list = json.loads(default_produtos_json)
                    for p in produtos_list:
                        p['Quantidade'] = float(p.get('Quantidade', 0))
                        p['Preço Unitário'] = float(p.get('Preço Unitário', 0))
                        p['Custo Unitário'] = float(p.get('Custo Unitário', 0))
                        p['Produto_ID'] = str(p.get('Produto_ID', '')) # Garante o ID
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


    # =================================================================
    # SIDEBAR: Formulário de Nova/Edição de Movimentação
    # =================================================================
    with st.sidebar:
        st.header("Nova Movimentação" if not edit_mode else "Editar Movimentação Existente")
        
        # --- INPUTS FORA DO FORM (Para controle de RERUN e Estado) ---
        tipo = st.radio("Tipo", ["Entrada", "Saída"], index=0 if default_tipo == "Entrada" else 1, key="input_tipo")
        
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
                
                # Prepara o JSON para a submissão final
                produtos_para_json = df_produtos[['Produto_ID', 'Produto', 'Quantidade', 'Preço Unitário', 'Custo Unitário']].to_dict('records')
                produtos_vendidos_json = json.dumps(produtos_para_json)
                
                st.success(f"Soma Total da Venda Calculada: R$ {valor_calculado:,.2f}")

            with st.expander("➕ Adicionar/Limpar Lista de Produtos", expanded=False):
                with st.container():
                    st.markdown("##### Produtos Atuais:")
                    if st.session_state.lista_produtos:
                        df_exibicao_produtos = pd.DataFrame(st.session_state.lista_produtos)
                        st.dataframe(df_exibicao_produtos[['Produto', 'Quantidade', 'Preço Unitário']], use_container_width=True, hide_index=True)
                    else:
                        st.info("Lista de produtos vazia.")

                    # --- Inputs de Produto para Adicionar ---
                    produto_selecionado = st.selectbox("Selecione o Produto (ID | Nome)", opcoes_produtos, key="input_produto_selecionado")
                    
                    
                    if produto_selecionado == OPCAO_MANUAL:
                        # --- ENTRADA MANUAL ---
                        nome_produto_manual = st.text_input("Nome do Produto (Manual)", key="input_nome_prod_manual")
                        quantidade_manual = st.number_input("Qtd Manual", min_value=0.01, value=1.0, step=1.0, key="input_qtd_prod_manual")
                        preco_unitario_manual = st.number_input("Preço Unitário (R$)", min_value=0.01, format="%.2f", key="input_preco_prod_manual")
                        custo_unitario_manual = st.number_input("Custo Unitário (R$)", min_value=0.00, value=0.00, format="%.2f", key="input_custo_prod_manual")

                        if st.button("Adicionar Item Manual", key="adicionar_item_manual_button", use_container_width=True):
                             if nome_produto_manual and quantidade_manual > 0:
                                st.session_state.lista_produtos.append({
                                    "Produto_ID": "", # Vazio para item manual (sem controle de estoque)
                                    "Produto": nome_produto_manual,
                                    "Quantidade": quantidade_manual,
                                    "Preço Unitário": preco_unitario_manual,
                                    "Custo Unitário": custo_unitario_manual 
                                })
                                st.rerun()
                             else:
                                 st.warning("Preencha o nome e a quantidade para o item manual.")
                        # --- FIM ENTRADA MANUAL ---

                    
                    elif produto_selecionado != "":
                        # --- ENTRADA DE ESTOQUE ---
                        produto_id_selecionado = extrair_id_do_nome(produto_selecionado) 
                        produto_row_completa = produtos_para_venda[produtos_para_venda["ID"] == produto_id_selecionado]
                        
                        if not produto_row_completa.empty:
                            produto_data = produto_row_completa.iloc[0]
                            nome_produto = produto_data['Nome']
                            preco_sugerido = produto_data['PrecoVista']
                            custo_unit = produto_data['PrecoCusto']
                            estoque_disp = produto_data['Quantidade']

                            col_p1, col_p2 = st.columns(2)
                            with col_p1:
                                # O max_value garante que não possa vender mais do que tem no estoque
                                quantidade_input = st.number_input("Qtd", min_value=1, value=1, step=1, max_value=int(estoque_disp) if estoque_disp > 0 else 1, key="input_qtd_prod_edit")
                            with col_p2:
                                preco_unitario_input = st.number_input("Preço Unitário (R$)", min_value=0.01, format="%.2f", value=float(preco_sugerido), key="input_preco_prod_edit")
                            
                            st.caption(f"Custo Unitário: R$ {custo_unit:,.2f}")
                            
                            if st.button("Adicionar Item à Venda", key="adicionar_item_button", use_container_width=True):
                                if quantidade_input > 0 and quantidade_input <= estoque_disp:
                                    st.session_state.lista_produtos.append({
                                        "Produto_ID": produto_id_selecionado, # Chave para débito de estoque
                                        "Produto": nome_produto,
                                        "Quantidade": quantidade_input,
                                        "Preço Unitário": preco_unitario_input,
                                        "Custo Unitário": custo_unit 
                                    })
                                    st.rerun()
                                elif quantidade_input > estoque_disp:
                                    st.warning(f"A quantidade ({quantidade_input}) excede o estoque disponível ({estoque_disp}).")
                                else:
                                    st.warning("A quantidade deve ser maior que zero.")
                        # --- FIM ENTRADA DE ESTOQUE ---
                        
                    
                    if st.button("Limpar Lista de Produtos", key="limpar_lista_button", type="secondary", use_container_width=True):
                        st.session_state.lista_produtos = []
                        st.rerun()
            
            # Valor final da movimentação (se lista vazia, permite input manual)
            valor_input_manual = st.number_input(
                "Valor Total (R$)", 
                value=valor_calculado if valor_calculado > 0.0 else default_valor,
                min_value=0.01, 
                format="%.2f",
                disabled=(valor_calculado > 0.0), # Desabilita se houver valor calculado
                key="input_valor_entrada"
            )
            valor_final_movimentacao = valor_calculado if valor_calculado > 0.0 else valor_input_manual

            
        else: # Tipo é Saída
            # Lógica de categoria fora do form principal
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
                                                key="input_categoria_saida")
                
            if categoria_selecionada == "Outro/Diversos":
                descricao_personalizada = st.text_input("Especifique o Gasto", 
                                                         value=custom_desc_default, 
                                                         key="input_custom_category")
                if descricao_personalizada:
                    categoria_selecionada = f"Outro: {descricao_personalizada}"
                
            valor_input_manual = st.number_input(
                "Valor (R$)", 
                value=default_valor, 
                min_value=0.01, 
                format="%.2f", 
                key="input_valor_saida"
            )
            valor_final_movimentacao = valor_input_manual

        # --- FIM DOS INPUTS FORA DO FORM ---

        # --- INÍCIO DO FORM PRINCIPAL DE SUBMISSÃO ---
        with st.form("form_movimentacao_sidebar", clear_on_submit=not edit_mode):
            
            # Inputs restantes que precisam ser resetados na submissão
            loja_selecionada = st.selectbox("Loja Responsável", 
                                            LOJAS_DISPONIVEIS, 
                                            index=LOJAS_DISPONIVEIS.index(default_loja) if default_loja in LOJAS_DISPONIVEIS else 0,
                                            key="input_loja_form")
            data_input = st.date_input("Data", value=default_data, key="input_data_form")
            cliente = st.text_input("Nome do Cliente (ou Descrição)", value=default_cliente, key="input_cliente_form")
            forma_pagamento = st.selectbox("Forma de Pagamento", 
                                            FORMAS_PAGAMENTO, 
                                            index=FORMAS_PAGAMENTO.index(default_forma) if default_forma in FORMAS_PAGAMENTO else 0,
                                            key="input_forma_pagamento_form")
            
            # Campos de Status (Repetição de estado forçada para resetar com o form)
            status_selecionado_form = st.radio("Status", ["Realizada", "Pendente"], index=0 if default_status == "Realizada" else 1, key="input_status_form")
            
            # Valor final (apenas exibição, o valor real vem de fora do form)
            st.caption(f"Valor Final da Movimentação: R$ {valor_final_movimentacao:,.2f}")


            # --- Botões de Submissão ---
            if edit_mode:
                col_save, col_cancel = st.columns(2)
                with col_save:
                    enviar = st.form_submit_button("💾 Salvar Edição", type="primary", use_container_width=True)
                with col_cancel:
                    cancelar = st.form_submit_button("❌ Cancelar Edição", type="secondary", use_container_width=True)
            else:
                enviar = st.form_submit_button("Adicionar Movimentação e Salvar", type="primary", use_container_width=True)
                cancelar = False 

            # --- Lógica principal (Adicionar/Editar) - Executada no Submit ---
            if enviar:
                
                # Revalidação e Lógica de Armazenamento
                if valor_final_movimentacao <= 0:
                    st.error("O valor deve ser maior que R$ 0,00.")
                elif tipo == "Saída" and categoria_selecionada == "Outro/Diversos":
                    st.error("Por favor, especifique o 'Outro/Diversos' para Saída.")
                else:
                    valor_armazenado = valor_final_movimentacao if tipo == "Entrada" else -valor_final_movimentacao
                    
                    if tipo == "Entrada" and not cliente and st.session_state.lista_produtos:
                        cliente_desc = f"Venda de {len(st.session_state.lista_produtos)} produto(s)"
                    else:
                        cliente_desc = cliente
                        
                    # LÓGICA DE ESTOQUE e REVERSÃO
                    if edit_mode:
                        original_row = df_dividas.loc[st.session_state.edit_id]
                        
                        # Se status antigo Realizada -> novo Pendente
                        if original_row["Status"] == "Realizada" and status_selecionado_form == "Pendente" and original_row["Tipo"] == "Entrada":
                            try:
                                produtos_vendidos_antigos = ast.literal_eval(original_row['Produtos Vendidos'])
                                for item in produtos_vendidos_antigos:
                                    if item.get("Produto_ID"): # Só credita se tiver ID de estoque
                                        ajustar_estoque(item["Produto_ID"], item["Quantidade"], "creditar")
                            except: pass
                            
                        # Se status continua Realizada, ajusta a diferença
                        elif original_row["Status"] == "Realizada" and status_selecionado_form == "Realizada" and original_row["Tipo"] == "Entrada":
                            # Credita o estoque antigo (se existia)
                            try:
                                produtos_vendidos_antigos = ast.literal_eval(original_row['Produtos Vendidos'])
                                for item in produtos_vendidos_antigos:
                                    if item.get("Produto_ID"):
                                        ajustar_estoque(item["Produto_ID"], item["Quantidade"], "creditar")
                            except: pass
                            
                            # Debita o novo estoque (se houver lista atualizada e itens com ID)
                            if produtos_vendidos_json:
                                produtos_vendidos_novos = json.loads(produtos_vendidos_json)
                                for item in produtos_vendidos_novos:
                                    if item.get("Produto_ID"):
                                        ajustar_estoque(item["Produto_ID"], item["Quantidade"], "debitar")
                            
                        # Salva ajuste de estoque
                        if salvar_produtos_no_github(st.session_state.produtos, ARQ_PRODUTOS, "Ajuste de estoque por edição de venda"):
                            inicializar_produtos.clear()
                            st.cache_data.clear() # Limpa o cache de dados para refletir mudanças no Livro Caixa
                            
                    # LÓGICA DE DÉBITO INICIAL (Nova Realizada)
                    elif not edit_mode and tipo == "Entrada" and status_selecionado_form == "Realizada" and st.session_state.lista_produtos:
                        if produtos_vendidos_json:
                            produtos_vendidos_novos = json.loads(produtos_vendidos_json)
                            for item in produtos_vendidos_novos:
                                if item.get("Produto_ID"): # Só debita se tiver ID de estoque
                                    ajustar_estoque(item["Produto_ID"], item["Quantidade"], "debitar")
                        if salvar_produtos_no_github(st.session_state.produtos, ARQ_PRODUTOS, "Débito de estoque por nova venda"):
                            inicializar_produtos.clear()
                            st.cache_data.clear() # Limpa o cache de dados para refletir mudanças no Livro Caixa


                    # MONTAGEM FINAL DA LINHA
                    data_pagamento_final = data_input if status_selecionado_form == "Realizada" else data_pagamento_final # Se Pendente, usa o valor de fora do form
                    
                    nova_linha_data = {
                        "Data": data_input,
                        "Loja": loja_selecionada, 
                        "Cliente": cliente, # Usa o cliente do formulário
                        "Valor": valor_armazenado, 
                        "Forma de Pagamento": forma_pagamento,
                        "Tipo": tipo,
                        "Produtos Vendidos": produtos_vendidos_json,
                        "Categoria": categoria_selecionada,
                        "Status": status_selecionado_form, 
                        "Data Pagamento": data_pagamento_final
                    }
                    
                    if edit_mode:
                        st.session_state.df.loc[st.session_state.edit_id] = pd.Series(nova_linha_data)
                        commit_msg = COMMIT_MESSAGE_EDIT
                    else:
                        st.session_state.df = pd.concat([df_dividas, pd.DataFrame([nova_linha_data])], ignore_index=True)
                        commit_msg = COMMIT_MESSAGE
                    
                    # Salva e recarrega
                    salvar_dados_no_github(st.session_state.df, commit_msg)
                    st.session_state.edit_id = None
                    st.session_state.lista_produtos = [] 
                    st.cache_data.clear()
                    st.rerun()


            # Lógica de Cancelamento (fora do bloco 'if enviar')
            if cancelar:
                st.session_state.edit_id = None
                st.session_state.lista_produtos = []
                st.rerun()


    # ========================================================
    # SEÇÃO PRINCIPAL (Abas: Movimentações/Resumo e Relatórios/Filtros)
    # ========================================================
    tab_mov, tab_rel = st.tabs(["📋 Movimentações e Resumo", "📈 Relatórios e Filtros"])


    with tab_mov:
        
        # --- FILTRAR PARA O MÊS ATUAL ---
        hoje = date.today()
        primeiro_dia_mes = hoje.replace(day=1)

        if hoje.month == 12:
            proximo_mes = hoje.replace(year=hoje.year + 1, month=1, day=1)
        else:
            proximo_mes = hoje.replace(month=hoje.month + 1, day=1)
        ultimo_dia_mes = proximo_mes - timedelta(days=1)

        # Filtra o DataFrame de exibição para incluir apenas o mês atual E que foram REALIZADAS
        df_mes_atual_realizado = df_exibicao[
            (df_exibicao["Data"] >= primeiro_dia_mes) &
            (df_exibicao["Data"] <= ultimo_dia_mes) &
            (df_exibicao["Status"] == "Realizada")
        ]
        
        st.subheader(f"📊 Resumo Financeiro Geral - Mês de {primeiro_dia_mes.strftime('%m/%Y')}")

        # Calcula Resumo com dados do Mês Atual REALIZADO
        total_entradas, total_saidas, saldo = calcular_resumo(df_mes_atual_realizado)

        col1, col2, col3 = st.columns(3)
        col1.metric("Total de Entradas", f"R$ {total_entradas:,.2f}")
        col2.metric("Total de Saídas", f"R$ {total_saidas:,.2f}")
        delta_saldo = f"R$ {saldo:,.2f}"
        col3.metric("💼 Saldo Final (Realizado)", f"R$ {saldo:,.2f}", delta=delta_saldo if saldo != 0 else None, delta_color="normal")

        st.markdown("---")
        
        # --- LÓGICA DE ALERTA DE DÍVIDAS PENDENTES (Lembretes) ---
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
        
        # --- Resumo Agregado por Loja (MÊS ATUAL REALIZADO) ---
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
            # --- FILTROS RÁPIDOS NA TABELA PRINCIPAL (UX Improvement) ---
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

            # --- PREPARAÇÃO DA TABELA ---
            df_para_mostrar = df_filtrado_rapido.copy()
            df_para_mostrar['Produtos Resumo'] = df_para_mostrar['Produtos Vendidos'].apply(format_produtos_resumo)
            
            colunas_tabela = ['ID Visível', 'Data', 'Loja', 'Cliente', 'Categoria', 'Valor', 'Forma de Pagamento', 'Tipo', 'Status', 'Data Pagamento', 'Produtos Resumo', 'Saldo Acumulado']
            
            # --- Lógica Correta para Estilização Condicional ---
            df_styling = df_para_mostrar[colunas_tabela + ['Cor_Valor']].copy()

            styled_df = df_styling.style.apply(highlight_value, axis=1)
            styled_df = styled_df.hide(subset=['Cor_Valor'], axis=1)


            # 4. Exibe o DataFrame estilizado
            st.dataframe(
                styled_df,
                use_container_width=True,
                column_config={
                    "Valor": st.column_config.NumberColumn(
                        "Valor (R$)",
                        format="R$ %.2f",
                    ),
                    "Saldo Acumulado": st.column_config.NumberColumn(
                        "Saldo Acumulado (R$)",
                        format="R$ %.2f",
                    ),
                    "Produtos Resumo": st.column_config.TextColumn("Detalhe dos Produtos"),
                    "Categoria": "Categoria (C. Custo)",
                    "Data Pagamento": st.column_config.DateColumn("Data Pagt. Previsto/Real", format="DD/MM/YYYY")
                },
                height=400,
                selection_mode='single-row', 
                key='movimentacoes_table_styled'
            )


            # --- Lógica de Exibição de Detalhes da Linha Selecionada ---
            selection_state = st.session_state.get('movimentacoes_table_styled')

            if selection_state and selection_state.get('selection', {}).get('rows'):
                selected_index = selection_state['selection']['rows'][0]
                
                if selected_index < len(df_para_mostrar):
                    row = df_para_mostrar.iloc[selected_index]

                    if row['Tipo'] == 'Entrada' and row['Produtos Vendidos'] and pd.notna(row['Produtos Vendidos']):
                        st.markdown("#### Detalhes dos Produtos Selecionados")
                        try:
                            produtos = json.loads(row['Produtos Vendidos'])
                            
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
                                    "Lucro Bruto": st.column_config.NumberColumn("Lucro Bruto", format="R$ %.2f"),
                                }
                            )
                        except Exception as e:
                            st.error(f"Erro ao carregar detalhes dos produtos: {e}")
                    elif row['Tipo'] == 'Saída':
                        st.info(f"Movimentação de Saída. Categoria: **{row['Categoria']}**")

            st.caption("Clique em uma linha para ver os detalhes dos produtos (se for Entrada).")
            st.markdown("---")

            # =================================================================
            # --- OPÇÕES DE EDIÇÃO E EXCLUSÃO UNIFICADAS ---
            # =================================================================
            st.markdown("### 📝 Operações de Movimentação (Editar/Excluir)")
            
            opcoes_operacao = {
                f"ID {row['ID Visível']} | {row['Data'].strftime('%d/%m/%Y')} | {row['Loja']} | R$ {row['Valor']:,.2f} ({row['Tipo']})": row['original_index'] 
                for index, row in df_exibicao.iterrows()
            }
            opcoes_keys = list(opcoes_operacao.keys())
            
            if not opcoes_keys:
                st.info("Nenhuma movimentação para editar ou excluir.")
            else:
                col_modo, col_selecao = st.columns([0.3, 0.7])
                
                with col_modo:
                    st.session_state.operacao_selecionada = st.radio(
                        "Escolha a Operação:",
                        options=["Editar", "Excluir"],
                        index=0 if st.session_state.operacao_selecionada == "Editar" else 1, 
                        key="radio_operacao_select",
                        horizontal=True,
                        disabled=edit_mode
                    )

                with col_selecao:
                    movimentacao_selecionada_str = st.selectbox(
                        f"Selecione a movimentação para {st.session_state.operacao_selecionada}:",
                        options=opcoes_keys,
                        index=0,
                        key="select_operacao",
                        disabled=edit_mode
                    )
                
                original_idx_selecionado = opcoes_operacao.get(movimentacao_selecionada_str)
                
                # --- Botões de Ação Contextual ---
                if original_idx_selecionado is not None:
                    if st.session_state.operacao_selecionada == "Editar":
                        if st.button("✏️ Levar para Edição na Sidebar", type="secondary", use_container_width=True, disabled=edit_mode):
                            st.session_state.edit_id = original_idx_selecionado
                            st.rerun()
                    
                    elif st.session_state.operacao_selecionada == "Excluir":
                        st.markdown("##### Confirmação de Exclusão:")
                        if st.button(f"🗑️ Excluir permanentemente: {movimentacao_selecionada_str}", type="primary", use_container_width=True):
                            
                            # Lógica de estorno de estoque
                            row_original_df = df_dividas.loc[original_idx_selecionado]
                            if row_original_df['Status'] == "Realizada" and row_original_df["Tipo"] == "Entrada" and row_original_df["Produtos Vendidos"] and row_original_df["Produtos Vendidos"] != "":
                                try:
                                    produtos_vendidos = ast.literal_eval(row_original_df['Produtos Vendidos'])
                                    for item in produtos_vendidos:
                                        produto_id = item.get("Produto_ID")
                                        if produto_id: 
                                            ajustar_estoque(produto_id, item["Quantidade"], "creditar")
                                    if salvar_produtos_no_github(st.session_state.produtos, ARQ_PRODUTOS, "Crédito de estoque por exclusão de venda"):
                                        inicializar_produtos.clear()
                                        st.warning("Estoque creditado de volta.")
                                except Exception as e:
                                    st.error(f"Erro ao creditar estoque: {e}")
                            
                            # Exclui a linha e salva
                            st.session_state.df = st.session_state.df.drop(original_idx_selecionado, errors='ignore')
                            
                            if salvar_dados_no_github(st.session_state.df, COMMIT_MESSAGE_DELETE):
                                st.cache_data.clear()
                                st.rerun()
    
    with tab_rel:
        
        st.header("📈 Relatórios e Filtros")
        
        df_filtrado_loja = df_exibicao.copy()
        loja_filtro_relatorio = "Todas as Lojas"

        if not df_exibicao.empty:
            
            lojas_unicas_no_df = df_exibicao["Loja"].unique().tolist()
            todas_lojas = ["Todas as Lojas"] + [l for l in LOJAS_DISPONIVEIS if l in lojas_unicas_no_df] + [l for l in lojas_unicas_no_df if l not in LOJAS_DISPONIVEIS and l != "Todas as Lojas"]
            todas_lojas = list(dict.fromkeys(todas_lojas))

            loja_filtro_relatorio = st.selectbox(
                "Selecione a Loja para Filtrar Relatórios",
                options=todas_lojas,
                key="loja_filtro_rel"
            )

            if loja_filtro_relatorio != "Todas as Lojas":
                df_filtrado_loja = df_exibicao[df_exibicao["Loja"] == loja_filtro_relatorio].copy()
            else:
                df_filtrado_loja = df_exibicao.copy()
                
            st.subheader(f"Dashboard de Relatórios - {loja_filtro_relatorio}")

        else:
            st.info("Não há dados suficientes para gerar relatórios e filtros.")
        

        subtab_dashboard, subtab_filtro, subtab_produtos, subtab_dividas = st.tabs(["Dashboard Geral", "Filtro e Tabela", "Produtos e Lucro", "🧾 Dívidas Pendentes"])
        
        # O teste df_filtrado_loja.empty garante que a lógica de relatórios só ocorra com dados.

        with subtab_dividas:
            st.header("🧾 Gerenciamento de Dívidas Pendentes")
            
            df_pendente = df_exibicao[df_exibicao["Status"] == "Pendente"].copy()
            
            if df_pendente.empty:
                st.info("🎉 Não há Contas a Pagar ou Receber pendentes!")
            else:
                
                # --- Separação Contas a Receber e Pagar ---
                df_receber = df_pendente[df_pendente["Tipo"] == "Entrada"].reset_index(drop=True)
                df_pagar = df_pendente[df_pendente["Tipo"] == "Saída"].reset_index(drop=True)
                
                st.markdown("---")
                st.markdown("### 📥 Contas a Receber (Vendas Pendentes)")
                
                if df_receber.empty:
                    st.info("Nenhuma venda pendente para receber.")
                else:
                    st.dataframe(
                        df_receber[['ID Visível', 'Data', 'Loja', 'Cliente', 'Valor', 'Data Pagamento', 'original_index']],
                        use_container_width=True,
                        selection_mode='multi-row',
                        hide_index=True,
                        column_config={
                            "Data Pagamento": st.column_config.DateColumn("Data Prevista", format="DD/MM/YYYY"),
                            "Valor": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f"),
                        },
                        column_order=('ID Visível', 'Data', 'Loja', 'Cliente', 'Valor', 'Data Pagamento'),
                        key="tabela_receber"
                    )
                    st.info(f"Total a Receber: R$ {df_receber['Valor'].sum():,.2f}")
                    
                st.markdown("---")
                st.markdown("### 📤 Contas a Pagar (Despesas Pendentes)")
                
                if df_pagar.empty:
                    st.info("Nenhuma despesa pendente para pagar.")
                else:
                    st.dataframe(
                        df_pagar[['ID Visível', 'Data', 'Loja', 'Cliente', 'Categoria', 'Valor', 'Data Pagamento', 'original_index']],
                        use_container_width=True,
                        selection_mode='multi-row',
                        hide_index=True,
                        column_config={
                            "Data Pagamento": st.column_config.DateColumn("Data Prevista", format="DD/MM/YYYY"),
                            "Valor": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f"), 
                        },
                        column_order=('ID Visível', 'Data', 'Loja', 'Cliente', 'Categoria', 'Valor', 'Data Pagamento'),
                        key="tabela_pagar"
                    )
                    st.info(f"Total a Pagar: R$ {abs(df_pagar['Valor'].sum()):,.2f}")

                st.markdown("---")
                st.markdown("### ✅ Concluir Pagamentos Pendentes")

                selecao_receber = st.session_state.get('tabela_receber', {}).get('selection', {}).get('rows', [])
                selecao_pagar = st.session_state.get('tabela_pagar', {}).get('selection', {}).get('rows', [])
                
                indices_selecionados = []
                
                if selecao_receber:
                    indices_selecionados.extend(df_receber.iloc[selecao_receber]['original_index'].tolist())
                
                if selecao_pagar:
                    indices_selecionados.extend(df_pagar.iloc[selecao_pagar]['original_index'].tolist())

                if indices_selecionados:
                    st.info(f"Total de {len(indices_selecionados)} transações selecionadas para conclusão.")
                    
                    with st.form("form_concluir_dividas"):
                        st.markdown("##### Detalhes da Conclusão:")
                        data_conclusao = st.date_input("Data de Pagamento Real", value=hoje)
                        forma_conclusao = st.selectbox("Forma de Pagamento Real (PIX, Dinheiro, etc.)", options=FORMAS_PAGAMENTO)
                        
                        submeter_conclusao = st.form_submit_button("Concluir Pagamentos Selecionados e Salvar", type="primary")

                    if submeter_conclusao:
                        df_temp_session = st.session_state.df.copy()
                        
                        for original_idx in indices_selecionados:
                            # 1. Ajusta o status, data e forma no DataFrame original
                            if original_idx in df_temp_session.index:
                                df_temp_session.loc[original_idx, 'Status'] = 'Realizada'
                                df_temp_session.loc[original_idx, 'Data Pagamento'] = data_conclusao
                                df_temp_session.loc[original_idx, 'Forma de Pagamento'] = forma_conclusao
                                
                                # 2. LÓGICA DE DÉBITO DE ESTOQUE (SE FOR VENDA)
                                original_row = df_dividas.loc[original_idx]
                                if original_row['Tipo'] == "Entrada" and original_row["Produtos Vendidos"] and original_row["Produtos Vendidos"] != "":
                                    try:
                                        produtos_vendidos = ast.literal_eval(original_row['Produtos Vendidos'])
                                        for item in produtos_vendidos:
                                            produto_id = item.get("Produto_ID")
                                            if produto_id: 
                                                ajustar_estoque(produto_id, item["Quantidade"], "debitar")
                                        if salvar_produtos_no_github(st.session_state.produtos, ARQ_PRODUTOS, "Débito de estoque por liquidação de dívida"):
                                            inicializar_produtos.clear()
                                        st.success("Estoque debitado por venda liquidada.")
                                    except Exception as e:
                                        st.error(f"Erro ao debitar estoque: {e}")

                        st.session_state.df = df_temp_session
                        
                        if salvar_dados_no_github(st.session_state.df, COMMIT_MESSAGE_DEBT_REALIZED):
                            st.cache_data.clear()
                            st.rerun()
                else:
                    st.warning("Selecione itens nas tabelas acima para concluir.")


        with subtab_dashboard:
            if df_filtrado_loja.empty:
                st.warning("Nenhuma movimentação encontrada para gerar o Dashboard.")
            else:
                
                # --- Análise de Saldo Acumulado (Série Temporal) ---
                st.markdown("### 📉 Saldo Acumulado (Tendência no Tempo)")
                
                df_acumulado = df_filtrado_loja.sort_values(by='Data_dt', ascending=True).copy()
                df_acumulado = df_acumulado[df_acumulado['Status'] == 'Realizada']

                if df_acumulado.empty:
                    st.info("Nenhuma transação Realizada para calcular o Saldo Acumulado.")
                else:
                    fig_line = px.line(
                        df_acumulado,
                        x='Data_dt',
                        y='Saldo Acumulado',
                        title='Evolução do Saldo Realizado ao Longo do Tempo',
                        labels={'Data_dt': 'Data', 'Saldo Acumulado': 'Saldo Acumulado (R$)'},
                        line_shape='spline',
                        markers=True
                    )
                    fig_line.update_layout(xaxis_title="Data", yaxis_title="Saldo Acumulado (R$)")
                    st.plotly_chart(fig_line, use_container_width=True)
                
                st.markdown("---")

                # --- Distribuição de Saídas por Categoria (Centro de Custo) ---
                st.markdown("### 📊 Saídas por Categoria (Centro de Custo - Realizadas)")
                
                df_saidas = df_filtrado_loja[(df_filtrado_loja['Tipo'] == 'Saída') & (df_filtrado_loja['Status'] == 'Realizada')].copy()
                
                if df_saidas.empty:
                    st.info("Nenhuma saída Realizada registrada para análise de categorias.")
                else:
                    df_saidas['Valor Absoluto'] = df_saidas['Valor'].abs()
                    df_categorias = df_saidas.groupby('Categoria')['Valor Absoluto'].sum().reset_index()
                    
                    fig_cat_pie = px.pie(
                        df_categorias,
                        values='Valor Absoluto',
                        names='Categoria',
                        title='Distribuição de Gastos por Categoria',
                        hole=.3
                    )
                    st.plotly_chart(fig_cat_pie, use_container_width=True)

                st.markdown("---")

                # --- Gráfico de Ganhos vs. Gastos (Existente, mas reajustado para Realizada) ---
                st.markdown("### 📈 Ganhos (Entradas) vs. Gastos (Saídas) por Mês (Realizados)")
                
                df_ganhos_gastos = df_filtrado_loja[df_filtrado_loja['Status'] == 'Realizada'].copy()
                
                if df_ganhos_gastos.empty:
                    st.info("Nenhuma transação Realizada para a análise mensal.")
                else:
                    df_ganhos_gastos['MesAno'] = df_ganhos_gastos['Data'].apply(lambda x: x.strftime('%Y-%m'))
                    df_grouped = df_ganhos_gastos.groupby(['MesAno', 'Tipo'])['Valor'].sum().abs().reset_index()
                    df_grouped.columns = ['MesAno', 'Tipo', 'Total']
                    df_grouped = df_grouped.sort_values(by='MesAno')

                    fig_bar = px.bar(
                        df_grouped,
                        x='MesAno',
                        y='Total',
                        color='Tipo',
                        barmode='group',
                        text='Total',
                        color_discrete_map={'Entrada': 'green', 'Saída': 'red'},
                        labels={'Total': 'Valor (R$)', 'MesAno': 'Mês/Ano'},
                        height=500
                    )
                    fig_bar.update_traces(texttemplate='R$ %{y:,.2f}', textposition='outside')
                    st.plotly_chart(fig_bar, use_container_width=True)

        with subtab_produtos:
            st.markdown("## 💰 Análise de Produtos e Lucratividade (Realizados)")

            if df_filtrado_loja.empty:
                st.warning("Nenhuma movimentação encontrada para gerar a Análise de Produtos.")
            else:
                df_entradas_produtos = df_filtrado_loja[(df_filtrado_loja['Tipo'] == 'Entrada') & (df_filtrado_loja['Status'] == 'Realizada')].copy()

                if df_entradas_produtos.empty:
                    st.info("Nenhuma entrada com produtos REALIZADA registrada para análise.")
                else:
                    
                    lista_produtos_agregada = []
                    for index, row in df_entradas_produtos.iterrows():
                        if pd.notna(row['Produtos Vendidos']) and row['Produtos Vendidos'] and row['Produtos Vendidos'] != "":
                            try:
                                produtos = json.loads(row['Produtos Vendidos'])
                                for p in produtos:
                                    try:
                                        qtd = float(p.get('Quantidade', 0))
                                        preco_un = float(p.get('Preço Unitário', 0))
                                        custo_un = float(p.get('Custo Unitário', 0))
                                    except ValueError:
                                        continue
                                    
                                    if qtd > 0:
                                        lista_produtos_agregada.append({
                                            "Produto": p['Produto'],
                                            "Quantidade": qtd,
                                            "Total Venda": qtd * preco_un,
                                            "Total Custo": qtd * custo_un,
                                            "Lucro Bruto": (qtd * preco_un) - (qtd * custo_un),
                                        })
                            except:
                                pass

                    if lista_produtos_agregada:
                        df_produtos_agregados = pd.DataFrame(lista_produtos_agregada)
                        df_produtos_agregados = df_produtos_agregados.groupby('Produto').sum(numeric_only=True).reset_index()

                        st.markdown("### 🏆 Top 10 Produtos (Valor de Venda)")
                        top_venda = df_produtos_agregados.sort_values(by='Total Venda', ascending=False).head(10)
                        
                        fig_top_venda = px.bar(
                            top_venda,
                            x='Produto',
                            y='Total Venda',
                            text='Total Venda',
                            title='Top 10 Produtos por Valor Total de Venda (R$)',
                            color='Total Venda'
                        )
                        fig_top_venda.update_traces(texttemplate='R$ %{y:,.2f}', textposition='outside')
                        st.plotly_chart(fig_top_venda, use_container_width=True)
                        
                        if df_produtos_agregados['Lucro Bruto'].sum() > 0:
                            st.markdown("### 💸 Top 10 Produtos por Lucro Bruto")
                            top_lucro = df_produtos_agregados.sort_values(by='Lucro Bruto', ascending=False).head(10)
                            
                            fig_top_lucro = px.bar(
                                top_lucro,
                                x='Produto',
                                y='Lucro Bruto',
                                text='Lucro Bruto',
                                title='Top 10 Produtos Mais Lucrativos (R$)',
                                color='Lucro Bruto',
                                color_continuous_scale=px.colors.sequential.Greens
                            )
                            fig_top_lucro.update_traces(texttemplate='R$ %{y:,.2f}', textposition='outside')
                            st.plotly_chart(fig_top_lucro, use_container_width=True)
                        else:
                            st.info("Adicione o 'Custo Unitário' no cadastro de produtos para ver o ranking de Lucro Bruto.")
                            
                    else:
                        st.info("Nenhum produto com dados válidos encontrado para agregar.")

        with subtab_filtro:
            
            if df_filtrado_loja.empty:
                st.warning("Nenhuma movimentação encontrada para gerar a Tabela Filtrada.")
            else:
                st.subheader("📅 Filtrar Movimentações por Período e Loja")
                
                df_base_filtro_tabela = df_filtrado_loja

                col_data_inicial, col_data_final = st.columns(2)
                
                data_minima = df_base_filtro_tabela["Data"].min() if pd.notna(df_base_filtro_tabela["Data"].min()) else hoje
                data_maxima = df_base_filtro_tabela["Data"].max() if pd.notna(df_base_filtro_tabela["Data"].max()) else hoje
                
                data_min_value = data_minima if pd.notna(data_minima) else hoje
                data_max_value = data_maxima if pd.notna(data_maxima) else hoje
                
                with col_data_inicial:
                    data_inicial = st.date_input("Data Inicial", value=data_min_value, key="filtro_data_ini")
                with col_data_final:
                    data_final = st.date_input("Data Final", value=data_max_value, key="filtro_data_fim")

                if data_inicial and data_final:
                    data_inicial_dt = pd.to_datetime(data_inicial).date()
                    data_final_dt = pd.to_datetime(data_final).date()
                    
                    df_filtrado_final = df_base_filtro_tabela[
                        (df_base_filtro_tabela["Data"] >= data_inicial_dt) &
                        (df_base_filtro_tabela["Data"] <= data_final_dt)
                    ].copy()
                    
                    if df_filtrado_final.empty:
                        st.warning("Não há movimentações para o período selecionado.")
                    else:
                        st.markdown("#### Tabela Filtrada")
                        
                        df_filtrado_final['Produtos Resumo'] = df_filtrado_final['Produtos Vendidos'].apply(format_produtos_resumo)
                        
                        colunas_filtro_tabela = ['ID Visível', 'Data', 'Loja', 'Cliente', 'Categoria', 'Valor', 'Forma de Pagamento', 'Tipo', 'Status', 'Data Pagamento', 'Produtos Resumo', 'Saldo Acumulado']

                        df_styling_filtro = df_filtrado_final[colunas_filtro_tabela + ['Cor_Valor']].copy()
                        styled_df_filtro = df_styling_filtro.style.apply(highlight_value, axis=1)
                        styled_df_filtro = styled_df_filtro.hide(subset=['Cor_Valor'], axis=1)
                        
                        st.dataframe(
                            styled_df_filtro,
                            use_container_width=True,
                            column_config={
                                "Valor": st.column_config.NumberColumn(
                                    "Valor (R$)",
                                    format="R$ %.2f",
                                ),
                                "Saldo Acumulado": st.column_config.NumberColumn(
                                    "Saldo Acumulado (R$)",
                                    format="R$ %.2f",
                                ),
                                "Produtos Resumo": st.column_config.TextColumn("Detalhe dos Produtos"),
                                "Categoria": "Categoria (C. Custo)",
                                "Data Pagamento": st.column_config.DateColumn("Data Pagt. Previsto/Real", format="DD/MM/YYYY")
                            }
                        )

                        entradas_filtro, saidas_filtro, saldo_filtro = calcular_resumo(df_filtrado_final)

                        st.markdown("#### 💰 Resumo do Período Filtrado (Apenas Realizado)")
                        col1_f, col2_f, col3_f = st.columns(3)
                        col1_f.metric("Entradas", f"R$ {entradas_filtro:,.2f}")
                        col2_f.metric("Saídas", f"R$ {saidas_filtro:,.2f}")
                        col3_f.metric("Saldo", f"R$ {saldo_filtro:,.2f}")


# =====================================
# ROTEAMENTO FINAL
# =====================================

# Limpa estados de páginas removidas
if "produtos_manuais" in st.session_state: del st.session_state["produtos_manuais"]
if "df_produtos_geral" in st.session_state: del st.session_state["df_produtos_geral"]
if "insumos" in st.session_state: del st.session_state["insumos"]
if "produtos_papelaria" in st.session_state: del st.session_state["produtos_papelaria"]


main_tab_select = st.sidebar.radio(
    "Escolha a página:",
    ["Livro Caixa", "Produtos"],
    key='main_page_select_widget'
)

if main_tab_select == "Livro Caixa":
    livro_caixa()
elif main_tab_select == "Produtos":
    gestao_produtos()


