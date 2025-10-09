# utils.py
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
import requests
from requests.exceptions import ConnectionError, RequestException
from io import StringIO
import json
import hashlib
import ast
import calendar
import os
from github import Github # Adicionei aqui para garantir o uso em todas as funções de salvar


# =================================================================================
# No arquivo utils.py, corrija o bloco para:
from constants_and_css import (
    TOKEN, OWNER, REPO_NAME, BRANCH, GITHUB_TOKEN, GITHUB_REPO, GITHUB_BRANCH,
    PATH_DIVIDAS, ARQ_PRODUTOS, ARQ_LOCAL, ARQ_COMPRAS, ARQ_PROMOCOES,
    COLUNAS_COMPRAS, 
    COLUNAS_PADRAO, 
    COLUNAS_PADRAO_COMPLETO,
    COLUNAS_COMPLETAS_PROCESSADAS,
    COLUNAS_PRODUTOS,
    COLUNAS_PRODUTOS_COMPLETAS, # <--- CORREÇÃO!
    FATOR_CARTAO, COMMIT_MESSAGE, COMMIT_MESSAGE_EDIT, COMMIT_MESSAGE_DELETE,
    # === NOVAS CONSTANTES DE CASHBACK ===
    ARQ_CASHBACK, COLUNAS_CASHBACK, NIVEIS_CASHBACK
)
# =================================================================================

# ==================== FUNÇÕES DE TRATAMENTO BÁSICO ====================

def to_float(valor_str):
    try:
        if isinstance(valor_str, (int, float)):
            return float(valor_str)
        return float(str(valor_str).replace(",", ".").strip())
    except:
        return 0.0


def prox_id(df, coluna_id="ID"):
    if df is None or df.empty:
        return "1"
    else:
        try:
            return str(pd.to_numeric(df[coluna_id], errors='coerce').fillna(0).astype(int).max() + 1)
        except Exception:
            try:
                numeric_ids = pd.to_numeric(df[coluna_id].astype(str).str.extract(r'(\d+)')[0], errors='coerce').fillna(0).astype(int)
                return str(numeric_ids.max() + 1)
            except Exception:
                return str(len(df) + 1)


def hash_df(df):
    df_temp = df.copy()
    for col in df_temp.select_dtypes(include=['datetime64[ns]']).columns:
        df_temp[col] = df_temp[col].astype(str)
    try:
        return hashlib.md5(df_temp.to_json().encode('utf-8')).hexdigest()
    except Exception:
        return "error"


def parse_date_yyyy_mm_dd(date_str):
    if pd.isna(date_str) or not date_str:
        return None
    try:
        return datetime.strptime(str(date_str).split(" ")[0], "%Y-%m-%d").date()
    except Exception:
        return None


def add_months(d: date, months: int) -> date:
    month = d.month + months
    year = d.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def calcular_valor_em_aberto(linha):
    try:
        if isinstance(linha, pd.DataFrame) and not linha.empty:
            valor_raw = pd.to_numeric(linha['Valor'].iloc[0], errors='coerce')
        elif isinstance(linha, pd.Series):
            valor_raw = pd.to_numeric(linha['Valor'], errors='coerce')
        else:
            return 0.0
        valor_float = float(valor_raw) if pd.notna(valor_raw) else 0.0
        return round(abs(valor_float), 2)
    except Exception:
        return 0.0


def format_produtos_resumo(produtos_json):
    if pd.isna(produtos_json) or produtos_json == "":
        return ""
    try:
        try:
            produtos = json.loads(produtos_json)
        except (json.JSONDecodeError, TypeError):
            produtos = ast.literal_eval(produtos_json)
        if not isinstance(produtos, list):
            return "Dados inválidos"
        count = len(produtos)
        if count > 0:
            primeiro = produtos[0].get('Produto', 'Produto Desconhecido')
            total_custo, total_venda = 0.0, 0.0
            for p in produtos:
                try:
                    qtd = float(p.get('Quantidade', 0))
                    preco_unit = float(p.get('Preço Unitário', 0))
                    custo_unit = float(p.get('Custo Unitário', 0))
                except Exception:
                    qtd = 0.0
                    preco_unit = 0.0
                    custo_unit = 0.0
                total_custo += custo_unit * qtd
                total_venda += preco_unit * qtd
            lucro = total_venda - total_custo
            lucro_str = f"| Lucro R$ {lucro:,.2f}" if lucro != 0 else ""
            return f"{count} item(s): {primeiro}... {lucro_str}"
    except Exception:
        return "Erro JSON Inválido"
    return ""


# =================================================================================
# 🔍 Utilitários de carregamento remoto (GitHub raw)
# =================================================================================
def load_csv_github(url: str) -> pd.DataFrame | None:
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        import csv
        sample = response.text[:500]
        sniffer = csv.Sniffer()
        delimiter = ","
        try:
            delimiter = sniffer.sniff(sample).delimiter
        except Exception:
            pass
        df = pd.read_csv(StringIO(response.text), dtype=str, sep=delimiter, encoding="utf-8-sig")
        df.columns = [col.upper().replace(' ', '_') for col in df.columns]
        if df.empty:
            st.warning("⚠️ O arquivo CSV está vazio ou sem dados válidos.")
        return df
    except Exception as e:
        st.error(f"❌ Erro ao ler CSV do GitHub: {e}")
        return None

# =================================================================================
# 🔧 Funções de Lógica e Persistência
# =================================================================================

