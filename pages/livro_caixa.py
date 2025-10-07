# pages/livro_caixa.py

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
import json
import ast
import hashlib # Importação necessária para gerar o RecorrenciaID
import time # Adicionando time para garantir que COMMIT_MESSAGE não seja uma constante vazia

# Define COMMIT_MESSAGE se não for importado, para evitar NameError no else:
try:
    from constants_and_css import COMMIT_MESSAGE
except ImportError:
    COMMIT_MESSAGE = "Nova Movimentação Registrada" # Valor padrão de segurança

# ==============================================================================
# Bloco de Importação das Funções Auxiliares do utils.py
# ==============================================================================
from utils import (
    inicializar_produtos, carregar_livro_caixa, ajustar_estoque, to_float,
    salvar_dados_no_github, processar_dataframe, calcular_resumo,
    calcular_valor_em_aberto, format_produtos_resumo, ler_codigo_barras_api,
    callback_adicionar_manual, callback_adicionar_estoque, salvar_produtos_no_github,
    add_months, carregar_promocoes, norm_promocoes
)

from constants_and_css import (
    LOJAS_DISPONIVEIS, CATEGORIAS_SAIDA, FORMAS_PAGAMENTO, FATOR_CARTAO,
    COMMIT_MESSAGE_EDIT, COMMIT_MESSAGE_DELETE
)

# ==============================================================================
# 💡 MELHORIA SUGERIDA APLICADA AQUI
# ==============================================================================
def highlight_value(row):
    """Função auxiliar para colorir o valor na tabela de movimentações."""
    color = row.get('Cor_Valor', 'black')
    return [f'color: {color}' if col == 'Valor' else '' for col in row.index]



