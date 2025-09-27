import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
import requests
from io import StringIO
import io
import json
import hashlib
import ast
import plotly.express as px
import base64 # <-- CORREÇÃO: Módulo base64 importado para a função salvar_csv_no_github

# ==================== CONFIGURAÇÕES GLOBAIS E CONSTANTES ====================

# Configurações de Repositório (Assumidas ou carregadas de st.secrets)
# **NOTA:** O código original usava secrets para TOKEN, OWNER, etc. Recomendo manter essa prática.
# Se as variáveis não estiverem nos secrets, o salvamento falhará.
try:
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
    GITHUB_REPO = st.secrets["REPO_OWNER"] + "/" + st.secrets["REPO_NAME"] # Assumindo que REPO_NAME e OWNER estão em secrets
    GITHUB_BRANCH = st.secrets.get("BRANCH", "main")
except KeyError:
    # Fallback para execução, mas o salvamento no GitHub NÃO funcionará sem as chaves corretas.
    GITHUB_TOKEN = "TOKEN_FICTICIO"
    GITHUB_REPO = "user/repo_default"
    GITHUB_BRANCH = "main"

URL_BASE_REPOS = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/" 

# Caminhos dos arquivos
PATH_DIVIDAS = "contas_a_pagar_receber.csv"
ARQ_DIVIDAS = URL_BASE_REPOS + PATH_DIVIDAS
ARQ_PRODUTOS = "produtos_estoque.csv"
URL_PRODUTOS = URL_BASE_REPOS + ARQ_PRODUTOS

# Mensagens de Commit
COMMIT_MESSAGE_DIVIDA = "Atualização automática no rastreamento de dívidas"
COMMIT_MESSAGE_PROD = "Atualização automática de estoque/produtos"

# Constantes para Produto
FATOR_CARTAO = 0.8872 # 1 - Taxa de 11.28% para cálculo do Preço no Cartão


# ===============================
# FUNÇÕES DE PERSISTÊNCIA E AUXILIARES
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
    # Simulação de leitura de código.
    return ["1234567890123"] 

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
        return hashlib.md5(pd.util.hash_pandas_object(df_temp, index=False).values).hexdigest()
    except Exception:
        return "error" 
             
def load_csv_github(url: str) -> pd.DataFrame:
    """Carrega um arquivo CSV diretamente do GitHub."""
    try:
        response = requests.get(url)
        response.raise_for_status()
        df = pd.read_csv(StringIO(response.text), dtype=str)
        return df
    except Exception:
        return pd.DataFrame()

def salvar_csv_no_github(token, repo, path, dataframe, branch="main", mensagem="Atualização via app"):
    """Salva o DataFrame como CSV no GitHub via API."""
    from requests import get, put
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    
    # 1. Prepara dados para salvar (garante que datas são strings)
    df_to_save = dataframe.copy()
    for col in df_to_save.select_dtypes(include=['datetime64[ns]']).columns:
        df_to_save[col] = df_to_save[col].dt.strftime('%Y-%m-%d').fillna('')
        
    conteudo = df_to_save.to_csv(index=False)
    # Linha que gerou o erro corrigida pelo import do módulo base64 no topo
    conteudo_b64 = base64.b64encode(conteudo.encode()).decode() 
    headers = {"Authorization": f"token {token}"}
    r = get(url, headers=headers)
    sha = r.json().get("sha") if r.status_code == 200 else None
    payload = {"message": mensagem, "content": conteudo_b64, "branch": branch}
    if sha: payload["sha"] = sha
    r2 = put(url, headers=headers, json=payload)
    if r2.status_code in (200, 201):
        st.success(f"✅ Arquivo `{path}` atualizado no GitHub!")
        return True
    else:
        st.error(f"❌ Erro ao salvar `{path}`: {r2.text}")
        return False
        
# Função unificada de persistência
def save_data_github(df, path, commit_message):
    """Encapsula a lógica de persistência e hash."""
    repo = GITHUB_REPO
    token = GITHUB_TOKEN
    
    # Gerar hash antes de salvar
    novo_hash = hash_df(df)
    
    # Determinar a chave de hash no session_state com base no path
    hash_key = f"hash_{path.replace('.', '_')}"
    
    if hash_key not in st.session_state:
        st.session_state[hash_key] = "initial"

    if novo_hash != st.session_state[hash_key] and novo_hash != "error":
        if salvar_csv_no_github(token, repo, path, df, GITHUB_BRANCH, commit_message):
            st.session_state[hash_key] = novo_hash
            return True
    return False

