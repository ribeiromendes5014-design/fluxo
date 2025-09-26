import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
import requests
from io import StringIO
import io, os
import json 
# Importa a biblioteca PyGithub para gerenciamento de persistência
from github import Github
import plotly.express as px

# ==================== CONFIGURAÇÕES DO APLICATIVO ====================
# As variáveis de token e repositório são carregadas dos segredos do Streamlit.
try:
    TOKEN = st.secrets["GITHUB_TOKEN"]
    OWNER = st.secrets["REPO_OWNER"]
    REPO_NAME = st.secrets["REPO_NAME"]
    CSV_PATH = st.secrets["CSV_PATH"]
    BRANCH = st.secrets.get("BRANCH", "main")
except KeyError:
    st.error("Por favor, configure as chaves 'GITHUB_TOKEN', 'REPO_OWNER', 'REPO_NAME' e 'CSV_PATH' no seu secrets.toml.")
    st.stop() # Interrompe o aplicativo se as chaves essenciais não existirem

COMMIT_MESSAGE = "Atualiza livro caixa via Streamlit (com produtos/categorias)"
COMMIT_MESSAGE_DELETE = "Exclui movimentações do livro caixa"
COMMIT_MESSAGE_EDIT = "Edita movimentação via Streamlit"
COMMIT_MESSAGE_DEBT_REALIZED = "Conclui dívidas pendentes"

ARQ_LOCAL = "livro_caixa.csv"
# COLUNA PADRÃO ATUALIZADA: Adiciona 'Status' e 'Data Pagamento'
COLUNAS_PADRAO = ["Data", "Loja", "Cliente", "Valor", "Forma de Pagamento", "Tipo", "Produtos Vendidos", "Categoria", "Status", "Data Pagamento"]

# Lojas disponíveis para seleção
LOJAS_DISPONIVEIS = ["Doce&bella", "Papelaria", "Fotografia", "Outro"]

# Categorias de Saída (Centro de Custo)
CATEGORIAS_SAIDA = ["Aluguel", "Salários/Pessoal", "Marketing/Publicidade", "Fornecedores/Matéria Prima", "Despesas Fixas", "Impostos/Taxas", "Outro/Diversos", "Não Categorizado"]

# Formas de pagamento para conclusão de dívidas
FORMAS_PAGAMENTO = ["Dinheiro", "Cartão", "PIX", "Transferência", "Outro"]

# ========================================================
# FUNÇÕES DE PERSISTÊNCIA (adaptadas do loja.py)
# ========================================================
def ensure_csv(path: str, columns: list) -> pd.DataFrame:
    """Garante que o CSV exista localmente com as colunas corretas."""
    try:
        df = pd.read_csv(path, dtype=str)
    except Exception:
        df = pd.DataFrame(columns=columns)
        df.to_csv(path, index=False)
    
    # Garante que todas as colunas padrão existam
    for c in columns:
        if c not in df.columns:
            df[c] = ""
    
    return df[columns]

def load_csv_github(path: str) -> pd.DataFrame | None:
    """Carrega CSV de repositório privado do GitHub (via token)."""
    try:
        g = Github(TOKEN)
        repo = g.get_repo(f"{OWNER}/{REPO_NAME}")
        contents = repo.get_contents(path, ref=BRANCH)
        # Usa io.StringIO para ler o conteúdo decodificado
        return pd.read_csv(io.StringIO(contents.decoded_content.decode()), dtype=str)
    except Exception:
        return None

def load_csv_from_url(url: str) -> pd.DataFrame | None:
    """Carrega CSV de repositório público (URL raw)."""
    try:
        df = pd.read_csv(url, dtype=str)
        if df.empty or len(df.columns) < 2:
            return None
        return df
    except Exception:
        return None

@st.cache_data(show_spinner="Carregando dados do Livro Caixa...")
def carregar_livro_caixa():
    """Orquestra o carregamento: GitHub privado → público → local"""
    df = None
    
    # Tenta carregar do GitHub (privado ou público)
    df = load_csv_github(CSV_PATH)
    if df is None:
        url_raw = f"https://raw.githubusercontent.com/{OWNER}/{REPO_NAME}/{BRANCH}/{CSV_PATH}"
        df = load_csv_from_url(url_raw)

    # Fallback ou processamento pós-carga
    if df is None or df.empty:
        df = ensure_csv(ARQ_LOCAL, COLUNAS_PADRAO)
        
    # Garante que as colunas padrão existam e preenche novas colunas com ""
    for col in COLUNAS_PADRAO:
        if col not in df.columns:
            # Novo: 'Status' padrão é 'Realizada' para compatibilidade com dados antigos
            df[col] = "Realizada" if col == "Status" else "" 
            
    # Retorna apenas as colunas padrão na ordem correta
    return df[COLUNAS_PADRAO]

def salvar_dados_no_github(df: pd.DataFrame, commit_message: str):
    """Salva o DataFrame CSV no GitHub e também localmente (backup)."""
    # Backup local
    df.to_csv(ARQ_LOCAL, index=False)

    # Prepara DataFrame para envio ao GitHub
    df_temp = df.copy()
    if 'Data' in df_temp.columns:
        # Garante que as datas sejam strings no formato ISO para salvar corretamente
        df_temp['Data'] = df_temp['Data'].apply(
            lambda x: x.strftime('%Y-%m-%d') if pd.notnull(x) and hasattr(x, 'strftime') else x
        )
    if 'Data Pagamento' in df_temp.columns:
        # Garante que as datas de pagamento sejam strings no formato ISO
        df_temp['Data Pagamento'] = df_temp['Data Pagamento'].apply(
            lambda x: x.strftime('%Y-%m-%d') if pd.notnull(x) and hasattr(x, 'strftime') else x
        )

    try:
        g = Github(TOKEN)
        repo = g.get_repo(f"{OWNER}/{REPO_NAME}")
        csv_string = df_temp.to_csv(index=False)

        try:
            # Tenta obter o SHA do conteúdo atual
            contents = repo.get_contents(CSV_PATH, ref=BRANCH)
            # Atualiza o arquivo
            repo.update_file(contents.path, commit_message, csv_string, contents.sha, branch=BRANCH)
            st.success("📁 Dados salvos (atualizados) no GitHub com sucesso!")
        except Exception:
            # Cria o arquivo (se não foi encontrado, assume-se que é a primeira vez)
            repo.create_file(CSV_PATH, commit_message, csv_string, branch=BRANCH)
            st.success("📁 Dados salvos (criados) no GitHub com sucesso!")

        return True

    except Exception as e:
        st.error(f"❌ Erro ao salvar no GitHub: {e}")
        st.error("Verifique se seu 'GITHUB_TOKEN' tem permissões e se o repositório existe.")
        return False

