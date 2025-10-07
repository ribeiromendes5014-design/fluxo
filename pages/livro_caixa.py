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
# 🚨 CORREÇÃO: Bloco de Importação das Funções Auxiliares do utils.py
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

def highlight_value(row):
    """Função auxiliar para colorir o valor na tabela de movimentações."""
    color = row['Cor_Valor']
    return [f'color: {color}' if col == 'Valor' else '' for col in row.index]


def livro_caixa():
    
    st.header("📘 Livro Caixa - Gerenciamento de Movimentações") 

    # Funções importadas agora disponíveis
    produtos = inicializar_produtos() 

    if "df" not in st.session_state: st.session_state.df = carregar_livro_caixa()
    # Garante que todas as colunas de controle existam
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
    # NOVA CHAVE: Para controlar a quitação rápida na aba Nova Movimentação
    if "divida_a_quitar" not in st.session_state: st.session_state.divida_a_quitar = None 
    
    # CORREÇÃO CRÍTICA: Inicializa a aba ativa com um valor padrão válido
    abas_validas = ["📝 Nova Movimentação", "📋 Movimentações e Resumo", "📈 Relatórios e Filtros"]
    
    if "aba_ativa_livro_caixa" not in st.session_state or str(st.session_state.aba_ativa_livro_caixa) not in abas_validas: 
        st.session_state.aba_ativa_livro_caixa = abas_validas[0]

    # --- CORREÇÃO DO KEYERROR APLICADA AQUI ---
    # Os dados em st.session_state.df já foram processados pela função carregar_livro_caixa().
    # Não é necessário chamar processar_dataframe() novamente.
    df_exibicao = st.session_state.df.copy() # Usamos o df direto da session_state
    df_dividas = st.session_state.df # Usado para operações de salvamento
    # --- FIM DA CORREÇÃO ---

    # CORREÇÃO: Garante que os produtos para venda incluem variações e itens simples (PaiID nulo ou vazio)
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
            
            # CORREÇÃO: Carrega a lista de produtos APENAS se o item for diferente do último carregado
            if st.session_state.edit_id_loaded != original_idx_to_edit:
                if default_tipo == "Entrada" and default_produtos_json:
                    try:
                        try:
                            produtos_list = json.loads(default_produtos_json)
                        except json.JSONDecodeError:
                            produtos_list = ast.literal_eval(default_produtos_json)

                        for p in produtos_list:
                            p['Quantidade'] = float(p.get('Quantidade', 0))
                            p['Preço Unitário'] = float(p.get('Preço Unitário', 0))
                            p['Custo Unitário'] = float(p.get('Custo Unitário', 0))
                            p['Produto_ID'] = str(p.get('Produto_ID', ''))
                            
                        st.session_state.lista_produtos = [p for p in produtos_list if p['Quantidade'] > 0] 
                    except:
                        st.session_state.lista_produtos = []
                else: # Tipo Saída ou sem produtos, limpa a lista.
                    st.session_state.lista_produtos = []
                
                st.session_state.edit_id_loaded = original_idx_to_edit # Marca como carregado
                st.session_state.cb_lido_livro_caixa = "" # Limpa CB lido
            
            st.warning(f"Modo EDIÇÃO ATIVO: Movimentação ID {movimentacao_para_editar['ID Visível']}")
            
        else:
            st.session_state.edit_id = None
            st.session_state.edit_id_loaded = None 
            st.session_state.lista_produtos = [] 
            edit_mode = False
            st.info("Movimentação não encontrada, saindo do modo de edição.")
            st.rerun() 
    else:
        # NOVO: Se não está no modo edição, garante que a lista esteja vazia e a flag limpa
        if st.session_state.edit_id_loaded is not None:
             st.session_state.edit_id_loaded = None
             st.session_state.lista_produtos = []
        # NOVO: Limpa o alerta de dívida, exceto se houver um re-run imediato
        if st.session_state.cliente_selecionado_divida and st.session_state.cliente_selecionado_divida != "CHECKED":
             st.session_state.cliente_selecionado_divida = None


    # --- CRIAÇÃO DAS NOVAS ABAS ---
    tab_nova_mov, tab_mov, tab_rel = st.tabs(abas_validas)


    # ==============================================================================================
    # NOVA ABA: NOVA MOVIMENTAÇÃO (Substitui a Sidebar)
    # ==============================================================================================
    with tab_nova_mov:
        
        st.subheader("Nova Movimentação" if not edit_mode else "Editar Movimentação Existente")

        # --- NOVO: FORMULÁRIO DE QUITAÇÃO RÁPIDA (Se houver dívida selecionada na aba) ---
        if 'divida_a_quitar' in st.session_state and st.session_state.divida_a_quitar is not None:
            
            idx_quitar = st.session_state.divida_a_quitar
            
            # --- VERIFICAÇÃO DE SEGURANÇA ADICIONAL ---
            try:
                # Tenta acessar o registro. Isso deve retornar uma Series do Pandas.
                divida_para_quitar = st.session_state.df.loc[idx_quitar].copy()
            except KeyError:
                st.session_state.divida_a_quitar = None
                st.error("Erro: A dívida selecionada não foi encontrada no registro principal. Tente novamente ou cancele.")
                st.rerun()
                
            except Exception as e:
                st.session_state.divida_a_quitar = None
                st.error(f"Erro inesperado ao carregar dívida: {e}. Cancelando quitação.")
                st.rerun()

            valor_em_aberto = calcular_valor_em_aberto(divida_para_quitar)
            
            if valor_em_aberto <= 0.01:
                st.session_state.divida_a_quitar = None
                st.warning("Dívida já quitada.")
                st.rerun()
            
            st.subheader(f"✅ Quitar Dívida: {divida_para_quitar['Cliente']}")
            st.info(f"Valor Total em Aberto: **R$ {valor_em_aberto:,.2f}**")
            
            with st.form("form_quitar_divida_rapida", clear_on_submit=False):
                col_q1, col_q2, col_q3 = st.columns(3)
                
                with col_q1:
                    valor_pago = st.number_input(
                        f"Valor Pago Agora (Máx: R$ {valor_em_aberto:,.2f})", 
                        min_value=0.01, 
                        max_value=valor_em_aberto, 
                        value=valor_em_aberto, # Valor sugerido é o total
                        format="%.2f",
                        key="input_valor_pago_quitar"
                    )
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
                    
                    if idx_original not in st.session_state.df.index:
                        st.error("Erro interno ao localizar dívida. O registro original foi perdido.")
                        st.rerun()
                        return

                    row_original = divida_para_quitar 
                    
                    # 1. Cria a transação de pagamento (Realizada)
                    valor_pagamento_com_sinal = valor_pago if row_original['Tipo'] == 'Entrada' else -valor_pago
                    
                    # Cria a nova transação de pagamento
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
                    
                    # 2. Atualiza a dívida original
                    if valor_restante > 0.01:
                        # Pagamento parcial: atualiza a dívida original
                        novo_valor_restante_com_sinal = valor_restante if row_original['Tipo'] == 'Entrada' else -valor_restante

                        st.session_state.df.loc[idx_original, 'Valor'] = novo_valor_restante_com_sinal
                        st.session_state.df.loc[idx_original, 'Cliente'] = f"{row_original['Cliente'].split(' (')[0]} (EM ABERTO: R$ {valor_restante:,.2f})"
                        
                        commit_msg = f"Pagamento parcial de R$ {valor_pago:,.2f} da dívida. Resta R$ {valor_restante:,.2f}."
                        
                    else: 
                        # Pagamento total: exclui a linha original
                        st.session_state.df = st.session_state.df.drop(idx_original, errors='ignore')
                        
                        # Débito de Estoque (Apenas para Entrada)
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
                        st.session_state.cliente_selecionado_divida = None # Garante que o alerta do cliente suma
                        st.cache_data.clear()
                        st.rerun()

            # Não exibe o restante do formulário "Nova Movimentação" se estiver no modo quitação
            st.stop()
        
        # O layout principal do formulário agora vai aqui, sem o `st.sidebar`
        
        # Categoria Principal
        col_principal_1, col_principal_2 = st.columns([1, 1])
        with col_principal_1:
            # ALTERADO: Adicionado "Empréstimo" às opções de tipo
            opcoes_tipo = ["Entrada", "Saída", "Empréstimo"]
            default_index_tipo = opcoes_tipo.index(default_tipo) if default_tipo in opcoes_tipo else 0
            tipo = st.radio("Tipo", opcoes_tipo, index=default_index_tipo, key="input_tipo", disabled=edit_mode)
        
        # Variáveis de estado
        is_recorrente = False
        status_selecionado = default_status
        data_primeira_parcela = date.today().replace(day=1) + timedelta(days=32)
        valor_parcela = default_valor
        nome_despesa_recorrente = default_cliente
        num_parcelas = 1
        valor_calculado = 0.0
        produtos_vendidos_json = ""
        categoria_selecionada = default_categoria # Usar default_categoria como inicial
        
        # NOVAS VARIÁVEIS DE ESTADO PARA EMPRÉSTIMO
        is_emprestimo = False
        emprestimo_ja_gasto = None # True, False ou None (Não selecionado)
        categoria_gasto_emprestimo = None
        # FIM NOVAS VARIÁVEIS

        # --- Seção de Entrada (Venda/Produtos) ---
        if tipo == "Entrada":
            
            # Campo de Cliente (precisa ser definido antes para a lógica de dívida)
            with col_principal_2:
                cliente = st.text_input("Nome do Cliente (ou Descrição)", 
                                        value=default_cliente, 
                                        key="input_cliente_form",
                                        on_change=lambda: st.session_state.update(cliente_selecionado_divida="CHECKED", edit_id=None, divida_a_quitar=None), # Gatilho de busca
                                        disabled=edit_mode)
                
                # NOVO: Lógica de Alerta Inteligente de Dívida
                if cliente.strip() and not edit_mode:
                    
                    df_dividas_cliente = df_exibicao[
                        
                        (df_exibicao["Cliente"].astype(str).str.lower().str.startswith(cliente.strip().lower())) &
                        
                        (df_exibicao["Status"] == "Pendente") &
                        (df_exibicao["Tipo"] == "Entrada")
                    ].sort_values(by="Data Pagamento", ascending=True).copy()

                    if not df_dividas_cliente.empty:
                        
                        # CORREÇÃO: Arredonda o valor antes de somar para evitar erros de float
                        total_divida = df_dividas_cliente["Valor"].abs().round(2).sum() 
                        num_dividas = df_dividas_cliente.shape[0]
                        divida_mais_antiga = df_dividas_cliente.iloc[0]
                        
                        # Extrai o valor da dívida mais antiga (a que será editada/quitada) usando a nova função
                        valor_divida_antiga = calcular_valor_em_aberto(divida_mais_antiga)
                        
                        original_idx_divida = divida_mais_antiga['original_index']
                        vencimento_str = divida_mais_antiga['Data Pagamento'].strftime('%d/%m/%Y') if pd.notna(divida_mais_antiga['Data Pagamento']) else "S/ Data"

                        st.session_state.cliente_selecionado_divida = divida_mais_antiga.name # Salva o índice original

                        # Sua linha de alerta corrigida (agora com o valor que é usado para quitação)
                        st.warning(f"💰 Dívida em Aberto para {cliente}: R$ {valor_divida_antiga:,.2f}") 
                        
                        # ALERTA DE INFORMAÇÃO sobre o total
                        st.info(f"Total Pendente: **R$ {total_divida:,.2f}**. Mais antiga venceu/vence: **{vencimento_str}**")

                        col_btn_add, col_btn_conc, col_btn_canc = st.columns(3)

                        if col_btn_add.button("➕ Adicionar Mais Produtos à Dívida", key="btn_add_produtos", use_container_width=True, type="secondary"):
                            st.session_state.edit_id = original_idx_divida
                            st.session_state.edit_id_loaded = None # Força o recarregamento dos dados na próxima execução
                            st.rerun()

                        # ALTERADO: Este botão agora define a nova chave de estado para abrir o formulário de quitação rápida
                        if col_btn_conc.button("✅ Concluir/Pagar Dívida", key="btn_concluir_divida", use_container_width=True, type="primary"):
                            st.session_state.divida_a_quitar = divida_mais_antiga['original_index']
                            st.session_state.edit_id = None 
                            st.session_state.edit_id_loaded = None 
                            st.session_state.lista_produtos = []
                            st.rerun()

                        if col_btn_canc.button("🗑️ Cancelar Dívida", key="btn_cancelar_divida", use_container_width=True):
                            # Lógica simplificada de exclusão (cancelamento)
                            df_to_delete = df_dividas_cliente.copy()
                            for idx in df_to_delete['original_index'].tolist():
                                st.session_state.df = st.session_state.df.drop(idx, errors='ignore')
                            
                            if salvar_dados_no_github(st.session_state.df, f"Cancelamento de {num_dividas} dívida(s) de {cliente.strip()}"):
                                st.session_state.cliente_selecionado_divida = None
                                st.session_state.edit_id_loaded = None 
                                st.cache_data.clear()
                                st.success(f"{num_dividas} dívida(s) de {cliente.strip()} cancelada(s) com sucesso!")
                                st.rerun()
                    else:
                        st.session_state.cliente_selecionado_divida = None # Limpa a chave se não houver dívida

                st.markdown("#### 🛍️ Detalhes dos Produtos")
                
                # Exibe a soma calculada dos produtos (se houver)
                if st.session_state.lista_produtos:
                    df_produtos = pd.DataFrame(st.session_state.lista_produtos)
                    df_produtos['Quantidade'] = pd.to_numeric(df_produtos['Quantidade'], errors='coerce').fillna(0)
                    df_produtos['Preço Unitário'] = pd.to_numeric(df_produtos['Preço Unitário'], errors='coerce').fillna(0.0)
                    df_produtos['Custo Unitário'] = pd.to_numeric(df_produtos['Custo Unitário'], errors='coerce').fillna(0.0)
                    
                    valor_calculado = (df_produtos['Quantidade'] * df_produtos['Preço Unitário']).sum()
                    
                    produtos_para_json = df_produtos[['Produto_ID', 'Produto', 'Quantidade', 'Preço Unitário', 'Custo Unitário']].to_dict('records')
                    produtos_vendidos_json = json.dumps(produtos_para_json)
                    
                    st.success(f"Soma Total da Venda Calculada: R$ {valor_calculado:,.2f}")

            # Expandido para adicionar produtos
            with st.expander("➕ Adicionar/Limpar Lista de Produtos (Venda)", expanded=True):
                
                col_prod_lista, col_prod_add = st.columns([1, 1])
                
                with col_prod_lista:
                    st.markdown("##### Produtos Atuais:")
                    if st.session_state.lista_produtos:
                        df_exibicao_produtos = pd.DataFrame(st.session_state.lista_produtos)
                        st.dataframe(df_exibicao_produtos[['Produto', 'Quantidade', 'Preço Unitário']], use_container_width=True, hide_index=True)
                    else:
                        st.info("Lista de produtos vazia.")
                    
                    if st.button("Limpar Lista", key="limpar_lista_button", type="secondary", use_container_width=True, help="Limpa todos os produtos da lista de venda"):
                        st.session_state.lista_produtos = []
                        # NOVO: Limpa o ID de carregamento para a próxima edição/nova venda
                        st.session_state.edit_id_loaded = None 
                        st.rerun()

                with col_prod_add:
                    st.markdown("##### Adicionar Produto")
                    
                    # --- NOVO: Upload de imagem para leitura do Código de Barras ---
                    foto_cb_upload_caixa = st.file_uploader(
                        "📤 Upload de imagem do código de barras", 
                        type=["png", "jpg", "jpeg"], 
                        key="cb_upload_caixa"
                    )
                    
                    if foto_cb_upload_caixa is not None:
                        imagem_bytes = foto_cb_upload_caixa.getvalue() 
                        codigos_lidos = ler_codigo_barras_api(imagem_bytes)
                        if codigos_lidos:
                            st.session_state.cb_lido_livro_caixa = codigos_lidos[0]
                            st.toast(f"Código de barras lido: {codigos_lidos[0]}")
                        else:
                            st.session_state.cb_lido_livro_caixa = ""
                            st.error("❌ Não foi possível ler nenhum código na imagem enviada.")
                    
                    index_selecionado = 0
                    if st.session_state.cb_lido_livro_caixa: 
                        opcao_encontrada = encontrar_opcao_por_cb(st.session_state.cb_lido_livro_caixa, produtos_para_venda, opcoes_produtos)
                        if opcao_encontrada:
                            index_selecionado = opcoes_produtos.index(opcao_encontrada)
                            st.toast(f"Produto correspondente ao CB encontrado! Selecionado: {opcao_encontrada}")
                        else:
                            st.warning(f"Código '{st.session_state.cb_lido_livro_caixa}' lido, mas nenhum produto com esse CB encontrado no estoque.")
                            st.session_state.cb_lido_livro_caixa = ""

                    produto_selecionado = st.selectbox(
                        "Selecione o Produto (ID | Nome)", 
                        opcoes_produtos, 
                        key="input_produto_selecionado",
                        index=index_selecionado if index_selecionado != 0 else (opcoes_produtos.index(st.session_state.input_produto_selecionado) if st.session_state.input_produto_selecionado in opcoes_produtos else 0)
                    )
                    
                    if produto_selecionado != opcoes_produtos[index_selecionado] and index_selecionado != 0 and st.session_state.cb_lido_livro_caixa:
                         st.session_state.cb_lido_livro_caixa = ""

                    if produto_selecionado == OPCAO_MANUAL:
                        # Lógica de Adição Manual
                        nome_produto_manual = st.text_input("Nome do Produto (Manual)", value=st.session_state.input_nome_prod_manual, key="input_nome_prod_manual")
                        col_m1, col_m2 = st.columns(2)
                        with col_m1:
                            quantidade_manual = st.number_input("Qtd Manual", min_value=0.01, value=st.session_state.input_qtd_prod_manual, step=1.0, key="input_qtd_prod_manual")
                            custo_unitario_manual = st.number_input("Custo Unitário (R$)", min_value=0.00, value=st.session_state.input_custo_prod_manual, format="%.2f", key="input_custo_prod_manual")
                        with col_m2:
                            preco_unitario_manual = st.number_input("Preço Unitário (R$)", min_value=0.01, format="%.2f", value=st.session_state.input_preco_prod_manual, key="input_preco_prod_manual")
                        
                        if st.button("Adicionar Manual", key="adicionar_item_manual_button", use_container_width=True,
                            on_click=callback_adicionar_manual,
                            args=(nome_produto_manual, quantidade_manual, preco_unitario_manual, custo_unitario_manual)): st.rerun() 

                    elif produto_selecionado != "":
                        # Lógica de Adição do Estoque
                        produto_id_selecionado = extrair_id_do_nome(produto_selecionado) 
                        produto_row_completa = produtos_para_venda[produtos_para_venda["ID"] == produto_id_selecionado]
                        
                        if not produto_row_completa.empty:
                            produto_data = produto_row_completa.iloc[0]
                            nome_produto = produto_data['Nome']
                            preco_sugerido = produto_data['PrecoVista'] 
                            custo_unit = produto_data['PrecoCusto']
                            estoque_disp = produto_data['Quantidade']

                            col_p1, col_p2 = st.columns(2)
                            with col_p1:
                                quantidade_input = st.number_input("Qtd", min_value=1, value=1, step=1, max_value=int(estoque_disp) if estoque_disp > 0 else 1, key="input_qtd_prod_edit")
                                st.caption(f"Estoque Disponível: {int(estoque_disp)}")
                            with col_p2:
                                preco_unitario_input = st.number_input("Preço Unitário (R$)", min_value=0.01, format="%.2f", value=float(preco_sugerido), key="input_preco_prod_edit")
                                st.caption(f"Custo Unitário: R$ {custo_unit:,.2f}")

                            if st.button("Adicionar Item", key="adicionar_item_button", use_container_width=True,
                                on_click=callback_adicionar_estoque,
                                args=(produto_id_selecionado, nome_produto, quantidade_input, preco_unitario_input, custo_unit, estoque_disp)): st.rerun()


            # Input do Valor Total e Status para Entrada
            col_entrada_valor, col_entrada_status = st.columns(2)
            with col_entrada_valor:
                valor_input_manual = st.number_input(
                    "Valor Total (R$)", 
                    value=valor_calculado if valor_calculado > 0.0 else default_valor,
                    min_value=0.01, 
                    format="%.2f",
                    disabled=(valor_calculado > 0.0), 
                    key="input_valor_entrada"
                )
                valor_final_movimentacao = valor_calculado if valor_calculado > 0.0 else valor_input_manual
            
            with col_entrada_status:
                status_selecionado = st.radio(
                    "Status", 
                    ["Realizada", "Pendente"], 
                    index=0 if default_status == "Realizada" else 1, 
                    key="input_status_global_entrada",
                    disabled=edit_mode
                )

        # --- Seção de Saída (Despesa) ---
        elif tipo == "Saída":
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
                if is_recorrente and not edit_mode:
                    st.markdown("##### 🧾 Detalhes da Recorrência")
                    
                    nome_despesa_recorrente = st.text_input("Nome da Despesa Recorrente (Ex: Aluguel)", 
                                                            value=default_cliente if default_cliente else "", 
                                                            key="input_nome_despesa_recorrente")
                    col_rec1, col_rec2 = st.columns(2)
                    with col_rec1:
                        num_parcelas = st.number_input("Quantidade de Parcelas", min_value=1, value=12, step=1, key="input_num_parcelas")
                    with col_rec2:
                        valor_parcela = st.number_input("Valor de Cada Parcela (R$)", min_value=0.01, format="%.2f", value=default_valor, key="input_valor_parcela")
                    data_primeira_parcela = st.date_input("Data de Vencimento da 1ª Parcela", value=date.today().replace(day=1) + timedelta(days=32), key="input_data_primeira_parcela")
                    valor_final_movimentacao = float(valor_parcela)
                    status_selecionado = "Pendente" 
                    st.caption(f"Status forçado para **Pendente**. Serão geradas {int(num_parcelas)} parcelas de R$ {valor_final_movimentacao:,.2f}.")
                    
                else:
                    status_selecionado = st.radio(
                        "Status", 
                        ["Realizada", "Pendente"], 
                        index=0 if default_status == "Realizada" else 1, 
                        key="input_status_global_saida",
                        disabled=edit_mode
                    )
                    valor_input_manual = st.number_input(
                        "Valor (R$)", 
                        value=default_valor, 
                        min_value=0.01, 
                        format="%.2f", 
                        key="input_valor_saida"
                    )
                    valor_final_movimentacao = valor_input_manual
                    cliente = st.text_input("Nome do Cliente (ou Descrição)", 
                                        value=default_cliente, 
                                        key="input_cliente_form_saida",
                                        disabled=edit_mode)


        # --- NOVO: Seção de Empréstimo ---
        elif tipo == "Empréstimo":
            st.markdown("---")
            col_emp_1, col_emp_2 = st.columns(2)
            
            is_emprestimo = True
            
            with col_emp_1:
                st.markdown("#### 💸 Detalhes do Empréstimo Recebido")
                
                status_selecionado = "Pendente" # Dívida (futura saída)
                st.text_input("Status da Dívida (Saída Futura)", "Pendente", disabled=True)

                valor_input_manual = st.number_input(
                    "Valor do Empréstimo Recebido (R$)", 
                    value=default_valor, 
                    min_value=0.01, 
                    format="%.2f", 
                    key="input_valor_emprestimo"
                )
                valor_final_movimentacao = valor_input_manual
            
            with col_emp_2:
                cliente = st.text_input("Credor (Quem emprestou)", 
                                        value=default_cliente, 
                                        key="input_credor_form",
                                        disabled=edit_mode)
                                        
                forma_pagamento = st.selectbox("Forma de Recebimento", FORMAS_PAGAMENTO, key="input_forma_pagamento_emprestimo")
                
            st.markdown("##### ❓ O dinheiro já foi gasto?")
            emprestimo_gasto_radio = st.radio(
                "Selecione uma opção:", 
                ["Selecione...", "Sim, já foi usado para um gasto (Não altera Saldo Atual)", "Não, é saldo disponível (Adiciona ao Saldo Atual)"],
                index=0,
                key="radio_emprestimo_gasto",
                horizontal=True
            )
            
            if emprestimo_gasto_radio == "Sim, já foi usado para um gasto (Não altera Saldo Atual)":
                emprestimo_ja_gasto = True
                st.warning("⚠️ Serão registradas três linhas: **Dívida (Pendente)**, **Entrada Realizada** e **Saída Realizada (Gasto)**. O Saldo Atual (Geral) NÃO será alterado.")
                
                # Usuário deve selecionar a categoria REAL do gasto
                categoria_gasto_emprestimo = st.selectbox(
                    "Qual a **Categoria REAL** do Gasto Financiado?", 
                    CATEGORIAS_SAIDA, 
                    index=CATEGORIAS_SAIDA.index(default_categoria) if default_categoria in CATEGORIAS_SAIDA else 0,
                    key="input_categoria_gasto_emprestimo"
                )
                if categoria_gasto_emprestimo == "Outro/Diversos":
                    descricao_personalizada_gasto = st.text_input("Especifique o Gasto Financiado", key="input_custom_category_emprestimo")
                    if descricao_personalizada_gasto:
                        categoria_gasto_emprestimo = f"Outro: {descricao_personalizada_gasto}"
                
            elif emprestimo_gasto_radio == "Não, é saldo disponível (Adiciona ao Saldo Atual)":
                emprestimo_ja_gasto = False
                st.success("✅ Serão registradas duas linhas: **Dívida (Pendente)** e **Entrada Realizada** (Valor adicionado ao Saldo Atual).")
                
            else:
                emprestimo_ja_gasto = None
            
            # Força Data Pagamento para a dívida
            data_pagamento_final = st.date_input(
                "Data Prevista de Pagamento da Dívida (Saída Futura)", 
                value=default_data_pagamento if default_data_pagamento else date.today() + timedelta(days=30), 
                key="input_data_pagamento_emprestimo"
            )
            
            # Cliente final para display (Dívida)
            cliente_final = f"Dívida Empréstimo: {cliente}"
            categoria_selecionada = "Empréstimo Recebido - Dívida" # Categoria para a dívida pendente
        # --- FIM: Seção de Empréstimo ---


        data_pagamento_final = None 
        
        # Lógica para Data Prevista (Movimentação Pendente NÃO recorrente e NÃO empréstimo)
        if status_selecionado == "Pendente" and not is_recorrente and not is_emprestimo:
            with st.expander("🗓️ Data Prevista de Pagamento/Recebimento (Opcional)", expanded=False):
                data_prevista_existe = pd.notna(default_data_pagamento) and (default_data_pagamento is not None)
                data_status_opcoes = ["Com Data Prevista", "Sem Data Prevista"]
                data_status_key = "input_data_status_previsto_global" 
                
                default_data_status_index = 0
                if edit_mode and default_status == "Pendente":
                    data_status_previsto_str = "Com Data Prevista" if data_prevista_existe else "Sem Data Prevista"
                    default_data_status_index = data_status_opcoes.index(data_status_previsto_str) if data_status_previsto_str in data_status_opcoes else 0
                elif data_status_key in st.session_state:
                    default_data_status_index = data_status_opcoes.index(st.session_state[data_status_key]) if st.session_state[data_status_key] in data_status_opcoes else 0

                data_status_selecionado_previsto = st.radio(
                    "Essa pendência tem data prevista?",
                    options=data_status_opcoes,
                    index=default_data_status_index,
                    key=data_status_key, 
                    horizontal=True,
                    disabled=edit_mode and default_status == "Pendente" and data_prevista_existe
                )
                
                if data_status_selecionado_previsto == "Com Data Prevista":
                    prev_date_value = default_data_pagamento if data_prevista_existe and edit_mode else date.today() 
                    
                    data_prevista_pendente = st.date_input(
                        "Selecione a Data Prevista", 
                        value=prev_date_value, 
                        key="input_data_pagamento_prevista_global"
                    )
                    data_pagamento_final = data_prevista_pendente
                else:
                    data_pagamento_final = None
        
        # Lógica para Data Prevista (Movimentação Pendente Recorrente)
        elif status_selecionado == "Pendente" and is_recorrente:
            data_pagamento_final = data_primeira_parcela
            st.markdown(f"##### 🗓️ 1ª Parcela Vence em: **{data_pagamento_final.strftime('%d/%m/%Y')}**")


        # --- FORMULÁRIO DE DADOS GERAIS E BOTÃO SALVAR ---
        st.markdown("---")
        with st.form("form_movimentacao", clear_on_submit=not edit_mode):
            st.markdown("#### Dados Finais da Transação")
            
            col_f1, col_f2, col_f3 = st.columns(3)

            with col_f1:
                loja_selecionada = st.selectbox("Loja Responsável", 
                                                    LOJAS_DISPONIVEIS, 
                                                    index=LOJAS_DISPONIVEIS.index(default_loja) if default_loja in LOJAS_DISPONIVEIS else 0,
                                                    key="input_loja_form",
                                                    disabled=(is_recorrente or is_emprestimo) and not edit_mode)
                                                    
                data_input = st.date_input("Data da Transação (Lançamento)", value=default_data, key="input_data_form", disabled=(is_recorrente or is_emprestimo) and not edit_mode)
            
            with col_f2:
                # O campo Cliente aqui é uma duplicata, pois o input_cliente_form já está sendo usado. 
                if tipo == "Entrada" and not edit_mode:
                    cliente_final = cliente
                elif tipo == "Saída" and is_recorrente and not edit_mode:
                    cliente_final = nome_despesa_recorrente
                elif tipo == "Saída" and not edit_mode:
                    cliente_final = cliente
                elif is_emprestimo and not edit_mode: # NOVO: Caso Empréstimo
                    # Já definido em `elif tipo == "Empréstimo":` como cliente_final = f"Dívida Empréstimo: {cliente}"
                    pass 
                else: # Modo Edição ou Saída não recorrente
                    cliente_final = default_cliente
                
                st.text_input("Cliente/Descrição (Final)", 
                                        value=cliente_final, 
                                        key="input_cliente_form_display",
                                        disabled=True)
                
                if status_selecionado == "Realizada" and not is_emprestimo:
                    data_pagamento_final = data_input
                    
                    forma_pagamento = st.selectbox("Forma de Pagamento", 
                                                        FORMAS_PAGAMENTO, 
                                                        index=FORMAS_PAGAMENTO.index(default_forma) if default_forma in FORMAS_PAGAMENTO else 0,
                                                        key="input_forma_pagamento_form")
                elif is_emprestimo: # NOVO: Forma de pagamento é a do empréstimo recebido (definida acima)
                    st.text_input("Forma de Pagamento", value=forma_pagamento, disabled=True)
                else:
                    forma_pagamento = "Pendente" 
                    st.text_input("Forma de Pagamento", value="Pendente", disabled=True)
            
            with col_f3:
                st.markdown(f"**Valor Final:** R$ {valor_final_movimentacao:,.2f}")
                st.markdown(f"**Status:** **{status_selecionado}**")
                st.markdown(f"**Data Pagamento:** {data_pagamento_final.strftime('%d/%m/%Y') if data_pagamento_final else 'N/A'}")

            # Botões de Envio
            if edit_mode:
                col_save, col_cancel = st.columns(2)
                with col_save:
                    enviar = st.form_submit_button("💾 Salvar", type="primary", use_container_width=True, help="Salvar Edição")
                with col_cancel:
                    cancelar = st.form_submit_button("❌ Cancelar", type="secondary", use_container_width=True, help="Cancelar Edição")
            else:
                label_btn = "Adicionar Recorrência e Salvar" if is_recorrente else ("Registrar Empréstimo" if is_emprestimo else "Adicionar e Salvar")
                enviar = st.form_submit_button(label_btn, type="primary", use_container_width=True, help=label_btn)
                cancelar = False 

            if enviar:
                # [Lógica de validação e salvamento do código original, movida aqui]
                if valor_final_movimentacao <= 0 and not is_recorrente and not is_emprestimo:
                    st.error("O valor deve ser maior que R$ 0,00.")
                elif valor_parcela <= 0 and is_recorrente:
                    st.error("O valor da parcela deve ser maior que R$ 0,00.")
                elif is_emprestimo and emprestimo_ja_gasto is None and not edit_mode: # NOVO: Validação Empréstimo
                    st.error("Para registrar um empréstimo, você deve selecionar se o valor já foi gasto ou se é saldo disponível.")
                elif tipo == "Saída" and not is_recorrente and categoria_selecionada == "Outro/Diversos": 
                    st.error("Por favor, especifique o 'Outro/Diversos' para Saída.")
                elif is_recorrente and not edit_mode and not nome_despesa_recorrente:
                    st.error("O nome da Despesa Recorrente é obrigatório.")
                else:
                    valor_armazenado = valor_final_movimentacao if tipo == "Entrada" else -valor_final_movimentacao
                    
                    # Lógica de ajuste de estoque (reversão e débito)
                    if edit_mode:
                        original_row = df_dividas.loc[st.session_state.edit_id]
                        
                        # 1. Reversão de estoque se o status da Entrada mudar para Pendente
                        if original_row["Status"] == "Realizada" and status_selecionado == "Pendente" and original_row["Tipo"] == "Entrada":
                            try:
                                produtos_vendidos_antigos = ast.literal_eval(original_row['Produtos Vendidos'])
                                for item in produtos_vendidos_antigos:
                                    if item.get("Produto_ID"): ajustar_estoque(item["Produto_ID"], item["Quantidade"], "creditar")
                            except: pass
                            
                        # 2. Reversão e novo débito se for uma edição de Entrada Realizada
                        elif original_row["Status"] == "Realizada" and status_selecionado == "Realizada" and original_row["Tipo"] == "Entrada":
                            try:
                                # Reverte o estoque da venda original
                                produtos_vendidos_antigos = ast.literal_eval(original_row['Produtos Vendidos'])
                                for item in produtos_vendidos_antigos:
                                    if item.get("Produto_ID"): ajustar_estoque(item["Produto_ID"], item["Quantidade"], "creditar")
                            except: pass
                            
                            # Aplica o débito do novo estado (st.session_state.lista_produtos)
                            if produtos_vendidos_json:
                                produtos_vendidos_novos = json.loads(produtos_vendidos_json)
                                for item in produtos_vendidos_novos:
                                    if item.get("Produto_ID"): ajustar_estoque(item["Produto_ID"], item["Quantidade"], "debitar")
                            
                            if salvar_produtos_no_github(st.session_state.produtos, "Ajuste de estoque por edição de venda"):
                                inicializar_produtos.clear()
                                st.cache_data.clear()
                        
                        # 3. Débito se for uma conclusão de Entrada Pendente
                        elif original_row["Status"] == "Pendente" and status_selecionado == "Realizada" and original_row["Tipo"] == "Entrada":
                            if produtos_vendidos_json:
                                produtos_vendidos_novos = json.loads(produtos_vendidos_json)
                                for item in produtos_vendidos_novos:
                                    if item.get("Produto_ID"): ajustar_estoque(item["Produto_ID"], item["Quantidade"], "debitar")
                            if salvar_produtos_no_github(st.session_state.produtos, "Débito de estoque por conclusão de venda"):
                                inicializar_produtos.clear()
                                st.cache_data.clear()
                                
                        # 4. Novo Débito se for uma nova Entrada Realizada
                    elif not edit_mode and tipo == "Entrada" and status_selecionado == "Realizada" and st.session_state.lista_produtos:
                        if produtos_vendidos_json:
                            produtos_vendidos_novos = json.loads(produtos_vendidos_json)
                            for item in produtos_vendidos_novos:
                                if item.get("Produto_ID"): ajustar_estoque(item["Produto_ID"], item["Quantidade"], "debitar")
                        if salvar_produtos_no_github(st.session_state.produtos, "Débito de estoque por nova venda"):
                            inicializar_produtos.clear()
                            st.cache_data.clear()


                    novas_movimentacoes = []
                    if is_recorrente and not edit_mode:
                        # [Bloco de geração de recorrência]
                        num_parcelas_int = int(num_parcelas)
                        valor_parcela_float = float(valor_parcela)
                        recorrencia_seed = f"{nome_despesa_recorrente}{data_primeira_parcela}{num_parcelas_int}{valor_parcela_float}{categoria_selecionada}{loja_selecionada}"
                        recorrencia_id = hashlib.md5(recorrencia_seed.encode('utf-8')).hexdigest()[:10]
                        
                        for i in range(1, num_parcelas_int + 1):
                            data_vencimento_parcela = add_months(data_primeira_parcela, i - 1)
                            nova_linha_parcela = {
                                "Data": data_input, 
                                "Loja": loja_selecionada, 
                                "Cliente": f"{nome_despesa_recorrente} (Parc. {i}/{num_parcelas_int})",
                                "Valor": -valor_parcela_float,
                                "Forma de Pagamento": "Pendente", 
                                "Tipo": "Saída",
                                "Produtos Vendidos": "",
                                "Categoria": categoria_selecionada,
                                "Status": "Pendente",
                                "Data Pagamento": data_vencimento_parcela, 
                                "RecorrenciaID": recorrencia_id,
                                "TransacaoPaiID": "" 
                            }
                            novas_movimentacoes.append(nova_linha_parcela)
                        
                        st.session_state.df = pd.concat([df_dividas, pd.DataFrame(novas_movimentacoes)], ignore_index=True)
                        commit_msg = f"Cadastro de Dívida Recorrente ({num_parcelas_int} parcelas)"
                        
                    # NOVO: Lógica de Empréstimo Recebido
                    elif is_emprestimo and not edit_mode and emprestimo_ja_gasto is not None:
                        
                        novas_movimentacoes = []
                        
                        # 1. Registro da Dívida (Saída Futura - Pendente)
                        # Este é o registro da dívida que precisa ser paga, sempre Saída Pendente
                        nova_linha_divida = {
                            "Data": data_input, 
                            "Loja": loja_selecionada, 
                            "Cliente": f"Pagamento Empréstimo: {cliente}",
                            "Valor": -valor_final_movimentacao, # Saída (Dívida)
                            "Forma de Pagamento": "Pendente", 
                            "Tipo": "Saída",
                            "Produtos Vendidos": "",
                            "Categoria": "Empréstimo Recebido - Dívida", 
                            "Status": "Pendente",
                            "Data Pagamento": data_pagamento_final, # Data prevista de pagamento
                            "RecorrenciaID": "",
                            "TransacaoPaiID": "" 
                        }
                        novas_movimentacoes.append(nova_linha_divida)

                        commit_msg = f"Registro de Empréstimo Recebido de R$ {valor_final_movimentacao:,.2f}."

                        if emprestimo_ja_gasto:
                            # 2. Saída Realizada (Gasto)
                            nova_linha_gasto = {
                                "Data": data_input, 
                                "Loja": loja_selecionada, 
                                "Cliente": f"Gasto Financiado: {cliente}",
                                "Valor": -valor_final_movimentacao, # Saída (Gasto)
                                "Forma de Pagamento": forma_pagamento, 
                                "Tipo": "Saída",
                                "Produtos Vendidos": "",
                                "Categoria": categoria_gasto_emprestimo, # Categoria REAL do gasto
                                "Status": "Realizada",
                                "Data Pagamento": data_input, 
                                "RecorrenciaID": "",
                                "TransacaoPaiID": "" 
                            }
                            novas_movimentacoes.append(nova_linha_gasto)
                            
                            # 3. Entrada Realizada (Entrada de Dinheiro para Cobrir o Gasto)
                            nova_linha_entrada = {
                                "Data": data_input, 
                                "Loja": loja_selecionada, 
                                "Cliente": f"Entrada Financiada: {cliente}",
                                "Valor": valor_final_movimentacao, # Entrada (Dinheiro no Caixa)
                                "Forma de Pagamento": forma_pagamento, 
                                "Tipo": "Entrada",
                                "Produtos Vendidos": "",
                                "Categoria": "Empréstimo Recebido - Entrada",
                                "Status": "Realizada",
                                "Data Pagamento": data_input, 
                                "RecorrenciaID": "",
                                "TransacaoPaiID": "" 
                            }
                            novas_movimentacoes.append(nova_linha_entrada)
                            commit_msg += " (Gasto imediato do valor registrado, Saldo Geral neutro)."
                            
                        else: 
                            # 2. Entrada Realizada (Saldo Disponível)
                            nova_linha_entrada_saldo = {
                                "Data": data_input, 
                                "Loja": loja_selecionada, 
                                "Cliente": f"Entrada Empréstimo (Saldo): {cliente}",
                                "Valor": valor_final_movimentacao, # Entrada (Dinheiro no Saldo)
                                "Forma de Pagamento": forma_pagamento, 
                                "Tipo": "Entrada",
                                "Produtos Vendidos": "",
                                "Categoria": "Empréstimo Recebido - Saldo",
                                "Status": "Realizada",
                                "Data Pagamento": data_input, 
                                "RecorrenciaID": "",
                            "TransacaoPaiID": "" 
                            }
                            novas_movimentacoes.append(nova_linha_entrada_saldo)
                            commit_msg += " (Valor adicionado ao Saldo Atual)."
                        
                        st.session_state.df = pd.concat([df_dividas, pd.DataFrame(novas_movimentacoes)], ignore_index=True)
                        
                    else:
                        # [Bloco de adição/edição de item único]
                        nova_linha_data = {
                            "Data": data_input,
                            "Loja": loja_selecionada, 
                            "Cliente": cliente_final,
                            "Valor": valor_armazenado, 
                            "Forma de Pagamento": forma_pagamento,
                            "Tipo": tipo,
                            "Produtos Vendidos": produtos_vendidos_json,
                            "Categoria": categoria_selecionada,
                            "Status": status_selecionado, 
                            "Data Pagamento": data_pagamento_final,
                            "RecorrenciaID": "",
                            "TransacaoPaiID": "" 
                        }
                        
                        if edit_mode:
                            st.session_state.df.loc[st.session_state.edit_id] = pd.Series(nova_linha_data)
                            commit_msg = COMMIT_MESSAGE_EDIT
                        else:
                            st.session_state.df = pd.concat([df_dividas, pd.DataFrame([nova_linha_data])], ignore_index=True)
                            commit_msg = COMMIT_MESSAGE # Usa o COMMIT_MESSAGE definido (ou padrão)
                    
                    salvar_dados_no_github(st.session_state.df, commit_msg)
                    st.session_state.edit_id = None
                    st.session_state.edit_id_loaded = None 
                    st.session_state.lista_produtos = [] 
                    st.session_state.divida_a_quitar = None # Limpa a chave de quitação
                    st.cache_data.clear()
                    st.rerun()


            if cancelar:
                st.session_state.edit_id = None
                st.session_state.edit_id_loaded = None 
                st.session_state.lista_produtos = []
                st.rerun()
                
    # ==============================================================================================
    # ABA: MOVIMENTAÇÕES E RESUMO (Código Original)
    # ==============================================================================================
    with tab_mov:
        
        hoje = date.today()
        primeiro_dia_mes = hoje.replace(day=1)
        if hoje.month == 12: proximo_mes = hoje.replace(year=hoje.year + 1, month=1, day=1)
        else: proximo_mes = hoje.replace(month=hoje.month + 1, day=1)
        ultimo_dia_mes = proximo_mes - timedelta(days=1)

        df_mes_atual_realizado = df_exibicao[
            (df_exibicao["Data"] >= primeiro_dia_mes) &
            (df_exibicao["Data"] <= ultimo_dia_mes) &
            (df_exibicao["Status"] == "Realizada")
        ]
        
        st.subheader(f"📊 Resumo Financeiro Geral")

        total_entradas_mes, total_saidas_mes, saldo_mes = calcular_resumo(df_mes_atual_realizado)

        df_geral_realizado = df_exibicao[df_exibicao['Status'] == 'Realizada']
        _, _, saldo_geral_total = calcular_resumo(df_geral_realizado)
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric(f"Entradas (Mês: {primeiro_dia_mes.strftime('%b')})", f"R$ {total_entradas_mes:,.2f}")
        col2.metric(f"Saídas (Mês: {primeiro_dia_mes.strftime('%b')})", f"R$ {total_saidas_mes:,.2f}")
        delta_saldo_mes = f"R$ {saldo_mes:,.2f}"
        col3.metric("Saldo do Mês (Realizado)", f"R$ {saldo_mes:,.2f}", delta=delta_saldo_mes if saldo_mes != 0 else None, delta_color="normal")
        col4.metric("Saldo Atual (Geral)", f"R$ {saldo_geral_total:,.2f}")

        st.markdown("---")
        
        # [Bloco de Alerta de Dívidas Pendentes Vencidas]
        hoje_date = date.today()
        df_pendente_alerta = df_exibicao[
            (df_exibicao["Status"] == "Pendente") & 
            (pd.notna(df_exibicao["Data Pagamento"]))
        ].copy()

        df_pendente_alerta["Data Pagamento"] = pd.to_datetime(df_pendente_alerta["Data Pagamento"], errors='coerce').dt.date
        df_pendente_alerta.dropna(subset=["Data Pagamento"], inplace=True)
        
        df_vencidas = df_pendente_alerta[
            df_pendente_alerta["Data Pagamento"] <= hoje_date
        ]

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
        
        # O Nome da variável 'first_day_of_month' está incorreta no seu código (usando a var. 'primeiro_dia_mes' em cima)
        st.subheader(f"🏠 Resumo Rápido por Loja (Mês de {primeiro_dia_mes.strftime('%m/%Y')} - Realizado)")
        
        # [Bloco de Resumo por Loja]
        df_resumo_loja = df_mes_atual_realizado.groupby('Loja')['Valor'].agg(['sum', lambda x: x[x >= 0].sum(), lambda x: abs(x[x < 0].sum())]).reset_index()
        df_resumo_loja.columns = ['Loja', 'Saldo', 'Entradas', 'Saídas']
        
        if not df_resumo_loja.empty:
            cols_loja = st.columns(min(4, len(df_resumo_loja.index))) 
            
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
        
        # [Bloco de Filtros e Tabela de Movimentações]
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
                # CORRIGIDO: Tipos únicos agora incluem Empréstimo, mas o filtro deve usar o Tipo da transação (Entrada/Saída)
                tipos_unicos = ["Todos", "Entrada", "Saída"] # O tipo "Empréstimo" não existe no DF final
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
                selection_mode='disabled',
                key='movimentacoes_table_styled_display_only'
            )


            st.markdown("---")
            st.markdown("### Operações de Edição e Exclusão")
            
            # [Bloco de Edição e Exclusão]
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
                            # [Bloco de exibição de detalhes dos produtos]
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

    # ==============================================================================================
    # ABA: RELATÓRIOS E FILTROS (Código Original)
    # ==============================================================================================
    with tab_rel:
        
        st.subheader("📄 Relatório Detalhado e Comparativo")
        
        # [Conteúdo original da aba tab_rel]
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

                    # fig_comp e fig_cresc requerem 'import plotly.express as px' (presumido)
                    # O código original não importou 'plotly.express', o que causaria um erro. Mantendo o código sem a importação para evitar um erro diferente, mas observe que ele não rodará.
                    # fig_comp = px.bar(df_agrupado, x='MesAno', y=['Entradas', 'Saídas'], title="Comparativo de Entradas vs. Saídas por Mês",
                    #      labels={'value': 'Valor (R$)', 'variable': 'Tipo', 'MesAno': 'Mês/Ano'}, barmode='group', color_discrete_map={'Entradas': 'green', 'Saídas': 'red'})
                    # st.plotly_chart(fig_comp, use_container_width=True)

                    # fig_cresc = px.line(df_agrupado, x='MesAno', y=['Crescimento Entradas (%)', 'Crescimento Saídas (%)'],
                    #      title="Crescimento Percentual Mensal (Entradas e Saídas)",
                    #      labels={'value': '% de Crescimento', 'variable': 'Métrica', 'MesAno': 'Mês/Ano'}, markers=True)
                    # st.plotly_chart(fig_cresc, use_container_width=True)

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

            # NOVO: Início do Formulário de Pagamento Parcial/Total
            with st.form("form_concluir_divida"):
                st.markdown("##### ✅ Concluir Dívida Pendente (Pagamento Parcial ou Total)")
                
                # NOVO: Usa divida_parcial_id se vier da aba Nova Movimentação
                default_concluir_idx = 0
                divida_para_concluir = None
                
                opcoes_pendentes_map = {
                    f"ID {row['ID Visível']} | {row['Tipo']} | R$ {calcular_valor_em_aberto(row):,.2f} | Venc.: {row['Data Pagamento'].strftime('%d/%m/%Y') if pd.notna(row['Data Pagamento']) else 'S/ Data'} | {row['Cliente']}": row['original_index']
                    for index, row in df_pendentes_ordenado.iterrows()
                }
                opcoes_keys = ["Selecione uma dívida..."] + list(opcoes_pendentes_map.keys())

                if 'divida_parcial_id' in st.session_state and st.session_state.divida_parcial_id is not None:
                    # Encontra a chave da dívida selecionada
                    original_idx_para_selecionar = st.session_state.divida_parcial_id
                    try:
                        divida_row = df_pendentes_ordenado[df_pendentes_ordenado['original_index'] == original_idx_para_selecionar].iloc[0]
                        valor_row_formatado = calcular_valor_em_aberto(divida_row)
                        option_key = f"ID {divida_row['ID Visível']} | {divida_row['Tipo']} | R$ {valor_row_formatado:,.2f} | Venc.: {divida_row['Data Pagamento'].strftime('%d/%m/%Y') if pd.notna(divida_row['Data Pagamento']) else 'S/ Data'} | {divida_row['Cliente']}"
                        
                        opcoes_pendentes = {
                            f"ID {row['ID Visível']} | {row['Tipo']} | R$ {calcular_valor_em_aberto(row):,.2f} | Venc.: {row['Data Pagamento'].strftime('%d/%m/%Y') if pd.notna(row['Data Pagamento']) else 'S/ Data'} | {row['Cliente']}": row['original_index']
                            for index, row in df_pendentes_ordenado.iterrows()
                        }
                        
                        opcoes_keys = ["Selecione uma dívida..."] + list(opcoes_pendentes_map.keys())
                        
                        if option_key in opcoes_keys:
                            default_concluir_idx = opcoes_keys.index(option_key)
                        
                        # Carrega os dados da dívida para exibição
                        divida_para_concluir = divida_row
                    except Exception:
                        pass # Continua com o índice 0 (Selecione)
                    
                    # Limpa a chave após a seleção
                    st.session_state.divida_parcial_id = None
                
                
                divida_selecionada_str = st.selectbox(
                    "Selecione a Dívida para Concluir:", 
                    options=opcoes_keys, 
                    index=default_concluir_idx,
                    key="select_divida_concluir"
                )
                
                original_idx_concluir = opcoes_pendentes_map.get(divida_selecionada_str)
                
                if original_idx_concluir is not None and divida_para_concluir is None:
                    # Carrega os dados da dívida se o usuário selecionar manualmente
                    divida_para_concluir = df_pendentes_ordenado[df_pendentes_ordenado['original_index'] == original_idx_concluir].iloc[0]


                if divida_para_concluir is not None:
                    # >> USO DA NOVA FUNÇÃO PARA GARANTIR VALOR CORRETO E ARREDONDADO <<<
                    valor_em_aberto = calcular_valor_em_aberto(divida_para_concluir)
                    # << FIM DO USO DA NOVA FUNÇÃO >>>

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

                    # CORREÇÃO: Adicionado o st.form_submit_button para evitar o erro "Missing Submit Button"
                    concluir = st.form_submit_button("✅ Registrar Pagamento", use_container_width=True, type="primary")

                    if concluir:
                        valor_restante = round(valor_em_aberto - valor_pago, 2)
                        idx_original = original_idx_concluir
                        
                        if idx_original not in st.session_state.df.index:
                            st.error("Erro interno ao localizar dívida. O registro original foi perdido.")
                            st.rerun()
                            return

                        row_original = st.session_state.df.loc[idx_original].copy()
                        
                        # 1. Cria a transação de pagamento (Realizada)
                        # O valor deve ter o sinal correto (Entrada é positivo, Saída é negativo)
                        valor_pagamento_com_sinal = valor_pago if row_original['Tipo'] == 'Entrada' else -valor_pago
                        
                        nova_transacao_pagamento = {
                            "Data": data_conclusao,
                            "Loja": row_original['Loja'],
                            "Cliente": f"{row_original['Cliente'].split(' (')[0]} (Pagto de R$ {valor_pago:,.2f})",
                            "Valor": valor_pagamento_com_sinal, 
                            "Forma de Pagamento": forma_pagt_concluir,
                            "Tipo": row_original['Tipo'],
                            "Produtos Vendidos": row_original['Produtos Vendidos'], # Mantém os produtos para rastreio
                            "Categoria": row_original['Categoria'],
                            "Status": "Realizada",
                            "Data Pagamento": data_conclusao,
                            "RecorrenciaID": row_original['RecorrenciaID'],
                            "TransacaoPaiID": idx_original # Rastreia o ID original (índice Pandas)
                        }
                        
                        # Adiciona o pagamento realizado
                        st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([nova_transacao_pagamento])], ignore_index=True)
                        
                        # 2. Atualiza a dívida original
                        if valor_restante > 0.01: # Pagamento parcial: atualiza a dívida original
                            
                            # Atualiza o valor restante (o sinal já foi definido no processamento)
                            novo_valor_restante_com_sinal = valor_restante if row_original['Tipo'] == 'Entrada' else -valor_restante

                            st.session_state.df.loc[idx_original, 'Valor'] = novo_valor_restante_com_sinal
                            st.session_state.df.loc[idx_original, 'Cliente'] = f"{row_original['Cliente'].split(' (')[0]} (EM ABERTO: R$ {valor_restante:,.2f})"
                            
                            commit_msg = f"Pagamento parcial de R$ {valor_pago:,.2f} da dívida {row_original['Cliente']}. Resta R$ {valor_restante:,.2f}."
                            
                        else: # Pagamento total (valor restante <= 0.01)
                            
                            # Exclui a linha original pendente (pois o pagamento total já foi registrado como nova transação)
                            st.session_state.df = st.session_state.df.drop(idx_original, errors='ignore')
                            
                            # Débito de Estoque (Apenas para Entrada)
                            # O débito de estoque só deve ocorrer se a transação original for a venda (Tipo Entrada)
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
                    # --- CORREÇÃO DE SINTAXE (INDENTAÇÃO) ---
                    st.info("Selecione uma dívida válida para prosseguir com o pagamento.")


            st.markdown("---")

            st.markdown("##### Tabela Detalhada de Dívidas Pendentes")
            df_para_mostrar_pendentes = df_pendentes_ordenado.copy()
            df_para_mostrar_pendentes['Status Vencimento'] = df_para_mostrar_pendentes['Dias Até/Atraso'].apply(
                lambda x: f"Atrasado {-x} dias" if x < 0 else (f"Vence em {x} dias" if x > 0 else "Vence Hoje")
            )
            df_styling_pendentes = df_para_mostrar_pendentes.style.apply(highlight_pendentes, axis=1)
            
            # --- SINTAXE CORRIGIDA PARA VERSÕES ANTIGAS DO PANDAS ---
            # A versão correta para o seu ambiente usa 'subset' e 'axis=1'.
            df_styling_pendentes = df_styling_pendentes.hide(subset=['Dias Até/Atraso'], axis=1)

            st.dataframe(df_styling_pendentes, use_container_width=True, hide_index=True)


