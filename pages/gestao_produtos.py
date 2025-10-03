# pages/gestao_produtos.py

import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import json
import ast
# Importa tudo que Produtos precisa
from utils import (
    inicializar_produtos, carregar_livro_caixa, ajustar_estoque, to_float, 
    salvar_produtos_no_github, ler_codigo_barras_api, callback_salvar_novo_produto, 
    save_data_github_produtos, parse_date_yyyy_mm_dd, prox_id, norm_promocoes, carregar_promocoes
)
from constants_and_css import (
    FATOR_CARTAO, 
    COMMIT_MESSAGE_PROD,  # <-- CONSTANTE ADICIONADA
    ARQ_PRODUTOS          # <-- CONSTANTE ADICIONADA
)


def relatorio_produtos():
    """Sub-aba de Relatório e Alertas de Produtos."""
    
    st.subheader("⚠️ Relatório e Alertas de Estoque")
    st.info("Função de relatório e alerta de produtos ativada. Lógica de cálculo pendente.")
    
    # Se esta parte estivesse incompleta, o erro de NameError já teria ocorrido antes.
    # Assumimos que a lógica aqui está correta, mas com o código de exibição removido.
    produtos = inicializar_produtos().copy()
    df_movimentacoes = carregar_livro_caixa()
    vendas = df_movimentacoes[df_movimentacoes["Tipo"] == "Entrada"].copy()


def gestao_produtos():
    """PÁGINA GESTÃO DE PRODUTOS: Cadastro, listagem e alertas."""
    
    # Inicializa ou carrega o estado de produtos
    produtos = inicializar_produtos()
    
    st.header("📦 Gestão de Produtos e Estoque") 

    # ESTA LINHA AGORA DEVE FUNCIONAR:
    save_data_github_produtos(produtos, ARQ_PRODUTOS, COMMIT_MESSAGE_PROD)

    tab_cadastro, tab_lista, tab_relatorio = st.tabs(["📝 Cadastro de Produtos", "📑 Lista & Busca", "📈 Relatório e Alertas"])

    with tab_cadastro:
        st.subheader("📝 Cadastro de Produtos")
        st.info("Conteúdo do formulário de cadastro de produtos pendente.")

    with tab_lista:
        st.subheader("📑 Lista & Busca de Produtos")
        st.info("Conteúdo da lista de produtos pendente.")

    with tab_relatorio:
        relatorio_produtos()
