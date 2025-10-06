# pages/homepage.py

import streamlit as st
import pandas as pd
from datetime import date
# Importa funções e constantes
from utils import inicializar_produtos, carregar_livro_caixa, get_most_sold_products(...)
from constants_and_css import URL_MAIS_VENDIDOS, URL_OFERTAS, URL_NOVIDADES, FATOR_CARTAO


def homepage():
    """PÁGINA PRINCIPAL: Exibição de produtos, ofertas e mais vendidos."""
    
    # --- 1. Carrega dados e calcula métricas ---
    produtos_df = inicializar_produtos()
    df_movimentacoes = carregar_livro_caixa()
    
    # Produtos novos (últimos N cadastrados com estoque > 0)
    produtos_novos = produtos_df[produtos_df['Quantidade'] > 0].sort_values(by='ID', ascending=False).head(10)
    
    # Produtos mais vendidos (Top N)
    df_mais_vendidos_id = get_most_sold_products(df_movimentacoes)
    top_ids_vendidos = df_mais_vendidos_id["Produto_ID"].head(10).tolist() if not df_mais_vendidos_id.empty else []
    if top_ids_vendidos:
        temp = produtos_df[produtos_df["ID"].isin(top_ids_vendidos)].copy()
        present_ids = [pid for pid in top_ids_vendidos if pid in temp["ID"].astype(str).values]
        if present_ids:
            produtos_mais_vendidos = temp.set_index("ID").loc[present_ids].reset_index()
        else:
            produtos_mais_vendidos = pd.DataFrame(columns=produtos_df.columns)
    else:
        produtos_mais_vendidos = pd.DataFrame(columns=produtos_df.columns)
    
    # Produtos em Oferta: PrecoCartao < PrecoVista (PrecoVista)
    produtos_oferta = produtos_df.copy()
    produtos_oferta['PrecoVista_f'] = pd.to_numeric(produtos_oferta['PrecoVista'], errors='coerce').fillna(0)
    produtos_oferta['PrecoCartao_f'] = pd.to_numeric(produtos_oferta['PrecoCartao'], errors='coerce').fillna(0)
    produtos_oferta = produtos_oferta[
        (produtos_oferta['PrecoVista_f'] > 0) &
        (produtos_oferta['PrecoCartao_f'] < produtos_oferta['PrecoVista_f'])
    ].sort_values(by='Nome').head(10)

    
    # ==================================================
    # 3. SEÇÃO MAIS VENDIDOS (Carrossel)
    # ==================================================
    st.markdown(f'<img src="{URL_MAIS_VENDIDOS}" class="section-header-img" alt="Mais Vendidos">', unsafe_allow_html=True)
    
    if produtos_mais_vendidos.empty:
        st.info("Não há dados de vendas suficientes (Entradas Realizadas) para determinar os produtos mais vendidos.")
    else:
        html_cards = []
        for i, row in produtos_mais_vendidos.iterrows():
            vendas_count = df_mais_vendidos_id[df_mais_vendidos_id["Produto_ID"] == str(row["ID"])]["Quantidade Total Vendida"].iloc[0] if not df_mais_vendidos_id.empty and not df_mais_vendidos_id[df_mais_vendidos_id["Produto_ID"] == str(row["ID"])].empty else 0
            nome_produto = row['Nome']
            descricao = row['Marca'] if row['Marca'] else row['Categoria']
            preco_cartao = to_float(row.get('PrecoCartao', 0))
            foto_url = row.get("FotoURL") if row.get("FotoURL") else f"https://placehold.co/150x150/F48FB1/880E4F?text={str(row.get('Nome','')).replace(' ', '+')}"
            card_html = f'''
                <div class="product-card">
                    <img src="{foto_url}" alt="{nome_produto}">
                    <p style="font-size: 0.9em; height: 40px; white-space: normal;">{nome_produto} - {descricao}</p>
                    <p style="margin: 5px 0 15px;">
                        <span class="price-promo">R$ {preco_cartao:,.2f}</span>
                    </p>
                    <button onclick="window.alert('Compra simulada: {nome_produto}')" class="buy-button">COMPRAR</button>
                    <p style="font-size: 0.7em; color: #888; margin-top: 5px;">Vendas: {int(vendas_count)}</p>
                </div>
            '''
            html_cards.append(card_html)
        st.markdown(f'''
            <div class="carousel-outer-container">
                <div class="product-wrapper">
                    {"".join(html_cards)}
                </div>
            </div>
        ''', unsafe_allow_html=True)

    st.markdown("---")

    # ==================================================
    # 4. SEÇÃO NOSSAS OFERTAS (Carrossel)
    # ==================================================
    st.markdown('<div class="offer-section">', unsafe_allow_html=True)
    st.markdown(f'<img src="{URL_OFERTAS}" class="section-header-img" alt="Nossas Ofertas">', unsafe_allow_html=True)

    if produtos_oferta.empty:
        st.info("Nenhum produto em promoção registrado no momento.")
    else:
        html_cards_ofertas = []
        for i, row in produtos_oferta.iterrows():
            nome_produto = row['Nome']
            descricao = row['Marca'] if row['Marca'] else row['Categoria']
            preco_vista_original = row['PrecoVista_f']
            preco_cartao_promo = row['PrecoCartao_f']
            desconto = 0.0
            try:
                desconto = 1 - (preco_cartao_promo / preco_vista_original) if preco_vista_original > 0 else 0
            except:
                desconto = 0.0
            desconto_percent = round(desconto * 100)
            foto_url = row.get("FotoURL") if row.get("FotoURL") else f"https://placehold.co/150x150/E91E63/FFFFFF?text={str(row.get('Nome','')).replace(' ', '+')}"
            card_html = f'''
                <div class="product-card" style="background-color: #FFF5F7;">
                    <img src="{foto_url}" alt="{nome_produto}">
                    <p style="font-size: 0.9em; height: 40px; white-space: normal;">{nome_produto} - {descricao}</p>
                    <p style="margin: 5px 0 0;">
                        <span class="price-original">R$ {preco_vista_original:,.2f}</span>
                        <span class="price-promo">R$ {preco_cartao_promo:,.2f}</span>
                    </p>
                    <p style="color: #E91E63; font-weight: bold; font-size: 0.8em; margin-top: 5px; margin-bottom: 10px;">{desconto_percent}% OFF</p>
                    <button onclick="window.alert('Compra simulada: {nome_produto}')" class="buy-button">COMPRAR</button>
                </div>
            '''
            html_cards_ofertas.append(card_html)
        st.markdown(f'''
            <div class="carousel-outer-container">
                <div class="product-wrapper">
                    {"".join(html_cards_ofertas)}
                </div>
            </div>
        ''', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)  # Fecha offer-section
    st.markdown("---")

    # ==================================================
    # 5. SEÇÃO NOSSAS NOVIDADES (Carrossel Automático)
    # ==================================================
    st.markdown(f'<h2>Nossas Novidades</h2>', unsafe_allow_html=True)

    # Seleciona os últimos 10 produtos cadastrados com estoque > 0
    produtos_novos = produtos_df[produtos_df['Quantidade'] > 0].sort_values(by='ID', ascending=False).head(10)

    if produtos_novos.empty:
        st.info("Não há produtos cadastrados no estoque para exibir como novidades.")
    else:
        html_cards_novidades = []
        for _, row in produtos_novos.iterrows():
            foto_url = row.get("FotoURL") if row.get("FotoURL") else f"https://placehold.co/400x400/FFC1E3/E91E63?text={row['Nome'].replace(' ', '+')}"
            preco_vista = to_float(row.get('PrecoVista', 0))
            preco_formatado = f"R$ {preco_vista:,.2f}" if preco_vista > 0 else "Preço não disponível"
            nome = row.get("Nome", "")
            marca = row.get("Marca", "")
            qtd = int(row.get("Quantidade", 0))

            card_html = f"""
            <div class="product-card">
                <p style="font-weight: bold; color: #E91E63; margin-bottom: 10px; font-size: 0.9em;">✨ Doce&Bella - Novidade</p>
                <img src="{foto_url}" alt="{nome}">
                <p style="font-weight: bold; margin-top: 10px; height: 30px; white-space: normal;">{nome} ({marca})</p>
                <p style="font-size: 0.9em;">✨ Estoque: {qtd}</p>
                <p style="font-weight: bold; color: #E91E63; margin-top: 5px;">💸 {preco_formatado}</p>
                
            </div>
            """
            html_cards_novidades.append(card_html)

        # Renderiza o carrossel
        st.markdown(f"""
            <div class="carousel-outer-container">
                <div class="product-wrapper">
                    {''.join(html_cards_novidades)}
               
                </div>
            </div>
        """, unsafe_allow_html=True)