def norm_promocoes(df_promocoes: pd.DataFrame) -> pd.DataFrame:
    """Normaliza o DataFrame de promoções, convertendo datas e garantindo tipos. Retorna APENAS as promoções ativas."""
    COLUNAS_PROMO_NOVAS = ["ID_PROMOCAO", "ID_PRODUTO", "NOME_PRODUTO", "PRECO_ORIGINAL", "PRECO_PROMOCIONAL", "STATUS", "DATA_INICIO", "DATA_FIM"]
    if df_promocoes is None or df_promocoes.empty:
        return pd.DataFrame(columns=COLUNAS_PROMO_NOVAS)
    df = df_promocoes.copy()
    for col in COLUNAS_PROMO_NOVAS:
        if col not in df.columns:
            df[col] = ''
    for col in ["DATA_INICIO", "DATA_FIM"]:
        df[col] = pd.to_datetime(df[col], errors='coerce').dt.date
    df["PRECO_ORIGINAL"] = pd.to_numeric(df["PRECO_ORIGINAL"], errors='coerce').fillna(0.0)
    df["PRECO_PROMOCIONAL"] = pd.to_numeric(df["PRECO_PROMOCIONAL"], errors='coerce').fillna(0.0)
    hoje = date.today()
    df_ativas = df[
        (df["STATUS"].astype(str).str.upper() == 'ATIVO') &
        (df["DATA_FIM"] >= hoje) & 
        (df["DATA_INICIO"] <= hoje)
    ].copy()
    return df_ativas[COLUNAS_PROMO_NOVAS]

def salvar_dados_no_github(df: pd.DataFrame, commit_message: str):
    """
    Função para salvar o Livro Caixa (movimentações) no GitHub. 
    (Substitui 'salvar_historico_no_github' para maior clareza de uso).
    """
    # Importa as constantes necessárias (melhor deixar fora do try/except se possível)
    try:
        from constants_and_css import PATH_DIVIDAS as CONST_PATH, OWNER as CONST_OWNER, REPO_NAME as CONST_REPO, BRANCH as CONST_BRANCH
        from constants_and_css import GITHUB_TOKEN, ARQ_LOCAL # Garante a importação de GITHUB_TOKEN e ARQ_LOCAL
    except Exception:
        # Se as constantes não carregarem, a falha é estrutural.
        return False
        
    # --- 1. Busca de Credenciais ---
    # Usando o GITHUB_TOKEN já importado, garantindo o fallback
    token = (st.secrets.get("GITHUB_TOKEN") or st.secrets.get("github_token") or GITHUB_TOKEN)
    repo_owner = st.secrets.get("REPO_OWNER") or st.secrets.get("owner") or CONST_OWNER
    repo_name = st.secrets.get("REPO_NAME") or st.secrets.get("repo") or CONST_REPO
    branch = st.secrets.get("BRANCH") or CONST_BRANCH
    csv_remote_path = CONST_PATH or "movimentacoes.csv"
    
    if not token:
        st.warning("⚠️ Nenhum token do GitHub encontrado. Salve manualmente.")
        return False
        
    # --- 2. Backup Local (Corrigido index=True para index=False se for Livro Caixa) ---
    try:
        # Nota: Livro Caixa geralmente não usa index=True, mas mantive o original se for seu requisito
        df.to_csv(ARQ_LOCAL, index=False, encoding="utf-8-sig") 
    except Exception as e:
        st.error(f"Erro ao salvar localmente: {e}")
        
    # --- 3. Envio para o GitHub ---
    try:
        g = Github(token)
        repo = g.get_repo(f"{repo_owner}/{repo_name}")
        csv_content = df.to_csv(index=False, encoding="utf-8-sig")
        
        try:
            contents = repo.get_contents(csv_remote_path, ref=branch)
            repo.update_file(contents.path, commit_message, csv_content, contents.sha, branch=branch)
            st.success("📁 Dados atualizados no GitHub!")
        except Exception:
            repo.create_file(csv_remote_path, commit_message, csv_content, branch=branch)
            st.success("📁 Arquivo de dados criado no GitHub!")
            
        # A LINHA CRÍTICA: LIMPEZA DO CACHE PARA FORÇAR O RELOAD
        carregar_livro_caixa.clear()
        
        return True
        
    except Exception as e:
        st.warning(f"Falha ao enviar dados para o GitHub — backup local mantido. ({e})")
        return False

