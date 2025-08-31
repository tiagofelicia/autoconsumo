import streamlit as st
import pandas as pd
import datetime
import io
import time
import graficos as gfx
import processamento_dados as proc_dados
import calculos as calc
import constantes as C
import math
import exportacao

from streamlit_folium import st_folium
import folium

from st_aggrid import AgGrid, GridOptionsBuilder
from st_aggrid.shared import GridUpdateMode, JsCode
from bs4 import BeautifulSoup # Para processar o resumo HTML
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill # Para formatação Excel
from openpyxl.utils import get_column_letter # Para nomes de colunas Excel
from calendar import monthrange

st.set_page_config(page_title="Simulador de Autoconsumo Solar - Portugal", layout="wide",initial_sidebar_state="collapsed")

# --- Carregar ficheiro Excel do GitHub ---
url_excel = "https://github.com/tiagofelicia/autoconsumo/raw/refs/heads/main/TiagoFelicia_Simulador_Autoconsumo.xlsx"
OMIE_CICLOS, CONSTANTES = proc_dados.carregar_dados_excel(url_excel)


def atualizar_distrito_pelas_coords():
    """
    Encontra o distrito mais próximo das coordenadas atuais e atualiza o seletor.
    """
    lat_atual = st.session_state.solar_latitude
    lon_atual = st.session_state.solar_longitude
    
    distrito_mais_proximo = None
    menor_distancia = float('inf')

    for distrito, (lat_distrito, lon_distrito) in C.COORDENADAS_DISTRITOS.items():
        distancia = math.sqrt((lat_atual - lat_distrito)**2 + (lon_atual - lon_distrito)**2)
        if distancia < menor_distancia:
            menor_distancia = distancia
            distrito_mais_proximo = distrito
    
    if distrito_mais_proximo and st.session_state.distrito_selecionado != distrito_mais_proximo:
        st.session_state.distrito_selecionado = distrito_mais_proximo

def handle_coord_change():
    """
    Função chamada quando as coordenadas são alteradas.
    Define uma flag temporária para indicar que a última ação foi uma mudança de coordenadas,
    e depois chama a função para atualizar o distrito.
    """
    st.session_state['_coord_just_changed'] = True
    atualizar_distrito_pelas_coords()

def atualizar_coords_pelo_distrito():
    """
    Atualiza as coordenadas para os valores de backup do distrito selecionado,
    mas só se o distrito mudou em relação ao anterior. 
    Se apenas se alteraram coordenadas dentro do mesmo distrito, mantém as coords.
    """
    if st.session_state.get('_coord_just_changed', False):
        # Limpa a flag depois de usada
        st.session_state['_coord_just_changed'] = False
        return

    distrito = st.session_state.distrito_selecionado
    ultimo_distrito = st.session_state.get('_ultimo_distrito', None)

    # Só atualizar coordenadas se o distrito mudou realmente
    if distrito != ultimo_distrito and distrito in C.COORDENADAS_DISTRITOS:
        lat, lon = C.COORDENADAS_DISTRITOS[distrito]
        st.session_state.solar_latitude = lat
        st.session_state.solar_longitude = lon

    # Atualiza o "último distrito" para a próxima vez
    st.session_state['_ultimo_distrito'] = distrito


def formatar_numero_pt(numero, casas_decimais=2, sufixo=""):
    """Formata um número para o padrão português (ex: 1 234,56)."""
    try:
        # Primeiro, formata com um ponto decimal e vírgula para milhares (padrão US)
        # Depois, substitui a vírgula por um espaço e o ponto por uma vírgula.
        formatado = f"{numero:,.{casas_decimais}f}".replace(",", " ").replace(".", ",")
        return f"{formatado}{sufixo}"
    except (ValueError, TypeError):
        return f"-{sufixo}"


def inicializar_estado():
    """Define os valores iniciais para o st.session_state se ainda não existirem."""
    # Dicionário de valores padrão para inicializar
    valores_padrao = {
        # Tarifário
        'sel_potencia': 3.45, 'sel_opcao_horaria': "Simples",
        # Simulação Solar
        'solar_potencia': 2.0, 'solar_latitude': 40.5374, 'solar_longitude': -7.0367,
        'solar_inclinacao': 35, 'solar_orientacao_graus': 0, 'solar_loss': 14,
        'solar_montagem': "Instalação livre (free-standing)", 'distrito_selecionado': 'Guarda',
        # Simulação Bateria
        'bat_capacidade': 5.0, 'bat_potencia': 2.5, 'bat_dod': 80, 'bat_eficiencia': 90,
        # Controlo de estado
        'cenarios_guardados': [], 'calculo_executado': False,    
        # --- CHAVES PARA GUARDAR O ÚLTIMO ESTADO CALCULADO ---
        'last_calculated_latitude': None, 'last_calculated_longitude': None,
        'last_calculated_potencia': None, 'last_calculated_inclinacao': None,
        'last_calculated_orientacao': None, 'last_calculated_loss': None,
        'last_calculated_montagem': None, 'last_calculated_solar_sombra': None,
        'solar_sombra': 0, 'num_anos_analise': 25, 'slider_degradacao': 0.5,
        'slider_inflacao_energia': 3.0, 'slider_variacao_venda': 0.0,
        '_ultimo_distrito': None
    }

    # Itera e inicializa cada chave se ela não existir no estado da sessão
    for chave, valor in valores_padrao.items():
        if chave not in st.session_state:
            st.session_state[chave] = valor

def reset_app_state():
    """
    Faz um reset completo ao estado da aplicação, limpando caches,
    resultados de simulações e repondo os valores padrão dos widgets.
    """
    # Limpa a cache de dados do Streamlit
    st.cache_data.clear()

    # Lista de chaves a apagar do session_state.
    # Apagamos tudo exceto o estado do próprio uploader de ficheiros.
    keys_to_delete = [key for key in st.session_state.keys() if key != 'consumos_uploader']
    
    for key in keys_to_delete:
        del st.session_state[key]
    
    # Reinicializa o estado com os valores default
    inicializar_estado()

def reset_solar_callback():
    """
    Executada quando a checkbox 'chk_simular_paineis' muda.
    Se for desmarcada, faz um reset completo a TODOS os estados da simulação.
    """
    if not st.session_state.chk_simular_paineis:
        keys_to_reset = [
            # Resultados da simulação solar
            'df_apos_solar', 'fonte_dados_simulacao', 'erro_api_simulacao',
            # Memória da última simulação (para os avisos)
            'last_calculated_latitude', 'last_calculated_longitude',
            'last_calculated_potencia', 'last_calculated_inclinacao',
            'last_calculated_orientacao', 'last_calculated_loss',
            'last_calculated_montagem', 'last_calculated_solar_sombra',
            # Resultados FINAIS e FINANCEIROS
            'df_simulado_final',
            'financeiro_simulado',
            'metricas_simulacao_atual'
        ]
        for key in keys_to_reset:
            if key in st.session_state:
                del st.session_state[key]
        
        # Reinicia o estado de controlo
        st.session_state.calculo_executado = False
        
        # Se a simulação solar for desligada, a bateria também deve ser (se depender dela)
        if not st.session_state.get('tem_upac_existente', False):
            st.session_state.chk_simular_bateria = False

def calcular_simulacao_callback():
    df_apos_solar = None
    df_analise_original = st.session_state.get('df_analise_original')
    if df_analise_original is None or df_analise_original.empty:
        return
    
    with st.spinner("A calcular..."):
        # Se a simulação solar está ativa, corre os cálculos solares
        if st.session_state.get('chk_simular_paineis', False):
            potencia = st.session_state.solar_potencia
            latitude = st.session_state.solar_latitude
            longitude = st.session_state.solar_longitude
            inclinacao = st.session_state.solar_inclinacao
            orientacao_graus = st.session_state.solar_orientacao_graus
            system_loss = st.session_state.solar_loss
            mapa_montagem = {"Instalação livre (free-standing)": "free", "Telhado/Integrado no edifício (BIPV)": "building"}
            posicao_montagem = mapa_montagem[st.session_state.solar_montagem]
            distrito_backup = st.session_state.distrito_selecionado

            df_apos_solar, fonte_usada, erro_api = calc.simular_autoconsumo_completo(
                df_analise_original, potencia, latitude, longitude, inclinacao, 
                orientacao_graus, system_loss, posicao_montagem, distrito_backup, st.session_state.solar_sombra
            )
            
            # --- ATUALIZAR ESTADO COMPLETO APÓS CÁLCULO SOLAR ---
            st.session_state.last_calculated_latitude = latitude
            st.session_state.last_calculated_longitude = longitude
            st.session_state.last_calculated_potencia = potencia
            st.session_state.last_calculated_inclinacao = inclinacao
            st.session_state.last_calculated_orientacao = orientacao_graus
            st.session_state.last_calculated_loss = system_loss
            st.session_state.last_calculated_montagem = st.session_state.solar_montagem
            st.session_state.last_calculated_solar_sombra = st.session_state.solar_sombra
            st.session_state.calculo_executado = True

        else: # Se a checkbox de painéis for desmarcada, limpa os resultados
            if 'df_apos_solar' in st.session_state: del st.session_state.df_apos_solar
            st.session_state.calculo_executado = False

        # --- Aplicação da Simulação Solar ao Cenário Base ---
        df_pre_bateria = calc.aplicar_simulacao_solar_aos_dados_base(df_analise_original, df_apos_solar)

        # --- Simulação da Bateria ---
        df_simulado_final = df_pre_bateria.copy()
        if st.session_state.get('chk_simular_bateria', False):
            capacidade = st.session_state.get('bat_capacidade', 5.0)
            potencia_bat = st.session_state.get('bat_potencia', 2.5)
            eficiencia = st.session_state.get('bat_eficiencia', 90)
            dod = st.session_state.get('bat_dod', 80)

            df_para_bateria = pd.DataFrame({
                'DataHora': df_pre_bateria['DataHora'],
                'Excedente_kWh': df_pre_bateria['Injecao_Rede_Final_kWh'],
                'Consumo_Rede_kWh': df_pre_bateria['Consumo_Rede_Final_kWh']
            })
            df_com_bateria = calc.simular_bateria(df_para_bateria, capacidade, potencia_bat, eficiencia, dod)
            
            df_simulado_final['Consumo_Rede_Final_kWh'] = df_com_bateria['Consumo_Rede_kWh']
            df_simulado_final['Injecao_Rede_Final_kWh'] = df_com_bateria['Excedente_kWh']

            
            # Adiciona as colunas de detalhe da bateria
            battery_cols = ['Bateria_SoC_kWh', 'Bateria_Carga_kWh', 'Bateria_Descarga_kWh', 'Bateria_Energia_Entregue_kWh']
            for col in battery_cols:
                if col in df_com_bateria.columns:
                    df_simulado_final[col] = df_com_bateria[col]
                else: # Garante que as colunas existem mesmo que a função de bateria mude
                    df_simulado_final[col] = 0.0
        
        # Guardar os resultados finais no estado da sessão para a interface usar
        st.session_state.df_apos_solar = df_apos_solar
        st.session_state.df_simulado_final = df_simulado_final
        st.session_state.fonte_dados_simulacao = fonte_usada if 'fonte_usada' in locals() else None
        st.session_state.erro_api_simulacao = erro_api if 'erro_api' in locals() else None


def exibir_inputs_precos_energia(opcao_horaria_selecionada):
    """
    Gera dinamicamente os campos de input para os preços de energia
    com base na opção horária selecionada e retorna um dicionário com os preços.
    """
    oh_lower = opcao_horaria_selecionada.lower()
    precos_siva = {}

    # Dicionário de configuração para os períodos de cada opção horária
    config_periodos = {
        "simples": {"S": ("Preço Energia (€/kWh, s/ IVA)", 0.1658)},
        "bi-horário": {
            "V": ("Preço Vazio (€/kWh, s/ IVA)", 0.1094),
            "F": ("Preço Fora Vazio (€/kWh, s/ IVA)", 0.2008),
        },
        "tri-horário": {
            "V": ("Preço Vazio (€/kWh, s/ IVA)", 0.1094),
            "C": ("Preço Cheias (€/kWh, s/ IVA)", 0.1777),
            "P": ("Preço Ponta (€/kWh, s/ IVA)", 0.2448),
        },
    }

    if "simples" in oh_lower:
        periodos_a_mostrar = config_periodos["simples"]
    elif "bi-horário" in oh_lower:
        periodos_a_mostrar = config_periodos["bi-horário"]
    else: # "tri-horário"
        periodos_a_mostrar = config_periodos["tri-horário"]
    
    # Cria colunas para uma melhor disposição
    cols = st.columns(len(periodos_a_mostrar))

    # Itera sobre os períodos e cria os widgets
    for i, (periodo, (label, valor_default)) in enumerate(periodos_a_mostrar.items()):
        with cols[i]:
            # A chave única garante que o estado é guardado corretamente
            key = f"preco_energia_{periodo.lower()}_siva"
            precos_siva[periodo] = st.number_input(
                label,
                value=valor_default,
                step=0.0001,
                format="%.4f",
                key=key
            )
            
    return precos_siva

def df_to_excel_bytes_com_cabecalho(df, cabecalho_texto):
    """
    Converte um DataFrame para um ficheiro Excel em memória (bytes),
    adicionando um cabeçalho personalizado nas primeiras linhas.
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Escreve o cabeçalho
        df_cabecalho = pd.DataFrame({'Info': cabecalho_texto.split('\n')})
        df_cabecalho.to_excel(writer, index=False, header=False, sheet_name='Dados')
        
        # Escreve os dados do DataFrame, deixando uma linha em branco
        df.to_excel(writer, index=False, sheet_name='Dados', startrow=len(cabecalho_texto.split('\n')) + 1)
        
    return output.getvalue()

def guardar_cenario_callback():
    """
    Guarda um resumo completo da simulação atual, incluindo o custo da instalação
    e a poupança base, na lista de cenários para comparação.
    """
    if 'metricas_simulacao_atual' not in st.session_state or 'financeiro_simulado' not in st.session_state:
        st.warning("Não há dados de simulação para guardar. Execute uma simulação primeiro.")
        return

    # Recalcular a poupança base aqui para garantir que temos o valor correto para guardar
    financeiro_atual = st.session_state.financeiro_atual
    financeiro_simulado = st.session_state.financeiro_simulado
    poupanca_base_periodo = financeiro_atual['balanco_final'] - financeiro_simulado['balanco_final']
    poupanca_anual_base = poupanca_base_periodo * (365.25 / dias) if dias > 0 else 0

    # Pega no dicionário de métricas que já temos...
    cenario_para_guardar = st.session_state.metricas_simulacao_atual.copy()
    
    # ...e adiciona a informação que falta
    cenario_para_guardar['custo_instalacao'] = st.session_state.get('custo_instalacao', 0.0)
    cenario_para_guardar['poupanca_anual_base'] = poupanca_anual_base
    
    # Inclui o DataFrame completo no dicionário do cenário
    cenario_para_guardar['dataframe_resultado'] = st.session_state.df_simulado_final
    
    st.session_state.cenarios_guardados.append(cenario_para_guardar)

def limpar_cenarios_callback():
    """Limpa a lista de cenários guardados."""
    st.session_state.cenarios_guardados = []

# --- Chamar a função para garantir que o estado é inicializado ---
inicializar_estado()

def df_to_excel_bytes(df):
    """Converte um DataFrame para um ficheiro Excel em memória (bytes)."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Dados_15_min')
    processed_data = output.getvalue()
    return processed_data



