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


def precificacao_completa():
    st.title("📊 Precificador de Produtos")
    
    # --- Configurações do GitHub para SALVAR ---
    # NOTA: Estes GITHUB_REPO/PATH_PRECFICACAO devem ser movidos para constants_and_css.py
    # para serem limpos, mas os mantemos aqui para evitar um novo erro de NameError.
    GITHUB_TOKEN = st.secrets.get("github_token", "TOKEN_FICTICIO")
    GITHUB_REPO = "ribeiromendes5014-design/Precificar"
    GITHUB_BRANCH = "main"
    PATH_PRECFICACAO = "precificacao.csv"
    ARQ_CAIXAS = "https://raw.githubusercontent.com/ribeiromendes5014-design/Precificar/main/" + PATH_PRECFICACAO
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
