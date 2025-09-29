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
# Funções auxiliares (Troca API ZXing por WebQR - JSON)
# =====================================

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
            # st.write("Debug API ZXing:", codigos)
            pass

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

# >>> INÍCIO ADIÇÃO: CONSTANTES DO HISTÓRICO DE COMPRAS <<<<
ARQ_COMPRAS = "historico_compras.csv" # Novo arquivo para o histórico
COMMIT_MESSAGE_COMPRAS = "Atualiza histórico de compras via Streamlit"
# ADIÇÃO: Nova coluna "FotoURL" para o histórico de compras
COLUNAS_COMPRAS = ["Data", "Produto", "Quantidade", "Valor Total", "Cor", "FotoURL"] 
# >>> FIM ADIÇÃO: CONSTANTES DO HISTÓRICO DE COMPRAS <<<<


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

# ========================================================
# FUNÇÕES DE PERSISTÊNCIA: HISTÓRICO DE COMPRAS (ADIÇÃO)
# ========================================================

@st.cache_data(show_spinner="Carregando histórico de compras...")
def carregar_historico_compras():
    """Orquestra o carregamento do Histórico de Compras."""
    df = None
    
    # 1. Tenta carregar do GitHub
    url_raw = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/{ARQ_COMPRAS}"
    df = load_csv_github(url_raw)

    if df is None or df.empty:
        # 2. Fallback para DF vazio
        df = pd.DataFrame(columns=COLUNAS_COMPRAS)

    # Garante que as colunas padrão existam
    for col in COLUNAS_COMPRAS:
        if col not in df.columns:
            df[col] = "" 
            
    # Assegura que o DataFrame retornado tem as colunas corretas (e na ordem)
    return df[COLUNAS_COMPRAS] 

def salvar_historico_no_github(df: pd.DataFrame, commit_message: str):
    """Salva o DataFrame CSV de Histórico de Compras no GitHub e localmente."""
    
    # 1. Backup local (Tenta salvar, ignora se falhar)
    try:
        df.to_csv(ARQ_COMPRAS.replace(".csv", "_local.csv"), index=False)
    except Exception:
        pass

    df_temp = df.copy()
    
    try:
        g = Github(TOKEN)
        repo = g.get_repo(f"{OWNER}/{REPO_NAME}")
        csv_string = df_temp.to_csv(index=False)

        try:
            # Tenta obter o SHA do conteúdo atual
            contents = repo.get_contents(ARQ_COMPRAS, ref=BRANCH)
            # Atualiza o arquivo
            repo.update_file(contents.path, commit_message, csv_string, contents.sha, branch=BRANCH)
            st.success("📁 Histórico de Compras salvo (atualizado) no GitHub!")
        except Exception:
            # Cria o arquivo 
            repo.create_file(ARQ_COMPRAS, commit_message, csv_string, branch=BRANCH)
            st.success("📁 Histórico de Compras salvo (criado) no GitHub!")

        return True

    except Exception as e:
        st.error(f"❌ Erro ao salvar no GitHub: {e}")
        st.error("Verifique se seu 'GITHUB_TOKEN' tem permissões e se o repositório existe.")
        return False
# ========================================================
# FIM DAS FUNÇÕES DE PERSISTÊNCIA: HISTÓRICO DE COMPRAS
# ========================================================


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
        
        # O Saldo Acumulado é a soma cumulativa apenas das realizadas. 
        # Preenche com o valor anterior para manter a continuidade visual
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
            # Usa ast.literal_eval como fallback, pois o json.loads pode falhar se a string não for estritamente JSON
            try:
                produtos = json.loads(produtos_json)
            except json.JSONDecodeError:
                produtos = ast.literal_eval(produtos_json)

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

