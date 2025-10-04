# pages/precificacao.py

import streamlit as st
import pandas as pd
import json
import ast
from datetime import date
from io import BytesIO

# Importa as funções auxiliares (que devem estar em precificar_utils.py na raiz)
from precificar_utils import (
    gerar_pdf, enviar_pdf_telegram, exibir_resultados, processar_dataframe,
    load_csv_github, hash_df, salvar_csv_no_github, extrair_produtos_pdf,
    col_defs_para, garantir_colunas_extras, render_input_por_tipo,
    TOPICO_ID # Constante
)

# Importa FATOR_CARTAO que a função usa
from constants_and_css import FATOR_CARTAO

# ==========================================================
# ⚙️ CONFIGURAÇÃO DO GITHUB (SEGURA)
# ==========================================================
# 1️⃣ Lê o token do Streamlit Secrets (sem expor valor)
GITHUB_TOKEN = st.secrets.get("github_token") or st.secrets.get("GITHUB_TOKEN", "TOKEN_FICTICIO")

# 2️⃣ Define repositório e branch corretos
GITHUB_REPO = "ribeiromendes5014-design/fluxo"
GITHUB_BRANCH = "main"
PATH_PRECFICACAO = "precificacao.csv"

# 3️⃣ Monta URL completa para leitura do CSV remoto
ARQ_CAIXAS = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{PATH_PRECFICACAO}"

# 4️⃣ Dicionário de imagens (mantido do seu código original)
imagens_dict = {}


def _garantir_data_cadastro(df):
    """
    Garante que o DataFrame tenha a coluna 'Data Cadastro'.
    Se ausente, adiciona com a data de hoje (ISO).
    Retorna o mesmo DataFrame (ou um novo válido se for None).
    Totalmente à prova de erro.
    """
    try:
        hoje = date.today().isoformat()
    except Exception:
        hoje = "2025-01-01"  # fallback seguro

    # Caso não haja DataFrame
    if df is None:
        return pd.DataFrame({"Produto": [], "Data Cadastro": [hoje]})

    # Caso seja um tipo inesperado
    if not isinstance(df, pd.DataFrame):
        return pd.DataFrame({"Produto": [], "Data Cadastro": [hoje]})

    # Garante coluna
    if "Data Cadastro" not in df.columns:
        df["Data Cadastro"] = hoje

    # Se for completamente vazio, garante estrutura mínima
    if df.empty and "Produto" not in df.columns:
        df["Produto"] = []

    return df



