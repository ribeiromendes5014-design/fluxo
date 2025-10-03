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
from constants_and_css import FATOR_CARTAO, COMMIT_MESSAGE_PROD

# Colar a função relatorio_produtos (ela é uma sub-função da gestao_produtos)
def relatorio_produtos():
    """Sub-aba de Relatório e Alertas de Produtos."""
    # ... [Cole o corpo da sua função relatorio_produtos() aqui]
    
    st.subheader("⚠️ Relatório e Alertas de Estoque")

    produtos = inicializar_produtos().copy()
    df_movimentacoes = carregar_livro_caixa()
    vendas = df_movimentacoes[df_movimentacoes["Tipo"] == "Entrada"].copy()

    # --- Configurações de Alerta ---
    with st.expander("⚙️ Configurações de Alerta", expanded=False):
        # ... [O restante da lógica de relatorio_produtos]
        
    pass # Remova o pass após colar o código

def gestao_produtos():
    """PÁGINA GESTÃO DE PRODUTOS: Cadastro, listagem e alertas."""
    
    # [Cole o restante do código da sua função gestao_produtos() aqui]
    
    # ... (O corpo inteiro da função)
    
    pass # Remova o pass após colar o código