import pandas as pd
import streamlit as st
import requests
import base64
from io import StringIO
from datetime import date

# --- Configurações (Ajuste para suas credenciais do secrets) ---
OWNER = st.secrets.get("REPO_OWNER", "ribeiromendes5014-design")
REPO_NAME = st.secrets.get("REPO_NAME", "fluxo")
BRANCH = st.secrets.get("BRANCH", "main")
TOKEN = st.secrets.get("GITHUB_TOKEN", None)
ARQ_PROMOCOES_MARKETING = "marketing_promocoes.csv"
HEADERS = {"Authorization": f"token {TOKEN}", "Accept": "application/vnd.github.v3+json"}
# ---------------------------------------------------------------

COLUNAS_PROMOCOES_MARKETING = ["ID_PROMO", "DATA_ENVIO", "TEMPLATE_NOME", "FOTO_URL", "TEXTO_VAR1", "TEXTO_VAR2", "STATUS"]

@st.cache_data(show_spinner="Carregando agenda de marketing...")
def carregar_agenda_marketing():
    """Carrega a agenda de promoções de marketing do GitHub."""
    url_raw = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/{ARQ_PROMOCOES_MARKETING}"
    
    try:
        response = requests.get(url_raw)
        if response.status_code == 404:
             return pd.DataFrame(columns=COLUNAS_PROMOCOES_MARKETING)
             
        response.raise_for_status()
        
        if not response.text.strip():
            return pd.DataFrame(columns=COLUNAS_PROMOCOES_MARKETING)
            
        df = pd.read_csv(StringIO(response.text), dtype=str)
        # Garante que todas as colunas existem
        for col in COLUNAS_PROMOCOES_MARKETING:
            if col not in df.columns:
                df[col] = ''
        return df
    
    except Exception as e:
        st.error(f"Erro ao carregar agenda de promoções: {e}")
        return pd.DataFrame(columns=COLUNAS_PROMOCOES_MARKETING)

def salvar_agenda_marketing(df_novo: pd.DataFrame, commit_message: str):
    """Salva a agenda de marketing atualizada de volta no GitHub."""
    if not TOKEN:
        st.error("Erro: Token do GitHub não configurado para salvar.")
        return False
        
    api_url = f"https://api.github.com/repos/{OWNER}/{REPO_NAME}/contents/{ARQ_PROMOCOES_MARKETING}"
    
    try:
        # 1. Obter o SHA do arquivo atual (necessário para atualização)
        response = requests.get(api_url, headers=HEADERS)
        sha = response.json().get('sha') if response.status_code == 200 else None
        
        # 2. Preparar o novo conteúdo
        csv_content = df_novo.to_csv(index=False, encoding="utf-8-sig")
        content_base64 = base64.b64encode(csv_content.encode('utf-8-sig')).decode('utf-8')
        
        payload = {
            "message": commit_message, 
            "content": content_base64, 
            "branch": BRANCH
        }
        if sha: payload["sha"] = sha 
        
        # 3. Fazer o commit
        put_response = requests.put(api_url, headers=HEADERS, json=payload)
        
        if put_response.status_code in [200, 201]:
            carregar_agenda_marketing.clear()
            return True
        else:
            st.error(f"Falha no Commit: {put_response.json().get('message', 'Erro desconhecido')}")
            return False
            
    except Exception as e:
        st.error(f"Erro ao tentar salvar a agenda no GitHub: {e}")
        return False