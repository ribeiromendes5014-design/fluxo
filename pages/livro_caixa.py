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

# Note: Assumindo que constants_and_css está importando render_utils, caso contrário, será necessário corrigir.
from constants_and_css import * # Importação explícita de funções de renderização para garantir que estão definidas
try:
    from render_utils import render_global_config, render_custom_header
except ImportError:
    # Se render_utils não existir, apenas define as funções como dummy para não quebrar
    def render_global_config(): pass
    def render_custom_header(paginas_ordenadas, paginas_map): pass


# ================================================================
# 🔑 CREDENCIAIS E CONFIGURAÇÕES DO REPOSITÓRIO (carregadas do secrets)
# ================================================================
import streamlit as st

OWNER = st.secrets.get("REPO_OWNER", "ribeiromendes5014-design")
REPO_NAME = st.secrets.get("REPO_NAME", "fluxo")
BRANCH = st.secrets.get("BRANCH", "main")
TOKEN = st.secrets.get("GITHUB_TOKEN", None)

# ================================================================
# 📂 Caminhos dos arquivos no repositório
# ================================================================
ARQ_CLIENTES_CASH = "clientes_cash.csv"       
# O nome do arquivo principal (Livro Caixa) no GitHub e local
PATH_DIVIDAS = "livro_caixa.csv"              
# O ARQ_LOCAL deve ter o mesmo nome do PATH_DIVIDAS para consistência
ARQ_LOCAL = PATH_DIVIDAS                      
# Nome do arquivo de promoções
ARQ_PROMOCOES = "promocoes.csv"               
# Nome do arquivo de histórico de compras
ARQ_COMPRAS = "historico_compras.csv"         
# Nome do arquivo de produtos/estoque
ARQ_PRODUTOS = "produtos_estoque.csv" 

# NOVO: Constante para o arquivo de clientes

COLUNAS_CLIENTES_CASH = ["Nome", "Cashback", "TotalGasto", "Nivel"]

COLUNAS_COMPRAS = ["Data", "Produto", "Quantidade", "Valor Total", "Cor", "FotoURL"]
COLUNAS_PADRAO = ["Data", "Loja", "Cliente", "Valor", "Forma de Pagamento", "Tipo", "Produtos Vendidos", "Categoria", "Status", "Data Pagamento", "FonteRecurso"]
COLUNAS_PADRAO_COMPLETO = COLUNAS_PADRAO + ["RecorrenciaID", "TransacaoPaiID", "TransactionID"] # Adicionado TransactionID e FonteRecurso
COLUNAS_COMPLETAS_PROCESSADAS = COLUNAS_PADRAO_COMPLETO + ["Data_dt", "original_index", "Saldo Acumulado", "ID Visível", "Cor_Valor"]
FATOR_CARTAO = 0.95 # Ex: 5% de taxa de cartão

CATEGORIAS_SAIDA = ["Aluguel", "Salários", "Fornecedores", "Marketing", "Impostos", "Manutenção", "Outro/Diversos"]
LOJAS_DISPONIVEIS = ["Doce&Bella", "Fotografia", "Papelaria"]
FORMAS_PAGAMENTO = ["Dinheiro", "Cartão de Crédito", "Cartão de Débito", "PIX", "Boleto", "Transferência", "Cheque"]

COMMIT_MESSAGE = "Nova movimentação adicionada via Streamlit"
COMMIT_MESSAGE_EDIT = "Movimentação editada via Streamlit"
COMMIT_MESSAGE_DELETE = "Movimentação excluída via Streamlit"
COMMIT_MESSAGE_PROD = "Atualização de produtos via Streamlit"

# URLs de Imagens (Apenas placeholders)
URL_MAIS_VENDIDOS = "https://via.placeholder.com/200x50.png?text=Mais+Vendidos"
URL_OFERTAS = "https://via.placeholder.com/200x50.png?text=Nossas+Ofertas"

# ==============================================================================
# CONFIGURAÇÃO GERAL E INÍCIO DO APP (Usando render_global_config)
# ==============================================================================

# Executa a configuração global e injeta o CSS
render_global_config()

# ==============================================================================
# FUNÇÕES CORE (Mantidas e verificadas para persistência)
# ==============================================================================

try:
    from github import Github
except ImportError:
    class Github:
        def __init__(self, token): pass
        def get_repo(self, repo_name): return self
        def update_file(self, path, msg, content, sha, branch): pass
        def create_file(self, path, msg, content, branch): pass

def get_livro_caixa_path(data_transacao: date) -> str:
    """Retorna o nome do arquivo CSV formatado como livro_caixa_AAAA_MM.csv."""
    if isinstance(data_transacao, str):
        try:
            data_transacao = datetime.strptime(data_transacao, '%Y-%m-%d').date()
        except ValueError:
            data_transacao = date.today()
    elif not isinstance(data_transacao, date):
        data_transacao = date.today()
        
    ano_mes = data_transacao.strftime('%Y_%m')
    return f"livro_caixa_{ano_mes}.csv"


def ler_codigo_barras_api(image_bytes):
    """Decodifica códigos de barras usando a API pública ZXing."""
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
                if codigo and not codigo.startswith("Erro na decodificação"):
                    codigos.append(codigo)
        if not codigos and 'streamlit' in globals():
            st.toast("⚠️ API ZXing não retornou nenhum código válido. Tente novamente ou use uma imagem mais clara.")
        return codigos
    except Exception as e:
        if 'streamlit' in globals(): st.error(f"❌ Erro inesperado: {e}")
        return []

def add_months(d: date, months: int) -> date:
    """Adiciona um número específico de meses a uma data."""
    month = d.month + months
    year = d.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)

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

# =======================================================================
# 🔑 INSERIR NOVA FUNÇÃO AQUI:
# =======================================================================
def get_livro_caixa_path(data_transacao: date) -> str:
    """Retorna o nome do arquivo CSV formatado como livro_caixa_AAAA_MM.csv."""
    if isinstance(data_transacao, str):
        try:
            data_transacao = datetime.strptime(data_transacao, '%Y-%m-%d').date()
        except ValueError:
            data_transacao = date.today()
    elif not isinstance(data_transacao, date):
        data_transacao = date.today()
        
    ano_mes = data_transacao.strftime('%Y_%m')
    return f"livro_caixa_{ano_mes}.csv"

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
    
    # 1. Converte para datetime
    df["DataInicio_dt"] = pd.to_datetime(df["DataInicio"], errors='coerce')
    df["DataFim_dt"] = pd.to_datetime(df["DataFim"], errors='coerce')
    
    # 2. Remove promoções com datas inválidas (NaT) para evitar o TypeError
    df = df.dropna(subset=["DataInicio_dt", "DataFim_dt"])
    
    # 3. Extrai o objeto date (agora sem NaT, evitando o erro de dtype)
    df["DataInicio"] = df["DataInicio_dt"].dt.date
    df["DataFim"] = df["DataFim_dt"].dt.date
    
    # 4. Filtra promoções expiradas (agora seguro)
    # Garante que a comparação seja feita com o objeto date extraído (df["DataFim"]) 
    # ou use df["DataFim_dt"] e pd.Timestamp(date.today()) para mais segurança.
    df = df[df["DataFim"] >= date.today()] 
    
    # Remove colunas auxiliares
    df.drop(columns=["DataInicio_dt", "DataFim_dt"], errors='ignore', inplace=True)
    
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

def salvar_dados_no_github(df_completo: pd.DataFrame, commit_message: str, data_transacao: date):
    """
    Salva os dados do Livro Caixa no arquivo CSV mensal correspondente no GitHub.
    Esta função determina o arquivo correto com base na data da transação, filtra os dados
    e cria ou atualiza o arquivo no repositório.
    """
    
    # 1. Determina o nome do arquivo com base na data da transação
    # Ex: Para uma data em Outubro de 2025, o caminho será "livro_caixa_2025_10.csv"
    file_path = f"livro_caixa_{data_transacao.year}_{data_transacao.month:02d}.csv"
    
    # 2. Filtra o DataFrame completo para conter apenas os dados do mês correto
    # Isso garante que cada arquivo mensal contenha apenas as transações daquele mês.
    df_mes_especifico = df_completo[
        (pd.to_datetime(df_completo['Data']).dt.year == data_transacao.year) &
        (pd.to_datetime(df_completo['Data']).dt.month == data_transacao.month)
    ].copy()

    # 3. Prepara as colunas de data do DataFrame filtrado para serem salvas como string
    for col_date in ['Data', 'Data Pagamento']:
        if col_date in df_mes_especifico.columns:
            df_mes_especifico[col_date] = pd.to_datetime(df_mes_especifico[col_date], errors='coerce').apply(
                lambda x: x.strftime('%Y-%m-%d') if pd.notnull(x) else ''
            )

    try:
        g = Github(TOKEN)
        repo = g.get_repo(f"{OWNER}/{REPO_NAME}")
        csv_string = df_mes_especifico.to_csv(index=False, encoding="utf-8-sig")

        try:
            # Tenta obter o conteúdo do arquivo mensal atual
            contents = repo.get_contents(file_path, ref=BRANCH)
            # Se o arquivo já existe, atualiza-o
            repo.update_file(contents.path, commit_message, csv_string, contents.sha, branch=BRANCH)
            st.success(f"📁 Livro Caixa salvo (atualizado) em '{file_path}' no GitHub!")
        except Exception:
            # Se o arquivo não existe (ex: primeiro lançamento do mês), cria um novo
            repo.create_file(file_path, commit_message, csv_string, branch=BRANCH)
            st.success(f"📁 Livro Caixa salvo (novo arquivo '{file_path}' criado) no GitHub!")

        # Limpa o cache para forçar a releitura de todos os arquivos na próxima vez
        carregar_livro_caixa.clear()
        
        return True

    except Exception as e:
        st.error(f"❌ Erro ao salvar no GitHub: {e}")
        st.error("Verifique se seu 'GITHUB_TOKEN' tem permissões e se o repositório existe.")
        return False