# --- Inicializar lista de resultados ---
resultados_list = []

# --- Título e Botão de Limpeza Geral (Layout Revisto) ---

# Linha 1: Logo e Título
col_logo, col_titulo = st.columns([1, 5])

with col_logo:
    st.image("https://raw.githubusercontent.com/tiagofelicia/simulador-tarifarios-eletricidade/refs/heads/main/Logo_Tiago_Felicia.png", width=180)

with col_titulo:
    st.title("☀️ Tiago Felícia - Simulador de Autoconsumo Fotovoltaico")

if st.button("🧹 Limpar e Reiniciar Simulador", help="Repõe todos os campos do simulador para os valores iniciais.", use_container_width=True):
    reset_app_state()
    st.success("Aplicação reiniciada para os valores iniciais!")
    time.sleep(1)
    st.rerun()

# ##################################################################
# INÍCIO DO BLOCO - GUIA RÁPIDO
# ##################################################################

with st.expander("❓ Como Usar o Simulador (Guia Rápido)", expanded=False):
    st.markdown("""
    Bem-vindo! Esta ferramenta foi desenhada para o ajudar a tomar a melhor decisão sobre o seu investimento em energia solar. Siga estes 4 passos simples para descobrir o seu potencial de poupança.

    #### **Passo 1: 📂 O Ponto de Partida: O Seu Consumo**
    Tudo começa com os seus dados reais. O simulador precisa do **diagrama de carga**, um ficheiro Excel que a E-Redes disponibiliza gratuitamente e que detalha o seu consumo a cada 15 minutos.

    * **Onde o encontrar?** Faça o download no Balcão Digital da E-Redes: [balcaodigital.e-redes.pt](https://balcaodigital.e-redes.pt/consumptions/history)
    * **Como carregar?** Use o botão "Carregue o seu Diagrama de Carga" abaixo. Pode carregar vários ficheiros de períodos consecutivos; o simulador irá juntá-los automaticamente.

    #### **Passo 2: ⚡ A Sua Realidade Energética**
    Configure os detalhes do seu contrato atual para que os cálculos financeiros sejam precisos.

    * **Defina a Potência e o Tarifário:** Escolha a sua potência contratada e a opção horária (Simples, Bi-horário, etc.).
    * **Filtre o Período:** Selecione as datas de início e fim que pretende analisar. Quanto maior o período, mais fiável será a simulação anual.

    #### **Passo 3: ☀️ O Seu Novo Sistema Solar (e 🔋 Bateria)**
    Agora, vamos desenhar o seu futuro sistema de autoconsumo. Ative as caixas de seleção "Simular sistema solar" e/ou "Simular bateria".

    * **Localização é Chave:** Use o mapa interativo para marcar a localização exata da sua instalação. A produção solar varia significativamente em Portugal!
    * **Configure os Painéis:** Defina a **potência** do sistema (kWp), a **inclinação** e a **orientação** dos painéis. A orientação 0° corresponde a Sul.
    * **Adicione uma Bateria (Opcional):** Se quiser maximizar o seu autoconsumo, experimente adicionar uma bateria, definindo a sua capacidade (kWh) e potência (kW).

    #### **Passo 4: 💡 Análise e Decisão**
    Depois de configurar o sistema, clique em **"Calcular e Visualizar Resultados"**. Explore os resultados para entender o impacto do seu investimento.

    * **Dashboard de Resultados:** Veja um resumo claro da produção solar, do novo consumo da rede e, mais importante, da **poupança anual estimada** e do **tempo de retorno do investimento (Payback)**.
    * **Gráficos Detalhados:** Analise os gráficos para perceber como a produção solar se alinha com o seu consumo ao longo do dia, da semana e do mês.
    * **Compare Cenários:** Use o botão **"💾 Guardar Cenário"** para guardar uma simulação. Depois, altere os parâmetros (ex: adicione mais painéis ou uma bateria) e compare os resultados lado a lado.
    * **Exporte e Partilhe:** Use os botões de download para gerar um **Relatório PDF** completo ou um ficheiro **Excel** para analisar noutras ferramentas.
    """)

# ##################################################################
# FIM DO BLOCO - GUIA RÁPIDO
# ##################################################################

# ##################################################################
# ### SECÇÃO EXTRA: MAPA SOLAR DE PORTUGAL                       ###
# ##################################################################
st.subheader("🗺️ Mapa Solar Interativo de Portugal")

