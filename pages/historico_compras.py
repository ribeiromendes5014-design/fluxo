# pages/historico_compras.py

import streamlit as st
import pandas as pd
from datetime import date, timedelta
import plotly.express as px
import json
import ast

# As importações relativas estão corretas para a estrutura do projeto
from ..utils import carregar_historico_compras, salvar_historico_no_github, to_float, prox_id
from ..constants_and_css import COLUNAS_COMPRAS


def historico_compras():

    st.header("🛒 Histórico de Compras de Insumos")
    st.info("Utilize esta página para registrar produtos (insumos, materiais, estoque) comprados. Estes dados são **separados** do controle de estoque principal e do Livro Caixa.")

    if "df_compras" not in st.session_state:
        st.session_state.df_compras = carregar_historico_compras()

    df_compras = st.session_state.df_compras.copy()

    if not df_compras.empty:
        df_compras['Data'] = pd.to_datetime(df_compras['Data'], errors='coerce').dt.date
        df_compras['Quantidade'] = pd.to_numeric(df_compras['Quantidade'], errors='coerce').fillna(0).astype(int)
        df_compras['Valor Total'] = pd.to_numeric(df_compras['Valor Total'], errors='coerce').fillna(0.0)

    df_exibicao = df_compras.sort_values(by='Data', ascending=False).reset_index(drop=False)
    df_exibicao.rename(columns={'index': 'original_index'}, inplace=True)
    df_exibicao.insert(0, 'ID', df_exibicao.index + 1)

    hoje = date.today()
    primeiro_dia_mes = hoje.replace(day=1)
    if hoje.month == 12:
        proximo_mes = hoje.replace(year=hoje.year + 1, month=1, day=1)
    else:
        proximo_mes = hoje.replace(month=hoje.month + 1, day=1)
    ultimo_dia_mes = proximo_mes - timedelta(days=1)

    df_mes_atual = df_exibicao[
        (df_exibicao["Data"].apply(lambda x: pd.notna(x) and x >= primeiro_dia_mes and x <= ultimo_dia_mes)) &
        (df_exibicao["Valor Total"] > 0)
    ].copy()

    total_gasto_mes = df_mes_atual['Valor Total'].sum()

    st.markdown("---")
    st.subheader(f"📊 Resumo de Gastos - Mês de {primeiro_dia_mes.strftime('%m/%Y')}")
    st.metric(
        label="💰 Total Gasto com Compras de Insumos (Mês Atual)",
        value=f"R$ {total_gasto_mes:,.2f}"
    )
    st.markdown("---")

    tab_cadastro, tab_dashboard = st.tabs(["📝 Cadastro & Lista de Compras", "📈 Dashboard de Gastos"])

    with tab_dashboard:
        st.header("📈 Análise de Gastos com Compras")

        if df_exibicao.empty:
            st.info("Nenhum dado de compra registrado para gerar o dashboard.")
        else:
            df_gasto_por_produto = df_exibicao.groupby('Produto')['Valor Total'].sum().reset_index()
            df_gasto_por_produto = df_gasto_por_produto.sort_values(by='Valor Total', ascending=False)

            st.markdown("### 🥇 Top Produtos Mais Gastos (Valor Total)")

            if not df_gasto_por_produto.empty:
                top_n = st.slider("Mostrar Top N Produtos", min_value=5, max_value=20, value=10)
                top_produtos = df_gasto_por_produto.head(top_n)

                fig_top_produtos = px.bar(
                    top_produtos,
                    x='Produto',
                    y='Valor Total',
                    text='Valor Total',
                    title=f'Top {top_n} Produtos por Gasto Total',
                    labels={'Valor Total': 'Gasto Total (R$)', 'Produto': 'Produto'},
                    color='Valor Total',
                    color_continuous_scale=px.colors.sequential.Sunset
                )
                fig_top_produtos.update_traces(texttemplate='R$ %{y:,.2f}', textposition='outside')
                fig_top_produtos.update_layout(xaxis={'categoryorder':'total descending'}, height=500)
                st.plotly_chart(fig_top_produtos, use_container_width=True)

                st.markdown("---")
                st.markdown("### 📅 Gasto Mensal Histórico (Agregado)")

                df_temp_data = df_exibicao[df_exibicao['Data'].notna()].copy()
                df_temp_data['Data_dt'] = pd.to_datetime(df_temp_data['Data'])
                df_temp_data['MesAno'] = df_temp_data['Data_dt'].dt.strftime('%Y-%m')

                df_gasto_mensal = df_temp_data.groupby('MesAno')['Valor Total'].sum().reset_index()
                df_gasto_mensal = df_gasto_mensal.sort_values(by='MesAno')

                fig_mensal = px.line(
                    df_gasto_mensal,
                    x='MesAno',
                    y='Valor Total',
                    title='Evolução do Gasto Mensal com Compras',
                    labels={'Valor Total': 'Gasto (R$)', 'MesAno': 'Mês/Ano'},
                    markers=True
                )
                st.plotly_chart(fig_mensal, use_container_width=True)

    with tab_cadastro:

        edit_mode_compra = st.session_state.get('edit_compra_idx') is not None

        if edit_mode_compra:
            original_idx_to_edit = st.session_state.edit_compra_idx
            linha_para_editar = df_compras[df_compras.index == original_idx_to_edit]

            if not linha_para_editar.empty:
                compra_data = linha_para_editar.iloc[0]
                try:
                    default_data = pd.to_datetime(compra_data['Data']).date()
                except:
                    default_data = date.today()

                default_produto = compra_data['Produto']
                default_qtd = int(compra_data['Quantidade'])
                valor_total_compra = float(compra_data['Valor Total'])
                default_qtd_float = float(default_qtd)
                valor_unitario_existente = valor_total_compra / default_qtd_float if default_qtd_float > 0 else valor_total_compra
                default_valor = float(valor_unitario_existente)

                default_cor = compra_data['Cor']
                default_foto_url = compra_data['FotoURL']

                st.subheader("📝 Editar Compra Selecionada")
                st.warning(f"Editando item: **{default_produto}** (ID Interno: {original_idx_to_edit})")
            else:
                st.session_state.edit_compra_idx = None
                edit_mode_compra = False
                st.subheader("📝 Formulário de Registro")

        if not edit_mode_compra:
            st.subheader("📝 Formulário de Registro")
            default_data = date.today()
            default_produto = ""
            default_qtd = 1
            default_valor = 10.00
            default_cor = "#007bff"
            default_foto_url = ""

        with st.form("form_compra", clear_on_submit=not edit_mode_compra):

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                data = st.date_input("Data da Compra", value=default_data, key="compra_data_form")
                nome_produto = st.text_input("Produto/Material Comprado", value=default_produto, key="compra_nome_form")

            with col2:
                quantidade = st.number_input("Quantidade", min_value=1, value=default_qtd, step=1, key="compra_qtd_form")
                valor_unitario_input = st.number_input("Preço Unitário (R$)", min_value=0.01, format="%.2f", value=default_valor, key="compra_valor_form")

            with col3:
                cor_selecionada = st.color_picker("Cor para Destaque", value=default_cor, key="compra_cor_form")

            with col4:
                foto_url = st.text_input("URL da Foto do Produto (Opcional)", value=default_foto_url, key="compra_foto_url_form")

            valor_total_calculado = float(quantidade) * float(valor_unitario_input)
            st.markdown(f"**Custo Total Calculado:** R$ {valor_total_calculado:,.2f}")

            if edit_mode_compra:
                col_sub1, col_sub2 = st.columns(2)
                salvar_compra = col_sub1.form_submit_button("💾 Salvar Edição", type="primary", use_container_width=True)
                cancelar_edicao = col_sub2.form_submit_button("❌ Cancelar Edição", type="secondary", use_container_width=True)
            else:
                salvar_compra = st.form_submit_button("💾 Adicionar Compra", type="primary", use_container_width=True)
                cancelar_edicao = False

            if salvar_compra:
                if not nome_produto or valor_total_calculado <= 0 or quantidade <= 0:
                    st.error("Preencha todos os campos obrigatórios com valores válidos. O Custo Total deve ser maior que R$ 0,00.")
                else:
                    nova_linha = {
                        "Data": data.strftime('%Y-%m-%d'),
                        "Produto": nome_produto.strip(),
                        "Quantidade": int(quantidade),
                        "Valor Total": valor_total_calculado,
                        "Cor": cor_selecionada,
                        "FotoURL": foto_url.strip(),
                    }

                    if edit_mode_compra:
                        st.session_state.df_compras.loc[original_idx_to_edit] = pd.Series(nova_linha)
                        commit_msg = f"Edição da compra {nome_produto}"
                    else:
                        df_original = st.session_state.df_compras.iloc[:, :len(COLUNAS_COMPRAS)]
                        st.session_state.df_compras = pd.concat([df_original, pd.DataFrame([nova_linha])], ignore_index=True)
                        commit_msg = f"Nova compra registrada: {nome_produto}"

                    if salvar_historico_no_github(st.session_state.df_compras, commit_msg):
                        st.session_state.edit_compra_idx = None
                        st.cache_data.clear()
                        st.rerun()

            if cancelar_edicao:
                st.session_state.edit_compra_idx = None
                st.rerun()

        st.markdown("---")
        st.subheader("Lista e Operações de Histórico")

        with st.expander("🔍 Filtros da Lista", expanded=False):
            col_f1, col_f2 = st.columns([1, 2])

            with col_f1:
                filtro_produto = st.text_input("Filtrar por nome do Produto:", key="filtro_compra_produto_tab")

            with col_f2:
                data_range_option = st.radio(
                    "Filtrar por Período:",
                    ["Todo o Histórico", "Personalizar Data"],
                    key="filtro_compra_data_opt_tab",
                    horizontal=True
                )

            df_filtrado = df_exibicao.copy()

            if filtro_produto:
                df_filtrado = df_filtrado[df_filtrado["Produto"].astype(str).str.contains(filtro_produto, case=False, na=False)]

            if data_range_option == "Personalizar Data":
                if not df_filtrado.empty:
                    min_date_val = df_filtrado['Data'].min() if pd.notna(df_filtrado['Data'].min()) else date.today()
                    max_date_val = df_filtrado['Data'].max() if pd.notna(df_filtrado['Data'].max()) else date.today()
                else:
                    min_date_val = date.today()
                    max_date_val = date.today()

                col_date1, col_date2 = st.columns(2)
                with col_date1:
                    data_ini = st.date_input("De:", value=min_date_val, key="filtro_compra_data_ini_tab")
                with col_date2:
                    data_fim = st.date_input("Até:", value=max_date_val, key="filtro_compra_data_fim_tab")

                df_filtrado = df_filtrado[
                    (df_filtrado["Data"] >= data_ini) &
                    (df_filtrado["Data"] <= data_fim)
                ]

        if df_filtrado.empty:
            st.info("Nenhuma compra encontrada com os filtros aplicados.")
        else:
            df_filtrado['Data Formatada'] = df_filtrado['Data'].apply(lambda x: x.strftime('%d/%m/%Y') if pd.notna(x) else '')

            def highlight_color_compras(row):
                color = row['Cor']
                return [f'background-color: {color}30' for col in row.index]

            df_para_mostrar = df_filtrado.copy()
            df_para_mostrar['Foto'] = df_para_mostrar['FotoURL'].fillna('').astype(str).apply(lambda x: '📷' if x.strip() else '')

            df_display_cols = ['ID', 'Data Formatada', 'Produto', 'Quantidade', 'Valor Total', 'Foto', 'Cor', 'original_index']
            df_styling = df_para_mostrar[df_display_cols].copy()

            styled_df = df_styling.style.apply(highlight_color_compras, axis=1)
            styled_df = styled_df.hide(subset=['Cor', 'original_index'], axis=1)

            st.markdown("##### Tabela de Itens Comprados")
            st.dataframe(
                styled_df,
                use_container_width=True,
                column_config={
                    "Data Formatada": st.column_config.TextColumn("Data da Compra"),
                    "Valor Total": st.column_config.NumberColumn("Valor Total (R$)", format="R$ %.2f"),
                    "Foto": st.column_config.TextColumn("Foto"),
                },
                column_order=('ID', 'Data Formatada', 'Produto', 'Quantidade', 'Valor Total', 'Foto'),
                height=400,
                selection_mode='disabled',
                key='compras_table_styled'
            )

            st.markdown("### Operações de Edição e Exclusão")

            opcoes_compra_operacao = {
                f"ID {row['ID']} | {row['Data Formatada']} | {row['Produto']} | R$ {row['Valor Total']:,.2f}": row['original_index']
                for index, row in df_para_mostrar.iterrows()
            }
            opcoes_keys = list(opcoes_compra_operacao.keys())

            compra_selecionada_str = st.selectbox(
                "Selecione o item para Editar ou Excluir:",
                options=opcoes_keys,
                index=0,
                key="select_compra_operacao"
            )

            original_idx_selecionado = opcoes_compra_operacao.get(compra_selecionada_str)
            item_selecionado_str = compra_selecionada_str

            if original_idx_selecionado is not None:

                col_edit, col_delete = st.columns(2)

                if col_edit.button(f"✏️ Editar: {item_selecionado_str}", type="secondary", use_container_width=True):
                    st.session_state.edit_compra_idx = original_idx_selecionado
                    st.rerun()

                if col_delete.button(f"🗑️ Excluir: {item_selecionado_str}", type="primary", use_container_width=True):
                    st.session_state.df_compras = st.session_state.df_compras.drop(original_idx_selecionado, errors='ignore')

                    if salvar_historico_no_github(st.session_state.df_compras, f"Exclusão da compra {item_selecionado_str}"):
                        st.cache_data.clear()
                        st.rerun()
            else:
                st.info("Selecione um item no menu acima para editar ou excluir.")