def livro_caixa():

    st.header("📘 Livro Caixa - Gerenciamento de Movimentações")

    produtos = inicializar_produtos()

    if "df" not in st.session_state: st.session_state.df = carregar_livro_caixa()
    for col in ['RecorrenciaID', 'TransacaoPaiID']:
        if col not in st.session_state.df.columns: st.session_state.df[col] = ''

    if "produtos" not in st.session_state: st.session_state.produtos = produtos
    if "lista_produtos" not in st.session_state: st.session_state.lista_produtos = []
    if "edit_id" not in st.session_state: st.session_state.edit_id = None
    if "operacao_selecionada" not in st.session_state: st.session_state.operacao_selecionada = "Editar"
    if "cb_lido_livro_caixa" not in st.session_state: st.session_state.cb_lido_livro_caixa = ""
    if "edit_id_loaded" not in st.session_state: st.session_state.edit_id_loaded = None
    if "cliente_selecionado_divida" not in st.session_state: st.session_state.cliente_selecionado_divida = None
    if "divida_parcial_id" not in st.session_state: st.session_state.divida_parcial_id = None
    if "divida_a_quitar" not in st.session_state: st.session_state.divida_a_quitar = None

    abas_validas = ["📝 Nova Movimentação", "📋 Movimentações e Resumo", "📈 Relatórios e Filtros"]
    if "aba_ativa_livro_caixa" not in st.session_state or str(st.session_state.aba_ativa_livro_caixa) not in abas_validas:
        st.session_state.aba_ativa_livro_caixa = abas_validas[0]

    df_exibicao = st.session_state.df.copy()
    df_dividas = st.session_state.df

    produtos_para_venda = produtos[produtos["PaiID"].notna() | produtos["PaiID"].isnull()].copy()
    opcoes_produtos = [""] + produtos_para_venda.apply(
        lambda row: f"{row.ID} | {row.Nome} ({row.Marca}) | Estoque: {row.Quantidade}", axis=1
    ).tolist()
    OPCAO_MANUAL = "Adicionar Item Manual (Sem Controle de Estoque)"
    opcoes_produtos.append(OPCAO_MANUAL)

    def extrair_id_do_nome(opcoes_str):
        if ' | ' in opcoes_str: return opcoes_str.split(' | ')[0]
        return None

    def encontrar_opcao_por_cb(codigo_barras, produtos_df, opcoes_produtos_list):
        if not codigo_barras: return None
        produto_encontrado = produtos_df[produtos_df["CodigoBarras"] == codigo_barras]
        if not produto_encontrado.empty:
            produto_id = produto_encontrado.iloc[0]["ID"]
            for opcao in opcoes_produtos_list:
                if opcao.startswith(f"{produto_id} |"):
                    return opcao
        return None

    if "input_nome_prod_manual" not in st.session_state: st.session_state.input_nome_prod_manual = ""
    if "input_qtd_prod_manual" not in st.session_state: st.session_state.input_qtd_prod_manual = 1.0
    if "input_preco_prod_manual" not in st.session_state: st.session_state.input_preco_prod_manual = 0.01
    if "input_custo_prod_manual" not in st.session_state: st.session_state.input_custo_prod_manual = 0.00
    if "input_produto_selecionado" not in st.session_state: st.session_state.input_produto_selecionado = ""

    edit_mode = st.session_state.edit_id is not None
    movimentacao_para_editar = None
    default_loja = LOJAS_DISPONIVEIS[0]
    default_data = datetime.now().date()
    default_cliente = ""
    default_valor = 0.01
    default_forma = "Dinheiro"
    default_tipo = "Entrada"
    default_produtos_json = ""
    default_categoria = CATEGORIAS_SAIDA[0]
    default_status = "Realizada"
    default_data_pagamento = None

    if edit_mode:
        original_idx_to_edit = st.session_state.edit_id
        linha_df_exibicao = df_exibicao[df_exibicao['original_index'] == original_idx_to_edit]
        if not linha_df_exibicao.empty:
            movimentacao_para_editar = linha_df_exibicao.iloc[0]
            default_loja = movimentacao_para_editar['Loja']
            default_data = movimentacao_para_editar['Data'] if pd.notna(movimentacao_para_editar['Data']) else datetime.now().date()
            default_cliente = movimentacao_para_editar['Cliente']
            default_valor = abs(movimentacao_para_editar['Valor']) if movimentacao_para_editar['Valor'] != 0 else 0.01
            default_forma = movimentacao_para_editar['Forma de Pagamento']
            default_tipo = movimentacao_para_editar['Tipo']
            default_produtos_json = movimentacao_para_editar['Produtos Vendidos'] if pd.notna(movimentacao_para_editar['Produtos Vendidos']) else ""
            default_categoria = movimentacao_para_editar['Categoria']
            default_status = movimentacao_para_editar['Status']
            default_data_pagamento = movimentacao_para_editar['Data Pagamento'] if pd.notna(movimentacao_para_editar['Data Pagamento']) else (movimentacao_para_editar['Data'] if movimentacao_para_editar['Status'] == 'Realizada' else None)
            if st.session_state.edit_id_loaded != original_idx_to_edit:
                if default_tipo == "Entrada" and default_produtos_json:
                    try:
                        produtos_list = ast.literal_eval(default_produtos_json.replace("'", '"'))
                        for p in produtos_list:
                            p['Quantidade'] = float(p.get('Quantidade', 0))
                            p['Preço Unitário'] = float(p.get('Preço Unitário', 0))
                            p['Custo Unitário'] = float(p.get('Custo Unitário', 0))
                            p['Produto_ID'] = str(p.get('Produto_ID', ''))
                        st.session_state.lista_produtos = [p for p in produtos_list if p['Quantidade'] > 0]
                    except:
                        st.session_state.lista_produtos = []
                else:
                    st.session_state.lista_produtos = []
                st.session_state.edit_id_loaded = original_idx_to_edit
                st.session_state.cb_lido_livro_caixa = ""
            st.warning(f"Modo EDIÇÃO ATIVO: Movimentação ID {movimentacao_para_editar['ID Visível']}")
        else:
            st.session_state.edit_id = None
            st.session_state.edit_id_loaded = None
            st.session_state.lista_produtos = []
            edit_mode = False
            st.info("Movimentação não encontrada, saindo do modo de edição.")
            st.rerun()
    else:
        if st.session_state.edit_id_loaded is not None:
             st.session_state.edit_id_loaded = None
             st.session_state.lista_produtos = []
        if st.session_state.cliente_selecionado_divida and st.session_state.cliente_selecionado_divida != "CHECKED":
             st.session_state.cliente_selecionado_divida = None

    tab_nova_mov, tab_mov, tab_rel = st.tabs(abas_validas)

    with tab_nova_mov:
        st.subheader("Nova Movimentação" if not edit_mode else "Editar Movimentação Existente")
        if 'divida_a_quitar' in st.session_state and st.session_state.divida_a_quitar is not None:
            idx_quitar = st.session_state.divida_a_quitar
            try:
                divida_para_quitar = st.session_state.df.loc[idx_quitar].copy()
            except KeyError:
                st.session_state.divida_a_quitar = None
                st.error("Erro: A dívida selecionada não foi encontrada. Tente novamente.")
                st.rerun()
            valor_em_aberto = calcular_valor_em_aberto(divida_para_quitar)
            if valor_em_aberto <= 0.01:
                st.session_state.divida_a_quitar = None
                st.warning("Dívida já quitada.")
                st.rerun()
            st.subheader(f"✅ Quitar Dívida: {divida_para_quitar['Cliente']}")
            st.info(f"Valor Total em Aberto: **R$ {valor_em_aberto:,.2f}**")
            with st.form("form_quitar_divida_rapida"):
                col_q1, col_q2, col_q3 = st.columns(3)
                with col_q1:
                    valor_pago = st.number_input(f"Valor Pago (Máx: R$ {valor_em_aberto:,.2f})", 0.01, valor_em_aberto, valor_em_aberto, format="%.2f", key="input_valor_pago_quitar")
                with col_q2:
                    data_conclusao = st.date_input("Data do Pagamento", date.today(), key="data_conclusao_quitar")
                with col_q3:
                    forma_pagt_concluir = st.selectbox("Forma de Pagamento", FORMAS_PAGAMENTO, key="forma_pagt_quitar")
                concluir, cancelar_quitacao = st.form_submit_button("✅ Registrar Pagamento", use_container_width=True, type="primary"), st.form_submit_button("❌ Cancelar", use_container_width=True)
                if cancelar_quitacao:
                    st.session_state.divida_a_quitar = None
                    st.rerun()
                if concluir:
                    valor_restante = round(valor_em_aberto - valor_pago, 2)
                    idx_original = idx_quitar
                    row_original = divida_para_quitar
                    nova_transacao_pagamento = {
                        "Data": data_conclusao, "Loja": row_original['Loja'], "Cliente": f"{row_original['Cliente'].split(' (')[0]} (Pagto de R$ {valor_pago:,.2f})",
                        "Valor": valor_pago if row_original['Tipo'] == 'Entrada' else -valor_pago, "Forma de Pagamento": forma_pagt_concluir, "Tipo": row_original['Tipo'],
                        "Produtos Vendidos": row_original['Produtos Vendidos'], "Categoria": row_original['Categoria'], "Status": "Realizada", "Data Pagamento": data_conclusao,
                        "RecorrenciaID": row_original['RecorrenciaID'], "TransacaoPaiID": idx_original
                    }
                    st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([nova_transacao_pagamento])], ignore_index=True)
                    if valor_restante > 0.01:
                        st.session_state.df.loc[idx_original, 'Valor'] = valor_restante if row_original['Tipo'] == 'Entrada' else -valor_restante
                        st.session_state.df.loc[idx_original, 'Cliente'] = f"{row_original['Cliente'].split(' (')[0]} (EM ABERTO: R$ {valor_restante:,.2f})"
                        commit_msg = f"Pagamento parcial de R$ {valor_pago:,.2f}. Resta R$ {valor_restante:,.2f}."
                    else:
                        st.session_state.df = st.session_state.df.drop(idx_original, errors='ignore')
                        if row_original["Tipo"] == "Entrada" and row_original["Produtos Vendidos"]:
                            try:
                                produtos_vendidos = ast.literal_eval(row_original['Produtos Vendidos'])
                                for item in produtos_vendidos:
                                    if item.get("Produto_ID"): ajustar_estoque(item["Produto_ID"], item["Quantidade"], "debitar")
                                if salvar_produtos_no_github(st.session_state.produtos, "Débito de estoque"): inicializar_produtos.clear()
                            except: st.warning("Falha no débito do estoque.")
                        commit_msg = f"Pagamento total de R$ {valor_pago:,.2f} da dívida."
                    if salvar_dados_no_github(st.session_state.df, commit_msg):
                        st.session_state.divida_a_quitar, st.session_state.cliente_selecionado_divida = None, None
                        st.cache_data.clear()
                        st.rerun()
            st.stop()
        
        col_principal_1, col_principal_2 = st.columns([1, 1])
        with col_principal_1:
            opcoes_tipo = ["Entrada", "Saída", "Empréstimo"]
            default_index_tipo = opcoes_tipo.index(default_tipo) if default_tipo in opcoes_tipo else 0
            tipo = st.radio("Tipo", opcoes_tipo, index=default_index_tipo, key="input_tipo", disabled=edit_mode)
        
        is_recorrente, status_selecionado, data_primeira_parcela, valor_parcela, nome_despesa_recorrente, num_parcelas, valor_calculado, produtos_vendidos_json, categoria_selecionada = False, default_status, date.today().replace(day=1) + timedelta(days=32), default_valor, default_cliente, 1, 0.0, "", default_categoria
        is_emprestimo, emprestimo_ja_gasto, categoria_gasto_emprestimo = False, None, None

        if tipo == "Entrada":
            with col_principal_2:
                cliente = st.text_input("Nome do Cliente", value=default_cliente, key="input_cliente_form", on_change=lambda: st.session_state.update(cliente_selecionado_divida="CHECKED", edit_id=None, divida_a_quitar=None), disabled=edit_mode)
                if cliente.strip() and not edit_mode:
                    df_dividas_cliente = df_exibicao[(df_exibicao["Cliente"].astype(str).str.lower().str.startswith(cliente.strip().lower())) & (df_exibicao["Status"] == "Pendente") & (df_exibicao["Tipo"] == "Entrada")].sort_values(by="Data Pagamento").copy()
                    if not df_dividas_cliente.empty:
                        total_divida, num_dividas, divida_mais_antiga = df_dividas_cliente["Valor"].abs().round(2).sum(), df_dividas_cliente.shape[0], df_dividas_cliente.iloc[0]
                        valor_divida_antiga = calcular_valor_em_aberto(divida_mais_antiga)
                        original_idx_divida = divida_mais_antiga['original_index']
                        vencimento_str = divida_mais_antiga['Data Pagamento'].strftime('%d/%m/%Y') if pd.notna(divida_mais_antiga['Data Pagamento']) else "S/ Data"
                        st.session_state.cliente_selecionado_divida = divida_mais_antiga.name
                        st.warning(f"💰 Dívida em Aberto para {cliente}: R$ {valor_divida_antiga:,.2f}")
                        st.info(f"Total Pendente: **R$ {total_divida:,.2f}**. Vencimento mais antigo: **{vencimento_str}**")
                        col_btn_add, col_btn_conc, col_btn_canc = st.columns(3)
                        if col_btn_add.button("➕ Adicionar à Dívida", use_container_width=True, type="secondary"):
                            st.session_state.edit_id, st.session_state.edit_id_loaded = original_idx_divida, None
                            st.rerun()
                        if col_btn_conc.button("✅ Pagar Dívida", use_container_width=True, type="primary"):
                            st.session_state.divida_a_quitar, st.session_state.edit_id, st.session_state.edit_id_loaded, st.session_state.lista_produtos = divida_mais_antiga['original_index'], None, None, []
                            st.rerun()
                        if col_btn_canc.button("🗑️ Cancelar Dívida", use_container_width=True):
                            df_to_delete = df_dividas_cliente.copy()
                            for idx in df_to_delete['original_index'].tolist():
                                st.session_state.df = st.session_state.df.drop(idx, errors='ignore')
                            if salvar_dados_no_github(st.session_state.df, f"Cancelamento de {num_dividas} dívida(s) de {cliente.strip()}"):
                                st.session_state.cliente_selecionado_divida, st.session_state.edit_id_loaded = None, None
                                st.cache_data.clear()
                                st.success(f"{num_dividas} dívida(s) cancelada(s).")
                                st.rerun()
                    else:
                        st.session_state.cliente_selecionado_divida = None
                st.markdown("#### 🛍️ Detalhes dos Produtos")
                if st.session_state.lista_produtos:
                    df_produtos = pd.DataFrame(st.session_state.lista_produtos)
                    valor_calculado = (pd.to_numeric(df_produtos['Quantidade'], errors='coerce').fillna(0) * pd.to_numeric(df_produtos['Preço Unitário'], errors='coerce').fillna(0.0)).sum()
                    produtos_vendidos_json = json.dumps(df_produtos[['Produto_ID', 'Produto', 'Quantidade', 'Preço Unitário', 'Custo Unitário']].to_dict('records'))
                    st.success(f"Soma Total: R$ {valor_calculado:,.2f}")

            with st.expander("➕ Adicionar/Limpar Lista de Produtos", expanded=True):
                col_prod_lista, col_prod_add = st.columns([1, 1])
                with col_prod_lista:
                    st.markdown("##### Produtos Atuais:")
                    if st.session_state.lista_produtos:
                        st.dataframe(pd.DataFrame(st.session_state.lista_produtos)[['Produto', 'Quantidade', 'Preço Unitário']], use_container_width=True, hide_index=True)
                    else:
                        st.info("Lista de produtos vazia.")
                    if st.button("Limpar Lista", type="secondary", use_container_width=True):
                        st.session_state.lista_produtos, st.session_state.edit_id_loaded = [], None
                        st.rerun()
                with col_prod_add:
                    st.markdown("##### Adicionar Produto")
                    foto_cb_upload_caixa = st.file_uploader("📤 Upload de imagem do código de barras", ["png", "jpg", "jpeg"], key="cb_upload_caixa")
                    if foto_cb_upload_caixa:
                        codigos_lidos = ler_codigo_barras_api(foto_cb_upload_caixa.getvalue())
                        st.session_state.cb_lido_livro_caixa = codigos_lidos[0] if codigos_lidos else ""
                        st.toast(f"CB lido: {codigos_lidos[0]}" if codigos_lidos else "Nenhum CB encontrado.")
                    index_selecionado = 0
                    if st.session_state.cb_lido_livro_caixa:
                        opcao_encontrada = encontrar_opcao_por_cb(st.session_state.cb_lido_livro_caixa, produtos_para_venda, opcoes_produtos)
                        if opcao_encontrada: index_selecionado = opcoes_produtos.index(opcao_encontrada)
                        else: st.warning(f"CB '{st.session_state.cb_lido_livro_caixa}' não encontrado.")
                        st.session_state.cb_lido_livro_caixa = ""
                    produto_selecionado = st.selectbox("Selecione o Produto", opcoes_produtos, key="input_produto_selecionado", index=index_selecionado)
                    if produto_selecionado == OPCAO_MANUAL:
                        nome_produto_manual = st.text_input("Nome do Produto (Manual)", key="input_nome_prod_manual")
                        col_m1, col_m2 = st.columns(2)
                        with col_m1:
                            quantidade_manual = st.number_input("Qtd", 0.01, step=1.0, key="input_qtd_prod_manual")
                            custo_unitario_manual = st.number_input("Custo Unitário (R$)", 0.00, format="%.2f", key="input_custo_prod_manual")
                        with col_m2:
                            preco_unitario_manual = st.number_input("Preço Unitário (R$)", 0.01, format="%.2f", key="input_preco_prod_manual")
                        if st.button("Adicionar Manual", use_container_width=True, on_click=callback_adicionar_manual, args=(nome_produto_manual, quantidade_manual, preco_unitario_manual, custo_unitario_manual)): st.rerun()
                    elif produto_selecionado:
                        produto_id_selecionado = extrair_id_do_nome(produto_selecionado)
                        produto_data = produtos_para_venda[produtos_para_venda["ID"] == produto_id_selecionado].iloc[0]
                        col_p1, col_p2 = st.columns(2)
                        with col_p1:
                            quantidade_input = st.number_input("Qtd", 1, int(produto_data['Quantidade']) if produto_data['Quantidade'] > 0 else 1, step=1, key="input_qtd_prod_edit")
                            st.caption(f"Estoque: {int(produto_data['Quantidade'])}")
                        with col_p2:
                            preco_unitario_input = st.number_input("Preço Unitário (R$)", 0.01, value=float(produto_data['PrecoVista']), format="%.2f", key="input_preco_prod_edit")
                            st.caption(f"Custo: R$ {produto_data['PrecoCusto']:,.2f}")
                        if st.button("Adicionar Item", use_container_width=True, on_click=callback_adicionar_estoque, args=(produto_id_selecionado, produto_data['Nome'], quantidade_input, preco_unitario_input, produto_data['PrecoCusto'], produto_data['Quantidade'])): st.rerun()
            col_entrada_valor, col_entrada_status = st.columns(2)
            with col_entrada_valor:
                valor_final_movimentacao = valor_calculado if valor_calculado > 0 else st.number_input("Valor Total (R$)", 0.01, value=default_valor, format="%.2f", disabled=(valor_calculado > 0.0), key="input_valor_entrada")
            with col_entrada_status:
                status_selecionado = st.radio("Status", ["Realizada", "Pendente"], index=0 if default_status == "Realizada" else 1, key="input_status_global_entrada", disabled=edit_mode)
        elif tipo == "Saída":
            st.markdown("---")
            col_saida_1, col_saida_2 = st.columns(2)
            with col_saida_1:
                st.markdown("#### ⚙️ Centro de Custo")
                if not edit_mode: is_recorrente = st.checkbox("🔄 Despesa Recorrente", key="input_is_recorrente")
                default_select_index = CATEGORIAS_SAIDA.index(default_categoria) if default_categoria in CATEGORIAS_SAIDA else (CATEGORIAS_SAIDA.index("Outro/Diversos") if default_categoria.startswith("Outro: ") and "Outro/Diversos" in CATEGORIAS_SAIDA else 0)
                custom_desc_default = default_categoria.replace("Outro: ", "") if default_categoria.startswith("Outro: ") else ""
                categoria_selecionada = st.selectbox("Categoria de Gasto", CATEGORIAS_SAIDA, index=default_select_index, key="input_categoria_saida", disabled=is_recorrente and not edit_mode)
                if categoria_selecionada == "Outro/Diversos" and not (is_recorrente and not edit_mode):
                    descricao_personalizada = st.text_input("Especifique o Gasto", value=custom_desc_default, key="input_custom_category")
                    if descricao_personalizada: categoria_selecionada = f"Outro: {descricao_personalizada}"
            with col_saida_2:
                if is_recorrente and not edit_mode:
                    st.markdown("##### 🧾 Detalhes da Recorrência")
                    nome_despesa_recorrente = st.text_input("Nome da Despesa", value=default_cliente or "", key="input_nome_despesa_recorrente")
                    col_rec1, col_rec2 = st.columns(2)
                    with col_rec1: num_parcelas = st.number_input("Qtd Parcelas", 1, value=12, step=1, key="input_num_parcelas")
                    with col_rec2: valor_parcela = st.number_input("Valor da Parcela (R$)", 0.01, format="%.2f", value=default_valor, key="input_valor_parcela")
                    data_primeira_parcela = st.date_input("Vencimento 1ª Parcela", date.today().replace(day=1) + timedelta(days=32), key="input_data_primeira_parcela")
                    valor_final_movimentacao, status_selecionado = float(valor_parcela), "Pendente"
                    st.caption(f"{int(num_parcelas)} parcelas de R$ {valor_final_movimentacao:,.2f} serão geradas como 'Pendente'.")
                else:
                    status_selecionado = st.radio("Status", ["Realizada", "Pendente"], index=0 if default_status == "Realizada" else 1, key="input_status_global_saida", disabled=edit_mode)
                    valor_final_movimentacao = st.number_input("Valor (R$)", 0.01, value=default_valor, format="%.2f", key="input_valor_saida")
                    cliente = st.text_input("Descrição", value=default_cliente, key="input_cliente_form_saida", disabled=edit_mode)
        elif tipo == "Empréstimo":
            st.markdown("---")
            is_emprestimo = True
            col_emp_1, col_emp_2 = st.columns(2)
            with col_emp_1:
                st.markdown("#### 💸 Detalhes do Empréstimo")
                st.text_input("Status da Dívida", "Pendente", disabled=True)
                valor_final_movimentacao = st.number_input("Valor Recebido (R$)", 0.01, value=default_valor, format="%.2f", key="input_valor_emprestimo")
            with col_emp_2:
                cliente = st.text_input("Credor", value=default_cliente, key="input_credor_form", disabled=edit_mode)
                forma_pagamento = st.selectbox("Forma de Recebimento", FORMAS_PAGAMENTO, key="input_forma_pagamento_emprestimo")
            st.markdown("##### ❓ O dinheiro já foi gasto?")
            emprestimo_gasto_radio = st.radio("Selecione:", ["Selecione...", "Sim, já foi usado (não altera saldo)", "Não, é saldo disponível (adiciona ao saldo)"], 0, key="radio_emprestimo_gasto", horizontal=True)
            if emprestimo_gasto_radio == "Sim, já foi usado (não altera saldo)":
                emprestimo_ja_gasto = True
                st.warning("Serão gerados 3 registros: Dívida (Pendente), Entrada (Realizada) e Saída (Realizada). Saldo geral não muda.")
                categoria_gasto_emprestimo = st.selectbox("Categoria REAL do Gasto", CATEGORIAS_SAIDA, index=CATEGORIAS_SAIDA.index(default_categoria) if default_categoria in CATEGORIAS_SAIDA else 0, key="input_categoria_gasto_emprestimo")
                if categoria_gasto_emprestimo == "Outro/Diversos":
                    descricao_personalizada_gasto = st.text_input("Especifique o Gasto", key="input_custom_category_emprestimo")
                    if descricao_personalizada_gasto: categoria_gasto_emprestimo = f"Outro: {descricao_personalizada_gasto}"
            elif emprestimo_gasto_radio == "Não, é saldo disponível (adiciona ao saldo)":
                emprestimo_ja_gasto = False
                st.success("Serão gerados 2 registros: Dívida (Pendente) e Entrada (Realizada).")
            data_pagamento_final = st.date_input("Data Prevista de Pagamento da Dívida", default_data_pagamento or date.today() + timedelta(days=30), key="input_data_pagamento_emprestimo")
            cliente_final, categoria_selecionada = f"Dívida Empréstimo: {cliente}", "Empréstimo Recebido - Dívida"
        
        data_pagamento_final = None
        if status_selecionado == "Pendente" and not is_recorrente and not is_emprestimo:
            with st.expander("🗓️ Data Prevista (Opcional)"):
                data_status_selecionado_previsto = st.radio("Pendência com data?", ["Com Data", "Sem Data"], 0 if pd.notna(default_data_pagamento) else 1, key="input_data_status_previsto_global", horizontal=True, disabled=edit_mode and pd.notna(default_data_pagamento))
                if data_status_selecionado_previsto == "Com Data":
                    data_pagamento_final = st.date_input("Selecione a Data", default_data_pagamento or date.today(), key="input_data_pagamento_prevista_global")
        elif status_selecionado == "Pendente" and is_recorrente:
            data_pagamento_final = data_primeira_parcela
            st.markdown(f"##### 🗓️ 1ª Parcela Vence em: **{data_pagamento_final.strftime('%d/%m/%Y')}**")

        st.markdown("---")
        with st.form("form_movimentacao", clear_on_submit=not edit_mode):
            st.markdown("#### Dados Finais da Transação")
            col_f1, col_f2, col_f3 = st.columns(3)
            with col_f1:
                loja_selecionada = st.selectbox("Loja", LOJAS_DISPONIVEIS, index=LOJAS_DISPONIVEIS.index(default_loja) if default_loja in LOJAS_DISPONIVEIS else 0, key="input_loja_form", disabled=(is_recorrente or is_emprestimo) and not edit_mode)
                data_input = st.date_input("Data do Lançamento", default_data, key="input_data_form", disabled=(is_recorrente or is_emprestimo) and not edit_mode)
            with col_f2:
                cliente_final = cliente if tipo == "Entrada" and not edit_mode else (nome_despesa_recorrente if tipo == "Saída" and is_recorrente and not edit_mode else (cliente if tipo == "Saída" and not edit_mode else (f"Dívida Empréstimo: {cliente}" if is_emprestimo and not edit_mode else default_cliente)))
                st.text_input("Cliente/Descrição (Final)", cliente_final, key="input_cliente_form_display", disabled=True)
                if status_selecionado == "Realizada" and not is_emprestimo:
                    data_pagamento_final = data_input
                    forma_pagamento = st.selectbox("Forma de Pagamento", FORMAS_PAGAMENTO, index=FORMAS_PAGAMENTO.index(default_forma) if default_forma in FORMAS_PAGAMENTO else 0, key="input_forma_pagamento_form")
                elif is_emprestimo: st.text_input("Forma de Pagamento", forma_pagamento, disabled=True)
                else: forma_pagamento = "Pendente"; st.text_input("Forma de Pagamento", "Pendente", disabled=True)
            with col_f3:
                st.markdown(f"**Valor Final:** R$ {valor_final_movimentacao:,.2f}")
                st.markdown(f"**Status:** **{status_selecionado}**")
                st.markdown(f"**Data Pagamento:** {data_pagamento_final.strftime('%d/%m/%Y') if data_pagamento_final else 'N/A'}")
            
            enviar_label = "Adicionar Recorrência" if is_recorrente else ("Registrar Empréstimo" if is_emprestimo else ("💾 Salvar" if edit_mode else "Adicionar e Salvar"))
            enviar = st.form_submit_button(enviar_label, type="primary", use_container_width=True)
            if edit_mode and st.form_submit_button("❌ Cancelar", type="secondary", use_container_width=True):
                st.session_state.edit_id, st.session_state.edit_id_loaded, st.session_state.lista_produtos = None, None, []
                st.rerun()
            
            if enviar:
                if (valor_final_movimentacao <= 0 and not is_recorrente and not is_emprestimo) or (valor_parcela <= 0 and is_recorrente) or (is_emprestimo and emprestimo_ja_gasto is None and not edit_mode) or (tipo == "Saída" and not is_recorrente and categoria_selecionada == "Outro/Diversos") or (is_recorrente and not edit_mode and not nome_despesa_recorrente):
                    st.error("Verifique os campos obrigatórios.")
                else:
                    valor_armazenado = valor_final_movimentacao if tipo == "Entrada" else -valor_final_movimentacao
                    if edit_mode:
                        original_row = df_dividas.loc[st.session_state.edit_id]
                        if original_row["Status"] == "Realizada" and original_row["Tipo"] == "Entrada": # Reversão de estoque
                            try:
                                for item in ast.literal_eval(original_row['Produtos Vendidos']):
                                    if item.get("Produto_ID"): ajustar_estoque(item["Produto_ID"], item["Quantidade"], "creditar")
                            except: pass
                        if produtos_vendidos_json and status_selecionado == "Realizada": # Novo débito
                            try:
                                for item in json.loads(produtos_vendidos_json):
                                    if item.get("Produto_ID"): ajustar_estoque(item["Produto_ID"], item["Quantidade"], "debitar")
                                if salvar_produtos_no_github(st.session_state.produtos, "Ajuste de estoque por edição"): inicializar_produtos.clear()
                            except: pass
                    elif not edit_mode and tipo == "Entrada" and status_selecionado == "Realizada" and produtos_vendidos_json: # Novo débito
                        try:
                            for item in json.loads(produtos_vendidos_json):
                                if item.get("Produto_ID"): ajustar_estoque(item["Produto_ID"], item["Quantidade"], "debitar")
                            if salvar_produtos_no_github(st.session_state.produtos, "Débito de estoque por venda"): inicializar_produtos.clear()
                        except: pass
                    
                    if is_recorrente and not edit_mode:
                        recorrencia_id = hashlib.md5(f"{nome_despesa_recorrente}{data_primeira_parcela}{num_parcelas}{valor_parcela}".encode()).hexdigest()[:10]
                        novas_movimentacoes = [{"Data": data_input, "Loja": loja_selecionada, "Cliente": f"{nome_despesa_recorrente} (Parc. {i+1}/{int(num_parcelas)})", "Valor": -float(valor_parcela), "Forma de Pagamento": "Pendente", "Tipo": "Saída", "Produtos Vendidos": "", "Categoria": categoria_selecionada, "Status": "Pendente", "Data Pagamento": add_months(data_primeira_parcela, i), "RecorrenciaID": recorrencia_id, "TransacaoPaiID": ""} for i in range(int(num_parcelas))]
                        st.session_state.df = pd.concat([df_dividas, pd.DataFrame(novas_movimentacoes)], ignore_index=True)
                        commit_msg = f"Cadastro de Dívida Recorrente ({int(num_parcelas)} parcelas)"
                    elif is_emprestimo and not edit_mode:
                        novas_movimentacoes = [{"Data": data_input, "Loja": loja_selecionada, "Cliente": f"Pagamento Empréstimo: {cliente}", "Valor": -valor_final_movimentacao, "Forma de Pagamento": "Pendente", "Tipo": "Saída", "Produtos Vendidos": "", "Categoria": "Empréstimo Recebido - Dívida", "Status": "Pendente", "Data Pagamento": data_pagamento_final, "RecorrenciaID": "", "TransacaoPaiID": ""}]
                        if emprestimo_ja_gasto:
                            novas_movimentacoes.append({"Data": data_input, "Loja": loja_selecionada, "Cliente": f"Gasto Financiado: {cliente}", "Valor": -valor_final_movimentacao, "Forma de Pagamento": forma_pagamento, "Tipo": "Saída", "Produtos Vendidos": "", "Categoria": categoria_gasto_emprestimo, "Status": "Realizada", "Data Pagamento": data_input, "RecorrenciaID": "", "TransacaoPaiID": ""})
                            novas_movimentacoes.append({"Data": data_input, "Loja": loja_selecionada, "Cliente": f"Entrada Financiada: {cliente}", "Valor": valor_final_movimentacao, "Forma de Pagamento": forma_pagamento, "Tipo": "Entrada", "Produtos Vendidos": "", "Categoria": "Empréstimo Recebido - Entrada", "Status": "Realizada", "Data Pagamento": data_input, "RecorrenciaID": "", "TransacaoPaiID": ""})
                        else:
                            novas_movimentacoes.append({"Data": data_input, "Loja": loja_selecionada, "Cliente": f"Entrada Empréstimo (Saldo): {cliente}", "Valor": valor_final_movimentacao, "Forma de Pagamento": forma_pagamento, "Tipo": "Entrada", "Produtos Vendidos": "", "Categoria": "Empréstimo Recebido - Saldo", "Status": "Realizada", "Data Pagamento": data_input, "RecorrenciaID": "", "TransacaoPaiID": ""})
                        st.session_state.df = pd.concat([df_dividas, pd.DataFrame(novas_movimentacoes)], ignore_index=True)
                        commit_msg = f"Registro de Empréstimo de R$ {valor_final_movimentacao:,.2f}."
                    else:
                        nova_linha_data = {"Data": data_input, "Loja": loja_selecionada, "Cliente": cliente_final, "Valor": valor_armazenado, "Forma de Pagamento": forma_pagamento, "Tipo": tipo, "Produtos Vendidos": produtos_vendidos_json, "Categoria": categoria_selecionada, "Status": status_selecionado, "Data Pagamento": data_pagamento_final, "RecorrenciaID": "", "TransacaoPaiID": ""}
                        if edit_mode:
                            st.session_state.df.loc[st.session_state.edit_id] = pd.Series(nova_linha_data)
                            commit_msg = COMMIT_MESSAGE_EDIT
                        else:
                            st.session_state.df = pd.concat([df_dividas, pd.DataFrame([nova_linha_data])], ignore_index=True)
                            commit_msg = COMMIT_MESSAGE
                    
                    salvar_dados_no_github(st.session_state.df, commit_msg)
                    st.session_state.edit_id, st.session_state.edit_id_loaded, st.session_state.lista_produtos, st.session_state.divida_a_quitar = None, None, [], None
                    st.cache_data.clear()
                    st.rerun()

    with tab_mov:
        hoje = date.today()
        primeiro_dia_mes = hoje.replace(day=1)
        ultimo_dia_mes = (primeiro_dia_mes.replace(month=primeiro_dia_mes.month % 12 + 1) if primeiro_dia_mes.month != 12 else primeiro_dia_mes.replace(year=primeiro_dia_mes.year + 1, month=1)) - timedelta(days=1)
        df_mes_atual_realizado = df_exibicao[(df_exibicao["Data"] >= primeiro_dia_mes) & (df_exibicao["Data"] <= ultimo_dia_mes) & (df_exibicao["Status"] == "Realizada")]
        st.subheader(f"📊 Resumo Financeiro Geral")
        total_entradas_mes, total_saidas_mes, saldo_mes = calcular_resumo(df_mes_atual_realizado)
        _, _, saldo_geral_total = calcular_resumo(df_exibicao[df_exibicao['Status'] == 'Realizada'])
        col1, col2, col3, col4 = st.columns(4)
        col1.metric(f"Entradas ({primeiro_dia_mes.strftime('%b')})", f"R$ {total_entradas_mes:,.2f}")
        col2.metric(f"Saídas ({primeiro_dia_mes.strftime('%b')})", f"R$ {total_saidas_mes:,.2f}")
        col3.metric("Saldo do Mês", f"R$ {saldo_mes:,.2f}", delta=f"R$ {saldo_mes:,.2f}" if saldo_mes != 0 else None)
        col4.metric("Saldo Atual (Geral)", f"R$ {saldo_geral_total:,.2f}")
        st.markdown("---")
        df_pendente_alerta = df_exibicao[(df_exibicao["Status"] == "Pendente") & pd.notna(df_exibicao["Data Pagamento"])].copy()
        if not df_pendente_alerta.empty:
            df_pendente_alerta["Data Pagamento"] = pd.to_datetime(df_pendente_alerta["Data Pagamento"], errors='coerce').dt.date
            df_vencidas = df_pendente_alerta[df_pendente_alerta["Data Pagamento"] <= hoje]
            if not df_vencidas.empty:
                num_receber, contas_a_receber_vencidas = df_vencidas[df_vencidas["Tipo"] == "Entrada"].shape[0], df_vencidas[df_vencidas["Tipo"] == "Entrada"]["Valor"].abs().sum()
                num_pagar, contas_a_pagar_vencidas = df_vencidas[df_vencidas["Tipo"] == "Saída"].shape[0], df_vencidas[df_vencidas["Tipo"] == "Saída"]["Valor"].abs().sum()
                if num_receber > 0 or num_pagar > 0:
                    alert_message = "### ⚠️ DÍVIDAS VENCIDAS!"
                    if num_receber > 0: alert_message += f"\n\n💸 **{num_receber} Contas a Receber** (Total: R$ {contas_a_receber_vencidas:,.2f})"
                    if num_pagar > 0: alert_message += f"\n\n💰 **{num_pagar} Contas a Pagar** (Total: R$ {contas_a_pagar_vencidas:,.2f})"
                    st.error(alert_message)
                    st.caption("Acesse a aba 'Relatórios e Filtros' para detalhes.")
                    st.markdown("---")

        st.subheader(f"🏠 Resumo por Loja (Mês de {primeiro_dia_mes.strftime('%m/%Y')})")
        df_resumo_loja = df_mes_atual_realizado.groupby('Loja')['Valor'].agg(['sum', lambda x: x[x >= 0].sum(), lambda x: abs(x[x < 0].sum())]).reset_index()
        df_resumo_loja.columns = ['Loja', 'Saldo', 'Entradas', 'Saídas']
        if not df_resumo_loja.empty:
            cols_loja = st.columns(min(4, len(df_resumo_loja.index)))
            for i, row in df_resumo_loja.iterrows():
                if i < len(cols_loja): cols_loja[i].metric(label=row['Loja'], value=f"R$ {row['Saldo']:,.2f}", delta=f"E: R$ {row['Entradas']:,.2f} | S: R$ {row['Saídas']:,.2f}", delta_color="off")
        else:
            st.info("Nenhuma movimentação realizada neste mês.")
        st.markdown("---")
        st.subheader("📋 Tabela de Movimentações")
        if df_exibicao.empty:
            st.info("Nenhuma movimentação registrada.")
        else:
            col_f1, col_f2, col_f3 = st.columns(3)
            min_date, max_date = (df_exibicao["Data"].min() or hoje), (df_exibicao["Data"].max() or hoje)
            with col_f1: filtro_data_inicio = st.date_input("De", min_date, key="quick_data_ini")
            with col_f2: filtro_data_fim = st.date_input("Até", max_date, key="quick_data_fim")
            with col_f3: filtro_tipo = st.selectbox("Filtrar por Tipo", ["Todos", "Entrada", "Saída"], key="quick_tipo")
            df_filtrado_rapido = df_exibicao[(df_exibicao["Data"] >= filtro_data_inicio) & (df_exibicao["Data"] <= filtro_data_fim) & ((df_exibicao["Tipo"] == filtro_tipo) if filtro_tipo != "Todos" else True)].copy()
            df_para_mostrar = df_filtrado_rapido.copy()
            df_para_mostrar['Produtos Resumo'] = df_para_mostrar['Produtos Vendidos'].apply(format_produtos_resumo)
            colunas_tabela = ['ID Visível', 'Data', 'Loja', 'Cliente', 'Categoria', 'Valor', 'Forma de Pagamento', 'Tipo', 'Status', 'Data Pagamento', 'Produtos Resumo', 'Saldo Acumulado']
            
            # Seção de Estilização da Tabela Principal
            if 'Cor_Valor' not in df_para_mostrar.columns: df_para_mostrar['Cor_Valor'] = 'black'
            df_styling = df_para_mostrar[colunas_tabela + ['Cor_Valor']].copy()
            styled_df = df_styling.style.apply(highlight_value, axis=1).hide(subset=['Cor_Valor'], axis=1)
            
            st.dataframe(styled_df, use_container_width=True, height=400, selection_mode='disabled', column_config={
                "Valor": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f"), "Saldo Acumulado": st.column_config.NumberColumn("Saldo (R$)", format="R$ %.2f"),
                "Produtos Resumo": st.column_config.TextColumn("Produtos"), "Data Pagamento": st.column_config.DateColumn("Data Pagt.", format="DD/MM/YYYY")})

            st.markdown("---")
            st.markdown("### Operações de Edição e Exclusão")
            if not df_para_mostrar.empty:
                opcoes_mov = {f"ID {row['ID Visível']} | {row['Data'].strftime('%d/%m/%Y')} | {row['Cliente']} | R$ {abs(row['Valor']):,.2f}": row['original_index'] for _, row in df_para_mostrar.iterrows()}
                selecionado_str = st.selectbox("Selecione para Editar/Excluir:", ["Selecione..."] + list(opcoes_mov.keys()))
                idx_selecionado = opcoes_mov.get(selecionado_str)
                if idx_selecionado is not None:
                    row = df_exibicao.loc[df_exibicao['original_index'] == idx_selecionado].iloc[0]
                    if row['Tipo'] == 'Entrada' and pd.notna(row['Produtos Vendidos']):
                        try:
                            df_detalhe = pd.DataFrame(ast.literal_eval(row['Produtos Vendidos']))
                            df_detalhe['Total Venda'] = pd.to_numeric(df_detalhe['Quantidade']) * pd.to_numeric(df_detalhe['Preço Unitário'])
                            df_detalhe['Lucro Bruto'] = df_detalhe['Total Venda'] - (pd.to_numeric(df_detalhe['Quantidade']) * pd.to_numeric(df_detalhe['Custo Unitário']))
                            st.dataframe(df_detalhe[['Produto', 'Quantidade', 'Preço Unitário', 'Total Venda', 'Lucro Bruto']], hide_index=True, use_container_width=True)
                        except: pass
                    col_op_1, col_op_2 = st.columns(2)
                    if col_op_1.button(f"✏️ Editar", key=f"edit_{idx_selecionado}", use_container_width=True, type="secondary"):
                        st.session_state.edit_id, st.session_state.edit_id_loaded = idx_selecionado, None
                        st.rerun()
                    if col_op_2.button(f"🗑️ Excluir", key=f"del_{idx_selecionado}", use_container_width=True, type="primary"):
                        if row['Status'] == 'Realizada' and row['Tipo'] == 'Entrada' and pd.notna(row['Produtos Vendidos']):
                            try:
                                for item in ast.literal_eval(row['Produtos Vendidos']):
                                    if item.get("Produto_ID"): ajustar_estoque(item["Produto_ID"], item["Quantidade"], "creditar")
                                if salvar_produtos_no_github(st.session_state.produtos, "Reversão por exclusão"): inicializar_produtos.clear()
                            except: pass
                        st.session_state.df = st.session_state.df.drop(row['original_index'], errors='ignore')
                        if salvar_dados_no_github(st.session_state.df, COMMIT_MESSAGE_DELETE):
                            st.cache_data.clear()
                            st.rerun()
            else: st.info("Nenhuma movimentação para operar com os filtros atuais.")
    
    with tab_rel:
        st.subheader("📄 Relatório Detalhado e Comparativo")
        with st.container(border=True):
            st.markdown("#### Filtros do Relatório")
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                lojas_selecionadas = st.multiselect("Lojas/Empresas", LOJAS_DISPONIVEIS, default=LOJAS_DISPONIVEIS)
                tipo_movimentacao = st.radio("Tipo de Movimentação", ["Ambos", "Entrada", "Saída"], horizontal=True, key="rel_tipo")
            with col_f2:
                min_date_geral, max_date_geral = (df_exibicao["Data"].min() or date.today()), (df_exibicao["Data"].max() or date.today())
                data_inicio_rel = st.date_input("Data de Início", min_date_geral, min_value=min_date_geral, max_value=max_date_geral, key="rel_data_ini")
                data_fim_rel = st.date_input("Data de Fim", max_date_geral, min_value=min_date_geral, max_value=max_date_geral, key="rel_data_fim")
            if st.button("📊 Gerar Relatório", use_container_width=True, type="primary"):
                df_relatorio = df_exibicao[(df_exibicao['Status'] == 'Realizada') & (df_exibicao['Loja'].isin(lojas_selecionadas)) & (df_exibicao['Data'].between(data_inicio_rel, data_fim_rel)) & ((df_exibicao['Tipo'] == tipo_movimentacao) if tipo_movimentacao != "Ambos" else True)].copy()
                if df_relatorio.empty:
                    st.warning("Nenhum dado encontrado com os filtros selecionados.")
                else:
                    df_relatorio['MesAno'] = pd.to_datetime(df_relatorio['Data']).dt.to_period('M').astype(str)
                    df_agrupado = df_relatorio.groupby('MesAno').apply(lambda x: pd.Series({'Entradas': x[x['Valor'] > 0]['Valor'].sum(), 'Saídas': abs(x[x['Valor'] < 0]['Valor'].sum())})).reset_index()
                    df_agrupado['Saldo'] = df_agrupado['Entradas'] - df_agrupado['Saídas']
                    st.markdown("---")
                    st.subheader("Resultados do Relatório")
                    st.dataframe(df_agrupado, use_container_width=True)
        st.markdown("---")
        st.subheader("🚩 Dívidas Pendentes")
        df_pendentes = df_exibicao[df_exibicao["Status"] == "Pendente"].copy()
        if df_pendentes.empty:
            st.success("🎉 Nenhuma dívida pendente registrada!")
        else:
            df_pendentes["Data Pagamento"] = pd.to_datetime(df_pendentes["Data Pagamento"], errors='coerce').dt.date
            df_pendentes_ordenado = df_pendentes.sort_values(by=["Data Pagamento", "Tipo", "Data"]).reset_index(drop=True)
            df_pendentes_ordenado['Dias Até/Atraso'] = df_pendentes_ordenado['Data Pagamento'].apply(lambda x: (x - date.today()).days if pd.notna(x) else float('inf'))
            total_receber, total_pagar = df_pendentes_ordenado[df_pendentes_ordenado["Tipo"] == "Entrada"]["Valor"].abs().sum(), df_pendentes_ordenado[df_pendentes_ordenado["Tipo"] == "Saída"]["Valor"].abs().sum()
            col_res_1, col_res_2 = st.columns(2)
            col_res_1.metric("Total a Receber", f"R$ {total_receber:,.2f}")
            col_res_2.metric("Total a Pagar", f"R$ {total_pagar:,.2f}")
            st.markdown("---")
            def highlight_pendentes(row):
                dias = row['Dias Até/Atraso']
                if dias < 0: return ['background-color: #fcece9' if col in ['Status', 'Data Pagamento'] else '' for col in row.index]
                elif dias <= 7: return ['background-color: #fffac9' if col in ['Status', 'Data Pagamento'] else '' for col in row.index]
                return ['' for col in row.index]
            with st.form("form_concluir_divida"):
                st.markdown("##### ✅ Concluir Dívida")
                opcoes_pendentes = {f"ID {row['ID Visível']} | {row['Tipo']} | R$ {calcular_valor_em_aberto(row):,.2f} | Venc: {row['Data Pagamento'].strftime('%d/%m/%Y') if pd.notna(row['Data Pagamento']) else 'S/D'} | {row['Cliente']}": row['original_index'] for _, row in df_pendentes_ordenado.iterrows()}
                selecionado_str_concluir = st.selectbox("Selecione a Dívida:", ["Selecione..."] + list(opcoes_pendentes.keys()))
                idx_concluir = opcoes_pendentes.get(selecionado_str_concluir)
                if idx_concluir is not None:
                    divida_para_concluir = df_pendentes_ordenado[df_pendentes_ordenado['original_index'] == idx_concluir].iloc[0]
                    valor_em_aberto = calcular_valor_em_aberto(divida_para_concluir)
                    st.markdown(f"**Valor em Aberto:** R$ {valor_em_aberto:,.2f}")
                    col_c1, col_c2, col_c3 = st.columns(3)
                    with col_c1: valor_pago = st.number_input("Valor Pago", 0.01, valor_em_aberto, valor_em_aberto, format="%.2f")
                    with col_c2: data_conclusao = st.date_input("Data do Pagamento", date.today())
                    with col_c3: forma_pagt_concluir = st.selectbox("Forma de Pagamento", FORMAS_PAGAMENTO)
                    if st.form_submit_button("✅ Registrar Pagamento", use_container_width=True, type="primary"):
                        valor_restante = round(valor_em_aberto - valor_pago, 2)
                        row_original = st.session_state.df.loc[idx_concluir].copy()
                        nova_transacao = {"Data": data_conclusao, "Loja": row_original['Loja'], "Cliente": f"{row_original['Cliente'].split(' (')[0]} (Pagto de R$ {valor_pago:,.2f})", "Valor": valor_pago if row_original['Tipo'] == 'Entrada' else -valor_pago, "Forma de Pagamento": forma_pagt_concluir, "Tipo": row_original['Tipo'], "Produtos Vendidos": row_original['Produtos Vendidos'], "Categoria": row_original['Categoria'], "Status": "Realizada", "Data Pagamento": data_conclusao, "RecorrenciaID": row_original['RecorrenciaID'], "TransacaoPaiID": idx_concluir}
                        st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([nova_transacao])], ignore_index=True)
                        if valor_restante > 0.01:
                            st.session_state.df.loc[idx_concluir, 'Valor'] = valor_restante if row_original['Tipo'] == 'Entrada' else -valor_restante
                            st.session_state.df.loc[idx_concluir, 'Cliente'] = f"{row_original['Cliente'].split(' (')[0]} (EM ABERTO: R$ {valor_restante:,.2f})"
                            commit_msg = f"Pagamento parcial de R$ {valor_pago:,.2f}."
                        else:
                            st.session_state.df = st.session_state.df.drop(idx_concluir, errors='ignore')
                            if row_original["Tipo"] == "Entrada" and pd.notna(row_original["Produtos Vendidos"]):
                                try:
                                    for item in ast.literal_eval(row_original['Produtos Vendidos']):
                                        if item.get("Produto_ID"): ajustar_estoque(item["Produto_ID"], item["Quantidade"], "debitar")
                                    if salvar_produtos_no_github(st.session_state.produtos, "Débito por conclusão"): inicializar_produtos.clear()
                                except: pass
                            commit_msg = f"Pagamento total de R$ {valor_pago:,.2f}."
                        if salvar_dados_no_github(st.session_state.df, commit_msg):
                            st.cache_data.clear()
                            st.rerun()
                else: st.info("Selecione uma dívida para concluir.")
            st.markdown("---")
            st.markdown("##### Tabela Detalhada de Dívidas Pendentes")

df_para_mostrar_pendentes = df_pendentes_ordenado.copy()
df_para_mostrar_pendentes['Status Vencimento'] = df_para_mostrar_pendentes['Dias Até/Atraso'].apply(
    lambda x: f"Atrasado {-x} dias" if x < 0 else (f"Vence em {x} dias" if x > 0 else "Vence Hoje")
)

# 🔧 Correção preventiva de erro KeyError (coluna Cor_Valor ausente)
if 'Cor_Valor' not in df_para_mostrar_pendentes.columns:
    df_para_mostrar_pendentes['Cor_Valor'] = 'black'

# Estilização da tabela de pendentes
df_styling_pendentes = (
    df_para_mostrar_pendentes
    .style
    .apply(highlight_pendentes, axis=1)
    .hide(subset=['Dias Até/Atraso'], axis=1)
)

# Exibição segura no Streamlit
st.dataframe(df_styling_pendentes, use_container_width=True, hide_index=True)





