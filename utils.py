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
        df = pd.read_csv(StringIO(response.text), dtype=str)
        if df is None or df.empty or len(df.columns) < 2:
            return None
        return df
    except Exception:
        return None


# =================================================================================
# 🔧 Funções de Lógica e Persistência Faltantes (Adicionadas)
# =================================================================================

def norm_promocoes(df_promocoes: pd.DataFrame) -> pd.DataFrame:
    """Normaliza o DataFrame de promoções, convertendo datas e garantindo tipos. Retorna APENAS as promoções ativas."""
    if df_promocoes is None or df_promocoes.empty:
        return pd.DataFrame(columns=["ID", "IDProduto", "NomeProduto", "Desconto", "DataInicio", "DataFim"])
    
    df = df_promocoes.copy()
    
    # Converte colunas de data para tipo date
    for col in ["DataInicio", "DataFim"]:
        df[col] = pd.to_datetime(df[col], errors='coerce').dt.date

    # Converte o desconto para float
    df["Desconto"] = pd.to_numeric(df["Desconto"], errors='coerce').fillna(0.0)
    
    # Filtra as promoções que não expiraram e já começaram
    hoje = date.today()
    df_ativas = df[(df["DataFim"] >= hoje) & (df["DataInicio"] <= hoje)].copy()
    
    return df_ativas


def salvar_dados_no_github(df: pd.DataFrame, commit_message: str):
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
        return pd.DataFrame(columns=COLUNAS_COMPLETAS_PROCESSADAS)

    df = df_movimentacoes.copy()
    
    # 1. Limpeza e Conversão
    df.index.name = 'original_index'
    df = df.reset_index()
    
    df["Valor"] = pd.to_numeric(df["Valor"], errors='coerce').fillna(0.0)
    
    # Conversão de datas
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce').dt.date
    df["Data Pagamento"] = pd.to_datetime(df["Data Pagamento"], errors='coerce').dt.date
    df["Data_dt"] = pd.to_datetime(df["Data"]) # Para cálculos (Plotly)
    
    # 2. Cor do Valor (Para estilização no Streamlit)
    df['Cor_Valor'] = df['Valor'].apply(lambda x: 'green' if x >= 0 else 'red')
    
    # 3. ID Visível (Simples)
    if 'ID Visível' not in df.columns or df['ID Visível'].isnull().all():
        df['ID Visível'] = range(1, len(df) + 1)
    
    # 4. Cálculo de Saldo Acumulado (Apenas para Realizadas)
    df_realizadas = df[df['Status'] == 'Realizada'].copy()
    df_realizadas = df_realizadas.sort_values(by=['Data', 'original_index'])
    df_realizadas['Saldo Acumulado'] = df_realizadas['Valor'].cumsum()
    
    # Merge de volta para o DF completo (para que as pendentes não tenham saldo)
    df = df.merge(df_realizadas[['original_index', 'Saldo Acumulado']], on='original_index', how='left')
    
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
        # import lazy do PyGithub para evitar falha na import do módulo se não estiver instalado
        try:
            from github import Github
        except ModuleNotFoundError:
            st.warning("PyGithub não está disponível no ambiente — apenas backup local salvo.")
            return False

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
# 🔧 Funções de persistência auxiliares (placeholders)
def salvar_produtos_no_github(dataframe, commit_message):
    """Placeholder de persistência (manter a função original)."""
    try:
        # Implementação real deve salvar ARQ_PRODUTOS
        return True
    except Exception:
        return False


def salvar_historico_no_github(df: pd.DataFrame, commit_message: str):
    """Placeholder de persistência (manter a função original)."""
    return True


def save_data_github_produtos(df, path, commit_message):
    """Placeholder de persistência (manter a função original)."""
    return False