def exibir_relatorios(df):
    """
    Calcula e exibe as métricas de precificação, incluindo filtros por data.
    """
    st.header("Análise Detalhada de Precificação")

    # === CORREÇÃO DE ERRO: Garante que a coluna 'Data Cadastro' exista para relatórios ===
    if 'Data Cadastro' not in df.columns:
        st.warning("⚠️ **Erro na Estrutura de Dados:** A coluna 'Data Cadastro' não foi encontrada. Relatórios baseados em data não podem ser gerados. Por favor, certifique-se de que o CSV carregado ou os produtos manuais possuem esta coluna.")
        st.dataframe(df) # Exibe o DF para debug
        return
    # ======================================================================================

    # 1. Filtro de Data
    df['Data Cadastro'] = pd.to_datetime(df['Data Cadastro'])

    # Configura o filtro de data
    data_minima = df['Data Cadastro'].min().date()
    data_maxima = df['Data Cadastro'].max().date()

    # Adiciona a subaba de filtro com datas
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        data_inicio = st.date_input("🗓️ Data Inicial", value=data_minima, min_value=data_minima, max_value=data_maxima)
    with col_f2:
        data_fim = st.date_input("🗓️ Data Final", value=data_maxima, min_value=data_minima, max_value=data_maxima)

    df_filtrado = df[(df['Data Cadastro'].dt.date >= data_inicio) & (df['Data Cadastro'].dt.date <= data_fim)].copy()

    if df_filtrado.empty:
        st.info("Nenhum produto encontrado no período selecionado.")
        return

    # 2. Métricas Principais (Média de Lucro, Preços, etc.)
    st.subheader("Métricas de Desempenho")

    df_filtrado["Lucro Unitário"] = df_filtrado["Preço à Vista"] - df_filtrado["Custo Total Unitário"]
    df_filtrado["Lucro Total"] = df_filtrado["Lucro Unitário"] * df_filtrado["Qtd"]

    margem_media = df_filtrado["Margem (%)"].mean()
    preco_medio_vista = df_filtrado["Preço à Vista"].mean()
    preco_medio_cartao = df_filtrado["Preço no Cartão"].mean()
    lucro_total_estimado = df_filtrado["Lucro Total"].sum()

    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    col_m1.metric("Margem Média (%)", f"{margem_media:.2f}%")
    col_m2.metric("Preço Médio à Vista (R$)", f"R$ {preco_medio_vista:,.2f}")
    col_m3.metric("Preço Médio no Cartão (R$)", f"R$ {preco_medio_cartao:,.2f}")
    col_m4.metric("Lucro Total Estimado (R$)", f"R$ {lucro_total_estimado:,.2f}")

    # 3. Distribuição de Margem (Gráfico)
    st.markdown("---")
    st.subheader("Distribuição da Margem de Lucro")

    # Cria um histograma
    st.bar_chart(df_filtrado.groupby(pd.cut(df_filtrado["Margem (%)"], bins=10, right=False)).size(), use_container_width=True)
    st.caption("Frequência de produtos por faixa de Margem de Lucro (%).")

    # 4. Tabela Top/Bottom Performers (por Lucro Total)
    st.markdown("---")
    st.subheader("Produtos Mais/Menos Lucrativos (por Volume Total)")

    df_rank = df_filtrado.sort_values(by="Lucro Total", ascending=False).reset_index(drop=True)

    col_t1, col_t2 = st.columns(2)

    format_mapping = {
        "Preço à Vista": "R$ {:,.2f}",
        "Custo Total Unitário": "R$ {:,.2f}",
        "Margem (%)": "{:.2f}%",
        "Lucro Total": "R$ {:,.2f}"
    }

    with col_t1:
        st.write("**Top 5 Produtos por Lucro Total**")
        st.dataframe(df_rank.head(5)[["Produto", "Qtd", "Preço à Vista", "Margem (%)", "Lucro Total"]].style.format(format_mapping), use_container_width=True)

    with col_t2:
        st.write("**Bottom 5 Produtos por Lucro Total**")
        st.dataframe(df_rank.tail(5)[["Produto", "Qtd", "Preço à Vista", "Margem (%)", "Lucro Total"]].style.format(format_mapping), use_container_width=True)