# ==================== FUNÇÕES DE PROCESSAMENTO DE DADOS ====================

def processar_dataframe(df):
    """
    Padroniza o DataFrame para uso na UI: conversão de tipos, cálculo de saldo acumulado e ordenação.
    Retorna o DataFrame processado.
    """
    if df.empty:
        return pd.DataFrame(columns=COLUNAS_PADRAO + ["ID Visível", "original_index", "Data_dt", "Saldo Acumulado"])
        
    df_proc = df.copy()
    
    # --- GARANTE A EXISTÊNCIA DAS COLUNAS ESSENCIAIS ANTES DO PROCESSAMENTO (FIX PARA KEYERROR) ---
    if 'Categoria' not in df_proc.columns:
        df_proc['Categoria'] = ""
    if 'Status' not in df_proc.columns: 
        df_proc['Status'] = "Realizada"
    if 'Data Pagamento' not in df_proc.columns:
        df_proc['Data Pagamento'] = pd.NaT 
    # --- FIM GARANTIA DE COLUNAS ---

    # Conversão de Valor
    df_proc["Valor"] = pd.to_numeric(df_proc["Valor"], errors="coerce").fillna(0.0)

    # Conversão de Data e Data Pagamento
    df_proc["Data"] = pd.to_datetime(df_proc["Data"], errors='coerce').dt.date
    df_proc["Data_dt"] = pd.to_datetime(df_proc["Data"], errors='coerce') # Data para ordenação
    
    # Agora 'Data Pagamento' existe garantidamente
    df_proc["Data Pagamento"] = pd.to_datetime(df_proc["Data Pagamento"], errors='coerce').dt.date
    
    # Remove linhas onde a data não pôde ser convertida
    df_proc.dropna(subset=['Data_dt'], inplace=True)
    
    # --- RESETAR O ÍNDICE E CALCULAR SALDO ACUMULADO ---
    
    # 1. Preserva o índice original e prepara para cálculo
    df_proc = df_proc.reset_index(drop=False) 
    df_proc.rename(columns={'index': 'original_index'}, inplace=True)
    
    # Filtra o DataFrame para calcular o Saldo Acumulado APENAS com transações REALIZADAS
    df_realizadas = df_proc[df_proc['Status'] == 'Realizada'].copy()

    # NOVO: Verifica se há transações realizadas
    if df_realizadas.empty:
        df_proc['Saldo Acumulado'] = 0.0
    else:
        # 2. Calula Saldo Acumulado (requer ordenação por data ascendente)
        df_proc_sorted_asc = df_realizadas.sort_values(by=['Data_dt', 'original_index'], ascending=[True, True]).reset_index(drop=True)
        # Usa um nome temporário único: TEMP_SALDO
        df_proc_sorted_asc['TEMP_SALDO'] = df_proc_sorted_asc['Valor'].cumsum()
        
        # Junta o saldo acumulado de volta ao DF principal
        df_proc = pd.merge(
            df_proc, 
            df_proc_sorted_asc[['original_index', 'TEMP_SALDO']], 
            on='original_index', 
            how='left'
        )
        
        # 3. Aplica fillna para preencher valores nulos e atribui ao nome final
        df_proc['Saldo Acumulado'] = df_proc['TEMP_SALDO'].fillna(method='ffill').fillna(0)
        df_proc.drop(columns=['TEMP_SALDO'], inplace=True)


    # 4. Retorna à ordenação para exibição (Data DESC)
    df_proc = df_proc.sort_values(by="Data_dt", ascending=False).reset_index(drop=True)
    df_proc.insert(0, 'ID Visível', df_proc.index + 1)
    
    
    # Adiciona a coluna de Cor para formatação condicional
    df_proc['Cor_Valor'] = df_proc.apply(lambda row: 'green' if row['Tipo'] == 'Entrada' and row['Valor'] >= 0 else 'red', axis=1)

    return df_proc

def calcular_resumo(df):
    """Calcula e retorna o resumo financeiro (Entradas, Saídas, Saldo) APENAS de transações Realizadas."""
    # Filtra apenas transações realizadas para o resumo do caixa
    df_realizada = df[df['Status'] == 'Realizada']
    
    if df_realizada.empty:
        return 0.0, 0.0, 0.0
        
    total_entradas = df_realizada[df_realizada["Tipo"] == "Entrada"]["Valor"].sum()
    total_saidas = abs(df_realizada[df_realizada["Tipo"] == "Saída"]["Valor"].sum()) 
    saldo = df_realizada["Valor"].sum()
    return total_entradas, total_saidas, saldo

# Função para formatar a coluna 'Produtos Vendidos'
def format_produtos_resumo(produtos_json):
    if produtos_json:
        try:
            produtos = json.loads(produtos_json)
            count = len(produtos)
            if count > 0:
                primeiro = produtos[0]['Produto']
                # Adiciona informação de lucro (se disponível)
                total_custo = sum(float(p.get('Custo Unitário', 0)) * float(p.get('Quantidade', 0)) for p in produtos)
                total_venda = sum(float(p.get('Preço Unitário', 0)) * float(p.get('Quantidade', 0)) for p in produtos)
                lucro = total_venda - total_custo
                
                lucro_str = f"| Lucro R$ {lucro:,.2f}" if lucro != 0 else ""
                
                return f"{count} item(s): {primeiro}... {lucro_str}"
        except:
            return "Erro na formatação"
    return ""

# Função para aplicar o destaque condicional na coluna Valor
def highlight_value(row):
    color = row['Cor_Valor']
    return [f'color: {color}' if col == 'Valor' else '' for col in row.index]


# ==================== INTERFACE STREAMLIT ====================
st.set_page_config(layout="wide", page_title="Livro Caixa", page_icon="📘") 
st.title("📘 Livro Caixa - Gerenciamento de Movimentações")

# === Inicialização do Session State ===
if "df" not in st.session_state:
    st.session_state.df = carregar_livro_caixa()

if "lista_produtos" not in st.session_state:
    st.session_state.lista_produtos = []
    
if "edit_id" not in st.session_state:
    st.session_state.edit_id = None
    
if "operacao_selecionada" not in st.session_state:
    st.session_state.operacao_selecionada = "Editar" 

# DataFrame usado na exibição e análise (já processado)
df_exibicao = processar_dataframe(st.session_state.df)

# =================================================
# LÓGICA DE CARREGAMENTO PARA EDIÇÃO
# =================================================

edit_mode = st.session_state.edit_id is not None
movimentacao_para_editar = None

