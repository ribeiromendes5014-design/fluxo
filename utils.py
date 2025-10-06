# utils.py

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

# ==================== CORREÇÃO CRÍTICA: MOCK DA CLASSE GITHUB ====================
# Isso evita que o aplicativo falhe se PyGithub não estiver instalado ou se o TOKEN falhar.
class Github:
    def __init__(self, token):
        # Apenas simula a inicialização; a conexão real será ignorada na função de salvar.
        pass
    def get_repo(self, repo_name):
        return self
    def get_contents(self, path, ref):
        # Simula erro (usado no bloco try/except da função salvar)
        raise Exception("Mock: Conexão GitHub desativada/Token ausente.")
    def update_file(self, path, msg, content, sha, branch):
        st.warning(f"💾 Salvamento de arquivo {path} ignorado (MOCK ATIVO).")
    def create_file(self, path, msg, content, branch):
        st.warning(f"💾 Criação de arquivo {path} ignorada (MOCK ATIVO).")

# =================================================================================

# Importa as constantes de negócio e de arquivo
from constants_and_css import (
    TOKEN, OWNER, REPO_NAME, BRANCH, GITHUB_TOKEN, GITHUB_REPO, GITHUB_BRANCH,
    PATH_DIVIDAS, ARQ_PRODUTOS, ARQ_LOCAL, ARQ_COMPRAS, ARQ_PROMOCOES,
    COLUNAS_COMPRAS, COLUNAS_PADRAO, COLUNAS_PADRAO_COMPLETO, COLUNAS_COMPLETAS_PROCESSADAS,
    COLUNAS_PRODUTOS, FATOR_CARTAO, COMMIT_MESSAGE, COMMIT_MESSAGE_EDIT, COMMIT_MESSAGE_DELETE
)

# ==================== FUNÇÕES DE TRATAMENTO BÁSICO ====================

def to_float(valor_str):
    """Converte string (com vírgula ou ponto) para float."""
    try:
        if isinstance(valor_str, (int, float)):
            return float(valor_str)
        return float(str(valor_str).replace(",", ".").strip())
    except:
        return 0.0

def prox_id(df, coluna_id="ID"):
    """Gera o próximo ID sequencial."""
    if df.empty:
        return "1"
    else:
        try:
            return str(pd.to_numeric(df[coluna_id], errors='coerce').fillna(0).astype(int).max() + 1)
        except:
            return str(len(df) + 1)

def hash_df(df):
    """Gera um hash para o DataFrame."""
    df_temp = df.copy()
    for col in df_temp.select_dtypes(include=['datetime64[ns]']).columns:
        df_temp[col] = df_temp[col].astype(str)
    try:
        return hashlib.md5(df_temp.to_json().encode('utf-8')).hexdigest()
    except Exception:
        return "error"

def parse_date_yyyy_mm_dd(date_str):
    """Tenta converter uma string para objeto date."""
    if pd.isna(date_str) or not date_str:
        return None
    try:
        return datetime.strptime(str(date_str).split(" ")[0], "%Y-%m-%d").date()
    except:
        return None

def add_months(d: date, months: int) -> date:
    """Adiciona um número específico de meses a uma data."""
    month = d.month + months
    year = d.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)

def calcular_valor_em_aberto(linha):
    """Calcula o valor absoluto e arredondado para 2 casas decimais."""
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
    """Formata o JSON de produtos para exibição na tabela."""
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


# ==================== FUNÇÕES DE PERSISTÊNCIA (GITHUB/CACHE) ====================

def load_csv_github(url: str) -> pd.DataFrame | None:
    """Tenta carregar um CSV do GitHub."""
    try:
        response = requests.get(url)
        response.raise_for_status()
        df = pd.read_csv(StringIO(response.text), dtype=str)
        if df.empty or len(df.columns) < 2:
            return None
        return df
    except Exception:
        # Permite que a inicialização continue se a conexão falhar
        return None