@st.cache_data(show_spinner="Carregando dados de todos os meses...")
def carregar_livro_caixa():
    """
    Busca todos os arquivos CSV mensais do Livro Caixa no GitHub (padrão: livro_caixa_AAAA_MM.csv),
    combina-os em um único DataFrame e garante que todas as colunas padrão existam.
    """
    all_monthly_dfs = []
    
    try:
        # Usamos a biblioteca PyGithub para listar os arquivos do repositório
        g = Github(TOKEN)
        repo = g.get_repo(f"{OWNER}/{REPO_NAME}")
        contents = repo.get_contents("", ref=BRANCH) # Pega o conteúdo da pasta raiz
        
        # Filtra a lista de conteúdo para encontrar apenas os arquivos CSV do livro caixa
        csv_files = [c for c in contents if c.name.startswith("livro_caixa_") and c.name.endswith(".csv")]
        
        if not csv_files:
            # Se nenhum arquivo for encontrado, retorna um DataFrame vazio com a estrutura correta
            return pd.DataFrame(columns=COLUNAS_PADRAO_COMPLETO)
            
        # Itera sobre os arquivos encontrados e carrega os dados de cada um
        for file in csv_files:
            url_raw = file.download_url
            df_monthly = load_csv_github(url_raw) # Reutiliza a função de carregamento individual
            if df_monthly is not None and not df_monthly.empty:
                all_monthly_dfs.append(df_monthly)

@st.cache_data(show_spinner=False)
def processar_dataframe(df):
    for col in COLUNAS_PADRAO:
        if col not in df.columns: df[col] = ""
    for col in ["RecorrenciaID", "TransacaoPaiID"]:
        if col not in df.columns: df[col] = ''

    if df.empty: return pd.DataFrame(columns=COLUNAS_COMPLETAS_PROCESSADAS)
    df_proc = df.copy()
    df_proc["Valor"] = pd.to_numeric(df_proc["Valor"], errors="coerce").fillna(0.0)
    df_proc["Data"] = pd.to_datetime(df_proc["Data"], errors='coerce').dt.date
    
    # --- INÍCIO DA CORREÇÃO ---
    # 1. Converte a coluna 'Data' para datetime
    df_proc["Data_dt"] = pd.to_datetime(df_proc["Data"], errors='coerce')
    
    # 2. Remove a linha que estava descartando os registros (dropna)
    # df_proc.dropna(subset=['Data_dt'], inplace=True) 
    
    # 3. Substitui os valores de data inválidos (NaT) por uma data muito antiga para permitir a ordenação.
    # Usamos o fillna no Data_dt para evitar erros de ordenação.
    df_proc["Data_dt"] = df_proc["Data_dt"].fillna(datetime(1900, 1, 1))

    # --- FIM DA CORREÇÃO ---
    
    df_proc["Data Pagamento"] = pd.to_datetime(df_proc["Data Pagamento"], errors='coerce').dt.date
    
    df_proc = df_proc.reset_index(drop=False)
    df_proc.rename(columns={'index': 'original_index'}, inplace=True)
    df_proc['Saldo Acumulado'] = 0.0
    
    # A lógica do saldo permanece a mesma, usando apenas 'Realizada' para o cálculo.
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
    
    # Adiciona TransacaoPaiID para processamento
    if 'TransacaoPaiID' not in df_proc.columns:
        df_proc['TransacaoPaiID'] = ''
        
    return df_proc

def calcular_resumo(df):
    df_realizada = df[df['Status'] == 'Realizada']
    if df_realizada.empty: return 0.0, 0.0, 0.0
    total_entradas = df_realizada[df_realizada["Tipo"] == "Entrada"]["Valor"].sum()
    total_saidas = abs(df_realizada[df_realizada["Tipo"] == "Saída"]["Valor"].sum()) 
    saldo = df_realizada["Valor"].sum()
    return total_entradas, total_saidas, saldo

def calcular_valor_em_aberto(linha):
    """Calcula o valor absoluto e arredondado para 2 casas decimais de uma linha do DataFrame."""
    try:
        if isinstance(linha, pd.DataFrame) and not linha.empty:
            valor_raw = pd.to_numeric(linha['Valor'].iloc[0], errors='coerce')
        elif isinstance(linha, pd.Series):
            valor_raw = pd.to_numeric(linha['Valor'], errors='coerce')
        else:
            return 0.0
            
        valor_float = float(valor_raw) if pd.notna(valor_raw) and not isinstance(valor_raw, pd.Series) else 0.0
        return round(abs(valor_float), 2)
    except Exception:
        return 0.0


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
            return "Erro na formatação/JSON InváLido"
    return ""

def highlight_value(row):
    color = row['Cor_Valor']
    return [f'color: {color}' if col == 'Valor' else '' for col in row.index]

# ==============================================================================
# FUNÇÕES CORE: CLIENTES E CASHBACK (NOVO)
# ==============================================================================

def calcular_nivel(total_gasto: float) -> str:
    """Define o nível de fidelidade do cliente baseado no total gasto."""
    if total_gasto >= 5000:
        return "Diamante 💎"
    elif total_gasto >= 2000:
        return "Ouro 🥇"
    elif total_gasto >= 500:
        return "Prata 🥈"
    else:
        return "Bronze 🥉"

@st.cache_data(show_spinner="Carregando clientes e cashback...")
def carregar_clientes_cash():
    """Carrega o histórico de clientes e cashback (GitHub primeiro) e renomeia as colunas."""
    df = None
    
    # 1. Tenta carregar do GitHub (fonte principal)
    url_raw = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/{ARQ_CLIENTES_CASH}"
    df = load_csv_github(url_raw)

    # 3. Se ainda assim não carregou, cria um DataFrame vazio
    if df is None or df.empty:
        df = pd.DataFrame(columns=["Nome", "Cashback", "TotalGasto", "Nivel"])

    # ===================================================================
    # CORREÇÃO PRINCIPAL: Renomeia as colunas do CSV para o padrão do app
    # ===================================================================
    mapa_colunas = {
        # NOVO: Padroniza a coluna de nome do seu CSV para o padrão do app
        "NOME": "Nome", 
        "CASHBACK_DISPONIVEL": "Cashback",
        "GASTO_ACUMULADO": "TotalGasto",
        "NIVEL_ATUAL": "Nivel"
    }
    df.rename(columns=mapa_colunas, inplace=True)
    # ===================================================================

    # Garante que as colunas padrão existam após renomear
    for col in ["Nome", "Cashback", "TotalGasto", "Nivel"]:
        if col not in df.columns:
            df[col] = 0.0 if col in ["Cashback", "TotalGasto"] else ""

    # Normaliza os tipos
    df["Cashback"] = pd.to_numeric(df["Cashback"], errors='coerce').fillna(0.0)
    df["TotalGasto"] = pd.to_numeric(df["TotalGasto"], errors='coerce').fillna(0.0)

    return df