# Valores padrão do formulário (preenchidos com valores iniciais ou valores de edição)
default_loja = LOJAS_DISPONIVEIS[0]
default_data = datetime.now().date()
default_cliente = ""
default_valor = 0.01
default_forma = "Dinheiro"
default_tipo = "Entrada"
default_produtos_json = ""
default_categoria = CATEGORIAS_SAIDA[0]
default_status = "Realizada" # Novo campo
default_data_pagamento = None # Novo campo

# Se estiver em modo de edição, carrega os dados
if edit_mode:
    original_idx_to_edit = st.session_state.edit_id
    
    linha_df_exibicao = df_exibicao[df_exibicao['original_index'] == original_idx_to_edit]

    if not linha_df_exibicao.empty:
        movimentacao_para_editar = linha_df_exibicao.iloc[0]
        
        # Define os valores padrão para a edição
        default_loja = movimentacao_para_editar['Loja']
        default_data = movimentacao_para_editar['Data']
        default_cliente = movimentacao_para_editar['Cliente']
        default_valor = abs(movimentacao_para_editar['Valor'])
        default_forma = movimentacao_para_editar['Forma de Pagamento']
        default_tipo = movimentacao_para_editar['Tipo']
        default_produtos_json = movimentacao_para_editar['Produtos Vendidos']
        default_categoria = movimentacao_para_editar['Categoria']
        default_status = movimentacao_para_editar['Status'] # Carrega Status
        default_data_pagamento = movimentacao_para_editar['Data Pagamento'] if pd.notna(movimentacao_para_editar['Data Pagamento']) else None # Carrega Data Pagamento
        
        # Carrega os produtos na lista de sessão (se for entrada)
        if default_tipo == "Entrada" and default_produtos_json:
            try:
                produtos_list = json.loads(default_produtos_json)
                for p in produtos_list:
                     p['Quantidade'] = float(p.get('Quantidade', 0))
                     p['Preço Unitário'] = float(p.get('Preço Unitário', 0))
                     p['Custo Unitário'] = float(p.get('Custo Unitário', 0))
                st.session_state.lista_produtos = produtos_list
            except:
                st.session_state.lista_produtos = []
        elif default_tipo == "Saída":
            st.session_state.lista_produtos = []
        
        st.sidebar.warning(f"Modo EDIÇÃO: Movimentação ID {movimentacao_para_editar['ID Visível']}")
        
    else:
        st.session_state.edit_id = None
        edit_mode = False
        st.sidebar.info("Movimentação não encontrada, saindo do modo de edição.")
        st.rerun() 

# --- Formulário de Nova Movimentação na barra lateral ---
st.sidebar.header("Nova Movimentação" if not edit_mode else "Editar Movimentação Existente")

# CAMPOS DE INPUT NA SIDEBAR (USANDO VALORES PADRÃO CALCULADOS ACIMA)
loja_selecionada = st.sidebar.selectbox("Loja Responsável pela Venda/Gasto", 
                                        LOJAS_DISPONIVEIS, 
                                        index=LOJAS_DISPONIVEIS.index(default_loja) if default_loja in LOJAS_DISPONIVEIS else 0)
data_input = st.sidebar.date_input("Data", value=default_data)

# --- Alerta de Data Antiga/Futura ---
hoje = date.today()
limite_passado = hoje - timedelta(days=90)
if data_input > hoje:
    st.sidebar.warning("⚠️ Data no futuro. Confirme se está correta.")
elif data_input < limite_passado:
    st.sidebar.warning(f"⚠️ Data muito antiga (anterior a {limite_passado.strftime('%d/%m/%Y')}). Confirme se está correta.")

cliente = st.sidebar.text_input("Nome do Cliente (ou Descrição)", value=default_cliente)
forma_pagamento = st.sidebar.selectbox("Forma de Pagamento", 
                                        FORMAS_PAGAMENTO, 
                                        index=FORMAS_PAGAMENTO.index(default_forma) if default_forma in FORMAS_PAGAMENTO else 0)
tipo = st.sidebar.radio("Tipo", ["Entrada", "Saída"], index=0 if default_tipo == "Entrada" else 1)

# --- NOVO: CAMPO DE STATUS E DATA DE PAGAMENTO ---
st.sidebar.markdown("#### 🔄 Status da Transação")
status_selecionado = st.sidebar.radio("Status", ["Realizada", "Pendente"], index=0 if default_status == "Realizada" else 1)

data_pagamento_final = None # Inicializa como None
if status_selecionado == "Pendente":
    # Se for pendente, o campo "Data Pagamento" é opcional (Data Prevista)
    data_pagamento_prevista = st.sidebar.date_input(
        "Data Prevista de Pagamento (Opcional)", 
        value=default_data_pagamento, 
        key="input_data_prevista"
    )
    data_pagamento_final = data_pagamento_prevista
    st.sidebar.info("⚠️ Transações Pendentes NÃO afetam o Saldo Atual.")
elif status_selecionado == "Realizada":
    # Se for realizada, a Data Pagamento deve ser a Data da transação (ou a data que já estava salva)
    data_pagamento_final = data_input 
# Fim NOVO

# VARIÁVEIS DE CÁLCULO
valor_calculado = 0.0
produtos_vendidos_json = ""
categoria_selecionada = ""