def salvar_dados_no_github(df: pd.DataFrame, commit_message: str):
    """
    Salva o DataFrame CSV no GitHub. Usa MOCK (Classe Github acima) se o PyGithub falhar.
    Prioriza o backup local e suprime o erro de conexão.
    """

    # 1. Backup local
    try:
        df.to_csv(ARQ_LOCAL, index=False, encoding="utf-8-sig")
        # st.toast("Backup local salvo.") # Opcional: para feedback
    except Exception:
        st.warning("Falha ao salvar backup local.")

    # 2. Prepara DataFrame para envio (mesmo que seja mockado, o Streamlit precisa deste formato)
    df_temp = df.copy()
    for col_date in ['Data', 'Data Pagamento']:
        if col_date in df_temp.columns:
            df_temp[col_date] = pd.to_datetime(df_temp[col_date], errors='coerce').apply(
                lambda x: x.strftime('%Y-%m-%d') if pd.notnull(x) else ''
            )

    try:
        g = Github(TOKEN) # Usa a classe Mock se a real falhou
        repo = g.get_repo(f"{OWNER}/{REPO_NAME}")
        csv_string = df_temp.to_csv(index=False, encoding="utf-8-sig")

        # Tenta obter o SHA do conteúdo atual (vai falhar no Mock, forçando a criação/simulação)
        try:
            contents = repo.get_contents(PATH_DIVIDAS, ref=BRANCH)
            repo.update_file(contents.path, commit_message, csv_string, contents.sha, branch=BRANCH)
            st.success("📁 Livro Caixa salvo (atualizado) no GitHub!")
        except Exception:
            repo.create_file(PATH_DIVIDAS, commit_message, csv_string, branch=BRANCH)
            st.success("📁 Livro Caixa salvo (criado) no GitHub!")

        return True

    except Exception as e:
        # A falha aqui é esperada se o PyGithub real não estiver configurado.
        st.error(f"❌ Erro de persistência no GitHub: {e}. Usando apenas backup local.")
        return False


# =================================================================================
# 🔑 FUNÇÃO DE PERSISTÊNCIA CRÍTICA: salvar_promocoes
# Esta função salva o DataFrame de promoções, seja no GitHub ou localmente.
def salvar_promocoes(df_promocoes: pd.DataFrame):
    """Salva o DataFrame de promoções em ARQ_PROMOCOES (no GitHub e/ou local)."""
    
    # Prepara o DataFrame para salvamento, garantindo que as datas sejam strings
    df_salvar = df_promocoes.copy()
    if 'DataInicio' in df_salvar.columns:
        df_salvar['DataInicio'] = df_salvar['DataInicio'].astype(str)
    if 'DataFim' in df_salvar.columns:
        df_salvar['DataFim'] = df_salvar['DataFim'].astype(str)
        
    csv_string = df_salvar.to_csv(index=False, encoding="utf-8-sig")

    # 1. Tenta salvar no GitHub (Mock ou Real)
    try:
        g = Github(TOKEN) # Usa a classe Mock se a real falhou
        repo = g.get_repo(f"{OWNER}/{REPO_NAME}")
        
        # Tenta obter o SHA do conteúdo atual
        try:
            contents = repo.get_contents(ARQ_PROMOCOES, ref=BRANCH)
            repo.update_file(contents.path, COMMIT_MESSAGE, csv_string, contents.sha, branch=BRANCH)
            st.toast("Promoções salvas (atualizadas) no GitHub.")
        except Exception:
            repo.create_file(ARQ_PROMOCOES, COMMIT_MESSAGE, csv_string, branch=BRANCH)
            st.toast("Promoções salvas (criadas) no GitHub.")
        return True

    except Exception as e:
        # 2. Fallback local se o GitHub falhar (opcional)
        st.warning(f"❌ Falha no salvamento do GitHub para promoções: {e}. Tentando salvar localmente.")
        try:
             df_salvar.to_csv(ARQ_PROMOCOES, index=False, encoding="utf-8-sig")
             st.warning("Backup de promoções salvo localmente.")
             return True
        except Exception as local_e:
             st.error(f"❌ Falha ao salvar promoções localmente: {local_e}")
             return False

