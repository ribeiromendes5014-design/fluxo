# test_app.py
import streamlit as st

st.set_page_config(layout="wide")
st.title("🔬 Teste de Importação Mínimo")

st.info("Este app tenta importar uma função simples do arquivo test_utils.py.")

try:
    from utils import inicializar_produtos # Testando a importação do seu arquivo real
    st.success("✅ SUCESSO ao importar do `utils.py` real!")

    from test_utils import uma_funcao_simples
    st.success("✅ SUCESSO ao importar do `test_utils.py`!")
    st.write(f"Resultado da função de teste: **{uma_funcao_simples()}**")

except ImportError as e:
    st.error("❌ FALHA NA IMPORTAÇÃO!")
    st.write("Ocorreu um `ImportError`. Isso significa que o problema está na forma como os módulos são carregados.")
    
    # Esta linha vai imprimir o erro completo e sem censura na tela
    st.exception(e)
except Exception as e:
    st.error("❌ FALHA! Ocorreu um erro diferente durante a importação.")
    st.exception(e)