# utils.py
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
import requests
from requests.exceptions import RequestException
from io import StringIO
import json
import hashlib
import ast
import calendar
import uuid # ✨ ADICIONADO para IDs únicos

# =================================================================================
# Importa as constantes de negócio e de arquivo
from constants_and_css import (
    TOKEN, OWNER, REPO_NAME, BRANCH, GITHUB_TOKEN, GITHUB_REPO, GITHUB_BRANCH,
    PATH_DIVIDAS, ARQ_PRODUTOS, ARQ_LOCAL, ARQ_COMPRAS, ARQ_PROMOCOES,
    COLUNAS_COMPRAS, COLUNAS_PADRAO, COLUNAS_PADRAO_COMPLETO,
    COLUNAS_PRODUTOS, FATOR_CARTAO, COMMIT_MESSAGE, COMMIT_MESSAGE_EDIT, COMMIT_MESSAGE_DELETE
)
# =================================================================================


# ==================== FUNÇÕES DE TRATAMENTO BÁSICO ====================

def to_float(valor_str):
    """Converte uma string para float, tratando vírgula como decimal."""
    try:
        if isinstance(valor_str, (int, float)):
            return float(valor_str)
        return float(str(valor_str).replace(",", ".").strip())
    except (ValueError, TypeError):
        return 0.0