# ==============================================================================
# LÓGICA DE ESTOQUE (USADA PELO LIVRO CAIXA)
# ==============================================================================

def inicializar_produtos():
    """Carrega ou inicializa o DataFrame de produtos."""
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
            
            # Garante tipos corretos
            df_carregado["Quantidade"] = pd.to_numeric(df_carregado["Quantidade"], errors='coerce').fillna(0).astype(int)
            df_carregado["PrecoCusto"] = pd.to_numeric(df_carregado["PrecoCusto"], errors='coerce').fillna(0.0)
            df_carregado["PrecoVista"] = pd.to_numeric(df_carregado["PrecoVista"], errors='coerce').fillna(0.0)
            df_carregado["PrecoCartao"] = pd.to_numeric(df_carregado["PrecoCartao"], errors='coerce').fillna(0.0)
            
            st.session_state.produtos = df_carregado
            
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

# ==============================================================================
# FUNÇÃO DA PÁGINA: GESTÃO DE PRODUTOS (ESTOQUE)
# ==============================================================================

def gestao_produtos():
    
    # Inicializa ou carrega o estado de produtos
    produtos = inicializar_produtos()
    
    # Título da Página
    st.header("📦 Gestão de Produtos e Estoque")

    # Lógica de Salvamento Automático
    save_data_github(produtos, ARQ_PRODUTOS, COMMIT_MESSAGE_PROD)


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
                st.file_uploader("📷 Enviar Foto", type=["png", "jpg", "jpeg"], key="cad_foto") # Mantido, mas não usado
                
                codigo_barras = st.text_input("Código de Barras (Pai/Simples)", value=st.session_state["codigo_barras"], key="cad_cb")

                # --- Escanear com câmera (Produto Simples/Pai) ---
                foto_codigo = st.camera_input("📷 Escanear código de barras / QR Code", key="cad_cam")
                if foto_codigo is not None:
                    imagem_bytes = foto_codigo.getvalue()
                    codigos_lidos = ler_codigo_barras_api(imagem_bytes)
                    if codigos_lidos:
                        st.session_state["codigo_barras"] = codigos_lidos[0]
                        st.success(f"Código lido: {st.session_state['codigo_barras']}")
                        st.rerun() 
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
                    var_preco_custo = var_c3.text_input(f"Preço de custo variação {i+1}", value="0,00", key=f"var_pc_{i}")
                    var_preco_vista = var_c4.text_input(f"Preço à vista variação {i+1}", value="0,00", key=f"var_pv_{i}")
                    
                    var_cb_c1, var_cb_c2, var_cb_c3 = st.columns([2, 1, 1])

                    with var_cb_c1:
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
                    
                    foto_lida = var_foto_upload or var_foto_cam
                    if foto_lida:
                        imagem_bytes = foto_lida.getvalue() 
                        codigos_lidos = ler_codigo_barras_api(imagem_bytes)
                        if codigos_lidos:
                            st.session_state.cb_grade_lidos[f"var_cb_{i}"] = codigos_lidos[0]
                            st.success(f"CB Variação {i+1} lido: {codigos_lidos[0]}")
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
                        "PaiID": None 
                    }
                    produtos = pd.concat([produtos, pd.DataFrame([novo])], ignore_index=True)
                else:
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

                    for var in variações:
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
                if 'cb_grade_lidos' in st.session_state:
                    del st.session_state.cb_grade_lidos 
                if 'codigo_barras' in st.session_state:
                    del st.session_state.codigo_barras 
                    
                # Força o salvamento e rerun
                save_data_github(produtos, ARQ_PRODUTOS, "Novo produto cadastrado")
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
                        produtos_filtrados = produtos[produtos["PrecoVista"].astype(float) == valor]
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
            produtos_pai = produtos_filtrados[produtos_filtrados["PaiID"].isnull()]
            produtos_filho = produtos_filtrados[produtos_filtrados["PaiID"].notnull()]

            for index, pai in produtos_pai.iterrows():
                with st.container(border=True):
                    c = st.columns([1, 3, 1, 1, 1])
                    if str(pai["FotoURL"]).strip():
                        try:
                            c[0].image(pai["FotoURL"], width=80)
                        except Exception:
                            c[0].write("Sem imagem")
                    else:
                        c[0].write("—")

                    cb = f' • CB: {pai["CodigoBarras"]}' if str(pai.get("CodigoBarras", "")).strip() else ""
                    c[1].markdown(f"**{pai['Nome']}** \nMarca: {pai['Marca']} \nCat: {pai['Categoria']}{cb}")
                    
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
                            # Apaga o pai e os filhos
                            produtos = produtos[produtos["ID"] != str(eid)]
                            produtos = produtos[produtos["PaiID"] != str(eid)]

                            st.session_state["produtos"] = produtos
                            save_data_github(produtos, ARQ_PRODUTOS, "Atualizando produtos")
                            st.warning(f"Produto {pai['Nome']} e suas variações excluídas!")
                            st.rerun()

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
                                        save_data_github(produtos, ARQ_PRODUTOS, "Atualizando produtos")
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
                            vdata = datetime.strptime(str(row["Validade"] or date.today()), "%Y-%m-%d").date()
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
                                st.success(f"Código lido: {novo_cb}")

                    col_save, col_cancel = st.columns([1, 1])
                    with col_save:
                        if st.button("Salvar alterações", key=f"save_{eid}"):
                            
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
                            save_data_github(produtos, ARQ_PRODUTOS, "Atualizando produto")
                            del st.session_state["edit_prod"]
                            st.rerun()
                            
                    with col_cancel:
                        if st.button("Cancelar edição", key=f"cancel_{eid}"):
                            del st.session_state["edit_prod"]
                            st.rerun()