def processar_dataframe(df_movimentacoes: pd.DataFrame) -> pd.DataFrame:
    """Processa o dataframe de movimentações para exibição e cálculo de saldo."""
    if df_movimentacoes is None or df_movimentacoes.empty:
        return pd.DataFrame(columns=[c.upper().replace(' ', '_') for c in COLUNAS_COMPLETAS_PROCESSADAS])
    df = df_movimentacoes.copy()
    if 'index' in df.columns:
        df = df.drop(columns=['index'])
    if 'original_index' in df.columns:
        df = df.drop(columns=['original_index'])
    df.index.name = 'original_index'
    df = df.reset_index()
    df["VALOR"] = pd.to_numeric(df["VALOR"], errors='coerce').fillna(0.0) 
    df["DATA"] = pd.to_datetime(df["DATA"], errors='coerce').dt.date 
    df["DATA_PAGAMENTO"] = pd.to_datetime(df["DATA_PAGAMENTO"], errors='coerce').dt.date 
    
    # CORREÇÃO PARA GARANTIR QUE REGISTROS PENDENTES COM DATA INVÁLIDA NÃO SEJAM DESCARTADOS
    df["Data_dt"] = pd.to_datetime(df["DATA"], errors='coerce')
    df["Data_dt"] = df["Data_dt"].fillna(datetime(1900, 1, 1)) # Preenche NaT com data mínima para ordenação
    # df.dropna(subset=['Data_dt'], inplace=True) <--- REMOVIDO PARA EVITAR DESCARTE DE PENDENTES
    
    df['Cor_Valor'] = df['VALOR'].apply(lambda x: 'green' if x >= 0 else 'red') 
    if 'ID_VISÍVEL' not in df.columns or df['ID_VISÍVEL'].isnull().all():
        df['ID_VISÍVEL'] = range(1, len(df) + 1)
        
    df_realizadas = df[df['STATUS'] == 'REALIZADA'].copy()
    if 'original_index' in df_realizadas.columns:
        df_realizadas = df_realizadas.sort_values(by=['DATA_dt', 'original_index']) 
        df_realizadas['Saldo Acumulado'] = df_realizadas['VALOR'].cumsum() 
        df = df.merge(df_realizadas[['original_index', 'Saldo Acumulado']], on='original_index', how='left')
    else:
        df['Saldo Acumulado'] = pd.NA
        
    livro_caixa_map = {
        'DATA': 'Data', 'LOJA': 'Loja', 'CLIENTE': 'Cliente', 'VALOR': 'Valor',
        'FORMA_DE_PAGAMENTO': 'Forma de Pagamento', 'TIPO': 'Tipo', 'PRODUTOS_VENDIDOS': 'Produtos Vendidos',
        'CATEGORIA': 'Categoria', 'STATUS': 'Status', 'DATA_PAGAMENTO': 'Data Pagamento', 
        'RECORRENCIAID': 'RecorrenciaID', 'TRANSACAOPAIID': 'TransacaoPaiID', 'ID_VISÍVEL': 'ID Visível', 
    }
    df.rename(columns=livro_caixa_map, inplace=True, errors='ignore')
    return df

def calcular_resumo(df_movimentacoes: pd.DataFrame):
    """Calcula o total de entradas, saídas e o saldo líquido de um DataFrame."""
    if df_movimentacoes is None or df_movimentacoes.empty:
        return 0.0, 0.0, 0.0
    df = df_movimentacoes.copy()
    df["Valor"] = pd.to_numeric(df["Valor"], errors='coerce').fillna(0.0) 
    total_entradas = df[df['Valor'] >= 0]['Valor'].sum()
    total_saidas = abs(df[df['Valor'] < 0]['Valor'].sum())
    saldo = total_entradas - total_saidas
    return round(total_entradas, 2), round(total_saidas, 2), round(saldo, 2)

def salvar_promocoes_no_github(df: pd.DataFrame, commit_message: str = "Atualiza promoções"):
    """Salva o CSV de promoções localmente e, se possível, também no GitHub."""
    try:
        from constants_and_css import ARQ_PROMOCOES, OWNER as CONST_OWNER, REPO_NAME as CONST_REPO, BRANCH as CONST_BRANCH
    except Exception as e:
        st.error(f"❌ Erro ao carregar constantes do projeto: {e}")
        return False
    try:
        df.to_csv(ARQ_PROMOCOES, index=False, encoding="utf-8-sig")
        try:
            st.toast("💾 Promoções salvas localmente!")
        except Exception:
            pass
    except Exception as e:
        st.error(f"Erro ao salvar promoções localmente: {e}")
        return False
    token = (st.secrets.get("GITHUB_TOKEN") or st.secrets.get("github_token") or GITHUB_TOKEN)
    repo_owner = st.secrets.get("REPO_OWNER") or st.secrets.get("owner") or CONST_OWNER
    repo_name = st.secrets.get("REPO_NAME") or st.secrets.get("repo") or CONST_REPO
    branch = st.secrets.get("BRANCH") or CONST_BRANCH
    csv_remote_path = os.path.basename(ARQ_PROMOCOES) or "promocoes.csv"
    if not token:
        st.warning("⚠️ Nenhum token do GitHub encontrado — apenas backup local salvo.")
        return False
    try:
        g = Github(token)
        repo = g.get_repo(f"{repo_owner}/{repo_name}")
        csv_content = df.to_csv(index=False, encoding="utf-8-sig")
        try:
            contents = repo.get_contents(csv_remote_path, ref=branch)
            repo.update_file(contents.path, commit_message, csv_content, contents.sha, branch=branch)
            st.success("📁 Promoções atualizadas no GitHub!")
        except Exception:
            repo.create_file(csv_remote_path, commit_message, csv_content, branch=branch)
            st.success("📁 Arquivo de promoções criado no GitHub!")
        return True
    except Exception as e:
        st.warning(f"Falha ao enviar promoções para o GitHub — backup local mantido. ({e})")
        return False

def salvar_historico_compras_no_github(df: pd.DataFrame, commit_message: str):
    """Salva o DataFrame de histórico de compras localmente como backup e o envia para o GitHub."""
    if df is None or df.empty:
        st.warning("⚠️ Nenhum dado de compra para salvar — operação ignorada para evitar sobrescrever o CSV no GitHub.")
        return False
    try:
        from constants_and_css import ARQ_COMPRAS, OWNER as CONST_OWNER, REPO_NAME as CONST_REPO, BRANCH as CONST_BRANCH, GITHUB_TOKEN # Re-importa constantes
    except Exception as e:
        st.error(f"❌ Erro ao carregar constantes do projeto: {e}")
        return False

    # 1. Backup Local
    try:
        df.to_csv(ARQ_COMPRAS, index=False, encoding="utf-8-sig")
        st.toast("💾 Histórico de Compras salvo localmente!")
    except Exception as e:
        st.error(f"Erro ao salvar histórico de compras localmente: {e}")
        return False

    # 2. Envio para o GitHub
    token = (st.secrets.get("GITHUB_TOKEN") or st.secrets.get("github_token") or GITHUB_TOKEN)
    repo_owner = st.secrets.get("REPO_OWNER") or st.secrets.get("owner") or CONST_OWNER
    repo_name = st.secrets.get("REPO_NAME") or st.secrets.get("repo") or CONST_REPO
    branch = st.secrets.get("BRANCH") or CONST_BRANCH
    csv_remote_path = ARQ_COMPRAS

    if not token:
        st.warning("⚠️ Nenhum token do GitHub encontrado — apenas backup local foi salvo.")
        return False
    try:
        g = Github(token)
        repo = g.get_repo(f"{repo_owner}/{repo_name}")
        csv_content = df.to_csv(index=False, encoding="utf-8-sig")

        try:
            contents = repo.get_contents(csv_remote_path, ref=branch)
            repo.update_file(contents.path, commit_message, csv_content, contents.sha, branch=branch)
            st.success("📁 Histórico de Compras atualizado no GitHub!")
        except Exception:
            repo.create_file(csv_remote_path, commit_message, csv_content, branch=branch)
            st.success("📁 Arquivo de Histórico de Compras criado no GitHub!")

        # Limpa o cache para forçar o reload na próxima vez
        carregar_historico_compras.clear()

        return True
    except Exception as e:
        st.warning(f"Falha ao enviar Histórico de Compras para o GitHub — backup local mantido. Erro: ({e})")
        return False

