import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import re
import sys, os 
# ----------------------------------------------------------------------------------
# 1. Ajuste de caminho para encontrar 'utils.py' na raiz
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
# ----------------------------------------------------------------------------------

# ✅ CORREÇÃO: Importa TUDO de uma única fonte (utils.py)
from utils import (
    # Funções de Contatos (CRM)
    carregar_contatos_marketing, 
    salvar_contatos_marketing,
    validar_contato, 

    # Funções de Agenda (CMS)
    # Assumindo que você as adicionou ao utils.py:
    carregar_agenda_marketing,
    salvar_agenda_marketing,

    # Outras Funções Auxiliares 
    prox_id # Puxa o prox_id do utils.py
) 

# ==============================================================================
# SUBABA: GESTÃO DE CONTATOS (REUTILIZAÇÃO E CADASTRO MANUAL)
# ==============================================================================

def gestao_contatos_subaba():
    st.subheader("👥 Gestão de Contatos de Marketing")
    
    # --- FORMULÁRIO DE CADASTRO MANUAL ---
    with st.expander("➕ Adicionar Contato Manualmente", expanded=False):
        with st.form("form_cadastro_manual"):
            col_nome, col_contato = st.columns(2)
            
            nome_manual = col_nome.text_input("👤 Nome", key="input_nome_manual")
            contato_manual = col_contato.text_input("📞 WhatsApp (DDD + Número)", key="input_contato_manual", help="Apenas números, Ex: 41991234567")
            
            # REMOVEMOS A DEFINIÇÃO LOCAL DE validar_contato, USANDO A IMPORTADA
            enviar_manual = st.form_submit_button("💾 Adicionar Contato e Ativar Opt-In")
            
            if enviar_manual:
                # 1. VALIDAÇÃO USANDO A FUNÇÃO IMPORTADA DE utils.py
                contato_limpo = validar_contato(contato_manual) 
                
                # ... (o restante da lógica de validação e salvamento permanece a mesma) ...
                if len(contato_limpo) < 12:
                    st.error("❌ Contato inválido. Use o DDD + Número (Ex: 41991234567).")
                    return
                if not nome_manual.strip():
                    st.error("❌ O nome é obrigatório.")
                    return

                # --- Lógica de Salvamento (reutiliza o handler importado) ---
                df_contatos = carregar_contatos_marketing()
                
                # Garante que as colunas existam
                for col in ["Nome", "Contato", "DataCadastro", "OPT_IN_PROMO"]:
                    if col not in df_contatos.columns:
                        df_contatos[col] = ""

                contato_existe = df_contatos['Contato'].astype(str).str.contains(contato_limpo).any()
                
                if contato_existe:
                    df_contatos.loc[df_contatos['Contato'].astype(str).str.contains(contato_limpo), 'OPT_IN_PROMO'] = True
                    df_contatos.loc[df_contatos['Contato'].astype(str).str.contains(contato_limpo), 'Nome'] = nome_manual.strip()
                    st.info(f"🎉 Contato {nome_manual.strip()} já existia. Opt-In reativado.")
                else:
                    nova_linha = {
                        "Nome": nome_manual.strip(),
                        "Contato": contato_limpo,
                        "DataCadastro": date.today().isoformat(),
                        "OPT_IN_PROMO": True
                    }
                    df_contatos = pd.concat([df_contatos, pd.DataFrame([nova_linha])], ignore_index=True)
                    st.success(f"✅ Contato {nome_manual.strip()} adicionado à lista VIP.")

                # 2. SALVA NO GITHUB USANDO A FUNÇÃO IMPORTADA
                salvar_contatos_marketing(df_contatos, f"Cadastro manual de contato: {nome_manual.strip()}")
                st.rerun() # Reinicia para atualizar a tabela

    st.markdown("---")
    
    # --- VISUALIZAÇÃO DOS CONTATOS ---
    st.subheader("Lista Completa de Contatos VIP")
    # 3. CARREGA OS DADOS PARA EXIBIÇÃO USANDO A FUNÇÃO IMPORTADA
    df_contatos_display = carregar_contatos_marketing()
    
    if df_contatos_display.empty:
        st.info("Nenhum contato cadastrado ainda.")
        return
        
    df_ativos = df_contatos_display[df_contatos_display['OPT_IN_PROMO'].astype(bool)].copy()
    df_inativos = df_contatos_display[~df_contatos_display['OPT_IN_PROMO'].astype(bool)].copy()

    st.metric(
        label="Total de Contatos Ativos para Envio", 
        value=len(df_ativos),
        delta=f"Inativos: {len(df_inativos)}",
        delta_color="inverse"
    )
    
    st.dataframe(
        df_ativos.sort_values(by="DataCadastro", ascending=False),
        use_container_width=True,
        column_config={
            "OPT_IN_PROMO": st.column_config.CheckboxColumn("Opt-In Ativo")
        },
        height=300
    )

# ==============================================================================
# FUNÇÃO PRINCIPAL: GESTÃO DE MARKETING
# ==============================================================================