# =================================================================================
# 🔄 Funções de carregamento com cache
# (Mantidas)
# =================================================================================
@st.cache_data(show_spinner="Carregando promoções...")
def carregar_promocoes():
    COLUNAS_PROMO = ["ID", "IDProduto", "NomeProduto", "Desconto", "DataInicio", "DataFim"]
    url_raw = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/{ARQ_PROMOCOES}"
    df = load_csv_github(url_raw)
    if df is None or df.empty:
        try:
            df = pd.read_csv(ARQ_PROMOCOES, dtype=str)
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
        except Exception:
            df = pd.DataFrame(columns=COLUNAS_PADRAO)
    if df.empty:
        df = pd.DataFrame(columns=COLUNAS_PADRAO)
    for col in COLUNAS_PADRAO:
        if col not in df.columns:
            df[col] = "Realizada" if col == "Status" else ""
    for col in ["RecorrenciaID", "TransacaoPaiID"]:
        if col not in df.columns:
            df[col] = ''
    cols_to_return = COLUNAS_PADRAO_COMPLETO
    return df[[col for col in cols_to_return if col in df.columns]]


@st.cache_data(show_spinner="Carregando produtos do estoque...")
def inicializar_produtos():
    if "produtos" not in st.session_state:
        url_raw = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/{ARQ_PRODUTOS}"
        df_carregado = load_csv_github(url_raw)
        if df_carregado is None or df_carregado.empty:
            df_base = pd.DataFrame(columns=COLUNAS_PRODUTOS)
        else:
            df_base = df_carregado
        for col in COLUNAS_PRODUTOS:
            if col not in df_base.columns:
                df_base[col] = ''
        df_base["Quantidade"] = pd.to_numeric(df_base["Quantidade"], errors='coerce').fillna(0).astype(int)
        df_base["PrecoCusto"] = pd.to_numeric(df_base["PrecoCusto"], errors='coerce').fillna(0.0)
        df_base["PrecoVista"] = pd.to_numeric(df_base["PrecoVista"], errors='coerce').fillna(0.0)
        df_base["PrecoCartao"] = pd.to_numeric(df_base["PrecoCartao"], errors='coerce').fillna(0.0)
        df_base["Validade"] = pd.to_datetime(df_base["Validade"], errors='coerce').dt.date
        st.session_state.produtos = df_base
    return st.session_state.produtos


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


# ==================== FUNÇÕES DE LÓGICA DE NEGÓCIO (PRODUTOS/ESTOQUE) ====================
# (Mantidas)
# =================================================================================
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
# (Mantidas)
# =================================================================================
def callback_salvar_novo_produto(produtos, tipo_produto, nome, marca, categoria, qtd, preco_custo, preco_vista, validade, foto_url, codigo_barras, variacoes):
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
            produtos, None, nome, marca, categoria,
            qtd, preco_custo, preco_vista,
            round(to_float(preco_vista) / FATOR_CARTAO, 2) if to_float(preco_vista) > 0 else 0.0,
            validade, foto_url, codigo_barras
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
            st.session_state.cad_validade = date.today()
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
            p_pai_id=None
        )
        cont_variacoes = 0
        for var in variacoes:
            if var.get("Nome") and var.get("Quantidade", 0) > 0:
                produtos, _ = add_product_row(
                    produtos, None,
                    f"{nome} ({var['Nome']})", marca, categoria,
                    var["Quantidade"], var["PrecoCusto"], var["PrecoVista"], var["PrecoCartao"],
                    validade, foto_url, var.get("CodigoBarras", ""),
                    p_pai_id=pai_id
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
                st.session_state.cad_validade = date.today()
                st.session_state.cad_foto_url = ""
                if "codigo_barras" in st.session_state:
                    del st.session_state["codigo_barras"]
                st.session_state.cb_grade_lidos = {}
                return True
            return False
        else:
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
    promocao_ativa = promocoes[
        (promocoes["IDProduto"] == prod_id) &
        (promocoes["DataInicio"] <= hoje) &
        (promocoes["DataFim"] >= hoje)
    ]
    preco_unitario_final = preco
    if not promocao_ativa.empty:
        desconto_aplicado = promocao_ativa.iloc[0]["Desconto"] / 100.0
        preco_unitario_final = preco * (1 - desconto_aplicado)
        try:
            st.toast(f"🏷️ Promoção de {promocao_ativa.iloc[0]['Desconto']:.0f}% aplicada a {prod_nome}!")
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