def salvar_produtos_no_github(df: pd.DataFrame, commit_message: str):
    """Salva o DataFrame de produtos localmente como backup e o envia para o GitHub."""
    if df is None or df.empty:
        st.warning("⚠️ Nenhum produto para salvar — operação ignorada para evitar sobrescrever o CSV no GitHub.")
        return False
    try:
        df.to_csv(ARQ_PRODUTOS, index=False, encoding="utf-8-sig")
        st.toast("💾 Produtos salvos localmente!")
    except Exception as e:
        st.error(f"Erro ao salvar produtos localmente: {e}")
        return False
    token = (st.secrets.get("GITHUB_TOKEN") or st.secrets.get("github_token") or GITHUB_TOKEN)
    repo_owner = st.secrets.get("REPO_OWNER") or st.secrets.get("owner") or OWNER
    repo_name = st.secrets.get("REPO_NAME") or st.secrets.get("repo") or REPO_NAME
    branch = st.secrets.get("BRANCH") or BRANCH
    csv_remote_path = ARQ_PRODUTOS
    if not token:
        st.warning("⚠️ Nenhum token do GitHub encontrado — apenas backup local foi salvo.")
        return False
    try:
        g = Github(token)
        repo = g.get_repo(f"{repo_owner}/{repo_name}")
        df_to_save = df.copy()
        for col_camel in COLUNAS_PRODUTOS_COMPLETAS:
            if col_camel not in df_to_save.columns:
                df_to_save[col_camel] = ''
        df_to_save = df_to_save[COLUNAS_PRODUTOS_COMPLETAS]
        csv_content = df_to_save.to_csv(index=False, encoding="utf-8-sig")
        try:
            contents = repo.get_contents(csv_remote_path, ref=branch)
            repo.update_file(contents.path, commit_message, csv_content, contents.sha, branch=branch)
            st.success("📁 Produtos atualizados no GitHub!")
        except Exception:
            repo.create_file(csv_remote_path, commit_message, csv_content, branch=branch)
            st.success("📁 Arquivo de produtos criado no GitHub!")
        carregar_produtos.clear()
        return True
    except Exception as e:
        st.warning(f"Falha ao enviar produtos para o GitHub — backup local mantido. Erro: ({e})")
        return False

def save_data_github_produtos(df, path, commit_message):
    """Função de compatibilidade que agora chama a função de salvar correta."""
    return salvar_produtos_no_github(df, commit_message)

# =================================================================================
# 🆕 FUNÇÕES DE PERSISTÊNCIA E LÓGICA DO CASHBACK
# =================================================================================

@st.cache_data(show_spinner="Carregando dados de Cashback...")
def carregar_cashback():
    """Carrega o DataFrame de Cashback, com fallback."""
    url_raw = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/{ARQ_CASHBACK}"
    df = load_csv_github(url_raw)
    
    if df is None or df.empty:
        try:
            # Tenta ler o arquivo localmente como backup
            df = pd.read_csv(ARQ_CASHBACK, dtype=str)
        except Exception:
            # Cria DataFrame vazio com as colunas esperadas
            df = pd.DataFrame(columns=COLUNAS_CASHBACK)
    
    # Garante que todas as colunas existam
    for col in COLUNAS_CASHBACK:
        if col not in df.columns:
            df[col] = ''
    
    # Normaliza tipos
    df["ID"] = df["ID"].astype(str)
    df["Saldo_Cashback"] = pd.to_numeric(df["Saldo_Cashback"], errors='coerce').fillna(0.0)
    df["Total_Gasto"] = pd.to_numeric(df["Total_Gasto"], errors='coerce').fillna(0.0)
    
    return df[COLUNAS_CASHBACK]