with st.expander("Ver mapa de produção solar de referência por distrito", expanded=False):
    
    texto_parametros_mapa = "Sistema de referência: 1 kWp, Orientação a Sul, Inclinação de 35°, 14% de perdas. / www.tiagofelicia.pt"
    
    col_filtro, col_download = st.columns(2)
    with col_filtro:
        meses_nomes = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
        periodo_selecionado = st.selectbox("Selecione o Período para Visualizar:", ["Anual"] + meses_nomes, key="mapa_periodo")

    producao_base = {}
    unidade_grafico, titulo_grafico = "", ""

    if periodo_selecionado == "Anual":
        producao_base = calc.calcular_producao_anual_pvgis_base(calc.C.DADOS_PVGIS_DISTRITO)
        unidade_grafico = "kWh/ano"
        titulo_grafico = "Produção Solar Anual Estimada (por 1 kWp) - Valores nas capitais de distrito"
    else:
        mes_num = meses_nomes.index(periodo_selecionado) + 1
        producao_base = calc.calcular_producao_mensal_pvgis_base(calc.C.DADOS_PVGIS_DISTRITO, mes_num)
        unidade_grafico = "kWh/mês"
        titulo_grafico = f"Produção Solar Estimada para {periodo_selecionado} (por 1 kWp) - Valores nas capitais de distrito"

    # Aplicar fator de perdas a ambos os valores: total e média diária
    producao_final_por_distrito = {}
    for distrito, valores in producao_base.items():
        producao_final_por_distrito[distrito] = {
            "total": round(valores['total'] * (1 - 0.14)),
            "media_diaria": round(valores['media_diaria'] * (1 - 0.14), 2)
        }

    # Formatar os dados para o Highmaps
    dados_para_mapa = []
    for distrito, valores in producao_final_por_distrito.items():
        if distrito in C.MAPA_DISTRITOS_HC:
            dados_para_mapa.append({
                "hc-key": C.MAPA_DISTRITOS_HC[distrito],
                "name": distrito,
                "value": valores['total'],
                "media_diaria": valores['media_diaria']
            })
    
    valores_producao = [d['total'] for d in producao_final_por_distrito.values()]

    # --- Lógica do Botão de Download ---
    with col_download:
        # 1. Converter o dicionário para um DataFrame com as colunas já separadas
        df_export = pd.DataFrame.from_dict(producao_final_por_distrito, orient='index').reset_index()

        # 2. Renomear as colunas para nomes mais limpos
        df_export.columns = ['Distrito', 'Total', 'Média Diária']

        # 3. Renomear as colunas com a unidade correta para clareza
        df_export.columns = ['Distrito', f'Total ({unidade_grafico})', 'Média Diária (kWh/dia)']

        cabecalho_excel = (
            f"Dados de Produção Solar Estimada para o período: {periodo_selecionado}\n"
            f"{texto_parametros_mapa}\n" 
            f"Extraído de: Simulador de Autoconsumo (por Tiago Felícia)\n"
            f"Data de Extração: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            f"Fonte dos Dados Base: PVGIS (Photovoltaic Geographical Information System) - https://re.jrc.ec.europa.eu/pvg_tools/en/"
        )

        dados_excel_bytes = df_to_excel_bytes_com_cabecalho(df_export, cabecalho_excel)

        st.markdown("<span></span>", unsafe_allow_html=True)
        st.download_button(
            label="📥 Exportar dados do mapa (Excel)",
            data=dados_excel_bytes,
            file_name=f"producao_solar_{periodo_selecionado}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    # --- Geração e apresentação do mapa ---
    if valores_producao:
        dados_grafico_mapa = {
            'titulo': titulo_grafico, 'subtitulo': texto_parametros_mapa,
            'map_url': 'https://code.highcharts.com/mapdata/countries/pt/pt-all.topo.json',
            'dados_mapa': dados_para_mapa,
            'min_color': min(valores_producao), 'max_color': max(valores_producao),
            'unidade': unidade_grafico
        }
        html_mapa = gfx.gerar_mapa_solar('mapa_solar_portugal', dados_grafico_mapa)
        st.components.v1.html(html_mapa, height=770, scrolling=True)


# --- SELEÇÃO DE POTÊNCIA E OPÇÃO HORÁRIA ---

col1, col2 = st.columns(2)

with col1:
    # O valor de st.session_state.sel_potencia já está garantido pela inicialização.
    # O Streamlit guarda o valor do widget e atualiza o estado automaticamente.
    st.selectbox(
        "Potência Contratada (kVA)",
        C.POTENCIAS_VALIDAS,
        key="sel_potencia",
        # Esta função formata cada número da lista para o formato desejado.
        format_func=lambda x: f"{str(x).replace('.', ',')} kVA"
    )

with col2:
    # 1. Determinar as opções horárias válidas com base na potência selecionada
    if st.session_state.sel_potencia >= 27.6:
        opcoes_validas_para_potencia = [
            "Tri-horário - Ciclo Diário",
            "Tri-horário - Ciclo Semanal"
        ]
    else:
        opcoes_validas_para_potencia = C.OPCOES_HORARIAS_TOTAIS

    # 2. Corrigir o estado SE a opção atual se tornou inválida
    # Isto acontece se o utilizador mudar de uma potência baixa para uma alta
    if st.session_state.sel_opcao_horaria not in opcoes_validas_para_potencia:
        st.session_state.sel_opcao_horaria = opcoes_validas_para_potencia[0]

    # 3. Criar o widget. O Streamlit irá gerir a atualização do estado.
    st.selectbox(
        "Opção Horária",
        opcoes_validas_para_potencia,
        key="sel_opcao_horaria" # A chave do session_state é a mesma do widget
    )

# --- 1. Upload do Ficheiro de Consumo ---
st.subheader("⚡ Carregue o seu Diagrama de Carga da E-Redes")
uploaded_files = st.file_uploader(
    "Selecione um ou mais ficheiros da E-Redes (com dados a partir de 01/01/2024)", 
    type=['xlsx'], 
    key="consumos_uploader",
    accept_multiple_files=True
)

# Lógica para determinar o modo e processar o ficheiro
# Se foram carregados novos ficheiros
if uploaded_files:
    # Criamos uma chave única baseada nos nomes e tamanhos dos ficheiros para saber se mudaram
    chave_ficheiros_atuais = "".join([f.name + str(f.size) for f in uploaded_files])

    if st.session_state.get('chave_ficheiros_processados') != chave_ficheiros_atuais:
        # --- RESET AUTOMÁTICO AO CARREGAR NOVO FICHEIRO ---
        reset_app_state()
        # --- FIM DA LINHA ADICIONADA ---

        with st.spinner("A processar e validar ficheiros..."):
            # Usar a nova função de validação
            df_combinado, erro = proc_dados.validar_e_juntar_ficheiros(uploaded_files)

            if erro:
                st.error(erro)
                st.session_state.dados_completos_ficheiro = None
            else:
                st.success("Ficheiros validados e carregados com sucesso!")
                st.session_state.dados_completos_ficheiro = df_combinado
                # Guardar a chave dos ficheiros processados para evitar reprocessamento
                st.session_state.chave_ficheiros_processados = chave_ficheiros_atuais
                # Guardar os nomes dos ficheiros para exibição
                st.session_state.nomes_ficheiros_processados = ", ".join([f.name for f in uploaded_files])
                st.rerun()

# Se não há ficheiros, mas havia antes, limpar o estado
elif not uploaded_files and 'dados_completos_ficheiro' in st.session_state:
     del st.session_state.dados_completos_ficheiro
     if 'chave_ficheiros_processados' in st.session_state:
         del st.session_state.chave_ficheiros_processados
     if 'nomes_ficheiros_processados' in st.session_state:
         del st.session_state.nomes_ficheiros_processados

# --- DEFINIÇÃO DE DATAS  ---
dias_mes = {"Janeiro":31,"Fevereiro":29,"Março":31,"Abril":30,"Maio":31,"Junho":30,"Julho":31,"Agosto":31,"Setembro":30,"Outubro":31,"Novembro":30,"Dezembro":31}
ano_atual = datetime.datetime.now().year
if ((ano_atual % 4 == 0 and ano_atual % 100 != 0) or (ano_atual % 400 == 0)):
    dias_mes["Fevereiro"] = 29

# --- 3. LÓGICA PRINCIPAL DA APLICAÇÃO ---

# A variável 'is_diagram_mode' verifica se temos dados de um ficheiro carregado.
is_diagram_mode = 'dados_completos_ficheiro' in st.session_state and st.session_state.dados_completos_ficheiro is not None

# #######################################################################
# O CÓDIGO SÓ AVANÇA PARA A SIMULAÇÃO SE is_diagram_mode FOR VERDADEIRO #
# #######################################################################
if is_diagram_mode:
    # --- PREPARAÇÃO INICIAL E FILTRO DE DATAS ---
    df_consumos = st.session_state.dados_completos_ficheiro
    st.success(f"Modo Diagrama ativo, usando dados de: {st.session_state.get('nomes_ficheiros_processados', 'ficheiro(s) carregado(s)')}")

    # --- PASSO 1: INPUTS E FILTRAGEM INICIAL ---
    df_consumos_total = st.session_state.dados_completos_ficheiro
    min_date_ficheiro = df_consumos_total['DataHora'].min().date()
    max_date_ficheiro = df_consumos_total['DataHora'].max().date()

    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        data_inicio = st.date_input("Filtrar Data Inicial", value=min_date_ficheiro, min_value=min_date_ficheiro, max_value=max_date_ficheiro, format="DD/MM/YYYY", key="data_inicio_ficheiro")
    with col_f2:
        data_fim = st.date_input("Filtrar Data Final", value=max_date_ficheiro, min_value=min_date_ficheiro, max_value=max_date_ficheiro, format="DD/MM/YYYY", key="data_fim_ficheiro")

    dias = (data_fim - data_inicio).days + 1 if data_fim >= data_inicio else 0
    with col_f3:
        gfx.exibir_metrica_personalizada("Nº de Dias", f"{dias} dias")
        
    df_consumos_bruto_filtrado = df_consumos_total[
        (df_consumos_total['DataHora'].dt.date >= data_inicio) &
        (df_consumos_total['DataHora'].dt.date <= data_fim)
    ].copy()

    # Filtrar o DataFrame para o período selecionado
    df_analise_original = df_consumos_total[
        (df_consumos_total['DataHora'].dt.date >= data_inicio) &
        (df_consumos_total['DataHora'].dt.date <= data_fim)
    ].copy()

    # Guardamos o dataframe na memória para que o callback possa aceder-lhe
    st.session_state.df_analise_original = df_analise_original

    df_omie_filtrado_para_analise = OMIE_CICLOS[
        (OMIE_CICLOS['DataHora'] >= pd.to_datetime(data_inicio)) &
        (OMIE_CICLOS['DataHora'] <= pd.to_datetime(data_fim) + pd.Timedelta(hours=23, minutes=59))
    ].copy()

    # --- PASSO 2: SEPARAÇÃO DAS SECÇÕES ---
    # ##################################################################
    # ### SECÇÃO 1: ANÁLISE DO FICHEIRO CARREGADO                    ###
    # ##################################################################
    st.markdown("---")
    st.subheader("📊 Análise do Ficheiro Carregado")

    # --- PONTO 1: DETEÇÃO DE UPAC EXISTENTE ---
    tem_upac_existente = 'Autoconsumo_Settlement_kWh' in df_analise_original.columns and df_analise_original['Autoconsumo_Settlement_kWh'].sum() > 0.01

    if tem_upac_existente:
        st.success("✅ Detetámos que o seu ficheiro já contém dados de um sistema de autoconsumo (UPAC).")
    else:
        st.info("ℹ️ O seu ficheiro não contém dados de produção solar. A secção de simulação abaixo permitirá criar um cenário com um sistema novo.")

    # --- PONTO 1 (Continuação): MOSTRAR INPUT DO INVERSOR CONDICIONALMENTE ---
    autoconsumo_inversor_kwh = 0.0
    if tem_upac_existente:
        st.markdown("##### ⚡ Dados de Produção Solar (Inversor)")
        st.info("""
        Para uma análise precisa, precisamos do valor de **autoconsumo instantâneo**. Este é o valor que os seus painéis produziram e que o seu local consumiu diretamente.
        **Onde encontrar este valor?** Na aplicação do seu inversor solar, procure por 'Autoconsumo' ou 'Self-consumption' para o período selecionado.
        """)
        autoconsumo_inversor_kwh = st.number_input(
            "Introduza o Autoconsumo do Inversor (kWh)",
            min_value=0.0, step=1.0, format="%.2f", key="autoconsumo_inversor"
        )

    # --- CÁLCULOS E APRESENTAÇÃO DO CENÁRIO ATUAL ---
    st.markdown("##### **Resumo do Cenário Atual**")
    
    # 1. Extrair valores base do ficheiro
    consumo_rede_real = df_analise_original['Consumo (kWh)'].sum()
    injecao_rede_real = df_analise_original.get('Injecao_Rede_kWh', pd.Series(0)).sum()
    consumo_total_casa_do_ficheiro = df_analise_original.get('Consumo_Total_Casa_kWh', consumo_rede_real).sum()
    autoconsumo_settlement_real = (consumo_total_casa_do_ficheiro - consumo_rede_real)
    injecao_total_upac_real = df_analise_original.get('Injecao_Total_UPAC_kWh', pd.Series(0)).sum()

    # 2. Calcular os Totais
    autoconsumo_total_real = autoconsumo_inversor_kwh + autoconsumo_settlement_real
    consumo_total_casa_calculado = consumo_rede_real + autoconsumo_total_real

    # 3. Guardar métricas na memória E criar a variável local
    st.session_state.analise_real = {
        "consumo_rede": consumo_rede_real,
        "injecao_rede": injecao_rede_real,
        "injecao_total_upac": injecao_total_upac_real,
        "consumo_total_casa": consumo_total_casa_calculado,
        "autoconsumo_settlement": autoconsumo_settlement_real,
        "autoconsumo_total": autoconsumo_total_real
    }
    # A linha abaixo garante que a variável está sempre disponível para o resto do script
    analise_real = st.session_state.analise_real

    # 4. Apresentar o Dashboard correto para cada cenário
    if tem_upac_existente:
        # Layout completo para quem tem UPAC (3 colunas)
        col_real1, col_real2, col_real3 = st.columns(3)
        with col_real1:
            st.markdown("<h5 style='text-align: center;'>🏠 Consumo no Local</h5>", unsafe_allow_html=True)
            gfx.exibir_metrica_personalizada("Consumo Total do Local", formatar_numero_pt(consumo_total_casa_calculado, casas_decimais=0, sufixo=" kWh"))
            gfx.exibir_metrica_personalizada("Consumo da Rede (após Settlement)", formatar_numero_pt(consumo_rede_real, casas_decimais=0, sufixo=" kWh"))
        with col_real2:
            st.markdown("<h5 style='text-align: center;'>☀️ Autoconsumo Real</h5>", unsafe_allow_html=True)
            gfx.exibir_metrica_personalizada("Do Inversor (Instantâneo)", formatar_numero_pt(autoconsumo_inversor_kwh, casas_decimais=0, sufixo=" kWh"))
            gfx.exibir_metrica_personalizada("Do Settlement (E-Redes)", formatar_numero_pt(autoconsumo_settlement_real, casas_decimais=0, sufixo=" kWh"))
            st.markdown(f"<div style='background-color:#028E52; color:white; text-align:center; padding: 10px; border-radius: 6px; margin-top:5px;'>"
                        f"<div style='font-size: 0.9rem; opacity: 0.8;'>AUTOCONSUMO TOTAL</div>"
                        f"<div style='font-size: 1.2rem; font-weight: bold;'>{formatar_numero_pt(autoconsumo_total_real, casas_decimais=0, sufixo=' kWh')}</div>"
                        f"</div>", unsafe_allow_html=True)
        with col_real3:
            st.markdown("<h5 style='text-align: center;'>⚡ Injeção na Rede</h5>", unsafe_allow_html=True)
            gfx.exibir_metrica_personalizada("Excedente Solar Gerado", formatar_numero_pt(injecao_total_upac_real, casas_decimais=0, sufixo=" kWh"))
            gfx.exibir_metrica_personalizada("Excedente (para venda)", formatar_numero_pt(injecao_rede_real, casas_decimais=0, sufixo=" kWh"))

    else:
        # Layout simplificado para quem NÃO tem UPAC
        st.markdown("<h5 style='text-align: center;'>🏠 Consumo do Local</h5>", unsafe_allow_html=True)
        gfx.exibir_metrica_personalizada("Consumo Total da Rede", formatar_numero_pt(consumo_rede_real, sufixo=" kWh"))

    # --- PASSO 2: ANÁLISE DE CONSUMOS E GRÁFICOS DO FICHEIRO ---
    st.markdown("##### Análise Detalhada de Consumos e Médias OMIE")
    consumos_agregados_brutos = proc_dados.agregar_consumos_por_periodo(df_consumos_bruto_filtrado, OMIE_CICLOS)
    omie_medios_para_tabela_bruta = proc_dados.calcular_medias_omie_para_todos_ciclos(df_consumos_bruto_filtrado, OMIE_CICLOS)
    tabela_analise_html_bruta = gfx.criar_tabela_analise_completa_html(consumos_agregados_brutos, omie_medios_para_tabela_bruta)
    st.markdown(tabela_analise_html_bruta, unsafe_allow_html=True)

    with st.expander("Ver Gráficos de Análise (Consumo do Ficheiro vs. OMIE)"):
        df_merged_bruto = pd.merge(df_consumos_bruto_filtrado, df_omie_filtrado_para_analise, on='DataHora', how='inner')
        dados_horario_bruto, dados_diario_bruto = gfx.preparar_dados_para_graficos(df_consumos_bruto_filtrado, df_omie_filtrado_para_analise, st.session_state.sel_opcao_horaria, dias)
        dados_semana_bruto = gfx.preparar_dados_dia_semana(df_merged_bruto, st.session_state)
        dados_mensal_bruto = gfx.preparar_dados_mensais(df_merged_bruto, st.session_state)

        if dados_horario_bruto:
            st.components.v1.html(gfx.gerar_grafico_highcharts('grafico_bruto_horario', dados_horario_bruto), height=620)
        if dados_diario_bruto:
            st.components.v1.html(gfx.gerar_grafico_highcharts('grafico_bruto_diario', dados_diario_bruto), height=620)
        if dados_semana_bruto:
            st.components.v1.html(gfx.gerar_grafico_highcharts('grafico_bruto_semana', dados_semana_bruto), height=620)
        if dados_mensal_bruto:
            st.components.v1.html(gfx.gerar_grafico_highcharts('grafico_bruto_mensal', dados_mensal_bruto), height=620)

    # ##################################################################
    # ### SECÇÃO 2: SIMULAÇÃO E COMPARAÇÃO                           ###
    # ##################################################################
    st.markdown("---")
    st.subheader("☀️ Simulação de Novo Cenário e Comparação")


    # --- PONTO 1: CONFIGURAÇÃO DAS SIMULAÇÕES COM CALLBACKS ---
    simular_paineis_check = st.checkbox("Simular (novo/ampliação) sistema solar", key="chk_simular_paineis", on_change=reset_solar_callback)
    
    pode_simular_bateria = tem_upac_existente or simular_paineis_check
    simular_bateria_check = st.checkbox("Simular bateria de armazenamento", key="chk_simular_bateria", on_change=calcular_simulacao_callback, disabled=not pode_simular_bateria)
    
    simulacao_ativa = simular_paineis_check or simular_bateria_check

    if simular_paineis_check:
        with st.expander("📍 1. Localização Geográfica do Sistema Solar", expanded=True):
            st.info("Clique no mapa para selecionar a sua localização ou insira as coordenadas manualmente.")
            
            m = folium.Map(
                location=[st.session_state.solar_latitude, st.session_state.solar_longitude],
                zoom_start=12
            )
            folium.Marker(
                [st.session_state.solar_latitude, st.session_state.solar_longitude], 
                popup="Localização Atual", tooltip="Localização Atual"
            ).add_to(m)

            col_mapa, col_coords = st.columns([3, 1])
            with col_mapa:
                map_data = st_folium(m, width=900, height=600)

            if map_data and map_data.get("last_clicked"):
                lat, lon = map_data["last_clicked"]["lat"], map_data["last_clicked"]["lng"]

                if not math.isclose(lat, st.session_state.solar_latitude, abs_tol=1e-4) or \
                not math.isclose(lon, st.session_state.solar_longitude, abs_tol=1e-4):

                    st.session_state.solar_latitude = lat
                    st.session_state.solar_longitude = lon

                    # CORREÇÃO: Ativar a flag de segurança ANTES de atualizar o distrito
                    st.session_state['_coord_just_changed'] = True

                    atualizar_distrito_pelas_coords()

                    # Atualizar o 'último distrito'
                    st.session_state['_ultimo_distrito'] = st.session_state.distrito_selecionado

                    st.rerun()

            with col_coords:
                st.number_input("Latitude", -90.0, 90.0, 40.5374, 0.001, "%.3f", key="solar_latitude", on_change=handle_coord_change)
                st.number_input("Longitude", -180.0, 180.0, -7.0367, 0.001, "%.3f", key="solar_longitude", on_change=handle_coord_change)

                st.markdown("---")
                # Seletor de backup
                st.selectbox(
                    "Distrito (para backup)",
                    options=list(C.COORDENADAS_DISTRITOS.keys()),
                    key="distrito_selecionado",
                    on_change=atualizar_coords_pelo_distrito,
                    help="Usado como alternativa se a API do PVGIS falhar."
                    )
                st.session_state['_coord_just_changed'] = False
                
        # --- EXPANDER PARA OS RESTANTES PARÂMETROS ---
        with st.expander("⚙️ 2. Parâmetros do Sistema Fotovoltaico e Resumo", expanded=True):
            st.markdown("##### Parâmetros do Sistema Fotovoltaico")

            col1_ac, col2_ac, col3_ac = st.columns(3)
            with col1_ac:
                st.number_input("Potência (kWp)", min_value=0.0, value=2.0, step=0.1, format="%.1f",
                    key="solar_potencia")
                st.selectbox(
                    "Posição de Montagem", ["Instalação livre (free-standing)", "Telhado/Integrado no edifício (BIPV)"], 
                    key="solar_montagem", help="**Instalação livre** - os módulos são colocados numa estrutura que permite a livre circulação de ar atrás deles; **Telhado/Integrado no edifício** - os módulos estão totalmente integrados na estrutura da parede ou telhado do edifício, permitindo pouca ou nenhuma circulação de ar pela parte traseira dos módulos."
                )
            with col2_ac:
                st.number_input("Inclinação (°)", min_value=0, max_value=90, value=35, step=1,
                    key="solar_inclinacao")
                st.slider("Orientação (°)", min_value=-90, max_value=90, value=0,
                    key="solar_orientacao_graus", help="-90° corresponde a Este, 0° a Sul, e 90° a Oeste.")
            with col3_ac:
                st.number_input("Perdas do Sistema (%)", min_value=0, max_value=50, value=14,
                    key="solar_loss", help="Perdas totais do sistema (cabos, sujidade, temperatura, etc.). 14% é um valor standard.")
                st.session_state.fator_sombra = st.slider(
                    "Fator de Sombreamento Anual (%)", 
                    min_value=0, max_value=80, value=0, step=5,
                    key="solar_sombra",
                    help="Estime a percentagem de perda de produção devido a sombras ao longo do ano. 0% = sem sombras; 10-15% = algumas sombras no início/fim do dia; >25% = sombras significativas."
                )
            st.markdown("---")

            # --- LÓGICA DE AVISOS DETALHADOS ---
            if st.session_state.calculo_executado:
                parametros_alterados = []
                mapa_nomes = {
                    'latitude': 'Localização', 'longitude': 'Localização', 'potencia': 'Potência',
                    'inclinacao': 'Inclinação', 'orientacao': 'Orientação', 'loss': 'Perdas',
                    'montagem': 'Montagem'
                }
                # Compara cada parâmetro atual com o último que foi calculado
                if st.session_state.solar_latitude != st.session_state.last_calculated_latitude: parametros_alterados.append('Localização')
                if st.session_state.solar_potencia != st.session_state.last_calculated_potencia: parametros_alterados.append('Potência')
                if st.session_state.solar_inclinacao != st.session_state.last_calculated_inclinacao: parametros_alterados.append('Inclinação')
                if st.session_state.solar_orientacao_graus != st.session_state.last_calculated_orientacao: parametros_alterados.append('Orientação')
                if st.session_state.solar_loss != st.session_state.last_calculated_loss: parametros_alterados.append('Perdas')
                if st.session_state.solar_montagem != st.session_state.last_calculated_montagem: parametros_alterados.append('Montagem')
                if st.session_state.solar_sombra != st.session_state.last_calculated_solar_sombra: parametros_alterados.append('Sombreamento')

                # Remove duplicados (para latitude/longitude)
                parametros_alterados = list(dict.fromkeys(parametros_alterados))

                if len(parametros_alterados) == 1:
                    st.error(f"🔴 O parâmetro '{parametros_alterados[0]}' mudou. Clique abaixo para atualizar a simulação.")
                elif len(parametros_alterados) > 1:
                    st.error("🔴 Vários parâmetros mudaram. Clique abaixo para atualizar a simulação.")

            if st.button("📊 Calcular e Visualizar Resultados", type="primary", use_container_width=True):
                calcular_simulacao_callback()
                st.rerun()

            # O resumo da simulação só aparece se um cálculo já tiver sido executado
            if st.session_state.calculo_executado and 'df_apos_solar' in st.session_state and st.session_state.df_apos_solar is not None:
                st.markdown("##### Desempenho do Novo Sistema / Ampliação (no período)")

                fonte_usada = st.session_state.get('fonte_dados_simulacao', '')
                erro_api = st.session_state.get('erro_api_simulacao', None)

                if fonte_usada == "API PVGIS":
                    st.success("✅ Resultados calculados com dados da API PVGIS.")
                elif fonte_usada == "Backup por Distrito":
                    st.warning(f"⚠️ A API falhou, foram usados dados do Distrito de backup selecionado.")

                df_solar_res = st.session_state.df_apos_solar
                res_col1, res_col2, res_col3 = st.columns(3)
                with res_col1: gfx.exibir_metrica_personalizada("Produção Solar", formatar_numero_pt(df_solar_res['Producao_Solar_kWh'].sum(), casas_decimais=0, sufixo=" kWh"))
                with res_col2: gfx.exibir_metrica_personalizada("Autoconsumo", formatar_numero_pt(df_solar_res['Autoconsumo_kWh'].sum(), casas_decimais=0, sufixo=" kWh"))
                with res_col3: gfx.exibir_metrica_personalizada("Excedente", formatar_numero_pt(df_solar_res['Excedente_kWh'].sum(), casas_decimais=0, sufixo=" kWh"))

    if simular_bateria_check:
        with st.expander("Configuração e Resumo da Simulação da Bateria", expanded=True):
            st.info("A bateria será carregada com o excedente total (existente + simulado) e descarregará para alimentar o consumo da casa.")
            col_bat1, col_bat2, col_bat3, col_bat4 = st.columns(4)
            with col_bat1: st.number_input("Capacidade (kWh)", min_value=0.0, value=5.0, step=0.1, format="%.1f", key="bat_capacidade", on_change=calcular_simulacao_callback)
            with col_bat2: st.number_input("Potência C/D (kW)", min_value=0.0, value=2.5, step=0.1, format="%.1f", key="bat_potencia", help="Potência máxima de carga e descarga da bateria.", on_change=calcular_simulacao_callback)
            with col_bat3: st.slider("Profundidade de Descarga (DoD) (%)", min_value=0, max_value=100, value=80, key="bat_dod", help="(em inglês: **Depth of Discharge - DoD**). Percentagem máxima da capacidade que será utilizada para proteger a bateria.", on_change=calcular_simulacao_callback)
            with col_bat4: st.slider("Eficiência de Ida e Volta (RTE) (%)", min_value=0, max_value=100, value=90, key="bat_eficiencia", help="(em inglês: **Round Trip Efficiency - RTE**). Percentagem de energia que é devolvida pela bateria após um ciclo de carga e descarga.", on_change=calcular_simulacao_callback)

            if 'df_simulado_final' in st.session_state and 'Bateria_Carga_kWh' in st.session_state.df_simulado_final.columns and st.session_state.df_simulado_final['Bateria_Carga_kWh'].sum() > 0:
                st.markdown("##### Resumo do Aproveitamento da Bateria")
                df_bateria = st.session_state.df_simulado_final
                energia_armazenada = df_bateria['Bateria_Carga_kWh'].sum()
                energia_utilizada = df_bateria['Bateria_Energia_Entregue_kWh'].sum()
                perdas = energia_armazenada - energia_utilizada
                res_bat1, res_bat2, res_bat3 = st.columns(3)
                with res_bat1: gfx.exibir_metrica_personalizada("Energia Armazenada", formatar_numero_pt(energia_armazenada, casas_decimais=0, sufixo=" kWh"))
                with res_bat2: gfx.exibir_metrica_personalizada("Energia Utilizada", formatar_numero_pt(energia_utilizada, casas_decimais=0, sufixo=" kWh"))
                with res_bat3: gfx.exibir_metrica_personalizada("Perdas por Eficiência", formatar_numero_pt(perdas, casas_decimais=0, sufixo=" kWh"))

    # --- Expander dedicado aos Gráficos Diários ---
    # Condição para mostrar este expander: só se houver pelo menos um gráfico para exibir
    mostrar_expander_graficos = (
        (simular_paineis_check and 'df_apos_solar' in st.session_state and st.session_state.df_apos_solar is not None) or
        (simular_bateria_check and 'df_simulado_final' in st.session_state and 'Bateria_Carga_kWh' in st.session_state.df_simulado_final.columns and st.session_state.df_simulado_final['Bateria_Carga_kWh'].sum() > 0)
    )

    if mostrar_expander_graficos:
        with st.expander("Gráfico para Visualização Detalhada por Dia", expanded=True):
            st.info("Se calculado com a API PVGIS, os gráficos são construidos com valores médios horários para todos os dias do mês presentes na base de dados PVGIS. Se calculado com backup, são utilizados valores médios horários mensais.")

            # Lógica para encontrar a melhor data pré-selecionada (default)
            default_day = data_inicio
            if simular_paineis_check and 'df_apos_solar' in st.session_state and st.session_state.df_apos_solar is not None:
                default_day = st.session_state.df_apos_solar.groupby(st.session_state.df_apos_solar['DataHora'].dt.date)['Producao_Solar_kWh'].sum().idxmax()
            elif tem_upac_existente and df_analise_original['Injecao_Total_UPAC_kWh'].sum() > 0:
                default_day = df_analise_original.groupby(df_analise_original['DataHora'].dt.date)['Injecao_Total_UPAC_kWh'].sum().idxmax()
            
            # Seletor de data único e partilhado
            dia_selecionado_para_grafico = st.date_input("Selecione um dia para visualizar:", value=default_day, min_value=data_inicio, max_value=data_fim, format="DD/MM/YYYY", key="date_input_grafico_diario")

            # --- BOTÕES DE DOWNLOAD (DIÁRIO E COMPLETO) ---
            #col_d1, col_d2 = st.columns(2)

            #with col_d1:
                # Botão para o dia selecionado (como já existia)
            #    df_dia_final = st.session_state.df_simulado_final[st.session_state.df_simulado_final['DataHora'].dt.date == dia_selecionado_para_grafico].copy()
            #    dados_excel_dia_bytes = df_to_excel_bytes(df_dia_final)
            #    st.download_button(
            #        label="📥 Exportar dados do dia",
            #        data=dados_excel_dia_bytes,
            #        file_name=f"dados_simulacao_{dia_selecionado_para_grafico.strftime('%Y-%m-%d')}.xlsx",
            #        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            #        use_container_width=True
            #    )
            
            #with col_d2:
                # --- BOTÃO NOVO PARA A SIMULAÇÃO COMPLETA ---
                # Usamos o DataFrame completo que está guardado na memória da sessão
            #    df_simulacao_completa = st.session_state.df_simulado_final
            #    dados_excel_completo_bytes = df_to_excel_bytes(df_simulacao_completa)
            #    st.download_button(
            #        label="📥 Exportar simulação completa",
            #        data=dados_excel_completo_bytes,
            #        file_name=f"dados_simulacao_completa_{data_inicio.strftime('%Y%m%d')}_a_{data_fim.strftime('%Y%m%d')}.xlsx",
            #        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            #        use_container_width=True
            #    )
            #st.markdown("---") # Separador visual


            # Mostrar Gráfico Solar (se aplicável)
            if simular_paineis_check and 'df_apos_solar' in st.session_state and st.session_state.df_apos_solar is not None:
                df_solar_res = st.session_state.df_apos_solar
                df_dia_original = df_analise_original[df_analise_original['DataHora'].dt.date == dia_selecionado_para_grafico].copy()
                df_dia_exemplo = df_solar_res[df_solar_res['DataHora'].dt.date == dia_selecionado_para_grafico].copy()
                dados_grafico = {'titulo': 'Produção Solar vs. Consumo Horário (no dia selecionado)', 'categorias': df_dia_exemplo['DataHora'].dt.strftime('%H:%M').tolist(), 'series': [{"name": "Consumo (kWh)", "data": df_dia_original['Consumo (kWh)'].round(3).tolist(), "color": "#2E75B6"}, {"name": "Produção Solar (kWh)", "data": df_dia_exemplo['Producao_Solar_kWh'].round(3).tolist(), "color": "#FFA500"}]}
                st.components.v1.html(gfx.gerar_grafico_solar('grafico_autoconsumo_solar', dados_grafico), height=420)

            # Mostrar Gráfico da Bateria (se aplicável)
            if simular_bateria_check and 'df_simulado_final' in st.session_state and 'Bateria_Carga_kWh' in st.session_state.df_simulado_final.columns and st.session_state.df_simulado_final['Bateria_Carga_kWh'].sum() > 0:
                df_bateria = st.session_state.df_simulado_final
                df_dia_bateria = df_bateria[df_bateria['DataHora'].dt.date == dia_selecionado_para_grafico].copy()
                df_dia_bateria['Fluxo_Carga_kW'] = df_dia_bateria['Bateria_Carga_kWh'] * 4
                df_dia_bateria['Fluxo_Descarga_kW'] = -df_dia_bateria['Bateria_Descarga_kWh'] * 4
                dados_grafico_bat = {'titulo': 'Comportamento da Bateria', 'categorias': df_dia_bateria['DataHora'].dt.strftime('%H:%M').tolist(), 'capacidade_util': st.session_state.bat_capacidade * (st.session_state.bat_dod / 100.0), 'series': [{"name": "Estado de Carga (SoC)", "type": "area", "data": df_dia_bateria['Bateria_SoC_kWh'].round(3).tolist(), "color": "#4472C4", "yAxis": 0}, {"name": "Fluxo (Carga/Descarga)", "type": "column", "data": (df_dia_bateria['Fluxo_Carga_kW'] + df_dia_bateria['Fluxo_Descarga_kW']).round(3).tolist(), "color": "#ED7D31", "yAxis": 1}]}
                st.components.v1.html(gfx.gerar_grafico_bateria('grafico_bateria', dados_grafico_bat), height=420)

        # --- PONTO 2: APRESENTAÇÃO DOS RESULTADOS ---
        if simulacao_ativa and 'df_simulado_final' in st.session_state:
            
            st.markdown("---")
            st.markdown("##### **Comparação: Cenário Atual vs. Cenário Simulado**")
            
            # --- Lógica de cálculo unificada e corrigida ---
            analise_real = st.session_state.analise_real
            df_resultado = st.session_state.df_simulado_final

            # 1. Métricas de energia
            consumo_rede_simulado = df_resultado['Consumo_Rede_Final_kWh'].sum()
            injecao_rede_simulada = df_resultado['Injecao_Rede_Final_kWh'].sum()
            autoconsumo_novo_solar = df_resultado.get('Autoconsumo_kWh_Novo', 0).sum()
            autoconsumo_bateria = df_resultado.get('Bateria_Energia_Entregue_kWh', 0).sum() if 'Bateria_Energia_Entregue_kWh' in df_resultado.columns else 0.0
            autoconsumo_total_final_simulado = analise_real['autoconsumo_total'] + autoconsumo_novo_solar + autoconsumo_bateria
            excedente_novo_solar = df_resultado.get('Excedente_kWh_Novo', 0).sum()
            excedente_solar_gerado_simulado = analise_real['injecao_total_upac'] + excedente_novo_solar

            # 2. Construir o dicionário de métricas para a simulação atual
            nome_cenario = ""
            if st.session_state.get('chk_simular_paineis', False):
                nome_cenario += f"Painéis {st.session_state.get('solar_potencia', 0)} kWp"
            if st.session_state.get('chk_simular_bateria', False):
                if nome_cenario: nome_cenario += " + "
                nome_cenario += f"Bateria {st.session_state.get('bat_capacidade', 0)} kWh"

            st.session_state.metricas_simulacao_atual = {
                "nome": nome_cenario if nome_cenario else "Simulação",
                "consumo_rede": consumo_rede_simulado,
                "excedente_gerado": excedente_solar_gerado_simulado,
                "excedente_venda": injecao_rede_simulada,
                "autoconsumo_total": autoconsumo_total_final_simulado,
                # Adicionar o resultado financeiro aqui, depois de ser calculado
            }

            delta_consumo_rede = consumo_rede_simulado - analise_real['consumo_rede']
            delta_injecao_rede = injecao_rede_simulada - analise_real['injecao_rede']
            delta_autoconsumo = autoconsumo_total_final_simulado - analise_real['autoconsumo_total']
            delta_excedente_gerado = excedente_solar_gerado_simulado - analise_real['injecao_total_upac']

            # 1. Definir o número de colunas necessário
            num_cenarios = len(st.session_state.cenarios_guardados)
            # Colunas = 1 (Atual) + nº de cenários guardados + 1 (Simulação em curso)
            colunas = st.columns(2 + num_cenarios)

            # 2. Apresentar o Cenário Atual (sempre na primeira coluna)
            with colunas[0]:
                st.markdown("<h5 style='text-align: center;'><strong>Cenário Atual</strong></h5>", unsafe_allow_html=True)
                gfx.exibir_metrica_personalizada("Consumo da Rede", formatar_numero_pt(analise_real['consumo_rede'], casas_decimais=0, sufixo=" kWh"))
                if tem_upac_existente:
                    gfx.exibir_metrica_personalizada("Excedente Solar Gerado", formatar_numero_pt(analise_real['injecao_total_upac'], casas_decimais=0, sufixo=" kWh"))
                    gfx.exibir_metrica_personalizada("Excedente (para venda)", formatar_numero_pt(analise_real['injecao_rede'], casas_decimais=0, sufixo=" kWh"))
                    gfx.exibir_metrica_personalizada("Autoconsumo Total", formatar_numero_pt(analise_real['autoconsumo_total'], casas_decimais=0, sufixo=" kWh"))

            # 3. Apresentar a Simulação em Curso (sempre na segunda coluna)
            with colunas[1]:
                metricas_atuais = st.session_state.metricas_simulacao_atual
                st.markdown("#### Simulação Atual")
                st.metric("Consumo da Rede", 
                    formatar_numero_pt(metricas_atuais['consumo_rede'], casas_decimais=0, sufixo=" kWh"), 
                    delta=formatar_numero_pt(metricas_atuais['consumo_rede'] - analise_real['consumo_rede'], casas_decimais=0, sufixo=" kWh"))
                st.metric("Excedente Solar Gerado",
                    formatar_numero_pt(metricas_atuais['excedente_gerado'],casas_decimais=0, sufixo=" kWh"), 
                    delta=formatar_numero_pt(metricas_atuais['excedente_gerado'] - analise_real['injecao_total_upac'], casas_decimais=0, sufixo=" kWh"))
                st.metric("Excedente (para venda)",
                    formatar_numero_pt(metricas_atuais['excedente_venda'], casas_decimais=0, sufixo=" kWh"), 
                    delta=formatar_numero_pt(metricas_atuais['excedente_venda'] - analise_real['injecao_rede'], casas_decimais=0, sufixo=" kWh"))
                st.metric("Autoconsumo Total",
                    formatar_numero_pt(metricas_atuais['autoconsumo_total'], casas_decimais=0, sufixo=" kWh"), 
                    delta=formatar_numero_pt(metricas_atuais['autoconsumo_total'] - analise_real['autoconsumo_total'], casas_decimais=0, sufixo=" kWh"))

            # 4. Apresentar todos os Cenários Guardados
            for i, cenario in enumerate(st.session_state.cenarios_guardados):
                with colunas[i + 2]:
                    st.markdown(f"#### {cenario['nome']}")
                    st.metric("Consumo da Rede", 
                        formatar_numero_pt(cenario['consumo_rede'], casas_decimais=0, sufixo=" kWh"), 
                        delta=formatar_numero_pt(cenario['consumo_rede'] - analise_real['consumo_rede'], casas_decimais=0, sufixo=" kWh"))
                    st.metric("Excedente Solar Gerado",
                        formatar_numero_pt(cenario['excedente_gerado'], casas_decimais=0, sufixo=" kWh"), 
                        delta=formatar_numero_pt(cenario['excedente_gerado'] - analise_real['injecao_total_upac'], casas_decimais=0, sufixo=" kWh"))
                    st.metric("Excedente (para venda)",
                        formatar_numero_pt(cenario['excedente_venda'], casas_decimais=0, sufixo=" kWh"), 
                        delta=formatar_numero_pt(cenario['excedente_venda'] - analise_real['injecao_rede'], casas_decimais=0, sufixo=" kWh"))                    
                    st.metric("Autoconsumo Total",
                        formatar_numero_pt(cenario['autoconsumo_total'], casas_decimais=0, sufixo=" kWh"), 
                        delta=formatar_numero_pt(cenario['autoconsumo_total'] - analise_real['autoconsumo_total'], casas_decimais=0, sufixo=" kWh"))

            # --- ANÁLISE DO CONSUMO LÍQUIDO (TABELA E GRÁFICOS) ---
            st.markdown("##### Análise Comparativa de Consumos (Inicial vs. Simulado)")
            
            df_para_tabela_inicial = df_analise_original.copy()
            consumos_agregados_inicial = proc_dados.agregar_consumos_por_periodo(df_para_tabela_inicial, OMIE_CICLOS)

            df_para_tabela_simulada = df_resultado.copy()
            df_para_tabela_simulada['Consumo (kWh)'] = df_para_tabela_simulada['Consumo_Rede_Final_kWh']
            df_para_tabela_simulada['Injecao_Rede_kWh'] = df_para_tabela_simulada['Injecao_Rede_Final_kWh']

            consumos_agregados_simulado = proc_dados.agregar_consumos_por_periodo(df_para_tabela_simulada, OMIE_CICLOS)

            tabela_comparativa_html = gfx.criar_tabela_comparativa_html(consumos_agregados_inicial, consumos_agregados_simulado)
            st.markdown(tabela_comparativa_html, unsafe_allow_html=True)

            with st.expander("Ver Gráficos de Análise (Consumo Após Simulação vs. OMIE)"):
                df_merged_liquido = pd.merge(df_para_tabela_simulada, df_omie_filtrado_para_analise, on='DataHora', how='inner')
                dados_horario_liq, dados_diario_liq = gfx.preparar_dados_para_graficos(df_para_tabela_simulada, df_omie_filtrado_para_analise, st.session_state.sel_opcao_horaria, dias)
                dados_semana_liq = gfx.preparar_dados_dia_semana(df_merged_liquido, st.session_state)
                dados_mensal_liq = gfx.preparar_dados_mensais(df_merged_liquido, st.session_state)
                if dados_horario_liq: st.components.v1.html(gfx.gerar_grafico_highcharts('grafico_liq_horario', dados_horario_liq), height=620)
                if dados_diario_liq: st.components.v1.html(gfx.gerar_grafico_highcharts('grafico_liq_diario', dados_diario_liq), height=620)
                if dados_semana_liq: st.components.v1.html(gfx.gerar_grafico_highcharts('grafico_liq_semana', dados_semana_liq), height=620)
                if dados_mensal_liq: st.components.v1.html(gfx.gerar_grafico_highcharts('grafico_liq_mensal', dados_mensal_liq), height=620)

            # Gera os dados do Excel em memória
            excel_bytes = exportacao.criar_excel_para_simulador_tarifarios(
                df_original=st.session_state.df_analise_original,
                df_simulado=st.session_state.df_simulado_final,
                nome_cenario=st.session_state.metricas_simulacao_atual['nome']
            )
            st.download_button(
                label="📤 Exportar consumos para Simulador de Tarifários de Tiago Felícia (Excel)",
                data=excel_bytes,
                file_name=f"export_simulador_autoconsumo.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                help="Exporta um Excel formatado para análise e importação no Tiago Felícia - Simulador de Tarifários de Eletricidade.",
                use_container_width=True
            )
# ##################################################################
# ### SECÇÃO 3: DASHBOARD FINANCEIRO                             ###
# ##################################################################
simulacao_ativa_financeiro = st.session_state.get('chk_simular_paineis', False) or st.session_state.get('chk_simular_bateria', False)

# Esta secção só deve aparecer se tivermos um ficheiro carregado.
if is_diagram_mode:

    # CONDIÇÃO: A secção financeira só aparece se houver algo para analisar
    # (uma UPAC existente ou uma simulação ativa).
    if tem_upac_existente or simulacao_ativa_financeiro:
    
        st.markdown("---")
        st.subheader("💰 Análise Financeira e Poupança")

        # --- Bloco Único para Inputs Financeiros ---
        st.markdown("##### Preços do seu Tarifário de Eletricidade (para cálculo da compra à rede)")
        
        precos_energia_siva = exibir_inputs_precos_energia(st.session_state.sel_opcao_horaria)


        # CONDIÇÃO: A checkbox "Família Numerosa" só aparece para potências <= 6.9 kVA
        is_familia_numerosa = False # Definir como Falso por defeito
        if st.session_state.sel_potencia <= 6.9:
            is_familia_numerosa = st.checkbox("Sou beneficiário de Família Numerosa", key="chk_familia_numerosa")

        st.markdown("##### Venda do Excedente")
        col_fin1, col_fin2 = st.columns(2)
        with col_fin1:
            modelo_venda = st.selectbox("Modelo de Venda", ["Preço Fixo", "Indexado ao OMIE"], key="modelo_venda")
        with col_fin2:
            if modelo_venda == "Preço Fixo":
                tipo_comissao = None
                valor_comissao = st.number_input("Preço de Venda Fixo (€/kWh)", value=0.05, step=0.01, format="%.4f", key="valor_venda_fixo")
            else:
                tipo_comissao = st.radio("Tipo de Comissão sobre OMIE", ["Percentual (%)", "Fixo (€/MWh)"], horizontal=True, key="tipo_comissao")
                if tipo_comissao == "Percentual (%)":
                    valor_comissao = st.slider("Comissão (%)", 0, 100, 20, key="valor_comissao_perc")
                else:
                    valor_comissao = st.number_input("Comissão Fixa (€/MWh)", value=10.0, step=0.5, format="%.2f", key="valor_comissao_fixo")

        # --- Bloco de Cálculos Financeiros ---
        with st.spinner("A calcular resultados financeiros..."):
            # 1. Calcular sempre o balanço financeiro do CENÁRIO ATUAL (do ficheiro)
            df_cenario_atual_financeiro = pd.DataFrame({
                'DataHora': df_analise_original['DataHora'],
                'Consumo_Rede_Final_kWh': df_analise_original['Consumo (kWh)'],
                'Injecao_Rede_Final_kWh': df_analise_original.get('Injecao_Rede_kWh', pd.Series(0))
            })
            
            financeiro_atual = calc.calcular_valor_financeiro_cenario(
                df_cenario=df_cenario_atual_financeiro,
                df_omie_completo=OMIE_CICLOS,
                precos_compra_kwh_siva=precos_energia_siva,
                dias_calculo=dias,
                potencia_kva=st.session_state.sel_potencia,
                opcao_horaria_str=st.session_state.sel_opcao_horaria,
                familia_numerosa_bool=is_familia_numerosa,
                modelo_venda=modelo_venda,
                tipo_comissao=tipo_comissao,
                valor_comissao=valor_comissao
            )
            st.session_state.financeiro_atual = financeiro_atual

            # 2. Se houver simulação ativa, calcular o balanço do CENÁRIO SIMULADO
            if simulacao_ativa_financeiro and 'df_simulado_final' in st.session_state:
                st.markdown("##### Custo do Investimento")
                custo_instalacao = st.number_input("Custo da Nova Instalação / Ampliação (€)", value=2000.0, step=100.0, format="%.2f", key="custo_instalacao")
                
                df_simulado_para_financeiro = st.session_state.df_simulado_final
                
                financeiro_simulado = calc.calcular_valor_financeiro_cenario(
                    df_cenario=df_simulado_para_financeiro,
                    df_omie_completo=OMIE_CICLOS,
                    precos_compra_kwh_siva=precos_energia_siva,
                    dias_calculo=dias,
                    potencia_kva=st.session_state.sel_potencia,
                    opcao_horaria_str=st.session_state.sel_opcao_horaria,
                    familia_numerosa_bool=is_familia_numerosa,
                    modelo_venda=modelo_venda,
                    tipo_comissao=tipo_comissao,
                    valor_comissao=valor_comissao
                )
                st.session_state.financeiro_simulado = financeiro_simulado

        if simulacao_ativa and 'df_simulado_final' in st.session_state:
            
            # --- NOVO BLOCO DE BOTÕES PARA GERIR CENÁRIOS ---
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                st.button(
                    "💾 Guardar Cenário", 
                    on_click=guardar_cenario_callback,
                    help="Guarda a simulação atual para comparação com futuras simulações.",
                    use_container_width=True
                )
            with col_b2:
                st.button(
                    "🗑️ Limpar Cenários",
                    on_click=limpar_cenarios_callback,
                    help="Remove todos os cenários guardados.",
                    use_container_width=True
                )
            
            # Mostrar quantos cenários estão guardados
            num_cenarios = len(st.session_state.cenarios_guardados)
            if num_cenarios > 0:
                st.success(f"✅ {num_cenarios} cenário(s) guardado(s) para comparação.")
            # --- FIM DO NOVO BLOCO ---

        st.markdown("---")
        st.markdown("##### **Resultados Financeiros**")

        # --- NOVA ESTRUTURA LÓGICA ---
        # A decisão agora é mais simples:
        # 1. Se uma simulação completa já foi executada e guardada, mostra a vista de comparação.
        # 2. Caso contrário, mostra sempre a análise do cenário base (o ficheiro original).

        simulacao_pronta_para_mostrar = simulacao_ativa_financeiro and 'financeiro_simulado' in st.session_state and st.session_state.financeiro_simulado is not None

        if simulacao_pronta_para_mostrar:
            financeiro_atual = st.session_state.financeiro_atual
            
            # Adicionar o resultado financeiro ao dicionário da simulação atual
            st.session_state.metricas_simulacao_atual['financeiro_resultado'] = st.session_state.financeiro_simulado


            # 1. Calcular a poupança base do primeiro ano
            poupanca_base_periodo = financeiro_atual['balanco_final'] - financeiro_simulado['balanco_final']
            poupanca_anual_base = poupanca_base_periodo * (365.25 / dias) if dias > 0 else 0

            # 2. Decompor a poupança em "custo evitado" e "receita adicional"
            custo_evitado_periodo = financeiro_atual['custo_compra_c_iva'] - financeiro_simulado['custo_compra_c_iva']
            receita_adicional_periodo = financeiro_simulado['receita_venda'] - financeiro_atual['receita_venda']
            
            custo_evitado_anual = custo_evitado_periodo * (365.25 / dias) if dias > 0 else 0
            receita_adicional_anual = receita_adicional_periodo * (365.25 / dias) if dias > 0 else 0

            # --- ANÁLISE DE SENSIBILIDADE (NOVOS INPUTS) ---
            st.markdown("##### Projeção a Longo Prazo e Análise de Sensibilidade")
            col_sens1, col_sens2 = st.columns(2)
            with col_sens1:
                anos_analise = st.number_input("Período de Análise (anos)", min_value=1, max_value=30, value=25, key="num_anos_analise")
                inflacao_energia_perc = st.slider(
                    "Inflação anual do preço da energia (%)", 
                    min_value=-5.0, max_value=10.0, value=3.0, step=0.5, format="%.1f%%",
                    key="slider_inflacao_energia",
                    help="Aumento anual estimado do custo de compra de eletricidade."
                )                
            with col_sens2:
                degradacao_paineis_perc = st.slider(
                    "Degradação anual dos painéis (%)",
                    min_value=0.0, max_value=5.0, value=0.5, step=0.1, format="%.1f%%",
                    key="slider_degradacao",
                    help="Perda de eficiência anual dos painéis solares. Um valor típico é 0.5%."
                )
                variacao_venda_perc = st.slider(
                    "Variação anual no valor de venda do excedente (%)",
                    min_value=-10.0, max_value=10.0, value=0.0, step=0.5, format="%.1f%%",
                    key="slider_variacao_venda",
                    help="Aumento/descida anual estimada do preço médio de venda do seu excedente."
                )


            # O slider de variação de venda pode ficar abaixo ou noutra secção se preferir

            
            st.markdown("---") # Separador visual

            # --- COMPARAÇÃO FINANCEIRA DINÂMICA (COM CORREÇÕES) ---
            # 1. Juntar a simulação atual com os cenários guardados
            simulacao_atual_dict = st.session_state.metricas_simulacao_atual
            todos_os_cenarios = [simulacao_atual_dict] + st.session_state.cenarios_guardados
            
            # 2. Criar colunas dinamicamente (1 para o Atual + 1 para cada cenário)
            colunas_financeiras = st.columns(1 + len(todos_os_cenarios))

            # Lista para guardar os dados do payback para o novo gráfico
            dados_para_grafico_payback = []

            # --- LÓGICA CORRIGIDA PARA A ETIQUETA ---
            if tem_upac_existente:
                # Se já havia UPAC, a poupança é "Adicional"
                poupanca_label = f"Poupança Base Adicional Anual"
            else:
                # Se não havia UPAC, a poupança é a "da UPAC"
                poupanca_label = f"Poupança Base Anual da UPAC"
           # --- FIM DA LÓGICA CORRIGIDA ---

            # 3. Apresentar o Cenário Atual na primeira coluna
            with colunas_financeiras[0]:
                preco_medio_compra_atual = (financeiro_atual['custo_compra_c_iva'] / analise_real['consumo_rede']) if analise_real['consumo_rede'] > 0 else 0
                st.markdown("#### Cenário Atual")
                st.markdown("<div style='margin-top: 40px;'></div>", unsafe_allow_html=True)
                st.metric("Balanço Energético Atual", formatar_numero_pt(financeiro_atual['balanco_final'], sufixo=" €"))
                st.caption(f"Custo Compra: {formatar_numero_pt(financeiro_atual['custo_compra_c_iva'], sufixo=' €')}")
                st.caption(f"**↳ Preço Médio Compra: {formatar_numero_pt(preco_medio_compra_atual, casas_decimais=4, sufixo=' €/kWh')}** (c/IVA)")
                if financeiro_atual['receita_venda'] > 0:
                    st.caption(f"Receita Venda: {formatar_numero_pt(financeiro_atual['receita_venda'], sufixo=' €')}")
                    st.caption(f"**↳ Preço Médio Venda: {formatar_numero_pt(financeiro_atual['preco_medio_venda'], casas_decimais=4, sufixo=' €/kWh**')}")
                    st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)

                if tem_upac_existente:
                    consumo_rede_real_val = st.session_state.analise_real['consumo_rede']
                    preco_medio_compra_atual_kwh = 0
                    if consumo_rede_real_val > 0:
                        preco_medio_compra_atual_kwh = financeiro_atual['custo_compra_c_iva'] / consumo_rede_real_val

                    poupanca_dict_existente = calc.calcular_poupanca_upac_existente(
                        st.session_state.analise_real, financeiro_atual, preco_medio_compra_atual_kwh
                    )
                    poupanca_existente_total = poupanca_dict_existente['total']

                    poupanca_existente_label = f"Poupança da UPAC Atual ({dias} dias)"
                    if 28 <= dias <= 31: poupanca_existente_label = "Poupança Mensal da UPAC Atual"
                    elif 350 <= dias <= 380: poupanca_existente_label = "Poupança Anual da UPAC Atual"

                    st.metric(poupanca_existente_label, formatar_numero_pt(poupanca_existente_total, sufixo=" €"))
                    st.caption(f"Por Autoconsumo: {formatar_numero_pt(poupanca_dict_existente['por_autoconsumo'], sufixo=' €')}")
                    st.caption(f"**↳ Preço Médio Compra: {formatar_numero_pt(preco_medio_compra_atual, casas_decimais=4, sufixo=' €/kWh')}** (c/IVA)")

                    if poupanca_dict_existente['por_venda_excedente'] > 0:
                        st.caption(f"Por Venda de Excedente: {formatar_numero_pt(poupanca_dict_existente['por_venda_excedente'], sufixo=' €')}")

                    if financeiro_atual['receita_venda'] > 0:
                        st.caption(f"**↳ Preço Médio Venda: {formatar_numero_pt(financeiro_atual['preco_medio_venda'], casas_decimais=4, sufixo=' €/kWh**')}")
                    st.markdown("---") 

            # Iterar e apresentar cada cenário simulado
            for i, cenario in enumerate(todos_os_cenarios):
                with colunas_financeiras[i + 1]:
                    # CORREÇÃO: A "Simulação Atual" é a primeira da lista (índice 0)
                    custo_instalacao_cenario = st.session_state.custo_instalacao if i == 0 else cenario.get('custo_instalacao', 0.0)

                    st.markdown(f"#### {cenario['nome']}")
                    st.caption(f"Custo Instalação: {formatar_numero_pt(custo_instalacao_cenario, sufixo=' €')}")

                    financeiro_cenario = cenario['financeiro_resultado']
                    
                    custo_evitado_periodo = financeiro_atual['custo_compra_c_iva'] - financeiro_cenario['custo_compra_c_iva']
                    receita_adicional_periodo = financeiro_cenario['receita_venda'] - financeiro_atual['receita_venda']
                    custo_evitado_anual = (custo_evitado_periodo * (365.25 / dias)) if dias > 0 else 0
                    receita_adicional_anual = (receita_adicional_periodo * (365.25 / dias)) if dias > 0 else 0
                    
                    custo_evitado_ajustado = custo_evitado_anual * (1 + inflacao_energia_perc / 100.0)
                    receita_adicional_ajustada = receita_adicional_anual * (1 + variacao_venda_perc / 100.0)
                    poupanca_anual_ajustada = custo_evitado_ajustado + receita_adicional_ajustada
                    payback_anos_ajustado = custo_instalacao_cenario / poupanca_anual_ajustada if poupanca_anual_ajustada > 0 else float('inf')

                    # ### INÍCIO DO NOVO CÓDIGO A ADICIONAR ###

                    # Chamar a nova função de análise detalhada
                    analise_longo_prazo = calc.calcular_analise_longo_prazo(
                        custo_instalacao=custo_instalacao_cenario,
                        poupanca_autoconsumo_anual_base=custo_evitado_anual, # Usamos o valor anual base
                        poupanca_venda_anual_base=receita_adicional_anual, # Usamos o valor anual base
                        anos_analise=anos_analise,
                        taxa_degradacao_perc=degradacao_paineis_perc,
                        taxa_inflacao_energia_perc=inflacao_energia_perc,
                        taxa_variacao_venda_perc=variacao_venda_perc
                    )
                    # Guardar os resultados para usar no gráfico mais tarde
                    cenario['analise_longo_prazo'] = analise_longo_prazo

                    # ### FIM DO NOVO CÓDIGO A ADICIONAR ###

                    poupanca_anual_base_cenario = (custo_evitado_anual + receita_adicional_anual) if i == 0 else cenario.get('poupanca_anual_base', 0.0)

                    consumo_rede_cenario = cenario['consumo_rede']
                    preco_medio_compra_cenario = (financeiro_cenario['custo_compra_c_iva'] / consumo_rede_cenario) if consumo_rede_cenario > 0 else 0

                    st.metric("Balanço Energético Simulado", formatar_numero_pt(financeiro_cenario['balanco_final'], sufixo=" €"))

                    st.caption(f"Custo Compra: {formatar_numero_pt(financeiro_cenario['custo_compra_c_iva'], sufixo=' €')}")
                    st.caption(f"**↳ Preço Médio Compra: {formatar_numero_pt(preco_medio_compra_cenario, casas_decimais=4, sufixo=' €/kWh')}** (c/IVA)")


                    if financeiro_cenario['receita_venda'] > 0:
                        st.caption(f"Receita Venda: {formatar_numero_pt(financeiro_cenario['receita_venda'], sufixo=' €')}")
                        st.caption(f"**↳ Preço Médio Venda: {formatar_numero_pt(financeiro_cenario['preco_medio_venda'], casas_decimais=4, sufixo=' €/kWh**')}")
                    
                    st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
                    st.metric(poupanca_label, formatar_numero_pt(poupanca_anual_base_cenario, sufixo=" €"))

                    st.metric("Payback Detalhado", formatar_numero_pt(analise_longo_prazo['payback_detalhado'], casas_decimais=1, sufixo=" anos"), help="Payback que considera degradação dos painéis e inflação da energia.")
                    st.metric(f"Poupança Total em {int(anos_analise)} anos", formatar_numero_pt(analise_longo_prazo['poupanca_total_periodo'], sufixo=" €"))

                    # Guardar o resultado do payback para o gráfico
                    dados_para_grafico_payback.append({
                        "name": cenario['nome'],
                        "y": payback_anos_ajustado if payback_anos_ajustado != float('inf') else 0
                    })

            # ### INÍCIO DO NOVO GRÁFICO DE FLUXO DE CAIXA ###

            # O gráfico será mostrado para a "Simulação Atual"
            simulacao_atual_com_analise = todos_os_cenarios[0]

            if 'analise_longo_prazo' in simulacao_atual_com_analise:
                dados_projecao = simulacao_atual_com_analise['analise_longo_prazo']
                custo_instalacao_atual = st.session_state.custo_instalacao

                # Preparar os dados para a função do gráfico
                dados_grafico_projecao = {
                    'categorias': [f"Ano {i+1}" for i in range(len(dados_projecao['fluxo_caixa_anual']))],
                    'investimento': custo_instalacao_atual,
                    'series': [
                        {
                            'name': 'Poupança Anual',
                            'type': 'column',
                            'data': [round(v, 2) for v in dados_projecao['fluxo_caixa_anual']],
                            'color': '#7CB5EC'
                        },
                        {
                            'name': 'Poupança Acumulada',
                            'type': 'line',
                            'data': [round(v, 2) for v in dados_projecao['fluxo_caixa_acumulado']],
                            'color': '#434348'
                        },
                        {
                            'name': 'Investimento Inicial',
                            'type': 'line',
                            'data': [custo_instalacao_atual] * len(dados_projecao['fluxo_caixa_anual']),
                            'color': '#90ED7D',
                            'dashStyle': 'shortdot',
                            'marker': {'enabled': False}
                        }
                    ]
                }

                st.markdown("---")
                html_grafico_projecao = gfx.gerar_grafico_fluxo_caixa('grafico_fluxo_caixa', dados_grafico_projecao)
                st.components.v1.html(html_grafico_projecao, height=420)

            # ### FIM DO NOVO GRÁFICO DE FLUXO DE CAIXA ###


        else:
            # Calcular o preço médio de compra para usar na função de poupança e para exibição
            consumo_rede_real_val = st.session_state.analise_real['consumo_rede']
            preco_medio_compra_kwh = 0
            if consumo_rede_real_val > 0:
                preco_medio_compra_kwh = financeiro_atual['custo_compra_c_iva'] / consumo_rede_real_val

            poupanca_dict = calc.calcular_poupanca_upac_existente(
                st.session_state.analise_real, financeiro_atual, preco_medio_compra_kwh
            )
            poupanca_total = poupanca_dict['total']

            poupanca_label = f"Poupança no Período ({dias} dias)"
            if 28 <= dias <= 31: poupanca_label = "Poupança Mensal Gerada"
            elif 350 <= dias <= 380: poupanca_label = "Poupança Anual Gerada"
            
            col_res_fin1, col_res_fin2 = st.columns(2)
            with col_res_fin1:
                st.metric(poupanca_label, formatar_numero_pt(poupanca_total, sufixo=" €"))
                st.caption(f"Por Autoconsumo: {formatar_numero_pt(poupanca_dict['por_autoconsumo'], sufixo=' €')}")
                st.caption(f"**↳ Preço Médio Compra: {formatar_numero_pt(preco_medio_compra_kwh, casas_decimais=4, sufixo=' €/kWh')}** (c/IVA)")
                if poupanca_dict['por_venda_excedente'] > 0:
                    st.caption(f"Por Venda de Excedente: {formatar_numero_pt(poupanca_dict['por_venda_excedente'], sufixo=' €')}")
                if financeiro_atual['receita_venda'] > 0:
                    st.caption(f"**↳ Preço Médio Venda: {formatar_numero_pt(financeiro_atual['preco_medio_venda'], casas_decimais=4, sufixo=' €/kWh')}**")
                                
            with col_res_fin2:
                st.metric("Balanço Energético Atual", formatar_numero_pt(financeiro_atual['balanco_final'], sufixo=" €"))
                st.caption(f"Custo Compra: {formatar_numero_pt(financeiro_atual['custo_compra_c_iva'], sufixo=' €')}")
                st.caption(f"**↳ Preço Médio Compra: {formatar_numero_pt(preco_medio_compra_kwh, casas_decimais=4, sufixo=' €/kWh')}** (c/IVA)")
                if financeiro_atual['receita_venda'] > 0:
                    st.caption(f"Receita Venda: {formatar_numero_pt(financeiro_atual['receita_venda'], sufixo=' €')}")
                    st.caption(f"**↳ Preço Médio Venda: {formatar_numero_pt(financeiro_atual['preco_medio_venda'], casas_decimais=4, sufixo=' €/kWh**')}")



        # --- GRÁFICO DE CUSTOS MENSAIS (MULTI-CENÁRIO) ---
        if simulacao_ativa_financeiro and 'df_simulado_final' in st.session_state and st.session_state.df_simulado_final is not None:

            parametros_custo_mensal = {
                'df_omie_completo': OMIE_CICLOS,
                'precos_compra_kwh_siva': precos_energia_siva,
                'potencia_kva': st.session_state.sel_potencia,
                'opcao_horaria_str': st.session_state.sel_opcao_horaria,
                'familia_numerosa_bool': is_familia_numerosa,
                'modelo_venda': modelo_venda,
                'tipo_comissao': tipo_comissao,
                'valor_comissao': valor_comissao
            }

            # Preparar a lista de cenários para a função de cálculo
            # É a simulação atual + os cenários guardados
            todos_cenarios_simulados = [
                {"nome": st.session_state.metricas_simulacao_atual['nome'], "dataframe_resultado": st.session_state.df_simulado_final}
            ] + st.session_state.cenarios_guardados

            dados_grafico_custos = calc.calcular_custos_mensais(
                df_analise_original, 
                todos_cenarios_simulados, 
                **parametros_custo_mensal
            )
            
            if dados_grafico_custos:
                st.markdown("---")
                html_grafico_custos = gfx.gerar_grafico_comparacao_custos('grafico_custos_mensais', dados_grafico_custos)
                st.components.v1.html(html_grafico_custos, height=420)

            # --- NOVO GRÁFICO DE COMPARAÇÃO DE PAYBACK ---
            # Só mostra o gráfico se houver mais do que um cenário para comparar
            if len(dados_para_grafico_payback) > 1:
                st.markdown("---")
                
                # Ordenar os dados do melhor (menor) para o pior (maior) payback
                dados_payback_ordenados = sorted(dados_para_grafico_payback, key=lambda x: x['y'])
                
                dados_grafico = {
                    'titulo': 'Classificação de Cenários por Payback',
                    'series_data': dados_payback_ordenados
                }
                html_grafico_payback = gfx.gerar_grafico_payback('grafico_payback_cenarios', dados_grafico)
                st.components.v1.html(html_grafico_payback, height=350)

            # --- INÍCIO DO NOVO BLOCO DE RECOLHA DE DADOS E BOTÃO PDF ---
            st.markdown("---")

            # 1. Preparar a lista completa de cenários financeiros
            cenarios_financeiros_completos = []
            # O 'todos_os_cenarios' já contém a simulação atual + as guardadas
            for cenario in todos_os_cenarios:
                financeiro_cenario = cenario['financeiro_resultado']
                consumo_rede_cenario = cenario['consumo_rede']

                # Calcular os preços médios
                preco_medio_compra = (financeiro_cenario['custo_compra_c_iva'] / consumo_rede_cenario) if consumo_rede_cenario > 0 else 0
                preco_medio_venda = financeiro_cenario['preco_medio_venda']

                # Calcular poupanças anuais base
                poupanca_base_periodo = financeiro_atual['balanco_final'] - financeiro_cenario['balanco_final']
                poupanca_anual_base = poupanca_base_periodo * (365.25 / dias) if dias > 0 else 0

                cenarios_financeiros_completos.append({
                    'nome': cenario['nome'],
                    'metricas_energia': {
                        'consumo_rede': cenario['consumo_rede'] * (365.25 / dias),
                        'autoconsumo_total': cenario['autoconsumo_total'] * (365.25 / dias),
                        'excedente_venda': cenario['excedente_venda'] * (365.25 / dias),
                    },
                    'resultados_financeiros': {
                        'custo_investimento': cenario.get('custo_instalacao', st.session_state.custo_instalacao),
                        'poupanca_anual': poupanca_anual_base,
                        'poupanca_autoconsumo': custo_evitado_anual,
                        'poupanca_venda': receita_adicional_anual,
                        'preco_medio_compra': preco_medio_compra,
                        'preco_medio_venda': preco_medio_venda,
                    },
                    'projecao': cenario['analise_longo_prazo']
                })

            # 2. Reunir todos os dados para o relatório
            dados_para_relatorio = {
                'parametros': {
                    'data_inicio': data_inicio.strftime('%d/%m/%Y'),
                    'data_fim': data_fim.strftime('%d/%m/%Y'),
                    'dias': dias,
                    'latitude': st.session_state.solar_latitude,
                    'longitude': st.session_state.solar_longitude,
                    'distrito': st.session_state.distrito_selecionado,
                    'paineis_kwp': st.session_state.solar_potencia,
                    'inclinacao': st.session_state.solar_inclinacao,
                    'orientacao': st.session_state.solar_orientacao_graus,
                    'perdas': st.session_state.solar_loss,
                    'sombra': st.session_state.solar_sombra,
                    'bateria_kwh': st.session_state.bat_capacidade if st.session_state.chk_simular_bateria else 0,
                    'bateria_kw': st.session_state.bat_potencia if st.session_state.chk_simular_bateria else 0,
                    'opcao_horaria': st.session_state.sel_opcao_horaria
                },
                'cenario_atual_energia': {
                    'consumo_rede': analise_real['consumo_rede'] * (365.25 / dias),
                    'autoconsumo_total': analise_real['autoconsumo_total'] * (365.25 / dias),
                    'excedente_venda': analise_real['injecao_rede'] * (365.25 / dias),
                },
                'cenarios_simulados': cenarios_financeiros_completos,
                # Dados para as novas tabelas estáticas
                'dados_tabela_consumos': {
                    'inicial': consumos_agregados_inicial,
                    'simulado': consumos_agregados_simulado # Usar o da simulação atual
                },
                'dados_custos_mensais': dados_grafico_custos,
                'dados_ranking_payback': dados_para_grafico_payback
            }

            # 3. Gerar o PDF e o botão de download
            pdf_bytes = gfx.gerar_relatorio_pdf(dados_para_relatorio)
            # --- FIM DO NOVO BLOCO ---

            # --- BOTÕES DE DOWNLOAD (Relatório Detalhado e Análise Venda Excedente) ---
            col_exp_relatorio, col_exp_excedente = st.columns(2)
            with col_exp_relatorio:
                timestamp_relatorio = int(time.time())
                filename_relatorio = f"Tiago_Felicia_Relatorio_Autoconsumo_{timestamp_relatorio}.pdf"
                st.download_button(
                    label="📄 Descarregar Relatório Detalhado (PDF)",
                    data=pdf_bytes,
                    file_name=filename_relatorio,
                    mime="application/pdf",
                    use_container_width=True
                )
            with col_exp_excedente:
                timestamp_excedente = int(time.time())
                filename_excedente = f"Tiago_Felicia_Venda_Excedente_{timestamp_excedente}.xlsx"                
                
                st.download_button(
                    label="💹 Descarregar Venda Excedente (Excel)",
                    data=exportacao.criar_excel_analise_venda_excedente(
                        df_original=st.session_state.df_analise_original,
                        df_simulado=st.session_state.df_simulado_final,
                        df_omie=OMIE_CICLOS,
                        modelo_venda=st.session_state.get('modelo_venda', 'Indexado ao OMIE'),
                        tipo_comissao=st.session_state.get('tipo_comissao'),
                        valor_comissao=(
                            st.session_state.get('valor_comissao_perc', 20) if st.session_state.get('tipo_comissao') == 'Percentual (%)' 
                            else st.session_state.get('valor_comissao_fixo', 10.0) if st.session_state.get('tipo_comissao') == 'Fixo (€/MWh)'
                            else st.session_state.get('valor_venda_fixo', 0.05)
                        ),
                        nome_cenario=st.session_state.metricas_simulacao_atual['nome']
                    ),
                    file_name=filename_excedente,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            # --- FIM DO NOVO BOTÃO ---

    #🛠️ Assistente de Dimensionamento de Sistema
    simulacao_ativa = st.session_state.get('chk_simular_paineis', False) or st.session_state.get('chk_simular_bateria', False)

    if simulacao_ativa:

        st.markdown("---")
        st.subheader("🛠️ Assistente de Dimensionamento de Sistema")

        with st.expander("Calcular e comparar vários cenários de potência e armazenamento", expanded=False):
            st.info("Selecione várias opções de painéis e baterias para comparar o seu desempenho financeiro lado a lado.")

            st.markdown("##### Custos de Referência para Estimativa")
            col_custo1, col_custo2 = st.columns(2)
            with col_custo1:
                custo_por_kwp = st.number_input("Custo por kWp de painéis (€)", value=750, step=50)
            with col_custo2:
                custo_por_kwh = st.number_input("Custo por kWh de bateria (€)", value=300, step=50)


            # Opções de potências e baterias para o utilizador escolher
            opcoes_paineis_kwp = [0.0, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 12.0, 14.0, 16.0, 18.0, 20.0] # 0.0 representa "Sem novos paineis"
            opcoes_bateria_kwh = [0.0, 5.0, 7.5, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0] # 0.0 representa "Sem Bateria"

            col_dim1, col_dim2 = st.columns(2)
            with col_dim1:
                potencias_a_testar = st.multiselect("Potências de Painéis (kWp) a testar:", opcoes_paineis_kwp, default=[2.0, 3.0, 4.0])
            with col_dim2:
                baterias_a_testar = st.multiselect("Capacidades de Bateria (kWh) a testar:", opcoes_bateria_kwh, default=[0.0, 5.0, 10.0])

            # --- LÓGICA DE CONTROLO E LIMITE ---
            num_combinacoes = len(potencias_a_testar) * len(baterias_a_testar)
            LIMITE_COMBINACOES = 16 # O nosso limite prático

            if num_combinacoes > 0:
                st.write(f"Total de combinações a calcular: **{num_combinacoes}**")

            botao_desativado = False
            if num_combinacoes > LIMITE_COMBINACOES:
                st.warning(f"Selecionou {num_combinacoes} combinações. Para garantir um tempo de cálculo razoável, por favor selecione um máximo de {LIMITE_COMBINACOES} combinações.")
                botao_desativado = True
            elif num_combinacoes == 0:
                botao_desativado = True

            if st.button("Analisar Dimensionamento", disabled=botao_desativado, use_container_width=True, type="primary"):
                resultados_dimensionamento = []
                barra_progresso = st.progress(0.0, text="A iniciar cálculos...")

                total_a_calcular = num_combinacoes
                calculo_atual = 0

                # Loop principal que itera por todas as combinações
                for p_kwp in potencias_a_testar:
                    df_solar, _, _ = calc.simular_autoconsumo_completo(
                        st.session_state.df_analise_original, p_kwp,
                        st.session_state.solar_latitude, st.session_state.solar_longitude,
                        st.session_state.solar_inclinacao, st.session_state.solar_orientacao_graus,
                        st.session_state.solar_loss,
                        "free" if st.session_state.solar_montagem == "Instalação livre (free-standing)" else "building",
                        st.session_state.distrito_selecionado,
                        st.session_state.solar_sombra
                    )
                    df_pre_bateria_cenario = calc.aplicar_simulacao_solar_aos_dados_base(st.session_state.df_analise_original, df_solar)

                    for b_kwh in baterias_a_testar:
                        calculo_atual += 1
                        percentagem = calculo_atual / total_a_calcular
                        barra_progresso.progress(percentagem, text=f"A calcular {calculo_atual}/{total_a_calcular}: Painéis {p_kwp:.1f} kWp, Bateria {b_kwh:.1f} kWh...")

                        df_para_bateria = df_pre_bateria_cenario[['DataHora', 'Injecao_Rede_Final_kWh', 'Consumo_Rede_Final_kWh']].copy()
                        df_para_bateria.rename(columns={'Injecao_Rede_Final_kWh': 'Excedente_kWh', 'Consumo_Rede_Final_kWh': 'Consumo_Rede_kWh'}, inplace=True)

                        if b_kwh > 0:
                            # A função simular_bateria agora modifica df_para_bateria diretamente
                            df_com_bateria = calc.simular_bateria(
                                df_com_solar=df_para_bateria,
                                capacidade_kwh=b_kwh, potencia_kw=b_kwh/2,
                                eficiencia_perc=st.session_state.bat_eficiencia, dod_perc=st.session_state.bat_dod
                            )
                            # Renomeamos as colunas aqui para o padrão esperado pela função financeira
                            df_final_cenario = df_com_bateria.rename(columns={'Consumo_Rede_kWh': 'Consumo_Rede_Final_kWh', 'Excedente_kWh': 'Injecao_Rede_Final_kWh'})
                        else:
                            # Se não há bateria, apenas renomeamos as colunas do cenário solar
                            df_final_cenario = df_para_bateria.rename(columns={'Consumo_Rede_kWh': 'Consumo_Rede_Final_kWh', 'Excedente_kWh': 'Injecao_Rede_Final_kWh'})

                        # --- INÍCIO DO BLOCO DE CÁLCULO FINANCEIRO CORRIGIDO ---
                        financeiro_cenario = calc.calcular_valor_financeiro_cenario(
                            df_cenario=df_final_cenario, # CORREÇÃO 1: Usa a variável correta
                            df_omie_completo=OMIE_CICLOS,
                            precos_compra_kwh_siva=precos_energia_siva,
                            dias_calculo=dias,
                            potencia_kva=st.session_state.sel_potencia,
                            opcao_horaria_str=st.session_state.sel_opcao_horaria,
                            familia_numerosa_bool=is_familia_numerosa,
                            modelo_venda=modelo_venda,
                            tipo_comissao=tipo_comissao,
                            valor_comissao=valor_comissao
                        )

                        # CORREÇÃO 2: Calcula as poupanças anuais base para o payback
                        financeiro_atual = st.session_state.financeiro_atual
                        custo_evitado_periodo = financeiro_atual['custo_compra_c_iva'] - financeiro_cenario['custo_compra_c_iva']
                        receita_adicional_periodo = financeiro_cenario['receita_venda'] - financeiro_atual['receita_venda']
                        custo_evitado_anual = (custo_evitado_periodo * (365.25 / dias)) if dias > 0 else 0
                        receita_adicional_anual = (receita_adicional_periodo * (365.25 / dias)) if dias > 0 else 0
                        poupanca_anual_total = custo_evitado_anual + receita_adicional_anual

                        custo_estimado = p_kwp * custo_por_kwp + b_kwh * custo_por_kwh

                        # CORREÇÃO 3: Chama o payback com as variáveis corretas
                        analise_lp = calc.calcular_analise_longo_prazo(
                            custo_instalacao=custo_estimado, # Usa o custo estimado para este cenário
                            poupanca_autoconsumo_anual_base=custo_evitado_anual,
                            poupanca_venda_anual_base=receita_adicional_anual,
                            anos_analise=st.session_state.num_anos_analise, # Obtém da UI principal
                            taxa_degradacao_perc=st.session_state.slider_degradacao,
                            taxa_inflacao_energia_perc=st.session_state.slider_inflacao_energia,
                            taxa_variacao_venda_perc=st.session_state.slider_variacao_venda
                        )

                        resultados_dimensionamento.append({
                            "Painéis (kWp)": p_kwp,
                            "Bateria (kWh)": b_kwh,
                            "Custo Estimado (€)": custo_estimado,
                            "Poupança Anual (€)": round(poupanca_anual_total),
                            "Payback (anos)": round(analise_lp['payback_detalhado'], 1) if analise_lp['payback_detalhado'] != float('inf') else '>30'
                        })

                barra_progresso.empty()

                if resultados_dimensionamento:
                    df_resultados = pd.DataFrame(resultados_dimensionamento)
                    st.markdown("### Resultados Comparativos")
                    df_resultados_styled = df_resultados.style.highlight_min(
                        subset=['Payback (anos)'], color='lightgreen'
                    ).format(
                        # CORREÇÃO: Usar a função formatar_numero_pt para cada coluna
                        formatter={
                            "Custo Estimado (€)": lambda x: formatar_numero_pt(x, casas_decimais=0, sufixo=" €"),
                            "Poupança Anual (€)": lambda x: formatar_numero_pt(x, casas_decimais=0, sufixo=" €"),
                            "Painéis (kWp)": lambda x: formatar_numero_pt(x, casas_decimais=1),
                            "Bateria (kWh)": lambda x: formatar_numero_pt(x, casas_decimais=1),
                            # Lógica especial para o Payback, para não formatar o texto '>30'
                            "Payback (anos)": lambda x: formatar_numero_pt(x, casas_decimais=1) if isinstance(x, (int, float)) else x
                        }
                    )
                    st.dataframe(df_resultados_styled, use_container_width=True)

    st.markdown("---")
    st.subheader("⚖️ Comparador de Propostas Comerciais")

    with st.expander("Introduza e compare propostas de diferentes instaladores - irá utilizar a Localização Geográfica do Sistema Solar escolhida em Simular sistema Solar", expanded=False):
        
        # Inicializar a lista de propostas no estado da sessão, se não existir
        if 'propostas_comerciais' not in st.session_state:
            st.session_state.propostas_comerciais = []

        st.info("Adicione os detalhes das propostas que recebeu. O simulador usará os parâmetros de localização e orientação definidos acima para garantir uma comparação justa.")

        # Usamos um formulário para adicionar propostas, para não recarregar a página a cada input
        with st.form("form_add_proposta", clear_on_submit=True):
            st.markdown("##### Adicionar Nova Proposta")
            col_prop1, col_prop2, col_prop3, col_prop4 = st.columns(4)
            with col_prop1:
                nome_proposta = st.text_input("Nome da Proposta", placeholder="Ex: Empresa Solar")
            with col_prop2:
                kwp_proposta = st.number_input("Painéis (kWp)", min_value=0.0, step=0.1, format="%.2f")
            with col_prop3:
                kwh_bateria_proposta = st.number_input("Bateria (kWh)", min_value=0.0, step=0.1, format="%.1f")
            with col_prop4:
                custo_proposta = st.number_input("Custo Total (€)", min_value=0.0, step=100.0, format="%.2f")

            submitted = st.form_submit_button("Adicionar Proposta à Lista")
            if submitted and nome_proposta:
                nova_proposta = {
                    "nome": nome_proposta,
                    "kwp": kwp_proposta,
                    "kwh_bat": kwh_bateria_proposta,
                    "custo": custo_proposta
                }
                st.session_state.propostas_comerciais.append(nova_proposta)
                st.rerun() # Recarrega para mostrar a lista atualizada

        # Exibir a lista de propostas adicionadas
        if st.session_state.propostas_comerciais:
            st.markdown("---")
            st.markdown("##### Propostas para Comparar")
            
            for i, prop in enumerate(st.session_state.propostas_comerciais):
                cols_lista = st.columns([3, 2, 2, 2, 1])
                cols_lista[0].write(f"**{prop['nome']}**")
                cols_lista[1].write(f"{prop['kwp']} kWp")
                cols_lista[2].write(f"{prop['kwh_bat']} kWh")
                cols_lista[3].write(f"{formatar_numero_pt(prop['custo'], sufixo=' €')}")
                
                # Botão para remover a proposta
                if cols_lista[4].button("Remover", key=f"del_{i}"):
                    st.session_state.propostas_comerciais.pop(i)
                    st.rerun()
            
            st.markdown("---")
            # Botão principal para iniciar a comparação
            if st.button("📊 Comparar Todas as Propostas", type="primary", use_container_width=True, key="btn_comparar_propostas"):
                # Verificar se existem propostas para calcular
                if not st.session_state.propostas_comerciais:
                    st.warning("Por favor, adicione pelo menos uma proposta antes de comparar.")
                else:
                    resultados_finais = []
                    barra_progresso = st.progress(0.0, text="A iniciar comparação...")

                    num_propostas = len(st.session_state.propostas_comerciais)
                    
                    # Loop principal que calcula cada proposta
                    for i, prop in enumerate(st.session_state.propostas_comerciais):
                        barra_progresso.progress((i + 1) / num_propostas, text=f"A simular: {prop['nome']}...")

                        # 1. Simulação Solar
                        df_solar, _, _ = calc.simular_autoconsumo_completo(
                            st.session_state.df_analise_original, prop['kwp'],
                            st.session_state.solar_latitude, st.session_state.solar_longitude,
                            st.session_state.solar_inclinacao, st.session_state.solar_orientacao_graus,
                            st.session_state.solar_loss,
                            "free" if st.session_state.solar_montagem == "Instalação livre (free-standing)" else "building",
                            st.session_state.distrito_selecionado,
                            st.session_state.solar_sombra
                        )
                        df_pre_bateria_prop = calc.aplicar_simulacao_solar_aos_dados_base(st.session_state.df_analise_original, df_solar)

                        # 2. Simulação da Bateria (se aplicável)
                        df_final_prop = df_pre_bateria_prop.copy()
                        if prop['kwh_bat'] > 0:
                            df_para_bateria_prop = df_pre_bateria_prop.rename(columns={'Injecao_Rede_Final_kWh': 'Excedente_kWh', 'Consumo_Rede_Final_kWh': 'Consumo_Rede_kWh'})
                            df_final_prop = calc.simular_bateria(
                                df_para_bateria_prop, prop['kwh_bat'], prop['kwh_bat']/2,
                                st.session_state.bat_eficiencia, st.session_state.bat_dod
                            )

                        # 3. Cálculo Financeiro
                        financeiro_prop = calc.calcular_valor_financeiro_cenario(
                            df_cenario=df_final_prop, df_omie_completo=OMIE_CICLOS,
                            precos_compra_kwh_siva=precos_energia_siva, dias_calculo=dias,
                            potencia_kva=st.session_state.sel_potencia, opcao_horaria_str=st.session_state.sel_opcao_horaria,
                            familia_numerosa_bool=is_familia_numerosa, modelo_venda=modelo_venda,
                            tipo_comissao=tipo_comissao, valor_comissao=valor_comissao
                        )

                        # 4. Cálculo do Payback
                        financeiro_atual = st.session_state.financeiro_atual
                        custo_evitado_anual = ((financeiro_atual['custo_compra_c_iva'] - financeiro_prop['custo_compra_c_iva']) * (365.25 / dias))
                        receita_adicional_anual = ((financeiro_prop['receita_venda'] - financeiro_atual['receita_venda']) * (365.25 / dias))
                        
                        analise_lp = calc.calcular_analise_longo_prazo(
                            custo_instalacao=prop['custo'], poupanca_autoconsumo_anual_base=custo_evitado_anual,
                            poupanca_venda_anual_base=receita_adicional_anual, anos_analise=st.session_state.num_anos_analise,
                            taxa_degradacao_perc=st.session_state.slider_degradacao, taxa_inflacao_energia_perc=st.session_state.slider_inflacao_energia,
                            taxa_variacao_venda_perc=st.session_state.slider_variacao_venda
                        )

                        # Guardar os resultados para esta proposta
                        resultados_finais.append({
                            "Proposta": prop['nome'], "Painéis (kWp)": prop['kwp'], "Bateria (kWh)": prop['kwh_bat'],
                            "Custo Total (€)": prop['custo'], "Poupança Anual (€)": custo_evitado_anual + receita_adicional_anual,
                            # --- NOVO: Adicionar ROI aos resultados ---
                            "ROI Anual (%)": analise_lp['roi_simples_anual'],
                            "Payback (anos)": analise_lp['payback_detalhado'],
                            "Poupança a 25 anos (€)": analise_lp['poupanca_total_periodo'] if st.session_state.num_anos_analise == 25 else "N/A"
                        })

                    
                    barra_progresso.empty()
                    st.session_state.resultados_comparacao = resultados_finais # Guardar no estado para exibição
                    st.rerun()

        # Bloco para exibir os resultados da comparação, se existirem
        if 'resultados_comparacao' in st.session_state and st.session_state.resultados_comparacao:
            st.markdown("### Resultados da Comparação")
            
            df_resultados = pd.DataFrame(st.session_state.resultados_comparacao)

            # --- NOVO: Atualizar o estilo para incluir o ROI ---
            df_resultados_styled = df_resultados.style.highlight_min(
                subset=['Payback (anos)'], color='#D4EDDA'
            ).highlight_max(
                subset=['Poupança Anual (€)', 'Poupança a 25 anos (€)', 'ROI Anual (%)'], color='#D4EDDA' # Adicionar ROI aqui
            ).format(formatter={
                "Custo Total (€)": lambda x: formatar_numero_pt(x, casas_decimais=0, sufixo=" €"),
                "Poupança Anual (€)": lambda x: formatar_numero_pt(x, casas_decimais=0, sufixo=" €"),
                "Poupança a 25 anos (€)": lambda x: formatar_numero_pt(x, casas_decimais=0, sufixo=" €") if isinstance(x, (int, float)) else x,
                "Payback (anos)": lambda x: formatar_numero_pt(x, casas_decimais=1) if x != float('inf') else '>30',
                "ROI Anual (%)": lambda x: formatar_numero_pt(x, casas_decimais=1, sufixo=" %"), # Adicionar formatação para ROI
                "Painéis (kWp)": "{:.2f}", "Bateria (kWh)": "{:.1f}",
            })
            st.dataframe(df_resultados_styled, use_container_width=True, hide_index=True)

            # Gerar e exibir o gráfico de Payback
            dados_grafico = {
                'titulo': 'Comparação do Payback por Proposta',
                'series_data': df_resultados.rename(columns={'Proposta': 'name', 'Payback (anos)': 'y'})[['name', 'y']].to_dict('records')
            }
            # Ordenar pelo payback para o gráfico ficar mais claro
            dados_grafico['series_data'] = sorted(dados_grafico['series_data'], key=lambda x: x['y'])
            
            html_grafico_payback = gfx.gerar_grafico_payback('grafico_payback_propostas', dados_grafico)
            st.components.v1.html(html_grafico_payback, height=350)

    ### INÍCIO SECÇÃO DE ANÁLISE DE POTÊNCIA ###
    st.markdown("---") # Separador visual antes da secção de análise de potência
    st.subheader("⚡ Análise da Potência Contratada")

    is_trifasico = st.checkbox(
        "A minha instalação é Trifásica", 
        key="chk_trifasico",
        help="Selecione esta opção se a sua instalação for trifásica. Neste caso o valor de potência será estimado."
    )

    coluna_potencia_analise = "Potencia_kW_Para_Analise"

    # ALTERAÇÃO: Usar a variável 'df_analise_original' que contém os dados filtrados
    if not df_analise_original.empty and coluna_potencia_analise in df_analise_original.columns:
        # Converte o consumo máximo registado num período de 15 min (em kWh) de volta para potência média (em kW)
        pico_potencia_registado = df_analise_original[coluna_potencia_analise].max() * 4 
        potencia_a_comparar = pico_potencia_registado
        nota_trifasico = ""
        nota_trifasico_2 = ""

        if is_trifasico:
            potencia_a_comparar *= 1
            nota_trifasico = "(estimativa para 3 fases)"
            nota_trifasico_2 = "Dado que é uma instalação trifásica, a potência elétrica é distribuida por três fases, sendo o valor da potência máxima tomada a soma das três fases."

        col_p1, col_p2, col_p3 = st.columns(3)
        # ALTERAÇÃO: st.session_state.sel_potencia contém a potência selecionada
        potencia_contratada_valor = st.session_state.sel_potencia
        
        col_p1.metric("Potência Contratada", f"{str(potencia_contratada_valor).replace('.', ',')} kVA")
        col_p2.metric(f"Potência Máxima Registada (Médias de 15 min) {nota_trifasico}", formatar_numero_pt(potencia_a_comparar, casas_decimais=3, sufixo=" kW"), help=nota_trifasico_2)

        percentagem_uso = (potencia_a_comparar / potencia_contratada_valor) * 100 if potencia_contratada_valor > 0 else 0
        
        recomendacao = ""
        if percentagem_uso > 100:
            recomendacao = f"🔴 **Atenção:** A sua Potência Máxima Registada ultrapassa a sua potência contratada. Considere aumentar a potência."
        elif percentagem_uso > 85:
            recomendacao = f"✅ **Adequado:** A sua potência contratada parece bem dimensionada."
        elif percentagem_uso > 60:
            recomendacao = f"💡 **Oportunidade de Poupança:** A sua Potência Máxima Registada utiliza entre 60% e 85% da potência contratada. Pode ser possível reduzir a potência."
        else:
            recomendacao = f"💰 **Forte Oportunidade de Poupança:** A sua Potência Máxima Registada utiliza menos de 60% da sua potência contratada. É muito provável que possa reduzir a potência e poupar na fatura."

        col_p3.metric("Utilização da Potência Máxima", formatar_numero_pt(percentagem_uso, casas_decimais=1, sufixo=" %"))
        st.markdown(recomendacao)
            
    elif not df_analise_original.empty:
        st.warning("Não foi possível realizar a análise de potência. Verifique o conteúdo do ficheiro Excel.")

    ### FIM DA NOVA SECÇÃO ###

else:
    st.info("ℹ️ Por favor, carregue um ficheiro de consumo da E-Redes para iniciar a simulação.")

# --- INÍCIO DA SECÇÃO DE APOIO ---
st.markdown("---") # Separador visual antes da secção de apoio
st.subheader("💖 Apoie este Projeto")

st.markdown(
    "Se quiser apoiar a manutenção do site e o desenvolvimento contínuo deste simulador, "
    "pode fazê-lo através de uma das seguintes formas:"
)

# Link para BuyMeACoffee
st.markdown(
    "☕ [**Compre-me um café em BuyMeACoffee**](https://buymeacoffee.com/tiagofelicia)"
)

st.markdown("ou através do botão PayPal:")

# Código HTML para o botão do PayPal
paypal_button_html = """
<div style="text-align: left; margin-top: 10px; margin-bottom: 15px;">
    <form action="https://www.paypal.com/donate" method="post" target="_blank" style="display: inline-block;">
    <input type="hidden" name="hosted_button_id" value="W6KZHVL53VFJC">
    <input type="image" src="https://www.paypalobjects.com/pt_PT/PT/i/btn/btn_donate_SM.gif" border="0" name="submit" title="PayPal - The safer, easier way to pay online!" alt="Faça donativos com o botão PayPal">
    <img alt="" border="0" src="https://www.paypal.com/pt_PT/i/scr/pixel.gif" width="1" height="1">
    </form>
</div>
"""
st.markdown(paypal_button_html, unsafe_allow_html=True)
# --- FIM DA SECÇÃO DE APOIO ---

st.markdown("---")
# Título para as redes sociais
st.subheader("Redes sociais, onde poderão seguir o projeto:")

# URLs das redes sociais
url_x = "https://x.com/tiagofelicia"
url_bluesky = "https://bsky.app/profile/tiagofelicia.bsky.social"
url_youtube = "https://youtube.com/@tiagofelicia"
url_facebook_perfil = "https://www.facebook.com/profile.php?id=61555007360529"


icon_url_x = "https://upload.wikimedia.org/wikipedia/commons/thumb/c/cc/X_icon.svg/120px-X_icon.svg.png?20250519203220"
icon_url_bluesky = "https://upload.wikimedia.org/wikipedia/commons/7/7a/Bluesky_Logo.svg"
icon_url_youtube = "https://upload.wikimedia.org/wikipedia/commons/thumb/f/fd/YouTube_full-color_icon_%282024%29.svg/120px-YouTube_full-color_icon_%282024%29.svg.png"
icon_url_facebook = "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b9/2023_Facebook_icon.svg/120px-2023_Facebook_icon.svg.png"


svg_icon_style_dark_mode_friendly = "filter: invert(0.8) sepia(0) saturate(1) hue-rotate(0deg) brightness(1.5) contrast(0.8);"

col_social1, col_social2, col_social3, col_social4 = st.columns(4)

with col_social1:
    st.markdown(
        f"""
        <a href="{url_x}" target="_blank" style="text-decoration: none; color: inherit; display: flex; flex-direction: column; align-items: center; text-align: center;">
            <img src="{icon_url_x}" width="40" alt="X" style="margin-bottom: 8px; object-fit: contain;">
            X
        </a>
        """,
        unsafe_allow_html=True
    )

with col_social2:
    st.markdown(
        f"""
        <a href="{url_bluesky}" target="_blank" style="text-decoration: none; color: inherit; display: flex; flex-direction: column; align-items: center; text-align: center;">
            <img src="{icon_url_bluesky}" width="40" alt="Bluesky" style="margin-bottom: 8px; object-fit: contain;">
            Bluesky
        </a>
        """,
        unsafe_allow_html=True
    )

with col_social3:
    st.markdown(
        f"""
        <a href="{url_youtube}" target="_blank" style="text-decoration: none; color: inherit; display: flex; flex-direction: column; align-items: center; text-align: center;">
            <img src="{icon_url_youtube}" width="40" alt="YouTube" style="margin-bottom: 8px; object-fit: contain;">
            YouTube
        </a>
        """,
        unsafe_allow_html=True
    )

with col_social4:
    st.markdown(
        f"""
        <a href="{url_facebook_perfil}" target="_blank" style="text-decoration: none; color: inherit; display: flex; flex-direction: column; align-items: center; text-align: center;">
            <img src="{icon_url_facebook}" width="40" alt="Facebook" style="margin-bottom: 8px; object-fit: contain;">
            Facebook
        </a>
        """,
        unsafe_allow_html=True
    )

st.markdown("<br>", unsafe_allow_html=True) # Adiciona um espaço vertical

# Texto de Copyright
ano_copyright = 2025
nome_autor = "Tiago Felícia"
texto_copyright_html = f"© {ano_copyright} Todos os direitos reservados | {nome_autor} | <a href='{url_facebook_perfil}' target='_blank' style='color: inherit;'>Facebook</a>"

st.markdown(
    f"<div style='text-align: center; font-size: 0.9em; color: grey;'>{texto_copyright_html}</div>",
    unsafe_allow_html=True
)
