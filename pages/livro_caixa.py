# pages/livro_caixa.py

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
import json
import ast
import hashlib
import time

# --- CONSTANTES INTEGRADAS PARA CORRIGIR O IMPORT ERROR ---

# Mensagens de Commit para o GitHub
COMMIT_MESSAGE = "Nova Movimentação Registrada"
COMMIT_MESSAGE_EDIT = "Movimentação Editada"
COMMIT_MESSAGE_DELETE = "Movimentação Excluída"

# Listas de Opções para Formulários
LOJAS_DISPONIVEIS = [
    "Loja Matriz",
    "Loja Filial",
    "E-commerce"
]

CATEGORIAS_SAIDA = [
    "Compra de Mercadoria",
    "Aluguel",
    "Salários",
    "Marketing",
    "Impostos",
    "Contas (Água, Luz, Internet)",
    "Empréstimo (Não deduz do Saldo Geral)",
    "Outro/Diversos"
]

CATEGORIAS_ENTRADA = [
    "Venda de Produto",
    "Prestação de Serviço",
    "Empréstimo (Entrada)",
    "Aporte de Sócio"
]

FORMAS_PAGAMENTO = [
    "Dinheiro",
    "PIX",
    "Cartão de Débito",
    "Cartão de Crédito",
    "Pendente"
]

# Fator para cálculo (ex: juros de cartão)
FATOR_CARTAO = 1.05 # Exemplo: acréscimo de 5%

# --- FIM DAS CONSTANTES INTEGRADAS ---


# Supondo que essas funções de 'utils' estejam definidas em outro lugar
# Se elas também estiverem em um arquivo separado, você precisará integrá-las
# ou garantir que o arquivo 'utils.py' exista.
# Por enquanto, criarei funções vazias para evitar mais erros.

def inicializar_produtos():
    # Placeholder: Substitua pela sua lógica real de carregar produtos
    if "produtos" in st.session_state:
        return st.session_state.produtos
    return pd.DataFrame(columns=["ID", "Nome", "Marca", "Quantidade", "PaiID", "CodigoBarras"])

def carregar_livro_caixa():
    # Placeholder: Substitua pela sua lógica real de carregar o livro caixa
    if "df" in st.session_state:
        return st.session_state.df
    return pd.DataFrame(columns=["Data", "Loja", "Cliente", "Valor", "Forma de Pagamento", "Tipo", "Produtos Vendidos", "Categoria", "Status", "Data Pagamento", "RecorrenciaID", "TransacaoPaiID"])

def ajustar_estoque(prod_id, qtd, op):
    # Placeholder
    pass

def to_float(value):
    # Placeholder
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0

def salvar_dados_no_github(df, msg):
    # Placeholder
    st.success(f"Simulação de salvamento: {msg}")
    return True

def processar_dataframe(df):
    if df.empty:
        return df
    df_proc = df.copy()
    df_proc['Data'] = pd.to_datetime(df_proc['Data'], errors='coerce').dt.date
    df_proc['Data_dt'] = pd.to_datetime(df_proc['Data'], errors='coerce')
    df_proc.sort_values(by='Data', ascending=False, inplace=True)
    df_proc['original_index'] = df_proc.index
    df_proc['ID Visível'] = df_proc.index + 1
    df_proc['Cor_Valor'] = df_proc['Valor'].apply(lambda x: 'green' if x > 0 else 'red')
    df_proc['Saldo Acumulado'] = df_proc.sort_values(by='Data')['Valor'].cumsum()
    return df_proc

def calcular_resumo(df):
    entradas = df[df['Valor'] > 0]['Valor'].sum()
    saidas = abs(df[df['Valor'] < 0]['Valor'].sum())
    saldo = entradas - saidas
    return entradas, saidas, saldo

def calcular_valor_em_aberto(row):
    # Placeholder
    return abs(row['Valor'])

def format_produtos_resumo(produtos_json):
    # Placeholder
    if not produtos_json or pd.isna(produtos_json):
        return "N/A"
    try:
        items = ast.literal_eval(str(produtos_json))
        if isinstance(items, list) and items:
            return f"{len(items)} item(s)"
        return "N/A"
    except:
        return "Erro de Formato"

def ler_codigo_barras_api():
    # Placeholder
    return None

def callback_adicionar_manual():
    # Placeholder
    pass

def callback_adicionar_estoque():
    # Placeholder
    pass

def salvar_produtos_no_github(df, msg):
    # Placeholder
    st.success(f"Simulação de salvamento de produtos: {msg}")
    return True

def add_months(source_date, months):
    # Placeholder
    import calendar
    month = source_date.month - 1 + months
    year = source_date.year + month // 12
    month = month % 12 + 1
    day = min(source_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)

def carregar_promocoes():
    # Placeholder
    return pd.DataFrame()

def norm_promocoes(df):
    # Placeholder
    return df


def highlight_value(row):
    """Função auxiliar para colorir o valor na tabela de movimentações."""
    color = row['Cor_Valor']
    return [f'color: {color}' if col == 'Valor' else '' for col in row.index]