def salvar_cashback_no_github(df: pd.DataFrame, commit_message: str):
    """Salva o DataFrame de Cashback localmente e no GitHub."""
    if df is None or df.empty:
        st.warning("⚠️ Nenhum dado de cashback para salvar — operação ignorada.")
        return False
        
    # 1. Backup Local
    try:
        df.to_csv(ARQ_CASHBACK, index=False, encoding="utf-8-sig")
        st.toast("💾 Cashback salvo localmente!")
    except Exception as e:
        st.error(f"Erro ao salvar cashback localmente: {e}")
        return False
    
    # 2. Envio para o GitHub
    token = (st.secrets.get("GITHUB_TOKEN") or st.secrets.get("github_token") or GITHUB_TOKEN)
    repo_owner = st.secrets.get("REPO_OWNER") or st.secrets.get("owner") or OWNER
    repo_name = st.secrets.get("REPO_NAME") or st.secrets.get("repo") or REPO_NAME
    branch = st.secrets.get("BRANCH") or BRANCH
    csv_remote_path = ARQ_CASHBACK 
    
    if not token:
        st.warning("⚠️ Nenhum token do GitHub encontrado — apenas backup local foi salvo.")
        return False
        
    try:
        g = Github(token)
        repo = g.get_repo(f"{repo_owner}/{repo_name}")
        csv_content = df.to_csv(index=False, encoding="utf-8-sig")
        
        try:
            contents = repo.get_contents(csv_remote_path, ref=branch)
            repo.update_file(contents.path, commit_message, csv_content, contents.sha, branch=branch)
            st.toast("📁 Cashback atualizado no GitHub!")
        except Exception:
            repo.create_file(csv_remote_path, commit_message, csv_content, branch=branch)
            st.toast("📁 Arquivo de Cashback criado no GitHub!")
            
        carregar_cashback.clear()
        
        return True
    except Exception as e:
        st.warning(f"Falha ao enviar Cashback para o GitHub — backup local mantido. Erro: ({e})")
        return False


def obter_nivel_cashback(total_gasto: float) -> str:
    """Define o nível de cashback com base no total gasto pelo cliente (usando NIVEIS_CASHBACK)."""
    nivel_atual = "Bronze"
    max_gasto = -1
    
    for nivel, dados in NIVEIS_CASHBACK.items():
        if total_gasto >= dados["min_gasto"] and dados["min_gasto"] > max_gasto:
            max_gasto = dados["min_gasto"]
            nivel_atual = nivel
            
    return nivel_atual

def calcular_cashback_venda(valor_venda: float, cliente_id: str, df_cashback: pd.DataFrame) -> tuple[float, float, str]:
    """Calcula o valor do cashback para uma única venda."""
    
    if df_cashback is None or df_cashback.empty or not cliente_id:
        return 0.0, 0.0, "Bronze"
    
    cliente_row = df_cashback[df_cashback["ID"] == cliente_id]
    total_gasto_atual = 0.0
    
    if not cliente_row.empty:
        total_gasto_atual = cliente_row["Total_Gasto"].iloc[0]
        
    nivel = obter_nivel_cashback(total_gasto_atual)
    
    # Obtém o percentual do nível
    percentual_cashback = NIVEIS_CASHBACK.get(nivel, {"percentual": 0.00})["percentual"]
    
    valor_cashback = round(valor_venda * percentual_cashback, 2)
    
    return valor_cashback, percentual_cashback * 100, nivel

def creditar_cashback_e_atualizar_gasto(cliente_id: str, valor_venda: float, valor_cashback: float, df_cashback: pd.DataFrame):
    """Atualiza o saldo de cashback e o total gasto do cliente no DataFrame."""
    
    if df_cashback.empty: return df_cashback

    idx_cliente = df_cashback[df_cashback["ID"] == cliente_id].index
    
    if not idx_cliente.empty:
        idx = idx_cliente[0]
        
        # 1. Crédito do Cashback e Acumulação do Gasto
        df_cashback.loc[idx, "Saldo_Cashback"] += valor_cashback
        df_cashback.loc[idx, "Total_Gasto"] += valor_venda
        
        # 2. Atualiza o Nível com base no novo Total Gasto
        novo_total_gasto = df_cashback.loc[idx, "Total_Gasto"]
        novo_nivel = obter_nivel_cashback(novo_total_gasto)
        df_cashback.loc[idx, "Nivel"] = novo_nivel
        
    return df_cashback

# =================================================================================
# 🔄 Funções de carregamento com cache
# =================================================================================

@st.cache_data(show_spinner="Carregando promoções...")
def carregar_promocoes():
    COLUNAS_PROMO = ["ID_PROMOCAO", "ID_PRODUTO", "NOME_PRODUTO", "PRECO_ORIGINAL", "PRECO_PROMOCIONAL", "STATUS", "DATA_INICIO", "DATA_FIM"]
    url_raw = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/{ARQ_PROMOCOES}"
    df = load_csv_github(url_raw)
    if df is None or df.empty:
        try:
            df = pd.read_csv(ARQ_PROMOCOES, dtype=str)
            df.columns = [col.upper() for col in df.columns]
        except Exception:
            df = pd.DataFrame(columns=COLUNAS_PROMO)
    for col in COLUNAS_PROMO:
        if col not in df.columns:
            df[col] = ""
    return df[[col for col in COLUNAS_PROMO if col in df.columns]]

@st.cache_data(show_spinner="Carregando dados...")
def carregar_livro_caixa():
    url_raw = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/{PATH_DIVIDAS}"
    df = load_csv_github(url_raw)
    
    if df is None or df.empty:
        try:
            df = pd.read_csv(ARQ_LOCAL, dtype=str)
            df.columns = [col.upper().replace(' ', '_') for col in df.columns]
        except Exception:
            df = pd.DataFrame(columns=[c.upper().replace(' ', '_') for c in COLUNAS_PADRAO])
            
    if df.empty:
        df = pd.DataFrame(columns=[c.upper().replace(' ', '_') for c in COLUNAS_PADRAO])
        
    # Assegura que as colunas essenciais existam em MAIÚSCULAS/UNDERSCORE
    for col in [c.upper().replace(' ', '_') for c in COLUNAS_PADRAO_COMPLETO]:
        if col not in df.columns:
            df[col] = "REALIZADA" if col == "STATUS" else ""

    return processar_dataframe(df)