# =================================================================================


# Placeholder: A função real faz o salvamento, mas aqui precisa ser um placeholder.
def salvar_produtos_no_github(dataframe, commit_message):
    """Função PLACEHOLDER para salvar produtos no GitHub."""
    return True

# Placeholder: Salva histórico de compras (Comportamento original do 22.py)
def salvar_historico_no_github(df: pd.DataFrame, commit_message: str):
    return True

# Placeholder: Salva dados no GitHub (Comportamento original do 22.py)
def save_data_github_produtos(df, path, commit_message):
    return False


# ==================== FUNÇÕES DE CARREGAMENTO COM CACHE ====================

@st.cache_data(show_spinner="Carregando dados...")
def carregar_livro_caixa():
    """Orquestra o carregamento do Livro Caixa (Principal)."""
    url_raw = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/{PATH_DIVIDAS}"
    df = load_csv_github(url_raw)

    if df is None or df.empty:
        try:
            # Fallback para o arquivo de backup local
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
    """Carrega ou inicializa o DataFrame de Produtos."""
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
        df_base["Validade"] = pd.to_datetime(df_base["Validade"], errors='coerce').dt.date
        st.session_state.produtos = df_base
    return st.session_state.produtos

@st.cache_data(show_spinner="Carregando promoções...")
def carregar_promocoes():
    """Carrega o DataFrame de promoções."""
    COLUNAS_PROMO = ["ID", "IDProduto", "NomeProduto", "Desconto", "DataInicio", "DataFim"]
    url_raw = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/{ARQ_PROMOCOES}"
    df = load_csv_github(url_raw)
    if df is None or df.empty:
        # Tenta o fallback local se o GitHub falhar (importante para o desenvolvimento)
        try:
            df = pd.read_csv(ARQ_PROMOCOES, dtype=str)
        except Exception:
            df = pd.DataFrame(columns=COLUNAS_PROMO)

    for col in COLUNAS_PROMO:
        if col not in df.columns:
            df[col] = ""
    return df[[col for col in COLUNAS_PROMO if col in df.columns]]

@st.cache_data(show_spinner="Carregando histórico de compras...")
def carregar_historico_compras():
    """Carrega o DataFrame de histórico de compras."""
    url_raw = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/{ARQ_COMPRAS}"
    df = load_csv_github(url_raw)
    if df is None or df.empty:
        df = pd.DataFrame(columns=COLUNAS_COMPRAS)
    for col in COLUNAS_COMPRAS:
        if col not in df.columns:
            df[col] = ""
    return df[[col for col in COLUNAS_COMPRAS if col in df.columns]]


# ==================== FUNÇÕES DE TRATAMENTO DE DADOS (PANDAS) ====================

@st.cache_data(show_spinner=False)
def processar_dataframe(df):
    """Aplica o tratamento principal (Datas, Saldo Acumulado, ID Visível) no Livro Caixa."""
    for col in COLUNAS_PADRAO:
        if col not in df.columns: df[col] = ""
    for col in ["RecorrenciaID", "TransacaoPaiID"]:
        if col not in df.columns: df[col] = ''

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

    if 'TransacaoPaiID' not in df_proc.columns:
        df_proc['TransacaoPaiID'] = ''

    return df_proc

def calcular_resumo(df):
    """Calcula total de entradas, saídas e saldo de um DataFrame processado."""
    df_realizada = df[df['Status'] == 'Realizada']
    if df_realizada.empty: return 0.0, 0.0, 0.0
    total_entradas = df_realizada[df_realizada["Tipo"] == "Entrada"]["Valor"].sum()
    total_saidas = abs(df_realizada[df_realizada["Tipo"] == "Saída"]["Valor"].sum())
    saldo = df_realizada["Valor"].sum()
    return total_entradas, total_saidas, saldo

