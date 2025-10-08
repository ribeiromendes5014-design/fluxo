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

# =================================================================================
# Importa as constantes de negócio e de arquivo
from constants_and_css import (
    TOKEN, OWNER, REPO_NAME, BRANCH, GITHUB_TOKEN, GITHUB_REPO, GITHUB_BRANCH,
    PATH_DIVIDAS, ARQ_PRODUTOS, ARQ_LOCAL, ARQ_COMPRAS, ARQ_PROMOCOES,
    COLUNAS_COMPRAS, COLUNAS_PADRAO, COLUNAS_PADRAO_COMPLETO, COLUNAS_COMPLETAS_PROCESSADAS,
    COLUNAS_PRODUTOS, FATOR_CARTAO, COMMIT_MESSAGE, COMMIT_MESSAGE_EDIT, COMMIT_MESSAGE_DELETE
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
def load_csv_github(url: str) -> pd.DataFrame | None:
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()

        # 🔧 tenta detectar automaticamente o delimitador
        import csv
        sample = response.text[:500]
        sniffer = csv.Sniffer()
        delimiter = ","  # padrão
        try:
            delimiter = sniffer.sniff(sample).delimiter
        except Exception:
            pass

        df = pd.read_csv(StringIO(response.text), dtype=str, sep=delimiter, encoding="utf-8-sig")

        # Padroniza colunas
        df.columns = [col.upper().replace(' ', '_') for col in df.columns]

        # Não descarta se tiver 1 coluna — apenas avisa
        if df.empty:
            st.warning("⚠️ O arquivo CSV está vazio ou sem dados válidos.")
        return df
    except Exception as e:
        st.error(f"❌ Erro ao ler CSV do GitHub: {e}")
        return None



# =================================================================================
# 🔧 Funções de Lógica e Persistência Faltantes (Adicionadas)
# =================================================================================

def norm_promocoes(df_promocoes: pd.DataFrame) -> pd.DataFrame:
    """Normaliza o DataFrame de promoções, convertendo datas e garantindo tipos. Retorna APENAS as promoções ativas."""
    
    # ATUALIZAÇÃO: Usa as colunas do NOVO cabeçalho
    COLUNAS_PROMO_NOVAS = ["ID_PROMOCAO", "ID_PRODUTO", "NOME_PRODUTO", "PRECO_ORIGINAL", "PRECO_PROMOCIONAL", "STATUS", "DATA_INICIO", "DATA_FIM"]
    
    if df_promocoes is None or df_promocoes.empty:
        return pd.DataFrame(columns=COLUNAS_PROMO_NOVAS)
    
    df = df_promocoes.copy()
    
    # Garante que as novas colunas existam, caso o CSV antigo ainda esteja sendo lido.
    for col in COLUNAS_PROMO_NOVAS:
        if col not in df.columns:
            df[col] = ''
    
    # Converte colunas de data para tipo date (usa os novos nomes)
    for col in ["DATA_INICIO", "DATA_FIM"]:
        df[col] = pd.to_datetime(df[col], errors='coerce').dt.date

    # Converte as colunas de preço (usa os novos nomes)
    df["PRECO_ORIGINAL"] = pd.to_numeric(df["PRECO_ORIGINAL"], errors='coerce').fillna(0.0)
    df["PRECO_PROMOCIONAL"] = pd.to_numeric(df["PRECO_PROMOCIONAL"], errors='coerce').fillna(0.0)

    # Filtra as promoções que não expiraram e já começaram
    hoje = date.today()
    
    # O filtro agora usa STATUS e as novas colunas de data
    df_ativas = df[
        (df["STATUS"].astype(str).str.upper() == 'ATIVO') &
        (df["DATA_FIM"] >= hoje) & 
        (df["DATA_INICIO"] <= hoje)
    ].copy()
    
    # Retorna apenas as colunas do novo cabeçalho
    return df_ativas[COLUNAS_PROMO_NOVAS] 


def salvar_historico_no_github(df: pd.DataFrame, commit_message: str):
    """
    Função genérica para salvar o livro caixa (dividas/movimentações) no GitHub.
    Usa constantes definidas em constants_and_css.
    """
    try:
        from constants_and_css import PATH_DIVIDAS as CONST_PATH, OWNER as CONST_OWNER, REPO_NAME as CONST_REPO, BRANCH as CONST_BRANCH
    except Exception:
        return False

    token = (st.secrets.get("GITHUB_TOKEN") or st.secrets.get("github_token") or GITHUB_TOKEN)
    repo_owner = st.secrets.get("REPO_OWNER") or st.secrets.get("owner") or CONST_OWNER
    repo_name = st.secrets.get("REPO_NAME") or st.secrets.get("repo") or CONST_REPO
    branch = st.secrets.get("BRANCH") or CONST_BRANCH
    
    csv_remote_path = CONST_PATH or "movimentacoes.csv"

    if not token:
        st.warning("⚠️ Nenhum token do GitHub encontrado. Salve manualmente.")
        return False
    
    # Salvar localmente (backup)
    try:
        df.to_csv(ARQ_LOCAL, index=True, encoding="utf-8-sig")
    except Exception as e:
        st.error(f"Erro ao salvar localmente: {e}")

    try:
        from github import Github
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
        
        carregar_livro_caixa.clear() # Limpa o cache após salvar
        return True

    except Exception as e:
        st.warning(f"Falha ao enviar dados para o GitHub — backup local mantido. ({e})")
        return False


def processar_dataframe(df_movimentacoes: pd.DataFrame) -> pd.DataFrame:
    """Processa o dataframe de movimentações para exibição e cálculo de saldo."""
    if df_movimentacoes is None or df_movimentacoes.empty:
        return pd.DataFrame(columns=[c.upper().replace(' ', '_') for c in COLUNAS_COMPLETAS_PROCESSADAS])

    df = df_movimentacoes.copy()
    
    # 1. Limpeza e Conversão (Usando MAIÚSCULAS/UNDERSCORE)
    
    # --- CORREÇÃO ADICIONADA (ValueError) ---
    # Garante que uma coluna com o nome 'index' seja removida antes de
    # chamar reset_index(), evitando o ValueError.
    if 'index' in df.columns:
        df = df.drop(columns=['index'])
    
    # --- CORREÇÃO ADICIONADA (IndentationError e Lógica) ---
    # Remove a coluna 'original_index' se ela já existir para evitar conflito.
    if 'original_index' in df.columns:
        df = df.drop(columns=['original_index'])

    # Agora, renomeia o índice e o transforma em uma coluna com segurança.
    df.index.name = 'original_index'
    df = df.reset_index()
    
    df["VALOR"] = pd.to_numeric(df["VALOR"], errors='coerce').fillna(0.0) 
    
    # Conversão de datas
    df["DATA"] = pd.to_datetime(df["DATA"], errors='coerce').dt.date 
    df["DATA_PAGAMENTO"] = pd.to_datetime(df["DATA_PAGAMENTO"], errors='coerce').dt.date 
    df["Data_dt"] = pd.to_datetime(df["DATA"]) 
    
    # 2. Cor do Valor (Para estilização no Streamlit)
    df['Cor_Valor'] = df['VALOR'].apply(lambda x: 'green' if x >= 0 else 'red') 
    
    # 3. ID Visível (Simples)
    if 'ID_VISÍVEL' not in df.columns or df['ID_VISÍVEL'].isnull().all():
        df['ID_VISÍVEL'] = range(1, len(df) + 1)
    
    # 4. Cálculo de Saldo Acumulado (Apenas para Realizadas)
    df_realizadas = df[df['STATUS'] == 'REALIZADA'].copy()
    # Garante que 'original_index' exista antes de ordenar
    if 'original_index' in df_realizadas.columns:
        df_realizadas = df_realizadas.sort_values(by=['DATA', 'original_index']) 
        df_realizadas['Saldo Acumulado'] = df_realizadas['VALOR'].cumsum() 
        
        # Merge de volta para o DF completo (para que as pendentes não tenham saldo)
        df = df.merge(df_realizadas[['original_index', 'Saldo Acumulado']], on='original_index', how='left')
    else:
        # Se 'original_index' não foi criado, adiciona a coluna de saldo vazia para evitar erros
        df['Saldo Acumulado'] = pd.NA

    # --- BLOCO CRÍTICO: Renomear de volta para o formato CamelCase esperado pelas páginas ---
    # Mapeamento de MAIÚSCULAS/UNDERSCORE para o formato esperado pelo resto do app (CamelCase)
    livro_caixa_map = {
        'DATA': 'Data',
        'LOJA': 'Loja',
        'CLIENTE': 'Cliente',
        'VALOR': 'Valor',
        'FORMA_DE_PAGAMENTO': 'Forma de Pagamento',
        'TIPO': 'Tipo',
        'PRODUTOS_VENDIDOS': 'Produtos Vendidos',
        'CATEGORIA': 'Categoria',
        'STATUS': 'Status',
        'DATA_PAGAMENTO': 'Data Pagamento', 
        'RECORRENCIAID': 'RecorrenciaID',
        'TRANSACAOPAIID': 'TransacaoPaiID',
        'ID_VISÍVEL': 'ID Visível', 
    }
    
    # Tenta renomear o DF
    df.rename(columns=livro_caixa_map, inplace=True, errors='ignore')
    # --- FIM BLOCO CRÍTICO ---
    
    return df


def calcular_resumo(df_movimentacoes: pd.DataFrame):
    """Calcula o total de entradas, saídas e o saldo líquido de um DataFrame."""
    if df_movimentacoes is None or df_movimentacoes.empty:
        return 0.0, 0.0, 0.0
    
    # Assume que o DF já foi processado e tem as colunas em CamelCase
    df = df_movimentacoes.copy()
    df["Valor"] = pd.to_numeric(df["Valor"], errors='coerce').fillna(0.0) 
    
    total_entradas = df[df['Valor'] >= 0]['Valor'].sum()
    total_saidas = abs(df[df['Valor'] < 0]['Valor'].sum())
    saldo = total_entradas - total_saidas
    
    return round(total_entradas, 2), round(total_saidas, 2), round(saldo, 2)


# =================================================================================
# 🔑 FUNÇÃO DE PERSISTÊNCIA CRÍTICA: salvar_promocoes_no_github
# (Mantida)
# =================================================================================
def salvar_promocoes_no_github(df: pd.DataFrame, commit_message: str = "Atualiza promoções"):
    """Salva o CSV de promoções localmente e, se possível, também no GitHub."""
    try:
        from constants_and_css import ARQ_PROMOCOES, OWNER as CONST_OWNER, REPO_NAME as CONST_REPO, BRANCH as CONST_BRANCH
    except Exception as e:
        st.error(f"❌ Erro ao carregar constantes do projeto: {e}")
        return False

    # --- 1) Salvar localmente ---
    try:
        df.to_csv(ARQ_PROMOCOES, index=False, encoding="utf-8-sig")
        try:
            st.toast("💾 Promoções salvas localmente!")
        except Exception:
            pass
    except Exception as e:
        st.error(f"Erro ao salvar promoções localmente: {e}")
        return False

    # --- 2) Tentar salvar no GitHub ---
    token = (
        st.secrets.get("GITHUB_TOKEN")
        or st.secrets.get("github_token")
        or GITHUB_TOKEN
    )
    repo_owner = st.secrets.get("REPO_OWNER") or st.secrets.get("owner") or CONST_OWNER
    repo_name = st.secrets.get("REPO_NAME") or st.secrets.get("repo") or CONST_REPO
    branch = st.secrets.get("BRANCH") or CONST_BRANCH
    csv_remote_path = os.path.basename(ARQ_PROMOCOES) or "promocoes.csv"

    if not token:
        st.warning("⚠️ Nenhum token do GitHub encontrado — apenas backup local salvo.")
        return False

    try:
        from github import Github
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


# =================================================================================
# 🔧 Funções de persistência para PRODUTOS (CORRIGIDO)
# =================================================================================

def salvar_produtos_no_github(df: pd.DataFrame, commit_message: str):
    """
    Salva o DataFrame de produtos localmente como backup e o envia para o GitHub.
    Evita sobrescrever o CSV remoto quando o DataFrame está vazio.
    """

    # 🚨 Proteção contra sobrescrita acidental
    if df is None or df.empty:
        st.warning("⚠️ Nenhum produto para salvar — operação ignorada para evitar sobrescrever o CSV no GitHub.")
        return False

    # --- 1) Salvar localmente (backup) ---
    try:
        df.to_csv(ARQ_PRODUTOS, index=False, encoding="utf-8-sig")
        st.toast("💾 Produtos salvos localmente!")
    except Exception as e:
        st.error(f"Erro ao salvar produtos localmente: {e}")
        return False


    # --- 2) Tentar salvar no GitHub ---
    token = (
        st.secrets.get("GITHUB_TOKEN")
        or st.secrets.get("github_token")
        or GITHUB_TOKEN
    )
    repo_owner = st.secrets.get("REPO_OWNER") or st.secrets.get("owner") or OWNER
    repo_name = st.secrets.get("REPO_NAME") or st.secrets.get("repo") or REPO_NAME
    branch = st.secrets.get("BRANCH") or BRANCH
    csv_remote_path = ARQ_PRODUTOS

    if not token:
        st.warning("⚠️ Nenhum token do GitHub encontrado — apenas backup local foi salvo.")
        return False

    try:
        from github import Github
        g = Github(token)
        repo = g.get_repo(f"{repo_owner}/{repo_name}")

        # CRIA O MAPA COM TODAS AS COLUNAS ESPERADAS (Assumindo que Cash/Detalhe foram adicionados)
        COLUNAS_PRODUTOS_COMPLETAS = COLUNAS_PRODUTOS + ["CashbackPercent", "DetalhesGrade"]
        camel_case_map = {c.upper(): c for c in COLUNAS_PRODUTOS_COMPLETAS}

        df_to_save = df.copy()
        
        # Garante que as colunas existam no DF a ser salvo antes de renomear e converter
        for col_camel, col_upper in camel_case_map.items():
             if col_camel not in df_to_save.columns:
                 # Se a coluna CamelCase não existe (e deveria), cria com valor padrão
                 df_to_save[col_camel] = ''

        # Renomeia do formato MAIÚSCULO/UNDERSCORE (se vier assim) para CamelCase
        df_to_save.rename(columns=camel_case_map, inplace=True, errors='ignore')
        
        # Reordena para garantir que o CSV tenha a ordem correta
        df_to_save = df_to_save[[c for c in COLUNAS_PRODUTOS_COMPLETAS if c in df_to_save.columns]]

        # Converte o DataFrame para CSV
        csv_content = df_to_save.to_csv(index=False, encoding="utf-8-sig")

        try:
            # Tenta atualizar o arquivo existente
            contents = repo.get_contents(csv_remote_path, ref=branch)
            repo.update_file(contents.path, commit_message, csv_content, contents.sha, branch=branch)
            st.success("📁 Produtos atualizados no GitHub!")
        except Exception:
            # Se não existir, cria o arquivo
            repo.create_file(csv_remote_path, commit_message, csv_content, branch=branch)
            st.success("📁 Arquivo de produtos criado no GitHub!")
        
        # Limpa o cache para forçar a releitura dos dados na próxima vez
        inicializar_produtos.clear()
        return True

    except Exception as e:
        st.warning(f"Falha ao enviar produtos para o GitHub — backup local mantido. Erro: ({e})")
        return False


def save_data_github_produtos(df, path, commit_message):
    """
    Função de compatibilidade que agora chama a função de salvar correta.
    """
    return salvar_produtos_no_github(df, commit_message)


# =================================================================================
# 🔄 Funções de carregamento com cache
# =================================================================================
@st.cache_data(show_spinner="Carregando promoções...")
def carregar_promocoes():
    # ATUALIZAÇÃO: Usa as colunas do NOVO cabeçalho
    COLUNAS_PROMO = ["ID_PROMOCAO", "ID_PRODUTO", "NOME_PRODUTO", "PRECO_ORIGINAL", "PRECO_PROMOCIONAL", "STATUS", "DATA_INICIO", "DATA_FIM"]
    url_raw = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/{ARQ_PROMOCOES}"
    df = load_csv_github(url_raw)
    
    if df is None or df.empty:
        try:
            df = pd.read_csv(ARQ_PROMOCOES, dtype=str)
            df.columns = [col.upper() for col in df.columns]
        except Exception:
            df = pd.DataFrame(columns=COLUNAS_PROMO)
            
    # Garante que as novas colunas existam
    for col in COLUNAS_PROMO:
        if col not in df.columns:
            df[col] = ""
            
    return df[[col for col in COLUNAS_PROMO if col in df.columns]]


@st.cache_data(show_spinner="Carregando dados...")
def carregar_livro_caixa():
    url_raw = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/{PATH_DIVIDAS}"
    df = load_csv_github(url_raw)
    
    # O Livro Caixa é processado e renomeado para CamelCase em processar_dataframe
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


@st.cache_data(show_spinner="Carregando produtos do estoque...")
def inicializar_produtos():
    if "produtos" not in st.session_state:
        # 1. Tenta carregar do GitHub (prioridade)
        url_raw = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/{ARQ_PRODUTOS}"
        df_carregado = load_csv_github(url_raw) 
        
        # 2. Se o carregamento remoto falhar ou retornar vazio, tenta carregar localmente
        if df_carregado is None or df_carregado.empty:
            st.warning("⚠️ Falha ao carregar produtos do GitHub. Tentando carregar o arquivo local...")
            try:
                df_base = pd.read_csv(ARQ_PRODUTOS, dtype=str) 
                df_base.columns = [col.upper() for col in df_base.columns] 
            except Exception as e:
                st.error(f"❌ Falha ao carregar o arquivo local ({ARQ_PRODUTOS}): {e}")
                df_base = pd.DataFrame(columns=[c.upper() for c in COLUNAS_PRODUTOS])
        else:
            df_base = df_carregado

        # CRIA A LISTA COMPLETA DE COLUNAS (incluindo as que estavam faltando)
        COLUNAS_PRODUTOS_COMPLETAS = COLUNAS_PRODUTOS + ["CashbackPercent", "DetalhesGrade"]
        COLUNAS_PRODUTOS_UPPER = [c.upper() for c in COLUNAS_PRODUTOS_COMPLETAS]
        
        # Processamento dos dados (em MAIÚSCULAS)
        for col in COLUNAS_PRODUTOS_UPPER:
            if col not in df_base.columns:
                df_base[col] = ''

        # Conversão de tipos (usando MAIÚSCULAS)
        df_base["QUANTIDADE"] = pd.to_numeric(df_base["QUANTIDADE"], errors='coerce').fillna(0).astype(int)
        df_base["PRECOCUSTO"] = pd.to_numeric(df_base["PRECOCUSTO"], errors='coerce').fillna(0.0)
        df_base["PRECOVISTA"] = pd.to_numeric(df_base["PRECOVISTA"], errors='coerce').fillna(0.0)
        df_base["PRECOCARTAO"] = pd.to_numeric(df_base["PRECOCARTAO"], errors='coerce').fillna(0.0)
        df_base["VALIDADE"] = pd.to_datetime(df_base["VALIDADE"], errors='coerce').dt.date
        
        # 🚨 CORREÇÃO CRÍTICA: Conversão de tipos para as novas colunas
        df_base["CASHBACKPERCENT"] = pd.to_numeric(df_base["CASHBACKPERCENT"], errors='coerce').fillna(0.0)
        # Garante que DetalhesGrade seja sempre uma string representando um dicionário vazio se for nulo
        df_base["DETALHESGRADE"] = df_base["DETALHESGRADE"].astype(str).replace('nan', '{}').replace('', '{}')
        
        # Filtra apenas as colunas necessárias
        df_base = df_base[[col for col in COLUNAS_PRODUTOS_UPPER if col in df_base.columns]]
        
        # --- BLOCO CRÍTICO: Renomear de volta para o formato CamelCase esperado pelas páginas ---
        camel_case_map = {c.upper(): c for c in COLUNAS_PRODUTOS_COMPLETAS}
        df_base.rename(columns=camel_case_map, inplace=True, errors='ignore')
        # --- FIM DO BLOCO CRÍTICO ---
        
        st.session_state.produtos = df_base
    return st.session_state.produtos


@st.cache_data(show_spinner="Carregando histórico de compras...")
def carregar_historico_compras():
    url_raw = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/{ARQ_COMPRAS}"
    df = load_csv_github(url_raw)
    
    COLUNAS_COMPRAS_UPPER = [c.upper() for c in COLUNAS_COMPRAS]
    
    if df is None or df.empty:
        df = pd.DataFrame(columns=COLUNAS_COMPRAS_UPPER)
        
    for col in COLUNAS_COMPRAS_UPPER:
        if col not in df.columns:
            df[col] = ""
            
    # Renomear colunas para o formato esperado pela página de exibição
    camel_case_map = {c.upper(): c for c in COLUNAS_COMPRAS}
    df.rename(columns=camel_case_map, inplace=True, errors='ignore')
            
    return df[[col for col in COLUNAS_COMPRAS if col in df.columns]]


# ==================== FUNÇÕES DE LÓGICA DE NEGÓCIO (PRODUTOS/ESTOQUE) ====================
# (Mantidas)
# =================================================================================
def ajustar_estoque(id_produto, quantidade, operacao="debitar"):
    if "produtos" not in st.session_state:
        inicializar_produtos()
    produtos_df = st.session_state.produtos
    
    # Usa colunas em CamelCase
    idx_produto = produtos_df[produtos_df["ID"] == id_produto].index
    
    if not idx_produto.empty:
        idx = idx_produto[0]
        # Usa colunas em CamelCase
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
# CORRIGIDO: Adiciona CashbackPercent e DetalhesGrade
# =================================================================================
# ATENÇÃO: A função callback_salvar_novo_produto no arquivo 'py.py' (enviado anteriormente)
# tem 13 argumentos. Para compatibilidade, é preciso garantir que a assinatura aqui também tenha 13.
# O py.py tinha: callback_salvar_novo_produto(produtos.copy(), tipo_produto, nome, marca, categoria, qtd, preco_custo, preco_vista, validade, foto_url, codigo_barras, variações, cashback_percent)
# O código original (que estava incompleto) tinha 12.
def callback_salvar_novo_produto(produtos, tipo_produto, nome, marca, categoria, qtd, preco_custo, preco_vista, validade, foto_url, codigo_barras, variacoes, cashback_percent=0.0):
    if not nome:
        st.error("O nome do produto é obrigatório.")
        return False

    # CORRIGIDO: Adiciona p_cashback e p_detalhes na definição da linha
    def add_product_row(df, p_id, p_nome, p_marca, p_categoria, p_qtd, p_custo, p_vista, p_cartao, p_validade, p_foto, p_cb, p_pai_id=None, p_cashback=0.0, p_detalhes="{}"):
        novo_id = prox_id(df, "ID")
        # Mantém as chaves CamelCase aqui para que a escrita use o cabeçalho original se for o caso
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
            "PaiID": str(p_pai_id).strip() if p_pai_id else "",
            "CashbackPercent": to_float(p_cashback),  # 🚨 Nova coluna
            "DetalhesGrade": p_detalhes              # 🚨 Nova coluna
        }
        return pd.concat([df, pd.DataFrame([novo])], ignore_index=True), novo_id

    if tipo_produto == "Produto simples":
        produtos, new_id = add_product_row(
            produtos, None, nome, marca, categoria,
            qtd, preco_custo, preco_vista,
            round(to_float(preco_vista) / FATOR_CARTAO, 2) if to_float(preco_vista) > 0 else 0.0,
            validade, foto_url, codigo_barras,
            p_cashback=cashback_percent # Passa o cashback
        )
        if salvar_produtos_no_github(produtos, f"Novo produto simples: {nome} (ID {new_id})"):
            st.session_state.produtos = produtos
            inicializar_produtos.clear()
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
        produtos, pai_id = add_product_row(
            produtos, None, nome, marca, categoria,
            0, 0.0, 0.0, 0.0,
            validade, foto_url, codigo_barras,
            p_pai_id=None,
            p_cashback=cashback_percent # Passa o cashback do pai
        )
        cont_variacoes = 0
        for var in variacoes:
            detalhes_grade_str = str(var.get("DetalhesGrade", "{}"))
            
            if var.get("Nome") and var.get("Quantidade", 0) > 0:
                produtos, _ = add_product_row(
                    produtos, None,
                    f"{nome} ({var['Nome']})", marca, categoria,
                    var["Quantidade"], var["PrecoCusto"], var["PrecoVista"], var["PrecoCartao"],
                    validade, var.get("FotoURL", foto_url), var.get("CodigoBarras", ""),
                    p_pai_id=pai_id,
                    p_cashback=var.get("CashbackPercent", 0.0), # Passa o cashback da variação
                    p_detalhes=detalhes_grade_str # Passa os detalhes da grade
                )
                cont_variacoes += 1

        if cont_variacoes > 0:
            if salvar_produtos_no_github(produtos, f"Novo produto com grade: {nome} ({cont_variacoes} variações)"):
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
            # Exclui o produto pai que foi criado se não houver variações válidas
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
    promocoes = norm_promocoes(carregar_promocoes())
    hoje = date.today()
    
    # Usa as novas colunas para filtrar as promoções
    promocao_ativa = promocoes[
        (promocoes["ID_PRODUTO"] == prod_id) &
        (promocoes["DATA_INICIO"] <= hoje) &
        (promocoes["DATA_FIM"] >= hoje)
    ]
    
    preco_unitario_final = preco
    if not promocao_ativa.empty:
        # Usa PRECO_PROMOCIONAL
        preco_unitario_final = promocao_ativa.iloc[0]["PRECO_PROMOCIONAL"]
        
        # Calcula o desconto apenas para a mensagem de toast
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
            "Produto_ID": prod_id,
            "Produto": prod_nome,
            "Quantidade": qtd,
            "Preço Unitário": round(float(preco_unitario_final), 2),
            "Custo Unitário": custo
        })
        st.session_state.input_produto_selecionado = ""
    else:
        st.warning("A quantidade excede o estoque ou é inválida.")


# ==================== FUNÇÕES DE ANÁLISE (HOMEPAGE) ====================
# (Mantidas)
# =================================================================================
@st.cache_data(show_spinner="Calculando mais vendidos...")
def get_most_sold_products(df_movimentacoes):
    # Assume que df_movimentacoes está em CamelCase (após processar_dataframe)
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


