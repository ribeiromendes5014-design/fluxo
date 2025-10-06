# pages/gestao_produtos.py

import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import json
import ast

# ==============================================================================
# 🚨 CORREÇÃO: Bloco de Importação das Funções Auxiliares do utils.py
# (Funções usadas neste arquivo)
# ==============================================================================
from utils import (
    inicializar_produtos,
    carregar_livro_caixa,
    parse_date_yyyy_mm_dd,
    ler_codigo_barras_api,
    callback_salvar_novo_produto,
    to_float,
    salvar_produtos_no_github,
    save_data_github_produtos, # Função auxiliar de persistência (placeholder)
)

from constants_and_css import (
    FATOR_CARTAO, 
    COMMIT_MESSAGE_PROD,  
    ARQ_PRODUTOS          
)


def relatorio_produtos():
    """Sub-aba de Relatório e Alertas de Produtos."""
    st.subheader("⚠️ Relatório e Alertas de Estoque")

    # Funções importadas agora disponíveis
    produtos = inicializar_produtos().copy()
    df_movimentacoes = carregar_livro_caixa()
    vendas = df_movimentacoes[df_movimentacoes["Tipo"] == "Entrada"].copy()

    # --- Configurações de Alerta ---
    with st.expander("⚙️ Configurações de Alerta", expanded=False):
        col_c1, col_c2, col_c3 = st.columns(3)
        with col_c1:
            limite_estoque_baixo = st.number_input(
                "Estoque Baixo (Qtd. Máxima)", min_value=1, value=2, step=1, key="limite_estoque_baixo"
            )
        with col_c2:
            dias_validade_alerta = st.number_input(
                "Aviso de Vencimento (Dias)", min_value=1, max_value=365, value=60, step=1, key="dias_validade_alerta"
            )
        with col_c3:
            dias_sem_venda = st.number_input(
                "Produtos Parados (Dias)", min_value=1, max_value=365, value=90, step=7, key="dias_sem_venda_alerta"
            )
            
    st.markdown("---")

    # --- 1. Aviso de Estoque Baixo ---
    st.markdown(f"#### ⬇️ Alerta de Estoque Baixo (Qtd $\le {limite_estoque_baixo}$)")
    
    df_estoque_baixo = produtos[
        (produtos["Quantidade"] > 0) & 
        (produtos["Quantidade"] <= limite_estoque_baixo)
    ].sort_values(by="Quantidade").copy()
    
    if df_estoque_baixo.empty:
        st.success("🎉 Nenhum produto com estoque baixo encontrado.")
    else:
        st.warning(f"🚨 **{len(df_estoque_baixo)}** produto(s) com estoque baixo!")
        st.dataframe(
            df_estoque_baixo[["ID", "Nome", "Marca", "Quantidade", "Categoria", "PrecoVista"]],
            use_container_width=True, hide_index=True,
            column_config={"PrecoVista": st.column_config.NumberColumn("Preço Venda (R$)", format="R$ %.2f")}
        )

    st.markdown("---")

    # --- 2. Aviso de Vencimento ---
    st.markdown(f"#### ⏳ Alerta de Vencimento (Até {dias_validade_alerta} dias)")
    
    limite_validade = date.today() + timedelta(days=int(dias_validade_alerta))
    
    df_validade = produtos.copy()
    df_validade['Validade_dt'] = pd.to_datetime(df_validade['Validade'], errors='coerce')
    limite_validade_dt = datetime.combine(limite_validade, datetime.min.time()) 
    
    df_vencimento = df_validade[
        (df_validade["Quantidade"] > 0) &
        (df_validade["Validade_dt"].notna()) &
        (df_validade["Validade_dt"] <= limite_validade_dt)
    ].copy()
    
    # Calcula dias restantes
    def calcular_dias_restantes(x):
            if pd.notna(x) and isinstance(x, date):
                return (x - date.today()).days
            return float('inf')

    df_vencimento['Dias Restantes'] = df_vencimento['Validade'].apply(calcular_dias_restantes)
    df_vencimento = df_vencimento.sort_values("Dias Restantes")

    if df_vencimento.empty:
        st.success("🎉 Nenhum produto próximo da validade encontrado.")
    else:
        st.warning(f"🚨 **{len(df_vencimento)}** produto(s) vencendo em breve (até {dias_validade_alerta} dias)!")
        st.dataframe(
            df_vencimento[["ID", "Nome", "Marca", "Quantidade", "Validade", "Dias Restantes"]],
            use_container_width=True, hide_index=True
        )

    st.markdown("---")

    # --- 3. Produtos Parados (Sem Vendas) ---
    st.markdown(f"#### 📦 Alerta de Produtos Parados (Sem venda nos últimos {dias_sem_venda} dias)")

    # 1. Processa vendas para encontrar a última venda de cada produto
    vendas_list = []
    for index, row in vendas.iterrows():
        produtos_json = row["Produtos Vendidos"]
        if pd.notna(produtos_json) and produtos_json:
            try:
                # O ast.literal_eval pode ser mais robusto que o json.loads em alguns casos
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

    # 2. Merge com a lista de produtos
    produtos_parados = produtos.merge(ultima_venda, left_on="ID", right_on="IDProduto", how="left")
    
    produtos_parados["UltimaVenda"] = pd.to_datetime(produtos_parados["UltimaVenda"], errors='coerce')
    limite_dt = datetime.combine(date.today() - timedelta(days=int(dias_sem_venda)), datetime.min.time())

    # 3. Filtra: com estoque > 0 E (nunca vendidos OU última venda antes do limite)
    df_parados_sugeridos = produtos_parados[
        (produtos_parados["Quantidade"] > 0) &
        (produtos_parados["UltimaVenda"].isna() | (produtos_parados["UltimaVenda"] < limite_dt))
    ].copy()
    
    df_parados_sugeridos['UltimaVenda'] = df_parados_sugeridos['UltimaVenda'].dt.date.fillna(pd.NaT)
    
    if df_parados_sugeridos.empty:
        st.success("🎉 Nenhum produto parado com estoque encontrado.")
    else:
        st.warning(f"🚨 **{len(df_parados_sugeridos)}** produto(s) parados. Considere fazer uma promoção!")
        st.dataframe(
            df_parados_sugeridos[["ID", "Nome", "Quantidade", "UltimaVenda"]].fillna({"UltimaVenda": "NUNCA VENDIDO"}),
            use_container_width=True, hide_index=True
        )


