import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import json
import ast
import hashlib
import plotly.express as px

from utils import (
    inicializar_produtos,
    carregar_livro_caixa,
    ajustar_estoque,
    to_float,
    salvar_produtos_no_github,
    parse_date_yyyy_mm_dd,
    prox_id,
    norm_promocoes,
    carregar_promocoes,
    salvar_promocoes_no_github,
)
from constants_and_css import FATOR_CARTAO


def gestao_promocoes():
    """Página de gerenciamento de promoções."""

    st.header("🏷️ Promoções")

    # Inicializa ou carrega produtos e promoções
    produtos = inicializar_produtos()
    if "promocoes" not in st.session_state:
        st.session_state.promocoes = carregar_promocoes()
    promocoes_df = st.session_state.promocoes
    
    # ATENÇÃO: norm_promocoes é crucial. Assumindo que ela lida com 'ID_PROMOCAO', 'DATA_INICIO', etc.
    # O df 'promocoes' é o df filtrado e normalizado.
    promocoes = norm_promocoes(promocoes_df.copy()) 

    # Carrega o livro caixa para análise de produtos parados
    df_movimentacoes = carregar_livro_caixa()
    vendas = df_movimentacoes[df_movimentacoes["Tipo"] == "Entrada"].copy()

    vendas_list = []
    for _, row in vendas.iterrows():
        produtos_json = row.get("Produtos Vendidos")
        if pd.notna(produtos_json) and produtos_json:
            try:
                try:
                    items = json.loads(produtos_json)
                except (json.JSONDecodeError, TypeError):
                    items = ast.literal_eval(produtos_json)
                if isinstance(items, list):
                    for item in items:
                        produto_id = str(item.get("Produto_ID"))
                        if produto_id and produto_id != "None":
                            vendas_list.append(
                                {"Data": parse_date_yyyy_mm_dd(row["Data"]), "IDProduto": produto_id}
                            )
            except Exception:
                continue

    vendas_flat = pd.DataFrame(vendas_list, columns=["Data", "IDProduto"]) if vendas_list else pd.DataFrame(columns=["Data", "IDProduto"])

    # --- CADASTRAR ---
    with st.expander("➕ Cadastrar promoção", expanded=False):
        if produtos.empty:
            st.info("Cadastre produtos primeiro para criar promoções.")
        else:
            opcoes_prod = (produtos["ID"].astype(str) + " - " + produtos["Nome"]).tolist()
            opcoes_prod.insert(0, "")
            sel_prod = st.selectbox("Produto", opcoes_prod, key="promo_cad_produto")

            if sel_prod:
                # 1. Obter ID do Produto e Preço Original
                pid = sel_prod.split(" - ")[0].strip()
                pnome = sel_prod.split(" - ", 1)[1].strip()
                
                # Encontra a linha do produto no catálogo
                produto_selecionado = produtos[produtos['ID'].astype(str) == pid]
                
                if produto_selecionado.empty:
                     st.error("Produto não encontrado no catálogo.")
                     return
                
                produto_selecionado = produto_selecionado.iloc[0]
                
                # Preço Original (Assumindo que PRECOVISTA é o preço base no DF de produtos)
                preco_original = to_float(produto_selecionado.get('PRECOVISTA', 0.0)) 
                
                st.info(f"Preço de Venda Base: R$ {preco_original:.2f}")

                col1, col2, col3 = st.columns(3)
                with col1:
                    desconto_str = st.text_input("Desconto (%)", value="0", key="promo_cad_desc")
                with col2:
                    data_ini = st.date_input("Início", value=date.today(), key="promo_cad_inicio")
                with col3:
                    data_fim = st.date_input("Término", value=date.today() + timedelta(days=7), key="promo_cad_fim")
                
                desconto_float = to_float(desconto_str)
                preco_promocional = preco_original * (1 - (desconto_float / 100))
                
                st.markdown(f"**Preço Promocional Calculado:** R$ {preco_promocional:.2f}")


                if st.button("Adicionar promoção", key="promo_btn_add"):
                    desconto = to_float(desconto_str)
                    if desconto < 0 or desconto > 100:
                        st.error("O desconto deve estar entre 0 e 100%.")
                    elif data_fim < data_ini:
                        st.error("A data de término deve ser maior ou igual à data de início.")
                    elif preco_original <= 0:
                        st.error("O preço original do produto deve ser maior que zero para aplicar a promoção.")
                    else:
                        # 2. Montar o dicionário com o NOVO CABEÇALHO
                        novo = {
                            "ID_PROMOCAO": prox_id(promocoes_df, "ID_PROMOCAO"), 
                            "ID_PRODUTO": str(pid),                          
                            "NOME_PRODUTO": pnome,                           
                            "PRECO_ORIGINAL": float(preco_original),         
                            "PRECO_PROMOCIONAL": float(preco_promocional),   
                            "STATUS": "ATIVO",                               
                            "DATA_INICIO": str(data_ini),                    
                            "DATA_FIM": str(data_fim),                       
                        }
                        
                        df_atualizado = pd.concat([promocoes_df, pd.DataFrame([novo])], ignore_index=True)
                        st.session_state.promocoes = df_atualizado
                        try:
                            salvar_promocoes_no_github(df_atualizado)
                            carregar_promocoes.clear()
                            st.success("Promoção cadastrada e salva!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao salvar a promoção: {e}")

    # --- PRODUTOS PARADOS ---
    st.markdown("---")
    st.subheader("💡 Sugestões de Promoção — Produtos Parados")

    dias_sem_venda = st.number_input(
        "Considerar parados após quantos dias?",
        min_value=1, max_value=365, value=30, key="promo_dias_sem_venda",
    )

    if not vendas_flat.empty:
        vendas_flat["Data"] = pd.to_datetime(vendas_flat["Data"], errors="coerce")
        ultima_venda = vendas_flat.groupby("IDProduto")["Data"].max().reset_index()
        ultima_venda.columns = ["IDProduto", "UltimaVenda"]
    else:
        ultima_venda = pd.DataFrame(columns=["IDProduto", "UltimaVenda"])

    produtos_parados = produtos.merge(ultima_venda, left_on="ID", right_on="IDProduto", how="left")
    produtos_parados["UltimaVenda"] = pd.to_datetime(produtos_parados["UltimaVenda"], errors="coerce")
    limite_dt = datetime.combine(date.today() - timedelta(days=int(dias_sem_venda)), datetime.min.time())
    produtos_parados_sugeridos = produtos_parados[
        (produtos_parados["Quantidade"] > 0)
        & (produtos_parados["UltimaVenda"].isna() | (produtos_parados["UltimaVenda"] < limite_dt))
    ].copy()
    produtos_parados_sugeridos["UltimaVenda"] = produtos_parados_sugeridos["UltimaVenda"].dt.date.fillna(pd.NaT)

    if produtos_parados_sugeridos.empty:
        st.info("Nenhum produto parado encontrado com estoque e fora de promoção.")
    else:
        st.dataframe(
            produtos_parados_sugeridos[["ID", "Nome", "Quantidade", "UltimaVenda"]].fillna({"UltimaVenda": "NUNCA VENDIDO"}),
            use_container_width=True, hide_index=True,
        )
        with st.expander("⚙️ Criar Promoção Automática para Parados"):
            desconto_auto = st.number_input("Desconto sugerido (%)", min_value=1, max_value=100, value=20)
            dias_validade = st.number_input("Duração da promoção (dias)", min_value=1, max_value=90, value=7)
            
            if st.button("🔥 Criar promoção automática", key="promo_btn_auto"):
                df_atualizado = st.session_state.promocoes.copy()
                
                for _, row in produtos_parados_sugeridos.iterrows():
                    # Cálculo de preços para o novo cabeçalho
                    preco_original_auto = to_float(row.get('PRECOVISTA', 0.0))
                    preco_promocional_auto = preco_original_auto * (1 - (desconto_auto / 100))
                    
                    novo = {
                        "ID_PROMOCAO": prox_id(df_atualizado, "ID_PROMOCAO"),
                        "ID_PRODUTO": str(row["ID"]),
                        "NOME_PRODUTO": row["Nome"],
                        "PRECO_ORIGINAL": float(preco_original_auto),
                        "PRECO_PROMOCIONAL": float(preco_promocional_auto),
                        "STATUS": "ATIVO",
                        "DATA_INICIO": str(date.today()),
                        "DATA_FIM": str(date.today() + timedelta(days=int(dias_validade))),
                    }
                    df_atualizado = pd.concat([df_atualizado, pd.DataFrame([novo])], ignore_index=True)
                    
                st.session_state.promocoes = df_atualizado
                try:
                    salvar_promocoes_no_github(df_atualizado)
                    carregar_promocoes.clear()
                    st.success(f"Promoções criadas e salvas para {len(produtos_parados_sugeridos)} produtos!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar as promoções automáticas: {e}")

    # --- PROMOÇÕES ATIVAS ---
    st.markdown("---")
    st.subheader("📋 Promoções Ativas")

    if promocoes.empty:
        st.info("Nenhuma promoção ativa cadastrada.")
        return

    # Preparação do DataFrame para Exibição
    df_display = promocoes.copy()
    
    # CÁLCULO DE DESCONTO PARA EXIBIÇÃO:
    if 'PRECO_ORIGINAL' in df_display.columns and 'PRECO_PROMOCIONAL' in df_display.columns:
        # Evita divisão por zero
        df_display['Desconto_Calc'] = (1 - (df_display['PRECO_PROMOCIONAL'] / df_display['PRECO_ORIGINAL'].replace(0, 1e-6))) * 100
        df_display['Desconto'] = df_display['Desconto_Calc'].apply(lambda x: f"{max(0, x):.0f}%")
    else:
        # Fallback se as colunas de preço ainda não existirem
        df_display['Desconto'] = 'N/A'
    
    # Renomeando colunas de data para o formato de exibição:
    df_display["DataInicio"] = df_display["DATA_INICIO"].apply(lambda x: x.strftime("%d/%m/%Y"))
    df_display["DataFim"] = df_display["DATA_FIM"].apply(lambda x: x.strftime("%d/%m/%Y"))
    
    # Exibe as colunas com os novos nomes padronizados no DataFrame de Promoções
    st.dataframe(df_display[["ID_PROMOCAO", "NOME_PRODUTO", "Desconto", "DataInicio", "DataFim", "STATUS"]],
                 use_container_width=True, hide_index=True)

    st.markdown("#### ✏️ Editar ou Excluir Promoção")
    
    opcoes = {f"ID {row['ID_PROMOCAO']} | {row['NOME_PRODUTO']} | {row['Desconto']} | Fim: {row['DataFim']}": row["ID_PROMOCAO"]
              for _, row in df_display.iterrows()}
    opcoes_keys = ["Selecione uma promoção..."] + list(opcoes.keys())
    promo_sel_str = st.selectbox("Selecione:", opcoes_keys, index=0, key="promo_select_edit")
    promo_id_sel = opcoes.get(promo_sel_str)
    
    if not promo_id_sel:
        return

    # Usa ID_PROMOCAO para buscar a linha
    linha_original = promocoes_df[promocoes_df["ID_PROMOCAO"].astype(str) == promo_id_sel].iloc[0]
    
    # 1. Busca o preço original no DF de produtos (necessário para calcular o novo preço promocional)
    pid_original = str(linha_original.get("ID_PRODUTO")) 
    produto_catalogo = produtos[produtos["ID"].astype(str) == pid_original]
    
    # Prioriza o PRECO_ORIGINAL salvo no próprio DF de promoções como fallback
    preco_base_para_calc = float(linha_original.get("PRECO_ORIGINAL", 0.0)) 

    if not produto_catalogo.empty:
        # Prioriza o preço base atualizado do catálogo
        preco_base_para_calc = to_float(produto_catalogo.iloc[0].get('PRECOVISTA', preco_base_para_calc))
        
    st.markdown(f"**Preço Base do Produto:** R$ {preco_base_para_calc:.2f}")
    
    # Calcula o desconto atual para preencher o campo de edição
    desconto_atual = 0
    if preco_base_para_calc > 0 and 'PRECO_PROMOCIONAL' in linha_original:
        desconto_atual = (1 - (to_float(linha_original["PRECO_PROMOCIONAL"]) / preco_base_para_calc)) * 100

    col1, col2, col3 = st.columns(3)
    with col1:
        # Usa o desconto recalculado para preencher o campo de edição
        desc_edit = st.text_input("Desconto (%)", value=f"{desconto_atual:.0f}")
    with col2:
        # Usa DATA_INICIO
        data_ini_edit = parse_date_yyyy_mm_dd(linha_original["DATA_INICIO"]) or date.today()
        data_ini_edit = st.date_input("Início", value=data_ini_edit)
    with col3:
        # Usa DATA_FIM
        data_fim_edit = parse_date_yyyy_mm_dd(linha_original["DATA_FIM"]) or date.today() + timedelta(days=7)
        data_fim_edit = st.date_input("Término", value=data_fim_edit)

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("💾 Salvar Edição"):
            dnum = to_float(desc_edit)
            
            # Cálculo do novo PRECO_PROMOCIONAL
            novo_preco_promocional = preco_base_para_calc * (1 - (dnum / 100))
            
            if dnum < 0 or dnum > 100:
                st.error("O desconto deve estar entre 0 e 100%.")
            elif data_fim_edit < data_ini_edit:
                st.error("A data de término deve ser maior ou igual à de início.")
            else:
                # Usa ID_PROMOCAO
                idx = promocoes_df["ID_PROMOCAO"].astype(str) == promo_id_sel 
                
                # Atualiza as colunas de acordo com o NOVO CABEÇALHO
                promocoes_df.loc[idx, ["PRECO_PROMOCIONAL", "PRECO_ORIGINAL", "DATA_INICIO", "DATA_FIM", "STATUS"]] = [
                    float(novo_preco_promocional),
                    float(preco_base_para_calc), # Garante que o PRECO_ORIGINAL seja o base atualizado
                    str(data_ini_edit),
                    str(data_fim_edit),
                    "ATIVO", # Mantém como ativo após a edição
                ]
                
                st.session_state.promocoes = promocoes_df
                try:
                    salvar_promocoes_no_github(promocoes_df)
                    carregar_promocoes.clear()
                    st.success("Promoção atualizada e salva!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar edição: {e}")

    with col_btn2:
        if st.button("🗑️ Excluir Promoção"):
            # Usa ID_PROMOCAO
            df_atualizado = promocoes_df[promocoes_df["ID_PROMOCAO"].astype(str) != promo_id_sel] 
            st.session_state.promocoes = df_atualizado
            try:
                salvar_promocoes_no_github(df_atualizado)
                carregar_promocoes.clear()
                st.warning("Promoção excluída e salva!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar exclusão: {e}")
