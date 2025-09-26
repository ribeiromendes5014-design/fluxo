import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
import requests
from io import StringIO
import io, os
# Importa a biblioteca PyGithub para gerenciamento de persistência
from github import Github 
import plotly.express as px

# ==================== CONFIGURAÇÕES DO APLICATIVO ====================
# As variáveis de token e repositório são carregadas dos segredos do Streamlit.
# Garanta que suas credenciais estejam seguras no secrets.toml
try:
    TOKEN = st.secrets["GITHUB_TOKEN"]
    OWNER = st.secrets["REPO_OWNER"]
    REPO_NAME = st.secrets["REPO_NAME"] 
    CSV_PATH = st.secrets["CSV_PATH"]
    BRANCH = st.secrets.get("BRANCH", "main")
except KeyError:
    st.error("Por favor, configure as chaves 'GITHUB_TOKEN', 'REPO_OWNER', 'REPO_NAME' e 'CSV_PATH' no seu secrets.toml.")
    st.stop() # Interrompe o aplicativo se as chaves essenciais não existirem

COMMIT_MESSAGE = "Atualiza livro caixa via Streamlit" 
COMMIT_MESSAGE_DELETE = "Exclui movimentações do livro caixa" 

ARQ_LOCAL = "livro_caixa.csv"
# COLUNA PADRÃO ATUALIZADA para incluir 'Loja'
COLUNAS_PADRAO = ["Data", "Loja", "Cliente", "Valor", "Forma de Pagamento", "Tipo"]