def gestao_produtos():
    
    # Inicializa ou carrega o estado de produtos
    produtos = inicializar_produtos()
    
    # Título da Página
    st.header("📦 Gestão de Produtos e Estoque")

    # Lógica de Salvamento Automático para sincronizar alterações feitas pelo Livro Caixa
    save_data_github_produtos(produtos, ARQ_PRODUTOS, COMMIT_MESSAGE_PROD)


    # ================================
    # SUBABAS
    # ================================
    tab_cadastro, tab_lista, tab_relatorio = st.tabs(["📝 Cadastro de Produtos", "📑 Lista & Busca", "📈 Relatório e Alertas"])

    # ================================
    # SUBABA: CADASTRO
    # ================================
    with tab_cadastro:
        st.subheader("📝 Cadastro de Produtos")
        
        if 'codigo_barras' not in st.session_state:
            st.session_state["codigo_barras"] = ""
        if 'cb_grade_lidos' not in st.session_state:
            st.session_state.cb_grade_lidos = {}


        # --- Cadastro ---
        with st.expander("Cadastrar novo produto", expanded=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                tipo_produto = st.radio("Tipo de produto", ["Produto simples", "Produto com variações (grade)"], key="cad_tipo_produto")
                nome = st.text_input("Nome", key="cad_nome")
                marca = st.text_input("Marca", key="cad_marca")
                categoria = st.text_input("Categoria", key="cad_categoria")

            with c2:
                # Inicializa valores de produto simples para passar ao callback
                qtd = 0
                preco_custo = "0,00"
                preco_vista = "0,00"
                
                if tipo_produto == "Produto simples":
                    qtd = st.number_input("Quantidade", min_value=0, step=1, value=0, key="cad_qtd")
                    preco_custo = st.text_input("Preço de Custo", value="0,00", key="cad_preco_custo")
                    preco_vista = st.text_input("Preço à Vista", value="0,00", key="cad_preco_vista")
                    preco_cartao = 0.0
                    try:
                        preco_cartao = round(to_float(preco_vista) / FATOR_CARTAO, 2)
                    except Exception:
                        preco_cartao = 0.0
                    st.text_input("Preço no Cartão (auto)", value=str(preco_cartao).replace(".", ","), disabled=True, key="cad_preco_cartao")
                else:
                    st.info("Cadastre as variações abaixo (grade).")

            with c3:
                validade = st.date_input("Validade (opcional)", value=date.today(), key="cad_validade")
                foto_url = st.text_input("URL da Foto (opcional)", key="cad_foto_url")
                st.file_uploader("📷 Enviar Foto", type=["png", "jpg", "jpeg"], key="cad_foto") 
                
                # O campo de texto usa o valor do session_state (que é preenchido pela leitura)
                codigo_barras = st.text_input("Código de Barras (Pai/Simples)", value=st.session_state.get("codigo_barras", ""), key="cad_cb")

                # --- Escanear com câmera (Produto Simples/Pai) ---
                foto_codigo = st.camera_input("📷 Escanear código de barras / QR Code", key="cad_cam")
                if foto_codigo is not None:
                    imagem_bytes = foto_codigo.getbuffer() 
                    codigos_lidos = ler_codigo_barras_api(imagem_bytes)
                    if codigos_lidos:
                        # Preenche o valor no session_state e força o re-run
                        st.session_state["codigo_barras"] = codigos_lidos[0]
                        st.success(f"Código lido: **{st.session_state['codigo_barras']}**")
                        st.rerun() 
                    else:
                        st.error("❌ Não foi possível ler nenhum código.")

                # --- Upload de imagem do código de barras (Produto Simples/Pai) ---
                foto_codigo_upload = st.file_uploader("📤 Upload de imagem do código de barras", type=["png", "jpg", "jpeg"], key="cad_cb_upload")
                if foto_codigo_upload is not None:
                    imagem_bytes = foto_codigo_upload.getvalue() 
                    codigos_lidos = ler_codigo_barras_api(imagem_bytes)
                    if codigos_lidos:
                        # Preenche o valor no session_state e força o re-run
                        st.session_state["codigo_barras"] = codigos_lidos[0]
                        st.success(f"Código lido via upload: **{st.session_state['codigo_barras']}**")
                        st.rerun() 
                    else:
                        st.error("❌ Não foi possível ler nenhum código da imagem enviada.")

            # --- Cadastro da grade (variações) ---
            variações = []
            if tipo_produto == "Produto com variações (grade)":
                st.markdown("#### Cadastro das variações (grade)")
                qtd_variações = st.number_input("Quantas variações deseja cadastrar?", min_value=1, step=1, key="cad_qtd_variações")

                
                for i in range(int(qtd_variações)):
                    st.markdown(f"--- **Variação {i+1}** ---")
                    
                    var_c1, var_c2, var_c3, var_c4 = st.columns(4)
                    
                    var_nome = var_c1.text_input(f"Nome da variação {i+1}", key=f"var_nome_{i}")
                    var_qtd = var_c2.number_input(f"Quantidade variação {i+1}", min_value=0, step=1, value=0, key=f"var_qtd_{i}")
                    # CORREÇÃO DE LAYOUT: Preço de Custo e Preço à Vista em colunas separadas para evitar colisão
                    with var_c3:
                        var_preco_custo = st.text_input(f"Preço de Custo variação {i+1}", value="0,00", key=f"var_pc_{i}")
                    with var_c4:
                        var_preco_vista = st.text_input(f"Preço à Vista variação {i+1}", value="0,00", key=f"var_pv_{i}")
                    
                    var_cb_c1, var_cb_c2, var_cb_c3 = st.columns([2, 1, 1])

                    with var_cb_c1:
                        # O campo de texto da variação lê o valor salvo na sessão
                        valor_cb_inicial = st.session_state.cb_grade_lidos.get(f"var_cb_{i}", "")
                        var_codigo_barras = st.text_input(
                            f"Código de barras variação {i+1}", 
                            value=valor_cb_inicial, 
                            key=f"var_cb_{i}" 
                        )
                        
                    with var_cb_c2:
                        var_foto_upload = st.file_uploader(
                            "Upload CB", 
                            type=["png", "jpg", "jpeg"], 
                            key=f"var_cb_upload_{i}"
                        )
                    
                    with var_cb_c3:
                        var_foto_cam = st.camera_input(
                            "Escanear CB", 
                            key=f"var_cb_cam_{i}"
                        )
                    
                    # Logica de leitura do Código de Barras para a Variação
                    foto_lida = var_foto_upload or var_foto_cam
                    if foto_lida:
                        # Lógica para garantir que a leitura de CB use o valor correto
                        imagem_bytes = foto_lida.getvalue() if var_foto_upload else foto_lida.getbuffer()
                        codigos_lidos = ler_codigo_barras_api(imagem_bytes)
                        if codigos_lidos:
                            # Preenche o valor na sessão da grade e força o re-run
                            st.session_state.cb_grade_lidos[f"var_cb_{i}"] = codigos_lidos[0]
                            st.success(f"CB Variação {i+1} lido: **{codigos_lidos[0]}**")
                            st.rerun() 
                        else:
                            st.error("❌ Não foi possível ler nenhum código.")

                    variações.append({
                        "Nome": var_nome.strip(),
                        "Quantidade": int(var_qtd),
                        "PrecoCusto": to_float(var_preco_custo),
                        "PrecoVista": to_float(var_preco_vista),
                        "PrecoCartao": round(to_float(var_preco_vista) / FATOR_CARTAO, 2) if to_float(var_preco_vista) > 0 else 0.0,
                        "CodigoBarras": var_codigo_barras 
                    })
                
            # --- BOTÃO SALVAR PRODUTO (CHAMANDO CALLBACK) ---
            if st.button(
                "💾 Salvar", 
                use_container_width=True, 
                key="cad_salvar",
                # O callback_salvar_novo_produto deve ser chamado corretamente
                on_click=lambda: st.rerun() if callback_salvar_novo_produto(produtos.copy(), tipo_produto, nome, marca, categoria, qtd, preco_custo, preco_vista, validade, foto_url, codigo_barras, variações) else None,
                help="Salvar Novo Produto Completo" 
            ):
                # Se o callback for bem-sucedido, o rerun já é chamado. Se o botão for clicado sem o on_click disparar, este rerun garante a atualização.
                st.rerun()


    # ================================
    # SUBABA: LISTA & BUSCA
    # ================================
    with tab_lista:
        st.subheader("📑 Lista & Busca de Produtos")

        # --- Busca minimalista ---
        with st.expander("🔍 Pesquisar produto", expanded=True):
            criterio = st.selectbox(
                "Pesquisar por:",
                ["Nome", "Marca", "Código de Barras", "Valor"]
            )
            termo = st.text_input("Digite para buscar:")

            if termo:
                if criterio == "Nome":
                    produtos_filtrados = produtos[produtos["Nome"].astype(str).str.contains(termo, case=False, na=False)]
                elif criterio == "Marca":
                    produtos_filtrados = produtos[produtos["Marca"].astype(str).str.contains(termo, case=False, na=False)]
                elif criterio == "Código de Barras":
                    produtos_filtrados = produtos[produtos["CodigoBarras"].astype(str).str.contains(termo, case=False, na=False)]
                elif criterio == "Valor":
                    try:
                        valor = float(termo.replace(",", "."))
                        # Converte a coluna para float antes de comparar
                        produtos_filtrados = produtos[
                            (pd.to_numeric(produtos["PrecoVista"], errors='coerce').fillna(0) == valor) |
                            (pd.to_numeric(produtos["PrecoCusto"], errors='coerce').fillna(0) == valor) |
                            (pd.to_numeric(produtos["PrecoCartao"], errors='coerce').fillna(0) == valor)
                        ]
                    except:
                        st.warning("Digite um número válido para buscar por valor.")
                        produtos_filtrados = produtos.copy()
            else:
                # SE NENHUM TERMO FOR DIGITADO, EXIBE TODOS OS PRODUTOS
                produtos_filtrados = produtos.copy()

            if "PaiID" not in produtos_filtrados.columns:
                produtos_filtrados["PaiID"] = None

        # --- Lista de produtos com agrupamento por Pai e Variações ---
        st.markdown("### Lista de produtos")

        if produtos_filtrados.empty:
            st.info("Nenhum produto encontrado.")
        else:
            # 🚨 INJETANDO CSS LOCALMENTE AQUI PARA NÃO QUEBRAR O HEADER
            st.markdown("""
                <style>
                .custom-header, .custom-row {
                    display: grid;
                    grid-template-columns: 80px 3fr 1fr 1fr 1.5fr 0.5fr 0.5fr;
                    align-items: center;
                    gap: 5px;
                }
                .custom-header {
                    font-weight: bold;
                    padding: 8px 0;
                    border-bottom: 1px solid #ccc;
                    margin-bottom: 5px;
                }
                .custom-price-block {
                    line-height: 1.2;
                }
                /* NOTA: O CSS stButton > button foi movido para constants_and_css.py */
                </style>
                <div class="custom-header">
                    <div>Foto</div>
                    <div>Produto & Marca</div>
                    <div>Estoque</div>
                    <div>Validade</div>
                    <div>Preços (C/V/C)</div>
                    <div style="grid-column: span 2;">Ações</div>
                </div>
            """, unsafe_allow_html=True)
            # 🚨 FIM DA INJEÇÃO DE CSS

            produtos_filtrados["Quantidade"] = pd.to_numeric(produtos_filtrados["Quantidade"], errors='coerce').fillna(0).astype(int)
            
            # CRÍTICO: Filtra apenas os produtos que NÃO são variações (PaiID é nulo ou vazio/NaN)
            # Produtos que têm PaiID preenchido são listados *dentro* do expander do produto Pai.
            produtos_pai = produtos_filtrados[produtos_filtrados["PaiID"].isnull() | (produtos_filtrados["PaiID"] == '')]
            produtos_filho = produtos_filtrados[produtos_filtrados["PaiID"].notnull() & (produtos_filtrados["PaiID"] != '')]
            

            for index, pai in produtos_pai.iterrows():
                # A partir daqui, a lógica de listagem funciona como o esperado, usando apenas os "produtos_pai" (que incluem produtos simples).
                with st.container(border=True):
                    c = st.columns([1, 3, 1, 1, 1.5, 0.5, 0.5]) 
                    
                    if str(pai["FotoURL"]).strip():
                        try:
                            c[0].image(pai["FotoURL"], width=60)
                        except Exception:
                            c[0].write("—")
                    else:
                        c[0].write("—")

                    cb = f' • CB: {pai["CodigoBarras"]}' if str(pai.get("CodigoBarras", "")).strip() else ""
                    c[1].markdown(f"**{pai['Nome']}**<br><small>Marca: {pai['Marca']} | Cat: {pai['Categoria']}</small>", unsafe_allow_html=True)
                    
                    estoque_total = pai['Quantidade']
                    filhos_do_pai = produtos_filho[produtos_filho["PaiID"] == str(pai["ID"])]
                    if not filhos_do_pai.empty:
                        # Se houver filhos, o estoque total é a soma dos filhos.
                        estoque_total = filhos_do_pai['Quantidade'].sum()
                    
                    c[2].markdown(f"**{estoque_total}**")
                    
                    c[3].write(f"{pai['Validade']}")
                    
                    pv = to_float(pai['PrecoVista'])
                    pc_calc = round(pv / FATOR_CARTAO, 2)
                    
                    preco_html = (
                        f'<div class="custom-price-block">'
                        f'<small>C: R$ {to_float(pai["PrecoCusto"]):,.2f}</small><br>'
                        f'**V:** R$ {pv:,.2f}<br>'
                        f'**C:** R$ {pc_calc:,.2f}'
                        f'</div>'
                    )
                    c[4].markdown(preco_html, unsafe_allow_html=True)
                    
                    try:
                        eid = str(pai["ID"])
                    except Exception:
                        eid = str(index)

                    if c[5].button("✏️", key=f"edit_pai_{index}_{eid}", help="Editar produto"):
                        st.session_state["edit_prod"] = eid
                        st.rerun()

                    if c[6].button("🗑️", key=f"del_pai_{index}_{eid}", help="Excluir produto"):
                        products = produtos[produtos["ID"] != eid]
                        products = products[products["PaiID"] != eid]
                        st.session_state["produtos"] = products
                        
                        nome_pai = str(pai.get('Nome', 'Produto Desconhecido'))
                        if salvar_produtos_no_github(products, f"Exclusão do produto pai {nome_pai}"):
                            inicializar_produtos.clear() 
                        st.rerun()
                        
                    if not filhos_do_pai.empty:
                        with st.expander(f"Variações de {pai['Nome']} ({len(filhos_do_pai)} variações)"):
                            for index_var, var in filhos_do_pai.iterrows():
                                c_var = st.columns([1, 3, 1, 1, 1.5, 0.5, 0.5]) 
                                
                                foto_url_var = str(var["FotoURL"]).strip() or str(pai["FotoURL"]).strip()
                                if foto_url_var:
                                    try:
                                        c_var[0].image(foto_url_var, width=60)
                                    except Exception:
                                        c_var[0].write("—")
                                else:
                                    c_var[0].write("—")

                                cb_var = f' • CB: {var["CodigoBarras"]}' if str(var.get("CodigoBarras", "")).strip() else ""
                                c_var[1].markdown(f"**{var['Nome']}**<br><small>Marca: {var['Marca']} | Cat: {var['Categoria']}</small>", unsafe_allow_html=True)
                                
                                c_var[2].write(f"{var['Quantidade']}")
                                
                                c_var[3].write(f"{pai['Validade']}")

                                pv_var = to_float(var['PrecoVista'])
                                pc_var_calc = round(pv_var / FATOR_CARTAO, 2)
                                
                                preco_var_html = (
                                    f'<div class="custom-price-block">'
                                    f'<small>C: R$ {to_float(var["PrecoCusto"]):,.2f}</small><br>'
                                    f'**V:** R$ {pv_var:,.2f}<br>'
                                    f'**C:** R$ {pc_var_calc:,.2f}'
                                    f'</div>'
                                )
                                c_var[4].markdown(preco_var_html, unsafe_allow_html=True)
                                
                                try:
                                    eid_var = str(var["ID"])
                                except Exception:
                                    eid_var = str(index_var)

                                if c_var[5].button("✏️", key=f"edit_filho_{index_var}_{eid_var}", help="Editar variação"):
                                    st.session_state["edit_prod"] = eid_var
                                    st.rerun()

                                if c_var[6].button("🗑️", key=f"del_filho_{index_var}_{eid_var}", help="Excluir variação"):
                                    products = produtos[produtos["ID"] != eid_var]
                                    st.session_state["produtos"] = products
                                    
                                    nome_var = str(var.get('Nome', 'Variação Desconhecida'))
                                    if salvar_produtos_no_github(products, f"Exclusão da variação {nome_var}"):
                                        inicializar_produtos.clear() 
                                    st.rerun()

            if "edit_prod" in st.session_state:
                eid = st.session_state["edit_prod"]
                row = produtos[produtos["ID"] == str(eid)]
                if not row.empty:
                    st.subheader(f"Editar produto ID: {eid} ({row.iloc[0]['Nome']})")
                    row = row.iloc[0]
                    
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        novo_nome = st.text_input("Nome", value=row["Nome"], key=f"edit_nome_{eid}")
                        nova_marca = st.text_input("Marca", value=row["Marca"], key=f"edit_marca_{eid}")
                        nova_cat = st.text_input("Categoria", value=row["Categoria"], key=f"edit_cat_{eid}")
                    with c2:
                        qtd_value = int(row["Quantidade"]) if pd.notna(row["Quantidade"]) else 0
                        nova_qtd = st.number_input("Quantidade", min_value=0, step=1, value=qtd_value, key=f"edit_qtd_{eid}")
                        novo_preco_custo = st.text_input("Preço de Custo", value=f"{to_float(row["PrecoCusto"]):.2f}".replace(".", ","), key=f"edit_pc_{eid}")
                        novo_preco_vista = st.text_input("Preço à Vista", value=f"{to_float(row["PrecoVista"]):.2f}".replace(".", ","), key=f"edit_pv_{eid}")
                    with c3:
                        try:
                            # Tenta garantir que a validade seja um objeto date para o input
                            vdata = row["Validade"] if pd.notna(row["Validade"]) and isinstance(row["Validade"], date) else date.today()
                        except Exception:
                            vdata = date.today()
                        nova_validade = st.date_input("Validade", value=vdata, key=f"edit_val_{eid}")
                        nova_foto = st.text_input("URL da Foto", value=row["FotoURL"], key=f"edit_foto_{eid}")
                        novo_cb = st.text_input("Código de Barras", value=str(row.get("CodigoBarras", "")), key=f"edit_cb_{eid}")

                        foto_codigo_edit = st.camera_input("📷 Atualizar código de barras", key=f"edit_cam_{eid}")
                        if foto_codigo_edit is not None:
                            codigo_lido = ler_codigo_barras_api(foto_codigo_edit.getbuffer()) 
                            if codigo_lido:
                                novo_cb = codigo_lido[0]
                                st.success(f"Código lido: **{novo_cb}**")

                    col_empty_left, col_save, col_cancel = st.columns([3, 1.5, 1.5]) 
                    
                    with col_save:
                        if st.button("💾 Salvar", key=f"save_{eid}", type="primary", use_container_width=True, help="Salvar Alterações"):
                            preco_vista_float = to_float(novo_preco_vista)
                            novo_preco_cartao = round(preco_vista_float / FATOR_CARTAO, 2) if preco_vista_float > 0 else 0.0
                            
                            produtos.loc[produtos["ID"] == str(eid), [
                                "Nome", "Marca", "Categoria", "Quantidade",
                                "PrecoCusto", "PrecoVista", "PrecoCartao",
                                "Validade", "FotoURL", "CodigoBarras"
                            ]] = [
                                novo_nome.strip(),
                                nova_marca.strip(),
                                nova_cat.strip(),
                                int(nova_qtd),
                                to_float(novo_preco_custo),
                                preco_vista_float,
                                novo_preco_cartao,
                                nova_validade, # Já é um objeto date
                                nova_foto.strip(),
                                str(novo_cb).strip()
                            ]
                            st.session_state["produtos"] = produtos
                            if salvar_produtos_no_github(produtos, "Atualizando produto"):
                                inicializar_produtos.clear()
                                
                            del st.session_state["edit_prod"]
                            st.rerun()
                            
                    with col_cancel:
                        if st.button("❌ Cancelar", key=f"cancel_{eid}", use_container_width=True, help="Cancelar Edição"):
                            del st.session_state["edit_prod"]
                            st.rerun()

    # ================================
    # SUBABA: RELATÓRIO E ALERTAS (Novo)
    # ================================
    with tab_relatorio:
        relatorio_produtos()