# ==============================================================================
# FUNÇÃO DA PÁGINA: LIVRO CAIXA (DÍVIDAS/MOVIMENTAÇÕES)
# ==============================================================================

def livro_caixa():
    st.title("💰 Livro Caixa - Contas e Vendas")

    # --- Inicialização e Constantes Locais ---
    produtos = inicializar_produtos()
    
    COLUNAS_DIVIDAS = [
        "ID", "Tipo", "Valor", "Nome_Cliente", "Descricao", 
        "Data_Vencimento", "Status", "Data_Pagamento", "Forma_Pagamento",
        "Data_Criacao", "Produtos_Vendidos", "Loja", "Categoria" # Adicionado Loja e Categoria aqui para a carga inicial
    ]
    
    LOJAS_DISPONIVEIS = ["Doce&bella", "Papelaria", "Fotografia", "Outro"]
    CATEGORIAS_SAIDA = ["Aluguel", "Salários/Pessoal", "Marketing/Publicidade", "Fornecedores/Matéria Prima", "Despesas Fixas", "Impostos/Taxas", "Outro/Diversos", "Não Categorizado"]
    FORMAS_PAGAMENTO = ["Dinheiro", "Cartão", "PIX", "Transferência", "Outro"]

    # --- Lógica de Carregamento/Persistência das Dívidas ---
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
    
    # ------------------------------------------------------------------------------------------------------
    # PROBLEMA: save_data_github(df_dividas, PATH_DIVIDAS, COMMIT_MESSAGE_DIVIDA)
    # A linha acima estava chamando a função de persistência antes de ter a garantia de que o df está 
    # totalmente carregado e processado, e causaria um NameError se o hash falhasse na primeira execução.
    # Vou mantê-la no final do bloco de inicialização, após a carga.
    # ------------------------------------------------------------------------------------------------------

    # --- Preparação dos Produtos para a Venda ---
    produtos_para_venda = produtos[produtos["PaiID"].notna() | produtos["PaiID"].isnull()]
    
    # Adiciona ID ao nome para facilitar o parse
    opcoes_produtos = [""] + produtos_para_venda.apply(
        lambda row: f"{row.ID} | {row.Nome} ({row.Marca}) | Estoque: {row.Quantidade}", axis=1
    ).tolist()
    
    # Função para extrair ID do produto
    def extrair_id(opcoes_str):
        return opcoes_str.split(' | ')[0] if ' | ' in opcoes_str else None

    # --- Lógica de Processamento de Exibição (Simples) ---
    def processar_dividas_para_exibicao(df):
        if df.empty:
            return pd.DataFrame(columns=['ID', 'Tipo', 'Valor', 'Nome_Cliente', 'Data_Vencimento', 'Status', 'Data_Pagamento', 'Cor', 'Data_Vencimento_dt', 'Vencida', 'Data_Criacao'])
        
        df_proc = df.copy()
        
        # Garante que as colunas existem antes de tentar acessá-las
        for col in ['Tipo', 'Valor', 'Status', 'Data_Vencimento', 'Data_Criacao']:
            if col not in df_proc.columns:
                 df_proc[col] = '' # Adiciona colunas ausentes
                 
        df_proc['Cor'] = df_proc.apply(lambda row: 'green' if row['Tipo'] == 'A Receber' else 'red', axis=1)
        df_proc['Valor'] = pd.to_numeric(df_proc['Valor'], errors='coerce').fillna(0.0)
        
        hoje = datetime.now().date()
        df_proc['Data_Vencimento_dt'] = pd.to_datetime(df_proc['Data_Vencimento'], errors='coerce').dt.date
        df_proc['Vencida'] = (df_proc['Status'] == 'Pendente') & (df_proc['Data_Vencimento_dt'].notna()) & (df_proc['Data_Vencimento_dt'] <= hoje)
        
        # Converte Data_Criacao para datetime.date para ordenação se for string
        df_proc['Data_Criacao'] = pd.to_datetime(df_proc['Data_Criacao'], errors='coerce')

        return df_proc.sort_values(by="Data_Criacao", ascending=False).reset_index(drop=True)

    df_exibicao = processar_dividas_para_exibicao(df_dividas)

    # =================================================================
    # SIDEBAR: Lançamento de Nova Movimentação
    # =================================================================
    with st.sidebar:
        st.subheader("➕ Nova Movimentação")
        
        # Inicialização do estado de produtos da venda (se não existir)
        if "venda_produtos_list" not in st.session_state:
            st.session_state.venda_produtos_list = []
        
        with st.form("form_nova_divida_sidebar"):
            
            tipo = st.radio("Tipo de Conta", ["A Pagar", "A Receber (Venda)"], horizontal=True, key="divida_tipo_sb")
            
            produtos_vendidos_list = []
            valor_total_venda = 0.0

            if tipo == "A Receber (Venda)":
                st.markdown("---")
                st.caption("Detalhes da Venda")
                
                # --- Adicionar Produto à Lista de Venda ---
                with st.expander("🛍️ Adicionar Produto à Venda", expanded=False):
                    produto_selecionado = st.selectbox(
                        "Selecione o Produto",
                        opcoes_produtos,
                        key="produto_venda_selecao"
                    )

                    if produto_selecionado:
                        produto_id = extrair_id(produto_selecionado)
                        produto_row = produtos_para_venda[produtos_para_venda["ID"] == produto_id]
                        
                        if not produto_row.empty:
                            produto_row = produto_row.iloc[0]
                            qtd_disponivel = produto_row["Quantidade"]
                            
                            qtd_venda = st.number_input(
                                f"Qtd (Estoque: {qtd_disponivel})", 
                                min_value=1, 
                                max_value=int(qtd_disponivel) if qtd_disponivel >= 1 else 1,
                                step=1, 
                                key="qtd_venda_sb"
                            )
                            
                            preco_vista = produto_row["PrecoVista"]
                            valor_unitario = st.number_input(
                                f"Preço Unitário (Sug: R$ {preco_vista:.2f})",
                                min_value=0.01, 
                                format="%.2f",
                                value=float(preco_vista),
                                key="valor_unitario_venda_sb"
                            )
                            
                            if st.button("Adicionar Item à Lista", use_container_width=True):
                                if qtd_venda > 0 and qtd_venda <= qtd_disponivel:
                                    item_data = {
                                        "id": produto_id,
                                        "Produto": produto_row["Nome"],
                                        "Quantidade": qtd_venda,
                                        "Preço Unitário": valor_unitario,
                                        "Custo Unitário": produto_row["PrecoCusto"],
                                    }
                                    st.session_state.venda_produtos_list.append(item_data)
                                    st.success(f"Item '{produto_row['Nome']}' adicionado.")
                                    # Reinicia o formulário de venda (ou a seleção)
                                    st.experimental_rerun()
                                else:
                                    st.error("Quantidade inválida ou superior ao estoque.")
                
                # --- Lista de Produtos Adicionados ---
                if st.session_state.venda_produtos_list:
                    df_venda_items = pd.DataFrame(st.session_state.venda_produtos_list)
                    valor_total_venda = (df_venda_items['Quantidade'] * df_venda_items['Preço Unitário']).sum()
                    produtos_vendidos_list = st.session_state.venda_produtos_list # Prepara para salvar
                    
                    st.sidebar.dataframe(
                        df_venda_items[['Produto', 'Quantidade', 'Preço Unitário']],
                        hide_index=True,
                        use_container_width=True,
                        column_config={"Preço Unitário": st.column_config.NumberColumn(format="R$ %.2f")}
                    )
                    
                    if st.button("Limpar Venda Atual", key="limpar_venda_sb"):
                        st.session_state.venda_produtos_list = []
                        st.rerun()

                valor = st.number_input(
                    "Valor Total (R$)", 
                    value=valor_total_venda,
                    min_value=0.01, 
                    format="%.2f",
                    disabled=valor_total_venda > 0.01, # Desabilita se houver itens na lista
                    key="divida_valor_venda_sb"
                )
                produtos_vendidos_json = json.dumps(produtos_vendidos_list)

            else: # Tipo A Pagar
                valor = st.number_input("💸 Valor (R$)", min_value=0.01, format="%.2f", step=0.01, key="divida_valor_sb")
                produtos_vendidos_json = ""
                
                st.sidebar.markdown("#### ⚙️ Centro de Custo (Saída)")
                categoria_selecionada = st.selectbox("Categoria de Gasto", 
                                                 CATEGORIAS_SAIDA, 
                                                 key="categoria_saida_sb")
                if categoria_selecionada == "Outro/Diversos":
                    descricao_personalizada = st.text_input("Especifique o Gasto", key="input_custom_category_sb")
                    if descricao_personalizada:
                        categoria_selecionada = f"Outro: {descricao_personalizada}"
            
            # Campos comuns
            loja = st.selectbox("Loja Responsável", LOJAS_DISPONIVEIS, key="loja_sb")
            nome_cliente = st.text_input("👤 Nome do Cliente/Fornecedor/Descrição", key="divida_nome_cliente_sb")
            descricao = st.text_area("📝 Descrição Adicional", key="divida_descricao_sb", height=50)
            
            st.markdown("#### 🔄 Status")
            status_selecionado = st.radio("Status", ["Pendente", "Realizada"], horizontal=True, index=0, key="status_sb")
            
            data_vencimento = st.date_input(
                "📅 Data de Vencimento (Pendente)", 
                value=None, 
                min_value=datetime.now().date(), 
                key="divida_data_vencimento_sb"
            )
            
            data_pagamento_real = None
            forma_pagamento_real = ""
            if status_selecionado == "Realizada":
                data_pagamento_real = st.date_input("Data de Pagamento Real", value=datetime.now().date(), key="data_pagamento_real_sb")
                forma_pagamento_real = st.selectbox("Forma de Pagamento", FORMAS_PAGAMENTO, key="forma_pagamento_real_sb")

            adicionar = st.form_submit_button("✅ Lançar Conta")
            
            if adicionar:
                if not nome_cliente.strip() or valor <= 0:
                    st.warning("⚠️ O nome/descrição e o valor são obrigatórios.")
                else:
                    novo_id = pd.Timestamp.now().strftime("%Y%m%d%H%M%S") + "_" + str(len(df_dividas) + 1)
                    
                    nova_divida = {
                        "ID": novo_id,
                        "Tipo": tipo.replace(" (Venda)", ""),
                        "Valor": valor,
                        "Nome_Cliente": nome_cliente,
                        "Descricao": descricao,
                        "Data_Vencimento": pd.to_datetime(data_vencimento) if data_vencimento else pd.NaT,
                        "Status": status_selecionado,
                        "Data_Pagamento": pd.to_datetime(data_pagamento_real) if data_pagamento_real else pd.NaT,
                        "Forma_Pagamento": forma_pagamento_real,
                        "Data_Criacao": pd.Timestamp.now(),
                        "Produtos_Vendidos": produtos_vendidos_json,
                        "Loja": loja,
                        "Categoria": categoria_selecionada if tipo == "A Pagar" else "",
                    }
                    
                    # 1. Debitar o estoque se for uma VENDA REALIZADA
                    if tipo == "A Receber (Venda)" and status_selecionado == "Realizada" and produtos_vendidos_list:
                        for item in produtos_vendidos_list:
                            ajustar_estoque(item["id"], item["Quantidade"], "debitar")
                        # Força o salvamento dos produtos
                        save_data_github(st.session_state.produtos, ARQ_PRODUTOS, "Débito de estoque por nova venda")
                        st.success("Estoque debitado.")
                        
                    # 2. Adiciona a nova dívida ao DataFrame
                    st.session_state.dividas = pd.concat([df_dividas, pd.DataFrame([nova_divida])], ignore_index=True)
                    st.session_state.venda_produtos_list = [] # Limpa a lista de itens da venda
                    
                    # Força o salvamento e rerun
                    save_data_github(st.session_state.dividas, PATH_DIVIDAS, "Nova movimentação lançada")
                    st.rerun()

    
    # =================================================================
    # CORPO PRINCIPAL: Resumo e Tabelas
    # =================================================================
    
    st.markdown("---")
    
    # --- Alerta de Dívidas Vencidas ---
    df_vencidas = df_exibicao[df_exibicao["Vencida"] == True]
    if not df_vencidas.empty:
        total_vencido = df_vencidas["Valor"].abs().sum()
        st.error(f"🚨 **{len(df_vencidas)} CONTAS VENCIDAS!** Total: R$ {total_vencido:,.2f} - Liquide no Histórico.")
        st.markdown("---")

    tab_pendentes, tab_historico = st.tabs(["🧾 Contas Pendentes", "📋 Histórico Completo"])

    with tab_pendentes:
        df_pendentes = df_exibicao[df_exibicao["Status"] == "Pendente"].copy()
        
        if df_pendentes.empty:
            st.info("🎉 Nenhuma conta pendente. Tudo em dia!")
        else:
            
            # Formata colunas
            df_display_pendentes = df_pendentes.copy()
            df_display_pendentes['Data Vencimento'] = df_display_pendentes['Data_Vencimento'].dt.strftime('%d/%m/%Y').fillna('Sem Data')
            
            # Estilo para vencidas
            def highlight_vencida(row):
                return ['background-color: #f7a7a3' if row['Vencida'] else '' for _ in row.index]

            st.dataframe(
                df_display_pendentes[['ID', 'Tipo', 'Valor', 'Nome_Cliente', 'Data Vencimento', 'Descricao', 'Cor', 'Vencida']].style.apply(highlight_vencida, axis=1),
                use_container_width=True,
                column_config={
                    "Valor": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f"),
                    "Nome_Cliente": "Cliente/Fornecedor",
                    "Data Vencimento": "Vencimento Previsto",
                    "Descricao": "Detalhes"
                },
                hide_index=True,
                key="tabela_pendentes"
            )
            st.info(f"Total Pendente (Receber): R$ {df_pendentes[df_pendentes['Tipo'] == 'A Receber']['Valor'].sum():,.2f}")
            st.info(f"Total Pendente (Pagar): R$ {df_pendentes[df_pendentes['Tipo'] == 'A Pagar']['Valor'].sum():,.2f}")

    with tab_historico:
        st.subheader("📋 Histórico Completo (Pendente e Realizado)")
        
        df_historico = df_exibicao.copy()
        
        if df_historico.empty:
            st.info("Nenhuma movimentação no histórico.")
        else:
            df_historico['Data Vencimento'] = df_historico['Data_Vencimento'].dt.strftime('%d/%m/%Y').fillna('N/A')
            df_historico['Data Realizada'] = df_historico['Data_Pagamento'].dt.strftime('%d/%m/%Y').fillna('N/A')
            df_historico['Produtos Resumo'] = df_historico['Produtos_Vendidos'].apply(lambda x: f"({len(ast.literal_eval(x))} itens)" if x else "")

            cols_to_show = ['ID', 'Loja', 'Data_Criacao', 'Tipo', 'Valor', 'Nome_Cliente', 'Status', 'Data Realizada', 'Forma_Pagamento', 'Produtos Resumo']
            
            st.dataframe(
                df_historico[cols_to_show],
                use_container_width=True,
                column_config={
                    "Valor": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f"),
                    "Data_Criacao": st.column_config.DatetimeColumn("Data Lanç.", format="DD/MM/YYYY"),
                    "Nome_Cliente": "Cliente/Fornecedor",
                    "Data Realizada": "Data Pagt./Receb.",
                    "Forma_Pagamento": "Forma Pagt.",
                    "Produtos Resumo": "Detalhes Venda"
                },
                hide_index=True,
                key="tabela_historico"
            )

            # --- Lógica de Exclusão/Liquidação no Histórico ---
            st.markdown("---")
            st.markdown("### 📝 Operações no Histórico (Excluir/Liquidar)")
            
            opcoes_operacao = df_historico.apply(
                lambda row: f"{row['ID']} | R$ {row['Valor']:,.2f} ({row['Tipo']}) | Status: {row['Status']}", axis=1
            ).tolist()
            
            movimentacao_selecionada_str = st.selectbox(
                "Selecione a movimentação para Ação:",
                options=[""] + opcoes_operacao,
                key="select_acao_historico"
            )

            if movimentacao_selecionada_str:
                id_selecionado = movimentacao_selecionada_str.split(' | ')[0]
                row_original = df_dividas[df_dividas["ID"] == id_selecionado].iloc[0]
                idx_original = row_original.name # O índice real no df_dividas

                st.markdown(f"**Movimentação Selecionada:** {movimentacao_selecionada_str}")

                if row_original["Status"] == "Pendente":
                    # --- Liquidação (Conclusão) ---
                    st.markdown("##### ➡️ Liquidar Conta Pendente:")
                    with st.form("form_liquidar_historico"):
                        data_conclusao = st.date_input("Data de Pagamento Real", value=datetime.now().date(), key="liquidar_data_h")
                        forma_conclusao = st.selectbox("Forma de Pagamento Real", options=FORMAS_PAGAMENTO, key="liquidar_forma_h")
                        
                        confirmar_liquidacao = st.form_submit_button("✅ Concluir esta Conta")

                    if confirmar_liquidacao:
                        # 1. Se for A Receber (venda), debita o estoque
                        if row_original['Tipo'] == "A Receber" and row_original["Produtos_Vendidos"]:
                            try:
                                produtos_vendidos = ast.literal_eval(row_original['Produtos_Vendidos'])
                                for item in produtos_vendidos:
                                    ajustar_estoque(item["id"], item["Quantidade"], "debitar")
                                save_data_github(st.session_state.produtos, ARQ_PRODUTOS, "Débito de estoque por liquidação de venda pendente")
                                st.success("Estoque debitado por venda liquidada.")
                            except Exception as e:
                                st.error(f"Erro ao debitar estoque: {e}")

                        # 2. Atualiza o DataFrame de Dívidas
                        st.session_state.dividas.loc[idx_original, 'Status'] = 'Realizada'
                        st.session_state.dividas.loc[idx_original, 'Data_Pagamento'] = pd.to_datetime(data_conclusao)
                        st.session_state.dividas.loc[idx_original, 'Forma_Pagamento'] = forma_conclusao

                        save_data_github(st.session_state.dividas, PATH_DIVIDAS, f"Conta ID {id_selecionado} liquidada.")
                        st.rerun()

                # --- Exclusão (Sempre disponível) ---
                st.markdown("##### 🗑️ Excluir Movimentação:")
                if st.button(f"🗑️ Excluir Movimentação {id_selecionado}", type="primary"):
                    
                    # 1. Se era uma venda REALIZADA, credita o estoque
                    if row_original['Status'] == "Realizada" and row_original['Tipo'] == "A Receber" and row_original["Produtos_Vendidos"]:
                        try:
                            produtos_vendidos = ast.literal_eval(row_original['Produtos_Vendidos'])
                            for item in produtos_vendidos:
                                ajustar_estoque(item["id"], item["Quantidade"], "creditar")
                            save_data_github(st.session_state.produtos, ARQ_PRODUTOS, "Crédito de estoque por exclusão de venda")
                            st.warning("Estoque creditado de volta.")
                        except Exception as e:
                            st.error(f"Erro ao creditar estoque: {e}")

                    # 2. Remove a linha e salva
                    st.session_state.dividas = st.session_state.dividas.drop(idx_original, errors='ignore').reset_index(drop=True)
                    save_data_github(st.session_state.dividas, PATH_DIVIDAS, f"Movimentação ID {id_selecionado} excluída.")
                    st.rerun()

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
    ["Livro Caixa", "Produtos"],
    key='main_page_select_widget'
)

if main_tab_select == "Livro Caixa":
    livro_caixa()
elif main_tab_select == "Produtos":
    gestao_produtos()