# --- Callback para Cadastro de Novo Produto ---
def callback_salvar_novo_produto(produtos, tipo_produto, nome, marca, categoria, qtd, preco_custo, preco_vista, validade, foto_url, codigo_barras, variacoes):
    """Lógica de persistência para o novo produto."""
    
    if not nome.strip():
        st.warning("⚠️ O nome do produto é obrigatório.")
        return 
        
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
        # Produto Pai
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

        # Variações (Filhos)
        for var in variacoes:
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
    
    # Limpa estados para resetar o formulário
    if 'cb_grade_lidos' in st.session_state:
        del st.session_state.cb_grade_lidos 
    if 'codigo_barras' in st.session_state:
        del st.session_state.codigo_barras 
        
    # Força o salvamento e rerun
    if salvar_produtos_no_github(produtos, "Novo produto cadastrado"):
        inicializar_produtos.clear() # Limpa o cache após criar
        
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
                codigo_barras = st.text_input("Código de Barras (Pai/Simples)", value=st.session_state["codigo_barras"], key="cad_cb")

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
                        "CodigoBarras": var_codigo_barras.strip() 
                    })
                
            # --- BOTÃO SALVAR PRODUTO (CHAMANDO CALLBACK) ---
            if st.button(
                "💾 Salvar", # Rótulo curto
                use_container_width=True, 
                key="cad_salvar",
                on_click=callback_salvar_novo_produto,
                args=(produtos.copy(), tipo_produto, nome, marca, categoria, qtd, preco_custo, preco_vista, validade, foto_url, codigo_barras, variações),
                help="Salvar Novo Produto Completo" # Rótulo completo
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
                        # Busca por valor de custo, vista ou cartão
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
            # Garante que as colunas sejam tratadas corretamente (float/int) antes de filtrar
            produtos_filtrados["Quantidade"] = pd.to_numeric(produtos_filtrados["Quantidade"], errors='coerce').fillna(0).astype(int)
            produtos_pai = produtos_filtrados[produtos_filtrados["PaiID"].isnull()]
            produtos_filho = produtos_filtrados[produtos_filtrados["PaiID"].notnull()]
            
            # --- CSS Customizado para o Layout da Lista ---
            # O CSS já está configurado para o layout de grade e botões minimalistas.
            st.markdown("""
                <style>
                .custom-header, .custom-row {
                    display: grid;
                    /* Layout: Img | Produto/Marca | Estoque | Validade | Preços | Ações (2 cols) */
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
                # --- CONTAINER DO PRODUTO PAI ---
                with st.container(border=True):
                    # Usamos st.columns para criar o grid dentro do container
                    c = st.columns([1, 3, 1, 1, 1.5, 0.5, 0.5]) 
                    
                    # --- 1. Imagem ---
                    if str(pai["FotoURL"]).strip():
                        try:
                            c[0].image(pai["FotoURL"], width=60)
                        except Exception:
                            c[0].write("—")
                    else:
                        c[0].write("—")

                    # --- 2. Nome/Marca/Categoria ---
                    cb = f' • CB: {pai["CodigoBarras"]}' if str(pai.get("CodigoBarras", "")).strip() else ""
                    c[1].markdown(f"**{pai['Nome']}**<br><small>Marca: {pai['Marca']} | Cat: {pai['Categoria']}</small>", unsafe_allow_html=True)
                    
                    # --- 3. Estoque ---
                    estoque_total = pai['Quantidade']
                    filhos_do_pai = produtos_filho[produtos_filho["PaiID"] == str(pai["ID"])]
                    if not filhos_do_pai.empty:
                        estoque_total = filhos_do_pai['Quantidade'].sum()
                    
                    c[2].markdown(f"**{estoque_total}**")
                    
                    # --- 4. Validade ---
                    c[3].write(f"{pai['Validade']}")
                    
                    # --- 5. Detalhes de Preço (Custo/Vista/Cartão) ---
                    pv = to_float(pai['PrecoVista'])
                    pc_calc = round(pv / FATOR_CARTAO, 2)
                    
                    # Formatando o bloco de preços de forma mais limpa
                    preco_html = (
                        f'<div class="custom-price-block">'
                        f'<small>C: R$ {to_float(pai['PrecoCusto']):,.2f}</small><br>'
                        f'**V:** R$ {pv:,.2f}<br>'
                        f'**C:** R$ {pc_calc:,.2f}'
                        f'</div>'
                    )
                    c[4].markdown(preco_html, unsafe_allow_html=True)
                    
                    # --- 6 & 7. Ações Minimalistas (Editar & Excluir) ---
                    try:
                        eid = str(pai["ID"])
                    except Exception:
                        eid = str(index) # Fallback

                    if c[5].button("✏️", key=f"edit_pai_{index}_{eid}", help="Editar produto"):
                        st.session_state["edit_prod"] = eid
                        st.rerun()

                    if c[6].button("🗑️", key=f"del_pai_{index}_{eid}", help="Excluir produto"):
                        # Lógica de exclusão direta 
                        produtos = produtos[produtos["ID"] != eid]
                        produtos = produtos[produtos["PaiID"] != eid]
                        st.session_state["produtos"] = produtos
                        
                        nome_pai = str(pai.get('Nome', 'Produto Desconhecido'))
                        if salvar_produtos_no_github(produtos, f"Exclusão do produto pai {nome_pai}"):
                            inicializar_produtos.clear() 
                        st.rerun()
                        
                    if not filhos_do_pai.empty:
                        # --- Variações ---
                        with st.expander(f"Variações de {pai['Nome']} ({len(filhos_do_pai)} variações)"):
                            for index_var, var in filhos_do_pai.iterrows():
                                c_var = st.columns([1, 3, 1, 1, 1.5, 0.5, 0.5]) 
                                
                                # 1. Imagem (Variação) - usa FotoURL do pai se a variação não tiver
                                foto_url_var = str(var["FotoURL"]).strip() or str(pai["FotoURL"]).strip()
                                if foto_url_var:
                                    try:
                                        c_var[0].image(foto_url_var, width=60)
                                    except Exception:
                                        c_var[0].write("—")
                                else:
                                    c_var[0].write("—")

                                # 2. Nome/Marca/Categoria (Variação)
                                cb_var = f' • CB: {var["CodigoBarras"]}' if str(var.get("CodigoBarras", "")).strip() else ""
                                c_var[1].markdown(f"**{var['Nome']}**<br><small>Marca: {var['Marca']} | Cat: {var['Categoria']}</small>", unsafe_allow_html=True)
                                
                                # 3. Estoque (Variação)
                                c_var[2].write(f"{var['Quantidade']}")
                                
                                # 4. Validade (Variação)
                                c_var[3].write(f"{var['Validade']}")

                                # 5. Detalhes de Preço (Variação)
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

                                # 6 & 7. Ações Minimalistas (Variação)
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

            # Editor inline (para pais e filhos) - Mantido para permitir a edição
            if "edit_prod" in st.session_state:
                eid = st.session_state["edit_prod"]
                row = produtos[produtos["ID"] == str(eid)]
                if not row.empty:
                    st.subheader(f"Editar produto ID: {eid} ({row.iloc[0]['Nome']})")
                    row = row.iloc[0]
                    
                    # Layout dos inputs de edição (3 colunas, 3 itens por coluna)
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        novo_nome = st.text_input("Nome", value=row["Nome"], key=f"edit_nome_{eid}")
                        nova_marca = st.text_input("Marca", value=row["Marca"], key=f"edit_marca_{eid}")
                        nova_cat = st.text_input("Categoria", value=row["Categoria"], key=f"edit_cat_{eid}")
                    with c2:
                        # Garante que a quantidade seja um int para o number_input
                        qtd_value = int(row["Quantidade"]) if pd.notna(row["Quantidade"]) else 0
                        nova_qtd = st.number_input("Quantidade", min_value=0, step=1, value=qtd_value, key=f"edit_qtd_{eid}")
                        # Formata o float para string com vírgula para o input
                        novo_preco_custo = st.text_input("Preço de Custo", value=f"{to_float(row["PrecoCusto"]):.2f}".replace(".", ","), key=f"edit_pc_{eid}")
                        novo_preco_vista = st.text_input("Preço à Vista", value=f"{to_float(row["PrecoVista"]):.2f}".replace(".", ","), key=f"edit_pv_{eid}")
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

                    # ALINHAMENTO DOS BOTÕES DE AÇÃO:
                    col_empty_left, col_save, col_cancel = st.columns([3, 1.5, 1.5]) 
                    
                    with col_save:
                        # Botão "Salvar" 
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
                                str(nova_validade),
                                nova_foto.strip(),
                                str(novo_cb).strip()
                            ]
                            st.session_state["produtos"] = produtos
                            # CORREÇÃO: Chama salvar_produtos_no_github
                            if salvar_produtos_no_github(produtos, "Atualizando produto"):
                                inicializar_produtos.clear() # Limpa o cache após edição
                                
                            del st.session_state["edit_prod"]
                            st.rerun()
                            
                    with col_cancel:
                        # Botão "Cancelar"
                        if st.button("❌ Cancelar", key=f"cancel_{eid}", use_container_width=True, help="Cancelar Edição"):
                            del st.session_state["edit_prod"]
                            st.rerun()


# ==============================================================================
# FUNÇÃO DA PÁGINA: HISTÓRICO DE COMPRAS (NOVA ADIÇÃO)
# ==============================================================================

# Novo estado para gerenciar qual compra está sendo editada
if "edit_compra_idx" not in st.session_state:
    st.session_state.edit_compra_idx = None
    
def historico_compras():
    st.title("🛒 Histórico de Compras de Insumos")
    st.info("Utilize esta página para registrar produtos (insumos, materiais, estoque) comprados. Estes dados são **separados** do controle de estoque principal e do Livro Caixa.")

    # --- Inicialização e Carregamento ---
    if "df_compras" not in st.session_state:
        st.session_state.df_compras = carregar_historico_compras()

    df_compras = st.session_state.df_compras.copy()
    
    # Processamento para exibição e persistência interna (simplificado)
    if not df_compras.empty:
        # Tenta converter para tipos, se for string vazia, retorna None/0
        df_compras['Data'] = pd.to_datetime(df_compras['Data'], errors='coerce').dt.date
        df_compras['Quantidade'] = pd.to_numeric(df_compras['Quantidade'], errors='coerce').fillna(0).astype(int)
        df_compras['Valor Total'] = pd.to_numeric(df_compras['Valor Total'], errors='coerce').fillna(0.0)
        
    # Prepara o DF para manipulação de índice (exibição e remoção)
    df_exibicao = df_compras.sort_values(by='Data', ascending=False).reset_index(drop=False)
    df_exibicao.rename(columns={'index': 'original_index'}, inplace=True)
    df_exibicao.insert(0, 'ID', df_exibicao.index + 1)
    
    # ==================================================
    # 1. RELATÓRIO DO MÊS ATUAL
    # ==================================================
    hoje = date.today()
    primeiro_dia_mes = hoje.replace(day=1)

    if hoje.month == 12:
        proximo_mes = hoje.replace(year=hoje.year + 1, month=1, day=1)
    else:
        proximo_mes = hoje.replace(month=hoje.month + 1, day=1)
    ultimo_dia_mes = proximo_mes - timedelta(days=1)
    
    # Filtra as compras do mês atual e onde o valor total é positivo (gasto)
    df_mes_atual = df_exibicao[
        (df_exibicao["Data"].apply(lambda x: pd.notna(x) and x >= primeiro_dia_mes and x <= ultimo_dia_mes)) &
        (df_exibicao["Valor Total"] > 0)
    ].copy()

    # CORREÇÃO: A soma do Valor Total está correta, pois o usuário insere o valor total da compra. 
    # Se o problema é visualização, é devido ao cache ou input. Mantemos a soma direta.
    total_gasto_mes = df_mes_atual['Valor Total'].sum() 

    st.markdown("---")
    st.subheader(f"📊 Resumo de Gastos - Mês de {primeiro_dia_mes.strftime('%m/%Y')}")
    st.metric(
        label="💰 Total Gasto com Compras de Insumos (Mês Atual)",
        value=f"R$ {total_gasto_mes:,.2f}"
    )
    st.markdown("---")
    # ==================================================
    
    # Define as abas: Cadastro + Dashboard/Lista/Filtro
    tab_cadastro, tab_dashboard = st.tabs(["📝 Cadastro & Lista de Compras", "📈 Dashboard de Gastos"])
    
    # ==================================================
    # 2. DASHBOARD DE GASTOS (Nova Aba)
    # ==================================================
    with tab_dashboard:
        st.header("📈 Análise de Gastos com Compras")
        
        if df_exibicao.empty:
            st.info("Nenhum dado de compra registrado para gerar o dashboard.")
        else:
            # Agregação por Produto (calcula o total gasto por produto em todo o histórico)
            # NOTA: df_exibicao['Valor Total'] já é o gasto total daquela linha.
            # Se você registrar 2 produtos de R$ 100,00, a linha terá Qtd=2, Valor Total=200.
            # O agrupamento abaixo soma 200 (se o produto for o mesmo).
            df_gasto_por_produto = df_exibicao.groupby('Produto')['Valor Total'].sum().reset_index()
            df_gasto_por_produto = df_gasto_por_produto.sort_values(by='Valor Total', ascending=False)
            
            st.markdown("### 🥇 Top Produtos Mais Gastos (Valor Total)")
            
            if df_gasto_por_produto.empty:
                 st.info("Nenhum produto com gasto registrado.")
            else:
                top_n = st.slider("Mostrar Top N Produtos", min_value=5, max_value=20, value=10)
                top_produtos = df_gasto_por_produto.head(top_n)

                # Gráfico de Barras para Top Gastos
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
                
                # Análise temporal (cria coluna MesAno)
                df_temp_data = df_exibicao[df_exibicao['Data'].notna()].copy()
                df_temp_data['Data_dt'] = pd.to_datetime(df_temp_data['Data'])
                df_temp_data['MesAno'] = df_temp_data['Data_dt'].dt.strftime('%Y-%m')
                
                df_gasto_mensal = df_temp_data.groupby('MesAno')['Valor Total'].sum().reset_index()
                df_gasto_mensal = df_gasto_mensal.sort_values(by='MesAno')

                # Gráfico de Linha para Gasto Mensal
                fig_mensal = px.line(
                    df_gasto_mensal,
                    x='MesAno',
                    y='Valor Total',
                    title='Evolução do Gasto Mensal com Compras',
                    labels={'Valor Total': 'Gasto (R$)', 'MesAno': 'Mês/Ano'},
                    markers=True
                )
                st.plotly_chart(fig_mensal, use_container_width=True)
    
    # ==================================================
    # 3. CADASTRO & LISTA DE COMPRAS (Aba Unificada)
    # ==================================================
    with tab_cadastro:
        
        # --- LÓGICA DE EDIÇÃO ---
        edit_mode_compra = st.session_state.edit_compra_idx is not None
        
        if edit_mode_compra:
            original_idx_to_edit = st.session_state.edit_compra_idx
            # Encontra a linha no DataFrame original (não o df_exibicao reindexado)
            linha_para_editar = df_compras[df_compras.index == original_idx_to_edit]
            
            if not linha_para_editar.empty:
                compra_data = linha_para_editar.iloc[0]
                
                # Valores padrão para edição
                # Garantindo a conversão de Data
                try:
                    default_data = pd.to_datetime(compra_data['Data']).date()
                except:
                    default_data = date.today()
                    
                default_produto = compra_data['Produto']
                default_qtd = int(compra_data['Quantidade'])
                default_valor = float(compra_data['Valor Total'])
                default_cor = compra_data['Cor']
                default_foto_url = compra_data['FotoURL']
                
                st.subheader("📝 Editar Compra Selecionada")
                st.warning(f"Editando item: **{default_produto}** (ID Interno: {original_idx_to_edit})")
            else:
                st.session_state.edit_compra_idx = None
                edit_mode_compra = False
                st.subheader("📝 Formulário de Registro") # Fallback
                
        if not edit_mode_compra:
            st.subheader("📝 Formulário de Registro")
            default_data = date.today()
            default_produto = ""
            default_qtd = 1
            default_valor = 10.00
            default_cor = "#007bff"
            default_foto_url = ""


        # --- Formulário de Cadastro/Edição ---
        with st.form("form_compra", clear_on_submit=not edit_mode_compra):
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                data = st.date_input("Data da Compra", value=default_data, key="compra_data_form")
                nome_produto = st.text_input("Produto/Material Comprado", value=default_produto, key="compra_nome_form")
                
            with col2:
                quantidade = st.number_input("Quantidade", min_value=1, value=default_qtd, step=1, key="compra_qtd_form")
                valor_total_input = st.number_input("Valor Total (R$)", min_value=0.01, format="%.2f", value=default_valor, key="compra_valor_form")
                
            with col3:
                cor_selecionada = st.color_picker("Cor para Destaque", value=default_cor, key="compra_cor_form")
            
            with col4:
                foto_url = st.text_input("URL da Foto do Produto (Opcional)", value=default_foto_url, key="compra_foto_url_form")
            
            
            if edit_mode_compra:
                col_sub1, col_sub2 = st.columns(2)
                salvar_compra = col_sub1.form_submit_button("💾 Salvar Edição", type="primary", use_container_width=True)
                cancelar_edicao = col_sub2.form_submit_button("❌ Cancelar Edição", type="secondary", use_container_width=True)
            else:
                salvar_compra = st.form_submit_button("💾 Adicionar Compra", type="primary", use_container_width=True)
                cancelar_edicao = False


            # --- Lógica de Ação ---
            if salvar_compra:
                if not nome_produto or valor_total_input <= 0 or quantidade <= 0:
                    st.error("Preencha todos os campos obrigatórios com valores válidos.")
                else:
                    nova_linha = {
                        "Data": data.strftime('%Y-%m-%d'),
                        "Produto": nome_produto.strip(),
                        "Quantidade": int(quantidade),
                        "Valor Total": float(valor_total_input),
                        "Cor": cor_selecionada,
                        "FotoURL": foto_url.strip(),
                    }
                    
                    if edit_mode_compra:
                        # Modo Edição: Atualiza a linha existente
                        st.session_state.df_compras.loc[original_idx_to_edit] = pd.Series(nova_linha)
                        commit_msg = f"Edição da compra {nome_produto}"
                    else:
                        # Modo Cadastro: Adiciona nova linha
                        df_original = st.session_state.df_compras.iloc[:, :len(COLUNAS_COMPRAS)]
                        st.session_state.df_compras = pd.concat([df_original, pd.DataFrame([nova_linha])], ignore_index=True)
                        commit_msg = f"Nova compra registrada: {nome_produto}"

                    # Salva e recarrega
                    if salvar_historico_no_github(st.session_state.df_compras, commit_msg):
                        st.session_state.edit_compra_idx = None # Sai do modo edição
                        st.cache_data.clear()
                        st.rerun()

            if cancelar_edicao:
                st.session_state.edit_compra_idx = None
                st.rerun()
        
        # --- Lista e Operações ---
        st.markdown("---")
        st.subheader("Lista e Operações de Histórico")
        
        # --- Filtros de Busca (Produto e Data) ---
        with st.expander("🔍 Filtros da Lista", expanded=False):
            col_f1, col_f2 = st.columns([1, 2])
            
            # 1. Filtro de Produto
            with col_f1:
                filtro_produto = st.text_input("Filtrar por nome do Produto:", key="filtro_compra_produto_tab")
            
            # 2. Filtro de Data
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
                    
                # Requer conversão de volta para date para comparação, mas o DF já está com objetos date
                df_filtrado = df_filtrado[
                    (df_filtrado["Data"] >= data_ini) &
                    (df_filtrado["Data"] <= data_fim)
                ]
            
        # --- Tabela de Exibição com Ações ---
        
        if df_filtrado.empty:
            st.info("Nenhuma compra encontrada com os filtros aplicados.")
        else:
            # Cria a coluna 'Data Formatada' no DataFrame filtrado, antes de ser usada para a tabela e para as opções de exclusão.
            df_filtrado['Data Formatada'] = df_filtrado['Data'].apply(lambda x: x.strftime('%d/%m/%Y') if pd.notna(x) else '')
            
            # Estilização condicional (usando CSS para cor de fundo)
            def highlight_color_compras(row):
                """Função para aplicar o destaque de cor na linha."""
                color = row['Cor']
                return [f'background-color: {color}30' for col in row.index]
            
            df_para_mostrar = df_filtrado.copy()
            
            # Inclui a Foto como uma coluna de link para melhor visualização na tabela.
            df_para_mostrar['Foto'] = df_para_mostrar['FotoURL'].apply(lambda x: '📷' if x.strip() else '')

            # Prepara a lista de colunas para exibição e estilos
            df_display_cols = ['ID', 'Data Formatada', 'Produto', 'Quantidade', 'Valor Total', 'Foto', 'Cor', 'original_index']
            df_styling = df_para_mostrar[df_display_cols].copy()
            
            styled_df = df_styling.style.apply(highlight_color_compras, axis=1)
            # Oculta a coluna de cor e o índice original
            styled_df = styled_df.hide(subset=['Cor', 'original_index'], axis=1)

            st.markdown("##### Tabela de Itens Comprados")
            # 4. Exibe o DataFrame estilizado
            st.dataframe(
                styled_df,
                use_container_width=True,
                column_config={
                    "Data Formatada": st.column_config.TextColumn("Data da Compra"),
                    "Valor Total": st.column_config.NumberColumn(
                        "Valor Total (R$)",
                        format="R$ %.2f",
                    ),
                    "Foto": st.column_config.TextColumn("Foto"),
                },
                column_order=('ID', 'Data Formatada', 'Produto', 'Quantidade', 'Valor Total', 'Foto'),
                height=400,
                selection_mode='single-row', 
                key='compras_table_styled'
            )
            
            # --- Lógica de Seleção para Editar/Excluir ---
            selection_state = st.session_state.get('compras_table_styled')
            selected_row_index = None # Índice do DF filtrado
            
            if selection_state and selection_state.get('selection', {}).get('rows'):
                selected_row_index = selection_state['selection']['rows'][0]
                
            
            st.markdown("### Operações de Edição e Exclusão")
            
            if selected_row_index is not None:
                # Mapeia o índice da linha selecionada no DF filtrado para o 'original_index'
                original_idx_selecionado = df_para_mostrar.iloc[selected_row_index]['original_index']
                item_selecionado_str = f"ID {df_para_mostrar.iloc[selected_row_index]['ID']} | {df_para_mostrar.iloc[selected_row_index]['Produto']}"
                
                col_edit, col_delete = st.columns(2)

                # Botão de Edição
                # Desabilita o botão de edição se já estiver no modo edição
                if col_edit.button(f"✏️ Editar: {item_selecionado_str}", type="secondary", use_container_width=True, disabled=edit_mode_compra):
                    st.session_state.edit_compra_idx = original_idx_selecionado
                    st.rerun()

                # Botão de Exclusão
                if col_delete.button(f"🗑️ Excluir: {item_selecionado_str}", type="primary", use_container_width=True, disabled=edit_mode_compra):
                    # Exclui a linha do DF original da sessão (usando o índice original mapeado)
                    st.session_state.df_compras = st.session_state.df_compras.drop(original_idx_selecionado, errors='ignore')
                    
                    if salvar_historico_no_github(st.session_state.df_compras, f"Exclusão da compra {item_selecionado_str}"):
                        st.cache_data.clear()
                        st.rerun()
            else:
                st.info("Selecione uma linha na tabela acima para editar ou excluir.")


# ==============================================================================
# FUNÇÃO DA PÁGINA: LIVRO CAIXA COMPLETO (BASEADO EM ff.py)
# ==============================================================================

# --- Funções de Callback para Adição de Produtos ---
def callback_adicionar_manual(nome, qtd, preco, custo):
    """Adiciona item manual e limpa o session state."""
    if nome and qtd > 0:
        st.session_state.lista_produtos.append({
            "Produto_ID": "", 
            "Produto": nome,
            "Quantidade": qtd,
            "Preço Unitário": preco,
            "Custo Unitário": custo 
        })
        # Limpa os campos de input manual no session state
        st.session_state.input_nome_prod_manual = ""
        st.session_state.input_qtd_prod_manual = 1.0
        st.session_state.input_preco_prod_manual = 0.01
        st.session_state.input_custo_prod_manual = 0.00
        # Limpa o seletor para que o usuário possa selecionar o próximo item
        st.session_state.input_produto_selecionado = "" 
        
def callback_adicionar_estoque(prod_id, prod_nome, qtd, preco, custo, estoque_disp):
    """Adiciona item de estoque e limpa o seletor."""
    if qtd > 0 and qtd <= estoque_disp:
        st.session_state.lista_produtos.append({
            "Produto_ID": prod_id, # Chave para débito de estoque
            "Produto": prod_nome,
            "Quantidade": qtd,
            "Preço Unitário": preco,
            "Custo Unitário": custo 
        })
        # Limpa o seletor
        st.session_state.input_produto_selecionado = ""
    else:
        # Nota: O warning pode não ser exibido corretamente devido ao re-run
        st.warning("A quantidade excede o estoque ou é inválida.")

# --- Função Principal ---

def livro_caixa():
    #st.set_page_config(layout="wide", page_title="Livro Caixa", page_icon="📘") # REMOVIDO: Apenas uma chamada é permitida
    st.title("📘 Livro Caixa - Gerenciamento de Movimentações")

    # --- Inicialização e Constantes Locais ---
    # Acessa os produtos que podem ter sido alterados pela página 'Produtos'
    # Esta é a linha que estava faltando a inicialização no session_state no fluxo de erro.
    produtos = inicializar_produtos() 

    # === Inicialização do Session State ===
    if "df" not in st.session_state:
        st.session_state.df = carregar_livro_caixa()

    # **GARANTIA DE ESTADO:** Garante que 'produtos' esteja no session_state para chamadas futuras.
    if "produtos" not in st.session_state:
            st.session_state.produtos = produtos

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
        
    # Variáveis de controle de input manual
    if "input_nome_prod_manual" not in st.session_state:
        st.session_state.input_nome_prod_manual = ""
    if "input_qtd_prod_manual" not in st.session_state:
        st.session_state.input_qtd_prod_manual = 1.0
    if "input_preco_prod_manual" not in st.session_state:
        st.session_state.input_preco_prod_manual = 0.01
    if "input_custo_prod_manual" not in st.session_state:
        st.session_state.input_custo_prod_manual = 0.00
    if "input_produto_selecionado" not in st.session_state:
        st.session_state.input_produto_selecionado = ""


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
    default_data_status_previsto = "Com Data Prevista"

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
            # Se for Pendente, mantém a data de pagamento prevista. Se Realizada, usa a data da transação ou a que está salva.
            default_data_pagamento = movimentacao_para_editar['Data Pagamento'] if pd.notna(movimentacao_para_editar['Data Pagamento']) else (movimentacao_para_editar['Data'] if movimentacao_para_editar['Status'] == 'Realizada' else None) 
            
            # Define o status do rádio de data prevista para edição
            if default_status == "Pendente":
                default_data_status_previsto = "Com Data Prevista" if pd.notna(default_data_pagamento) else "Sem Data Prevista"
            
            # Carrega os produtos na lista de sessão (se for entrada)
            if default_tipo == "Entrada" and default_produtos_json:
                try:
                    # Tenta usar json.loads, mas usa ast.literal_eval como fallback
                    try:
                        produtos_list = json.loads(default_produtos_json)
                    except json.JSONDecodeError:
                        produtos_list = ast.literal_eval(default_produtos_json)

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
        # 1. TIPO (Entrada/Saída)
        tipo = st.radio("Tipo", ["Entrada", "Saída"], index=0 if default_tipo == "Entrada" else 1, key="input_tipo")
        
        # 2. STATUS (Realizada/Pendente) - MOVIDO PARA FORA DO FORM PARA RENDERIZAÇÃO CONDICIONAL
        status_selecionado = st.radio(
            "Status", 
            ["Realizada", "Pendente"], 
            index=0 if default_status == "Realizada" else 1, 
            key="input_status_global"
        )

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

            with st.expander("➕ Adicionar/Limpar Lista de Produtos", expanded=True):
                with st.container():
                    st.markdown("##### Produtos Atuais:")
                    if st.session_state.lista_produtos:
                        df_exibicao_produtos = pd.DataFrame(st.session_state.lista_produtos)
                        st.dataframe(df_exibicao_produtos[['Produto', 'Quantidade', 'Preço Unitário']], use_container_width=True, hide_index=True)
                    else:
                        st.info("Lista de produtos vazia.")

                    # --- Inputs de Produto para Adicionar ---
                    # Usa o valor do session state para que ele possa ser limpo depois da submissão
                    produto_selecionado = st.selectbox(
                        "Selecione o Produto (ID | Nome)", 
                        opcoes_produtos, 
                        key="input_produto_selecionado",
                        index=opcoes_produtos.index(st.session_state.input_produto_selecionado) if st.session_state.input_produto_selecionado in opcoes_produtos else 0
                    )
                    
                    
                    if produto_selecionado == OPCAO_MANUAL:
                        # --- ENTRADA MANUAL ---
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
                        
                        # Correção: O callback agora é chamado no 'on_click'
                        if st.button(
                            "Adicionar Manual", # Rótulo curto
                            key="adicionar_item_manual_button", 
                            use_container_width=True,
                            on_click=callback_adicionar_manual,
                            args=(nome_produto_manual, quantidade_manual, preco_unitario_manual, custo_unitario_manual),
                            help="Adicionar Item Manual à Lista de Venda" # Rótulo completo
                        ):
                            st.rerun() 
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

                            # Correção: O callback agora é chamado no 'on_click'
                            if st.button(
                                "Adicionar Item", # Rótulo curto
                                key="adicionar_item_button", 
                                use_container_width=True,
                                on_click=callback_adicionar_estoque,
                                args=(produto_id_selecionado, nome_produto, quantidade_input, preco_unitario_input, custo_unit, estoque_disp),
                                help="Adicionar Item do Estoque à Lista de Venda" # Rótulo completo
                            ):
                                st.rerun()
                        # --- FIM ENTRADA DE ESTOQUE ---
                        
                    
                    if st.button("Limpar Lista", key="limpar_lista_button", type="secondary", use_container_width=True, help="Limpa todos os produtos da lista de venda"):
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

        # --- LÓGICA DE DATA DE PAGAMENTO (REFACTOR: FORA DO FORM PARA MELHOR UX) ---
        data_pagamento_final = None # Valor final a ser enviado no submit

        if status_selecionado == "Pendente":
            st.markdown("##### 🗓️ Previsão de Pagamento")
            
            # Verifica se default_data_pagamento é uma data válida para pré-selecionar 'Com Data Prevista'
            data_prevista_existe = pd.notna(default_data_pagamento) and (default_data_pagamento is not None)

            data_status_opcoes = ["Com Data Prevista", "Sem Data Prevista"]
            # A chave é diferente do form para que este componente sobreviva ao submit
            data_status_key = "input_data_status_previsto_global" 
            
            # Tenta usar o valor anterior da sessão se houver
            default_data_status_index = 0
            if data_status_key in st.session_state:
                   # Se estiver em modo edição, usa o default_data_status_previsto (do load_data)
                if edit_mode:
                    default_data_status_index = data_status_opcoes.index(default_data_status_previsto) if default_data_status_previsto in data_status_opcoes else 0
                # Caso contrário, usa o último estado salvo (para nova movimentação)
                else:
                    default_data_status_index = data_status_opcoes.index(st.session_state[data_status_key]) if st.session_state[data_status_key] in data_status_opcoes else 0
            else:
                   default_data_status_index = data_status_opcoes.index(default_data_status_previsto) if default_data_status_previsto in data_status_opcoes else 0

            data_status_selecionado_previsto = st.radio(
                "Essa pendência tem data prevista?",
                options=data_status_opcoes,
                index=default_data_status_index,
                key=data_status_key, 
                horizontal=True
            )

            # Para que o date_input não resete a cada rerun, definimos a chave no session_state
            if data_status_selecionado_previsto == "Com Data Prevista":
                # Se for Pendente COM data, mostra o campo
                prev_date_value = default_data_pagamento if data_prevista_existe else date.today() 
                
                data_prevista_pendente = st.date_input(
                    "Selecione a Data Prevista", 
                    value=prev_date_value, 
                    key="input_data_pagamento_prevista_global"
                )
                data_pagamento_final = data_prevista_pendente
            else:
                # Se for Pendente SEM data, data_pagamento_final permanece None
                data_pagamento_final = None

        # --- FIM DOS INPUTS FORA DO FORM ---

        # --- INÍCIO DO FORM PRINCIPAL DE SUBMISSÃO (Onde a Data de Transação é coletada) ---
        with st.form("form_movimentacao_sidebar", clear_on_submit=not edit_mode):
            
            # Inputs restantes que precisam ser resetados na submissão
            loja_selecionada = st.selectbox("Loja Responsável", 
                                                 LOJAS_DISPONIVEIS, 
                                                 index=LOJAS_DISPONIVEIS.index(default_loja) if default_loja in LOJAS_DISPONIVEIS else 0,
                                                 key="input_loja_form")
            data_input = st.date_input("Data da Transação (Lançamento)", value=default_data, key="input_data_form")
            cliente = st.text_input("Nome do Cliente (ou Descrição)", value=default_cliente, key="input_cliente_form")
            forma_pagamento = st.selectbox("Forma de Pagamento", 
                                                 FORMAS_PAGAMENTO, 
                                                 index=FORMAS_PAGAMENTO.index(default_forma) if default_forma in FORMAS_PAGAMENTO else 0,
                                                 key="input_forma_pagamento_form")
            
            
            if status_selecionado == "Realizada":
                 # Se for Realizada, a Data Pagamento É a Data da Transação
                data_pagamento_final = data_input
            elif status_selecionado == "Pendente" and data_pagamento_final is None:
                # Se for Pendente SEM Data Prevista, garantimos que a forma de pagamento é 'Pendente' para o registro
                forma_pagamento = "Pendente" 
            
            # Valor final (apenas exibição, o valor real vem de fora do form)
            st.caption(f"Valor Final da Movimentação: R$ {valor_final_movimentacao:,.2f}")


            # --- Botões de Submissão ---
            if edit_mode:
                col_save, col_cancel = st.columns(2)
                with col_save:
                    enviar = st.form_submit_button("💾 Salvar", type="primary", use_container_width=True, help="Salvar Edição")
                with col_cancel:
                    cancelar = st.form_submit_button("❌ Cancelar", type="secondary", use_container_width=True, help="Cancelar Edição")
            else:
                enviar = st.form_submit_button("Adicionar e Salvar", type="primary", use_container_width=True, help="Adicionar Nova Movimentação e Salvar")
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
                        if original_row["Status"] == "Realizada" and status_selecionado == "Pendente" and original_row["Tipo"] == "Entrada":
                            try:
                                # Reverte o estoque (credita)
                                # Garantindo que o valor seja avaliado corretamente (pode ser string de JSON)
                                produtos_vendidos_antigos = ast.literal_eval(original_row['Produtos Vendidos'])
                                for item in produtos_vendidos_antigos:
                                    if item.get("Produto_ID"): # Só credita se tiver ID de estoque
                                        ajustar_estoque(item["Produto_ID"], item["Quantidade"], "creditar")
                            except: pass
                            
                        # Se status continua Realizada, ajusta a diferença
                        elif original_row["Status"] == "Realizada" and status_selecionado == "Realizada" and original_row["Tipo"] == "Entrada":
                            # 1. Credita o estoque antigo (se existia)
                            try:
                                produtos_vendidos_antigos = ast.literal_eval(original_row['Produtos Vendidos'])
                                for item in produtos_vendidos_antigos:
                                    if item.get("Produto_ID"):
                                        ajustar_estoque(item["Produto_ID"], item["Quantidade"], "creditar")
                            except: pass
                            
                            # 2. Debita o novo estoque (se houver lista atualizada e itens com ID)
                            if produtos_vendidos_json:
                                produtos_vendidos_novos = json.loads(produtos_vendidos_json)
                                for item in produtos_vendidos_novos:
                                    if item.get("Produto_ID"):
                                        ajustar_estoque(item["Produto_ID"], item["Quantidade"], "debitar")
                            
                            if salvar_produtos_no_github(st.session_state.produtos, "Ajuste de estoque por edição de venda"):
                                inicializar_produtos.clear()
                                st.cache_data.clear() # Limpa o cache de dados para refletir mudanças no Livro Caixa
                                
                        # LÓGICA DE DÉBITO INICIAL (Nova Realizada)
                        elif not edit_mode and tipo == "Entrada" and status_selecionado == "Realizada" and st.session_state.lista_produtos:
                            if produtos_vendidos_json:
                                produtos_vendidos_novos = json.loads(produtos_vendidos_json)
                                for item in produtos_vendidos_novos:
                                    if item.get("Produto_ID"): # Só debita se tiver ID de estoque
                                        ajustar_estoque(item["Produto_ID"], item["Quantidade"], "debitar")
                            if salvar_produtos_no_github(st.session_state.produtos, "Débito de estoque por nova venda"):
                                inicializar_produtos.clear()
                                st.cache_data.clear() # Limpa o cache de dados para refletir mudanças no Livro Caixa


                    # MONTAGEM FINAL DA LINHA
                    
                    nova_linha_data = {
                        "Data": data_input,
                        "Loja": loja_selecionada, 
                        "Cliente": cliente_desc, # Usa o cliente do formulário
                        "Valor": valor_armazenado, 
                        "Forma de Pagamento": forma_pagamento,
                        "Tipo": tipo,
                        "Produtos Vendidos": produtos_vendidos_json,
                        "Categoria": categoria_selecionada,
                        "Status": status_selecionado, # Usa o status que está fora do form
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
                            # Tenta usar json.loads, mas usa ast.literal_eval como fallback
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
                                    if salvar_produtos_no_github(st.session_state.produtos, "Crédito de estoque por exclusão de venda"): 
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
            st.header("🧾 Gerenciamento e Relatório de Dívidas Pendentes")
            
            df_pendente_completo = df_exibicao[df_exibicao["Status"] == "Pendente"].copy()
            
            if df_pendente_completo.empty:
                st.info("🎉 Não há Contas a Pagar ou Receber pendentes!")
            else:
                
                # --- CALCULO DO RESUMO PENDENTE ---
                total_a_receber = df_pendente_completo[df_pendente_completo["Tipo"] == "Entrada"]["Valor"].sum()
                total_a_pagar = abs(df_pendente_completo[df_pendente_completo["Tipo"] == "Saída"]["Valor"].sum()) 
                
                st.markdown("---")
                st.subheader("💰 Resumo das Dívidas (Impacto no Fluxo de Caixa Futuro)")
                col_rp1, col_rp2, col_rp3 = st.columns(3)
                
                col_rp1.metric("Total a Receber Pendente", f"R$ {total_a_receber:,.2f}", delta_color="off")
                col_rp2.metric("Total a Pagar Pendente", f"R$ {total_a_pagar:,.2f}", delta_color="off")
                col_rp3.metric("Saldo Líquido Pendente", f"R$ {total_a_receber - total_a_pagar:,.2f}", delta=f"R$ {total_a_receber - total_a_pagar:,.2f}" if total_a_receber - total_a_pagar != 0 else None, delta_color="normal")
                
                st.markdown("---")
                
                # --- GRÁFICO: Distribuição de Dívidas por Loja/Tipo ---
                st.subheader("📈 Distribuição de Dívidas Pendentes por Loja")
                
                df_grafico_dividas = df_pendente_completo.copy()
                df_grafico_dividas['Valor Absoluto'] = df_grafico_dividas['Valor'].abs()
                df_grafico_dividas['Tipo Movimentação'] = df_grafico_dividas['Tipo'].apply(lambda x: 'Receber' if x == 'Entrada' else 'Pagar')
                
                fig_dividas_loja = px.bar(
                    df_grafico_dividas,
                    x='Loja',
                    y='Valor Absoluto',
                    color='Tipo Movimentação',
                    title='Total Pendente por Loja (A Receber vs. A Pagar)',
                    labels={'Valor Absoluto': 'Valor Pendente (R$)', 'Loja': 'Loja'},
                    color_discrete_map={'Receber': 'green', 'Pagar': 'red'},
                    height=400
                )
                fig_dividas_loja.update_layout(xaxis={'categoryorder':'total descending'})
                st.plotly_chart(fig_dividas_loja, use_container_width=True)
                
                st.markdown("---")
                st.subheader("📋 Detalhamento e Conclusão de Dívidas")
                
                # --- Separação Contas a Receber e Pagar ---
                df_receber = df_pendente_completo[df_pendente_completo["Tipo"] == "Entrada"].reset_index(drop=True)
                df_pagar = df_pendente_completo[df_pendente_completo["Tipo"] == "Saída"].reset_index(drop=True)
                
                st.markdown("##### 📥 Contas a Receber (Vendas Pendentes)")
                
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
                st.markdown("##### 📤 Contas a Pagar (Despesas Pendentes)")
                
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
                st.markdown("### ✅ Concluir Pagamentos Selecionados")

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
                        
                        submeter_conclusao = st.form_submit_button("Concluir e Salvar", type="primary", help="Concluir Pagamentos Selecionados e Salvar")

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
                                        if salvar_produtos_no_github(st.session_state.produtos, "Débito de estoque por liquidação de dívida"): 
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
                df_acumulado = df_acumulado[df_filtrado_loja['Status'] == 'Realizada']

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
                                # Tenta usar json.loads, mas usa ast.literal_eval como fallback
                                try:
                                    produtos = json.loads(row['Produtos Vendidos'])
                                except json.JSONDecodeError:
                                    produtos = ast.literal_eval(row['Produtos Vendidos'])

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
    ["Livro Caixa", "Produtos", "Histórico de Compras"], # ADIÇÃO: Nova opção no menu
    key='main_page_select_widget'
)

if main_tab_select == "Livro Caixa":
    livro_caixa()
elif main_tab_select == "Produtos":
    gestao_produtos()
elif main_tab_select == "Histórico de Compras": # ADIÇÃO: Roteamento para a nova página
    historico_compras()