# --- LÓGICA DE PRODUTOS PARA ENTRADA ---
if tipo == "Entrada":
    st.sidebar.markdown("#### 🛍️ Detalhes dos Produtos (Entrada)")
    
    if st.session_state.lista_produtos:
        df_produtos = pd.DataFrame(st.session_state.lista_produtos)
        df_produtos['Quantidade'] = pd.to_numeric(df_produtos['Quantidade'], errors='coerce').fillna(0)
        df_produtos['Preço Unitário'] = pd.to_numeric(df_produtos['Preço Unitário'], errors='coerce').fillna(0.0)
        df_produtos['Custo Unitário'] = pd.to_numeric(df_produtos['Custo Unitário'], errors='coerce').fillna(0.0)
        
        df_produtos['Total Venda'] = df_produtos['Quantidade'] * df_produtos['Preço Unitário']
        df_produtos['Total Custo'] = df_produtos['Quantidade'] * df_produtos['Custo Unitário']
        df_produtos['Lucro Bruto'] = df_produtos['Total Venda'] - df_produtos['Total Custo']
        
        st.sidebar.dataframe(
            df_produtos[['Produto', 'Quantidade', 'Preço Unitário', 'Custo Unitário', 'Total Venda', 'Lucro Bruto']], 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "Preço Unitário": st.column_config.NumberColumn(format="R$ %.2f"),
                "Custo Unitário": st.column_config.NumberColumn(format="R$ %.2f"),
                "Total Venda": st.column_config.NumberColumn(format="R$ %.2f"),
                "Lucro Bruto": st.column_config.NumberColumn(format="R$ %.2f", width="small")
            }
        )
        
        valor_calculado = df_produtos['Total Venda'].sum()
        lucro_total = df_produtos['Lucro Bruto'].sum()
        st.sidebar.success(f"Soma Total da Venda: R$ {valor_calculado:,.2f}")
        st.sidebar.info(f"Lucro Bruto Calculado: R$ {lucro_total:,.2f}")
        
        produtos_para_json = df_produtos[['Produto', 'Quantidade', 'Preço Unitário', 'Custo Unitário']].to_dict('records')
        produtos_vendidos_json = json.dumps(produtos_para_json)

    else:
        st.sidebar.info("Nenhum produto adicionado. Use o campo 'Valor' abaixo para uma entrada geral.")

    st.sidebar.markdown("---")
    
    with st.sidebar.expander("➕ Adicionar Novo Produto"):
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            nome_produto = st.text_input("Nome do Produto", key="input_nome_prod_edit")
        with col_p2:
            quantidade_input = st.number_input("Qtd", min_value=1.0, value=1.0, step=1.0, key="input_qtd_prod_edit")
        
        col_p3, col_p4 = st.columns(2)
        with col_p3:
            preco_unitario_input = st.number_input("Preço Unitário (R$)", min_value=0.01, format="%.2f", key="input_preco_prod_edit")
        with col_p4:
            custo_unitario_input = st.number_input("Custo Unitário (R$)", min_value=0.00, value=0.00, format="%.2f", key="input_custo_prod_edit")
        
        if st.button("Adicionar Produto à Lista (Entrada)", use_container_width=True):
            if nome_produto and preco_unitario_input > 0 and quantidade_input > 0:
                st.session_state.lista_produtos.append({
                    "Produto": nome_produto,
                    "Quantidade": quantidade_input,
                    "Preço Unitário": preco_unitario_input,
                    "Custo Unitário": custo_unitario_input 
                })
                st.rerun()
            else:
                st.warning("Preencha o nome, quantidade e preço unitário corretamente.")
    
    if st.session_state.lista_produtos:
        if st.sidebar.button("Limpar Lista de Produtos (Entrada)", type="secondary"):
            st.session_state.lista_produtos = []
            st.rerun()
            
    valor_input_manual = st.sidebar.number_input(
        "Valor Total (R$)", 
        value=valor_calculado if valor_calculado > 0.0 else default_valor,
        min_value=0.01, 
        format="%.2f",
        disabled=(valor_calculado > 0.0), 
        key="input_valor_entrada"
    )
    
    valor_final_movimentacao = valor_calculado if valor_calculado > 0.0 else valor_input_manual
    categoria_selecionada = "" 

else: # Tipo é Saída
    if not edit_mode or tipo != default_tipo:
        st.session_state.lista_produtos = [] 
        
    custom_desc_default = ""
    default_select_index = 0
    
    if default_categoria in CATEGORIAS_SAIDA:
        default_select_index = CATEGORIAS_SAIDA.index(default_categoria)
    elif default_categoria.startswith("Outro: "):
        default_select_index = CATEGORIAS_SAIDA.index("Outro/Diversos")
        custom_desc_default = default_categoria.replace("Outro: ", "")
    
    st.sidebar.markdown("#### ⚙️ Centro de Custo (Saída)")
    categoria_selecionada = st.sidebar.selectbox("Categoria de Gasto", 
                                                 CATEGORIAS_SAIDA, 
                                                 index=default_select_index)
        
    if categoria_selecionada == "Outro/Diversos":
        descricao_personalizada = st.sidebar.text_input("Especifique o Gasto (Obrigatório)", 
                                                        value=custom_desc_default, 
                                                        placeholder="Ex: Aluguel de Novo Escritório",
                                                        key="input_custom_category")
        if descricao_personalizada:
            categoria_selecionada = f"Outro: {descricao_personalizada}"
        else:
            pass 
        
    valor_input_manual = st.sidebar.number_input(
        "Valor (R$)", 
        value=default_valor, 
        min_value=0.01, 
        format="%.2f", 
        key="input_valor_saida"
    )
    valor_final_movimentacao = valor_input_manual
    produtos_vendidos_json = "" 

# --- Botões de Submissão Único ---
if edit_mode:
    col_save, col_cancel = st.sidebar.columns(2)
    with col_save:
        enviar = st.button("💾 Salvar Edição", type="primary", use_container_width=True)
    with col_cancel:
        cancelar = st.button("❌ Cancelar Edição", type="secondary", use_container_width=True)
else:
    enviar = st.sidebar.button("Adicionar Movimentação e Salvar", type="primary", use_container_width=True)
    cancelar = False 

# Lógica de Cancelamento
if cancelar:
    st.session_state.edit_id = None
    st.session_state.lista_produtos = []
    st.rerun()

# --- Lógica principal (Adicionar/Editar) ---
if enviar:
    if not cliente or valor_final_movimentacao <= 0:
        st.sidebar.warning("Por favor, preencha a descrição/cliente e o valor corretamente.")
    elif tipo == "Entrada" and valor_final_movimentacao == 0.01 and not st.session_state.lista_produtos and not edit_mode:
        st.sidebar.warning("Se o Tipo for 'Entrada', insira um Valor real ou adicione produtos.")
    else:
        # Se for Pendente, o valor deve ser positivo para Entrada e NEGATIVO para Saída para a tabela de dívidas.
        valor_armazenado = valor_final_movimentacao if tipo == "Entrada" else -valor_final_movimentacao
        
        if tipo == "Entrada" and not cliente:
            cliente_desc = f"Venda de {len(st.session_state.lista_produtos)} produto(s)"
        else:
            cliente_desc = cliente
            
        nova_linha_data = {
            "Data": data_input,
            "Loja": loja_selecionada, 
            "Cliente": cliente_desc,
            "Valor": valor_armazenado, 
            "Forma de Pagamento": forma_pagamento,
            "Tipo": tipo,
            "Produtos Vendidos": produtos_vendidos_json,
            "Categoria": categoria_selecionada,
            "Status": status_selecionado, # Novo
            "Data Pagamento": data_pagamento_final # Novo
        }
        
        if edit_mode:
            original_idx_to_edit = st.session_state.edit_id
            if original_idx_to_edit in st.session_state.df.index:
                nova_linha_str = {k: str(v) for k, v in nova_linha_data.items() if pd.notna(v)}
                st.session_state.df.loc[original_idx_to_edit] = pd.Series(nova_linha_str)
                commit_msg = COMMIT_MESSAGE_EDIT
            else:
                st.error("Erro interno: Movimentação original não encontrada para edição.")
                st.session_state.edit_id = None
                st.rerun()
        else:
            st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([nova_linha_data])], ignore_index=True)
            commit_msg = COMMIT_MESSAGE
            
        
        if salvar_dados_no_github(st.session_state.df, commit_msg):
            st.session_state.edit_id = None
            st.session_state.lista_produtos = [] 
            st.cache_data.clear()
            st.rerun()

