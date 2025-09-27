import streamlit as st
import pandas as pd
import requests
from fpdf import FPDF
from io import BytesIO, StringIO
import base64
import hashlib
import ast
import datetime 
from datetime import date # Import necessário para a função de Produtos

# ===============================
# CONFIGURAÇÕES E CONSTANTES GLOBAIS
# ===============================

# Configurações Telegram
HARDCODED_TELEGRAM_TOKEN = "8412132908:AAG8N_vFzkpVNX-WN3bwT0Vl3H41Q-9Rfw4"
TELEGRAM_CHAT_ID = "-1003030758192"
TOPICO_ID = 28 # ID do tópico (thread) no grupo Telegram

# Configurações de Repositório
GITHUB_TOKEN = st.secrets.get("github_token", "TOKEN_FICTICIO")
GITHUB_REPO = "ribeiromendes5014-design/Precificar"
GITHUB_BRANCH = "main"
URL_BASE_REPOS = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/" 

# Caminhos dos arquivos
PATH_PRECFICACAO = "precificacao.csv"
ARQ_CAIXAS = URL_BASE_REPOS + PATH_PRECFICACAO
PATH_DIVIDAS = "contas_a_pagar_receber.csv"
ARQ_DIVIDAS = URL_BASE_REPOS + PATH_DIVIDAS
ARQ_PRODUTOS = "produtos_estoque.csv"
URL_PRODUTOS = URL_BASE_REPOS + ARQ_PRODUTOS

# Constantes para Produto
FATOR_CARTAO = 0.8872 # Taxa de cartão de 11.28% (para chegar a 0.8872 do preço de venda)


# ===============================
# FUNÇÕES AUXILIARES GLOBAIS
# ===============================

def to_float(valor_str):
    """Converte string com vírgula para float, ou retorna 0.0."""
    try:
        if isinstance(valor_str, (int, float)):
            return float(valor_str)
        return float(str(valor_str).replace(",", ".").strip())
    except:
        return 0.0

def ler_codigo_barras_api(imagem_bytes):
    """Função mock para ler código de barras de uma imagem."""
    # Como não temos uma API real de leitura de código de barras,
    # esta função é mockada para retornar um exemplo de código.
    # Em uma aplicação real, você faria uma chamada para um serviço como Google Vision API ou similar.
    # st.info("Simulando leitura de código de barras...")
    return ["1234567890123"] # Exemplo de código lido

def prox_id(df, coluna_id="ID"):
    """Função auxiliar para criar um novo ID sequencial (usada na Gestão de Produtos)"""
    if df.empty:
        return "1"
    else:
        try:
            # O pd.to_numeric e .max() garantem a maior segurança para IDs mistos
            return str(pd.to_numeric(df[coluna_id], errors='coerce').fillna(0).astype(int).max() + 1)
        except:
            return str(len(df) + 1)

# Função de persistência para o novo fluxo
def save_csv_github(dataframe, path, mensagem="Atualização via app"):
    """Salva o DataFrame como CSV no GitHub via API, usando a função global."""
    # Garante que as colunas de data sejam strings
    df_temp = dataframe.copy()
    for col in df_temp.select_dtypes(include=['datetime64[ns]']).columns:
         df_temp[col] = df_temp[col].dt.strftime('%Y-%m-%d').fillna('')
    
    salvar_csv_no_github(GITHUB_TOKEN, GITHUB_REPO, path, df_temp, GITHUB_BRANCH, mensagem)