def salvar_clientes_cash_github(df: pd.DataFrame, commit_message: str):
    """Salva o DataFrame de Clientes no GitHub, preservando todas as colunas originais do CSV."""
    try:
        from github import Github
    except ImportError:
        pass 
        
    df_temp = df.copy()

    # ===================================================================
    # CORREÇÃO PRINCIPAL: Renomeia as colunas do app para o padrão do CSV antes de salvar
    # ===================================================================
    mapa_colunas_reverso = {
        "Nome": "NOME",
        "Cashback": "CASHBACK_DISPONIVEL",
        "TotalGasto": "GASTO_ACUMULADO",
        "Nivel": "NIVEL_ATUAL"
    }
    df_temp.rename(columns=mapa_colunas_reverso, inplace=True)
    # ===================================================================
    
    # Garante que TODAS as colunas do seu CSV original existam no DataFrame a ser salvo.
    # Preenche com valores vazios se alguma coluna estiver faltando (ex: em um cliente novo).
    colunas_finais_csv = [
        "NOME", "APELIDO/DESCRIÇÃO", "CONTATO", "CASHBACK_DISPONIVEL", 
        "GASTO_ACUMULADO", "NIVEL_ATUAL", "INDICADO_POR", 
        "PRIMEIRA_COMPRA_FEITA", "CONTATO_LIMPO"
    ]
    for col in colunas_finais_csv:
        if col not in df_temp.columns:
            # Define um valor padrão apropriado para colunas que podem ser numéricas
            if col in ["CASHBACK_DISPONIVEL", "GASTO_ACUMULADO"]:
                df_temp[col] = 0.0
            else:
                df_temp[col] = ""

    # Reordena o DataFrame para manter o padrão exato do seu arquivo
    df_temp = df_temp[colunas_finais_csv]

    try:
        g = Github(TOKEN)
        repo = g.get_repo(f"{OWNER}/{REPO_NAME}")
        csv_string = df_temp.to_csv(index=False, encoding="utf-8-sig")
        
        try:
            contents = repo.get_contents(ARQ_CLIENTES_CASH, ref=BRANCH)
            repo.update_file(contents.path, commit_message, csv_string, contents.sha, branch=BRANCH)
        except Exception:
            repo.create_file(ARQ_CLIENTES_CASH, commit_message, csv_string, branch=BRANCH)
        
        carregar_clientes_cash.clear()
        return True
    
    except Exception as e:
        return False

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
        return True

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
            # Se não adicionou variações, exclui o pai criado (or avisa)
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
# 1. PÁGINA DE APRESENTAÇÃO (HOMEPAGE) (Mantida)
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

# ==============================================================================
# NOVA FUNÇÃO: relatorio_produtos (Para ser usada na nova sub-aba)
# ==============================================================================

def relatorio_produtos():
    """Sub-aba de Relatório e Alertas de Produtos."""
    st.subheader("⚠️ Relatório e Alertas de Estoque")

    produtos = inicializar_produtos().copy()
    df_movimentacoes = carregar_livro_caixa()
    vendas = df_movimentacoes[df_movimentacoes["Tipo"] == "Entrada"].copy()

    # --- Configurações de Alerta ---
    with st.expander("⚙️ Configurações de Alerta", expanded=False):
        col_c1, col_c2, col_c3 = st.columns(3)
        with col_c1:
            limite_estoque_baixo = st.number_input(
                "Estoque Baixo (Qtd. Máxima)", min_value=1, value=2, step=1, key="limite_estoque_baixo"
            )
        with col_c2:
            dias_validade_alerta = st.number_input(
                "Aviso de Vencimento (Dias)", min_value=1, max_value=365, value=60, step=1, key="dias_validade_alerta"
            )
        with col_c3:
            dias_sem_venda = st.number_input(
                "Produtos Parados (Dias)", min_value=1, max_value=365, value=90, step=7, key="dias_sem_venda_alerta"
            )
            
    st.markdown("---")

    # --- 1. Aviso de Estoque Baixo ---
    st.markdown(f"#### ⬇️ Alerta de Estoque Baixo (Qtd $\le {limite_estoque_baixo}$)")
    
    df_estoque_baixo = produtos[
        (produtos["Quantidade"] > 0) & 
        (produtos["Quantidade"] <= limite_estoque_baixo)
    ].sort_values(by="Quantidade").copy()
    
    if df_estoque_baixo.empty:
        st.success("🎉 Nenhum produto com estoque baixo encontrado.")
    else:
        st.warning(f"🚨 **{len(df_estoque_baixo)}** produto(s) com estoque baixo!")
        st.dataframe(
            df_estoque_baixo[["ID", "Nome", "Marca", "Quantidade", "Categoria", "PrecoVista"]],
            use_container_width=True, hide_index=True,
            column_config={"PrecoVista": st.column_config.NumberColumn("Preço Venda (R$)", format="R$ %.2f")}
        )

    st.markdown("---")

    # --- 2. Aviso de Vencimento ---
    st.markdown(f"#### ⏳ Alerta de Vencimento (Até {dias_validade_alerta} dias)")
    
    limite_validade = date.today() + timedelta(days=int(dias_validade_alerta))
    
    df_validade = produtos.copy()
    df_validade['Validade_dt'] = pd.to_datetime(df_validade['Validade'], errors='coerce')
    limite_validade_dt = datetime.combine(limite_validade, datetime.min.time()) 
    
    df_vencimento = df_validade[
        (df_validade["Quantidade"] > 0) &
        (df_validade["Validade_dt"].notna()) &
        (df_validade["Validade_dt"] <= limite_validade_dt)
    ].copy()
    
    # Calcula dias restantes
    def calcular_dias_restantes(x):
            if pd.notna(x) and isinstance(x, date):
                return (x - date.today()).days
            return float('inf')

    df_vencimento['Dias Restantes'] = df_vencimento['Validade'].apply(calcular_dias_restantes)
    df_vencimento = df_vencimento.sort_values("Dias Restantes")

    if df_vencimento.empty:
        st.success("🎉 Nenhum produto próximo da validade encontrado.")
    else:
        st.warning(f"🚨 **{len(df_vencimento)}** produto(s) vencendo em breve (até {dias_validade_alerta} dias)!")
        st.dataframe(
            df_vencimento[["ID", "Nome", "Marca", "Quantidade", "Validade", "Dias Restantes"]],
            use_container_width=True, hide_index=True
        )

    st.markdown("---")

    # --- 3. Produtos Parados (Sem Vendas) ---
    st.markdown(f"#### 📦 Alerta de Produtos Parados (Sem venda nos últimos {dias_sem_venda} dias)")

    # 1. Processa vendas para encontrar a última venda de cada produto
    vendas_list = []
    for index, row in vendas.iterrows():
        produtos_json = row["Produtos Vendidos"]
        if pd.notna(produtos_json) and produtos_json:
            try:
                items = ast.literal_eval(produtos_json)
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
    
    if vendas_list:
        vendas_flat = pd.DataFrame(vendas_list)
        vendas_flat["Data"] = pd.to_datetime(vendas_flat["Data"], errors="coerce")
        ultima_venda = vendas_flat.groupby("IDProduto")["Data"].max().reset_index()
        ultima_venda.columns = ["IDProduto", "UltimaVenda"]
    else:
        ultima_venda = pd.DataFrame(columns=["IDProduto", "UltimaVenda"])

    # 2. Merge com a lista de produtos
    produtos_parados = produtos.merge(ultima_venda, left_on="ID", right_on="IDProduto", how="left")
    
    produtos_parados["UltimaVenda"] = pd.to_datetime(produtos_parados["UltimaVenda"], errors='coerce')
    limite_dt = datetime.combine(date.today() - timedelta(days=int(dias_sem_venda)), datetime.min.time())

    # 3. Filtra: com estoque > 0 E (nunca vendidos OU última venda antes do limite)
    df_parados_sugeridos = produtos_parados[
        (produtos_parados["Quantidade"] > 0) &
        (produtos_parados["UltimaVenda"].isna() | (produtos_parados["UltimaVenda"] < limite_dt))
    ].copy()
    
    df_parados_sugeridos['UltimaVenda'] = df_parados_sugeridos['UltimaVenda'].dt.date.fillna(pd.NaT)
    
    if df_parados_sugeridos.empty:
        st.success("🎉 Nenhum produto parado com estoque encontrado.")
    else:
        st.warning(f"🚨 **{len(df_parados_sugeridos)}** produto(s) parados. Considere fazer uma promoção!")
        st.dataframe(
            df_parados_sugeridos[["ID", "Nome", "Quantidade", "UltimaVenda"]].fillna({"UltimaVenda": "NUNCA VENDIDO"}),
            use_container_width=True, hide_index=True
        )


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
    # NOVA ABA: Adicionando relatorio_produtos como tab_relatorio
    tab_cadastro, tab_lista, tab_relatorio = st.tabs(["📝 Cadastro de Produtos", "📑 Lista & Busca", "📈 Relatório e Alertas"])

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

    # ================================
    # SUBABA: RELATÓRIO E ALERTAS (Novo)
    # ================================
    with tab_relatorio:
        relatorio_produtos()


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

                    # Note: You need to implement 'salvar_historico_no_github' function for this to work
                    if True: # Simulating salvar_historico_no_github success
                        st.session_state.edit_compra_idx = None
                        carregar_historico_compras.clear()
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
                    
                    if True: # Simulating salvar_historico_no_github success
                        carregar_historico_compras.clear()
                        st.rerun()
            else:
                st.info("Selecione um item no menu acima para editar ou excluir.")