# ========================================================
# SEÇÃO PRINCIPAL (Abas)
# ========================================================
tab_mov, tab_rel = st.tabs(["📋 Movimentações e Resumo", "📈 Relatórios e Filtros"])


with tab_mov:
    
    # --- FILTRAR PARA O MÊS ATUAL ---
    hoje = date.today()
    primeiro_dia_mes = hoje.replace(day=1)

    if hoje.month == 12:
        proximo_mes = hoje.replace(year=hoje.year + 1, month=1, day=1)
    else:
        proximo_mes = hoje.replace(month=hoje.month + 1, day=1)
    ultimo_dia_mes = proximo_mes - timedelta(days=1)

    # Filtra o DataFrame de exibição para incluir apenas o mês atual E que foram REALIZADAS
    df_mes_atual_realizado = df_exibicao[
        (df_exibicao["Data"] >= primeiro_dia_mes) &
        (df_exibicao["Data"] <= ultimo_dia_mes) &
        (df_exibicao["Status"] == "Realizada")
    ]
    
    # Título Atualizado
    st.subheader(f"📊 Resumo Financeiro Geral - Mês de {primeiro_dia_mes.strftime('%m/%Y')}")

    # Calcula Resumo com dados do Mês Atual REALIZADO
    total_entradas, total_saidas, saldo = calcular_resumo(df_mes_atual_realizado)

    col1, col2, col3 = st.columns(3)
    col1.metric("Total de Entradas", f"R$ {total_entradas:,.2f}")
    col2.metric("Total de Saídas", f"R$ {total_saidas:,.2f}")
    delta_saldo = f"R$ {saldo:,.2f}"
    col3.metric("💼 Saldo Final (Realizado)", f"R$ {saldo:,.2f}", delta=delta_saldo if saldo != 0 else None, delta_color="normal")

    st.markdown("---")
    
    # --- Resumo Agregado por Loja (MÊS ATUAL REALIZADO) ---
    st.subheader(f"🏠 Resumo Rápido por Loja (Mês de {primeiro_dia_mes.strftime('%m/%Y')} - Realizado)")
    
    df_resumo_loja = df_mes_atual_realizado.groupby('Loja')['Valor'].agg(['sum', lambda x: x[x >= 0].sum(), lambda x: abs(x[x < 0].sum())]).reset_index()
    df_resumo_loja.columns = ['Loja', 'Saldo', 'Entradas', 'Saídas']
    
    if not df_resumo_loja.empty:
        cols_loja = st.columns(len(df_resumo_loja.index))
        
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
    
    if df_exibicao.empty:
        st.info("Nenhuma movimentação registrada ainda.")
    else:
        # --- FILTROS RÁPIDOS NA TABELA PRINCIPAL (UX Improvement) ---
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            filtro_data_inicio = st.date_input("De", value=df_exibicao["Data"].min(), key="quick_data_ini")
        with col_f2:
            filtro_data_fim = st.date_input("Até", value=df_exibicao["Data"].max(), key="quick_data_fim")
        with col_f3:
            tipos_unicos = ["Todos"] + df_exibicao["Tipo"].unique().tolist()
            filtro_tipo = st.selectbox("Filtrar por Tipo", options=tipos_unicos, key="quick_tipo")

        df_filtrado_rapido = df_exibicao.copy()
        
        # Aplicar filtros de data
        df_filtrado_rapido = df_filtrado_rapido[
            (df_filtrado_rapido["Data"] >= filtro_data_inicio) &
            (df_filtrado_rapido["Data"] <= filtro_data_fim)
        ]

        # Aplicar filtro de tipo
        if filtro_tipo != "Todos":
            df_filtrado_rapido = df_filtrado_rapido[df_filtrado_rapido["Tipo"] == filtro_tipo]

        # --- PREPARAÇÃO DA TABELA ---
        df_para_mostrar = df_filtrado_rapido.copy()
        df_para_mostrar['Produtos Resumo'] = df_para_mostrar['Produtos Vendidos'].apply(format_produtos_resumo)
        
        # Adiciona Status na exibição da tabela principal
        colunas_tabela = ['ID Visível', 'Data', 'Loja', 'Cliente', 'Categoria', 'Valor', 'Forma de Pagamento', 'Tipo', 'Status', 'Data Pagamento', 'Produtos Resumo']
        
        # --- Lógica Correta para Estilização Condicional ---
        df_styling = df_para_mostrar[colunas_tabela + ['Cor_Valor']].copy()

        styled_df = df_styling.style.apply(highlight_value, axis=1)
        styled_df = styled_df.hide(subset=['Cor_Valor'], axis=1)


        # 4. Exibe o DataFrame estilizado
        st.dataframe(
            styled_df,
            use_container_width=True,
            column_config={
                "Valor": st.column_config.NumberColumn(
                    "Valor (R$)",
                    format="R$ %.2f",
                ),
                "Produtos Resumo": st.column_config.TextColumn("Detalhe dos Produtos"),
                "Categoria": "Categoria (C. Custo)",
                "Data Pagamento": st.column_config.DateColumn("Data Pagt. Previsto/Real", format="DD/MM/YYYY")
            },
            height=400,
            selection_mode='single-row', 
            key='movimentacoes_table_styled'
        )


        # --- Lógica de Exibição de Detalhes da Linha Selecionada (Acessando o Session State para estabilidade) ---
        selection_state = st.session_state.get('movimentacoes_table_styled')

        if selection_state and selection_state.get('selection', {}).get('rows'):
            selected_index = selection_state['selection']['rows'][0]
            
            if selected_index < len(df_para_mostrar):
                row = df_para_mostrar.iloc[selected_index]

                if row['Tipo'] == 'Entrada' and row['Produtos Vendidos']:
                    st.markdown("#### Detalhes dos Produtos Selecionados")
                    try:
                        produtos = json.loads(row['Produtos Vendidos'])
                        
                        df_detalhe = pd.DataFrame(produtos)
                        
                        df_detalhe['Total Venda'] = df_detalhe['Quantidade'] * df_detalhe['Preço Unitário']
                        df_detalhe['Total Custo'] = df_detalhe['Quantidade'] * df_detalhe['Custo Unitário']
                        df_detalhe['Lucro Bruto'] = df_detalhe['Total Venda'] - df_detalhe['Total Custo']

                        st.dataframe(
                            df_detalhe,
                            hide_index=True,
                            use_container_width=True,
                            column_config={
                                "Produto": "Produto",
                                "Quantidade": st.column_config.NumberColumn("Qtd"),
                                "Preço Unitário": st.column_config.NumberColumn("Preço Un.", format="R$ %.2f"),
                                "Custo Unitário": st.column_config.NumberColumn("Custo Un.", format="R$ %.2f"),
                                "Total Venda": st.column_config.NumberColumn("Total Venda", format="R$ %.2f"),
                                "Total Custo": st.column_config.NumberColumn("Total Custo", format="R$ %.2f"),
                                "Lucro Bruto": st.column_config.NumberColumn("Lucro Bruto", format="R$ %.2f"),
                            }
                        )
                    except Exception as e:
                        st.error(f"Erro ao carregar detalhes dos produtos: {e}")
                elif row['Tipo'] == 'Saída':
                    st.info(f"Movimentação de Saída. Categoria: **{row['Categoria']}**")

        st.caption("Clique em uma linha para ver os detalhes dos produtos (se for Entrada).")
        st.markdown("---")

        # =================================================================
        # --- OPÇÕES DE EDIÇÃO E EXCLUSÃO UNIFICADAS ---
        # =================================================================
        st.markdown("### 📝 Operações de Movimentação (Editar/Excluir)")
        
        opcoes_operacao = {
            f"ID {row['ID Visível']} | {row['Data'].strftime('%d/%m/%Y')} | {row['Loja']} | R$ {row['Valor']:,.2f}": row['original_index'] 
            for index, row in df_exibicao.iterrows()
        }
        opcoes_keys = list(opcoes_operacao.keys())
        
        col_modo, col_selecao = st.columns([0.3, 0.7])
        
        with col_modo:
            st.session_state.operacao_selecionada = st.radio(
                "Escolha a Operação:",
                options=["Editar", "Excluir"],
                key="radio_operacao_select",
                horizontal=True,
                disabled=edit_mode
            )

        with col_selecao:
            movimentacao_selecionada_str = st.selectbox(
                f"Selecione a movimentação para {st.session_state.operacao_selecionada}:",
                options=opcoes_keys,
                index=0,
                key="select_operacao",
                disabled=edit_mode
            )
            
        original_idx_selecionado = opcoes_operacao.get(movimentacao_selecionada_str)
        
        # --- Botões de Ação Contextual ---
        if original_idx_selecionado is not None:
            if st.session_state.operacao_selecionada == "Editar":
                if st.button("✏️ Levar para Edição na Sidebar", type="secondary", use_container_width=True, disabled=edit_mode):
                    st.session_state.edit_id = original_idx_selecionado
                    st.rerun()
            
            elif st.session_state.operacao_selecionada == "Excluir":
                st.markdown("##### Confirmação de Exclusão:")
                if st.button(f"🗑️ Excluir permanentemente: {movimentacao_selecionada_str}", type="primary", use_container_width=True):
                    
                    if original_idx_selecionado in st.session_state.df.index:
                        st.session_state.df = st.session_state.df.drop(original_idx_selecionado, errors='ignore')
                        
                        if salvar_dados_no_github(st.session_state.df, COMMIT_MESSAGE_DELETE):
                            st.cache_data.clear()
                            st.rerun()
                    else:
                        st.error("Erro interno: Movimentação não encontrada para exclusão.")
        