def livro_caixa():

    st.header("📘 Livro Caixa - Gerenciamento de Movimentações")

    CATEGORIA_EMPRESTIMO_SAIDA = "Empréstimo (Não deduz do Saldo Geral)"
    CATEGORIA_EMPRESTIMO_ENTRADA = "Empréstimo (Entrada)"

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

    df_dividas = st.session_state.df
    df_exibicao = processar_dataframe(df_dividas)

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
    default_categoria = ""
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
                        produtos_list = ast.literal_eval(default_produtos_json)
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

    # --- ABA DE NOVA MOVIMENTAÇÃO ---
    with tab_nova_mov:

        workflow_choice = st.radio(
            "Qual tipo de operação você quer registrar?",
            ["Entrada/Saída Padrão", "Registrar Empréstimo"],
            horizontal=True,
            key="workflow_selector"
        )
        st.markdown("---")

        if workflow_choice == "Registrar Empréstimo":
            st.subheader("💸 Registro de Empréstimos")

            tipo_emprestimo = st.radio(
                "Este empréstimo representa:",
                [
                    "Uma entrada de dinheiro no caixa (aumenta o Saldo Geral)",
                    "Um gasto/dívida que não mexe no caixa (apenas para relatório)"
                ],
                key="tipo_emprestimo_choice"
            )

            is_entrada_caixa = tipo_emprestimo.startswith("Uma entrada")

            if is_entrada_caixa:
                tipo = "Entrada"
                categoria_selecionada = CATEGORIA_EMPRESTIMO_ENTRADA
                is_recorrente = False
                st.info("Esta opção irá aumentar seu Saldo Atual (Geral).")
            else:
                tipo = "Saída"
                categoria_selecionada = CATEGORIA_EMPRESTIMO_SAIDA
                is_recorrente = st.checkbox("🔄 Registrar pagamentos como despesa recorrente (parcelas)?", key="emprestimo_is_recorrente")
                st.warning("Esta opção será registrada como gasto do mês, mas **não** irá diminuir seu Saldo Atual (Geral).")

            cliente = st.text_input("Nome do Credor/Descrição do Empréstimo", key="emprestimo_cliente")

            if is_recorrente:
                col_rec1, col_rec2 = st.columns(2)
                with col_rec1:
                    num_parcelas = st.number_input("Quantidade de Parcelas", min_value=1, value=12, step=1, key="emprestimo_num_parcelas")
                with col_rec2:
                    valor_parcela = st.number_input("Valor de Cada Parcela (R$)", min_value=0.01, format="%.2f", key="emprestimo_valor_parcela")
                data_primeira_parcela = st.date_input("Data de Vencimento da 1ª Parcela", value=date.today().replace(day=1) + timedelta(days=32), key="emprestimo_data_primeira")
                valor_final_movimentacao = float(valor_parcela)
                status_selecionado = "Pendente"
            else:
                valor_final_movimentacao = st.number_input("Valor Total do Empréstimo (R$)", min_value=0.01, format="%.2f", key="emprestimo_valor_total")
                status_selecionado = "Realizada" if is_entrada_caixa else st.radio("Status", ["Realizada", "Pendente"], index=1, key="emprestimo_status")
                num_parcelas = 1

            with st.form("form_emprestimo"):
                st.markdown("##### Dados Finais")
                col_f1, col_f2 = st.columns(2)
                with col_f1:
                    loja_selecionada = st.selectbox("Loja Responsável", LOJAS_DISPONIVEIS, key="emprestimo_loja")
                    data_input = st.date_input("Data de Lançamento", value=date.today(), key="emprestimo_data")
                with col_f2:
                    if status_selecionado == "Realizada":
                        data_pagamento_final = data_input
                        forma_pagamento = st.selectbox("Forma de Pagamento", FORMAS_PAGAMENTO, key="emprestimo_forma_pagto")
                    else:
                        data_pagamento_final = data_primeira_parcela if is_recorrente else None
                        forma_pagamento = "Pendente"
                        if not is_recorrente:
                             data_pagamento_final = st.date_input("Data Prevista de Pagamento (Opcional)", value=None, key="emprestimo_data_prevista")

                enviar_emprestimo = st.form_submit_button("💾 Salvar Empréstimo", use_container_width=True, type="primary")

                if enviar_emprestimo:
                    if not cliente or valor_final_movimentacao <= 0.0:
                        st.error("Preencha a descrição e o valor do empréstimo.")
                    else:
                        valor_armazenado = valor_final_movimentacao if tipo == "Entrada" else -valor_final_movimentacao

                        if is_recorrente:
                            recorrencia_seed = f"{cliente}{data_primeira_parcela}{num_parcelas}{valor_final_movimentacao}{categoria_selecionada}{loja_selecionada}"
                            recorrencia_id = hashlib.md5(recorrencia_seed.encode('utf-8')).hexdigest()[:10]
                            novas_movimentacoes = []
                            for i in range(1, int(num_parcelas) + 1):
                                data_vencimento = add_months(data_primeira_parcela, i - 1)
                                nova_parcela = {
                                    "Data": data_input, "Loja": loja_selecionada,
                                    "Cliente": f"{cliente} (Parc. {i}/{num_parcelas})",
                                    "Valor": -valor_final_movimentacao, "Forma de Pagamento": "Pendente",
                                    "Tipo": "Saída", "Produtos Vendidos": "", "Categoria": categoria_selecionada,
                                    "Status": "Pendente", "Data Pagamento": data_vencimento,
                                    "RecorrenciaID": recorrencia_id, "TransacaoPaiID": ""
                                }
                                novas_movimentacoes.append(nova_parcela)
                            st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame(novas_movimentacoes)], ignore_index=True)
                            commit_msg = f"Cadastro de Empréstimo Recorrente: {cliente}"
                        else:
                            nova_linha_data = {
                                "Data": data_input, "Loja": loja_selecionada, "Cliente": cliente,
                                "Valor": valor_armazenado, "Forma de Pagamento": forma_pagamento,
                                "Tipo": tipo, "Produtos Vendidos": "", "Categoria": categoria_selecionada,
                                "Status": status_selecionado, "Data Pagamento": data_pagamento_final,
                                "RecorrenciaID": "", "TransacaoPaiID": ""
                            }
                            st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([nova_linha_data])], ignore_index=True)
                            commit_msg = f"Registro de Empréstimo: {cliente}"

                        salvar_dados_no_github(st.session_state.df, commit_msg)
                        st.cache_data.clear()
                        st.success("Empréstimo registrado com sucesso!")
                        st.rerun()

        else: # Workflow Padrão
            st.subheader("Nova Movimentação" if not edit_mode else "Editar Movimentação Existente")

            if 'divida_a_quitar' in st.session_state and st.session_state.divida_a_quitar is not None:
                idx_quitar = st.session_state.divida_a_quitar
                try:
                    divida_para_quitar = st.session_state.df.loc[idx_quitar].copy()
                except Exception as e:
                    st.session_state.divida_a_quitar = None
                    st.error(f"Erro ao carregar dívida: {e}. Cancelando quitação.")
                    st.rerun()

                valor_em_aberto = calcular_valor_em_aberto(divida_para_quitar)
                if valor_em_aberto <= 0.01:
                    st.session_state.divida_a_quitar = None
                    st.warning("Dívida já quitada."); st.rerun()

                st.subheader(f"✅ Quitar Dívida: {divida_para_quitar['Cliente']}")
                st.info(f"Valor Total em Aberto: **R$ {valor_em_aberto:,.2f}**")

                with st.form("form_quitar_divida_rapida"):
                    col_q1, col_q2, col_q3 = st.columns(3)
                    with col_q1:
                        valor_pago = st.number_input(f"Valor Pago Agora (Máx: R$ {valor_em_aberto:,.2f})", min_value=0.01, max_value=valor_em_aberto, value=valor_em_aberto, format="%.2f", key="input_valor_pago_quitar")
                    with col_q2:
                        data_conclusao = st.date_input("Data Real do Pagamento", value=date.today(), key="data_conclusao_quitar")
                    with col_q3:
                        forma_pagt_concluir = st.selectbox("Forma de Pagamento", FORMAS_PAGAMENTO, key="forma_pagt_quitar")
                    concluir = st.form_submit_button("✅ Registrar Pagamento e Quitar", type="primary", use_container_width=True)
                    cancelar_quitacao = st.form_submit_button("❌ Cancelar Quitação", type="secondary", use_container_width=True)
                    if cancelar_quitacao:
                        st.session_state.divida_a_quitar = None
                        st.rerun()
                    if concluir:
                        valor_restante = round(valor_em_aberto - valor_pago, 2)
                        idx_original = idx_quitar
                        row_original = divida_para_quitar
                        valor_pagamento_com_sinal = valor_pago if row_original['Tipo'] == 'Entrada' else -valor_pago
                        nova_transacao_pagamento = {"Data": data_conclusao, "Loja": row_original['Loja'], "Cliente": f"{row_original['Cliente'].split(' (')[0]} (Pagto de R$ {valor_pago:,.2f})", "Valor": valor_pagamento_com_sinal, "Forma de Pagamento": forma_pagt_concluir, "Tipo": row_original['Tipo'], "Produtos Vendidos": row_original['Produtos Vendidos'], "Categoria": row_original['Categoria'], "Status": "Realizada", "Data Pagamento": data_conclusao, "RecorrenciaID": row_original['RecorrenciaID'],"TransacaoPaiID": idx_original}
                        st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([nova_transacao_pagamento])], ignore_index=True)
                        if valor_restante > 0.01:
                            novo_valor_restante_com_sinal = valor_restante if row_original['Tipo'] == 'Entrada' else -valor_restante
                            st.session_state.df.loc[idx_original, 'Valor'] = novo_valor_restante_com_sinal
                            st.session_state.df.loc[idx_original, 'Cliente'] = f"{row_original['Cliente'].split(' (')[0]} (EM ABERTO: R$ {valor_restante:,.2f})"
                            commit_msg = f"Pagamento parcial de R$ {valor_pago:,.2f} da dívida. Resta R$ {valor_restante:,.2f}."
                        else:
                            st.session_state.df = st.session_state.df.drop(idx_original, errors='ignore')
                            if row_original["Tipo"] == "Entrada" and row_original["Produtos Vendidos"]:
                                try:
                                    produtos_vendidos = ast.literal_eval(row_original['Produtos Vendidos'])
                                    for item in produtos_vendidos:
                                        if item.get("Produto_ID"): ajustar_estoque(item["Produto_ID"], item["Quantidade"], "debitar")
                                    if salvar_produtos_no_github(st.session_state.produtos, f"Débito de estoque por conclusão total"): inicializar_produtos.clear()
                                except: st.warning("⚠️ Venda concluída, mas falha no débito do estoque (JSON inválido).")
                            commit_msg = f"Pagamento total de R$ {valor_pago:,.2f} da dívida."
                        if salvar_dados_no_github(st.session_state.df, commit_msg):
                            st.session_state.divida_a_quitar = None
                            st.session_state.cliente_selecionado_divida = None
                            st.cache_data.clear()
                            st.rerun()
                st.stop()

            col_principal_1, col_principal_2 = st.columns([1, 1])
            with col_principal_1:
                tipo = st.radio("Tipo", ["Entrada", "Saída"], index=0 if default_tipo == "Entrada" else 1, key="input_tipo", disabled=edit_mode)

            is_recorrente = False
            status_selecionado = default_status
            data_primeira_parcela = date.today().replace(day=1) + timedelta(days=32)
            valor_parcela = default_valor
            nome_despesa_recorrente = default_cliente
            num_parcelas = 1
            valor_calculado = 0.0
            produtos_vendidos_json = ""
            categoria_selecionada = ""
            if tipo == "Entrada":
                with col_principal_2:
                    cliente = st.text_input("Nome do Cliente (ou Descrição)", value=default_cliente, key="input_cliente_form", on_change=lambda: st.session_state.update(cliente_selecionado_divida="CHECKED", edit_id=None, divida_a_quitar=None), disabled=edit_mode)
                    if cliente.strip() and not edit_mode:
                        df_dividas_cliente = df_exibicao[(df_exibicao["Cliente"].astype(str).str.lower().str.startswith(cliente.strip().lower())) & (df_exibicao["Status"] == "Pendente") & (df_exibicao["Tipo"] == "Entrada")].sort_values(by="Data Pagamento", ascending=True).copy()
                        if not df_dividas_cliente.empty:
                            total_divida = df_dividas_cliente["Valor"].abs().round(2).sum()
                            divida_mais_antiga = df_dividas_cliente.iloc[0]
                            valor_divida_antiga = calcular_valor_em_aberto(divida_mais_antiga)
                            original_idx_divida = divida_mais_antiga['original_index']
                            vencimento_str = divida_mais_antiga['Data Pagamento'].strftime('%d/%m/%Y') if pd.notna(divida_mais_antiga['Data Pagamento']) else "S/ Data"
                            st.session_state.cliente_selecionado_divida = divida_mais_antiga.name
                            st.warning(f"💰 Dívida em Aberto para {cliente}: R$ {valor_divida_antiga:,.2f}")
                            st.info(f"Total Pendente: **R$ {total_divida:,.2f}**. Mais antiga venceu/vence: **{vencimento_str}**")
                            col_btn_add, col_btn_conc, col_btn_canc = st.columns(3)
                            if col_btn_add.button("➕ Adicionar Mais Produtos à Dívida", key="btn_add_produtos", use_container_width=True, type="secondary"):
                                st.session_state.edit_id = original_idx_divida
                                st.session_state.edit_id_loaded = None
                                st.rerun()
                            if col_btn_conc.button("✅ Concluir/Pagar Dívida", key="btn_concluir_divida", use_container_width=True, type="primary"):
                                st.session_state.divida_a_quitar = divida_mais_antiga['original_index']
                                st.session_state.edit_id = None
                                st.session_state.edit_id_loaded = None
                                st.session_state.lista_produtos = []
                                st.rerun()
                            if col_btn_canc.button("🗑️ Cancelar Dívida", key="btn_cancelar_divida", use_container_width=True):
                                df_to_delete = df_dividas_cliente.copy()
                                for idx in df_to_delete['original_index'].tolist():
                                    st.session_state.df = st.session_state.df.drop(idx, errors='ignore')
                                if salvar_dados_no_github(st.session_state.df, f"Cancelamento de {df_to_delete.shape[0]} dívida(s) de {cliente.strip()}"):
                                    st.session_state.cliente_selecionado_divida = None
                                    st.session_state.edit_id_loaded = None
                                    st.cache_data.clear()
                                    st.success(f"{df_to_delete.shape[0]} dívida(s) de {cliente.strip()} cancelada(s) com sucesso!")
                                    st.rerun()
                        else:
                            st.session_state.cliente_selecionado_divida = None

                st.markdown("#### 🛍️ Detalhes dos Produtos")
                # ... (resto do código de Entrada Padrão)

            else: # Saída Padrão
                st.markdown("---")
                col_saida_1, col_saida_2 = st.columns(2)

                with col_saida_1:
                    st.markdown("#### ⚙️ Centro de Custo (Saída)")
                    if not edit_mode:
                        is_recorrente = st.checkbox("🔄 Cadastrar como Despesa Recorrente (Parcelas)", key="input_is_recorrente")

                    default_select_index = 0
                    custom_desc_default = ""
                    if default_categoria in CATEGORIAS_SAIDA:
                        default_select_index = CATEGORIAS_SAIDA.index(default_categoria)
                    elif default_categoria.startswith("Outro: "):
                        default_select_index = CATEGORIAS_SAIDA.index("Outro/Diversos") if "Outro/Diversos" in CATEGORIAS_SAIDA else 0
                        custom_desc_default = default_categoria.replace("Outro: ", "")

                    categoria_selecionada = st.selectbox("Categoria de Gasto",
                                                         CATEGORIAS_SAIDA,
                                                         index=default_select_index,
                                                         key="input_categoria_saida",
                                                         disabled=is_recorrente and not edit_mode)

                    if categoria_selecionada == "Outro/Diversos" and not (is_recorrente and not edit_mode):
                        descricao_personalizada = st.text_input("Especifique o Gasto",
                                                                value=custom_desc_default,
                                                                key="input_custom_category")
                        if descricao_personalizada:
                            categoria_selecionada = f"Outro: {descricao_personalizada}"

                with col_saida_2:
                    # ... (resto do código de Saída Padrão)
                    pass


    # --- ABA DE MOVIMENTAÇÕES E RESUMO ---
    with tab_mov:
        hoje = date.today()
        primeiro_dia_mes = hoje.replace(day=1)
        ultimo_dia_mes = (hoje.replace(month=hoje.month % 12 + 1, day=1) if hoje.month != 12 else hoje.replace(year=hoje.year + 1, month=1, day=1)) - timedelta(days=1)

        df_mes_atual_realizado = df_exibicao[
            (df_exibicao["Data"] >= primeiro_dia_mes) &
            (df_exibicao["Data"] <= ultimo_dia_mes) &
            (df_exibicao["Status"] == "Realizada")
        ]

        st.subheader(f"📊 Resumo Financeiro Geral")
        total_entradas_mes, total_saidas_mes, saldo_mes = calcular_resumo(df_mes_atual_realizado)

        df_geral_realizado = df_exibicao[
            (df_exibicao['Status'] == 'Realizada') &
            (df_exibicao['Categoria'] != CATEGORIA_EMPRESTIMO_SAIDA)
        ]
        _, _, saldo_geral_total = calcular_resumo(df_geral_realizado)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric(f"Entradas (Mês: {primeiro_dia_mes.strftime('%b')})", f"R$ {total_entradas_mes:,.2f}")
        col2.metric(f"Saídas (Mês: {primeiro_dia_mes.strftime('%b')})", f"R$ {total_saidas_mes:,.2f}")
        col3.metric("Saldo do Mês (Realizado)", f"R$ {saldo_mes:,.2f}", delta=f"R$ {saldo_mes:,.2f}" if saldo_mes != 0 else None)
        col4.metric("Saldo Atual (Geral)", f"R$ {saldo_geral_total:,.2f}")

        st.markdown("---")
        hoje_date = date.today()
        df_pendente_alerta = df_exibicao[(df_exibicao["Status"] == "Pendente") & (pd.notna(df_exibicao["Data Pagamento"]))].copy()
        if not df_pendente_alerta.empty:
            df_pendente_alerta["Data Pagamento"] = pd.to_datetime(df_pendente_alerta["Data Pagamento"], errors='coerce').dt.date
            df_pendente_alerta.dropna(subset=["Data Pagamento"], inplace=True)
            df_vencidas = df_pendente_alerta[df_pendente_alerta["Data Pagamento"] <= hoje_date]
            contas_a_receber_vencidas = df_vencidas[df_vencidas["Tipo"] == "Entrada"]["Valor"].abs().sum()
            contas_a_pagar_vencidas = df_vencidas[df_vencidas["Tipo"] == "Saída"]["Valor"].abs().sum()
            num_receber = df_vencidas[df_vencidas["Tipo"] == "Entrada"].shape[0]
            num_pagar = df_vencidas[df_vencidas["Tipo"] == "Saída"].shape[0]
            if num_receber > 0 or num_pagar > 0:
                alert_message = "### ⚠️ DÍVIDAS PENDENTES VENCIDAS (ou Vencendo Hoje)!"
                if num_receber > 0:
                    alert_message += f"\n\n💸 **{num_receber} Contas a Receber** (Total: R$ {contas_a_receber_vencidas:,.2f})"
                if num_pagar > 0:
                    alert_message += f"\n\n💰 **{num_pagar} Contas a Pagar** (Total: R$ {contas_a_pagar_vencidas:,.2f})"
                st.error(alert_message)
                st.caption("Acesse a aba **Relatórios e Filtros > Dívidas Pendentes** para concluir essas transações.")
                st.markdown("---")

        st.subheader(f"🏠 Resumo Rápido por Loja (Mês de {primeiro_dia_mes.strftime('%m/%Y')} - Realizado)")
        df_resumo_loja = df_mes_atual_realizado.groupby('Loja')['Valor'].agg(['sum', lambda x: x[x >= 0].sum(), lambda x: abs(x[x < 0].sum())]).reset_index()
        df_resumo_loja.columns = ['Loja', 'Saldo', 'Entradas', 'Saídas']
        if not df_resumo_loja.empty:
            cols_loja = st.columns(min(4, len(df_resumo_loja.index)))
            for i, row in df_resumo_loja.iterrows():
                if i < len(cols_loja):
                    cols_loja[i].metric(label=f"{row['Loja']}", value=f"R$ {row['Saldo']:,.2f}", delta=f"E: R$ {row['Entradas']:,.2f} | S: R$ {row['Saídas']:,.2f}", delta_color="off")
        else:
            st.info("Nenhuma movimentação REALIZADA registrada neste mês.")

        st.markdown("---")
        st.subheader("📋 Tabela de Movimentações")

        if df_exibicao.empty:
            st.info("Nenhuma movimentação registrada ainda.")
        else:
            col_f1, col_f2, col_f3 = st.columns(3)

            min_date = df_exibicao["Data"].min() if pd.notna(df_exibicao["Data"].min()) else hoje
            max_date = df_exibicao["Data"].max() if pd.notna(df_exibicao["Data"].max()) else hoje

            with col_f1:
                filtro_data_inicio = st.date_input("De", value=min_date, key="quick_data_ini")
            with col_f2:
                filtro_data_fim = st.date_input("Até", value=max_date, key="quick_data_fim")
            with col_f3:
                tipos_unicos = ["Todos"] + df_exibicao["Tipo"].unique().tolist()
                filtro_tipo = st.selectbox("Filtrar por Tipo", options=tipos_unicos, key="quick_tipo")

            df_filtrado_rapido = df_exibicao.copy()

            df_filtrado_rapido = df_filtrado_rapido[
                (df_filtrado_rapido["Data"] >= filtro_data_inicio) &
                (df_filtrado_rapido["Data"] <= filtro_data_fim)
            ]

            if filtro_tipo != "Todos":
                df_filtrado_rapido = df_filtrado_rapido[df_filtrado_rapido["Tipo"] == filtro_tipo]

            df_para_mostrar = df_filtrado_rapido.copy()
            df_para_mostrar['Produtos Resumo'] = df_para_mostrar['Produtos Vendidos'].apply(format_produtos_resumo)

            colunas_tabela = ['ID Visível', 'Data', 'Loja', 'Cliente', 'Categoria', 'Valor', 'Forma de Pagamento', 'Tipo', 'Status', 'Data Pagamento', 'Produtos Resumo', 'Saldo Acumulado']

            df_styling = df_para_mostrar[colunas_tabela + ['Cor_Valor']].copy()
            styled_df = df_styling.style.apply(highlight_value, axis=1)
            styled_df = styled_df.hide(subset=['Cor_Valor'], axis=1)

            st.dataframe(
                styled_df,
                use_container_width=True,
                column_config={
                    "Valor": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f"),
                    "Saldo Acumulado": st.column_config.NumberColumn("Saldo Acumulado (R$)", format="R$ %.2f"),
                    "Produtos Resumo": st.column_config.TextColumn("Detalhe dos Produtos"),
                    "Categoria": "Categoria (C. Custo)",
                    "Data Pagamento": st.column_config.DateColumn("Data Pagt. Previsto/Real", format="DD/MM/YYYY")
                },
                height=400,
                key='movimentacoes_table_styled_display_only'
            )

            st.markdown("---")
            st.markdown("### Operações de Edição e Exclusão")

            if df_para_mostrar.empty:
                st.info("Nenhuma movimentação disponível para edição/exclusão com os filtros aplicados.")
            else:
                opcoes_movimentacao_operacao = {
                    f"ID {row['ID Visível']} | {row['Data'].strftime('%d/%m/%Y')} | {row['Cliente']} | R$ {abs(row['Valor']):,.2f}": row['original_index']
                    for index, row in df_para_mostrar.iterrows()
                }
                opcoes_keys = ["Selecione uma movimentação..."] + list(opcoes_movimentacao_operacao.keys())

                movimentacao_selecionada_str = st.selectbox(
                    "Selecione o item para Editar ou Excluir:",
                    options=opcoes_keys,
                    index=0,
                    key="select_movimentacao_operacao_lc"
                )

                original_idx_selecionado = opcoes_movimentacao_operacao.get(movimentacao_selecionada_str)
                item_selecionado_str = movimentacao_selecionada_str

                if original_idx_selecionado is not None and movimentacao_selecionada_str != "Selecione uma movimentação...":
                    row = df_exibicao[df_exibicao['original_index'] == original_idx_selecionado].iloc[0]

                    if row['Tipo'] == 'Entrada' and row['Produtos Vendidos'] and pd.notna(row['Produtos Vendidos']):
                        st.markdown("#### Detalhes dos Produtos Selecionados")
                        try:
                            try:
                                produtos = json.loads(row['Produtos Vendidos'])
                            except json.JSONDecodeError:
                                produtos = ast.literal_eval(row['Produtos Vendidos'])

                            df_detalhe = pd.DataFrame(produtos)
                            for col in ['Quantidade', 'Preço Unitário', 'Custo Unitário']:
                                df_detalhe[col] = pd.to_numeric(df_detalhe[col], errors='coerce').fillna(0)

                            df_detalhe['Total Venda'] = df_detalhe['Quantidade'] * df_detalhe['Preço Unitário']
                            df_detalhe['Total Custo'] = df_detalhe['Quantidade'] * df_detalhe['Custo Unitário']
                            df_detalhe['Lucro Bruto'] = df_detalhe['Total Venda'] - df_detalhe['Total Custo']

                            st.dataframe(df_detalhe, hide_index=True, use_container_width=True,
                                column_config={
                                    "Produto": "Produto",
                                    "Quantidade": st.column_config.NumberColumn("Qtd"),
                                    "Preço Unitário": st.column_config.NumberColumn("Preço Un.", format="R$ %.2f"),
                                    "Custo Unitário": st.column_config.NumberColumn("Custo Un.", format="R$ %.2f"),
                                    "Total Venda": st.column_config.NumberColumn("Total Venda", format="R$ %.2f"),
                                    "Total Custo": st.column_config.NumberColumn("Total Custo", format="R$ %.2f"),
                                    "Lucro Bruto": st.column_config.NumberColumn("Lucro Bruto", format="R$ %.2f", help="Venda - Custo")
                                }
                            )

                        except Exception as e:
                            st.error(f"Erro ao processar detalhes dos produtos: {e}")

                        st.markdown("---")

                    col_op_1, col_op_2 = st.columns(2)

                    if col_op_1.button(f"✏️ Editar: {item_selecionado_str}", key=f"edit_mov_{original_idx_selecionado}", use_container_width=True, type="secondary"):
                        st.session_state.edit_id = original_idx_selecionado
                        st.session_state.edit_id_loaded = None
                        st.rerun()

                    if col_op_2.button(f"🗑️ Excluir: {item_selecionado_str}", key=f"del_mov_{original_idx_selecionado}", use_container_width=True, type="primary"):
                        if row['Status'] == 'Realizada' and row['Tipo'] == 'Entrada':
                            try:
                                produtos_vendidos_antigos = ast.literal_eval(row['Produtos Vendidos'])
                                for item in produtos_vendidos_antigos:
                                    if item.get("Produto_ID"): ajustar_estoque(item["Produto_ID"], item["Quantidade"], "creditar")
                                if salvar_produtos_no_github(st.session_state.produtos, "Reversão de estoque por exclusão de venda"):
                                    inicializar_produtos.clear()
                            except: pass

                        st.session_state.df = st.session_state.df.drop(row['original_index'], errors='ignore')

                        if salvar_dados_no_github(st.session_state.df, COMMIT_MESSAGE_DELETE):
                            st.cache_data.clear()
                            st.rerun()
                else:
                    st.info("Selecione uma movimentação no menu acima para ver detalhes e opções de edição/exclusão.")

    # --- ABA DE RELATÓRIOS ---
    with tab_rel:
        st.subheader("📄 Relatório Detalhado e Comparativo")

        with st.container(border=True):
            st.markdown("#### Filtros do Relatório")

            col_f1, col_f2 = st.columns(2)
            with col_f1:
                lojas_selecionadas = st.multiselect(
                    "Selecione uma ou mais lojas/empresas",
                    options=LOJAS_DISPONIVEIS,
                    default=LOJAS_DISPONIVEIS
                )

                tipo_movimentacao = st.radio(
                    "Tipo de Movimentação",
                    ["Ambos", "Entrada", "Saída"],
                    horizontal=True,
                    key="rel_tipo"
                )

            with col_f2:
                min_date_geral = df_exibicao["Data"].min() if not df_exibicao.empty and pd.notna(df_exibicao["Data"].min()) else date.today()
                max_date_geral = df_exibicao["Data"].max() if not df_exibicao.empty and pd.notna(df_exibicao["Data"].max()) else date.today()

                data_inicio_rel = st.date_input("Data de Início", value=min_date_geral, min_value=min_date_geral, max_value=max_date_geral, key="rel_data_ini")
                data_fim_rel = st.date_input("Data de Fim", value=max_date_geral, min_value=min_date_geral, max_value=max_date_geral, key="rel_data_fim")

            if st.button("📊 Gerar Relatório Comparativo", use_container_width=True, type="primary"):

                df_relatorio = df_exibicao[
                    (df_exibicao['Status'] == 'Realizada') &
                    (df_exibicao['Loja'].isin(lojas_selecionadas)) &
                    (df_exibicao['Data'] >= data_inicio_rel) &
                    (df_exibicao['Data'] <= data_fim_rel)
                ].copy()

                if tipo_movimentacao != "Ambos":
                    df_relatorio = df_relatorio[df_relatorio['Tipo'] == tipo_movimentacao]

                if df_relatorio.empty:
                    st.warning("Nenhum dado encontrado com os filtros selecionados.")
                else:
                    df_relatorio['MesAno'] = df_relatorio['Data_dt'].dt.to_period('M').astype(str)

                    df_agrupado = df_relatorio.groupby('MesAno').apply(lambda x: pd.Series({
                        'Entradas': x[x['Valor'] > 0]['Valor'].sum(),
                        'Saídas': abs(x[x['Valor'] < 0]['Valor'].sum())
                    })).reset_index()

                    df_agrupado['Saldo'] = df_agrupado['Entradas'] - df_agrupado['Saídas']

                    df_agrupado = df_agrupado.sort_values(by='MesAno').reset_index(drop=True)
                    df_agrupado['Crescimento Entradas (%)'] = (df_agrupado['Entradas'].pct_change() * 100).fillna(0)
                    df_agrupado['Crescimento Saídas (%)'] = (df_agrupado['Saídas'].pct_change() * 100).fillna(0)

                    st.markdown("---")
                    st.subheader("Resultados do Relatório")

                    st.markdown("##### 🗓️ Tabela Comparativa Mensal")
                    st.dataframe(df_agrupado, use_container_width=True,
                        column_config={"MesAno": "Mês/Ano","Entradas": st.column_config.NumberColumn("Entradas (R$)", format="R$ %.2f"),
                            "Saídas": st.column_config.NumberColumn("Saídas (R$)", format="R$ %.2f"),
                            "Saldo": st.column_config.NumberColumn("Saldo (R$)", format="R$ %.2f"),
                            "Crescimento Entradas (%)": st.column_config.NumberColumn("Cresc. Entradas", format="%.2f%%"),
                            "Crescimento Saídas (%)": st.column_config.NumberColumn("Cresc. Saídas", format="%.2f%%")}
                    )

                    if 'Entradas' in df_agrupado.columns and not df_agrupado[df_agrupado['Entradas'] > 0].empty:
                        st.markdown("##### 🏆 Ranking de Vendas (Entradas) por Mês")
                        df_ranking = df_agrupado[['MesAno', 'Entradas']].sort_values(by='Entradas', ascending=False).reset_index(drop=True)
                        df_ranking.index += 1
                        st.dataframe(df_ranking, use_container_width=True,
                            column_config={"MesAno": "Mês/Ano","Entradas": st.column_config.NumberColumn("Total de Entradas (R$)", format="R$ %.2f")}
                        )

        st.markdown("---")

        st.subheader("🚩 Dívidas Pendentes (A Pagar e A Receber)")

        df_pendentes = df_exibicao[df_exibicao["Status"] == "Pendente"].copy()

        if df_pendentes.empty:
            st.info("Parabéns! Não há dívidas pendentes registradas.")
        else:
            df_pendentes["Data Pagamento"] = pd.to_datetime(df_pendentes["Data Pagamento"], errors='coerce').dt.date
            df_pendentes_ordenado = df_pendentes.sort_values(by=["Data Pagamento", "Tipo", "Data"], ascending=[True, True, True]).reset_index(drop=True)
            hoje_date = date.today()
            df_pendentes_ordenado['Dias Até/Atraso'] = df_pendentes_ordenado['Data Pagamento'].apply(
                lambda x: (x - hoje_date).days if pd.notna(x) else float('inf')
            )

            total_receber = df_pendentes_ordenado[df_pendentes_ordenado["Tipo"] == "Entrada"]["Valor"].abs().sum()
            total_pagar = df_pendentes_ordenado[df_pendentes_ordenado["Tipo"] == "Saída"]["Valor"].abs().sum()

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
                st.markdown("##### ✅ Concluir Dívida Pendente (Pagamento Parcial ou Total)")

                default_concluir_idx = 0
                divida_para_concluir = None

                opcoes_pendentes_map = {
                    f"ID {row['ID Visível']} | {row['Tipo']} | R$ {calcular_valor_em_aberto(row):,.2f} | Venc.: {row['Data Pagamento'].strftime('%d/%m/%Y') if pd.notna(row['Data Pagamento']) else 'S/ Data'} | {row['Cliente']}": row['original_index']
                    for index, row in df_pendentes_ordenado.iterrows()
                }
                opcoes_keys = ["Selecione uma dívida..."] + list(opcoes_pendentes_map.keys())

                if 'divida_parcial_id' in st.session_state and st.session_state.divida_parcial_id is not None:
                    original_idx_para_selecionar = st.session_state.divida_parcial_id
                    try:
                        divida_row = df_pendentes_ordenado[df_pendentes_ordenado['original_index'] == original_idx_para_selecionar].iloc[0]
                        valor_row_formatado = calcular_valor_em_aberto(divida_row)
                        option_key = f"ID {divida_row['ID Visível']} | {divida_row['Tipo']} | R$ {valor_row_formatado:,.2f} | Venc.: {divida_row['Data Pagamento'].strftime('%d/%m/%Y') if pd.notna(divida_row['Data Pagamento']) else 'S/ Data'} | {divida_row['Cliente']}"

                        if option_key in opcoes_keys:
                            default_concluir_idx = opcoes_keys.index(option_key)

                        divida_para_concluir = divida_row
                    except Exception:
                        pass

                    st.session_state.divida_parcial_id = None


                divida_selecionada_str = st.selectbox(
                    "Selecione a Dívida para Concluir:",
                    options=opcoes_keys,
                    index=default_concluir_idx,
                    key="select_divida_concluir"
                )

                original_idx_concluir = opcoes_pendentes_map.get(divida_selecionada_str)

                if original_idx_concluir is not None and divida_para_concluir is None:
                    divida_para_concluir = df_pendentes_ordenado[df_pendentes_ordenado['original_index'] == original_idx_concluir].iloc[0]

                if divida_para_concluir is not None:
                    valor_em_aberto = calcular_valor_em_aberto(divida_para_concluir)

                    st.markdown(f"**Valor em Aberto:** R$ {valor_em_aberto:,.2f}")

                    col_c1, col_c2, col_c3 = st.columns(3)
                    with col_c1:
                        valor_pago = st.number_input(
                            f"Valor Pago (Máx: R$ {valor_em_aberto:,.2f})",
                            min_value=0.01,
                            max_value=valor_em_aberto,
                            value=valor_em_aberto,
                            format="%.2f",
                            key="input_valor_pago_parcial"
                        )
                    with col_c2:
                        data_conclusao = st.date_input("Data Real do Pagamento", value=hoje_date, key="data_conclusao_divida")
                    with col_c3:
                        forma_pagt_concluir = st.selectbox("Forma de Pagamento", FORMAS_PAGAMENTO, key="forma_pagt_concluir")

                    concluir = st.form_submit_button("✅ Registrar Pagamento", use_container_width=True, type="primary")

                    if concluir:
                        valor_restante = round(valor_em_aberto - valor_pago, 2)
                        idx_original = original_idx_concluir

                        if idx_original not in st.session_state.df.index:
                            st.error("Erro interno ao localizar dívida. O registro original foi perdido.")
                            st.rerun()
                            return

                        row_original = st.session_state.df.loc[idx_original].copy()

                        valor_pagamento_com_sinal = valor_pago if row_original['Tipo'] == 'Entrada' else -valor_pago

                        nova_transacao_pagamento = {
                            "Data": data_conclusao,
                            "Loja": row_original['Loja'],
                            "Cliente": f"{row_original['Cliente'].split(' (')[0]} (Pagto de R$ {valor_pago:,.2f})",
                            "Valor": valor_pagamento_com_sinal,
                            "Forma de Pagamento": forma_pagt_concluir,
                            "Tipo": row_original['Tipo'],
                            "Produtos Vendidos": row_original['Produtos Vendidos'],
                            "Categoria": row_original['Categoria'],
                            "Status": "Realizada",
                            "Data Pagamento": data_conclusao,
                            "RecorrenciaID": row_original['RecorrenciaID'],
                            "TransacaoPaiID": idx_original
                        }

                        st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([nova_transacao_pagamento])], ignore_index=True)

                        if valor_restante > 0.01:

                            novo_valor_restante_com_sinal = valor_restante if row_original['Tipo'] == 'Entrada' else -valor_restante

                            st.session_state.df.loc[idx_original, 'Valor'] = novo_valor_restante_com_sinal
                            st.session_state.df.loc[idx_original, 'Cliente'] = f"{row_original['Cliente'].split(' (')[0]} (EM ABERTO: R$ {valor_restante:,.2f})"

                            commit_msg = f"Pagamento parcial de R$ {valor_pago:,.2f} da dívida {row_original['Cliente']}. Resta R$ {valor_restante:,.2f}."

                        else:

                            st.session_state.df = st.session_state.df.drop(idx_original, errors='ignore')

                            if row_original["Tipo"] == "Entrada" and row_original["Produtos Vendidos"]:
                                try:
                                    produtos_vendidos = ast.literal_eval(row_original['Produtos Vendidos'])
                                    for item in produtos_vendidos:
                                        if item.get("Produto_ID"): ajustar_estoque(item["Produto_ID"], item["Quantidade"], "debitar")
                                    if salvar_produtos_no_github(st.session_state.produtos, f"Débito de estoque por conclusão total {row_original['Cliente']}"): inicializar_produtos.clear()
                                except: st.warning("⚠️ Venda concluída, mas falha no débito do estoque (JSON inválido).")

                            commit_msg = f"Pagamento total de R$ {valor_pago:,.2f} da dívida {row_original['Cliente'].split(' (')[0]}."


                        if salvar_dados_no_github(st.session_state.df, commit_msg):
                            st.session_state.divida_parcial_id = None
                            st.cache_data.clear()
                            st.rerun()
                else:
                    st.info("Selecione uma dívida válida para prosseguir com o pagamento.")

            st.markdown("---")

            st.markdown("##### Tabela Detalhada de Dívidas Pendentes")
            df_para_mostrar_pendentes = df_pendentes_ordenado.copy()
            df_para_mostrar_pendentes['Status Vencimento'] = df_para_mostrar_pendentes['Dias Até/Atraso'].apply(
                lambda x: f"Atrasado {-x} dias" if x < 0 else (f"Vence em {x} dias" if x > 0 else "Vence Hoje") if pd.notna(x) else "Sem Data"
            )
            df_styling_pendentes = df_para_mostrar_pendentes.style.apply(highlight_pendentes, axis=1)

            st.dataframe(df_styling_pendentes, use_container_width=True, hide_index=True)


# Para rodar este arquivo, você pode chamá-lo diretamente
if __name__ == '__main__':
    livro_caixa()
