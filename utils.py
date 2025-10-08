# pages/gestao_produtos.py

import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import json
import ast

# ==============================================================================
# 🚨 Bloco de Importação das Funções Auxiliares do utils.py
# ==============================================================================
from utils import (
    inicializar_produtos,
    carregar_livro_caixa,
    parse_date_yyyy_mm_dd,
    ler_codigo_barras_api,
    callback_salvar_novo_produto,
    to_float,
    salvar_produtos_no_github,
    save_data_github_produtos,
)

from constants_and_css import (
    FATOR_CARTAO,
    COMMIT_MESSAGE_PROD,
    ARQ_PRODUTOS
)

# ==============================================================================
# FUNÇÃO AUXILIAR: Define os campos de grade com base na Categoria
# ==============================================================================
def get_campos_grade(categoria: str) -> dict:
    """Retorna os campos de detalhe da grade (Cor, Tamanho) com base na categoria."""
    cat_lower = categoria.lower().strip()
    if "calçado" in cat_lower or "chinelo" in cat_lower:
        return {
            "Cor": {"type": "text", "help": "Ex: Preto, Azul, etc."},
            "Tamanho/Numeração": {"type": "conditional_calçado"},
        }
    elif "roupa" in cat_lower:
        return {
            "Cor": {"type": "text", "help": "Ex: Vermelho, Branco, etc."},
            "Tamanho": {"type": "selectbox", "options": ["", "P", "M", "G", "GG", "Único"], "help": "Selecione o tamanho padrão."},
        }
    return {}