@st.cache_data(show_spinner="Carregando histórico de compras...")
def carregar_historico_compras():
    """Carrega o histórico de compras do GitHub, com fallback para o arquivo local."""
    url_raw = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/{ARQ_COMPRAS}"
    df = load_csv_github(url_raw)
    
    # Use uma lista de mapeamento para os nomes finais esperados
    colunas_esperadas = COLUNAS_COMPRAS 
    
    if df is None or df.empty:
        try:
            df = pd.read_csv(ARQ_COMPRAS, dtype=str)
            
            # Padroniza as colunas do arquivo local para facilitar o mapeamento
            df.columns = [col.upper().replace(' ', '_') for col in df.columns]
        except Exception:
            # Em caso de falha total, cria o DF vazio com as colunas esperadas
            return pd.DataFrame(columns=colunas_esperadas)
    
    # 1. Cria o mapeamento de colunas padronizadas para as colunas esperadas
    col_mapping = {
        col.upper().replace(' ', '_'): col
        for col in colunas_esperadas
    }
    
    # 2. Renomeia as colunas no DataFrame, usando o mapeamento
    # Isso converte 'DATA' para 'Data', 'VALOR_TOTAL' para 'Valor Total', etc.
    df.rename(columns=col_mapping, inplace=True)
    
    # 3. Garante que TODAS as colunas esperadas existam (e na ordem correta)
    df_final = pd.DataFrame(columns=colunas_esperadas)
    for col in colunas_esperadas:
        if col in df.columns:
            df_final[col] = df[col]
        else:
            df_final[col] = "" # Adiciona coluna vazia se estiver faltando
            
    return df_final

# --- BLOCO DE FUNÇÕES PARA CARREGAMENTO DE PRODUTOS ---
def processar_produtos(df_bruto):
    """FUNÇÃO 1: A ESPECIALISTA EM LIMPEZA."""
    df = df_bruto.copy()
    df["QUANTIDADE"] = pd.to_numeric(df.get("QUANTIDADE"), errors='coerce').fillna(0).astype(int)
    df["PRECOCUSTO"] = pd.to_numeric(df.get("PRECOCUSTO"), errors='coerce').fillna(0.0)
    df["PRECOVISTA"] = pd.to_numeric(df.get("PRECOVISTA"), errors='coerce').fillna(0.0)
    df["PRECOCARTAO"] = pd.to_numeric(df.get("PRECOCARTAO"), errors='coerce').fillna(0.0)
    df["VALIDADE"] = pd.to_datetime(df.get("VALIDADE"), errors='coerce').dt.date
    df["CASHBACKPERCENT"] = pd.to_numeric(df.get("CASHBACKPERCENT"), errors='coerce').fillna(0.0)
    df["DETALHESGRADE"] = df.get("DETALHESGRADE", pd.Series(dtype='str')).astype(str).replace('nan', '{}').replace('', '{}')
    COLUNAS_PRODUTOS_UPPER = [c.upper() for c in COLUNAS_PRODUTOS_COMPLETAS]
    df = df[[col for col in COLUNAS_PRODUTOS_UPPER if col in df.columns]]
    camel_case_map = {c.upper(): c for c in COLUNAS_PRODUTOS_COMPLETAS}
    df.rename(columns=camel_case_map, inplace=True, errors='ignore')
    return df

