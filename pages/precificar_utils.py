# precificar_utils.py

import streamlit as st
import pandas as pd
import requests
from fpdf import FPDF
from io import BytesIO, StringIO
import base64
import hashlib
import ast
import numpy as np # Necessário para pd.util.hash_pandas_object


# ===============================
# CONSTANTES GLOBAIS
# ===============================

# Configurações Telegram (Mantenha as constantes de URL/IDs aqui)
HARDCODED_TELEGRAM_TOKEN = "8412132908:AAG8N_vFzkpVNX-WN3bwT0Vl3H41Q-9Rfw4"
TELEGRAM_CHAT_ID = "-1003030758192"
TOPICO_ID = 28 

# Definições de colunas base
INSUMOS_BASE_COLS_GLOBAL = ["Nome", "Categoria", "Unidade", "Preço Unitário (R$)"]
PRODUTOS_BASE_COLS_GLOBAL = ["Produto", "Custo Total", "Preço à Vista", "Preço no Cartão", "Margem (%)"]
COLUNAS_CAMPOS = ["Campo", "Aplicação", "Tipo", "Opções"]


# ===============================
# FUNÇÕES AUXILIARES (COLE AQUI)
# ===============================

def gerar_pdf(df: pd.DataFrame) -> BytesIO:
    """Gera um PDF formatado a partir do DataFrame de precificação."""
    # Cole o corpo da função gerar_pdf() aqui
    pdf = FPDF()
    # ... (cole o restante do código da função)
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Relatório de Precificação", 0, 1, "C")
    pdf.ln(5)

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

    pdf.set_font("Arial", "B", 10)
    for col_name, width in zip(pdf_cols, current_widths):
        pdf.cell(width, 10, col_name, border=1, align='C')
    pdf.ln()

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
    
# Cole as outras funções auxiliares aqui:
# 1. enviar_pdf_telegram
def enviar_pdf_telegram(pdf_bytesio, df_produtos: pd.DataFrame, thread_id=None):
    """Envia o arquivo PDF e a primeira imagem (se existir) em mensagens separadas para o Telegram."""
    
    token = st.secrets.get("telegram_token", HARDCODED_TELEGRAM_TOKEN)
    image_url = None
    image_caption = "Relatório de Precificação"
    
    if not df_produtos.empty and "Imagem_URL" in df_produtos.columns:
        first_row = df_produtos.iloc[0]
        url = first_row.get("Imagem_URL")
        produto = first_row.get("Produto", "Produto")
        
        if isinstance(url, str) and url.startswith("http"):
            image_url = url
            image_caption = f"📦 Produto Principal: {produto}\n\n[Relatório de Precificação em anexo]"

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
    
    if image_url:
        try:
            url_photo = f"https://api.telegram.org/bot{token}/sendPhoto"
            
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
            
# 2. exibir_resultados
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
                img_to_display = imagens_dict.get(row.get("Produto"))

                if img_to_display is None and row.get("Imagem") is not None and isinstance(row.get("Imagem"), bytes):
                    try:
                        img_to_display = row.get("Imagem")
                    except Exception:
                        pass

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

# 3. processar_dataframe
def processar_dataframe(df: pd.DataFrame, frete_total: float, custos_extras: float,
                        modo_margem: str, margem_fixa: float) -> pd.DataFrame:
    """Processa o DataFrame, aplica rateio, margem e calcula os preços finais."""
    if df.empty:
        return pd.DataFrame(columns=[
            "Produto", "Qtd", "Custo Unitário", "Custos Extras Produto", 
            "Custo Total Unitário", "Margem (%)", "Preço à Vista", "Preço no Cartão"
        ])

    df = df.copy()

    for col in ["Qtd", "Custo Unitário", "Margem (%)", "Custos Extras Produto"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
        elif col not in df.columns:
            df[col] = 0.0
            
    qtd_total = df["Qtd"].sum()
    rateio_unitario = 0
    if qtd_total > 0:
        rateio_unitario = (frete_total + custos_extras) / qtd_total

    if frete_total > 0 or custos_extras > 0:
        pass
    else:
        pass

    df["Custo Total Unitário"] = df["Custo Unitário"] + df["Custos Extras Produto"]

    if "Margem (%)" not in df.columns:
        df["Margem (%)"] = margem_fixa
    
    df["Margem (%)"] = df["Margem (%)"].apply(lambda x: x if pd.notna(x) else margem_fixa)

    df["Preço à Vista"] = df["Custo Total Unitário"] * (1 + df["Margem (%)"] / 100)
    df["Preço no Cartão"] = df["Preço à Vista"] / 0.8872

    cols_to_keep = [
        "Produto", "Qtd", "Custo Unitário", "Custos Extras Produto", 
        "Custo Total Unitário", "Margem (%)", "Preço à Vista", "Preço no Cartão", 
        "Imagem", "Imagem_URL"
    ]
    
    df_final = df[[col for col in cols_to_keep if col in df.columns]]

    return df_final
    
# 4. load_csv_github
def load_csv_github(url: str) -> pd.DataFrame:
    """Carrega um arquivo CSV diretamente do GitHub."""
    try:
        response = requests.get(url)
        response.raise_for_status()
        df = pd.read_csv(StringIO(response.text))
        return df
    except Exception as e:
        st.error(f"Erro ao carregar CSV do GitHub: {e}")
        return pd.DataFrame()
        
# 5. extrair_produtos_pdf
def extrair_produtos_pdf(pdf_file) -> list:
    """Função mock para extração de produtos de PDF."""
    st.warning("Função extrair_produtos_pdf ainda não implementada. Use o carregamento manual ou de CSV.")
    return []

# 6. baixar_csv_aba
def baixar_csv_aba(df, nome_arquivo, key_suffix=""):
    """Cria um botão de download para o DataFrame."""
    csv = df.to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        f"⬇️ Baixar {nome_arquivo}",
        data=csv,
        file_name=nome_arquivo,
        mime="text/csv",
        key=f"download_button_{nome_arquivo.replace('.', '_')}_{key_suffix}"
    )