# ==============================================================================
# RELATÓRIO DE ALERTAS DE ESTOQUE
# ==============================================================================
def relatorio_produtos():
    """Sub-aba de Relatório e Alertas de Produtos."""
    st.subheader("⚠️ Relatório e Alertas de Estoque")

    produtos = inicializar_produtos().copy()

    if produtos is None or produtos.empty:
        st.warning("⚠️ Nenhum produto encontrado no CSV ou GitHub.")
        return

    # Ajuste de nomes de colunas para compatibilidade
    produtos.columns = [col.capitalize() for col in produtos.columns]

    # Garante que a coluna de validade seja do tipo data
    produtos["Validade"] = pd.to_datetime(produtos["Validade"], errors="coerce").dt.date

    df_movimentacoes = carregar_livro_caixa()
    vendas = df_movimentacoes[df_movimentacoes["Tipo"] == "Entrada"].copy()

    with st.expander("⚙️ Configurações de Alerta", expanded=False):
        col_c1, col_c2, col_c3 = st.columns(3)
        with col_c1:
            limite_estoque_baixo = st.number_input(
                "Estoque Baixo (Qtd. Máxima)", min_value=1, value=2, step=1
            )
        with col_c2:
            dias_validade_alerta = st.number_input(
                "Aviso de Vencimento (Dias)", min_value=1, max_value=365, value=60, step=1
            )
        with col_c3:
            dias_sem_venda = st.number_input(
                "Produtos Parados (Dias)", min_value=1, max_value=365, value=90, step=7
            )

    st.markdown("---")

    # ==========================================================
    # ESTOQUE BAIXO
    # ==========================================================
    st.markdown(f"#### ⬇️ Alerta de Estoque Baixo (Qtd ≤ {limite_estoque_baixo})")
    df_estoque_baixo = produtos[
        (produtos["Quantidade"] > 0) &
        (produtos["Quantidade"] <= limite_estoque_baixo)
    ].sort_values(by="Quantidade")

    if df_estoque_baixo.empty:
        st.success("🎉 Nenhum produto com estoque baixo encontrado.")
    else:
        st.warning(f"🚨 {len(df_estoque_baixo)} produto(s) com estoque baixo!")
        st.dataframe(
            df_estoque_baixo[["Id", "Nome", "Marca", "Quantidade", "Categoria", "Precovista"]],
            use_container_width=True, hide_index=True,
            column_config={"Precovista": st.column_config.NumberColumn("Preço Venda (R$)", format="R$ %.2f")}
        )

    st.markdown("---")

    # ==========================================================
    # VENCIMENTO
    # ==========================================================
    st.markdown(f"#### ⏳ Alerta de Vencimento (Até {dias_validade_alerta} dias)")
    limite_validade = date.today() + timedelta(days=int(dias_validade_alerta))
    df_vencimento = produtos[
        (produtos["Quantidade"] > 0) &
        (produtos["Validade"].notna()) &
        (produtos["Validade"] <= limite_validade)
    ].copy()

    if not df_vencimento.empty:
        df_vencimento["Dias Restantes"] = df_vencimento["Validade"].apply(
            lambda x: (x - date.today()).days if pd.notna(x) else float("inf")
        )
        df_vencimento = df_vencimento.sort_values("Dias Restantes")

    if df_vencimento.empty:
        st.success("🎉 Nenhum produto próximo da validade encontrado.")
    else:
        st.warning(f"🚨 {len(df_vencimento)} produto(s) vencendo em breve!")
        st.dataframe(
            df_vencimento[["Id", "Nome", "Marca", "Quantidade", "Validade", "Dias Restantes"]],
            use_container_width=True, hide_index=True
        )

    st.markdown("---")

    # ==========================================================
    # PRODUTOS PARADOS
    # ==========================================================
    st.markdown(f"#### 📦 Alerta de Produtos Parados (Sem venda nos últimos {dias_sem_venda} dias)")
    vendas_list = []
    for _, row in vendas.iterrows():
        produtos_json = row["Produtos Vendidos"]
        if pd.notna(produtos_json) and produtos_json:
            try:
                items = ast.literal_eval(produtos_json)
                if isinstance(items, list):
                    for item in items:
                        produto_id = str(item.get("Produto_ID"))
                        if produto_id and produto_id != "None":
                            vendas_list.append({
                                "Data": parse_date_yyyy_mm_dd(row["Data"]),
                                "IDProduto": produto_id
                            })
            except Exception:
                continue

    if vendas_list:
        vendas_flat = pd.DataFrame(vendas_list)
        vendas_flat["Data"] = pd.to_datetime(vendas_flat["Data"], errors="coerce")
        ultima_venda = vendas_flat.groupby("IDProduto")["Data"].max().reset_index()
        ultima_venda.columns = ["IDProduto", "UltimaVenda"]
    else:
        ultima_venda = pd.DataFrame(columns=["IDProduto", "UltimaVenda"])

    produtos_parados = produtos.merge(ultima_venda, left_on="Id", right_on="IDProduto", how="left")
    produtos_parados["UltimaVenda"] = pd.to_datetime(produtos_parados["UltimaVenda"], errors="coerce")
    limite_dt = datetime.now() - timedelta(days=int(dias_sem_venda))
    df_parados_sugeridos = produtos_parados[
        (produtos_parados["Quantidade"] > 0) &
        (produtos_parados["UltimaVenda"].isna() | (produtos_parados["UltimaVenda"] < limite_dt))
    ].copy()
    df_parados_sugeridos["UltimaVenda"] = df_parados_sugeridos["UltimaVenda"].dt.date.fillna(pd.NaT)

    if df_parados_sugeridos.empty:
        st.success("🎉 Nenhum produto parado com estoque encontrado.")
    else:
        st.warning(f"🚨 {len(df_parados_sugeridos)} produto(s) parados. Considere fazer uma promoção!")
        st.dataframe(
            df_parados_sugeridos[["Id", "Nome", "Quantidade", "UltimaVenda"]].fillna({"UltimaVenda": "NUNCA VENDIDO"}),
            use_container_width=True, hide_index=True
        )


# ==============================================================================
# PÁGINA PRINCIPAL DE GESTÃO DE PRODUTOS
# ==============================================================================
def gestao_produtos():
    produtos = inicializar_produtos()

    if produtos is None or produtos.empty:
        st.error("❌ Nenhum produto foi carregado. Verifique o arquivo CSV ou conexão com o GitHub.")
        return

    # Padroniza colunas para exibição correta
    produtos.columns = [col.capitalize() for col in produtos.columns]

    st.header("📦 Gestão de Produtos e Estoque")

    # Mostra o conteúdo carregado (debug)
    with st.expander("📂 Dados carregados (debug)", expanded=False):
        st.dataframe(produtos.head())

    save_data_github_produtos(produtos, ARQ_PRODUTOS, COMMIT_MESSAGE_PROD)

    tab_cadastro, tab_lista, tab_relatorio = st.tabs(["📝 Cadastro de Produtos", "📑 Lista & Busca", "📈 Relatório e Alertas"])

    # ============ ABA RELATÓRIO ============
    with tab_relatorio:
        relatorio_produtos()