with tab_rel:
    
    st.header("📈 Relatórios e Filtros")
    
    # --- 1. DEFINIÇÃO DAS SUB-ABAS ---
    subtab_dashboard, subtab_filtro, subtab_produtos, subtab_dividas = st.tabs(["Dashboard Geral", "Filtro e Tabela", "Produtos e Lucro", "🧾 Dívidas Pendentes"])
    
    # --- 2. INICIALIZAÇÃO DE FALLBACK (Garante que df_filtrado_loja SEMPRE exista) ---
    # Usa df_exibicao como fallback, que já é garantido existir, mesmo que vazio.
    df_filtrado_loja = df_exibicao.copy()
    loja_filtro_relatorio = "Todas as Lojas"
    
    # --- 3. VERIFICAÇÃO DE DADOS ---
    if df_exibicao.empty:
        st.info("Não há dados suficientes para gerar relatórios e filtros.")
        # Se estiver vazio, não há nada mais para fazer aqui.
        
    else:
        # --- 4. FILTRO GLOBAL DE LOJA (Ocorre apenas se houver dados) ---
        

        lojas_unicas_no_df = df_exibicao["Loja"].unique().tolist()
        todas_lojas = ["Todas as Lojas"] + [l for l in LOJAS_DISPONIVEIS if l in lojas_unicas_no_df] + [l for l in lojas_unicas_no_df if l not in LOJAS_DISPONIVEIS and l != "Todas as Lojas"]
        todas_lojas = list(dict.fromkeys(todas_lojas))

        loja_filtro_relatorio = st.selectbox(
            "Selecione a Loja para Filtrar Relatórios",
            options=todas_lojas,
            key="loja_filtro_rel"
        )

        if loja_filtro_relatorio != "Todas as Lojas":
            df_filtrado_loja = df_exibicao[df_exibicao["Loja"] == loja_filtro_relatorio].copy()
        else:
            df_filtrado_loja = df_exibicao.copy()
            
        st.subheader(f"Dashboard de Relatórios - {loja_filtro_relatorio}")

        # --- SUB-ABAS COM LÓGICA RESTRITA ---
        # A lógica abaixo AGORA usa df_filtrado_loja, que está definido no escopo de 'else' e é guaranteed to exist.

        with subtab_dividas:
            st.header("🧾 Gerenciamento de Dívidas Pendentes")
            
            # O df_exibicao sempre existe, então esta lógica é segura
            df_pendente = df_exibicao[df_exibicao["Status"] == "Pendente"].copy()
            
            if df_pendente.empty:
                st.info("🎉 Não há Contas a Pagar ou Receber pendentes!")
            else:
                
                # --- Separação Contas a Receber e Pagar ---
                df_receber = df_pendente[df_pendente["Tipo"] == "Entrada"]
                df_pagar = df_pendente[df_pendente["Tipo"] == "Saída"]
                
                st.markdown("---")
                st.markdown("### 📥 Contas a Receber (Vendas Pendentes)")
                
                if df_receber.empty:
                    st.info("Nenhuma venda pendente para receber.")
                else:
                    st.dataframe(
                        df_receber[['ID Visível', 'Data', 'Loja', 'Cliente', 'Valor', 'Data Pagamento']],
                        use_container_width=True,
                        selection_mode='multi-row',
                        column_config={
                            "Data Pagamento": st.column_config.DateColumn("Data Prevista", format="DD/MM/YYYY"),
                            "Valor": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f"),
                        },
                        key="tabela_receber"
                    )
                    
                st.markdown("---")
                st.markdown("### 📤 Contas a Pagar (Despesas Pendentes)")
                
                if df_pagar.empty:
                    st.info("Nenhuma despesa pendente para pagar.")
                else:
                    st.dataframe(
                        df_pagar[['ID Visível', 'Data', 'Loja', 'Cliente', 'Categoria', 'Valor', 'Data Pagamento']],
                        use_container_width=True,
                        selection_mode='multi-row',
                        column_config={
                            "Data Pagamento": st.column_config.DateColumn("Data Prevista", format="DD/MM/YYYY"),
                            "Valor": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f"),
                        },
                        key="tabela_pagar"
                    )

                st.markdown("---")
                st.markdown("### ✅ Concluir Pagamentos Pendentes")

                selecao_receber = st.session_state.get('tabela_receber', {}).get('selection', {}).get('rows', [])
                selecao_pagar = st.session_state.get('tabela_pagar', {}).get('selection', {}).get('rows', [])
                
                indices_selecionados = []
                if selecao_receber:
                    indices_selecionados.extend(df_receber.iloc[selecao_receber]['original_index'].tolist())
                if selecao_pagar:
                    indices_selecionados.extend(df_pagar.iloc[selecao_pagar]['original_index'].tolist())
                
                if indices_selecionados:
                    st.info(f"Total de {len(indices_selecionados)} transações selecionadas para conclusão.")
                    
                    with st.form("form_concluir_dividas"):
                        st.markdown("##### Detalhes da Conclusão:")
                        data_conclusao = st.date_input("Data de Pagamento Real", value=hoje)
                        forma_conclusao = st.selectbox("Forma de Pagamento Real (PIX, Dinheiro, etc.)", options=FORMAS_PAGAMENTO)
                        
                        submeter_conclusao = st.form_submit_button("Concluir Pagamentos Selecionados e Salvar", type="primary")

                    if submeter_conclusao:
                        df_temp_session = st.session_state.df.copy()
                        
                        for original_idx in indices_selecionados:
                            # Atualiza a linha no DataFrame original usando o índice real (original_idx)
                            if original_idx in df_temp_session.index:
                                df_temp_session.loc[original_idx, 'Status'] = 'Realizada'
                                df_temp_session.loc[original_idx, 'Data Pagamento'] = data_conclusao
                                df_temp_session.loc[original_idx, 'Forma de Pagamento'] = forma_conclusao
                                
                        st.session_state.df = df_temp_session
                        
                        if salvar_dados_no_github(st.session_state.df, COMMIT_MESSAGE_DEBT_REALIZED):
                            st.cache_data.clear()
                            st.rerun()
                else:
                    st.warning("Selecione itens nas tabelas acima para concluir.")

        with subtab_dashboard:
            # Agora o acesso a df_filtrado_loja é seguro
            if df_filtrado_loja.empty:
                st.warning("Nenhuma movimentação encontrada para gerar o Dashboard.")
            else:
                
                # --- Análise de Saldo Acumulado (Série Temporal) ---
                st.markdown("### 📉 Saldo Acumulado (Tendência no Tempo)")
                
                # O Saldo Acumulado é calculado apenas para transações REALIZADAS no processamento_dataframe
                df_acumulado = df_filtrado_loja.sort_values(by='Data_dt', ascending=True).copy()
                df_acumulado = df_acumulado[df_acumulado['Status'] == 'Realizada']

                if df_acumulado.empty:
                    st.info("Nenhuma transação Realizada para calcular o Saldo Acumulado.")
                else:
                    fig_line = px.line(
                        df_acumulado,
                        x='Data_dt',
                        y='Saldo Acumulado',
                        title='Evolução do Saldo Realizado ao Longo do Tempo',
                        labels={'Data_dt': 'Data', 'Saldo Acumulado': 'Saldo Acumulado (R$)'},
                        line_shape='spline',
                        markers=True
                    )
                    fig_line.update_layout(xaxis_title="Data", yaxis_title="Saldo Acumulado (R$)")
                    st.plotly_chart(fig_line, use_container_width=True)
                
                st.markdown("---")

                # --- Distribuição de Saídas por Categoria (Centro de Custo) ---
                st.markdown("### 📊 Saídas por Categoria (Centro de Custo - Realizadas)")
                
                df_saidas = df_filtrado_loja[(df_filtrado_loja['Tipo'] == 'Saída') & (df_filtrado_loja['Status'] == 'Realizada')].copy()
                
                if df_saidas.empty:
                    st.info("Nenhuma saída Realizada registrada para análise de categorias.")
                else:
                    df_saidas['Valor Absoluto'] = df_saidas['Valor'].abs()
                    df_categorias = df_saidas.groupby('Categoria')['Valor Absoluto'].sum().reset_index()
                    
                    fig_cat_pie = px.pie(
                        df_categorias,
                        values='Valor Absoluto',
                        names='Categoria',
                        title='Distribuição de Gastos por Categoria',
                        hole=.3
                    )
                    st.plotly_chart(fig_cat_pie, use_container_width=True)

                st.markdown("---")

                # --- Gráfico de Ganhos vs. Gastos (Existente, mas reajustado para Realizada) ---
                st.markdown("### 📈 Ganhos (Entradas) vs. Gastos (Saídas) por Mês (Realizados)")
                
                df_ganhos_gastos = df_filtrado_loja[df_filtrado_loja['Status'] == 'Realizada'].copy()
                
                if df_ganhos_gastos.empty:
                    st.info("Nenhuma transação Realizada para a análise mensal.")
                else:
                    df_ganhos_gastos['MesAno'] = df_ganhos_gastos['Data'].apply(lambda x: x.strftime('%Y-%m'))
                    df_grouped = df_ganhos_gastos.groupby(['MesAno', 'Tipo'])['Valor'].sum().abs().reset_index()
                    df_grouped.columns = ['MesAno', 'Tipo', 'Total']
                    df_grouped = df_grouped.sort_values(by='MesAno')

                    fig_bar = px.bar(
                        df_grouped,
                        x='MesAno',
                        y='Total',
                        color='Tipo',
                        barmode='group',
                        text='Total',
                        color_discrete_map={'Entrada': 'green', 'Saída': 'red'},
                        labels={'Total': 'Valor (R$)', 'MesAno': 'Mês/Ano'},
                        height=500
                    )
                    fig_bar.update_traces(texttemplate='R$ %{y:,.2f}', textposition='outside')
                    st.plotly_chart(fig_bar, use_container_width=True)

        with subtab_produtos:
            st.markdown("## 💰 Análise de Produtos e Lucratividade (Realizados)")

            if df_filtrado_loja.empty:
                st.warning("Nenhuma movimentação encontrada para gerar a Análise de Produtos.")
            else:
                df_entradas_produtos = df_filtrado_loja[(df_filtrado_loja['Tipo'] == 'Entrada') & (df_filtrado_loja['Status'] == 'Realizada')].copy()

                if df_entradas_produtos.empty:
                    st.info("Nenhuma entrada com produtos REALIZADA registrada para análise.")
                else:
                    
                    lista_produtos_agregada = []
                    for index, row in df_entradas_produtos.iterrows():
                        if row['Produtos Vendidos']:
                            try:
                                produtos = json.loads(row['Produtos Vendidos'])
                                for p in produtos:
                                    qtd = float(p.get('Quantidade', 0))
                                    preco_un = float(p.get('Preço Unitário', 0))
                                    custo_un = float(p.get('Custo Unitário', 0))
                                    
                                    lista_produtos_agregada.append({
                                        "Produto": p['Produto'],
                                        "Quantidade": qtd,
                                        "Total Venda": qtd * preco_un,
                                        "Total Custo": qtd * custo_un,
                                        "Lucro Bruto": (qtd * preco_un) - (qtd * custo_un),
                                    })
                            except:
                                pass

                    if lista_produtos_agregada:
                        df_produtos_agregados = pd.DataFrame(lista_produtos_agregada)
                        df_produtos_agregados = df_produtos_agregados.groupby('Produto').sum().reset_index()

                        # --- Top 10 Produtos por Valor Total de Venda ---
                        st.markdown("### 🏆 Top 10 Produtos (Valor de Venda)")
                        top_venda = df_produtos_agregados.sort_values(by='Total Venda', ascending=False).head(10)
                        
                        fig_top_venda = px.bar(
                            top_venda,
                            x='Produto',
                            y='Total Venda',
                            text='Total Venda',
                            title='Top 10 Produtos por Valor Total de Venda (R$)',
                            color='Total Venda'
                        )
                        fig_top_venda.update_traces(texttemplate='R$ %{y:,.2f}', textposition='outside')
                        st.plotly_chart(fig_top_venda, use_container_width=True)
                        
                        # --- Top 10 Produtos por Lucro Bruto (se houver custo) ---
                        if df_produtos_agregados['Lucro Bruto'].sum() > 0:
                            st.markdown("### 💸 Top 10 Produtos por Lucro Bruto")
                            top_lucro = df_produtos_agregados.sort_values(by='Lucro Bruto', ascending=False).head(10)
                            
                            fig_top_lucro = px.bar(
                                top_lucro,
                                x='Produto',
                                y='Lucro Bruto',
                                text='Lucro Bruto',
                                title='Top 10 Produtos Mais Lucrativos (R$)',
                                color='Lucro Bruto',
                                color_continuous_scale=px.colors.sequential.Greens
                            )
                            fig_top_lucro.update_traces(texttemplate='R$ %{y:,.2f}', textposition='outside')
                            st.plotly_chart(fig_top_lucro, use_container_width=True)
                        else:
                            st.info("Adicione o 'Custo Unitário' no cadastro de produtos para ver o ranking de Lucro Bruto.")
                            
                    else:
                        st.info("Nenhum produto com dados válidos encontrado para agregar.")

        with subtab_filtro:
            
            if df_filtrado_loja.empty:
                st.warning("Nenhuma movimentação encontrada para gerar a Tabela Filtrada.")
            else:
                st.subheader("📅 Filtrar Movimentações por Período e Loja")
                
                df_base_filtro_tabela = df_filtrado_loja

                col_data_inicial, col_data_final = st.columns(2)
                
                data_minima = df_base_filtro_tabela["Data"].min() if not df_base_filtro_tabela.empty and df_base_filtro_tabela["Data"].min() is not pd.NaT else datetime.now().date()
                data_maxima = df_base_filtro_tabela["Data"].max() if not df_base_filtro_tabela.empty and df_base_filtro_tabela["Data"].max() is not pd.NaT else datetime.now().date()
                
                data_min_value = data_minima
                data_max_value = data_maxima
                
                with col_data_inicial:
                    data_inicial = st.date_input("Data Inicial", value=data_min_value, key="filtro_data_ini")
                with col_data_final:
                    data_final = st.date_input("Data Final", value=data_max_value, key="filtro_data_fim")

                if data_inicial and data_final:
                    data_inicial_dt = pd.to_datetime(data_inicial).date()
                    data_final_dt = pd.to_datetime(data_final).date()
                    
                    df_filtrado_final = df_base_filtro_tabela[
                        (df_base_filtro_tabela["Data"] >= data_inicial_dt) &
                        (df_base_filtro_tabela["Data"] <= data_final_dt)
                    ].copy()
                    
                    if df_filtrado_final.empty:
                        st.warning("Não há movimentações para o período selecionado.")
                    else:
                        st.markdown("#### Tabela Filtrada")
                        
                        df_filtrado_final['Produtos Resumo'] = df_filtrado_final['Produtos Vendidos'].apply(format_produtos_resumo)
                        
                        colunas_filtro_tabela = ['ID Visível', 'Data', 'Loja', 'Cliente', 'Categoria', 'Valor', 'Forma de Pagamento', 'Tipo', 'Status', 'Data Pagamento', 'Produtos Resumo']

                        # --- Lógica Correta para Estilização Condicional na Tabela Filtrada ---
                        df_styling_filtro = df_filtrado_final[colunas_filtro_tabela + ['Cor_Valor']].copy()
                        styled_df_filtro = df_styling_filtro.style.apply(highlight_value, axis=1)
                        styled_df_filtro = styled_df_filtro.hide(subset=['Cor_Valor'], axis=1)
                        
                        # Aplica estilo condicional na tabela filtrada também
                        st.dataframe(
                            styled_df_filtro,
                            use_container_width=True,
                            column_config={
                                "Valor": st.column_config.NumberColumn(
                                    "Valor (R$)",
                                    format="R$ %.2f",
                                ),
                                "Produtos Resumo": st.column_config.TextColumn("Detalhe dos Produtos"),
                                "Categoria": "Categoria (C. Custo)",
                                "Data Pagamento": st.column_config.DateColumn("Data Pagt. Previsto/Real", format="DD/MM/YYYY")
                            }
                        )

                        # --- Resumo do Período Filtrado (Apenas Realizado) ---
                        entradas_filtro, saidas_filtro, saldo_filtro = calcular_resumo(df_filtrado_final)

                        st.markdown("#### 💰 Resumo do Período Filtrado (Apenas Realizado)")
                        col1_f, col2_f, col3_f = st.columns(3)
                        col1_f.metric("Entradas", f"R$ {entradas_filtro:,.2f}")
                        col2_f.metric("Saídas", f"R$ {saidas_filtro:,.2f}")
                        col3_f.metric("Saldo", f"R$ {saldo_filtro:,.2f}")