def parse_date_yyyy_mm_dd(date_str):
    """Converte uma string de data no formato YYYY-MM-DD para um objeto date."""
    if pd.isna(date_str) or not date_str:
        return None
    try:
        return datetime.strptime(str(date_str).split(" ")[0], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None

# =================================================================================
# Utilitários de carregamento e salvamento no GitHub
# =================================================================================

def load_csv_github(url: str) -> pd.DataFrame | None:
    """Carrega um CSV de uma URL raw do GitHub."""
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        # Usa utf-8-sig para lidar com BOM (Byte Order Mark) que pode ser salvo pelo Excel
        return pd.read_csv(StringIO(response.text), dtype=str, encoding='utf-8-sig')
    except RequestException as e:
        # st.warning(f"Erro de conexão ao carregar dados do GitHub: {e}")
        return None
    except Exception as e:
        # st.error(f"Ocorreu um erro inesperado ao ler CSV do GitHub: {e}")
        return None

def salvar_dados_no_github(df: pd.DataFrame, file_path: str, commit_message: str):
    """Função genérica para salvar QUALQUER dataframe no GitHub."""
    token = st.secrets.get("GITHUB_TOKEN", GITHUB_TOKEN)
    repo_owner = st.secrets.get("REPO_OWNER", OWNER)
    repo_name = st.secrets.get("REPO_NAME", REPO_NAME)
    branch = st.secrets.get("BRANCH", BRANCH)

    if not all([token, repo_owner, repo_name, branch, file_path]):
        st.error("Configurações do GitHub incompletas. Verifique as constantes e secrets.")
        return False

    try:
        from github import Github
        g = Github(token)
        repo = g.get_repo(f"{repo_owner}/{repo_name}")
        csv_content = df.to_csv(index=False, encoding="utf-8-sig")

        try:
            contents = repo.get_contents(file_path, ref=branch)
            repo.update_file(contents.path, commit_message, csv_content, contents.sha, branch=branch)
        except Exception: # Se o arquivo não existe, cria
            repo.create_file(file_path, commit_message, csv_content, branch=branch)
        return True
    except Exception as e:
        st.error(f"Falha ao enviar dados para o GitHub: {e}")
        return False

# =================================================================================
# Funções de persistência específicas (usando a função genérica)
# =================================================================================

def salvar_promocoes_no_github(df: pd.DataFrame, commit_message: str = "Atualiza promoções"):
    return salvar_dados_no_github(df, ARQ_PROMOCOES, commit_message)

def salvar_produtos_no_github(dataframe: pd.DataFrame, commit_message: str):
    """Salva o dataframe de produtos no GitHub."""
    return salvar_dados_no_github(dataframe, ARQ_PRODUTOS, commit_message)

def save_data_github_produtos(df, path, commit_message):
    """Alias para compatibilidade."""
    return salvar_produtos_no_github(df, commit_message)

# =================================================================================
# Funções de carregamento com cache
# =================================================================================

@st.cache_data(show_spinner="Carregando produtos do estoque...")
def inicializar_produtos():
    """Carrega e prepara o DataFrame de produtos."""
    df_base = None
    url_raw = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/{ARQ_PRODUTOS}"
    df_base = load_csv_github(url_raw)

    if df_base is None or df_base.empty:
        # st.warning("⚠️ Falha ao carregar produtos do GitHub. Tentando carregar arquivo local...")
        try:
            df_base = pd.read_csv(ARQ_PRODUTOS, dtype=str, encoding='utf-8-sig')
        except FileNotFoundError:
            st.error(f"❌ Arquivo local '{ARQ_PRODUTOS}' não encontrado. Criando uma base de dados vazia.")
            df_base = pd.DataFrame(columns=COLUNAS_PRODUTOS)
        except Exception as e:
            st.error(f"❌ Falha ao carregar o arquivo local: {e}")
            return pd.DataFrame(columns=COLUNAS_PRODUTOS)

    # Garante que todas as colunas esperadas existam
    for col in COLUNAS_PRODUTOS:
        if col not in df_base.columns:
            df_base[col] = ''

    # Conversões de tipo, garantindo que as colunas existam
    df_base["Quantidade"] = pd.to_numeric(df_base.get("Quantidade"), errors='coerce').fillna(0).astype(int)
    df_base["PrecoCusto"] = pd.to_numeric(df_base.get("PrecoCusto"), errors='coerce').fillna(0.0)
    df_base["PrecoVista"] = pd.to_numeric(df_base.get("PrecoVista"), errors='coerce').fillna(0.0)
    df_base["PrecoCartao"] = pd.to_numeric(df_base.get("PrecoCartao"), errors='coerce').fillna(0.0)
    df_base["CashbackPercent"] = pd.to_numeric(df_base.get("CashbackPercent"), errors='coerce').fillna(0.0)
    df_base["Validade"] = pd.to_datetime(df_base.get("Validade"), errors='coerce').dt.date

    # Garante a ordem e a presença das colunas
    df_final = df_base.reindex(columns=COLUNAS_PRODUTOS, fill_value='')
    
    st.session_state.produtos = df_final
    return df_final.copy()


@st.cache_data(show_spinner="Carregando dados financeiros...")
def carregar_livro_caixa():
    """Carrega e prepara o DataFrame do livro caixa."""
    url_raw = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/{PATH_DIVIDAS}"
    df = load_csv_github(url_raw)

    if df is None or df.empty:
        try:
            df = pd.read_csv(ARQ_LOCAL, dtype=str)
        except Exception:
            return pd.DataFrame(columns=COLUNAS_PADRAO_COMPLETO)
            
    # Assegura que as colunas essenciais existam
    for col in COLUNAS_PADRAO_COMPLETO:
        if col not in df.columns:
            df[col] = "Realizada" if col == "Status" else ""

    df["Valor"] = pd.to_numeric(df.get("Valor"), errors='coerce').fillna(0.0)
    df["Data"] = pd.to_datetime(df.get("Data"), errors='coerce').dt.date
    df["Data Pagamento"] = pd.to_datetime(df.get("Data Pagamento"), errors='coerce').dt.date

    return df.reindex(columns=COLUNAS_PADRAO_COMPLETO, fill_value='')


def ler_codigo_barras_api(image_bytes):
    """Decodifica código de barras de uma imagem usando a API online ZXing."""
    URL_DECODER_ZXING = "https://zxing.org/w/decode"
    try:
        files = {"f": ("barcode.png", image_bytes, "image/png")}
        response = requests.post(URL_DECODER_ZXING, files=files, timeout=30)
        if response.status_code != 200:
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
        if not codigos:
            st.toast("⚠️ API ZXing não retornou código. Tente uma imagem mais clara.")
        return codigos
    except RequestException as e:
        st.error(f"❌ Erro de Conexão com a API de código de barras: {e}")
        return []
    except Exception as e:
        st.error(f"❌ Ocorreu um erro ao ler código de barras: {e}")
        return []

# =============================================================================
# ✨ FUNÇÃO DE CALLBACK PARA SALVAR PRODUTOS - VERSÃO CORRIGIDA E MELHORADA ✨
# =============================================================================
def callback_salvar_novo_produto(
    produtos_df, tipo_produto, nome, marca, categoria,
    qtd, preco_custo, preco_vista, validade, foto_url,
    codigo_barras, variacoes, cashback_percent
):
    """
    Callback para validar e salvar um novo produto ou um produto com grade.
    Função atualizada para aceitar 'cashback_percent' e usar UUIDs.
    """
    if not nome or not marca or not categoria:
        st.error("Preencha os campos obrigatórios: Nome, Marca e Categoria.")
        return False

    if tipo_produto == "Produto simples":
        novo_produto = {
            "ID": str(uuid.uuid4()),
            "PaiID": "",
            "Nome": nome.strip(),
            "Marca": marca.strip(),
            "Categoria": categoria.strip(),
            "Quantidade": int(qtd),
            "PrecoCusto": to_float(preco_custo),
            "PrecoVista": to_float(preco_vista),
            "PrecoCartao": round(to_float(preco_vista) / FATOR_CARTAO, 2) if to_float(preco_vista) > 0 else 0.0,
            "Validade": validade.strftime('%Y-%m-%d') if isinstance(validade, date) else validade,
            "FotoURL": foto_url.strip(),
            "CodigoBarras": codigo_barras.strip(),
            "CashbackPercent": float(cashback_percent)
        }
        produtos_df = pd.concat([produtos_df, pd.DataFrame([novo_produto])], ignore_index=True)

    else:  # Produto com variações (grade)
        pai_id = str(uuid.uuid4())
        produto_pai = {
            "ID": pai_id, "PaiID": "", "Nome": nome.strip(), "Marca": marca.strip(), "Categoria": categoria.strip(),
            "Quantidade": 0, "PrecoCusto": 0.0, "PrecoVista": 0.0, "PrecoCartao": 0.0,
            "Validade": validade.strftime('%Y-%m-%d') if isinstance(validade, date) else validade,
            "FotoURL": foto_url.strip(), "CodigoBarras": codigo_barras.strip(), "CashbackPercent": 0.0
        }
        novos_produtos_list = [produto_pai]

        for var in variacoes:
            if not var.get("Nome"):
                st.error("O nome de cada variação é obrigatório.")
                return False
            
            nova_variacao = {
                "ID": str(uuid.uuid4()), "PaiID": pai_id, "Nome": var["Nome"], "Marca": marca.strip(),
                "Categoria": categoria.strip(), "Quantidade": var["Quantidade"], "PrecoCusto": var["PrecoCusto"],
                "PrecoVista": var["PrecoVista"], "PrecoCartao": var["PrecoCartao"],
                "Validade": validade.strftime('%Y-%m-%d') if isinstance(validade, date) else validade,
                "FotoURL": foto_url.strip(), "CodigoBarras": var["CodigoBarras"],
                "CashbackPercent": var["CashbackPercent"]
            }
            novos_produtos_list.append(nova_variacao)
        
        produtos_df = pd.concat([produtos_df, pd.DataFrame(novos_produtos_list)], ignore_index=True)

    # Persiste os dados e limpa o cache
    if salvar_produtos_no_github(produtos_df, f"Adicionado novo produto: {nome}"):
        st.success(f"Produto '{nome}' salvo com sucesso!")
        inicializar_produtos.clear() # Força o recarregamento dos dados
        
        # Limpa os campos do formulário para evitar re-submissão acidental
        campos_form = ["cad_nome", "cad_marca", "cad_categoria", "cad_qtd", "cad_preco_custo", 
                       "cad_preco_vista", "cad_foto_url", "codigo_barras", "cad_cb"]
        for campo in campos_form:
            if campo in st.session_state:
                if isinstance(st.session_state[campo], (int, float)):
                    st.session_state[campo] = 0
                else:
                    st.session_state[campo] = ""
        if 'cad_validade' in st.session_state:
            st.session_state.cad_validade = date.today()

        return True
    else:
        st.error("Falha ao salvar os dados no GitHub.")
        return False
        
def callback_adicionar_estoque(prod_id, prod_nome, qtd, preco, custo, estoque_disp):
    """Adiciona um produto do estoque à lista de vendas, aplicando promoções."""
    promocoes = carregar_promocoes() # Carrega todas as promoções
    hoje = date.today()
    
    # Normaliza os nomes das colunas para busca
    promocoes.columns = [str(c).lower().replace(' ', '').replace('_', '') for c in promocoes.columns]
    
    promocao_ativa = promocoes[
        (promocoes["idproduto"] == prod_id)
    ]
    
    preco_unitario_final = preco
    if not promocao_ativa.empty:
        promo = promocao_ativa.iloc[0]
        data_inicio = parse_date_yyyy_mm_dd(promo.get("datainicio"))
        data_fim = parse_date_yyyy_mm_dd(promo.get("datafim"))
        
        if promo.get("status", "").upper() == 'ATIVO' and data_inicio and data_fim and data_inicio <= hoje <= data_fim:
            preco_unitario_final = to_float(promo.get("precopromocional", preco))
            
            try:
                preco_original_calc = to_float(promo.get("precooriginal", 0))
                if preco_original_calc > 0:
                    desconto_aplicado = (1 - (preco_unitario_final / preco_original_calc)) * 100
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

@st.cache_data(show_spinner="Calculando mais vendidos...")
def get_most_sold_products(df_movimentacoes):
    """Obtém os produtos mais vendidos a partir do livro caixa."""
    df_vendas = df_movimentacoes[
        (df_movimentacoes["Tipo"] == "Entrada") & 
        (df_movimentacoes["Status"] == "Realizada") & 
        (df_movimentacoes["Produtos Vendidos"].notna()) & 
        (df_movimentacoes["Produtos Vendidos"] != "")
    ].copy()

    if df_vendas.empty:
        return pd.DataFrame(columns=["Produto_ID", "Produto", "Quantidade Total Vendida"])

    vendas_list = []
    for produtos_json in df_vendas["Produtos Vendidos"]:
        try:
            produtos = ast.literal_eval(produtos_json)
            if isinstance(produtos, list):
                for item in produtos:
                    produto_id = str(item.get("Produto_ID"))
                    if produto_id and produto_id != "None":
                        vendas_list.append({
                            "Produto_ID": produto_id,
                            "Produto": item.get("Produto", "Desconhecido"),
                            "Quantidade": to_float(item.get("Quantidade", 0))
                        })
        except Exception:
            continue

    if not vendas_list:
        return pd.DataFrame(columns=["Produto_ID", "Produto", "Quantidade Total Vendida"])

    df_vendas_detalhada = pd.DataFrame(vendas_list)
    df_mais_vendidos = df_vendas_detalhada.groupby(["Produto_ID", "Produto"])["Quantidade"].sum().reset_index()
    df_mais_vendidos.rename(columns={"Quantidade": "Quantidade Total Vendida"}, inplace=True)
    df_mais_vendidos.sort_values(by="Quantidade Total Vendida", ascending=False, inplace=True)
    
    return df_mais_vendidos