# Lojas disponíveis para seleção
LOJAS_DISPONIVEIS = ["Loja A (Física)", "Loja B (Física)", "Online", "Outro"]

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
    for c in columns:
        if c not in df.columns:
            # Se a coluna 'Loja' não existir em um arquivo antigo, preenche com "Não Informado"
            df[c] = "Não Informado" if c == "Loja" else ""
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
        
    # Garante que as colunas padrão existam
    for col in COLUNAS_PADRAO:
        if col not in df.columns:
            # Preenche 'Loja' com valor padrão se for um arquivo antigo sem a coluna
            df[col] = "Não Informado" if col == "Loja" else pd.NA
            
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
    Padroniza o DataFrame para uso na UI: conversão de tipos e ordenação.
    Retorna o DataFrame processado.
    """
    if df.empty:
        return pd.DataFrame(columns=COLUNAS_PADRAO)
        
    df_proc = df.copy()
    
    # Conversão de Valor
    df_proc["Valor"] = pd.to_numeric(df_proc["Valor"], errors="coerce").fillna(0.0)

    # Conversão de Data
    df_proc["Data"] = pd.to_datetime(df_proc["Data"], errors='coerce').dt.date
    
    # Remove linhas onde a data não pôde ser convertida
    df_proc.dropna(subset=['Data'], inplace=True)
    
    # Ordena e adiciona ID Visível
    df_proc = df_proc.sort_values(by="Data", ascending=False).reset_index(drop=True)
    df_proc.insert(0, 'ID Visível', df_proc.index + 1)
    
    return df_proc

def calcular_resumo(df):
    """Calcula e retorna o resumo financeiro (Entradas, Saídas, Saldo)."""
    if df.empty:
        return 0.0, 0.0, 0.0
        
    total_entradas = df[df["Tipo"] == "Entrada"]["Valor"].sum()
    total_saidas = abs(df[df["Tipo"] == "Saída"]["Valor"].sum()) 
    saldo = df["Valor"].sum()
    return total_entradas, total_saidas, saldo

# ==================== INTERFACE STREAMLIT ====================
st.set_page_config(layout="wide", page_title="Livro Caixa")
st.title("📘 Livro Caixa - Gerenciamento de Movimentações")

# === Carregamento e Processamento Inicial ===
if "df" not in st.session_state:
    st.session_state.df = carregar_livro_caixa()

# DataFrame usado na exibição e análise (já processado)
df_exibicao = processar_dataframe(st.session_state.df)

# --- Formulário de Nova Movimentação na barra lateral ---
st.sidebar.header("Nova Movimentação")
with st.sidebar.form("form_movimentacao"):
    # NOVA OPÇÃO DE LOJA AQUI
    loja_selecionada = st.selectbox("Loja Responsável pela Venda/Gasto", LOJAS_DISPONIVEIS)

    data_input = st.date_input("Data", datetime.now().date())
    cliente = st.text_input("Nome do Cliente (ou Descrição)")
    valor = st.number_input("Valor (R$)", min_value=0.01, format="%.2f")
    forma_pagamento = st.selectbox("Forma de Pagamento", ["Dinheiro", "Cartão", "PIX", "Transferência", "Outro"])
    tipo = st.radio("Tipo", ["Entrada", "Saída"])
    enviar = st.form_submit_button("Adicionar Movimentação")

# --- Lógica principal (Adicionar) ---
if enviar:
    if not cliente or valor <= 0:
        st.sidebar.warning("Por favor, preencha a descrição/cliente e o valor corretamente.")
    else:
        valor_armazenado = valor if tipo == "Entrada" else -valor
        nova_linha = {
            "Data": data_input,
            "Loja": loja_selecionada, # Adiciona a loja
            "Cliente": cliente,
            "Valor": valor_armazenado, 
            "Forma de Pagamento": forma_pagamento,
            "Tipo": tipo
        }
        
        st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([nova_linha])], ignore_index=True)
        
        if salvar_dados_no_github(st.session_state.df, COMMIT_MESSAGE):
            st.cache_data.clear()
            st.rerun()

# ========================================================
# SEÇÃO PRINCIPAL (Abas)
# ========================================================
tab_mov, tab_rel = st.tabs(["📋 Movimentações e Resumo", "📈 Relatórios e Filtros"])

with tab_mov:
    st.subheader("📊 Resumo Financeiro Geral")
    total_entradas, total_saidas, saldo = calcular_resumo(df_exibicao)

    col1, col2, col3 = st.columns(3)
    col1.metric("Total de Entradas", f"R$ {total_entradas:,.2f}")
    col2.metric("Total de Saídas", f"R$ {total_saidas:,.2f}")
    delta_saldo = f"R$ {saldo:,.2f}"
    col3.metric("💼 Saldo Final", f"R$ {saldo:,.2f}", delta=delta_saldo if saldo != 0 else None, delta_color="normal")

    st.markdown("---")
    st.subheader("📋 Tabela de Movimentações")
    
    if df_exibicao.empty:
        st.info("Nenhuma movimentação registrada ainda.")
    else:
        # Colunas de exibição atualizadas
        colunas_para_mostrar = ['ID Visível', 'Data', 'Loja', 'Cliente', 'Valor', 'Forma de Pagamento', 'Tipo']
        st.dataframe(
            df_exibicao[colunas_para_mostrar], 
            use_container_width=True,
            column_config={
                "Valor": st.column_config.NumberColumn(
                    "Valor (R$)",
                    format="R$ %.2f",
                ),
            },
            height=400
        )

        st.markdown("---")

        # --- EXCLUSÃO (Mantida na aba principal de Movimentações) ---
        st.markdown("### 🗑️ Excluir Movimentações")
        opcoes_exclusao = {
            f"ID {row['ID Visível']} | {row['Data'].strftime('%d/%m/%Y')} | {row['Loja']} | R$ {row['Valor']:,.2f}": row.name 
            for index, row in df_exibicao.iterrows()
        }
        movimentacoes_a_excluir_str = st.multiselect(
            "Selecione as movimentações que deseja excluir:",
            options=list(opcoes_exclusao.keys()),
            key="multi_excluir"
        )
        indices_a_excluir = [opcoes_exclusao[s] for s in movimentacoes_a_excluir_str]

        if st.button("Excluir Selecionadas e Salvar no GitHub", type="primary"):
            if indices_a_excluir:
                st.session_state.df = st.session_state.df.drop(indices_a_excluir, errors='ignore')
                if salvar_dados_no_github(st.session_state.df, COMMIT_MESSAGE_DELETE):
                    st.cache_data.clear()
                    st.rerun()
            else:
                st.warning("Selecione pelo menos uma movimentação para excluir.")

with tab_rel:
    st.header("📈 Relatórios Financeiros")
    
    if df_exibicao.empty:
        st.info("Não há dados suficientes para gerar relatórios e filtros.")
    else:
        
        # FILTRO GLOBAL DE LOJA PARA RELATÓRIOS
        todas_lojas = ["Todas as Lojas"] + df_exibicao["Loja"].unique().tolist()
        loja_filtro_relatorio = st.selectbox(
            "Selecione a Loja para Filtrar Relatórios",
            options=todas_lojas,
            key="loja_filtro_rel"
        )

        # Aplicar filtro de loja
        if loja_filtro_relatorio != "Todas as Lojas":
            df_filtrado_loja = df_exibicao[df_exibicao["Loja"] == loja_filtro_relatorio]
            st.subheader(f"Dashboard da Loja: {loja_filtro_relatorio}")
        else:
            df_filtrado_loja = df_exibicao
            st.subheader("Dashboard de Relatórios (Todas as Lojas)")


        # === SUBABAS DE RELATÓRIOS ===
        subtab_dashboard, subtab_filtro = st.tabs(["Dashboard de Ganhos/Gastos", "Filtro e Tabela"])

        with subtab_dashboard:
            
            if df_filtrado_loja.empty:
                st.warning(f"Nenhuma movimentação para {loja_filtro_relatorio} no período.")
            else:
                # --- Opção 1: Últimos 2 meses ---
                hoje = date.today()
                data_2_meses_atras = hoje.replace(day=1) - timedelta(days=1)
                data_2_meses_atras = data_2_meses_atras.replace(day=1)
                
                # --- Opção 2: Comparação Personalizada ---
                st.markdown("#### Configuração de Comparação")
                
                tipo_comparacao = st.radio(
                    "Escolha o tipo de relatório:",
                    ["Últimos 2 Meses (Padrão)", "Comparação entre Datas Personalizadas"],
                    horizontal=True,
                    key="tipo_comp_dash"
                )
                
                if tipo_comparacao == "Últimos 2 Meses (Padrão)":
                    df_relatorio = df_filtrado_loja[df_filtrado_loja["Data"] >= data_2_meses_atras]
                    st.markdown(f"**Análise:** Movimentações de **{data_2_meses_atras.strftime('%d/%m/%Y')}** até **{hoje.strftime('%d/%m/%Y')}**.")
                    
                else: # Comparação Personalizada
                    col_d_ini, col_d_fim = st.columns(2)
                    
                    with col_d_ini:
                        data_rel_inicial = st.date_input("Data Inicial do Relatório", value=data_2_meses_atras, key="rel_data_ini")
                    with col_d_fim:
                        data_rel_final = st.date_input("Data Final do Relatório", value=hoje, key="rel_data_fim")
                    
                    if data_rel_inicial > data_rel_final:
                        st.error("A data inicial não pode ser maior que a data final.")
                        df_relatorio = pd.DataFrame()
                    else:
                        df_relatorio = df_filtrado_loja[
                            (df_filtrado_loja["Data"] >= data_rel_inicial) &
                            (df_filtrado_loja["Data"] <= data_rel_final)
                        ]
                
                if df_relatorio.empty:
                    st.warning("Nenhuma movimentação encontrada no período selecionado para o dashboard.")
                else:
                    # --- Preparação dos dados para o Gráfico ---
                    df_relatorio['MesAno'] = df_relatorio['Data'].apply(lambda x: x.strftime('%Y-%m'))
                    
                    # Agrupamento por Tipo (Entrada/Saída) e Mês/Ano
                    df_grouped = df_relatorio.groupby(['MesAno', 'Tipo'])['Valor'].sum().abs().reset_index()
                    df_grouped.columns = ['MesAno', 'Tipo', 'Total']
                    
                    df_grouped = df_grouped.sort_values(by='MesAno')

                    # --- Gráfico de Barras: Ganhos x Gastos por Mês ---
                    st.markdown("### 📊 Ganhos (Entradas) vs. Gastos (Saídas)")
                    
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
                    
                    fig_bar.update_traces(texttemplate='R$ %{y:.2f}', textposition='outside')
                    fig_bar.update_layout(uniformtext_minsize=8, uniformtext_mode='hide')
                    
                    st.plotly_chart(fig_bar, use_container_width=True)

                    # --- Gráfico de Pizza: Distribuição por Forma de Pagamento ---
                    st.markdown("### 🍕 Distribuição por Forma de Pagamento (Entradas)")
                    
                    df_entradas_formas = df_relatorio[df_relatorio['Tipo'] == 'Entrada']
                    df_formas_grouped = df_entradas_formas.groupby('Forma de Pagamento')['Valor'].sum().reset_index()
                    
                    fig_pie = px.pie(
                        df_formas_grouped,
                        values='Valor',
                        names='Forma de Pagamento',
                        title='Total de Entradas por Forma de Pagamento',
                        hole=.3
                    )
                    st.plotly_chart(fig_pie, use_container_width=True)


        with subtab_filtro:
            st.subheader("📅 Filtrar Movimentações por Período e Loja")
            
            # DataFrame para o filtro de tabela é o filtrado por loja
            df_base_filtro_tabela = df_filtrado_loja

            col_data_inicial, col_data_final = st.columns(2)
            
            data_minima = df_base_filtro_tabela["Data"].min() if not df_base_filtro_tabela.empty else datetime.now().date()
            data_maxima = df_base_filtro_tabela["Data"].max() if not df_base_filtro_tabela.empty else datetime.now().date()
            
            with col_data_inicial:
                data_inicial = st.date_input("Data Inicial", value=data_minima, key="filtro_data_ini")
            with col_data_final:
                data_final = st.date_input("Data Final", value=data_maxima, key="filtro_data_fim")

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
                    st.dataframe(df_filtrado_final[colunas_para_mostrar], use_container_width=True)

                    # --- Resumo do Período Filtrado ---
                    entradas_filtro, saidas_filtro, saldo_filtro = calcular_resumo(df_filtrado_final)

                    st.markdown("#### 💰 Resumo do Período Filtrado")
                    col1_f, col2_f, col3_f = st.columns(3)
                    col1_f.metric("Entradas", f"R$ {entradas_filtro:,.2f}")
                    col2_f.metric("Saídas", f"R$ {saidas_filtro:,.2f}")
                    col3_f.metric("Saldo", f"R$ {saldo_filtro:,.2f}")