def precificacao_completa():
    st.title("📊 Precificador de Produtos")

    # ==========================================================
    # 🔒 Verificação de Token (com depuração segura)
    # ==========================================================
    is_token_valid = GITHUB_TOKEN != "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"

    # Mostra um pequeno log para confirmar se o token foi lido (sem expor o valor)
    st.write("🔑 Token carregado:", ("✅ Sim" if is_token_valid else "❌ Não encontrado"))

    if not is_token_valid:
        st.error(
            "🛑 **ERRO DE AUTENTICAÇÃO:** O token do GitHub não está configurado ou é inválido.\n\n"
            "➡️ Vá até o painel de *Secrets* do Streamlit Cloud (ou o arquivo `.streamlit/secrets.toml`) "
            "e adicione a chave `github_token` com um token pessoal do GitHub.\n\n"
            "Sem isso, o app **não conseguirá salvar o arquivo** `precificacao.csv` no repositório."
        )
    else:
        st.success("✅ Token do GitHub encontrado. Salvamento no repositório habilitado.")


    # ----------------------------------------------------
    # Inicialização e Carregamento Automático
    # ----------------------------------------------------

    # 1. Inicialização de variáveis de estado, incluindo a nova coluna "Data Cadastro"
    if "produtos_manuais" not in st.session_state:
        st.session_state.produtos_manuais = pd.DataFrame(columns=[
            "Produto", "Qtd", "Custo Unitário", "Custos Extras Produto", "Margem (%)", "Imagem", "Imagem_URL", "Data Cadastro"
        ])

    # Garante a nova coluna Data Cadastro nos produtos manuais, se não existir
    if "Data Cadastro" not in st.session_state.produtos_manuais.columns:
        st.session_state.produtos_manuais["Data Cadastro"] = date.today().isoformat()

    # 2. Lógica de Carregamento Automático do CSV do GitHub (se o DF estiver vazio)
    if st.session_state.produtos_manuais.empty:
        df_inicial = load_csv_github(ARQ_CAIXAS)
        if not df_inicial.empty:

            # Garante a nova coluna 'Data Cadastro'
            if "Data Cadastro" not in df_inicial.columns:
                df_inicial["Data Cadastro"] = date.today().isoformat()

            # Garante outras colunas de inicialização
            df_inicial["Custos Extras Produto"] = df_inicial.get("Custos Extras Produto", 0.0)
            df_inicial["Imagem"] = None
            df_inicial["Imagem_URL"] = df_inicial.get("Imagem_URL", "")

            st.session_state.produtos_manuais = df_inicial.copy()
            # Processa o DataFrame com custos e margens padrão (0.0/30.0) para iniciar
            st.session_state.df_produtos_geral = processar_dataframe(
                df_inicial, 0.0, 0.0, "Margem fixa", 30.0
            )

            # === GARANTIA ADICIONAL: Cria 'Data Cadastro' antes do merge ===
            st.session_state.produtos_manuais = _garantir_data_cadastro(st.session_state.produtos_manuais)
            st.session_state.df_produtos_geral = _garantir_data_cadastro(st.session_state.df_produtos_geral)

            st.session_state.df_produtos_geral = st.session_state.df_produtos_geral.merge(
                st.session_state.produtos_manuais[['Produto', 'Data Cadastro']],
                on='Produto',
                how='left'
            )

            st.toast("✅ Dados de precificação carregados automaticamente do GitHub!", icon="🚀")


    # 3. Inicialização de df_produtos_geral com dados de exemplo (se necessário e não carregado)
    if "df_produtos_geral" not in st.session_state or st.session_state.df_produtos_geral.empty:
        exemplo_data = [
            {"Produto": "Produto A", "Qtd": 10, "Custo Unitário": 5.0, "Margem (%)": 20, "Preço à Vista": 6.0, "Preço no Cartão": 6.5, "Data Cadastro": date.today().isoformat()},
            {"Produto": "Produto B", "Qtd": 5, "Custo Unitário": 3.0, "Margem (%)": 15, "Preço à Vista": 3.5, "Preço no Cartão": 3.8, "Data Cadastro": date.today().isoformat()},
        ]
        df_base = pd.DataFrame(exemplo_data)
        df_base["Custos Extras Produto"] = 0.0
        df_base["Imagem"] = None
        df_base["Imagem_URL"] = ""

        st.session_state.df_produtos_geral = processar_dataframe(df_base, 0.0, 0.0, "Margem fixa", 30.0)
        st.session_state.produtos_manuais = df_base.copy()

        # Garante Data Cadastro
        st.session_state.produtos_manuais = _garantir_data_cadastro(st.session_state.produtos_manuais)
        st.session_state.df_produtos_geral = _garantir_data_cadastro(st.session_state.df_produtos_geral)

        st.session_state.df_produtos_geral = st.session_state.df_produtos_geral.merge(
            st.session_state.produtos_manuais[['Produto', 'Data Cadastro']],
            on='Produto',
            how='left'
        )

    # Carrega estados de custos e margem
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
    # Lógica de Salvamento Automático (Mantida para edições e exclusões)
    # ----------------------------------------------------

    # Prepara o DataFrame para salvar: remove a coluna 'Imagem' que contém bytes
    df_to_hash = st.session_state.produtos_manuais.drop(columns=["Imagem"], errors='ignore')

    # 1. Inicializa o hash para o estado da precificação
    if "hash_precificacao" not in st.session_state:
        st.session_state.hash_precificacao = hash_df(df_to_hash)

    # 2. Verifica se houve alteração nos produtos manuais para salvar automaticamente
    # E verifica se o token é válido antes de tentar salvar!
    novo_hash = hash_df(df_to_hash)
    if novo_hash != st.session_state.hash_precificacao and is_token_valid:
        if novo_hash != "error": # Evita salvar se a função hash falhou
            try: # Adiciona bloco de tratamento de erro para salvar automaticamente
                salvar_csv_no_github(
                    GITHUB_TOKEN,
                    GITHUB_REPO,
                    PATH_PRECFICACAO,
                    df_to_hash, # Salva o df sem a coluna 'Imagem'
                    GITHUB_BRANCH,
                    mensagem="♻️ Alteração automática na precificação"
                )
                st.session_state.hash_precificacao = novo_hash
            except Exception as e:
                # Se falhar aqui (incluindo 401), o erro será capturado e exibido.
                st.error(f"❌ Falha no salvamento automático! Verifique as permissões do seu token. Erro: {e}")


    # ----------------------------------------------------
    # Tabela Geral (com Edição e Exclusão)
    # ----------------------------------------------------
    st.subheader("Produtos cadastrados (Clique no índice da linha e use DEL para excluir)")

    cols_display = [
        "Produto", "Qtd", "Custo Unitário", "Custos Extras Produto",
        "Custo Total Unitário", "Margem (%)", "Preço à Vista", "Preço no Cartão", "Data Cadastro"
    ]
    cols_to_show = [col for col in cols_display if col in st.session_state.df_produtos_geral.columns]

    editado_df = st.data_editor(
        st.session_state.df_produtos_geral[cols_to_show],
        num_rows="dynamic", # Permite que o usuário adicione ou remova linhas
        use_container_width=True,
        column_config={"Data Cadastro": st.column_config.DatetimeColumn(format="YYYY-MM-DD")}, # Formata a data
        key="editor_produtos_geral"
    )

    original_len = len(st.session_state.df_produtos_geral)
    edited_len = len(editado_df)

    # Lógica de Sincronização e Edição
    if edited_len < original_len:
        # Exclusão
        produtos_manuais_filtrado = st.session_state.produtos_manuais[
            st.session_state.produtos_manuais['Produto'].isin(editado_df['Produto'])
        ].copy()

        st.session_state.produtos_manuais = produtos_manuais_filtrado.reset_index(drop=True)
        st.session_state.df_produtos_geral = processar_dataframe(
            st.session_state.produtos_manuais, frete_total, custos_extras, modo_margem, margem_fixa
        )
        # === CORREÇÃO DE ERRO: Garante que a coluna 'Data Cadastro' é mantida no DF geral após processamento ===
        st.session_state.produtos_manuais = _garantir_data_cadastro(st.session_state.produtos_manuais)
        st.session_state.df_produtos_geral = _garantir_data_cadastro(st.session_state.df_produtos_geral)

        st.session_state.df_produtos_geral = st.session_state.df_produtos_geral.merge(
            st.session_state.produtos_manuais[['Produto', 'Data Cadastro']],
            on='Produto',
            how='left'
        )
        # =======================================================================================================
        st.success("✅ Produto excluído da lista e sincronizado.")
        st.rerun()

    elif not editado_df.equals(st.session_state.df_produtos_geral[cols_to_show]):
        # Edição de Dados
        for idx, row in editado_df.iterrows():
            produto_nome = str(row.get('Produto'))
            manual_idx = st.session_state.produtos_manuais[st.session_state.produtos_manuais['Produto'] == produto_nome].index

            if not manual_idx.empty:
                manual_idx = manual_idx[0]

                # Sincroniza campos editáveis
                st.session_state.produtos_manuais.loc[manual_idx, "Produto"] = produto_nome
                st.session_state.produtos_manuais.loc[manual_idx, "Qtd"] = row.get("Qtd", 1)
                st.session_state.produtos_manuais.loc[manual_idx, "Custo Unitário"] = row.get("Custo Unitário", 0.0)
                st.session_state.produtos_manuais.loc[manual_idx, "Margem (%)"] = row.get("Margem (%)", margem_fixa)
                st.session_state.produtos_manuais.loc[manual_idx, "Custos Extras Produto"] = row.get("Custos Extras Produto", 0.0)
                # Mantém a data de cadastro original

        # Recalcula
        st.session_state.df_produtos_geral = processar_dataframe(
            st.session_state.produtos_manuais, frete_total, custos_extras, modo_margem, margem_fixa
        )
        # === CORREÇÃO DE ERRO: Garante que a coluna 'Data Cadastro' é mantida no DF geral após processamento ===
        st.session_state.produtos_manuais = _garantir_data_cadastro(st.session_state.produtos_manuais)
        st.session_state.df_produtos_geral = _garantir_data_cadastro(st.session_state.df_produtos_geral)

        st.session_state.df_produtos_geral = st.session_state.df_produtos_geral.merge(
            st.session_state.produtos_manuais[['Produto', 'Data Cadastro']],
            on='Produto',
            how='left'
        )
        # =======================================================================================================

        st.success("✅ Dados editados e precificação recalculada!")
        st.rerun()

    elif edited_len > original_len:
        st.warning("⚠️ Use o formulário 'Novo Produto Manual' para adicionar produtos.")
        st.session_state.df_produtos_geral = st.session_state.df_produtos_geral
        st.rerun()


    if st.button("📤 Gerar PDF e enviar para Telegram", key='precificacao_pdf_button'):
        if st.session_state.df_produtos_geral.empty:
            st.warning("⚠️ Nenhum produto para gerar PDF.")
        else:
            pdf_io = gerar_pdf(st.session_state.df_produtos_geral)
            enviar_pdf_telegram(pdf_io, st.session_state.df_produtos_geral, thread_id=TOPICO_ID)

    st.markdown("---")

    # ----------------------------------------------------
    # Abas de Precificação (Remoção da aba PDF e adição de Relatórios)
    # ----------------------------------------------------

    tab_manual, tab_relatorios, tab_github = st.tabs([
        "✍️ Precificador Manual",
        "📈 Relatórios Detalhados",
        "⚙️ Configuração / GitHub"
    ])

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
                st.session_state.df_produtos_geral = processar_dataframe(
                    st.session_state.produtos_manuais,
                    frete_total,
                    custos_extras,
                    modo_margem,
                    margem_fixa
                )
                # === CORREÇÃO DE ERRO: Garante que a coluna 'Data Cadastro' é mantida no DF geral após processamento ===
                st.session_state.produtos_manuais = _garantir_data_cadastro(st.session_state.produtos_manuais)
                st.session_state.df_produtos_geral = _garantir_data_cadastro(st.session_state.df_produtos_geral)

                st.session_state.df_produtos_geral = st.session_state.df_produtos_geral.merge(
                    st.session_state.produtos_manuais[['Produto', 'Data Cadastro']],
                    on='Produto',
                    how='left'
                )
                # =======================================================================================================
                st.success("✅ Rateio aplicado! Verifique a tabela principal.")
                st.rerun()

        with aba_prec_manual:
            if st.session_state.get("rerun_after_add"):
                del st.session_state["rerun_after_add"]
                st.rerun()

            st.subheader("Adicionar novo produto")

            col1, col2 = st.columns(2)
            with col1:
                produto = st.text_input("📝 Nome do Produto", key="input_produto_manual")
                quantidade = st.number_input("📦 Quantidade", min_value=1, step=1, key="input_quantidade_manual")
                valor_pago = st.number_input("💰 Valor Pago (Custo Unitário Base R$)", min_value=0.0, step=0.01, key="input_valor_pago_manual")
                imagem_url = st.text_input("🔗 URL da Imagem (opcional)", key="input_imagem_url_manual")

            with col2:
                valor_default_rateio = st.session_state.get("rateio_manual", 0.0)
                custo_extra_produto = st.number_input(
                    "💰 Custos extras do Produto (R$) + Rateio Global", min_value=0.0, step=0.01, value=valor_default_rateio, key="input_custo_extra_manual"
                )
                preco_final_sugerido = st.number_input(
                    "💸 Valor Final Sugerido (Preço à Vista) (R$)", min_value=0.0, step=0.01, key="input_preco_sugerido_manual"
                )
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

            preco_no_cartao_calc = preco_a_vista_calc / FATOR_CARTAO

            st.markdown(f"**Preço à Vista Calculado:** R$ {preco_a_vista_calc:,.2f}")
            st.markdown(f"**Preço no Cartão Calculado:** R$ {preco_no_cartao_calc:,.2f}")

            with st.form("form_submit_manual"):
                adicionar_produto = st.form_submit_button("➕ Adicionar Produto (Manual)")
                if adicionar_produto:
                    if produto and quantidade > 0 and valor_pago >= 0:
                        imagem_bytes = None
                        url_salvar = ""

                        if imagem_file is not None:
                            imagem_bytes = imagem_file.read()
                            imagens_dict[produto] = imagem_bytes

                        elif imagem_url.strip():
                            url_salvar = imagem_url.strip()

                        novo_produto_data = {
                            "Produto": [produto],
                            "Qtd": [quantidade],
                            "Custo Unitário": [valor_pago],
                            "Custos Extras Produto": [custo_extra_produto],
                            "Margem (%)": [margem_manual],
                            "Imagem": [imagem_bytes],
                            "Imagem_URL": [url_salvar],
                            "Data Cadastro": [date.today().isoformat()] # Adiciona data de hoje
                        }
                        novo_produto = pd.DataFrame(novo_produto_data)

                        st.session_state.produtos_manuais = pd.concat(
                            [st.session_state.produtos_manuais, novo_produto],
                            ignore_index=True
                        ).reset_index(drop=True)

                        st.session_state.df_produtos_geral = processar_dataframe(
                            st.session_state.produtos_manuais,
                            frete_total,
                            custos_extras,
                            modo_margem,
                            margem_fixa
                        )
                        # === CORREÇÃO DE ERRO: Garante que a coluna 'Data Cadastro' é mantida no DF geral após processamento ===
                        st.session_state.produtos_manuais = _garantir_data_cadastro(st.session_state.produtos_manuais)
                        st.session_state.df_produtos_geral = _garantir_data_cadastro(st.session_state.df_produtos_geral)

                        st.session_state.df_produtos_geral = st.session_state.df_produtos_geral.merge(
                            st.session_state.produtos_manuais[['Produto', 'Data Cadastro']],
                            on='Produto',
                            how='left'
                        )
                        # =======================================================================================================

                        # ==========================================================
                        # BLOCO: FORÇAR O SALVAMENTO NO GITHUB APÓS ADIÇÃO (COM TRATAMENTO DE ERRO)
                        # ==========================================================
                        if is_token_valid: # Adiciona a verificação do token
                            df_to_save = st.session_state.produtos_manuais.drop(columns=["Imagem"], errors='ignore')
                            novo_hash_salvar = hash_df(df_to_save)

                            if novo_hash_salvar != "error":
                                try: # Tenta salvar no GitHub
                                    salvar_csv_no_github(
                                        GITHUB_TOKEN,
                                        GITHUB_REPO,
                                        PATH_PRECFICACAO,
                                        df_to_save,
                                        GITHUB_BRANCH,
                                        mensagem="➕ Produto adicionado manualmente via formulário"
                                    )
                                    # Atualiza o hash de controle após o salvamento
                                    st.session_state.hash_precificacao = novo_hash_salvar
                                    st.toast("💾 Produto salvo no GitHub!", icon="✅")
                                except Exception as e:
                                    # ---- MELHORIA NA MENSAGEM DE ERRO ----
                                    st.error(f"❌ Falha ao salvar no GitHub! Erro: {e}")
                                    st.warning(
                                        "⚠️ **Ação Necessária:** Uma falha no salvamento (como o erro 401) indica um problema de credenciais. "
                                        "Verifique se o seu `github_token` nos Streamlit Secrets é válido e se ele possui a permissão **'repo'** no GitHub."
                                    )
                                    # ------------------------------------
                            else:
                                st.error("❌ Falha ao calcular o hash para salvar no GitHub.")
                        else:
                            st.warning("Produto adicionado localmente, mas não salvo no GitHub devido à falta/invalidez do Token.")
                        # ==========================================================

                        st.success("✅ Produto adicionado!")
                        st.session_state["rerun_after_add"] = True
                    else:
                        st.warning("⚠️ Preencha todos os campos obrigatórios.")

            st.markdown("---")
            st.subheader("Produtos adicionados manualmente (com botão de Excluir individual)")

            produtos = st.session_state.produtos_manuais

            if produtos.empty:
                st.info("⚠️ Nenhum produto cadastrado manualmente.")
            else:
                if "produto_para_excluir" not in st.session_state:
                    st.session_state["produto_para_excluir"] = None

                for i, row in produtos.iterrows():
                    cols = st.columns([4, 1])
                    with cols[0]:
                        custo_unit_val = row.get('Custo Unitário', 0.0)
                        st.write(f"**{row['Produto']}** — Quantidade: {row['Qtd']} — Custo Unitário Base: R$ {custo_unit_val:.2f}")
                    with cols[1]:
                        if st.button(f"❌ Excluir", key=f"excluir_{i}"):
                            st.session_state["produto_para_excluir"] = i
                            break

                if st.session_state["produto_para_excluir"] is not None:
                    i = st.session_state["produto_para_excluir"]
                    produto_nome_excluido = produtos.loc[i, "Produto"]

                    st.session_state.produtos_manuais = produtos.drop(i).reset_index(drop=True)

                    st.session_state.df_produtos_geral = processar_dataframe(
                        st.session_state.produtos_manuais,
                        frete_total,
                        custos_extras,
                        modo_margem,
                        margem_fixa
                    )
                    # === CORREÇÃO DE ERRO: Garante que a coluna 'Data Cadastro' é mantida no DF geral após processamento ===
                    st.session_state.produtos_manuais = _garantir_data_cadastro(st.session_state.produtos_manuais)
                    st.session_state.df_produtos_geral = _garantir_data_cadastro(st.session_state.df_produtos_geral)

                    st.session_state.df_produtos_geral = st.session_state.df_produtos_geral.merge(
                        st.session_state.produtos_manuais[['Produto', 'Data Cadastro']],
                        on='Produto',
                        how='left'
                    )
                    # =======================================================================================================

                    st.session_state["produto_para_excluir"] = None
                    st.success(f"✅ Produto '{produto_nome_excluido}' removido da lista manual.")
                    st.rerun()

            if "df_produtos_geral" in st.session_state and not st.session_state.df_produtos_geral.empty:
                exibir_resultados(st.session_state.df_produtos_geral, imagens_dict)
            else:
                st.info("⚠️ Nenhum produto processado para exibir.")

    # === Tab Relatórios Detalhados (NOVA ABA) ===
    with tab_relatorios:
        st.markdown("---")
        if not st.session_state.df_produtos_geral.empty:
            # Passa uma cópia para evitar warnings de modificação no dataframe
            exibir_relatorios(st.session_state.df_produtos_geral.copy())
        else:
            st.info("Cadastre produtos na aba 'Precificador Manual' para visualizar os relatórios.")


    # === Tab Configuração / GitHub (Ajustada) ===
    with tab_github:
        st.markdown("---")
        st.header("⚙️ Status de Sincronização e Configuração")

        # Indica o status real do token usado
        if is_token_valid:
            st.success("✅ O Token do GitHub está presente e pronto para salvar.")
        else:
            st.warning("⚠️ O Token do GitHub está usando um placeholder. Não será possível salvar no repositório.")

        st.info("O arquivo **precificacao.csv** do GitHub agora é carregado **automaticamente** ao iniciar a aplicação.")

        if st.session_state.df_produtos_geral.empty:
             st.warning("⚠️ Nenhum dado carregado. Verifique a aba 'Precificador Manual' para cadastrar ou tente recarregar.")
        else:
            st.success(f"✅ Última sincronização de dados: {date.today().strftime('%d/%m/%Y')}")
            if st.button("🔄 Forçar Recarregamento Manual do CSV do GitHub"):
                # Lógica de recarregamento forçado
                df_exemplo = load_csv_github(ARQ_CAIXAS)
                if not df_exemplo.empty:
                    if "Data Cadastro" not in df_exemplo.columns:
                        df_exemplo["Data Cadastro"] = date.today().isoformat()
                    df_exemplo["Custos Extras Produto"] = df_exemplo.get("Custos Extras Produto", 0.0)
                    df_exemplo["Imagem"] = None
                    df_exemplo["Imagem_URL"] = df_exemplo.get("Imagem_URL", "")

                    st.session_state.produtos_manuais = df_exemplo.copy()
                    st.session_state.df_produtos_geral = processar_dataframe(
                        df_exemplo, frete_total, custos_extras, modo_margem, margem_fixa
                    )
                    # === CORREÇÃO DE ERRO: Garante que a coluna 'Data Cadastro' é mantida no DF geral após processamento ===
                    st.session_state.produtos_manuais = _garantir_data_cadastro(st.session_state.produtos_manuais)
                    st.session_state.df_produtos_geral = _garantir_data_cadastro(st.session_state.df_produtos_geral)

                    st.session_state.df_produtos_geral = st.session_state.df_produtos_geral.merge(
                        st.session_state.produtos_manuais[['Produto', 'Data Cadastro']],
                        on='Produto',
                        how='left'
                    )
                    # =======================================================================================================

                    st.success("✅ CSV recarregado e processado com sucesso!")
                    st.rerun()
                else:
                    st.error("❌ Erro ao carregar o CSV. Verifique o caminho e permissões.")