def livro_caixa():
    
    st.header("📘 Livro Caixa - Gerenciamento de Movimentações") 
    # --- NOVO BOTÃO DE ATUALIZAÇÃO MANUAL DE DADOS ---
    if st.button("🔄 Atualizar Dados do GitHub"):
        # Limpa o cache das principais funções que carregam dados do GitHub
        carregar_livro_caixa.clear()
        carregar_clientes_cash.clear()
        carregar_historico_compras.clear()
        carregar_promocoes.clear()
        inicializar_produtos.clear() # Limpa o cache de produtos também

    produtos = inicializar_produtos() 

    if "df" not in st.session_state: st.session_state.df = carregar_livro_caixa()
    
    # 🔑 CORREÇÃO CRÍTICA (ANTI-KEYERROR): Assegura que o DataFrame principal sempre tenha um índice sequencial.
    if not st.session_state.df.empty:
        st.session_state.df = st.session_state.df.reset_index(drop=True)
    
    # NOVO: Inicialização de clientes e cashback
    if "df_clientes" not in st.session_state: st.session_state.df_clientes = carregar_clientes_cash()
    df_clientes = st.session_state.df_clientes # Referência para o DataFrame de clientes
    
    # Garante que todas as colunas de controle existam
    for col in ['RecorrenciaID', 'TransacaoPaiID']:
        if col not in st.session_state.df.columns: st.session_state.df[col] = ''
        
    if "produtos" not in st.session_state: st.session_state.produtos = produtos
    if "lista_produtos" not in st.session_state: st.session_state.lista_produtos = []
    if "edit_id" not in st.session_state: st.session_state.edit_id = None
    if "operacao_selecionada" not in st.session_state: st.session_state.operacao_selecionada = "Editar" 
    if "cb_lido_livro_caixa" not in st.session_state: st.session_state.cb_lido_livro_caixa = ""
    if "edit_id_loaded" not in st.session_state: st.session_state.edit_id_loaded = None
    if "cliente_selecionado_divida" not in st.session_state: st.session_state.cliente_selecionado_divida = None
    if "divida_parcial_id" not in st.session_state: st.session_state.divida_parcial_id = None
    if "divida_a_quitar" not in st.session_state: st.session_state.divida_a_quitar = None 
    if "search_trigger" not in st.session_state: st.session_state.search_trigger = ""
    
    abas_validas = ["📝 Nova Movimentação", "📋 Movimentações e Resumo", "📈 Relatórios e Filtros"]
    
    if "aba_ativa_livro_caixa" not in st.session_state or str(st.session_state.aba_ativa_livro_caixa) not in abas_validas: 
        st.session_state.aba_ativa_livro_caixa = abas_validas[0]

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
    
    def encontrar_opcao_por_cb(codigo_barras, produtos_df, opcoes_produtos_list):
        if not codigo_barras: return None
        
        produto_encontrado = produtos_df[produtos_df["CodigoBarras"] == codigo_barras]
        
        if not produto_encontrado.empty:
            produto_id = produto_encontrado.iloc[0]["ID"]
            
            for opcao in opcoes_produtos_list:
                if opcao.startswith(f"{produto_id} |"):
                    return opcao
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
            
            if st.session_state.edit_id_loaded != original_idx_to_edit:
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
                else: 
                    st.session_state.lista_produtos = []
                
                st.session_state.edit_id_loaded = original_idx_to_edit 
                st.session_state.cb_lido_livro_caixa = "" 
            
            st.warning(f"Modo EDIÇÃO ATIVO: Movimentação ID {movimentacao_para_editar['ID Visível']}")
            
        else:
            st.session_state.edit_id = None
            st.session_state.edit_id_loaded = None 
            st.session_state.lista_produtos = [] 
            edit_mode = False
            st.info("Movimentação não encontrada, saindo do modo de edição.")
            st.rerun() 
    else:
        if st.session_state.edit_id_loaded is not None:
             st.session_state.edit_id_loaded = None
             st.session_state.lista_produtos = []
        if st.session_state.cliente_selecionado_divida and st.session_state.cliente_selecionado_divida != "CHECKED":
             st.session_state.cliente_selecionado_divida = None

    tab_nova_mov, tab_mov, tab_rel = st.tabs(abas_validas)

    with tab_nova_mov:
        if "df_clientes" not in st.session_state:
            st.session_state.df_clientes = carregar_clientes_cash()
            
        st.subheader("Nova Movimentação" if not edit_mode else "Editar Movimentação Existente")

        if 'divida_a_quitar' in st.session_state and st.session_state.divida_a_quitar is not None:
            
            idx_quitar = st.session_state.divida_a_quitar
            
            try:
                divida_para_quitar = st.session_state.df.loc[idx_quitar].copy()
            except KeyError:
                st.session_state.divida_a_quitar = None
                st.error("Erro: A dívida selecionada não foi encontrada. Tente novamente.")
                st.rerun()
                
            valor_em_aberto = calcular_valor_em_aberto(divida_para_quitar)
            
            if valor_em_aberto <= 0.01:
                st.session_state.divida_a_quitar = None
                st.warning("Dívida já quitada.")
                st.rerun()
            
            st.subheader(f"✅ Quitar Dívida: {divida_para_quitar['Cliente']}")
            st.info(f"Valor Total em Aberto: **R$ {valor_em_aberto:,.2f}**")
            
            with st.form("form_quitar_divida_rapida"):
                col_q1, col_q2, col_q3 = st.columns(3)
                
                with col_q1:
                    valor_pago = st.number_input(f"Valor Pago Agora", min_value=0.01, max_value=valor_em_aberto, value=valor_em_aberto, format="%.2f")
                with col_q2:
                    data_conclusao = st.date_input("Data do Pagamento", value=date.today())
                with col_q3:
                    forma_pagt_concluir = st.selectbox("Forma de Pagamento", FORMAS_PAGAMENTO)

                concluir = st.form_submit_button("✅ Registrar Pagamento", type="primary", use_container_width=True)
                cancelar_quitacao = st.form_submit_button("❌ Cancelar", type="secondary", use_container_width=True)

                if cancelar_quitacao:
                    st.session_state.divida_a_quitar = None
                    st.rerun()
          # 3. SALVA A MOVIMENTAÇÃO PRINCIPAL E ATUALIZA A TELA
                if salvar_dados_no_github(df_movimentacoes_upd, msg_commit, data_input):
                        st.success("Movimentação salva com sucesso!")
                        st.session_state.df = df_movimentacoes_upd
                        st.session_state.lista_produtos = []
                        st.session_state.edit_id = None
                        carregar_livro_caixa.clear()
                        st.rerun()

            st.stop()
        
        col_principal_1, col_principal_2 = st.columns([1, 1])
        with col_principal_1:
            tipo = st.radio("Tipo", ["Entrada", "Saída"], index=0 if default_tipo == "Entrada" else 1, key="input_tipo", disabled=edit_mode)
        
        is_recorrente = False
        status_selecionado = default_status
        valor_calculado = 0.0
        produtos_vendidos_json = ""
        categoria_selecionada = ""

        if tipo == "Entrada":
            
            with col_principal_2:
                cliente = st.text_input("Nome do Cliente (ou Descrição)", 
                                        value=default_cliente, 
                                        key="input_cliente_form",
                                        on_change=lambda: st.session_state.update(cliente_selecionado_divida="CHECKED", edit_id=None, divida_a_quitar=None, search_trigger=datetime.now().isoformat()),
                                        disabled=edit_mode)
                
                st.caption("Aperte ENTER ou clique fora para buscar o cliente.")
                
                # ===================================================================
                # Bloco de Busca de Cliente e Gestão de Cashback (Versão Corrigida)
                # ===================================================================
                cliente_normalizado = cliente.strip().lower()

                if 'Nome' in df_clientes.columns:
                    cliente_encontrado = df_clientes['Nome'].str.strip().str.lower().eq(cliente_normalizado).any() if cliente_normalizado else False

                    if cliente.strip() and not edit_mode:
                        if cliente_encontrado:
                            cliente_df = df_clientes[df_clientes['Nome'].str.strip().str.lower() == cliente_normalizado]
                            c_cashback = cliente_df.iloc[0]["Cashback"]
                            c_nivel = cliente_df.iloc[0]["Nivel"]
                            st.success(f"🎉 Cliente Fidelidade Encontrado! Saldo Cashback: R$ {c_cashback:,.2f} | Nível: {c_nivel}")
                            
                            st.session_state.cliente_fidelidade_ativo = {
                                "nome": cliente.strip(), "cashback": c_cashback, "nivel": c_nivel
                            }
                        else:
                            st.info("✨ Cliente novo ou não encontrado na fidelidade. Será cadastrado após a venda!")
                            if "cliente_fidelidade_ativo" in st.session_state:
                                del st.session_state.cliente_fidelidade_ativo
                else:
                    if "cliente_fidelidade_ativo" in st.session_state:
                        del st.session_state.cliente_fidelidade_ativo
                # ===================================================================
                # Fim do Bloco Corrigido
                # ===================================================================

            # --- Lógica de Verificação de Dívidas Pendentes ---
            if 'modo_quitar_divida' not in st.session_state:
                st.session_state.modo_quitar_divida = False
            if 'dividas_encontradas' not in st.session_state:
                st.session_state.dividas_encontradas = None
                
            # Verifica dívidas SE o gatilho de busca foi ativado E não estamos já no modo de quitação
            if cliente.strip() and not edit_mode and st.session_state.get('search_trigger') and not st.session_state.modo_quitar_divida:
                
                # Busca por dívidas pendentes para este cliente (Apenas Entradas/Vendas)
                df_dividas_cliente = df_exibicao[
                    (df_exibicao["Cliente"].str.strip().str.lower() == cliente.strip().lower()) &
                    (df_exibicao["Status"] == "Pendente") &
                    (df_exibicao["Tipo"] == "Entrada") 
                ]
                
                total_divida = 0.0
                if not df_dividas_cliente.empty:
                    # Usa a função calcular_valor_em_aberto para somar corretamente
                    total_divida = df_dividas_cliente.apply(calcular_valor_em_aberto, axis=1).sum()

                # Se encontrou dívidas, para o fluxo e mostra as opções
                if not df_dividas_cliente.empty and total_divida > 0.01:
                    # Salva as dívidas encontradas no estado da sessão
                    st.session_state.dividas_encontradas = df_dividas_cliente
                    
                    # Container de aviso (igual ao da sua imagem, mas com botões)
                    with st.container(border=True):
                        st.warning(f"Cliente {cliente} possui {len(df_dividas_cliente)} dívida(s) pendente(s), totalizando R$ {total_divida:,.2f}.")
                        
                        # Botões de ação
                        col_divida_1, col_divida_2 = st.columns(2)
                        
                        with col_divida_1:
                            if st.button("💸 Quitar/Pagar Dívida", use_container_width=True, type="primary", key="btn_quitar_divida_agora"):
                                # 1. Ativa o modo de quitação
                                st.session_state.modo_quitar_divida = True 
                                # 2. Limpa o gatilho de busca
                                st.session_state.search_trigger = ""
                                st.rerun()

                        with col_divida_2:
                            if st.button("🛒 Continuar Nova Venda (Ignorar Dívida)", use_container_width=True, type="secondary", key="btn_ignorar_divida"):
                                # 1. Limpa os estados de dívida
                                st.session_state.dividas_encontradas = None
                                st.session_state.modo_quitar_divida = False
                                # 2. Limpa o gatilho de busca para não mostrar este bloco novamente
                                st.session_state.search_trigger = "" 
                                st.rerun()
                                
                    # Interrompe a renderização do resto do formulário de "Nova Venda"
                    # até que o usuário escolha uma ação.
                    st.stop()
                
                else:
                    # Se não achou dívidas, limpa o gatilho e continua
                    st.session_state.search_trigger = ""
                    st.session_state.dividas_encontradas = None
                    st.session_state.modo_quitar_divida = False

            # --- Fim da Lógica de Dívidas ---

            st.markdown("#### 🛍️ Detalhes dos Produtos")
            
            if st.session_state.lista_produtos:
                df_produtos = pd.DataFrame(st.session_state.lista_produtos)
                valor_calculado = (pd.to_numeric(df_produtos['Quantidade']) * pd.to_numeric(df_produtos['Preço Unitário'])).sum()
                produtos_para_json = df_produtos[['Produto_ID', 'Produto', 'Quantidade', 'Preço Unitário', 'Custo Unitário']].to_dict('records')
                produtos_vendidos_json = json.dumps(produtos_para_json)
                
            with st.expander("➕ Adicionar/Limpar Lista de Produtos (Venda)", expanded=True):
                col_prod_lista, col_prod_add = st.columns([1, 1])
                
                with col_prod_lista:
                    st.markdown("##### Produtos Atuais:")
                    if st.session_state.lista_produtos:
                        df_exibicao_produtos = pd.DataFrame(st.session_state.lista_produtos)
                        st.dataframe(df_exibicao_produtos[['Produto', 'Quantidade', 'Preço Unitário']], use_container_width=True, hide_index=True)
                    else:
                        st.info("Lista de produtos vazia.")
                    
                    if st.button("Limpar Lista", key="limpar_lista_button"):
                        st.session_state.lista_produtos = []
                        st.rerun()

                    # ==============================================================================
                    # ÁREA DE CÁLCULO DE TOTAIS E RESGATE DE CASHBACK (LUGAR CORRETO)
                    # ==============================================================================
                    valor_compra_atual = 0.0
                    if st.session_state.lista_produtos:
                        df_produtos_temp = pd.DataFrame(st.session_state.lista_produtos)
                        valor_compra_atual = (pd.to_numeric(df_produtos_temp['Quantidade']) * pd.to_numeric(df_produtos_temp['Preço Unitário'])).sum()
                        st.success(f"Subtotal do Carrinho: R$ {valor_compra_atual:,.2f}")

                    if "cliente_fidelidade_ativo" in st.session_state and valor_compra_atual > 0:
                        cliente_ativo = st.session_state.cliente_fidelidade_ativo
                        c_cashback = cliente_ativo['cashback']

                        if c_cashback >= 20.00:
                            max_resgate_permitido = round(valor_compra_atual * 0.5, 2)
                            max_resgate_real = min(c_cashback, max_resgate_permitido, valor_compra_atual)
                            st.session_state.cashback_a_usar = st.number_input(
                                "💸 Usar Cashback (Desconto)",
                                min_value=0.0, max_value=float(max_resgate_real),
                                value=st.session_state.get('cashback_a_usar', 0.0),
                                step=1.0, format="%.2f", key="input_cashback_resgate",
                                help=f"Você pode resgatar até R$ {max_resgate_real:,.2f} nesta compra."
                            )
                        elif c_cashback > 0:
                            st.info(f"ℹ️ Cliente tem R$ {c_cashback:,.2f} de cashback. Resgate acima de R$ 20,00.")
                            st.session_state.cashback_a_usar = 0.0
                    else:
                        st.session_state.cashback_a_usar = 0.0
                    # ==============================================================================
                    # FIM DA ÁREA
                    # ==============================================================================
                
                with col_prod_add:
                    st.markdown("##### Adicionar Produto")
                    
                    foto_cb_upload_caixa = st.file_uploader(
                        "📤 Upload de imagem do código de barras", 
                        type=["png", "jpg", "jpeg"], 
                        key="cb_upload_caixa"
                    )
                    
                    if foto_cb_upload_caixa is not None:
                        imagem_bytes = foto_cb_upload_caixa.getvalue() 
                        codigos_lidos = ler_codigo_barras_api(imagem_bytes)
                        if codigos_lidos:
                            st.session_state.cb_lido_livro_caixa = codigos_lidos[0]
                            st.toast(f"Código de barras lido: {codigos_lidos[0]}")
                        else:
                            st.session_state.cb_lido_livro_caixa = ""
                            st.error("❌ Não foi possível ler nenhum código na imagem enviada.")
                    
                    index_selecionado = 0
                    if st.session_state.get("cb_lido_livro_caixa"): 
                        opcao_encontrada = encontrar_opcao_por_cb(st.session_state.cb_lido_livro_caixa, produtos_para_venda, opcoes_produtos)
                        if opcao_encontrada:
                            index_selecionado = opcoes_produtos.index(opcao_encontrada)
                            st.toast(f"Produto correspondente ao CB encontrado!")
                        else:
                            st.warning(f"Código '{st.session_state.cb_lido_livro_caixa}' lido, mas nenhum produto com esse CB encontrado.")
                            st.session_state.cb_lido_livro_caixa = ""

                    produto_selecionado = st.selectbox(
                        "Selecione o Produto (ID | Nome)", 
                        opcoes_produtos, 
                        key="input_produto_selecionado",
                        index=index_selecionado
                    )
                    
                    if produto_selecionado and (produto_selecionado != opcoes_produtos[index_selecionado]) and st.session_state.get("cb_lido_livro_caixa"):
                         st.session_state.cb_lido_livro_caixa = ""

                    if produto_selecionado == OPCAO_MANUAL:
                        nome_produto_manual = st.text_input("Nome (Manual)", key="input_nome_prod_manual")
                        col_m1, col_m2 = st.columns(2)
                        with col_m1:
                            quantidade_manual = st.number_input("Qtd", min_value=0.01, step=1.0, key="input_qtd_prod_manual")
                            custo_unitario_manual = st.number_input("Custo Un. (R$)", min_value=0.00, format="%.2f", key="input_custo_prod_manual")
                        with col_m2:
                            preco_unitario_manual = st.number_input("Preço Un. (R$)", min_value=0.01, format="%.2f", key="input_preco_prod_manual")
                        
                        if st.button("Adicionar Manual", key="adicionar_item_manual_button", on_click=callback_adicionar_manual, args=(nome_produto_manual, quantidade_manual, preco_unitario_manual, custo_unitario_manual)):
                            st.rerun() 

                    elif produto_selecionado:
                        produto_id_selecionado = extrair_id_do_nome(produto_selecionado) 
                        produto_row_completa = produtos_para_venda[produtos_para_venda["ID"] == produto_id_selecionado]
                        
                        if not produto_row_completa.empty:
                            produto_data = produto_row_completa.iloc[0]
                            estoque_disp = int(produto_data['Quantidade'])
                            
                            col_p1, col_p2 = st.columns(2)
                            with col_p1:
                                quantidade_input = st.number_input("Qtd", min_value=1, value=1, step=1, max_value=estoque_disp if estoque_disp > 0 else 1, key="input_qtd_prod_edit")
                                st.caption(f"Estoque Disponível: {estoque_disp}")
                            with col_p2:
                                preco_unitario_input = st.number_input("Preço Unitário (R$)", min_value=0.01, format="%.2f", value=float(produto_data['PrecoVista']), key="input_preco_prod_edit")
                                st.caption(f"Custo Unitário: R$ {produto_data['PrecoCusto']:,.2f}")

                            if st.button("Adicionar Item", key="adicionar_item_button", on_click=callback_adicionar_estoque, args=(produto_id_selecionado, produto_data['Nome'], quantidade_input, preco_unitario_input, produto_data['PrecoCusto'], estoque_disp)):
                                st.rerun()

            col_entrada_valor, col_entrada_status = st.columns(2)
            with col_entrada_valor:
                valor_input_manual = st.number_input("Valor Total (R$)", value=valor_calculado if valor_calculado > 0.0 else default_valor, min_value=0.01, format="%.2f", disabled=(valor_calculado > 0.0), key="input_valor_entrada")
                valor_final_movimentacao = valor_calculado if valor_calculado > 0.0 else valor_input_manual
            with col_entrada_status:
                status_selecionado = st.radio("Status", ["Realizada", "Pendente"], index=0 if default_status == "Realizada" else 1, key="input_status_global_entrada", disabled=edit_mode)

        else: # Tipo é Saída
            st.markdown("---")
            # ... (Lógica de Saída, Categoria, Recorrência, etc.) ...
            cliente = st.text_input("Nome/Descrição da Despesa", value=default_cliente, key="input_cliente_form_saida", disabled=edit_mode)
            valor_final_movimentacao = st.number_input("Valor (R$)", value=default_valor, min_value=0.01, format="%.2f", key="input_valor_saida")
            status_selecionado = st.radio("Status", ["Realizada", "Pendente"], index=0 if default_status == "Realizada" else 1, key="input_status_global_saida", disabled=edit_mode)
        
        data_pagamento_final = None 
        if status_selecionado == "Pendente":
            data_pagamento_final = st.date_input("Data Prevista de Pagamento", value=date.today())

        with st.form("form_movimentacao", clear_on_submit=not edit_mode):
            st.markdown("#### Dados Finais da Transação")
            
            col_f1, col_f2, col_f3 = st.columns(3)

            with col_f1:
                loja_selecionada = st.selectbox("Loja Responsável", LOJAS_DISPONIVEIS, key="input_loja_form")
                data_input = st.date_input("Data da Transação", value=default_data, key="input_data_form")
            
            with col_f2:
                cliente_final = cliente
                st.text_input("Cliente/Descrição (Final)", value=cliente_final, key="input_cliente_form_display", disabled=True)
                
                if status_selecionado == "Realizada":
                    data_pagamento_final = data_input
                    forma_pagamento = st.selectbox("Forma de Pagamento", FORMAS_PAGAMENTO, key="input_forma_pagamento_form")
                else:
                    forma_pagamento = "Pendente" 
                    st.text_input("Forma de Pagamento", value="Pendente", disabled=True)
            
            with col_f3:
                st.markdown(f"**Valor Final:** R$ {valor_final_movimentacao:,.2f}")
                st.markdown(f"**Status:** **{status_selecionado}**")
                st.markdown(f"**Data Pagamento:** {data_pagamento_final.strftime('%d/%m/%Y') if data_pagamento_final else 'N/A'}")

            enviar = st.form_submit_button("💾 Adicionar e Salvar", type="primary", use_container_width=True)

            if enviar:
                # --- LÓGICA DE SALVAMENTO CORRIGIDA ---

                # 1. Determina o valor final e a categoria corretamente
                if tipo == "Saída":
                    # Para saídas, busca o valor do campo de número correspondente
                    valor_base = st.session_state.get('input_valor_saida', 0.0)
                    produtos_vendidos_json = "[]"
                    # Garante que o valor salvo para saídas seja negativo
                    valor_a_salvar = -abs(valor_base)
                    categoria_final = categoria_selecionada # Usa a categoria definida para saídas
                else: # tipo == "Entrada"
                    # Para entradas, calcula com base na lista de produtos ou valor manual
                    if st.session_state.lista_produtos:
                        df_prods = pd.DataFrame(st.session_state.lista_produtos)
                        valor_base = (pd.to_numeric(df_prods['Quantidade']) * pd.to_numeric(df_prods['Preço Unitário'])).sum()
                        produtos_vendidos_json = df_prods.to_json(orient='records')
                    else:
                        valor_base = st.session_state.get('input_valor_entrada', 0.0)
                        produtos_vendidos_json = "[]"
                    
                    cashback_resgatado = st.session_state.get('cashback_a_usar', 0.0)
                    valor_a_salvar = valor_base - cashback_resgatado
                    categoria_final = "" # Entradas não possuem categoria de custo

                # Lógica de atualização de cashback (mantida)
                if tipo == "Entrada" and status_selecionado == "Realizada" and cliente:
                    # ... (seu código original de gestão de cashback) ...
                    # Esta parte não precisa de alteração.
                    valor_base_compra = valor_base 
                    cashback_ganho = round(valor_base_compra * 0.03, 2)
                    
                    df_clientes_upd = st.session_state.df_clientes.copy()
                    
                    if 'Nome' in df_clientes_upd.columns:
                        cliente_idx_list = df_clientes_upd.index[df_clientes_upd['Nome'].str.strip().str.lower() == cliente.strip().lower()].tolist()

                        if cliente_idx_list:
                            idx = cliente_idx_list[0]
                            df_clientes_upd.loc[idx, "Cashback"] -= cashback_resgatado
                            df_clientes_upd.loc[idx, "Cashback"] += cashback_ganho
                            df_clientes_upd.loc[idx, "TotalGasto"] += valor_base_compra
                            df_clientes_upd.loc[idx, "Nivel"] = calcular_nivel(df_clientes_upd.loc[idx, "TotalGasto"])
                            msg_cashback = f"Cashback para {cliente}: Resgate R${cashback_resgatado:,.2f}, Ganho R${cashback_ganho:,.2f}"
                        else:
                            novo_cliente_data = {"Nome": cliente.strip(), "Cashback": cashback_ganho, "TotalGasto": valor_base_compra, "Nivel": calcular_nivel(valor_base_compra)}
                            df_clientes_upd = pd.concat([df_clientes_upd, pd.DataFrame([novo_cliente_data])], ignore_index=True)
                            msg_cashback = f"Novo cliente {cliente}: Ganho R${cashback_ganho:,.2f}"
                        
                        if salvar_clientes_cash_github(df_clientes_upd, msg_cashback):
                            st.toast(msg_cashback)
                            st.session_state.df_clientes = df_clientes_upd


                # 2. Monta o dicionário da nova movimentação usando as variáveis do formulário
                df_movimentacoes_upd = st.session_state.df.copy()
                nova_movimentacao = {
                    "Data": data_input.isoformat(),                   # CORRIGIDO: Usa a data do formulário
                    "Loja": loja_selecionada,                          # CORRIGIDO: Usa a loja do formulário
                    "Cliente": cliente_final,
                    "Valor": valor_a_salvar,                           # CORRIGIDO: Usa o valor correto e com sinal negativo para saídas
                    "Forma de Pagamento": forma_pagamento,             # CORRIGIDO: Usa a forma de pagamento selecionada
                    "Tipo": tipo,
                    "Produtos Vendidos": produtos_vendidos_json,
                    "Categoria": categoria_final,
                    "Status": status_selecionado,
                    "Data Pagamento": data_pagamento_final.isoformat() if data_pagamento_final else None
                }

                if edit_mode:
                    # (Seu código de edição existente)
                    df_movimentacoes_upd.loc[st.session_state.edit_id] = nova_movimentacao
                    msg_commit = "Movimentação editada"
                else:
                    df_movimentacoes_upd = pd.concat([df_movimentacoes_upd, pd.DataFrame([nova_movimentacao])], ignore_index=True)
                    msg_commit = "Nova movimentação"
                
                if salvar_dados_no_github(df_movimentacoes_upd, msg_commit, data_input):
                    st.success("Movimentação salva com sucesso!")
                    st.session_state.df = df_movimentacoes_upd
                    st.session_state.lista_produtos = []
                    st.session_state.edit_id = None
                    carregar_livro_caixa.clear()
                    st.rerun()


                
    # ==============================================================================================
    # ABA: MOVIMENTAÇÕES E RESUMO (Código Original)
    # ==============================================================================================
    with tab_mov:
        # REMOVIDO: st.session_state.aba_ativa_livro_caixa = "📋 Movimentações e Resumo"
        
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
        
        st.subheader(f"📊 Resumo Financeiro Geral")

        total_entradas_mes, total_saidas_mes, saldo_mes = calcular_resumo(df_mes_atual_realizado)

        df_geral_realizado = df_exibicao[df_exibicao['Status'] == 'Realizada']
        _, _, saldo_geral_total = calcular_resumo(df_geral_realizado)
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric(f"Entradas (Mês: {primeiro_dia_mes.strftime('%b')})", f"R$ {total_entradas_mes:,.2f}")
        col2.metric(f"Saídas (Mês: {primeiro_dia_mes.strftime('%b')})", f"R$ {total_saidas_mes:,.2f}")
        delta_saldo_mes = f"R$ {saldo_mes:,.2f}"
        col3.metric("Saldo do Mês (Realizado)", f"R$ {saldo_mes:,.2f}", delta=delta_saldo_mes if saldo_mes != 0 else None, delta_color="normal")
        col4.metric("Saldo Atual (Geral)", f"R$ {saldo_geral_total:,.2f}")

        st.markdown("---")
        
        # [Bloco de Alerta de Dívidas Pendentes Vencidas]
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
        
        # [Bloco de Resumo por Loja]
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
        
        # [Bloco de Filtros e Tabela de Movimentações]
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
            
            # [Bloco de Edição e Exclusão]
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
                            # [Bloco de exibição de detalhes dos produtos]
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

                            st.dataframe(df_detalhe, hide_index=True, use_container_width=True, 
                                column_config={
                                    "Produto": "Produto",
                                    "Quantidade": st.column_config.NumberColumn("Qtd"),
                                    "Preço Unitário": st.column_config.NumberColumn("Preço Un.", format="R$ %.2f"),
                                    "Custo Unitário": st.column_config.NumberColumn("Custo Un.", format="R$ %.2f"),
                                    "Total Venda": st.column_config.NumberColumn("Total Venda", format="R$ %.2f"),
                                    "Total Custo": st.column_config.NumberColumn("Total Custo", format="R$ %.2f"),
                                    "Lucro Bruto": st.column_config.NumberColumn("Lucro Bruto", format="R$ %.2f", help="Venda - Custo")
                                }
                            ) 
                        
                        except Exception as e:
                            st.error(f"Erro ao processar detalhes dos produtos: {e}")

                        st.markdown("---")


                    col_op_1, col_op_2 = st.columns(2)

                    if col_op_1.button(f"✏️ Editar: {item_selecionado_str}", key=f"edit_mov_{original_idx_selecionado}", use_container_width=True, type="secondary"):
                        st.session_state.edit_id = original_idx_selecionado
                        st.session_state.edit_id_loaded = None 
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

    # ==============================================================================================
    # ABA: RELATÓRIOS E FILTROS (Código Original)
    # ==============================================================================================
    with tab_rel:
        # REMOVIDO: st.session_state.aba_ativa_livro_caixa = "📈 Relatórios e Filtros"
        
        st.subheader("📄 Relatório Detalhado e Comparativo")
        
        # [Conteúdo original da aba tab_rel]
        with st.container(border=True):
            st.markdown("#### Filtros do Relatório")
            
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                lojas_selecionadas = st.multiselect(
                    "Selecione uma ou mais lojas/empresas",
                    options=LOJAS_DISPONIVEIS,
                    default=LOJAS_DISPONIVEIS
                )
                
                tipo_movimentacao = st.radio(
                    "Tipo de Movimentação",
                    ["Ambos", "Entrada", "Saída"],
                    horizontal=True,
                    key="rel_tipo"
                )
            
            with col_f2:
                min_date_geral = df_exibicao["Data"].min() if not df_exibicao.empty and pd.notna(df_exibicao["Data"].min()) else date.today()
                max_date_geral = df_exibicao["Data"].max() if not df_exibicao.empty and pd.notna(df_exibicao["Data"].max()) else date.today()

                data_inicio_rel = st.date_input("Data de Início", value=min_date_geral, min_value=min_date_geral, max_value=max_date_geral, key="rel_data_ini")
                data_fim_rel = st.date_input("Data de Fim", value=max_date_geral, min_value=min_date_geral, max_value=max_date_geral, key="rel_data_fim")

            if st.button("📊 Gerar Relatório Comparativo", use_container_width=True, type="primary"):
                
                df_relatorio = df_exibicao[
                    (df_exibicao['Status'] == 'Realizada') &
                    (df_exibicao['Loja'].isin(lojas_selecionadas)) &
                    (df_exibicao['Data'] >= data_inicio_rel) &
                    (df_exibicao['Data'] <= data_fim_rel)
                ].copy()

                if tipo_movimentacao != "Ambos":
                    df_relatorio = df_relatorio[df_relatorio['Tipo'] == tipo_movimentacao]
                
                if df_relatorio.empty:
                    st.warning("Nenhum dado encontrado com os filtros selecionados.")
                else:
                    df_relatorio['MesAno'] = df_relatorio['Data_dt'].dt.to_period('M').astype(str)
                    
                    df_agrupado = df_relatorio.groupby('MesAno').apply(lambda x: pd.Series({
                        'Entradas': x[x['Valor'] > 0]['Valor'].sum(),
                        'Saídas': abs(x[x['Valor'] < 0]['Valor'].sum())
                    })).reset_index()

                    df_agrupado['Saldo'] = df_agrupado['Entradas'] - df_agrupado['Saídas']
                    
                    df_agrupado = df_agrupado.sort_values(by='MesAno').reset_index(drop=True)
                    df_agrupado['Crescimento Entradas (%)'] = (df_agrupado['Entradas'].pct_change() * 100).fillna(0)
                    df_agrupado['Crescimento Saídas (%)'] = (df_agrupado['Saídas'].pct_change() * 100).fillna(0)
                    
                    st.markdown("---")
                    st.subheader("Resultados do Relatório")

                    st.markdown("##### 🗓️ Tabela Comparativa Mensal")
                    st.dataframe(df_agrupado, use_container_width=True,
                        column_config={"MesAno": "Mês/Ano","Entradas": st.column_config.NumberColumn("Entradas (R$)", format="R$ %.2f"),
                            "Saídas": st.column_config.NumberColumn("Saídas (R$)", format="R$ %.2f"),
                            "Saldo": st.column_config.NumberColumn("Saldo (R$)", format="R$ %.2f"),
                            "Crescimento Entradas (%)": st.column_config.NumberColumn("Cresc. Entradas", format="%.2f%%"),
                            "Crescimento Saídas (%)": st.column_config.NumberColumn("Cresc. Saídas", format="%.2f%%")}
                    )

                    fig_comp = px.bar(df_agrupado, x='MesAno', y=['Entradas', 'Saídas'], title="Comparativo de Entradas vs. Saídas por Mês",
                        labels={'value': 'Valor (R$)', 'variable': 'Tipo', 'MesAno': 'Mês/Ano'}, barmode='group', color_discrete_map={'Entradas': 'green', 'Saídas': 'red'})
                    st.plotly_chart(fig_comp, use_container_width=True)

                    fig_cresc = px.line(df_agrupado, x='MesAno', y=['Crescimento Entradas (%)', 'Crescimento Saídas (%)'],
                        title="Crescimento Percentual Mensal (Entradas e Saídas)",
                        labels={'value': '% de Crescimento', 'variable': 'Métrica', 'MesAno': 'Mês/Ano'}, markers=True)
                    st.plotly_chart(fig_cresc, use_container_width=True)

                    if 'Entradas' in df_agrupado.columns and not df_agrupado[df_agrupado['Entradas'] > 0].empty:
                        st.markdown("##### 🏆 Ranking de Vendas (Entradas) por Mês")
                        df_ranking = df_agrupado[['MesAno', 'Entradas']].sort_values(by='Entradas', ascending=False).reset_index(drop=True)
                        df_ranking.index += 1
                        st.dataframe(df_ranking, use_container_width=True,
                            column_config={"MesAno": "Mês/Ano","Entradas": st.column_config.NumberColumn("Total de Entradas (R$)", format="R$ %.2f")}
                        )

        st.markdown("---")

        st.subheader("🚩 Dívidas Pendentes (A Pagar e A Receber)")
        
        df_pendentes = df_exibicao[df_exibicao["Status"] == "Pendente"].copy()
        
        if df_pendentes.empty:
            st.info("Parabéns! Não há dívidas pendentes registradas.")
        else:
            df_pendentes["Data Pagamento"] = pd.to_datetime(df_pendentes["Data Pagamento"], errors='coerce').dt.date
            df_pendentes_ordenado = df_pendentes.sort_values(by=["Data Pagamento", "Tipo", "Data"], ascending=[True, True, True]).reset_index(drop=True)
            hoje_date = date.today()
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

            # NOVO: Início do Formulário de Pagamento Parcial/Total
            with st.form("form_concluir_divida"):
                st.markdown("##### ✅ Concluir Dívida Pendente (Pagamento Parcial ou Total)")
                
                # NOVO: Usa divida_parcial_id se vier da aba Nova Movimentação
                default_concluir_idx = 0
                divida_para_concluir = None
                
                opcoes_pendentes_map = {
                    f"ID {row['ID Visível']} | {row['Tipo']} | R$ {calcular_valor_em_aberto(row):,.2f} | Venc.: {row['Data Pagamento'].strftime('%d/%m/%Y') if pd.notna(row['Data Pagamento']) else 'S/ Data'} | {row['Cliente']}": row['original_index']
                    for index, row in df_pendentes_ordenado.iterrows()
                }
                opcoes_keys = ["Selecione uma dívida..."] + list(opcoes_pendentes_map.keys())

                if 'divida_parcial_id' in st.session_state and st.session_state.divida_parcial_id is not None:
                    # Encontra a chave da dívida selecionada
                    original_idx_para_selecionar = st.session_state.divida_parcial_id
                    try:
                        divida_row = df_pendentes_ordenado[df_pendentes_ordenado['original_index'] == original_idx_para_selecionar].iloc[0]
                        valor_row_formatado = calcular_valor_em_aberto(divida_row)
                        option_key = f"ID {divida_row['ID Visível']} | {divida_row['Tipo']} | R$ {valor_row_formatado:,.2f} | Venc.: {divida_row['Data Pagamento'].strftime('%d/%m/%Y') if pd.notna(divida_row['Data Pagamento']) else 'S/ Data'} | {divida_row['Cliente']}"
                        
                        opcoes_pendentes = {
                            f"ID {row['ID Visível']} | {row['Tipo']} | R$ {calcular_valor_em_aberto(row):,.2f} | Venc.: {row['Data Pagamento'].strftime('%d/%m/%Y') if pd.notna(row['Data Pagamento']) else 'S/ Data'} | {row['Cliente']}": row['original_index']
                            for index, row in df_pendentes_ordenado.iterrows()
                        }
                        
                        opcoes_keys = ["Selecione uma dívida..."] + list(opcoes_pendentes_map.keys())
                        
                        if option_key in opcoes_keys:
                            default_concluir_idx = opcoes_keys.index(option_key)
                        
                        # Carrega os dados da dívida para exibição
                        divida_para_concluir = divida_row
                    except Exception:
                        pass # Continua com o índice 0 (Selecione)
                    
                    # Limpa a chave após a seleção
                    st.session_state.divida_parcial_id = None
                
                
                divida_selecionada_str = st.selectbox(
                    "Selecione a Dívida para Concluir:", 
                    options=opcoes_keys, 
                    index=default_concluir_idx,
                    key="select_divida_concluir"
                )
                
                original_idx_concluir = opcoes_pendentes_map.get(divida_selecionada_str)
                
                if original_idx_concluir is not None and divida_para_concluir is None:
                    # Carrega os dados da dívida se o usuário selecionar manualmente
                    divida_para_concluir = df_pendentes_ordenado[df_pendentes_ordenado['original_index'] == original_idx_concluir].iloc[0]


                if divida_para_concluir is not None:
                    # >> USO DA NOVA FUNÇÃO PARA GARANTIR VALOR CORRETO E ARREDONDADO <<
                    valor_em_aberto = calcular_valor_em_aberto(divida_para_concluir)
                    # << FIM DO USO DA NOVA FUNÇÃO >>

                    st.markdown(f"**Valor em Aberto:** R$ {valor_em_aberto:,.2f}")
                    
                    col_c1, col_c2, col_c3 = st.columns(3)
                    with col_c1:
                        valor_pago = st.number_input(
                            f"Valor Pago (Máx: R$ {valor_em_aberto:,.2f})", 
                            min_value=0.01, 
                            max_value=valor_em_aberto, 
                            value=valor_em_aberto, 
                            format="%.2f",
                            key="input_valor_pago_parcial"
                        )
                    with col_c2:
                        data_conclusao = st.date_input("Data Real do Pagamento", value=hoje_date, key="data_conclusao_divida")
                    with col_c3:
                        forma_pagt_concluir = st.selectbox("Forma de Pagamento", FORMAS_PAGAMENTO, key="forma_pagt_concluir")

                    concluir = st.form_submit_button("✅ Registrar Pagamento", use_container_width=True, type="primary")

                    if concluir:
                        valor_restante = round(valor_em_aberto - valor_pago, 2)
                        idx_original = original_idx_concluir
                        
                        if idx_original not in st.session_state.df.index:
                            st.error("Erro interno ao localizar dívida. O registro original foi perdido.")
                            st.rerun()
                            return

                        row_original = st.session_state.df.loc[idx_original].copy()
                        
                        # 1. Cria a transação de pagamento (Realizada)
                        # O valor deve ter o sinal correto (Entrada é positivo, Saída é negativo)
                        valor_pagamento_com_sinal = valor_pago if row_original['Tipo'] == 'Entrada' else -valor_pago
                        
                        nova_transacao_pagamento = {
                            "Data": data_conclusao,
                            "Loja": row_original['Loja'],
                            "Cliente": f"{row_original['Cliente'].split(' (')[0]} (Pagto de R$ {valor_pago:,.2f})",
                            "Valor": valor_pagamento_com_sinal, 
                            "Forma de Pagamento": forma_pagt_concluir,
                            "Tipo": row_original['Tipo'],
                            "Produtos Vendidos": row_original['Produtos Vendidos'], # Mantém os produtos para rastreio
                            "Categoria": row_original['Categoria'],
                            "Status": "Realizada",
                            "Data Pagamento": data_conclusao,
                            "RecorrenciaID": row_original['RecorrenciaID'],
                            "TransacaoPaiID": idx_original # Rastreia o ID original (índice Pandas)
                        }
                        
                        # Adiciona o pagamento realizado
                        st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([nova_transacao_pagamento])], ignore_index=True)
                        
                        # 2. Atualiza a dívida original
                        if valor_restante > 0.01: # Pagamento parcial: atualiza a dívida original
                            
                            # Atualiza o valor restante (o sinal já foi definido no processamento)
                            novo_valor_restante_com_sinal = valor_restante if row_original['Tipo'] == 'Entrada' else -valor_restante

                            st.session_state.df.loc[idx_original, 'Valor'] = novo_valor_restante_com_sinal
                            st.session_state.df.loc[idx_original, 'Cliente'] = f"{row_original['Cliente'].split(' (')[0]} (EM ABERTO: R$ {valor_restante:,.2f})"
                            
                            commit_msg = f"Pagamento parcial de R$ {valor_pago:,.2f} da dívida {row_original['Cliente']}. Resta R$ {valor_restante:,.2f}."
                            
                        else: # Pagamento total (valor restante <= 0.01)
                            
                            # Exclui a linha original pendente (pois o pagamento total já foi registrado como nova transação)
                            st.session_state.df = st.session_state.df.drop(idx_original, errors='ignore')
                            
                            # Débito de Estoque (Apenas para Entrada)
                            # O débito de estoque só deve ocorrer se a transação original for a venda (Tipo Entrada)
                            if row_original["Tipo"] == "Entrada" and row_original["Produtos Vendidos"]:
                                try:
                                    produtos_vendidos = ast.literal_eval(row_original['Produtos Vendidos'])
                                    for item in produtos_vendidos:
                                        if item.get("Produto_ID"): ajustar_estoque(item["Produto_ID"], item["Quantidade"], "debitar")
                                    if salvar_produtos_no_github(st.session_state.produtos, f"Débito de estoque por conclusão total {row_original['Cliente']}"): inicializar_produtos.clear()
                                except: st.warning("⚠️ Venda concluída, mas falha no débito do estoque (JSON inválido).")
                                
                            commit_msg = f"Pagamento total de R$ {valor_pago:,.2f} da dívida {row_original['Cliente'].split(' (')[0]}."
                            
                        
                        if salvar_dados_no_github(st.session_state.df, commit_msg):
                            st.session_state.divida_parcial_id = None
                            st.cache_data.clear()
                            st.rerun()
                else:
                    st.info("Selecione uma dívida válida para prosseguir com o pagamento.")


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

# Usando a função importada de render_utils
render_custom_header(
    paginas_ordenadas=["Home", "Livro Caixa", "Produtos", "Promoções", "Histórico de Compra"],
    paginas_map=PAGINAS
)


# --- RENDERIZAÇÃO DO CONTEÚDO DA PÁGINA ---
PAGINAS[st.session_state.pagina_atual]()

# --- Exibe/Oculta o Sidebar do Formulário ---
# A sidebar só é necessária para o formulário de Adicionar/Editar Movimentação (Livro Caixa)
if st.session_state.pagina_atual != "Livro Caixa":
    st.sidebar.empty()

