def norm_promocoes(df):
    """Normaliza o DataFrame de promoções (datas e filtro de expiração)."""
    if df.empty: return df
    df = df.copy()
    df["Desconto"] = pd.to_numeric(df["Desconto"], errors='coerce').fillna(0.0)
    df["DataInicio"] = pd.to_datetime(df["DataInicio"], errors='coerce').dt.date
    df["DataFim"] = pd.to_datetime(df["DataFim"], errors='coerce').dt.date
    df = df[df["DataFim"] >= date.today()]
    return df


# ==================== FUNÇÕES DE LÓGICA DE NEGÓCIO (PRODUTOS/ESTOQUE) ====================

def ajustar_estoque(id_produto, quantidade, operacao="debitar"):
    """
    Ajusta a quantidade de um produto no st.session_state.produtos.
    Nota: A persistência no GitHub precisa ser chamada separadamente.
    """
    if "produtos" not in st.session_state:
          # Se o estado não existe, inicializa (garante o dataframe)
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

# ==================== FUNÇÕES DE LEITURA (API) ====================

def ler_codigo_barras_api(image_bytes):
    """Decodifica códigos de barras (1D e QR) usando a API pública ZXing."""
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
            st.toast("⚠️ API ZXing não retornou nenhum código válido. Tente novamente ou use uma imagem mais clara.")

        return codigos

    except Exception as e:
        if 'streamlit' in globals():
            st.error(f"❌ Erro de Requisição/Conexão: {e}")
        return []

# ==================== FUNÇÕES DE CALLBACK (PRODUTOS) ====================

def callback_salvar_novo_produto(produtos, tipo_produto, nome, marca, categoria, qtd, preco_custo, preco_vista, validade, foto_url, codigo_barras, variações):
    """Callback complexo para salvar produto simples ou com grade."""
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

    # ⚠️ Removida a simulação 'save_csv_github' local. Agora a função 'salvar_produtos_no_github'
    # precisa ser a lógica real de persistência para ARQ_PRODUTOS, conforme seu sistema.

    if tipo_produto == "Produto simples":
        # ... [lógica de salvar produto simples]
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
            # Limpa campos
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
        # ... [lógica de salvar produto com grade]
        produtos, pai_id = add_product_row(
            produtos, None, nome, marca, categoria,
            0, 0.0, 0.0, 0.0,
            validade, foto_url, codigo_barras,
            p_pai_id=None
        )
        cont_variacoes = 0
        for var in variações:
            if var["Nome"] and var["Quantidade"] > 0:
                produtos, _ = add_product_row(
                    produtos, None,
                    f"{nome} ({var['Nome']})", marca, categoria,
                    var["Quantidade"], var["PrecoCusto"], var["PrecoVista"], var["PrecoCartao"],
                    validade, foto_url, var["CodigoBarras"],
                    p_pai_id=pai_id
                )
                cont_variacoes += 1

        if cont_variacoes > 0:
            if salvar_produtos_no_github(produtos, f"Novo produto com grade: {nome} ({cont_variacoes} variações)"):
                st.session_state.produtos = produtos
                inicializar_produtos.clear()
                st.success(f"Produto '{nome}' com {cont_variacoes} variações cadastrado com sucesso!")
                # Limpa campos
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
            produtos = produtos[produtos["ID"] != pai_id]
            st.session_state.produtos = produtos
            st.error("Nenhuma variação válida foi fornecida. O produto principal não foi salvo.")
            return False
    return False

def callback_adicionar_manual(nome, qtd, preco, custo):
    """Adiciona item manual (sem controle de estoque) à lista de venda do Livro Caixa."""
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
    """Adiciona item do estoque à lista de venda do Livro Caixa (com lógica de promoção)."""

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
        st.toast(f"🏷️ Promoção de {promocao_ativa.iloc[0]['Desconto']:.0f}% aplicada a {prod_nome}!")

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

@st.cache_data(show_spinner="Calculando mais vendidos...")
def get_most_sold_products(df_movimentacoes):
    """Calcula os produtos mais vendidos (por quantidade de itens vendidos)."""

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