def gerar_pdf(df: pd.DataFrame) -> BytesIO:
    """Gera um PDF formatado a partir do DataFrame de precificação, incluindo a URL da imagem."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Relatório de Precificação", 0, 1, "C")
    pdf.ln(5)

    # Configurações de fonte para tabela
    pdf.set_font("Arial", "B", 10) 

    col_widths = {
        "Produto": 40,
        "Qtd": 15,
        "Custo Unitário": 25,
        "Margem (%)": 20,
        "Preço à Vista": 25,
        "Preço no Cartão": 25,
        "URL da Imagem": 40 
    }
    
    pdf_cols = [col for col in col_widths.keys() if col in df.columns or col == "Custo Unitário"]
    current_widths = [col_widths[col] for col in pdf_cols]

    # Cabeçalho da tabela
    for col_name, width in zip(pdf_cols, current_widths):
        pdf.cell(width, 10, col_name, border=1, align='C')
    pdf.ln()

    # Fonte para corpo da tabela
    pdf.set_font("Arial", "", 8) 

    if df.empty:
        pdf.cell(sum(current_widths), 10, "Nenhum produto cadastrado.", border=1, align="C")
        pdf.ln()
    else:
        for idx, row in df.iterrows():
            if "Produto" in pdf_cols:
                pdf.cell(col_widths["Produto"], 10, str(row.get("Produto", "")), border=1)
            if "Qtd" in pdf_cols:
                pdf.cell(col_widths["Qtd"], 10, str(row.get("Qtd", 0)), border=1, align="C")
            if "Custo Unitário" in pdf_cols:
                custo_unit_val = row.get("Custo Total Unitário", row.get("Custo Unitário", 0.0))
                pdf.cell(col_widths["Custo Unitário"], 10, f"R$ {custo_unit_val:.2f}", border=1, align="R")
            if "Margem (%)" in pdf_cols:
                pdf.cell(col_widths["Margem (%)"], 10, f"{row.get('Margem (%)', 0.0):.2f}%", border=1, align="R")
            if "Preço à Vista" in pdf_cols:
                pdf.cell(col_widths["Preço à Vista"], 10, f"R$ {row.get('Preço à Vista', 0.0):.2f}", border=1, align="R")
            if "Preço no Cartão" in pdf_cols:
                pdf.cell(col_widths["Preço no Cartão"], 10, f"R$ {row.get('Preço no Cartão', 0.0):.2f}", border=1, align="R")
            
            if "URL da Imagem" in pdf_cols:
                url_display = str(row.get("Imagem_URL", ""))
                if len(url_display) > 35:
                    url_display = url_display[:32] + "..."
                pdf.cell(col_widths["URL da Imagem"], 10, url_display, border=1, align="L", link=str(row.get("Imagem_URL", "")))
                
            pdf.ln()

    pdf_bytes = pdf.output(dest='S').encode('latin1')
    return BytesIO(pdf_bytes)


def enviar_pdf_telegram(pdf_bytesio, df_produtos: pd.DataFrame, thread_id=None):
    """Envia o arquivo PDF e a primeira imagem (se existir) em mensagens separadas para o Telegram."""
    
    token = st.secrets.get("telegram_token", HARDCODED_TELEGRAM_TOKEN)
    
    image_url = None
    image_caption = "Relatório de Precificação"
    # ... (restante da função enviar_pdf_telegram, mantida sem alterações) ...
    
    if not df_produtos.empty and "Imagem_URL" in df_produtos.columns:
        first_row = df_produtos.iloc[0]
        url = first_row.get("Imagem_URL")
        produto = first_row.get("Produto", "Produto")
        
        if isinstance(url, str) and url.startswith("http"):
            image_url = url
            image_caption = f"📦 Produto Principal: {produto}\n\n[Relatório de Precificação em anexo]"

    # 1. Envia o PDF (mensagem principal)
    
    url_doc = f"https://api.telegram.org/bot{token}/sendDocument"
    files_doc = {'document': ('precificacao.pdf', pdf_bytesio, 'application/pdf')}
    data_doc = {"chat_id": TELEGRAM_CHAT_ID, "caption": image_caption if not image_url else "[Relatório de Precificação em anexo]"}
    if thread_id is not None:
        data_doc["message_thread_id"] = thread_id
    
    resp_doc = requests.post(url_doc, data=data_doc, files=files_doc)
    resp_doc_json = resp_doc.json()
    
    if not resp_doc_json.get("ok"):
         st.error(f"❌ Erro ao enviar PDF: {resp_doc_json.get('description')}")
         return

    st.success("✅ PDF enviado para o Telegram.")
    
    # 2. Envia a foto (se existir) em uma mensagem separada
    if image_url:
        try:
            url_photo = f"https://api.telegram.org/bot{token}/sendPhoto"
            
            # Faz o Telegram buscar a foto diretamente da URL
            data_photo = {
                "chat_id": TELEGRAM_CHAT_ID, 
                "photo": image_url,
                "caption": f"🖼️ Foto do Produto Principal: {produto}"
            }
            if thread_id is not None:
                data_photo["message_thread_id"] = thread_id

            resp_photo = requests.post(url_photo, data=data_photo)
            resp_photo_json = resp_photo.json()

            if resp_photo_json.get("ok"):
                st.success("✅ Foto do produto principal enviada com sucesso!")
            else:
                 st.warning(f"❌ Erro ao enviar a foto do produto: {resp_photo_json.get('description')}")
                 
        except Exception as e:
            st.warning(f"⚠️ Erro ao tentar enviar a imagem. Erro: {e}")
            

def exibir_resultados(df: pd.DataFrame, imagens_dict: dict):
    """Exibe os resultados de precificação com tabela e imagens dos produtos."""
    if df is None or df.empty:
        st.info("⚠️ Nenhum produto disponível para exibir.")
        return

    st.subheader("📊 Resultados Detalhados da Precificação")

    for idx, row in df.iterrows():
        with st.container():
            cols = st.columns([1, 3])
            with cols[0]:
                img_to_display = None
                
                # 1. Tenta carregar imagem do dicionário (upload manual)
                img_to_display = imagens_dict.get(row.get("Produto"))

                # 2. Tenta carregar imagem dos bytes (se persistido)
                if img_to_display is None and row.get("Imagem") is not None and isinstance(row.get("Imagem"), bytes):
                    try:
                        img_to_display = row.get("Imagem")
                    except Exception:
                        pass # Continua tentando a URL

                # 3. Tenta carregar imagem da URL (se persistido)
                img_url = row.get("Imagem_URL")
                if img_to_display is None and img_url and isinstance(img_url, str) and img_url.startswith("http"):
                    st.image(img_url, width=100, caption="URL")
                elif img_to_display:
                    st.image(img_to_display, width=100, caption="Arquivo")
                else:
                    st.write("🖼️ N/A")
                    
            with cols[1]:
                st.markdown(f"**{row.get('Produto', '—')}**")
                st.write(f"📦 Quantidade: {row.get('Qtd', '—')}")
                
                custo_base = row.get('Custo Unitário', 0.0)
                custo_total_unitario = row.get('Custo Total Unitário', custo_base)

                st.write(f"💰 Custo Base: R$ {custo_base:.2f}")

                custos_extras_prod = row.get('Custos Extras Produto', 0.0)
                st.write(f"🛠 Rateio/Extras: R$ {custos_extras_prod:.2f}")

                if 'Custo Total Unitário' in df.columns:
                    st.write(f"💸 Custo Total/Un: **R$ {custo_total_unitario:.2f}**")

                if "Margem (%)" in df.columns:
                    margem_val = row.get("Margem (%)", 0)
                    try:
                        margem_float = float(margem_val)
                    except Exception:
                        margem_float = 0
                    st.write(f"📈 Margem: **{margem_float:.2f}%**")
                
                if "Preço à Vista" in df.columns:
                    st.write(f"💰 Preço à Vista: **R$ {row.get('Preço à Vista', 0):.2f}**")
                if "Preço no Cartão" in df.columns:
                    st.write(f"💳 Preço no Cartão: **R$ {row.get('Preço no Cartão', 0):.2f}**")


def processar_dataframe(df: pd.DataFrame, frete_total: float, custos_extras: float,
                        modo_margem: str, margem_fixa: float) -> pd.DataFrame:
    """Processa o DataFrame, aplica rateio, margem e calcula os preços finais."""
    if df.empty:
        # Garante que o DataFrame tem as colunas mínimas esperadas para evitar erros de índice/coluna
        return pd.DataFrame(columns=[
            "Produto", "Qtd", "Custo Unitário", "Custos Extras Produto", 
            "Custo Total Unitário", "Margem (%)", "Preço à Vista", "Preço no Cartão"
        ])

    df = df.copy()

    # Garante que as colunas de custo e quantidade são numéricas
    for col in ["Qtd", "Custo Unitário", "Margem (%)", "Custos Extras Produto"]:
        if col in df.columns:
            # Tenta converter, falhando para 0.0 se não for possível
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
        elif col not in df.columns:
            # Adiciona colunas ausentes com valor 0.0 se for necessário para o cálculo
            df[col] = 0.0
            
    # --- Cálculo do Rateio Global ---
    qtd_total = df["Qtd"].sum()
    rateio_unitario = 0
    if qtd_total > 0:
        rateio_unitario = (frete_total + custos_extras) / qtd_total

    # Se houver rateio global, garante que o custo extra total inclua este rateio
    if frete_total > 0 or custos_extras > 0:
        pass
    else:
        pass


    # Calcular o custo total por unidade
    df["Custo Total Unitário"] = df["Custo Unitário"] + df["Custos Extras Produto"]

    # Processar margens conforme o modo selecionado
    if "Margem (%)" not in df.columns:
        df["Margem (%)"] = margem_fixa
    
    df["Margem (%)"] = df["Margem (%)"].apply(lambda x: x if pd.notna(x) else margem_fixa)


    # Calcular os preços finais
    df["Preço à Vista"] = df["Custo Total Unitário"] * (1 + df["Margem (%)"] / 100)
    # Taxa de cartão de 11.28% (para chegar a 0.8872 do preço de venda)
    df["Preço no Cartão"] = df["Preço à Vista"] / 0.8872

    # Seleciona as colunas relevantes para o DataFrame final de exibição
    cols_to_keep = [
        "Produto", "Qtd", "Custo Unitário", "Custos Extras Produto", 
        "Custo Total Unitário", "Margem (%)", "Preço à Vista", "Preço no Cartão", 
        "Imagem", "Imagem_URL" # Adicionada Imagem_URL para persistência no CSV
    ]
    
    # Mantém apenas as colunas que existem no DF
    df_final = df[[col for col in cols_to_keep if col in df.columns]]

    return df_final


def load_csv_github(url: str) -> pd.DataFrame:
    """Carrega um arquivo CSV diretamente do GitHub."""
    try:
        response = requests.get(url)
        response.raise_for_status()
        df = pd.read_csv(StringIO(response.text))
        return df
    except Exception as e:
        # st.error(f"Erro ao carregar CSV do GitHub de {url}: {e}") # Comentado para evitar erro em primeira carga
        return pd.DataFrame()


def extrair_produtos_pdf(pdf_file) -> list:
    """Função mock para extração de produtos de PDF."""
    st.warning("Função extrair_produtos_pdf ainda não implementada. Use o carregamento manual ou de CSV.")
    return []


# Funções auxiliares gerais
def baixar_csv_aba(df, nome_arquivo, key_suffix=""):
    """Cria um botão de download para o DataFrame."""
    # Garante que os dados de data estejam em formato ISO string para o CSV
    df_temp = df.copy()
    for col in df_temp.select_dtypes(include=['datetime64[ns]']).columns:
         df_temp[col] = df_temp[col].dt.strftime('%Y-%m-%d').fillna('')

    csv = df_temp.to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        f"⬇️ Baixar {nome_arquivo}",
        data=csv,
        file_name=nome_arquivo,
        mime="text/csv",
        key=f"download_button_{nome_arquivo.replace('.', '_')}_{key_suffix}"
    )

def _opcoes_para_lista(opcoes_str):
    """Converte string de opções separadas por vírgula em lista."""
    if pd.isna(opcoes_str) or not str(opcoes_str).strip():
        return []
    return [o.strip() for o in str(opcoes_str).split(",") if o.strip()]

def hash_df(df):
    """
    Gera um hash para o DataFrame para detecção de mudanças.
    Usa um método mais robusto que evita problemas com dtypes específicos do pandas.
    """
    df_temp = df.copy()
    
    # Converte colunas de data/hora para string para hash consistente
    for col in df_temp.select_dtypes(include=['datetime64[ns]']).columns:
        df_temp[col] = df_temp[col].astype(str)
    
    try:
        return hashlib.md5(pd.util.hash_pandas_object(df_temp, index=False).values).hexdigest()
    except Exception as e:
        # Se houver erro, tenta converter colunas object para string
        for col in df_temp.select_dtypes(include=['object']).columns:
             df_temp[col] = df_temp[col].astype(str)
        try:
             return hashlib.md5(pd.util.hash_pandas_object(df_temp, index=False).values).hexdigest()
        except Exception as inner_e:
             # st.error(f"Erro interno no hash do DataFrame: {inner_e}") # Comentado para evitar ruído
             return "error" 
             

def salvar_csv_no_github(token, repo, path, dataframe, branch="main", mensagem="Atualização via app"):
    """Salva o DataFrame como CSV no GitHub via API."""
    from requests import get, put
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    conteudo = dataframe.to_csv(index=False)
    conteudo_b64 = base64.b64encode(conteudo.encode()).decode()
    headers = {"Authorization": f"token {token}"}
    r = get(url, headers=headers)
    sha = r.json().get("sha") if r.status_code == 200 else None
    payload = {"message": mensagem, "content": conteudo_b64, "branch": branch}
    if sha: payload["sha"] = sha
    r2 = put(url, headers=headers, json=payload)
    if r2.status_code in (200, 201):
        # st.success(f"✅ Arquivo `{path}` atualizado no GitHub!")
        pass # Mensagem de sucesso silenciosa para evitar ruído
    else:
        st.error(f"❌ Erro ao salvar `{path}`: {r2.text}")


# Definições de colunas base
INSUMOS_BASE_COLS_GLOBAL = ["Nome", "Categoria", "Unidade", "Preço Unitário (R$)"]
PRODUTOS_BASE_COLS_GLOBAL = ["Produto", "Custo Total", "Preço à Vista", "Preço no Cartão", "Margem (%)"]
COLUNAS_CAMPOS = ["Campo", "Aplicação", "Tipo", "Opções"]

def col_defs_para(aplicacao: str):
    """Filtra as definições de colunas extras por aplicação."""
    if "campos" not in st.session_state or st.session_state.campos.empty:
        return pd.DataFrame(columns=COLUNAS_CAMPOS)
    df = st.session_state.campos
    return df[(df["Aplicação"] == aplicacao) | (df["Aplicação"] == "Ambos")].copy()

def garantir_colunas_extras(df: pd.DataFrame, aplicacao: str) -> pd.DataFrame:
    """Adiciona colunas extras ao DataFrame se ainda não existirem."""
    defs = col_defs_para(aplicacao)
    for campo in defs["Campo"].tolist():
        if campo not in df.columns:
            df[campo] = ""
    return df

def render_input_por_tipo(label, tipo, opcoes, valor_padrao=None, key=None):
    """Renderiza um widget Streamlit baseado no tipo de campo definido."""
    if tipo == "Número":
        valor = float(valor_padrao) if (valor_padrao is not None and str(valor_padrao).strip() != "") else 0.0
        return st.number_input(label, min_value=0.0, format="%.2f", value=valor, key=key)
    elif tipo == "Seleção":
        lista = _opcoes_para_lista(opcoes)
        valor_display = str(valor_padrao) if valor_padrao is not None and pd.notna(valor_padrao) else ""
        
        # Garante que o valor padrão atual está na lista, senão adiciona ele na primeira posição
        if valor_display not in lista and valor_display != "":
            lista = [valor_display] + [o for o in lista if o != valor_display]
        elif valor_display == "" and lista:
            # Se não tem valor padrão e tem opções, usa a primeira como default
            valor_display = lista[0]
            
        try:
            index_padrao = lista.index(valor_display) if valor_display in lista else 0
        except ValueError:
            index_padrao = 0
            
        return st.selectbox(label, options=lista, index=index_padrao, key=key)
    else:
        return st.text_input(label, value=str(valor_padrao) if valor_padrao is not None else "", key=key)


# ==============================================================================
# FUNÇÃO DA PÁGINA: PRECIFICAÇÃO COMPLETA
# ==============================================================================

def precificacao_completa():
    # ... (Conteúdo da página de Precificação, mantido sem alterações) ...
    st.title("📊 Precificador de Produtos")
    
    # --- Configurações do GitHub para SALVAR ---
    # As configurações de GITHUB_TOKEN, GITHUB_REPO, GITHUB_BRANCH e URL_BASE_REPOS foram movidas para o topo
    PATH_PRECFICACAO = "precificacao.csv"
    ARQ_CAIXAS = URL_BASE_REPOS + PATH_PRECFICACAO
    imagens_dict = {}
    
    # ----------------------------------------------------
    # Inicialização e Configurações
    # ----------------------------------------------------
    
    # Inicialização de variáveis de estado da Precificação
    if "produtos_manuais" not in st.session_state:
        st.session_state.produtos_manuais = pd.DataFrame(columns=[
            "Produto", "Qtd", "Custo Unitário", "Custos Extras Produto", "Margem (%)", "Imagem", "Imagem_URL"
        ])
    
    # Garante a coluna Imagem_URL para produtos existentes que possam ter sido carregados
    if "Imagem_URL" not in st.session_state.produtos_manuais.columns:
        st.session_state.produtos_manuais["Imagem_URL"] = ""

    # Inicialização de df_produtos_geral com dados de exemplo (se necessário)
    if "df_produtos_geral" not in st.session_state or st.session_state.df_produtos_geral.empty:
        exemplo_data = [
            {"Produto": "Produto A", "Qtd": 10, "Custo Unitário": 5.0, "Margem (%)": 20, "Preço à Vista": 6.0, "Preço no Cartão": 6.5},
            {"Produto": "Produto B", "Qtd": 5, "Custo Unitário": 3.0, "Margem (%)": 15, "Preço à Vista": 3.5, "Preço no Cartão": 3.8},
        ]
        df_base = pd.DataFrame(exemplo_data)
        df_base["Custos Extras Produto"] = 0.0
        df_base["Imagem"] = None
        df_base["Imagem_URL"] = ""

        st.session_state.df_produtos_geral = processar_dataframe(df_base, 0.0, 0.0, "Margem fixa", 30.0)
        st.session_state.produtos_manuais = df_base.copy()


    if "frete_manual" not in st.session_state:
        st.session_state["frete_manual"] = 0.0
    if "extras_manual" not in st.session_state:
        st.session_state["extras_manual"] = 0.0
    if "modo_margem" not in st.session_state:
        st.session_state["modo_margem"] = "Margem fixa"
    if "margem_fixa" not in st.session_state:
        st.session_state["margem_fixa"] = 30.0

    frete_total = st.session_state.get("frete_manual", 0.0)
    custos_extras = st.session_state.get("extras_manual", 0.0)
    modo_margem = st.session_state.get("modo_margem", "Margem fixa")
    margem_fixa = st.session_state.get("margem_fixa", 30.0)
    
    
    # ----------------------------------------------------
    # Lógica de Salvamento Automático
    # ----------------------------------------------------
    
    # Prepara o DataFrame para salvar: remove a coluna 'Imagem' que contém bytes
    df_to_hash = st.session_state.produtos_manuais.drop(columns=["Imagem"], errors='ignore')

    # 1. Inicializa o hash para o estado da precificação
    if "hash_precificacao" not in st.session_state:
        st.session_state.hash_precificacao = hash_df(df_to_hash)

    # 2. Verifica se houve alteração nos produtos manuais para salvar automaticamente
    novo_hash = hash_df(df_to_hash)
    if novo_hash != st.session_state.hash_precificacao:
        if novo_hash != "error": # Evita salvar se a função hash falhou
            salvar_csv_no_github(
                GITHUB_TOKEN,
                GITHUB_REPO,
                PATH_PRECFICACAO,
                df_to_hash, # Salva o df sem a coluna 'Imagem'
                GITHUB_BRANCH,
                mensagem="♻️ Alteração automática na precificação"
            )
            st.session_state.hash_precificacao = novo_hash


    # ----------------------------------------------------
    # Tabela Geral (com Edição e Exclusão)
    # ----------------------------------------------------
    st.subheader("Produtos cadastrados (Clique no índice da linha e use DEL para excluir)")
    
    cols_display = [
        "Produto", "Qtd", "Custo Unitário", "Custos Extras Produto", 
        "Custo Total Unitário", "Margem (%)", "Preço à Vista", "Preço no Cartão"
    ]
    cols_to_show = [col for col in cols_display if col in st.session_state.df_produtos_geral.columns]

    editado_df = st.data_editor(
        st.session_state.df_produtos_geral[cols_to_show],
        num_rows="dynamic", # Permite que o usuário adicione ou remova linhas
        use_container_width=True,
        key="editor_produtos_geral"
    )

    original_len = len(st.session_state.df_produtos_geral)
    edited_len = len(editado_df)
    
    # 1. Lógica de Exclusão
    if edited_len < original_len:
        
        # Filtra os produtos_manuais para manter apenas aqueles que sobreviveram na edição
        produtos_manuais_filtrado = st.session_state.produtos_manuais[
            st.session_state.produtos_manuais['Produto'].isin(editado_df['Produto'])
        ].copy()
        
        st.session_state.produtos_manuais = produtos_manuais_filtrado.reset_index(drop=True)

        # Atualiza o DataFrame geral
        st.session_state.df_produtos_geral = processar_dataframe(
            st.session_state.produtos_manuais, frete_total, custos_extras, modo_margem, margem_fixa
        )
        
        st.success("✅ Produto excluído da lista e sincronizado.")
        st.rerun()
        
    # 2. Lógica de Edição de Dados
    elif not editado_df.equals(st.session_state.df_produtos_geral[cols_to_show]):
        
        # 2a. Sincroniza as mudanças essenciais de volta ao produtos_manuais
        for idx, row in editado_df.iterrows():
            produto_nome = str(row.get('Produto'))
            
            # Encontra o índice correspondente no produtos_manuais
            manual_idx = st.session_state.produtos_manuais[st.session_state.produtos_manuais['Produto'] == produto_nome].index
            
            if not manual_idx.empty:
                manual_idx = manual_idx[0]
                
                # O Custo Unitário (base) e a Margem são os campos que realmente importam para o recálculo
                st.session_state.produtos_manuais.loc[manual_idx, "Produto"] = produto_nome
                st.session_state.produtos_manuais.loc[manual_idx, "Qtd"] = row.get("Qtd", 1)
                st.session_state.produtos_manuais.loc[manual_idx, "Custo Unitário"] = row.get("Custo Unitário", 0.0)
                st.session_state.produtos_manuais.loc[manual_idx, "Margem (%)"] = row.get("Margem (%)", margem_fixa)
                st.session_state.produtos_manuais.loc[manual_idx, "Custos Extras Produto"] = row.get("Custos Extras Produto", 0.0)


        # 2b. Recalcula o DataFrame geral com base no manual atualizado
        st.session_state.df_produtos_geral = processar_dataframe(
            st.session_state.produtos_manuais, frete_total, custos_extras, modo_margem, margem_fixa
        )
        
        st.success("✅ Dados editados e precificação recalculada!")
        st.rerun()

    # 3. Lógica de Adição (apenas alerta)
    elif edited_len > original_len:
        st.warning("⚠️ Use o formulário 'Novo Produto Manual' ou o carregamento de CSV para adicionar produtos.")
        # Reverte a adição no df_produtos_geral
        st.session_state.df_produtos_geral = st.session_state.df_produtos_geral
        st.rerun() 


    if st.button("📤 Gerar PDF e enviar para Telegram", key='precificacao_pdf_button'):
        if st.session_state.df_produtos_geral.empty:
            st.warning("⚠️ Nenhum produto para gerar PDF.")
        else:
            pdf_io = gerar_pdf(st.session_state.df_produtos_geral)
            # Passa o DataFrame completo para a função de envio
            enviar_pdf_telegram(pdf_io, st.session_state.df_produtos_geral, thread_id=TOPICO_ID)
    
    st.markdown("---")
    
    # ----------------------------------------------------
    # Abas de Precificação
    # ----------------------------------------------------
    
    tab_pdf, tab_manual, tab_github = st.tabs([
        "📄 Precificador PDF",
        "✍️ Precificador Manual",
        "📥 Carregar CSV do GitHub"
    ])

    # === Tab PDF ===
    with tab_pdf:
        st.markdown("---")
        pdf_file = st.file_uploader("📤 Selecione o PDF da nota fiscal ou lista de compras", type=["pdf"])
        if pdf_file:
            try:
                produtos_pdf = extrair_produtos_pdf(pdf_file)
                if not produtos_pdf:
                    st.warning("⚠️ Nenhum produto encontrado no PDF. Use o CSV de exemplo abaixo.")
                else:
                    df_pdf = pd.DataFrame(produtos_pdf)
                    df_pdf["Custos Extras Produto"] = 0.0
                    df_pdf["Imagem"] = None
                    df_pdf["Imagem_URL"] = "" # Inicializa nova coluna
                    # Concatena os novos produtos ao manual
                    st.session_state.produtos_manuais = pd.concat([st.session_state.produtos_manuais, df_pdf], ignore_index=True)
                    st.session_state.df_produtos_geral = processar_dataframe(
                        st.session_state.produtos_manuais, frete_total, custos_extras, modo_margem, margem_fixa
                    )
                    exibir_resultados(st.session_state.df_produtos_geral, imagens_dict)
            except Exception as e:
                st.error(f"❌ Erro ao processar o PDF: {e}")
        else:
            st.info("📄 Faça upload de um arquivo PDF para começar.")
            if st.button("📥 Carregar CSV de exemplo (PDF Tab)"):
                df_exemplo = load_csv_github(ARQ_CAIXAS)
                if not df_exemplo.empty:
                    df_exemplo["Custos Extras Produto"] = 0.0
                    df_exemplo["Imagem"] = None
                    if "Imagem_URL" not in df_exemplo.columns:
                        df_exemplo["Imagem_URL"] = ""

                    st.session_state.produtos_manuais = df_exemplo.copy()
                    st.session_state.df_produtos_geral = processar_dataframe(
                        df_exemplo, frete_total, custos_extras, modo_margem, margem_fixa
                    )
                    exibir_resultados(st.session_state.df_produtos_geral, imagens_dict)
                    st.rerun()

    # === Tab Manual ===
    with tab_manual:
        st.markdown("---")
        aba_prec_manual, aba_rateio = st.tabs(["✍️ Novo Produto Manual", "🔢 Rateio Manual"])

        with aba_rateio:
            st.subheader("🔢 Cálculo de Rateio Unitário (Frete + Custos Extras)")
            col_r1, col_r2, col_r3 = st.columns(3)
            with col_r1:
                frete_manual = st.number_input("🚚 Frete Total (R$)", min_value=0.0, step=0.01, key="frete_manual")
            with col_r2:
                extras_manual = st.number_input("🛠 Custos Extras (R$)", min_value=0.0, step=0.01, key="extras_manual")
            with col_r3:
                qtd_total_produtos = st.session_state.df_produtos_geral["Qtd"].sum() if "Qtd" in st.session_state.df_produtos_geral.columns else 0
                st.markdown(f"📦 **Qtd. Total de Produtos no DF:** {qtd_total_produtos}")
                
            qtd_total_manual = st.number_input("📦 Qtd. Total para Rateio (ajuste)", min_value=1, step=1, value=qtd_total_produtos or 1, key="qtd_total_manual_override")


            if qtd_total_manual > 0:
                rateio_calculado = (frete_manual + extras_manual) / qtd_total_manual
            else:
                rateio_calculado = 0.0

            st.session_state["rateio_manual"] = round(rateio_calculado, 4)
            st.markdown(f"💰 **Rateio Unitário Calculado:** R$ {rateio_calculado:,.4f}")
            
            if st.button("🔄 Aplicar Novo Rateio aos Produtos Existentes", key="aplicar_rateio_btn"):
                # A re-aplicação do rateio exige que se use o df_produtos_manuais como base
                # para garantir que todos os campos de input sejam recalculados.
                st.session_state.df_produtos_geral = processar_dataframe(
                    st.session_state.produtos_manuais,
                    frete_total,
                    custos_extras,
                    modo_margem,
                    margem_fixa
                )
                st.success("✅ Rateio aplicado! Verifique a tabela principal.")
                st.rerun() 

        with aba_prec_manual:
            # Rerunning para limpar o formulário após a adição
            if st.session_state.get("rerun_after_add"):
                del st.session_state["rerun_after_add"]
                st.rerun()

            st.subheader("Adicionar novo produto")

            col1, col2 = st.columns(2)
            with col1:
                produto = st.text_input("📝 Nome do Produto", key="input_produto_manual")
                quantidade = st.number_input("📦 Quantidade", min_value=1, step=1, key="input_quantidade_manual")
                valor_pago = st.number_input("💰 Valor Pago (Custo Unitário Base R$)", min_value=0.0, step=0.01, key="input_valor_pago_manual")
                
                # --- Campo de URL da Imagem ---
                imagem_url = st.text_input("🔗 URL da Imagem (opcional)", key="input_imagem_url_manual")
                # --- FIM NOVO ---

                
            with col2:
                valor_default_rateio = st.session_state.get("rateio_manual", 0.0)
                custo_extra_produto = st.number_input(
                    "💰 Custos extras do Produto (R$) + Rateio Global", min_value=0.0, step=0.01, value=valor_default_rateio, key="input_custo_extra_manual"
                )
                preco_final_sugerido = st.number_input(
                    "💸 Valor Final Sugerido (Preço à Vista) (R$)", min_value=0.0, step=0.01, key="input_preco_sugerido_manual"
                )
                
                # Uploader de arquivo (mantido como alternativa)
                imagem_file = st.file_uploader("🖼️ Foto do Produto (Upload - opcional)", type=["png", "jpg", "jpeg"], key="imagem_manual")


            custo_total_unitario = valor_pago + custo_extra_produto

            if preco_final_sugerido > 0:
                margem_calculada = 0.0
                if custo_total_unitario > 0:
                    margem_calculada = (preco_final_sugerido / custo_total_unitario - 1) * 100
                margem_manual = round(margem_calculada, 2)
                st.info(f"🧮 Margem calculada automaticamente (com base no preço sugerido): {margem_manual:.2f}%")
                preco_a_vista_calc = preco_final_sugerido
            else:
                margem_manual = st.number_input("🧮 Margem de Lucro (%)", min_value=0.0, value=30.0, key="input_margem_manual")
                preco_a_vista_calc = custo_total_unitario * (1 + margem_manual / 100)

            preco_no_cartao_calc = preco_a_vista_calc / 0.8872

            st.markdown(f"**Preço à Vista Calculado:** R$ {preco_a_vista_calc:,.2f}")
            st.markdown(f"**Preço no Cartão Calculado:** R$ {preco_no_cartao_calc:,.2f}")

            with st.form("form_submit_manual"):
                adicionar_produto = st.form_submit_button("➕ Adicionar Produto (Manual)")
                if adicionar_produto:
                    if produto and quantidade > 0 and valor_pago >= 0:
                        imagem_bytes = None
                        url_salvar = ""

                        # Prioriza o arquivo uploaded, se existir
                        if imagem_file is not None:
                            imagem_bytes = imagem_file.read()
                            imagens_dict[produto] = imagem_bytes # Guarda para exibição na sessão
                        
                        # Se não houver upload, usa a URL
                        elif imagem_url.strip():
                            url_salvar = imagem_url.strip()

                        # Se houver upload, a URL salva deve ser vazia, e vice-versa.
                        # O CSV irá persistir a Imagem_URL.

                        novo_produto_data = {
                            "Produto": [produto],
                            "Qtd": [quantidade],
                            "Custo Unitário": [valor_pago],
                            "Custos Extras Produto": [custo_extra_produto],
                            "Margem (%)": [margem_manual],
                            "Imagem": [imagem_bytes],
                            "Imagem_URL": [url_salvar] # Salva a URL para persistência
                        }
                        novo_produto = pd.DataFrame(novo_produto_data)

                        # Adiciona ao produtos_manuais
                        st.session_state.produtos_manuais = pd.concat(
                            [st.session_state.produtos_manuais, novo_produto],
                            ignore_index=True
                        ).reset_index(drop=True)
                        
                        # Processa e atualiza o DataFrame geral
                        st.session_state.df_produtos_geral = processar_dataframe(
                            st.session_state.produtos_manuais,
                            frete_total,
                            custos_extras,
                            modo_margem,
                            margem_fixa
                        )
                        st.success("✅ Produto adicionado!")
                        st.session_state["rerun_after_add"] = True 
                    else:
                        st.warning("⚠️ Preencha todos os campos obrigatórios.")

            st.markdown("---")
            st.subheader("Produtos adicionados manualmente (com botão de Excluir individual)")

            # Exibir produtos com botão de exclusão
            produtos = st.session_state.produtos_manuais

            if produtos.empty:
                st.info("⚠️ Nenhum produto cadastrado manualmente.")
            else:
                if "produto_para_excluir" not in st.session_state:
                    st.session_state["produto_para_excluir"] = None
                
                # Exibir produtos individualmente com a opção de exclusão
                for i, row in produtos.iterrows():
                    cols = st.columns([4, 1])
                    with cols[0]:
                        custo_unit_val = row.get('Custo Unitário', 0.0)
                        st.write(f"**{row['Produto']}** — Quantidade: {row['Qtd']} — Custo Unitário Base: R$ {custo_unit_val:.2f}")
                    with cols[1]:
                        if st.button(f"❌ Excluir", key=f"excluir_{i}"):
                            st.session_state["produto_para_excluir"] = i
                            break 

                # Processamento da Exclusão
                if st.session_state["produto_para_excluir"] is not None:
                    i = st.session_state["produto_para_excluir"]
                    produto_nome_excluido = produtos.loc[i, "Produto"]
                    
                    # 1. Remove do DataFrame manual
                    st.session_state.produtos_manuais = produtos.drop(i).reset_index(drop=True)
                    
                    # 2. Recalcula e atualiza o DataFrame geral
                    st.session_state.df_produtos_geral = processar_dataframe(
                        st.session_state.produtos_manuais,
                        frete_total,
                        custos_extras,
                        modo_margem,
                        margem_fixa
                    )
                    
                    # 3. Limpa o estado e força o rerun
                    st.session_state["produto_para_excluir"] = None
                    st.success(f"✅ Produto '{produto_nome_excluido}' removido da lista manual.")
                    st.rerun()

            if "df_produtos_geral" in st.session_state and not st.session_state.df_produtos_geral.empty:
                exibir_resultados(st.session_state.df_produtos_geral, imagens_dict)
            else:
                st.info("⚠️ Nenhum produto processado para exibir.")

    # === Tab GitHub ===
    with tab_github:
        st.markdown("---")
        st.header("📥 Carregar CSV de Precificação do GitHub")
        if st.button("🔄 Carregar CSV do GitHub (Tab GitHub)"):
            df_exemplo = load_csv_github(ARQ_CAIXAS)
            if not df_exemplo.empty:
                df_exemplo["Custos Extras Produto"] = 0.0
                df_exemplo["Imagem"] = None
                
                # Garante a nova coluna ao carregar
                if "Imagem_URL" not in df_exemplo.columns:
                    df_exemplo["Imagem_URL"] = ""

                st.session_state.produtos_manuais = df_exemplo.copy()
                st.session_state.df_produtos_geral = processar_dataframe(
                    df_exemplo, frete_total, custos_extras, modo_margem, margem_fixa
                )
                st.success("✅ CSV carregado e processado com sucesso!")
                exibir_resultados(st.session_state.df_produtos_geral, imagens_dict)
                st.rerun()


# ==============================================================================
# FUNÇÃO DA PÁGINA: PAPELARIA
# ==============================================================================

def papelaria_aba():
    # ... (Conteúdo da página Papelaria, mantido sem alterações) ...
    st.title("📚 Gerenciador Papelaria Personalizada")
    
    # Variáveis de Configuração
    # As configurações de GITHUB_TOKEN, GITHUB_REPO, GITHUB_BRANCH e URL_BASE_REPOS foram movidas para o topo
    URL_BASE = URL_BASE_REPOS # Usando a variável global
    INSUMOS_CSV_URL = URL_BASE + "insumos_papelaria.csv"
    PRODUTOS_CSV_URL = URL_BASE + "produtos_papelaria.csv"
    CAMPOS_CSV_URL = URL_BASE + "categorias_papelaria.csv"

    # Estado da sessão
    if "insumos" not in st.session_state:
        st.session_state.insumos = load_csv_github(INSUMOS_CSV_URL)

    if "produtos_papelaria" not in st.session_state: # Renomeado para evitar conflito com o novo "produtos" de estoque
        st.session_state.produtos_papelaria = load_csv_github(PRODUTOS_CSV_URL)

    if "campos" not in st.session_state:
        st.session_state.campos = load_csv_github(CAMPOS_CSV_URL)
        
    # Inicializações de estado para garantir DFs não nulos
    if "campos" not in st.session_state or st.session_state.campos.empty:
        st.session_state.campos = pd.DataFrame(columns=["Campo", "Aplicação", "Tipo", "Opções"])

    if "insumos" not in st.session_state or st.session_state.insumos.empty:
        st.session_state.insumos = pd.DataFrame(columns=INSUMOS_BASE_COLS_GLOBAL)

    if "produtos_papelaria" not in st.session_state or st.session_state.produtos_papelaria.empty:
        st.session_state.produtos_papelaria = pd.DataFrame(columns=["Produto", "Custo Total", "Preço à Vista", "Preço no Cartão", "Margem (%)", "Insumos Usados"])
    
    # Garante colunas base
    for col in INSUMOS_BASE_COLS_GLOBAL:
        if col not in st.session_state.insumos.columns:
            st.session_state.insumos[col] = "" if col != "Preço Unitário (R$)" else 0.0

    cols_base_prod = ["Produto"] + [c for c in PRODUTOS_BASE_COLS_GLOBAL if c != "Produto"]
    for col in cols_base_prod:
        if col not in st.session_state.produtos_papelaria.columns:
            st.session_state.produtos_papelaria[col] = "" if col not in ["Custo Total", "Preço à Vista", "Preço no Cartão", "Margem (%)"] else 0.0
            
    if "Insumos Usados" not in st.session_state.produtos_papelaria.columns:
        st.session_state.produtos_papelaria["Insumos Usados"] = "[]"


    # Garante colunas extras e tipos
    st.session_state.insumos = garantir_colunas_extras(st.session_state.insumos, "Insumos")
    st.session_state.produtos_papelaria = garantir_colunas_extras(st.session_state.produtos_papelaria, "Produtos")

    # Verifica se houve alteração nos produtos para salvar automaticamente
    if "hash_produtos_papelaria" not in st.session_state: # Renomeado o hash
        st.session_state.hash_produtos_papelaria = hash_df(st.session_state.produtos_papelaria)

    novo_hash = hash_df(st.session_state.produtos_papelaria)
    if novo_hash != st.session_state.hash_produtos_papelaria:
        if novo_hash != "error": # Evita salvar se a função hash falhou
            salvar_csv_no_github(
                GITHUB_TOKEN,
                GITHUB_REPO,
                "produtos_papelaria.csv",
                st.session_state.produtos_papelaria,
                GITHUB_BRANCH,
                mensagem="♻️ Alteração automática nos produtos (Papelaria)"
            )
            st.session_state.hash_produtos_papelaria = novo_hash

    # Criação das abas
    aba_campos, aba_insumos, aba_produtos = st.tabs(["Campos (Colunas)", "Insumos", "Produtos"])

    # =====================================
    # Aba Campos (gerencia colunas extras)
    # =====================================
    with aba_campos:
        st.header("Campos / Colunas Personalizadas")

        with st.form("form_add_campo"):
            st.subheader("Adicionar novo campo")
            nome_campo = st.text_input("Nome do Campo (será o nome da coluna)", key="novo_campo_nome")
            aplicacao = st.selectbox("Aplicação", ["Insumos", "Produtos", "Ambos"], key="novo_campo_aplicacao")
            tipo = st.selectbox("Tipo", ["Texto", "Número", "Seleção"], key="novo_campo_tipo")
            opcoes = st.text_input("Opções (se 'Seleção', separe por vírgula)", key="novo_campo_opcoes")
            adicionar = st.form_submit_button("Adicionar Campo")

            if adicionar:
                if not nome_campo.strip():
                    st.warning("Informe um nome de campo válido.")
                else:
                    ja_existe = (
                        (st.session_state.campos["Campo"].astype(str).str.lower() == nome_campo.strip().lower())
                        & (st.session_state.campos["Aplicação"] == aplicacao)
                    ).any()
                    if ja_existe:
                        st.warning("Já existe um campo com esse nome para essa aplicação.")
                    else:
                        nova_linha = {
                            "Campo": nome_campo.strip(),
                            "Aplicação": aplicacao,
                            "Tipo": tipo,
                            "Opções": opcoes
                        }
                        st.session_state.campos = pd.concat(
                            [st.session_state.campos, pd.DataFrame([nova_linha])],
                            ignore_index=True
                        ).reset_index(drop=True)
                        st.success(f"Campo '{nome_campo}' adicionado para {aplicacao}!")
                        
                        st.session_state.insumos = garantir_colunas_extras(st.session_state.insumos, "Insumos")
                        st.session_state.produtos_papelaria = garantir_colunas_extras(st.session_state.produtos_papelaria, "Produtos")
                        
                        st.rerun()

        st.markdown("### Campos cadastrados")
        if st.session_state.campos.empty:
            st.info("Nenhum campo extra cadastrado ainda.")
        else:
            st.dataframe(st.session_state.campos, use_container_width=True)

        if not st.session_state.campos.empty:
            st.divider()
            st.subheader("Editar ou Excluir campo")
            rotulos = [
                f"{row.Campo} · ({row.Aplicação})"
                for _, row in st.session_state.campos.iterrows()
            ]
            escolha = st.selectbox("Escolha um campo", [""] + rotulos, key="campo_escolhido_edit_del")
            
            if escolha:
                idx_list = st.session_state.campos.index[st.session_state.campos.apply(lambda row: f"{row.Campo} · ({row.Aplicação})" == escolha, axis=1)].tolist()
                idx = idx_list[0] if idx_list else None
                
                if idx is not None:
                    campo_atual = st.session_state.campos.loc[idx]
                    
                    acao_campo = st.radio(
                        "Ação",
                        ["Nenhuma", "Editar", "Excluir"],
                        horizontal=True,
                        key=f"acao_campo_{idx}"
                    )
                    
                    if acao_campo == "Excluir":
                        if st.button("Confirmar Exclusão", key=f"excluir_campo_{idx}"):
                            nome = campo_atual["Campo"]
                            aplic = campo_atual["Aplicação"]
                            
                            st.session_state.campos = st.session_state.campos.drop(index=idx).reset_index(drop=True)
                            
                            if aplic in ("Insumos", "Ambos") and nome in st.session_state.insumos.columns:
                                st.session_state.insumos = st.session_state.insumos.drop(columns=[nome], errors='ignore')
                            if aplic in ("Produtos", "Ambos") and nome in st.session_state.produtos_papelaria.columns:
                                st.session_state.produtos_papelaria = st.session_state.produtos_papelaria.drop(columns=[nome], errors='ignore')
                                
                            st.success(f"Campo '{nome}' removido de {aplic}!")
                            st.rerun()
                            
                    if acao_campo == "Editar":
                        with st.form(f"form_edit_campo_{idx}"):
                            novo_nome = st.text_input("Nome do Campo", value=str(campo_atual["Campo"]), key=f"edit_nome_{idx}")
                            
                            aplic_opts = ["Insumos", "Produtos", "Ambos"]
                            aplic_idx = aplic_opts.index(campo_atual["Aplicação"])
                            nova_aplic = st.selectbox("Aplicação", aplic_opts, index=aplic_idx, key=f"edit_aplic_{idx}")
                            
                            tipo_opts = ["Texto", "Número", "Seleção"]
                            tipo_idx = tipo_opts.index(campo_atual["Tipo"])
                            novo_tipo = st.selectbox("Tipo", tipo_opts, index=tipo_idx, key=f"edit_tipo_{idx}")
                            
                            novas_opcoes = st.text_input("Opções (se 'Seleção')", value=str(campo_atual["Opções"]) if pd.notna(campo_atual["Opções"]) else "", key=f"edit_opcoes_{idx}")
                            
                            salvar = st.form_submit_button("Salvar Alterações")
                            
                            if salvar:
                                nome_antigo = campo_atual["Campo"]
                                aplic_antiga = campo_atual["Aplicação"]
                                
                                st.session_state.campos.loc[idx, ["Campo","Aplicação","Tipo","Opções"]] = [
                                    novo_nome, nova_aplic, novo_tipo, novas_opcoes
                                ]
                                
                                renomeou = (str(novo_nome).strip() != str(nome_antigo).strip())
                                
                                if renomeou:
                                    if aplic_antiga in ("Insumos", "Ambos") and nome_antigo in st.session_state.insumos.columns:
                                        st.session_state.insumos = st.session_state.insumos.rename(columns={nome_antigo: novo_nome})
                                    if aplic_antiga in ("Produtos", "Ambos") and nome_antigo in st.session_state.produtos_papelaria.columns:
                                        st.session_state.produtos_papelaria = st.session_state.produtos_papelaria.rename(columns={nome_antigo: novo_nome})
                                        
                                st.session_state.insumos = garantir_colunas_extras(st.session_state.insumos, "Insumos")
                                st.session_state.produtos_papelaria = garantir_colunas_extras(st.session_state.produtos_papelaria, "Produtos")

                                st.success("Campo atualizado!")
                                st.rerun()
                            
        if not st.session_state.produtos_papelaria.empty:
            st.markdown("### 📥 Exportação (aba Campos)")
            baixar_csv_aba(st.session_state.produtos_papelaria, "produtos_papelaria.csv", key_suffix="campos")


    # =====================================
    # Aba Insumos
    # =====================================
    with aba_insumos:
        st.header("Insumos")

        st.session_state.insumos = garantir_colunas_extras(st.session_state.insumos, "Insumos")

        with st.form("form_add_insumo"):
            st.subheader("Adicionar novo insumo")
            nome_insumo = st.text_input("Nome do Insumo", key="novo_insumo_nome")
            categoria_insumo = st.text_input("Categoria", key="novo_insumo_categoria")
            unidade_insumo = st.text_input("Unidade de Medida (ex: un, kg, m)", key="novo_insumo_unidade")
            preco_insumo = st.number_input("Preço Unitário (R$)", min_value=0.0, format="%.2f", key="novo_insumo_preco")

            extras_insumos = col_defs_para("Insumos")
            valores_extras = {}
            if not extras_insumos.empty:
                st.markdown("**Campos extras**")
                for i, row in extras_insumos.reset_index(drop=True).iterrows():
                    key = f"novo_insumo_extra_{row['Campo']}"
                    valores_extras[row["Campo"]] = render_input_por_tipo(
                        label=row["Campo"],
                        tipo=row["Tipo"],
                        opcoes=row["Opções"],
                        valor_padrao=None,
                        key=key
                    )

            adicionou = st.form_submit_button("Adicionar Insumo")
            if adicionou:
                if not nome_insumo.strip():
                    st.warning("Informe o Nome do Insumo.")
                else:
                    novo = {
                        "Nome": nome_insumo.strip(),
                        "Categoria": categoria_insumo.strip(),
                        "Unidade": unidade_insumo.strip(),
                        "Preço Unitário (R$)": float(preco_insumo),
                    }
                    for k, v in valores_extras.items():
                        novo[k] = v
                        
                    st.session_state.insumos = garantir_colunas_extras(st.session_state.insumos, "Insumos")
                    
                    st.session_state.insumos = pd.concat([st.session_state.insumos, pd.DataFrame([novo])], ignore_index=True).reset_index(drop=True)
                    st.success(f"Insumo '{nome_insumo}' adicionado!")
                    st.rerun()

        st.markdown("### Insumos cadastrados")
        ordem_cols = INSUMOS_BASE_COLS_GLOBAL + [c for c in st.session_state.insumos.columns if c not in INSUMOS_BASE_COLS_GLOBAL]
        st.dataframe(st.session_state.insumos.reindex(columns=ordem_cols), use_container_width=True)

        if not st.session_state.insumos.empty:
            insumo_selecionado = st.selectbox(
                "Selecione um insumo",
                [""] + st.session_state.insumos["Nome"].astype(str).fillna("").tolist(),
                key="insumo_escolhido_edit_del"
            )
        else:
            insumo_selecionado = None

        if insumo_selecionado:
            acao_insumo = st.radio(
                f"Ação para '{insumo_selecionado}'",
                ["Nenhuma", "Editar", "Excluir"],
                horizontal=True,
                key=f"acao_insumo_{insumo_selecionado}"
            )

            idxs = st.session_state.insumos.index[st.session_state.insumos["Nome"] == insumo_selecionado].tolist()
            idx = idxs[0] if idxs else None

            if acao_insumo == "Excluir" and idx is not None:
                if st.button("Confirmar Exclusão", key=f"excluir_insumo_{idx}"):
                    st.session_state.insumos = st.session_state.insumos.drop(index=idx).reset_index(drop=True)
                    st.success(f"Insumo '{insumo_selecionado}' removido!")
                    st.rerun()

            if acao_insumo == "Editar" and idx is not None:
                atual = st.session_state.insumos.loc[idx].fillna("")
                with st.form(f"form_edit_insumo_{idx}"):
                    novo_nome = st.text_input("Nome do Insumo", value=str(atual.get("Nome","")), key=f"edit_insumo_nome_{idx}")
                    nova_categoria = st.text_input("Categoria", value=str(atual.get("Categoria","")), key=f"edit_insumo_categoria_{idx}")
                    nova_unidade = st.text_input("Unidade de Medida (ex: un, kg, m)", value=str(atual.get("Unidade","")), key=f"edit_insumo_unidade_{idx}")
                    novo_preco = st.number_input(
                        "Preço Unitário (R$)", min_value=0.0, format="%.2f",
                        value=float(atual.get("Preço Unitário (R$)", 0.0)),
                        key=f"edit_insumo_preco_{idx}"
                    )

                    valores_extras_edit = {}
                    extras_insumos = col_defs_para("Insumos")
                    if not extras_insumos.empty:
                        st.markdown("**Campos extras**")
                        for i, row in extras_insumos.reset_index(drop=True).iterrows():
                            campo = row["Campo"]
                            key = f"edit_insumo_extra_{idx}_{campo}"
                            valores_extras_edit[campo] = render_input_por_tipo(
                                label=campo,
                                tipo=row["Tipo"],
                                opcoes=row["Opções"],
                                valor_padrao=atual.get(campo, ""),
                                key=key
                            )

                    salvou = st.form_submit_button("Salvar Alterações", key=f"salvar_insumo_{idx}")
                    if salvou:
                        st.session_state.insumos.loc[idx, "Nome"] = novo_nome
                        st.session_state.insumos.loc[idx, "Categoria"] = nova_categoria
                        st.session_state.insumos.loc[idx, "Unidade"] = nova_unidade
                        st.session_state.insumos.loc[idx, "Preço Unitário (R$)"] = float(novo_preco)
                        for k, v in valores_extras_edit.items():
                            st.session_state.insumos.loc[idx, k] = v
                        st.success("Insumo atualizado!")
                        st.rerun()


    # =====================================
    # Aba Produtos
    # =====================================
    with aba_produtos:
        st.header("Produtos")

        with st.form("form_add_produto"):
            st.subheader("Adicionar novo produto")
            nome_produto = st.text_input("Nome do Produto", key="novo_produto_nome")

            if 'Nome' in st.session_state.insumos.columns:
                insumos_disponiveis = st.session_state.insumos["Nome"].dropna().unique().tolist()
            else:
                insumos_disponiveis = []

            insumos_selecionados = st.multiselect("Selecione os insumos usados", insumos_disponiveis, key="novo_produto_insumos_selecionados")

            insumos_usados = []
            custo_total = 0.0

            for insumo in insumos_selecionados:
                dados_insumo = st.session_state.insumos.loc[st.session_state.insumos["Nome"] == insumo].iloc[0]
                preco_unit = float(dados_insumo.get("Preço Unitário (R$)", 0.0))
                unidade = str(dados_insumo.get("Unidade", ""))

                qtd_usada = st.number_input(
                    f"Quantidade usada de {insumo} ({unidade}) - Preço unitário R$ {preco_unit:.2f}",
                    min_value=0.0,
                    step=0.01,
                    key=f"novo_qtd_{insumo}"
                )

                custo_insumo = qtd_usada * preco_unit
                custo_total += custo_insumo

                insumos_usados.append({
                    "Insumo": insumo,
                    "Quantidade Usada": qtd_usada,
                    "Unidade": unidade,
                    "Preço Unitário (R$)": preco_unit,
                    "Custo": custo_insumo
                })

            st.markdown(f"**Custo Total Calculado (Insumos): R$ {custo_total:,.2f}**")

            margem = st.number_input("Margem de Lucro (%)", min_value=0.0, format="%.2f", value=30.0, key="novo_produto_margem")

            preco_vista = custo_total * (1 + margem / 100) if custo_total > 0 else 0.0
            preco_cartao = preco_vista / 0.8872 if preco_vista > 0 else 0.0

            st.markdown(f"💸 **Preço à Vista Calculado:** R$ {preco_vista:,.2f}")
            st.markdown(f"💳 **Preço no Cartão Calculado:** R$ {preco_cartao:,.2f}")

            extras_produtos = col_defs_para("Produtos")
            valores_extras_prod = {}
            if not extras_produtos.empty:
                st.markdown("**Campos extras**")
                for i, row in extras_produtos.reset_index(drop=True).iterrows():
                    key = f"novo_produto_extra_{row['Campo']}"
                    valores_extras_prod[row["Campo"]] = render_input_por_tipo(
                        label=row["Campo"],
                        tipo=row["Tipo"],
                        opcoes=row["Opções"],
                        valor_padrao=None,
                        key=key
                    )

            adicionou_prod = st.form_submit_button("Adicionar Produto")
            if adicionou_prod:
                if not nome_produto.strip():
                    st.warning("Informe o Nome do Produto.")
                elif not insumos_usados:
                    st.warning("Selecione ao menos um insumo para o produto.")
                else:
                    novo = {
                        "Produto": nome_produto.strip(),
                        "Custo Total": float(custo_total),
                        "Preço à Vista": float(preco_vista),
                        "Preço no Cartão": float(preco_cartao),
                        "Margem (%)": float(margem),
                        "Insumos Usados": str(insumos_usados)
                    }
                    for k, v in valores_extras_prod.items():
                        novo[k] = v

                    # Envio da mensagem para o Telegram (mantido)
                    try:
                        TELEGRAM_TOKEN_SECRET = st.secrets.get("telegram_token", HARDCODED_TELEGRAM_TOKEN)
                        TELEGRAM_CHAT_ID_PROD = TELEGRAM_CHAT_ID
                        THREAD_ID_PROD = 43

                        mensagem = f"<b>📦 Novo Produto Cadastrado:</b>\n"
                        mensagem += f"<b>Produto:</b> {nome_produto}\n"
                        mensagem += "<b>Insumos:</b>\n"

                        for insumo in insumos_usados:
                            nome = insumo['Insumo']
                            qtd = insumo['Quantidade Usada']
                            un = insumo['Unidade']
                            custo = insumo['Custo']
                            mensagem += f"• {nome} - {qtd} {un} (R$ {custo:.2f})\n"

                        mensagem += f"\n<b>Custo Total:</b> R$ {custo_total:,.2f}"
                        mensagem += f"\n<b>Preço à Vista:</b> R$ {preco_vista:,.2f}"
                        mensagem += f"\n<b>Preço no Cartão:</b> R$ {preco_cartao:,.2f}"

                        telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN_SECRET}/sendMessage"
                        payload = {
                            "chat_id": TELEGRAM_CHAT_ID_PROD,
                            "message_thread_id": THREAD_ID_PROD,
                            "text": mensagem,
                            "parse_mode": "HTML"
                        }

                        response = requests.post(telegram_url, json=payload)
                        if response.status_code != 200:
                            st.warning(f"⚠️ Erro ao enviar para Telegram: {response.text}")
                        else:
                             st.success("✅ Mensagem enviada para o Telegram!")

                    except Exception as e:
                        st.warning(f"⚠️ Falha ao tentar enviar para o Telegram: {e}")

                    # Salva no DataFrame local
                    st.session_state.produtos_papelaria = garantir_colunas_extras(st.session_state.produtos_papelaria, "Produtos")
                    
                    st.session_state.produtos_papelaria = pd.concat(
                        [st.session_state.produtos_papelaria, pd.DataFrame([novo])],
                        ignore_index=True
                    ).reset_index(drop=True)
                    st.success(f"Produto '{nome_produto}' adicionado!")
                    st.rerun()

        st.markdown("### Produtos cadastrados")
        ordem_cols_p = PRODUTOS_BASE_COLS_GLOBAL + ["Insumos Usados"] + [c for c in st.session_state.produtos_papelaria.columns if c not in PRODUTOS_BASE_COLS_GLOBAL + ["Insumos Usados"]]
        st.dataframe(st.session_state.produtos_papelaria.reindex(columns=ordem_cols_p), use_container_width=True)

        if not st.session_state.produtos_papelaria.empty:
            produto_selecionado = st.selectbox(
                "Selecione um produto",
                [""] + st.session_state.produtos_papelaria["Produto"].astype(str).fillna("").tolist(),
                key="produto_escolhido_edit_del"
            )
        else:
            produto_selecionado = None

        if produto_selecionado:
            acao_produto = st.radio(
                f"Ação para '{produto_selecionado}'",
                ["Nenhuma", "Editar", "Excluir"],
                horizontal=True,
                key=f"acao_produto_{produto_selecionado}"
            )

            idxs_p = st.session_state.produtos_papelaria.index[st.session_state.produtos_papelaria["Produto"] == produto_selecionado].tolist()
            idx_p = idxs_p[0] if idxs_p else None

            if acao_produto == "Excluir" and idx_p is not None:
                if st.button("Confirmar Exclusão", key=f"excluir_produto_{idx_p}"):
                    st.session_state.produtos_papelaria = st.session_state.produtos_papelaria.drop(index=idx_p).reset_index(drop=True)
                    st.success(f"Produto '{produto_selecionado}' removido!")
                    st.rerun()

            if acao_produto == "Editar" and idx_p is not None:
                atual_p = st.session_state.produtos_papelaria.loc[idx_p].fillna("")
                with st.form(f"form_edit_produto_{idx_p}"):
                    novo_nome = st.text_input("Nome do Produto", value=str(atual_p.get("Produto","")), key=f"edit_produto_nome_{idx_p}")
                    nova_margem = st.number_input("Margem (%)", min_value=0.0, format="%.2f", value=float(atual_p.get("Margem (%)", 0.0)), key=f"edit_produto_margem_{idx_p}")

                    try:
                        insumos_atual = ast.literal_eval(atual_p.get("Insumos Usados", "[]"))
                        if not isinstance(insumos_atual, list):
                            insumos_atual = []
                    except Exception:
                        insumos_atual = []

                    insumos_disponiveis = st.session_state.insumos["Nome"].dropna().unique().tolist()
                    nomes_pre_selecionados = [i["Insumo"] for i in insumos_atual]
                    insumos_editados = st.multiselect("Selecione os insumos usados", insumos_disponiveis, default=nomes_pre_selecionados, key=f"edit_produto_insumos_selecionados_{idx_p}")

                    insumos_usados_edit = []
                    novo_custo = 0.0

                    for insumo in insumos_editados:
                        dados_insumo = st.session_state.insumos.loc[st.session_state.insumos["Nome"] == insumo].iloc[0]
                        preco_unit = float(dados_insumo.get("Preço Unitário (R$)", 0.0))
                        unidade = str(dados_insumo.get("Unidade", ""))

                        qtd_default = 0.0
                        for item in insumos_atual:
                            if item.get("Insumo") == insumo:
                                qtd_default = float(item.get("Quantidade Usada", 0.0))

                        qtd_usada = st.number_input(
                            f"Quantidade usada de {insumo} ({unidade}) - Preço unitário R$ {preco_unit:.2f}",
                            min_value=0.0,
                            step=0.01,
                            value=qtd_default,
                            key=f"edit_qtd_{idx_p}_{insumo}"
                        )

                        custo_insumo = qtd_usada * preco_unit
                        novo_custo += custo_insumo

                        insumos_usados_edit.append({
                            "Insumo": insumo,
                            "Quantidade Usada": qtd_usada,
                            "Unidade": unidade,
                            "Preço Unitário (R$)": preco_unit,
                            "Custo": custo_insumo
                        })

                    novo_vista = novo_custo * (1 + nova_margem / 100)
                    novo_cartao = novo_vista / 0.8872

                    st.markdown(f"**Novo custo calculado: R$ {novo_custo:,.2f}**")
                    st.markdown(f"💸 **Preço à Vista Recalculado:** R$ {novo_vista:,.2f}")
                    st.markdown(f"💳 **Preço no Cartão Recalculado:** R$ {novo_cartao:,.2f}")

                    valores_extras_edit_p = {}
                    extras_produtos = col_defs_para("Produtos")
                    if not extras_produtos.empty:
                        st.markdown("**Campos extras**")
                        for i, row in extras_produtos.reset_index(drop=True).iterrows():
                            campo = row["Campo"]
                            key = f"edit_produto_extra_{idx_p}_{campo}"
                            valores_extras_edit_p[campo] = render_input_por_tipo(
                                label=campo,
                                tipo=row["Tipo"],
                                opcoes=row["Opções"],
                                valor_padrao=atual_p.get(campo, ""),
                                key=key
                            )

                    salvou_p = st.form_submit_button("Salvar Alterações", key=f"salvar_produto_{idx_p}")
                    if salvou_p:
                        st.session_state.produtos_papelaria.loc[idx_p, "Produto"] = novo_nome
                        st.session_state.produtos_papelaria.loc[idx_p, "Custo Total"] = float(novo_custo)
                        st.session_state.produtos_papelaria.loc[idx_p, "Preço à Vista"] = float(novo_vista)
                        st.session_state.produtos_papelaria.loc[idx_p, "Preço no Cartão"] = float(novo_cartao)
                        # LINHA CORRIGIDA ABAIXO
                        st.session_state.produtos_papelaria.loc[idx_p, "Margem (%)"] = float(nova_margem)
                        st.session_state.produtos_papelaria.loc[idx_p, "Insumos Usados"] = str(insumos_usados_edit)
                        for k, v in valores_extras_edit_p.items():
                            st.session_state.produtos_papelaria.loc[idx_p, k] = v
                        st.success("Produto atualizado!")
                        st.rerun()

        # botão de exportação CSV fora dos forms
        if not st.session_state.produtos_papelaria.empty:
            baixar_csv_aba(st.session_state.produtos_papelaria, "produtos_papelaria.csv", key_suffix="produtos")
            
# FIM DA FUNÇÃO papelaria_aba()

# ==============================================================================
# FUNÇÃO DA PÁGINA: GESTÃO DE PRODUTOS (ESTOQUE)
# ==============================================================================

def gestao_produtos():
    
    # ----------------------------------------------------
    # Inicialização e Carga do Estoque
    # ----------------------------------------------------
    COLUNAS_PRODUTOS = [
        "ID", "Nome", "Marca", "Categoria", "Quantidade", "PrecoCusto", 
        "PrecoVista", "PrecoCartao", "Validade", "FotoURL", "CodigoBarras", "PaiID"
    ]
    
    if "produtos" not in st.session_state:
        df_carregado = load_csv_github(URL_PRODUTOS)
        
        if df_carregado.empty:
            st.session_state.produtos = pd.DataFrame(columns=COLUNAS_PRODUTOS)
        else:
            for col in COLUNAS_PRODUTOS:
                if col not in df_carregado.columns:
                    df_carregado[col] = ''
            
            # Garante tipos corretos para manipulação (especialmente Quantidade e Preços)
            df_carregado["Quantidade"] = pd.to_numeric(df_carregado["Quantidade"], errors='coerce').fillna(0).astype(int)
            df_carregado["PrecoCusto"] = pd.to_numeric(df_carregado["PrecoCusto"], errors='coerce').fillna(0.0)
            df_carregado["PrecoVista"] = pd.to_numeric(df_carregado["PrecoVista"], errors='coerce').fillna(0.0)
            df_carregado["PrecoCartao"] = pd.to_numeric(df_carregado["PrecoCartao"], errors='coerce').fillna(0.0)
            
            st.session_state.produtos = df_carregado
            
    produtos = st.session_state.produtos

    # ----------------------------------------------------
    # Lógica de Salvamento Automático
    # ----------------------------------------------------
    if "hash_produtos_estoque" not in st.session_state:
        st.session_state.hash_produtos_estoque = hash_df(produtos)

    novo_hash = hash_df(produtos)
    if novo_hash != st.session_state.hash_produtos_estoque:
        if novo_hash != "error":
            save_csv_github(produtos, ARQ_PRODUTOS, "Atualização automática de estoque/produtos")
            st.session_state.hash_produtos_estoque = novo_hash

    # Título da Página
    st.header("📦 Gestão de Produtos e Estoque")

    # ================================
    # SUBABAS
    # ================================
    tab_cadastro, tab_lista = st.tabs(["📝 Cadastro de Produtos", "📑 Lista & Busca"])

    # ================================
    # SUBABA: CADASTRO (Lógica fornecida pelo usuário)
    # ================================
    with tab_cadastro:
        st.subheader("📝 Cadastro de Produtos")

        # --- Cadastro ---
        with st.expander("Cadastrar novo produto", expanded=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                # Produto pai ou simples
                tipo_produto = st.radio("Tipo de produto", ["Produto simples", "Produto com variações (grade)"], key="cad_tipo_produto")

                nome = st.text_input("Nome", key="cad_nome")
                marca = st.text_input("Marca", key="cad_marca")
                categoria = st.text_input("Categoria", key="cad_categoria")

            with c2:
                # Se for produto simples, cadastro direto da quantidade e preços
                if tipo_produto == "Produto simples":
                    qtd = st.number_input("Quantidade", min_value=0, step=1, value=0, key="cad_qtd")
                    # Usando to_float na conversão de volta
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
                foto_arquivo = st.file_uploader("📷 Enviar Foto", type=["png", "jpg", "jpeg"], key="cad_foto")

                if "codigo_barras" not in st.session_state:
                    st.session_state["codigo_barras"] = ""

                # O campo de código de barras principal é mantido apenas para Produto Simples/Pai
                codigo_barras = st.text_input("Código de Barras (Pai/Simples)", value=st.session_state["codigo_barras"], key="cad_cb")

                # --- Escanear com câmera (Produto Simples/Pai) ---
                foto_codigo = st.camera_input("📷 Escanear código de barras / QR Code", key="cad_cam")
                if foto_codigo is not None:
                    imagem_bytes = foto_codigo.getvalue()
                    codigos_lidos = ler_codigo_barras_api(imagem_bytes)
                    if codigos_lidos:
                        st.session_state["codigo_barras"] = codigos_lidos[0]
                        st.success(f"Código lido: {st.session_state['codigo_barras']}")
                        st.rerun() # Usando st.rerun() em vez de st.experimental_rerun()
                    else:
                        st.error("❌ Não foi possível ler nenhum código.")

                # --- Upload de imagem do código de barras (Produto Simples/Pai) ---
                foto_codigo_upload = st.file_uploader("📤 Upload de imagem do código de barras", type=["png", "jpg", "jpeg"], key="cad_cb_upload")
                if foto_codigo_upload is not None:
                    imagem_bytes = foto_codigo_upload.getvalue()
                    codigos_lidos = ler_codigo_barras_api(imagem_bytes)
                    if codigos_lidos:
                        st.session_state["codigo_barras"] = codigos_lidos[0]
                        st.success(f"Código lido via upload: {st.session_state['codigo_barras']}")
                        st.rerun() # Usando st.rerun() em vez de st.experimental_rerun()
                    else:
                        st.error("❌ Não foi possível ler nenhum código da imagem enviada.")

            # --- Cadastro da grade (variações) ---
            variações = []
            if tipo_produto == "Produto com variações (grade)":
                st.markdown("#### Cadastro das variações (grade)")
                qtd_variações = st.number_input("Quantas variações deseja cadastrar?", min_value=1, step=1, key="cad_qtd_variações")

                # Inicializa a lista de códigos de barras lidos para a grade na sessão
                if 'cb_grade_lidos' not in st.session_state:
                    st.session_state.cb_grade_lidos = {}
                    
                variações = []
                for i in range(int(qtd_variações)):
                    # Adicionado separador de linha para melhor visualização
                    st.markdown(f"--- **Variação {i+1}** ---")
                    
                    # Colunas para Nome, Qtd, Custo e Vista
                    var_c1, var_c2, var_c3, var_c4 = st.columns(4)
                    
                    var_nome = var_c1.text_input(f"Nome da variação {i+1}", key=f"var_nome_{i}")
                    var_qtd = var_c2.number_input(f"Quantidade variação {i+1}", min_value=0, step=1, value=0, key=f"var_qtd_{i}")
                    var_preco_custo = var_c3.text_input(f"Preço de custo variação {i+1}", value="0,00", key=f"var_pc_{i}")
                    var_preco_vista = var_c4.text_input(f"Preço à vista variação {i+1}", value="0,00", key=f"var_pv_{i}")
                    
                    # --- Leitura/Upload de Código de Barras para a Variação ---
                    # Colunas para Código de Barras (texto), Upload e Câmera
                    var_cb_c1, var_cb_c2, var_cb_c3 = st.columns([2, 1, 1])

                    # 1. Campo de texto do Código de Barras (puxa o valor lido da sessão)
                    with var_cb_c1:
                        valor_cb_inicial = st.session_state.cb_grade_lidos.get(f"var_cb_{i}", "")
                        var_codigo_barras = st.text_input(
                            f"Código de barras variação {i+1}", 
                            value=valor_cb_inicial, 
                            key=f"var_cb_{i}" # Chave principal para o CB da variação
                        )
                        
                    # 2. Upload da foto
                    with var_cb_c2:
                        var_foto_upload = st.file_uploader(
                            "Upload CB", 
                            type=["png", "jpg", "jpeg"], 
                            key=f"var_cb_upload_{i}"
                        )
                    
                    # 3. Câmera
                    with var_cb_c3:
                        var_foto_cam = st.camera_input(
                            "Escanear CB", 
                            key=f"var_cb_cam_{i}"
                        )
                    
                    # Logica de leitura do Código de Barras
                    foto_lida = var_foto_upload or var_foto_cam
                    if foto_lida:
                        # Se for ler o código, usa o buffer do objeto file_uploader/camera_input
                        imagem_bytes = foto_lida.getvalue() 
                        codigos_lidos = ler_codigo_barras_api(imagem_bytes)
                        if codigos_lidos:
                            # Armazena o código lido no estado da sessão (será puxado pelo campo de texto acima)
                            st.session_state.cb_grade_lidos[f"var_cb_{i}"] = codigos_lidos[0]
                            st.success(f"CB Variação {i+1} lido: {codigos_lidos[0]}")
                            st.rerun() # Usando st.rerun() em vez de st.experimental_rerun()
                        else:
                            st.error(f"❌ Variação {i+1}: Não foi possível ler o código.")

                    # Coleta os dados da variação para salvar
                    variações.append({
                        "Nome": var_nome.strip(),
                        "Quantidade": int(var_qtd),
                        "PrecoCusto": to_float(var_preco_custo),
                        "PrecoVista": to_float(var_preco_vista),
                        "PrecoCartao": round(to_float(var_preco_vista) / FATOR_CARTAO, 2) if to_float(var_preco_vista) > 0 else 0.0,
                        # Usa o valor final do campo de texto (que pode ter sido preenchido pela leitura)
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
                        "PaiID": None # Produto simples, sem pai
                    }
                    produtos = pd.concat([produtos, pd.DataFrame([novo])], ignore_index=True)
                else:
                    # Produto pai
                    novo_pai = {
                        "ID": novo_id,
                        "Nome": nome.strip(),
                        "Marca": marca.strip(),
                        "Categoria": categoria.strip(),
                        "Quantidade": 0, # estoque do pai fica 0, soma nas variações
                        "PrecoCusto": 0.0,
                        "PrecoVista": 0.0,
                        "PrecoCartao": 0.0,
                        "Validade": str(validade),
                        "FotoURL": foto_url.strip(),
                        "CodigoBarras": codigo_barras.strip(),
                        "PaiID": None
                    }
                    produtos = pd.concat([produtos, pd.DataFrame([novo_pai])], ignore_index=True)

                    # Agora cadastra as variações ligadas ao pai pelo ID
                    for var in variações:
                        if var["Nome"] == "":
                            continue # pula variações sem nome
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
                            "PaiID": novo_id # aponta para o produto pai
                        }
                        produtos = pd.concat([produtos, pd.DataFrame([novo_filho])], ignore_index=True)

                st.session_state["produtos"] = produtos
                # Limpa a sessão de códigos de barras lidos da grade
                if 'cb_grade_lidos' in st.session_state:
                    del st.session_state.cb_grade_lidos 
                if 'codigo_barras' in st.session_state:
                    del st.session_state.codigo_barras 
                    
                save_csv_github(produtos, ARQ_PRODUTOS, "Novo produto cadastrado")
                st.success(f"✅ Produto '{nome}' cadastrado com sucesso!")
                st.rerun()

    # ================================
    # SUBABA: LISTA & BUSCA (Lógica fornecida pelo usuário)
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

            # ✅ Garantir que PaiID exista mesmo após filtro
            if "PaiID" not in produtos_filtrados.columns:
                produtos_filtrados["PaiID"] = None

        # --- Lista de produtos com agrupamento por Pai e Variações ---
        st.markdown("### Lista de produtos")

        if produtos_filtrados.empty:
            st.info("Nenhum produto encontrado.")
        else:
            # Separar produtos pais e variações (filhos)
            produtos_pai = produtos_filtrados[produtos_filtrados["PaiID"].isnull()]
            produtos_filho = produtos_filtrados[produtos_filtrados["PaiID"].notnull()]

            for index, pai in produtos_pai.iterrows():
                with st.container(border=True): # Adicionado border para melhor visualização do Pai
                    c = st.columns([1, 3, 1, 1, 1])
                    # Imagem do produto pai
                    if str(pai["FotoURL"]).strip():
                        try:
                            c[0].image(pai["FotoURL"], width=80)
                        except Exception:
                            c[0].write("Sem imagem")
                    else:
                        c[0].write("—")

                    cb = f' • CB: {pai["CodigoBarras"]}' if str(pai.get("CodigoBarras", "")).strip() else ""
                    c[1].markdown(f"**{pai['Nome']}** \nMarca: {pai['Marca']} \nCat: {pai['Categoria']}{cb}")
                    
                    # Soma o estoque total se houver variações, senão usa o estoque do Pai (produto simples)
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
                            # ✅ Garante que a coluna 'PaiID' existe
                            if "PaiID" not in produtos.columns:
                                produtos["PaiID"] = None

                            # Apaga o pai
                            produtos = produtos[produtos["ID"] != str(eid)]

                            # Apaga as variações ligadas ao pai
                            produtos = produtos[produtos["PaiID"] != str(eid)]

                            # Atualiza estado e salva
                            st.session_state["produtos"] = produtos
                            save_csv_github(produtos, ARQ_PRODUTOS, "Atualizando produtos")
                            st.warning(f"Produto {pai['Nome']} e suas variações excluídas!")
                            st.rerun()

                    # Listar variações filhas do produto
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
                                        save_csv_github(produtos, ARQ_PRODUTOS, "Atualizando produtos")
                                        st.warning(f"Variação {var['Nome']} excluída!")
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
                        vdata = datetime.datetime.strptime(str(row["Validade"] or date.today()), "%Y-%m-%d").date()
                    except Exception:
                        vdata = date.today()
                    nova_validade = st.date_input("Validade", value=vdata, key=f"edit_val_{eid}")
                    nova_foto = st.text_input("URL da Foto", value=row["FotoURL"], key=f"edit_foto_{eid}")
                    novo_cb = st.text_input("Código de Barras", value=str(row.get("CodigoBarras", "")), key=f"edit_cb_{eid}")

                    foto_codigo_edit = st.camera_input("📷 Atualizar código de barras", key=f"edit_cam_{eid}")
                    if foto_codigo_edit is not None:
                        # Assumindo que ler_codigo_barras_api aceita bytes ou buffer
                        codigo_lido = ler_codigo_barras_api(foto_codigo_edit.getbuffer()) 
                        if codigo_lido:
                            novo_cb = codigo_lido[0]
                            st.success(f"Código lido: {novo_cb}")

                col_save, col_cancel = st.columns([1, 1])
                with col_save:
                    if st.button("Salvar alterações", key=f"save_{eid}"):
                        
                        # Calcula Preço Cartão
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
                        save_csv_github(produtos, ARQ_PRODUTOS, "Atualizando produto")
                        # Remove a chave para fechar a aba de edição
                        del st.session_state["edit_prod"]
                        st.success("Produto atualizado!")
                        st.rerun()
                        
                with col_cancel:
                    if st.button("Cancelar edição", key=f"cancel_{eid}"):
                        # Remove a chave para fechar a aba de edição
                        del st.session_state["edit_prod"]
                        st.info("Edição cancelada.")
                        st.rerun()


# ==============================================================================
# FUNÇÃO DA PÁGINA: LIVRO CAIXA (DÍVIDAS/MOVIMENTAÇÕES)
# ==============================================================================

def livro_caixa():
    st.title("💰 Livro Caixa (Dívidas e Vendas)")

    # Carrega dados do Estoque (apenas se não estiver carregado)
    if "produtos" not in st.session_state or st.session_state.produtos.empty:
        gestao_produtos() # Roda para forçar a carga inicial
        produtos = st.session_state.produtos
    else:
        produtos = st.session_state.produtos
    
    # Produtos disponíveis para venda (apenas filhos ou simples, não os pais)
    produtos_para_venda = produtos[produtos["PaiID"].notna() | produtos["PaiID"].isnull()]
    opcoes_produtos = [""] + produtos_para_venda.apply(
        lambda row: f"{row.ID} | {row.Nome} ({row.Marca}) | Estoque: {row.Quantidade}", axis=1
    ).tolist()
    
    # ----------------------------------------------------
    # Lógica de Movimentação de Estoque
    # ----------------------------------------------------

    def ajustar_estoque(id_produto, quantidade, operacao="debitar"):
        """Ajusta a quantidade no estoque e persiste."""
        
        # 1. Tenta localizar o produto pelo ID
        idx_produto = st.session_state.produtos[st.session_state.produtos["ID"] == id_produto].index
        
        if not idx_produto.empty:
            idx = idx_produto[0]
            qtd_atual = st.session_state.produtos.loc[idx, "Quantidade"]
            
            if operacao == "debitar":
                nova_qtd = qtd_atual - quantidade
                st.session_state.produtos.loc[idx, "Quantidade"] = max(0, nova_qtd)
                return True
            
            elif operacao == "creditar":
                nova_qtd = qtd_atual + quantidade
                st.session_state.produtos.loc[idx, "Quantidade"] = nova_qtd
                return True
                
        return False
    
    # ----------------------------------------------------
    # Inicialização e Carga das Dívidas/Movimentações
    # ----------------------------------------------------
    
    COLUNAS_DIVIDAS = [
        "ID", "Tipo", "Valor", "Nome_Cliente", "Descricao", 
        "Data_Vencimento", "Status", "Data_Pagamento", "Forma_Pagamento",
        "Data_Criacao", "Produtos_Vendidos" # NOVO: JSON string de produtos vendidos
    ]
    
    if "dividas" not in st.session_state:
        df_carregado = load_csv_github(ARQ_DIVIDAS)
        
        if df_carregado.empty:
            st.session_state.dividas = pd.DataFrame(columns=COLUNAS_DIVIDAS)
        else:
            for col in COLUNAS_DIVIDAS:
                if col not in df_carregado.columns:
                    df_carregado[col] = ''
                    
            st.session_state.dividas = df_carregado
        
        st.session_state.dividas["Data_Vencimento"] = pd.to_datetime(st.session_state.dividas["Data_Vencimento"], errors='coerce')
        st.session_state.dividas["Data_Pagamento"] = pd.to_datetime(st.session_state.dividas["Data_Pagamento"], errors='coerce')
        st.session_state.dividas["Data_Criacao"] = pd.to_datetime(st.session_state.dividas["Data_Criacao"], errors='coerce')
        
    df_dividas = st.session_state.dividas
    
    # ----------------------------------------------------
    # Lógica de Salvamento Automático
    # ----------------------------------------------------
    if "hash_dividas" not in st.session_state:
        st.session_state.hash_dividas = hash_df(df_dividas)

    novo_hash = hash_df(df_dividas)
    if novo_hash != st.session_state.hash_dividas:
        if novo_hash != "error":
            df_to_save = df_dividas.copy()
            for col in ["Data_Vencimento", "Data_Pagamento", "Data_Criacao"]:
                 if col in df_to_save.columns:
                    df_to_save[col] = df_to_save[col].dt.strftime('%Y-%m-%d').fillna('')
            
            salvar_csv_no_github(
                GITHUB_TOKEN,
                GITHUB_REPO,
                PATH_DIVIDAS,
                df_to_save,
                GITHUB_BRANCH,
                mensagem="♻️ Alteração automática no rastreamento de dívidas"
            )
            st.session_state.hash_dividas = novo_hash
    
    
    # ----------------------------------------------------
    # 1. Lançamento de Nova Movimentação (Sidebar)
    # ----------------------------------------------------
    with st.sidebar:
        st.subheader("➕ Nova Movimentação")
        
        with st.form("form_nova_divida_sidebar"):
            
            tipo = st.radio("Tipo de Conta", ["A Pagar", "A Receber (Venda)"], horizontal=True, key="divida_tipo_sb")
            
            if tipo == "A Receber (Venda)":
                st.markdown("---")
                st.caption("Detalhes da Venda (A Receber)")
                
                # Campos para o produto da venda (multi-seleção simplificada)
                produto_vendido_selecionado = st.selectbox(
                    "📦 Selecione o Produto Vendido",
                    opcoes_produtos,
                    key="produto_venda_sb"
                )

                produtos_vendidos_list = []
                valor_total_venda = 0.0

                if produto_vendido_selecionado:
                    
                    # Extrai o ID
                    produto_id = produto_vendido_selecionado.split(' | ')[0]
                    
                    # Busca os dados do produto
                    produto_row = produtos_para_venda[produtos_para_venda["ID"] == produto_id].iloc[0]
                    
                    # Pega a quantidade disponível
                    qtd_disponivel = produto_row["Quantidade"]
                    
                    qtd_venda = st.number_input(
                        f"Qtd vendida (Estoque: {qtd_disponivel})", 
                        min_value=1, 
                        max_value=int(qtd_disponivel),
                        step=1, 
                        key="qtd_venda_sb"
                    )
                    
                    preco_vista = produto_row["PrecoVista"]
                    
                    valor_unitario = st.number_input(
                        f"Preço Unitário (Sugestão: R$ {preco_vista:.2f})",
                        min_value=0.01, 
                        format="%.2f",
                        value=float(preco_vista),
                        key="valor_unitario_venda_sb"
                    )
                    
                    subtotal = qtd_venda * valor_unitario
                    valor_total_venda = subtotal
                    
                    st.info(f"Subtotal do Item: R$ {subtotal:.2f}")

                    produtos_vendidos_list.append({
                        "id": produto_id,
                        "nome": produto_row["Nome"],
                        "quantidade": qtd_venda,
                        "valor_unitario": valor_unitario
                    })
                
                # O valor da dívida é o valor total da venda
                valor = valor_total_venda
                st.markdown(f"**Valor Total da Conta (R$): {valor:.2f}**")
                
            else: # A Pagar ou se não selecionou produto
                 valor = st.number_input("💸 Valor (R$)", min_value=0.01, format="%.2f", step=0.01, key="divida_valor_sb")
            
            # Campos comuns
            nome_cliente = st.text_input("👤 Nome do Cliente/Fornecedor", key="divida_nome_cliente_sb")
            descricao = st.text_area("📝 Descrição da Conta", key="divida_descricao_sb", height=50)
            
            data_vencimento = st.date_input(
                "📅 Data de Vencimento (Opcional)", 
                value=None, 
                min_value=datetime.date.today(), 
                key="divida_data_vencimento_sb"
            )
            
            adicionar = st.form_submit_button("✅ Lançar Conta como Pendente")
            
            if adicionar:
                if not nome_cliente.strip() or valor <= 0:
                    st.warning("⚠️ O nome do cliente/fornecedor e o valor são obrigatórios.")
                else:
                    novo_id = pd.Timestamp.now().strftime("%Y%m%d%H%M%S") + "_" + str(len(df_dividas) + 1)
                    
                    # Converte lista de produtos para JSON string para salvar no DataFrame
                    produtos_json = str(produtos_vendidos_list) 
                    
                    nova_divida = {
                        "ID": novo_id,
                        "Tipo": tipo.replace(" (Venda)", ""), # Salva apenas "A Receber"
                        "Valor": valor,
                        "Nome_Cliente": nome_cliente,
                        "Descricao": descricao,
                        "Data_Vencimento": pd.to_datetime(data_vencimento) if data_vencimento else pd.NaT,
                        "Status": "Pendente",
                        "Data_Pagamento": pd.NaT,
                        "Forma_Pagamento": "",
                        "Data_Criacao": pd.Timestamp.now(),
                        "Produtos_Vendidos": produtos_json
                    }
                    
                    # 1. Debitar o estoque se for uma venda
                    if tipo == "A Receber (Venda)" and produtos_vendidos_list:
                        # Assumindo que o produto principal é o primeiro item na lista (para simplificação)
                        item_venda = produtos_vendidos_list[0]
                        ajustar_estoque(item_venda["id"], item_venda["quantidade"], "debitar")
                        st.session_state.produtos = produtos # Força o update para o salvamento automático
                        st.success(f"Estoque de {item_venda['nome']} atualizado.")
                        
                    # 2. Adiciona a nova dívida ao DataFrame
                    st.session_state.dividas = pd.concat([df_dividas, pd.DataFrame([nova_divida])], ignore_index=True)
                    st.success(f"Conta '{nome_cliente}' de R$ {valor:.2f} lançada como Pendente!")
                    st.rerun()

    
    # ----------------------------------------------------
    # 2. Dívidas Pendentes (Lembrete e Liquidação)
    # ----------------------------------------------------
    
    df_pendentes = df_dividas[df_dividas["Status"] == "Pendente"].sort_values(by="Data_Vencimento", ascending=True)

    st.subheader("🔔 Contas Pendentes (Lembrete)")

    if df_pendentes.empty:
        st.info("🎉 Parabéns! Nenhuma conta pendente no momento.")
    else:
        # Alerta para dívidas vencidas
        hoje = pd.Timestamp(datetime.date.today())
        dividas_vencidas = df_pendentes[df_pendentes["Data_Vencimento"].notna() & (df_pendentes["Data_Vencimento"] < hoje)]
        
        if not dividas_vencidas.empty:
            st.error(f"🚨 **{len(dividas_vencidas)} contas VENCERAM!** Total: R$ {dividas_vencidas['Valor'].sum():.2f}")
            
        
        # Prepara a tabela de visualização
        df_display_pendentes = df_pendentes[[
            "Tipo", "Valor", "Nome_Cliente", "Data_Vencimento", "Descricao"
        ]].copy()
        
        # Formata colunas para exibição
        df_display_pendentes['Valor'] = df_display_pendentes['Valor'].apply(lambda x: f"R$ {x:.2f}")
        df_display_pendentes['Data_Vencimento'] = df_display_pendentes['Data_Vencimento'].dt.strftime('%d/%m/%Y').fillna('Sem Data')
        
        st.dataframe(
            df_display_pendentes.style.apply(lambda x: ['background-color: #ffdddd' if (x.name in dividas_vencidas.index) else '' for i in x], axis=1),
            use_container_width=True,
            hide_index=True
        )
        
        st.markdown("##### Liquidar Contas Pendentes")
        
        # Cria um seletor para escolher qual dívida liquidar
        opcoes_liquidar = df_pendentes.apply(
            lambda row: f"{row.Tipo} | R$ {row.Valor:.2f} | {row.Nome_Cliente}", axis=1
        ).tolist()
        
        if not opcoes_liquidar:
            st.info("Nenhuma conta para liquidar.")
            return

        divida_a_liquidar = st.selectbox("Selecione a conta para liquidação:", [""] + opcoes_liquidar, key="select_liquidar")
        
        if divida_a_liquidar:
            # Encontra o ID da dívida selecionada
            try:
                idx_selecionado = df_pendentes[
                    df_pendentes.apply(lambda row: f"{row.Tipo} | R$ {row.Valor:.2f} | {row.Nome_Cliente}" == divida_a_liquidar, axis=1)
                ].index[0]
            except IndexError:
                st.warning("Selecione uma dívida válida.")
                return
            
            # Formulário de Conclusão (Liquidação)
            with st.form("form_liquidar_divida"):
                st.info(f"Liquidando: {divida_a_liquidar}")
                
                data_pagamento = st.date_input(
                    "📅 Data de Pagamento/Recebimento", 
                    value=datetime.date.today(), 
                    max_value=datetime.date.today(), 
                    key="liquidar_data_pagamento"
                )
                
                forma_pagamento = st.selectbox(
                    "💳 Forma de Pagamento/Recebimento (Pix/Dinheiro, etc.)", 
                    ["Pix", "Dinheiro", "Cartão de Débito", "Cartão de Crédito", "Transferência Bancária", "Outro"],
                    key="liquidar_forma_pagamento"
                )
                
                confirmar_liquidacao = st.form_submit_button("✅ Confirmar Liquidação")
                
                if confirmar_liquidacao:
                    # 1. Localiza o ID original da dívida
                    original_id = df_pendentes.loc[idx_selecionado, "ID"]
                    
                    # 2. Encontra o índice correspondente no DataFrame principal (st.session_state.dividas)
                    idx_original = st.session_state.dividas[st.session_state.dividas["ID"] == original_id].index[0]
                    
                    # 3. Atualiza o DataFrame principal
                    st.session_state.dividas.loc[idx_original, "Status"] = "Concluído"
                    st.session_state.dividas.loc[idx_original, "Data_Pagamento"] = pd.to_datetime(data_pagamento)
                    st.session_state.dividas.loc[idx_original, "Forma_Pagamento"] = forma_pagamento
                    
                    st.success(f"✅ Conta liquidada com sucesso! Status alterado para 'Concluído'.")
                    st.rerun()

    st.markdown("---")

    # ----------------------------------------------------
    # 3. Dívidas Concluídas (Histórico) - com opção de exclusão
    # ----------------------------------------------------
    st.subheader("📄 Histórico de Contas Concluídas (Vendas/Pagamentos)")
    
    df_concluidas = df_dividas[df_dividas["Status"] == "Concluído"].sort_values(by="Data_Pagamento", ascending=False)
    
    if df_concluidas.empty:
        st.info("Nenhuma conta concluída no histórico.")
    else:
        # Adiciona botão de exclusão
        for idx, row in df_concluidas.iterrows():
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([1, 2, 2, 1])
                
                tipo = row['Tipo']
                valor = row['Valor']
                cliente = row['Nome_Cliente']
                data_pag = row['Data_Pagamento'].strftime('%d/%m/%Y') if pd.notna(row['Data_Pagamento']) else 'N/A'
                
                c1.markdown(f"**{tipo}**")
                c2.markdown(f"**R$ {valor:.2f}** ({row['Forma_Pagamento']})")
                c3.markdown(f"**Cliente/Fornec.:** {cliente} ({data_pag})")
                
                # Botão de exclusão
                if c4.button("🗑️ Excluir Venda/Conta", key=f"excluir_concluido_{row['ID']}"):
                    
                    # Lógica de Reversão de Estoque
                    if row['Tipo'] == "A Receber" and str(row.get("Produtos_Vendidos", "")).strip():
                        try:
                            produtos_vendidos = ast.literal_eval(row['Produtos_Vendidos'])
                            if produtos_vendidos and isinstance(produtos_vendidos, list):
                                # Reverte o estoque do produto vendido (assume o primeiro item para simplificação)
                                item = produtos_vendidos[0]
                                ajustado = ajustar_estoque(item["id"], item["quantidade"], "creditar")
                                if ajustado:
                                    st.warning(f"🔄 Estoque de {item['nome']} (+{item['quantidade']}) creditado.")
                                
                        except Exception as e:
                            st.error(f"Erro ao reverter estoque: {e}")
                            
                    # Remove a linha do DataFrame principal
                    st.session_state.dividas = st.session_state.dividas.drop(index=idx).reset_index(drop=True)
                    st.success(f"✅ Conta ID {row['ID']} excluída e estoque revertido (se aplicável).")
                    st.rerun()

        st.markdown("---")
        st.markdown(f"Total de Contas Concluídas: **{len(df_concluidas)}**")
        
        baixar_csv_aba(
             df_concluidas[[c for c in COLUNAS_DIVIDAS if c in df_concluidas.columns]].fillna(''), 
             PATH_DIVIDAS, 
             key_suffix="dividas_historico"
        )

# FIM DA FUNÇÃO livro_caixa()


# =====================================
# ROTEAMENTO PRINCIPAL (Abas no Topo)
# =====================================

# O roteamento lateral antigo foi substituído por abas principais no topo
main_tab_select = st.sidebar.radio(
    "Escolha a página principal:",
    ["Livro Caixa", "Produtos", "Precificação", "Papelaria"],
    key='main_page_select_widget'
)

if main_tab_select == "Livro Caixa":
    livro_caixa()
elif main_tab_select == "Produtos":
    gestao_produtos()
elif main_tab_select == "Precificação":
    precificacao_completa()
elif main_tab_select == "Papelaria":
    papelaria_aba()