# 7. _opcoes_para_lista
def _opcoes_para_lista(opcoes_str):
    """Converte string de opções separadas por vírgula em lista."""
    if pd.isna(opcoes_str) or not str(opcoes_str).strip():
        return []
    return [o.strip() for o in str(opcoes_str).split(",") if o.strip()]

# 8. hash_df
def hash_df(df):
    """Gera um hash para o DataFrame para detecção de mudanças."""
    df_temp = df.copy() 
    
    try:
        # Usa o hash_pandas_object do Pandas para garantir consistência
        return hashlib.md5(pd.util.hash_pandas_object(df_temp.drop(columns=["Imagem"], errors='ignore'), index=False).values).hexdigest()
    except Exception as e:
        for col in df_temp.select_dtypes(include=['object']).columns:
             df_temp[col] = df_temp[col].astype(str)
        try:
             return hashlib.md5(pd.util.hash_pandas_object(df_temp.drop(columns=["Imagem"], errors='ignore'), index=False).values).hexdigest()
        except Exception as inner_e:
             st.error(f"Erro interno no hash do DataFrame: {inner_e}")
             return "error"
             

# 9. salvar_csv_no_github
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
        pass
    else:
        st.error(f"❌ Erro ao salvar `{path}`: {r2.text}")

# 10. col_defs_para
def col_defs_para(aplicacao: str):
    """Filtra as definições de colunas extras por aplicação."""
    # Como as definições de campos extras não foram movidas para 'st.session_state.campos' 
    # neste contexto, esta função precisa de um ajuste.
    # Assumindo que você usará esta lógica apenas para a parte 'papelaria' que você não incluiu,
    # vamos manter a dependência do st.session_state.campos.
    if "campos" not in st.session_state or st.session_state.campos.empty:
        return pd.DataFrame(columns=COLUNAS_CAMPOS)
    df = st.session_state.campos
    return df[(df["Aplicação"] == aplicacao) | (df["Aplicação"] == "Ambos")].copy()

# 11. garantir_colunas_extras
def garantir_colunas_extras(df: pd.DataFrame, aplicacao: str) -> pd.DataFrame:
    """Adiciona colunas extras ao DataFrame se ainda não existirem."""
    defs = col_defs_para(aplicacao)
    for campo in defs["Campo"].tolist():
        if campo not in df.columns:
            df[campo] = ""
    return df

# 12. render_input_por_tipo
def render_input_por_tipo(label, tipo, opcoes, valor_padrao=None, key=None):
    """Renderiza um widget Streamlit baseado no tipo de campo definido."""
    if tipo == "Número":
        valor = float(valor_padrao) if (valor_padrao is not None and str(valor_padrao).strip() != "") else 0.0
        return st.number_input(label, min_value=0.0, format="%.2f", value=valor, key=key)
    elif tipo == "Seleção":
        lista = _opcoes_para_lista(opcoes)
        valor_display = str(valor_padrao) if valor_padrao is not None and pd.notna(valor_padrao) else ""
        
        if valor_display not in lista and valor_display != "":
            lista = [valor_display] + [o for o in lista if o != valor_display]
        elif valor_display == "" and lista:
            valor_display = lista[0]
            
        try:
            index_padrao = lista.index(valor_display) if valor_display in lista else 0
        except ValueError:
            index_padrao = 0
            
        return st.selectbox(label, options=lista, index=index_padrao, key=key)
    else:
        return st.text_input(label, value=str(valor_padrao) if valor_padrao is not None else "", key=key)