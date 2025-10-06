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
    salvar_promocoes_no_github,  # ✅ função correta
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
                pid = sel_prod.split(" - ")[0].strip()
                pnome = sel_prod.split(" - ", 1)[1].strip()
                col1, col2, col3 = st.columns(3)
                with col1:
                    desconto_str = st.text_input("Desconto (%)", value="0", key="promo_cad_desc")
                with col2:
                    data_ini = st.date_input("Início", value=date.today(), key="promo_cad_inicio")
                with col3:
                    data_fim = st.date_input("Término", value=date.today() + timedelta(days=7), key="promo_cad_fim")

                if st.button("Adicionar promoção", key="promo_btn_add"):
                    desconto = to_float(desconto_str)
                    if desconto < 0 or desconto > 100:
                        st.error("O desconto deve estar entre 0 e 100%.")
                    elif data_fim < data_ini:
                        st.error("A data de término deve ser maior ou igual à data de início.")
                    else:
                        novo = {
                            "ID": prox_id(promocoes_df, "ID"),
                            "IDProduto": str(pid),
                            "NomeProduto": pnome,
                            "Desconto": float(desconto),
                            "DataInicio": str(data_ini),
                            "DataFim": str(data_fim),
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
                    novo = {
                        "ID": prox_id(df_atualizado, "ID"),
                        "IDProduto": str(row["ID"]),
                        "NomeProduto": row["Nome"],
                        "Desconto": float(desconto_auto),
                        "DataInicio": str(date.today()),
                        "DataFim": str(date.today() + timedelta(days=int(dias_validade))),
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

    df_display = promocoes.copy()
    df_display["Desconto"] = df_display["Desconto"].apply(lambda x: f"{x:.0f}%")
    df_display["DataInicio"] = df_display["DataInicio"].apply(lambda x: x.strftime("%d/%m/%Y"))
    df_display["DataFim"] = df_display["DataFim"].apply(lambda x: x.strftime("%d/%m/%Y"))
    st.dataframe(df_display[["ID", "NomeProduto", "Desconto", "DataInicio", "DataFim"]],
                 use_container_width=True, hide_index=True)

    st.markdown("#### ✏️ Editar ou Excluir Promoção")
    opcoes = {f"ID {row['ID']} | {row['NomeProduto']} | {row['Desconto']} | Fim: {row['DataFim']}": row["ID"]
              for _, row in df_display.iterrows()}
    opcoes_keys = ["Selecione uma promoção..."] + list(opcoes.keys())
    promo_sel_str = st.selectbox("Selecione:", opcoes_keys, index=0, key="promo_select_edit")
    promo_id_sel = opcoes.get(promo_sel_str)
    if not promo_id_sel:
        return

    linha_original = promocoes_df[promocoes_df["ID"].astype(str) == promo_id_sel].iloc[0]
    col1, col2, col3 = st.columns(3)
    with col1:
        desc_edit = st.text_input("Desconto (%)", value=str(to_float(linha_original["Desconto"])))
    with col2:
        data_ini_edit = parse_date_yyyy_mm_dd(linha_original["DataInicio"]) or date.today()
        data_ini_edit = st.date_input("Início", value=data_ini_edit)
    with col3:
        data_fim_edit = parse_date_yyyy_mm_dd(linha_original["DataFim"]) or date.today() + timedelta(days=7)
        data_fim_edit = st.date_input("Término", value=data_fim_edit)

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("💾 Salvar Edição"):
            dnum = to_float(desc_edit)
            if dnum < 0 or dnum > 100:
                st.error("O desconto deve estar entre 0 e 100%.")
            elif data_fim_edit < data_ini_edit:
                st.error("A data de término deve ser maior ou igual à de início.")
            else:
                idx = promocoes_df["ID"].astype(str) == promo_id_sel
                promocoes_df.loc[idx, ["Desconto", "DataInicio", "DataFim"]] = [
                    float(dnum),
                    str(data_ini_edit),
                    str(data_fim_edit),
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
            df_atualizado = promocoes_df[promocoes_df["ID"].astype(str) != promo_id_sel]
            st.session_state.promocoes = df_atualizado
            try:
                salvar_promocoes_no_github(df_atualizado)
                carregar_promocoes.clear()
                st.warning("Promoção excluída e salva!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar exclusão: {e}")