@st.cache_data(show_spinner="Carregando produtos do estoque...")
def carregar_produtos():
    """FUNÇÃO 2: A RESPONSÁVEL PELO CARREGAMENTO."""
    st.write("🔗 URL de carregamento:", f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/{ARQ_PRODUTOS}")
    df_base = load_csv_github(f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/{ARQ_PRODUTOS}")
    if df_base is None or df_base.empty:
        st.warning("⚠️ Falha ao carregar do GitHub. Tentando carregar o arquivo local...")
        try:
            df_base = pd.read_csv(ARQ_PRODUTOS, dtype=str)
        except Exception as e:
            st.error(f"❌ Falha ao carregar o arquivo local ({ARQ_PRODUTOS}): {e}")
            df_base = pd.DataFrame(columns=COLUNAS_PRODUTOS)
    df_base.columns = [col.upper() for col in df_base.columns]
    for col in [c.upper() for c in COLUNAS_PRODUTOS_COMPLETAS]:
        if col not in df_base.columns:
            df_base[col] = ''
    df_processado = processar_produtos(df_base)
    return df_processado

def inicializar_produtos():
    """FUNÇÃO 3: A GERENTE."""
    if "produtos" not in st.session_state or st.session_state.produtos.empty:
        st.session_state.produtos = carregar_produtos()
    return st.session_state.produtos

# ==================== FUNÇÕES DE LÓGICA DE NEGÓCIO (PRODUTOS/ESTOQUE) ====================
def ajustar_estoque(id_produto, quantidade, operacao="debitar"):
    if "produtos" not in st.session_state:
        inicializar_produtos()
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

def ler_codigo_barras_api(image_bytes):
    URL_DECODER_ZXING = "https://zxing.org/w/decode"
    try:
        files = {"f": ("barcode.png", image_bytes, "image/png")}
        response = requests.post(URL_DECODER_ZXING, files=files, timeout=30)
        if response.status_code != 200:
            if 'streamlit' in globals():
                st.error(f"❌ Erro na API ZXing. Status HTTP: {response.status_code}")
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
            try:
                st.toast("⚠️ API ZXing não retornou nenhum código válido. Tente novamente ou use uma imagem mais clara.")
            except Exception:
                pass
        return codigos
    except Exception as e:
        if 'streamlit' in globals():
            st.error(f"❌ Erro de Requisição/Conexão: {e}")
        return []

# ==================== FUNÇÕES DE CALLBACK (PRODUTOS) ====================
def callback_salvar_novo_produto(df_produtos, tipo_produto, nome, marca, categoria, qtd, preco_custo, preco_vista, validade, foto_url, codigo_barras, variações, cashback_percent, descricao_longa):
    if not nome:
        st.error("O nome do produto é obrigatório.")
        return False
    
    # Função auxiliar para adicionar linha no DF de produtos
    def add_product_row(df, p_id, p_nome, p_marca, p_categoria, p_qtd, p_custo, p_vista, p_cartao, p_validade, p_foto, p_cb, p_pai_id=None, p_cashback=0.0, p_detalhes="{}"):
        novo_id = prox_id(df, "ID")
        novo = {
            "ID": novo_id, "Nome": p_nome.strip(), "Marca": p_marca.strip(), "Categoria": p_categoria.strip(),
            "Quantidade": int(p_qtd), "PrecoCusto": to_float(p_custo), "PrecoVista": to_float(p_vista),
            "PrecoCartao": to_float(p_cartao), "Validade": str(p_validade), "FotoURL": p_foto.strip(),
            "CodigoBarras": str(p_cb).strip(), "PaiID": str(p_pai_id).strip() if p_pai_id else "",
            "CashbackPercent": to_float(p_cashback), "DetalhesGrade": p_detalhes
        }
        return pd.concat([df, pd.DataFrame([novo])], ignore_index=True), novo_id
    
    if tipo_produto == "Produto simples":
        # 1. Adiciona o Produto Simples no DF de Produtos
        produtos, new_id = add_product_row(
            df_produtos, None, nome, marca, categoria, qtd, preco_custo, preco_vista,
            round(to_float(preco_vista) / FATOR_CARTAO, 2) if to_float(preco_vista) > 0 else 0.0,
            validade, foto_url, codigo_barras, p_cashback=cashback_percent
        )
        
        # 2. Salva o DF de Produtos no GitHub
        if salvar_produtos_no_github(produtos, f"Novo produto simples: {nome} (ID {new_id})"):
            
            # 3. REGISTRO NO HISTÓRICO DE COMPRAS
            valor_custo_float = to_float(preco_custo)
            quantidade_int = int(qtd)
            
            if valor_custo_float > 0 and quantidade_int > 0:
                df_compras = carregar_historico_compras()
                valor_total_compra = valor_custo_float * quantidade_int

                nova_compra = {
                    "Data": date.today().strftime('%Y-%m-%d'),
                    "Produto": f"{nome} | ID: {new_id}",
                    "Quantidade": quantidade_int,
                    "Valor Total": valor_total_compra,
                    "Cor": "#007bff", 
                    "FotoURL": foto_url.strip(),
                }
                
                # Garante que as colunas do DF de compra correspondem ao COLUNAS_COMPRAS
                df_nova_compra = pd.DataFrame([nova_compra])[COLUNAS_COMPRAS] 
                df_compras = pd.concat([df_compras, df_nova_compra], ignore_index=True)
                
                # Salva o Histórico de Compras no GitHub
                salvar_historico_compras_no_github(df_compras, f"Registro de compra do novo produto simples: {nome}")
            # FIM DO NOVO BLOCO
            
            st.session_state.produtos = produtos
            carregar_produtos.clear()
            st.success(f"Produto '{nome}' cadastrado com sucesso!")
            st.session_state.cad_nome = ""
            st.session_state.cad_marca = ""
            st.session_state.cad_categoria = ""
            st.session_state.cad_qtd = 0
            st.session_state.cad_preco_custo = "0,00"
            st.session_state.cad_preco_vista = "0,00"
            if "cad_validade" in st.session_state: st.session_state.cad_validade = date.today()
            st.session_state.cad_foto_url = ""
            if "codigo_barras" in st.session_state:
                del st.session_state["codigo_barras"]
            return True
        return False
    
    elif tipo_produto == "Produto com variações (grade)":
        # 1. Adiciona o Produto PAI (com estoque 0)
        produtos, pai_id = add_product_row(
            df_produtos, None, nome, marca, categoria, 0, 0.0, 0.0, 0.0,
            validade, foto_url, codigo_barras, p_pai_id=None, p_cashback=cashback_percent
        )
        cont_variacoes = 0
        compras_para_historico = [] # Lista para acumular as compras das variações
        
        for var in variacoes:
            detalhes_grade_str = str(var.get("DetalhesGrade", "{}"))
            var_qtd = int(var.get("Quantidade", 0))
            
            if var.get("Nome") and var_qtd > 0:
                # Adiciona a variação (filho) ao DataFrame de produtos
                produtos, var_id = add_product_row(
                    produtos, None, f"{nome} ({var['Nome']})", marca, categoria,
                    var_qtd, var["PrecoCusto"], var["PrecoVista"], var["PrecoCartao"],
                    validade, var.get("FotoURL", foto_url), var.get("CodigoBarras", ""),
                    p_pai_id=pai_id, p_cashback=var.get("CashbackPercent", 0.0), p_detalhes=detalhes_grade_str
                )
                cont_variacoes += 1
                
                # PREPARA REGISTRO DE COMPRA DE VARIAÇÃO
                var_custo = to_float(var["PrecoCusto"])
                if var_custo > 0:
                    compras_para_historico.append({
                        "Data": date.today().strftime('%Y-%m-%d'),
                        "Produto": f"{nome} ({var['Nome']}) | ID: {var_id}",
                        "Quantidade": var_qtd,
                        "Valor Total": var_custo * var_qtd,
                        "Cor": "#007bff",
                        "FotoURL": var.get("FotoURL", foto_url).strip(),
                    })
        
        if cont_variacoes > 0:
            # 2. Salva o DF de Produtos (Pai + Filhos)
            if salvar_produtos_no_github(produtos, f"Novo produto com grade: {nome} ({cont_variacoes} variações)"):
                
                # 3. SALVAR HISTÓRICO DE COMPRAS DA GRADE
                if compras_para_historico:
                    df_compras = carregar_historico_compras()
                    
                    # Garante que as colunas do DF de compra correspondem ao COLUNAS_COMPRAS
                    df_novas_compras = pd.DataFrame(compras_para_historico)[COLUNAS_COMPRAS] 
                    df_compras = pd.concat([df_compras, df_novas_compras], ignore_index=True)
                    
                    # Salva o Histórico de Compras no GitHub
                    salvar_historico_compras_no_github(df_compras, f"Registro de compra do novo produto com grade: {nome}")
                # FIM DO NOVO BLOCO
                
                st.session_state.produtos = produtos
                inicializar_produtos.clear()
                st.success(f"Produto '{nome}' com {cont_variacoes} variações cadastrado com sucesso!")
                st.session_state.cad_nome = ""
                st.session_state.cad_marca = ""
                st.session_state.cad_categoria = ""
                if "cad_validade" in st.session_state: st.session_state.cad_validade = date.today()
                st.session_state.cad_foto_url = ""
                if "codigo_barras" in st.session_state:
                    del st.session_state["codigo_barras"]
                st.session_state.cb_grade_lidos = {}
                return True
            return False
        else:
            # Remove o produto pai se nenhuma variação foi salva
            produtos = produtos[produtos["ID"] != pai_id]
            st.session_state.produtos = produtos
            st.error("Nenhuma variação válida foi fornecida. O produto principal não foi salvo.")
            return False
            
    return False

def callback_adicionar_manual(nome, qtd, preco, custo):
    if nome and qtd > 0:
        st.session_state.lista_produtos.append({
            "Produto_ID": "", "Produto": nome, "Quantidade": qtd,
            "Preço Unitário": preco, "Custo Unitário": custo
        })
        st.session_state.input_nome_prod_manual = ""
        st.session_state.input_qtd_prod_manual = 1.0
        st.session_state.input_preco_prod_manual = 0.01
        st.session_state.input_custo_prod_manual = 0.00
        st.session_state.input_produto_selecionado = ""

def callback_adicionar_estoque(prod_id, prod_nome, qtd, preco, custo, estoque_disp):
    promocoes = norm_promocoes(carregar_promocoes())
    hoje = date.today()
    promocao_ativa = promocoes[
        (promocoes["ID_PRODUTO"] == prod_id) &
        (promocoes["DATA_INICIO"] <= hoje) &
        (promocoes["DATA_FIM"] >= hoje)
    ]
    preco_unitario_final = preco
    if not promocao_ativa.empty:
        preco_unitario_final = promocao_ativa.iloc[0]["PRECO_PROMOCIONAL"]
        preco_original_calc = promocao_ativa.iloc[0]["PRECO_ORIGINAL"]
        desconto_aplicado = 0
        if preco_original_calc > 0:
            desconto_aplicado = (1 - (preco_unitario_final / preco_original_calc)) * 100
        try:
            st.toast(f"🏷️ Promoção de {desconto_aplicado:.0f}% aplicada a {prod_nome}! Preço: R$ {preco_unitario_final:.2f}")
        except Exception:
            pass
    if qtd > 0 and qtd <= estoque_disp:
        st.session_state.lista_produtos.append({
            "Produto_ID": prod_id, "Produto": prod_nome, "Quantidade": qtd,
            "Preço Unitário": round(float(preco_unitario_final), 2), "Custo Unitário": custo
        })
        st.session_state.input_produto_selecionado = ""
    else:
        st.warning("A quantidade excede o estoque ou é inválida.")

# ==================== FUNÇÕES DE ANÁLISE (HOMEPAGE) ====================
@st.cache_data(show_spinner="Calculando mais vendidos...")
def get_most_sold_products(df_movimentacoes):
    df_vendas = df_movimentacoes[
        (df_movimentacoes["Tipo"] == "Entrada") & 
        (df_movimentacoes["Status"] == "Realizada") & 
        (df_movimentacoes["Produtos Vendidos"].notna()) & 
        (df_movimentacoes["Produtos Vendidos"] != "")
    ].copy()
    if df_vendas.empty:
        return pd.DataFrame(columns=["Produto_ID", "Quantidade Total Vendida"])
    vendas_list = []
    for produtos_json in df_vendas["Produtos Vendidos"]: 
        try:
            try:
                produtos = json.loads(produtos_json)
            except (json.JSONDecodeError, TypeError):
                produtos = ast.literal_eval(produtos_json)
            if isinstance(produtos, list):
                for item in produtos:
                    produto_id = str(item.get("Produto_ID"))
                    if produto_id and produto_id != "None":
                        vendas_list.append({
                            "Produto_ID": produto_id,
                            "Quantidade": to_float(item.get("Quantidade", 0))
                        })
        except Exception:
            continue
    df_vendas_detalhada = pd.DataFrame(vendas_list)
    if df_vendas_detalhada.empty:
        return pd.DataFrame(columns=["Produto_ID", "Quantidade Total Vendida"])
    df_mais_vendidos = df_vendas_detalhada.groupby("Produto_ID")["Quantidade"].sum().reset_index()
    df_mais_vendidos.rename(columns={"Quantidade": "Quantidade Total Vendida"}, inplace=True)
    df_mais_vendidos.sort_values(by="Quantidade Total Vendida", ascending=False, inplace=True)
    return df_mais_vendidos

# Compatibilidade de nomes (alias)
try:
    get_most_sold = get_most_sold_products
except Exception:
    pass