def gestao_marketing():
    st.title("📢 Central de Marketing e Disparo WhatsApp")
    
    # --- Tabs de Navegação ---
    tab_cms, tab_crm = st.tabs(["🗓️ Agendamento de Promoções (CMS)", "👥 Gestão de Contatos VIP"])

    # ==============================================================================
    # ABA 1: CMS - AGENDAMENTO DE MENSAGENS E PROGRAMAÇÃO
    # ==============================================================================
    with tab_cms:
        st.subheader("Agendar Nova Campanha de WhatsApp")
        
        df_agenda = carregar_agenda_marketing()
        
        with st.form("form_agendamento_promo"):
            
            # --- Configurações da Mensagem ---
            st.markdown("#### Configuração e Agendamento")
            col_data, col_template = st.columns(2)
            
            data_envio = col_data.date_input("🗓️ Data do Envio", min_value=date.today(), key="input_data_envio")
            
            # Usar o nome do template que foi aprovado na Meta
            template_nome = col_template.selectbox(
                "🏷️ Template do WhatsApp", 
                options=["promocao_com_midia", "black_friday_oferta"], # Substitua pelos seus nomes reais
                key="input_template_nome"
            )
            
            # URL da Foto (Cabeçalho de Mídia)
            foto_url = st.text_input("🔗 URL da Foto (Cabeçalho da Mensagem)", key="input_foto_url", help="Cole a URL da imagem para o cabeçalho.")
            
            st.markdown("#### Conteúdo Variável (Preenchimento do Template)")
            
            texto_var1 = st.text_input("📝 Texto Variável 1 ({{1}} - Ex: Saudação/Oferta)", key="input_var1")
            texto_var2 = st.text_area("📝 Texto Variável 2 ({{2}} - Ex: Detalhes da Promoção/Link)", key="input_var2")
            
            # --- Prévia da Mensagem ---
            st.markdown("---")
            st.markdown("#### Prévia da Mensagem (Estilo WhatsApp)")
            
            if foto_url:
                st.image(foto_url, caption="Prévia do Cabeçalho de Mídia", width=250)
            
            st.markdown(f"""
                <div style="background-color: #DCF8C6; padding: 10px; border-radius: 10px; max-width: 400px; margin-left: 10px;">
                    **[Cabeçalho da Imagem]**
                    <p style='margin-top: 5px;'>Olá, {'{Cliente}'}! {texto_var1.strip()}</p>
                    <p>{texto_var2.strip()}</p>
                    <p style='font-size: 0.8em; color: gray;'>[Botão: Ver Oferta]</p>
                </div>
            """, unsafe_allow_html=True)
            
            st.markdown("---")
            
            agendar = st.form_submit_button("✅ AGENDAR CAMPANHA", type="primary")

            if agendar:
                if not texto_var1.strip() or not foto_url.strip():
                    st.error("❌ Preencha o Texto Variável 1 e a URL da Foto.")
                    return
                
                # --- Lógica de Salvamento da Agenda ---
                novo_id = prox_id(df_agenda, "ID_PROMO")
                
                nova_promocao = {
                    "ID_PROMO": novo_id,
                    "DATA_ENVIO": data_envio.isoformat(),
                    "TEMPLATE_NOME": template_nome,
                    "FOTO_URL": foto_url.strip(),
                    "TEXTO_VAR1": texto_var1.strip(),
                    "TEXTO_VAR2": texto_var2.strip(),
                    "STATUS": "PENDENTE"
                }
                
                df_agenda_upd = pd.concat([df_agenda, pd.DataFrame([nova_promocao])], ignore_index=True)
                
                if salvar_agenda_marketing(df_agenda_upd, f"Agendamento de Campanha ID {novo_id} para {data_envio}"):
                    st.success(f"🎉 Campanha agendada com sucesso para {data_envio.strftime('%d/%m/%Y')}!")
                    st.rerun()
                else:
                    st.error("❌ Falha ao salvar a agenda no GitHub.")


        st.markdown("---")
        st.subheader("Agenda de Campanhas (PENDENTES)")
        
        # Exibir a agenda (apenas pendentes)
        df_agenda['DATA_ENVIO_DT'] = pd.to_datetime(df_agenda['DATA_ENVIO'], errors='coerce').dt.date
        df_pendentes = df_agenda[
            (df_agenda['STATUS'] == 'PENDENTE') & 
            (df_agenda['DATA_ENVIO_DT'] >= date.today())
        ].sort_values(by="DATA_ENVIO_DT", ascending=True)

        if df_pendentes.empty:
            st.info("Nenhuma campanha de marketing pendente. Agende uma!")
        else:
            st.dataframe(
                df_pendentes[['ID_PROMO', 'DATA_ENVIO_DT', 'TEXTO_VAR1', 'TEMPLATE_NOME', 'STATUS']],
                use_container_width=True,
                column_config={"DATA_ENVIO_DT": st.column_config.DateColumn("Data de Envio"), "TEXTO_VAR1": "Conteúdo Principal"}
            )
            
            st.caption("Essas campanhas serão disparadas automaticamente pelo Cron Job do Render na data programada.")


    # ==============================================================================
    # ABA 2: CRM - GESTÃO DE CONTATOS VIP
    # ==============================================================================
    with tab_crm:
        gestao_contatos_subaba()


if __name__ == "__main__":

    gestao_marketing()


