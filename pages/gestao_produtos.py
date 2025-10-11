# pages/gestao_produtos.py

import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import json
import ast

# ==============================================================================
# 🚨 Bloco de Importação das Funções Auxiliares do utils.py
# ==============================================================================
# Assumindo que essas funções foram implementadas corretamente em utils.py
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


def relatorio_produtos():
    """Sub-aba de Relatório e Alertas de Produtos."""
    st.subheader("⚠️ Relatório e Alertas de Estoque")

    produtos = inicializar_produtos().copy()
    # Garante que a coluna de validade seja do tipo data, tratando erros
    produtos['Validade'] = pd.to_datetime(produtos['Validade'], errors='coerce').dt.date

    df_movimentacoes = carregar_livro_caixa()
    vendas = df_movimentacoes[df_movimentacoes["Tipo"] == "Entrada"].copy()

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

    st.markdown(f"#### ⏳ Alerta de Vencimento (Até {dias_validade_alerta} dias)")
    limite_validade = date.today() + timedelta(days=int(dias_validade_alerta))

    df_vencimento = produtos[
        (produtos["Quantidade"] > 0) &
        (produtos["Validade"].notna()) &
        (produtos["Validade"] <= limite_validade)
    ].copy()

    if not df_vencimento.empty:
        # ✨ CORREÇÃO: Removido o `.date()` de 'x.date()' pois 'x' já é um objeto date.
        df_vencimento['Dias Restantes'] = df_vencimento['Validade'].apply(lambda x: (x - date.today()).days if pd.notna(x) else float('inf'))
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

    st.markdown(f"#### 📦 Alerta de Produtos Parados (Sem venda nos últimos {dias_sem_venda} dias)")
    vendas_list = []
    for index, row in vendas.iterrows():
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
    produtos_parados = produtos.merge(ultima_venda, left_on="ID", right_on="IDProduto", how="left")
    produtos_parados["UltimaVenda"] = pd.to_datetime(produtos_parados["UltimaVenda"], errors='coerce')
    limite_dt = datetime.now() - timedelta(days=int(dias_sem_venda))
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
    produtos = inicializar_produtos().copy()
    st.header("📦 Gestão de Produtos e Estoque")

    # Evita sobrescrever o CSV remoto se não houver produtos
    if produtos is not None and not produtos.empty:
        # Garante que a coluna exista antes de salvar (necessário para persistência)
        if "DescricaoLonga" not in produtos.columns:
            produtos["DescricaoLonga"] = ""
        save_data_github_produtos(produtos, ARQ_PRODUTOS, COMMIT_MESSAGE_PROD)
    else:
        st.warning("⚠️ Nenhum produto carregado — nada foi salvo no GitHub para evitar sobrescrita.")

    tab_cadastro, tab_lista, tab_relatorio = st.tabs(["📝 Cadastro de Produtos", "📑 Lista & Busca", "📈 Relatório e Alertas"])

    with tab_cadastro:
        st.subheader("📝 Cadastro de Produtos")
        if 'codigo_barras' not in st.session_state:
            st.session_state["codigo_barras"] = ""
        if 'cb_grade_lidos' not in st.session_state:
            st.session_state.cb_grade_lidos = {}

        with st.expander("Cadastrar novo produto", expanded=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                tipo_produto = st.radio("Tipo de produto", ["Produto simples", "Produto com variações (grade)"], key="cad_tipo_produto")
                nome = st.text_input("Nome", key="cad_nome")
                marca = st.text_input("Marca", key="cad_marca")
                categoria = st.text_input("Categoria (Ex: Calçado, Roupa, Geral)", key="cad_categoria")
                # NOVO CAMPO DE DESCRIÇÃO LONGA
                descricao_longa = st.text_area("Descrição Detalhada do Produto", help="Escreva detalhes importantes, composição ou características.", key="cad_descricao_longa")
            with c2:
                qtd = 0
                preco_custo = "0,00"
                preco_vista = "0,00"
                cashback_percent = 0.0
                if tipo_produto == "Produto simples":
                    qtd = st.number_input("Quantidade", min_value=0, step=1, value=0, key="cad_qtd")
                    preco_custo = st.text_input("Preço de Custo", value="0,00", key="cad_preco_custo")
                    preco_vista = st.text_input("Preço à Vista", value="0,00", key="cad_preco_vista")
                    oferece_cashback = st.checkbox("Oferece Cashback?", key="cad_oferece_cashback")
                    if oferece_cashback:
                        cashback_percent = st.number_input("Cashback (%)", min_value=0.0, max_value=100.0, value=3.0, step=0.5, key="cad_cashback_percent")
                    try:
                        preco_cartao = round(to_float(preco_vista) / FATOR_CARTAO, 2)
                    except Exception:
                        preco_cartao = 0.0
                    st.text_input("Preço no Cartão (auto)", value=str(preco_cartao).replace(".", ","), disabled=True, key="cad_preco_cartao")
                else:
                    st.info(f"Cadastre as variações abaixo. Categoria: **{categoria}**")
            with c3:
                tem_validade = st.checkbox("Produto com data de validade?", value=True, key="cad_tem_validade")
                validade = pd.NaT
                if tem_validade:
                    validade = st.date_input("Data de Validade", value=date.today() + timedelta(days=365), key="cad_validade")
                foto_url = st.text_input("URL da Foto (opcional)", help="Foto do produto principal", key="cad_foto_url")
                st.file_uploader("📷 Enviar Foto Principal", type=["png", "jpg", "jpeg"], key="cad_foto")
                codigo_barras = st.text_input("Código de Barras (Pai/Simples)", value=st.session_state.get("codigo_barras", ""), key="cad_cb")
                foto_codigo = st.camera_input("📷 Escanear código de barras / QR Code", key="cad_cam")
                if foto_codigo is not None:
                    codigos_lidos = ler_codigo_barras_api(foto_codigo.getbuffer())
                    if codigos_lidos:
                        st.session_state["codigo_barras"] = codigos_lidos[0]
                        st.success(f"Código lido: **{st.session_state['codigo_barras']}**")
                        st.rerun()
                    else:
                        st.error("❌ Não foi possível ler nenhum código.")
                foto_codigo_upload = st.file_uploader("📤 Upload de imagem do código de barras", type=["png", "jpg", "jpeg"], key="cad_cb_upload")
                if foto_codigo_upload is not None:
                    codigos_lidos = ler_codigo_barras_api(foto_codigo_upload.getvalue())
                    if codigos_lidos:
                        st.session_state["codigo_barras"] = codigos_lidos[0]
                        st.success(f"Código lido via upload: **{st.session_state['codigo_barras']}**")
                        st.rerun()
                    else:
                        st.error("❌ Não foi possível ler nenhum código da imagem enviada.")

            variações = []
            if tipo_produto == "Produto com variações (grade)":
                st.markdown("#### Cadastro das variações (grade)")
                qtd_variações = st.number_input("Quantas variações deseja cadastrar?", min_value=1, step=1, key="cad_qtd_variações")
                campos_grade = get_campos_grade(categoria)
                for i in range(int(qtd_variações)):
                    st.markdown(f"--- **Variação {i+1}** ---")
                    var_c1, var_c2, var_c3, var_c4 = st.columns(4)
                    var_nome = var_c1.text_input(f"Nome da variação {i+1}", key=f"var_nome_{i}")
                    var_qtd = var_c2.number_input(f"Quantidade variação {i+1}", min_value=0, step=1, value=0, key=f"var_qtd_{i}")
                    with var_c3:
                        var_preco_custo = st.text_input(f"Preço de Custo variação {i+1}", value="0,00", key=f"var_pc_{i}")
                    with var_c4:
                        var_preco_vista = st.text_input(f"Preço à Vista variação {i+1}", value="0,00", key=f"var_pv_{i}")
                    var_foto_url = st.text_input(f"URL Foto Variação {i+1} (Opcional)", key=f"var_foto_url_{i}")
                    st.markdown("##### Código de Barras e Cashback")
                    var_cb_c1, var_cb_c2, var_cb_c3, var_cb_c4 = st.columns([2, 1, 1, 1.5])
                    with var_cb_c1:
                        var_codigo_barras = st.text_input(f"Código de barras variação {i+1}", value=st.session_state.cb_grade_lidos.get(f"var_cb_{i}", ""), key=f"var_cb_{i}")
                    with var_cb_c2:
                        var_foto_upload = st.file_uploader("Upload CB", type=["png", "jpg", "jpeg"], key=f"var_cb_upload_{i}")
                    with var_cb_c3:
                        var_foto_cam = st.camera_input("Escanear CB", key=f"var_cb_cam_{i}")
                    with var_cb_c4:
                        var_cashback_percent = 0.0
                        var_oferece_cashback = st.checkbox(f"Cashback? {i+1}", key=f"var_cbk_chk_{i}")
                        if var_oferece_cashback:
                            var_cashback_percent = st.number_input(f"Cashback % {i+1}", min_value=0.0, max_value=100.0, value=3.0, step=0.5, key=f"var_cbk_percent_{i}")

                    var_detalhes = {}
                    if campos_grade:
                        st.markdown("##### Detalhes da Variação (Cor/Tamanho)")
                        is_calçado = any(k in categoria.lower() for k in ["calçado", "chinelo"])

                        if is_calçado:
                            tipo_numeração = st.radio("Tipo de Numeração", ["Única", "Dupla"], key=f"var_tipo_num_{i}", horizontal=True)
                            c_det1, c_det2 = st.columns(2)
                            var_detalhes["Cor"] = c_det1.text_input("Cor", key=f"var_det_cor_{i}")
                            with c_det2:
                                if tipo_numeração == "Única":
                                    num_unica = st.number_input("Numeração", min_value=1, step=1, value=38, key=f"var_det_num_unica_{i}")
                                    var_detalhes["Tamanho/Numeração"] = num_unica
                                else:
                                    num_c1, num_c2 = st.columns(2)
                                    num1 = num_c1.number_input("De", min_value=1, step=1, value=35, key=f"var_det_num1_{i}")
                                    num2 = num_c2.number_input("Até", min_value=1, step=1, value=36, key=f"var_det_num2_{i}")
                                    var_detalhes["Tamanho/Numeração"] = f"{int(num1)}/{int(num2)}"
                        else:
                            cols_add = st.columns(len(campos_grade))
                            col_idx = 0
                            for label, config in campos_grade.items():
                                key_detalhe = f"var_det_{label.replace(' ', '_')}_{i}"
                                if config["type"] == "text":
                                    valor = cols_add[col_idx].text_input(label, help=config.get("help"), key=key_detalhe)
                                elif config["type"] == "number":
                                    valor = cols_add[col_idx].number_input(label, min_value=config.get("min_value", 0), step=config.get("step", 1), value=config.get("value", 0), help=config.get("help"), key=key_detalhe)
                                elif config["type"] == "selectbox":
                                    index = 0 if config.get("options", [""])[0] == "" else None
                                    valor = cols_add[col_idx].selectbox(label, config.get("options", []), index=index, help=config.get("help"), key=key_detalhe)
                                var_detalhes[label] = valor
                                col_idx += 1

                    foto_lida = var_foto_upload or var_foto_cam
                    if foto_lida:
                        imagem_bytes = foto_lida.getvalue() if var_foto_upload else foto_lida.getbuffer()
                        codigos_lidos = ler_codigo_barras_api(imagem_bytes)
                        if codigos_lidos:
                            st.session_state.cb_grade_lidos[f"var_cb_{i}"] = codigos_lidos[0]
                            st.success(f"CB Variação {i+1} lido: **{codigos_lidos[0]}**")
                            st.rerun()
                        else:
                            st.error("❌ Não foi possível ler nenhum código.")
                    variações.append({"Nome": var_nome.strip(), "Quantidade": int(var_qtd), "PrecoCusto": to_float(var_preco_custo), "PrecoVista": to_float(var_preco_vista), "PrecoCartao": round(to_float(var_preco_vista) / FATOR_CARTAO, 2) if to_float(var_preco_vista) > 0 else 0.0, "CodigoBarras": var_codigo_barras, "CashbackPercent": var_cashback_percent, "FotoURL": var_foto_url.strip(), "DetalhesGrade": var_detalhes})

            # CHAMADA DA FUNÇÃO DE SALVAR ATUALIZADA COM O NOVO PARÂMETRO
            if st.button("💾 Salvar", use_container_width=True, key="cad_salvar", on_click=lambda: st.rerun() if callback_salvar_novo_produto(produtos.copy(), tipo_produto, nome, marca, categoria, qtd, preco_custo, preco_vista, validade, foto_url, codigo_barras, variações, cashback_percent, descricao_longa) else None, help="Salvar Novo Produto Completo"):
                st.rerun()

    with tab_lista:
        st.subheader("📑 Lista & Busca de Produtos")
        with st.expander("🔍 Pesquisar produto", expanded=True):
            criterio = st.selectbox("Pesquisar por:", ["Nome", "Marca", "Código de Barras", "Valor", "Detalhe de Grade (Cor, Tamanho, etc.)"])
            termo = st.text_input("Digite para buscar:")
            produtos_filtrados = produtos.copy()
            if termo:
                termo_lower = termo.lower().strip()
                if criterio == "Nome":
                    produtos_filtrados = produtos[produtos["Nome"].astype(str).str.contains(termo, case=False, na=False)]
                elif criterio == "Marca":
                    produtos_filtrados = produtos[produtos["Marca"].astype(str).str.contains(termo, case=False, na=False)]
                elif criterio == "Código de Barras":
                    produtos_filtrados = produtos[produtos["CodigoBarras"].astype(str).str.contains(termo, case=False, na=False)]
                elif criterio == "Valor":
                    try:
                        valor = float(termo.replace(",", "."))
                        produtos_filtrados = produtos[(pd.to_numeric(produtos["PrecoVista"], errors='coerce').fillna(0) == valor) | (pd.to_numeric(produtos["PrecoCusto"], errors='coerce').fillna(0) == valor) | (pd.to_numeric(produtos["PrecoCartao"], errors='coerce').fillna(0) == valor)]
                    except:
                        st.warning("Digite um número válido para buscar por valor.")
                        produtos_filtrados = produtos.copy()
                elif criterio == "Detalhe de Grade (Cor, Tamanho, etc.)":
                    def search_details(details_json):
                        if pd.isna(details_json) or not details_json: return False
                        try:
                            details = ast.literal_eval(details_json) if isinstance(details_json, str) else details_json
                            return any(termo_lower in str(v).lower() for v in details.values()) if isinstance(details, dict) else False
                        except: return False
                    produtos_filtrados = produtos[produtos["DetalhesGrade"].apply(search_details)]
            if "PaiID" not in produtos_filtrados.columns: produtos_filtrados["PaiID"] = None
            if "CashbackPercent" not in produtos_filtrados.columns: produtos_filtrados["CashbackPercent"] = 0.0
            if "DetalhesGrade" not in produtos_filtrados.columns: produtos_filtrados["DetalhesGrade"] = "{}"
            # GARANTE QUE A NOVA COLUNA ESTEJA NO DATAFRAME FILTRADO
            if "DescricaoLonga" not in produtos_filtrados.columns: produtos_filtrados["DescricaoLonga"] = ""


        st.markdown("### Lista de produtos")
        if produtos_filtrados.empty:
            st.info("Nenhum produto encontrado.")
        else:
            st.markdown("""<style>.custom-header, .custom-row {display: grid; grid-template-columns: 80px 3fr 1fr 1fr 1.5fr 1fr 1.5fr 0.5fr 0.5fr; align-items: center; gap: 5px;} .custom-header {font-weight: bold; padding: 8px 0; border-bottom: 1px solid #ccc; margin-bottom: 5px;} .custom-price-block {line-height: 1.2;}</style><div class="custom-header"><div>Foto</div><div>Produto & Marca</div><div>Estoque</div><div>Validade</div><div>Preços (C/V/C)</div><div>Cashback</div><div>Detalhes</div><div style="grid-column: span 2;">Ações</div></div>""", unsafe_allow_html=True)
            produtos_filtrados["Quantidade"] = pd.to_numeric(produtos_filtrados["Quantidade"], errors='coerce').fillna(0).astype(int)
            produtos_pai = produtos_filtrados[produtos_filtrados["PaiID"].isnull() | (produtos_filtrados["PaiID"] == '')]
            produtos_filho = produtos_filtrados[produtos_filtrados["PaiID"].notnull() & (produtos_filtrados["PaiID"] != '')]

            def format_details(details_json):
                if pd.isna(details_json) or not details_json: return "—"
                try:
                    details = ast.literal_eval(details_json) if isinstance(details_json, str) else details_json
                    return "<br>".join([f"**{k.split('/')[0][:1]}:** {v}" for k, v in details.items() if v]) if isinstance(details, dict) else "—"
                except: return "—"

            for index, pai in produtos_pai.iterrows():
                with st.container(border=True):
                    c = st.columns([1, 3, 1, 1, 1.5, 1, 1.5, 0.5, 0.5])
                    foto_url_pai = str(pai["FotoURL"]).strip()
                    if foto_url_pai:
                        try: c[0].image(foto_url_pai, width=60)
                        except Exception: c[0].write("—")
                    else: c[0].write("—")
                    c[1].markdown(f"**{pai['Nome']}**<br><small>Marca: {pai['Marca']} | Cat: {pai['Categoria']}</small>", unsafe_allow_html=True)
                    estoque_total = pai['Quantidade']
                    filhos_do_pai = produtos_filho[produtos_filho["PaiID"] == str(pai["ID"])]
                    if not filhos_do_pai.empty: estoque_total = filhos_do_pai['Quantidade'].sum()
                    c[2].markdown(f"**{estoque_total}**")

                    validade_formatada = str(pai['Validade']) if pd.notna(pai['Validade']) else "—"
                    c[3].write(validade_formatada)

                    pv = to_float(pai['PrecoVista'])
                    pc_calc = round(pv / FATOR_CARTAO, 2)
                    c[4].markdown(f'<div class="custom-price-block"><small>C: R$ {to_float(pai["PrecoCusto"]):,.2f}</small><br>**V:** R$ {pv:,.2f}<br>**C:** R$ {pc_calc:,.2f}</div>', unsafe_allow_html=True)
                    cashback_pai = to_float(pai.get('CashbackPercent', 0.0))
                    if cashback_pai > 0:
                        valor_cashback = pv * (cashback_pai / 100)
                        c[5].markdown(f'**{cashback_pai:.1f}%**<br><small>R$ {f"{valor_cashback:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")}</small>', unsafe_allow_html=True)
                    else: c[5].write("—")
                    c[6].markdown(format_details(pai.get('DetalhesGrade', None)), unsafe_allow_html=True)
                    eid = str(pai["ID"])
                    if c[7].button("✏️", key=f"edit_pai_{index}_{eid}", help="Editar produto"): st.session_state["edit_prod"] = eid; st.rerun()
                    if c[8].button("🗑️", key=f"del_pai_{index}_{eid}", help="Excluir produto"):
                        products = produtos[(produtos["ID"] != eid) & (produtos["PaiID"] != eid)]
                        st.session_state["produtos"] = products
                        if salvar_produtos_no_github(products, f"Exclusão do produto pai {pai.get('Nome', 'Desconhecido')}"): inicializar_produtos.clear()
                        st.rerun()
                    if not filhos_do_pai.empty:
                        with st.expander(f"Variações de {pai['Nome']} ({len(filhos_do_pai)} variações)"):
                            for index_var, var in filhos_do_pai.iterrows():
                                c_var = st.columns([1, 3, 1, 1, 1.5, 1, 1.5, 0.5, 0.5])
                                foto_url_var = str(var.get("FotoURL", "")).strip() or foto_url_pai
                                if foto_url_var:
                                    try: c_var[0].image(foto_url_var, width=60)
                                    except Exception: c_var[0].write("—")
                                else: c_var[0].write("—")
                                c_var[1].markdown(f"**{var['Nome']}**<br><small>Marca: {var['Marca']} | Cat: {var['Categoria']}</small>", unsafe_allow_html=True)
                                c_var[2].write(f"{var['Quantidade']}")
                                c_var[3].write(validade_formatada)
                                pv_var = to_float(var['PrecoVista'])
                                pc_var_calc = round(pv_var / FATOR_CARTAO, 2)
                                c_var[4].markdown(f'<div class="custom-price-block"><small>C: R$ {to_float(var["PrecoCusto"]):,.2f}</small><br>**V:** R$ {pv_var:,.2f}<br>**C:** R$ {pc_var_calc:,.2f}</div>', unsafe_allow_html=True)
                                cashback_var = to_float(var.get('CashbackPercent', 0.0))
                                if cashback_var > 0:
                                    valor_cashback_var = pv_var * (cashback_var / 100)
                                    c_var[5].markdown(f'**{cashback_var:.1f}%**<br><small>R$ {f"{valor_cashback_var:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")}</small>', unsafe_allow_html=True)
                                else: c_var[5].write("—")
                                c_var[6].markdown(format_details(var.get('DetalhesGrade', None)), unsafe_allow_html=True)
                                eid_var = str(var["ID"])
                                if c_var[7].button("✏️", key=f"edit_filho_{index_var}_{eid_var}", help="Editar variação"): st.session_state["edit_prod"] = eid_var; st.rerun()
                                if c_var[8].button("🗑️", key=f"del_filho_{index_var}_{eid_var}", help="Excluir variação"):
                                    products = produtos[produtos["ID"] != eid_var]
                                    st.session_state["produtos"] = products
                                    if salvar_produtos_no_github(products, f"Exclusão da variação {var.get('Nome', 'Desconhecida')}"): inicializar_produtos.clear()
                                    st.rerun()

            if "edit_prod" in st.session_state:
                eid = st.session_state["edit_prod"]
                row_df = produtos[produtos["ID"] == str(eid)]
                if not row_df.empty:
                    row = row_df.iloc[0]
                    st.subheader(f"Editar produto ID: {eid} ({row['Nome']})")
                    current_details_grade = {}
                    try:
                        details_str = row.get("DetalhesGrade", "{}")
                        if pd.notna(details_str) and isinstance(details_str, str):
                            current_details_grade = ast.literal_eval(details_str)
                        elif isinstance(details_str, dict):
                            current_details_grade = details_str
                    except:
                        pass # Mantém current_details_grade como {}

                    c1, c2, c3 = st.columns(3)
                    with c1:
                        novo_nome = st.text_input("Nome", value=row["Nome"], key=f"edit_nome_{eid}")
                        nova_marca = st.text_input("Marca", value=row["Marca"], key=f"edit_marca_{eid}")
                        nova_cat = st.text_input("Categoria", value=row["Categoria"], key=f"edit_cat_{eid}")
                        # NOVO CAMPO DE DESCRIÇÃO LONGA NA EDIÇÃO
                        nova_descricao_longa = st.text_area("Descrição Detalhada", value=row.get("DescricaoLonga", ""), help="Descrição completa do produto.", key=f"edit_descricao_longa_{eid}")
                    with c2:
                        nova_qtd = st.number_input("Quantidade", min_value=0, step=1, value=int(row["Quantidade"]), key=f"edit_qtd_{eid}")
                        novo_preco_custo = st.text_input("Preço de Custo", value=f"{to_float(row['PrecoCusto']):.2f}".replace(".", ","), key=f"edit_pc_{eid}")
                        novo_preco_vista = st.text_input("Preço à Vista", value=f"{to_float(row['PrecoVista']):.2f}".replace(".", ","), key=f"edit_pv_{eid}")
                    with c3:
                        produto_tem_validade = pd.notna(row["Validade"])
                        edit_tem_validade = st.checkbox("Produto com data de validade?", value=produto_tem_validade, key=f"edit_tem_validade_{eid}")
                        nova_validade = pd.NaT
                        if edit_tem_validade:
                            data_padrao = row["Validade"] if produto_tem_validade else date.today()
                            nova_validade = st.date_input("Data de Validade", value=data_padrao, key=f"edit_val_{eid}")
                        nova_foto = st.text_input("URL da Foto", value=row.get("FotoURL", ""), key=f"edit_foto_{eid}")
                        novo_cb = st.text_input("Código de Barras", value=str(row.get("CodigoBarras", "")), key=f"edit_cb_{eid}")

                        # --- CÓDIGO NOVO PARA O MODO TURBO ---
                        # Garante que a coluna PromocaoEspecial exista para a leitura
                        if "PromocaoEspecial" not in row:
                            row["PromocaoEspecial"] = "NAO" # Valor padrão se a coluna não existir

                        valor_atual_turbo = str(row.get("PromocaoEspecial", "NAO")).strip().upper() == "SIM"
                        
                        novo_status_turbo = st.toggle(
                            "🚀 Ativar Modo Turbo", 
                            value=valor_atual_turbo, 
                            key=f"edit_turbo_{eid}",
                            help="Produtos no modo Turbo dão mais cashback para clientes Ouro (7%) e Diamante (15%)."
                        )

                    st.markdown("##### Detalhes da Grade e Cashback")
                    col_details, col_cashback = st.columns([2, 1])
                    edited_details = current_details_grade.copy()
                    with col_details:
                        is_calçado_edit = any(k in nova_cat.lower() for k in ["calçado", "chinelo"])
                        if is_calçado_edit:
                            st.markdown("Detalhes da Grade:")
                            current_num = current_details_grade.get("Tamanho/Numeração", "")
                            is_dupla_inicial = isinstance(current_num, str) and "/" in current_num

                            tipo_numeração_edit = st.radio("Tipo de Numeração", ["Única", "Dupla"], index=1 if is_dupla_inicial else 0, key=f"edit_tipo_num_{eid}", horizontal=True)

                            c_edit1, c_edit2 = st.columns(2)
                            edited_details["Cor"] = c_edit1.text_input("Cor", value=current_details_grade.get("Cor", ""), key=f"edit_det_cor_{eid}")
                            with c_edit2:
                                if tipo_numeração_edit == "Única":
                                    default_val = int(current_num) if not is_dupla_inicial and str(current_num).isdigit() else 38
                                    num_unica = st.number_input("Numeração", min_value=1, step=1, value=default_val, key=f"edit_det_num_unica_{eid}")
                                    edited_details["Tamanho/Numeração"] = num_unica
                                else:
                                    num1_val, num2_val = (str(current_num).split('/')) if is_dupla_inicial else (35, 36)
                                    num_c1, num_c2 = st.columns(2)
                                    num1 = num_c1.number_input("De", min_value=1, step=1, value=int(num1_val), key=f"edit_det_num1_{eid}")
                                    num2 = num_c2.number_input("Até", min_value=1, step=1, value=int(num2_val), key=f"edit_det_num2_{eid}")
                                    edited_details["Tamanho/Numeração"] = f"{int(num1)}/{int(num2)}"
                        else:
                            st.info("Nenhum detalhe de grade para esta categoria.")
                    with col_cashback:
                        st.markdown("Cashback:")
                        current_cashback = to_float(row.get("CashbackPercent", 0.0))
                        edit_oferece_cashback = st.checkbox("Oferece Cashback?", value=(current_cashback > 0), key=f"edit_cbk_chk_{eid}")
                        novo_cashback_percent = 0.0
                        if edit_oferece_cashback:
                            novo_cashback_percent = st.number_input("Cashback (%)", min_value=0.0, max_value=100.0, value=current_cashback if current_cashback > 0 else 3.0, step=0.5, key=f"edit_cbk_val_{eid}")

                    _, col_save, col_cancel = st.columns([3, 1.5, 1.5])
                    if col_save.button("💾 Salvar", key=f"save_{eid}", type="primary", use_container_width=True):
                        preco_vista_float = to_float(novo_preco_vista)
                        
                        # Converte o status do toggle (True/False) para o texto ("SIM"/"NAO") a ser salvo
                        valor_turbo_para_salvar = "SIM" if novo_status_turbo else "NAO"

                        # Adicione "PromocaoEspecial" à lista de colunas e o valor_turbo_para_salvar à lista de valores
                        produtos.loc[produtos["ID"] == str(eid), 
                                     ["Nome", "Marca", "Categoria", "Quantidade", "PrecoCusto", 
                                      "PrecoVista", "PrecoCartao", "Validade", "FotoURL", 
                                      "CodigoBarras", "CashbackPercent", "DetalhesGrade", 
                                      "DescricaoLonga", "PromocaoEspecial" # <- COLUNA ADICIONADA
                                      ]] = [
                                          novo_nome.strip(), nova_marca.strip(), nova_cat.strip(), int(nova_qtd),
                                          to_float(novo_preco_custo), preco_vista_float, round(preco_vista_float / FATOR_CARTAO, 2),
                                          nova_validade, nova_foto.strip(), str(novo_cb).strip(), novo_cashback_percent,
                                          str(edited_details), nova_descricao_longa.strip(),
                                          valor_turbo_para_salvar # <- VALOR ADICIONADO
                                          ]

                        st.session_state["produtos"] = produtos
                        if salvar_produtos_no_github(produtos, "Atualizando produto"): inicializar_produtos.clear()
                        del st.session_state["edit_prod"]
                        st.rerun()

    with tab_relatorio:
        relatorio_produtos()

