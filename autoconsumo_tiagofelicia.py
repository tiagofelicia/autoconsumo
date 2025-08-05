import streamlit as st
import pandas as pd
import datetime
import io
import json
import time
import re
import graficos as gfx
import processamento_dados as proc_dados
import calculos as calc

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

# --- 1. DEFINIÇÕES GLOBAIS FIXAS ---

# Lista de potências válidas em kVA
POTENCIAS_VALIDAS = [1.15, 2.3, 3.45, 4.6, 5.75, 6.9, 10.35, 13.8, 17.25, 20.7, 27.6, 34.5, 41.4]

# Lista completa de todas as opções horárias possíveis
OPCOES_HORARIAS_TOTAIS = [
    "Simples",
    "Bi-horário - Ciclo Diário",
    "Bi-horário - Ciclo Semanal",
    "Tri-horário - Ciclo Diário",
    "Tri-horário - Ciclo Semanal"
]

# --- Fim das definições ---

def inicializar_estado():
    """Define os valores iniciais para o st.session_state se ainda não existirem."""
    if 'sel_potencia' not in st.session_state:
        st.session_state.sel_potencia = 3.45
    if 'sel_opcao_horaria' not in st.session_state:
        st.session_state.sel_opcao_horaria = "Simples"

# --- Chamar a função para garantir que o estado é inicializado ---
inicializar_estado()

def preparar_dados_para_graficos(df_consumos_filtrado, df_omie_filtrado, opcao_horaria_selecionada, dias_periodo):
    """
    Prepara os dados agregados para os gráficos Highcharts no MODO DIAGRAMA.
    - Gráfico Horário: Consumo TOTAL vs. Média OMIE. Tooltip mostra TOTAL e MÉDIA.
    - Gráfico Diário: Consumo empilhado vs. Média OMIE por período.
    """
    if df_consumos_filtrado.empty or df_omie_filtrado.empty:
        return None, None

    df_merged = pd.merge(df_consumos_filtrado, df_omie_filtrado, on='DataHora', how='inner')
    if df_merged.empty:
        st.warning("Não foi possível alinhar dados de consumo e OMIE para os gráficos.")
        return None, None

    # --- Lógica do Título do Ciclo e Períodos (Reutilizada) ---
    oh_lower = opcao_horaria_selecionada.lower()
    titulo_ciclo = "Simples"
    ciclo_a_usar = None
    periodos_ciclo = []
    
    nomes_periodos = {'V': 'Vazio', 'F': 'Fora Vazio', 'C': 'Cheias', 'P': 'Ponta'}
    
    cores_consumo_diario = {'V_bi': '#A9D18E', 'V_tri': '#BF9000', 'F': '#E2F0D9', 'C': '#FFD966', 'P': '#FFF2CC'}
    cores_consumo_semanal = {'V_bi': '#8FAADC', 'V_tri': '#C55A11', 'F': '#DAE3F3', 'C': '#F4B183', 'P': '#FBE5D6'}
    
    cores_omie = {'S': '#FF0000','V': '#000000', 'F': '#FFC000', 'C': '#2F5597', 'P': '#00B050'}
    
    cores_consumo_a_usar = cores_consumo_diario if "diário" in oh_lower else cores_consumo_semanal

    if oh_lower.startswith("bi"):
        periodos_ciclo = ['V', 'F']
        if "diário" in oh_lower:
            ciclo_a_usar = 'BD'; titulo_ciclo = "Bi-Horário - Ciclo Diário"
        else:
            ciclo_a_usar = 'BS'; titulo_ciclo = "Bi-Horário - Ciclo Semanal"
            
    elif oh_lower.startswith("tri"):
        periodos_ciclo = ['V', 'C', 'P']
        if "diário" in oh_lower:
            ciclo_a_usar = 'TD'; titulo_ciclo = "Tri-Horário - Ciclo Diário"
        else:
            ciclo_a_usar = 'TS'; titulo_ciclo = "Tri-Horário - Ciclo Semanal"
            
    # --- 1. Gráfico Horário (com barras empilhadas e OMIE por período) ---
    df_horario = df_merged.copy()
    df_horario['HoraParaAgrupar'] = (df_horario['DataHora'] - pd.Timedelta(seconds=1)).dt.hour
    
    num_dias = dias_periodo if dias_periodo > 0 else 1
    
    series_horario = []
    
    if not ciclo_a_usar:
        agg_horario = df_horario.groupby('HoraParaAgrupar').agg(
            Consumo_kWh_Total=('Consumo (kWh)', 'sum')
        ).reindex(range(24), fill_value=0)
        
        agg_horario['Consumo_kWh_Medio'] = agg_horario['Consumo_kWh_Total'] / num_dias
        
        data_points_horario = [
            {'y': row['Consumo_kWh_Total'], 'media': row['Consumo_kWh_Medio']}
            for _, row in agg_horario.iterrows()
        ]
        series_horario.append({"name": "Consumo por hora (kWh)", "type": "column", "data": data_points_horario, "yAxis": 0, "color": "#BFBFBF"})
    else:
        agg_total_horario_periodo = df_horario.groupby(['HoraParaAgrupar', ciclo_a_usar])['Consumo (kWh)'].sum().unstack(fill_value=0)
        agg_media_horario_periodo = agg_total_horario_periodo / num_dias
        
        for p in reversed(periodos_ciclo):
            if p in agg_total_horario_periodo.columns:
                
                dados_t_p = agg_total_horario_periodo[p].reindex(range(24), fill_value=0)
                dados_m_p = agg_media_horario_periodo[p].reindex(range(24), fill_value=0)
                
                data_points_periodo = [
                    {'y': total, 'media': media} 
                    for total, media in zip(dados_t_p, dados_m_p)
                ]
                
                cor_key = 'V_tri' if p == 'V' and oh_lower.startswith("tri") else ('V_bi' if p == 'V' else p)
                series_horario.append({
                    "name": f"Consumo {nomes_periodos.get(p, p)} (kWh)",
                    "type": "column",
                    "data": data_points_periodo,
                    "yAxis": 0,
                    "color": cores_consumo_a_usar.get(cor_key)
                })

    # Adicionar as linhas OMIE (visível e ocultas)
    agg_omie_horario_simples = df_horario.groupby('HoraParaAgrupar')['OMIE'].mean().reindex(range(24))
    dados_omie_simples_final = agg_omie_horario_simples.round(2).where(pd.notna(agg_omie_horario_simples), None).tolist() # Converte NaN para None
    series_horario.append({
        "name": "Média horária OMIE (€/MWh)", "type": "line", 
        "data": dados_omie_simples_final, "yAxis": 1, "color": cores_omie.get('S')
    })
    
    if ciclo_a_usar:
        agg_omie_horario_periodos = df_horario.groupby(['HoraParaAgrupar', ciclo_a_usar])['OMIE'].mean().unstack()
        for p in periodos_ciclo:
            if p in agg_omie_horario_periodos.columns:
                dados_omie_p = agg_omie_horario_periodos[p].reindex(range(24))
                dados_omie_p_final = dados_omie_p.round(2).where(pd.notna(dados_omie_p), None).tolist() # Converte NaN para None
                series_horario.append({
                    "name": f"Média OMIE {nomes_periodos.get(p, p)} (€/MWh)", "type": "line",
                    "data": dados_omie_p_final, "yAxis": 1, 
                    "color": cores_omie.get(p), "visible": False
                })

    dados_grafico_horario = {
        'titulo': f'Consumo por Hora vs. Preço OMIE Horário ({titulo_ciclo})',
        'titulo_eixo_y1': 'Consumo por hora (kWh)',
        'titulo_eixo_y2': 'Média horária OMIE (€/MWh)',
        'categorias': [f"{h}h-24h" if h == 23 else f"{h}h-{h + 1}h" for h in range(24)],
        'series': series_horario
    }

    # --- 2. Gráfico Diário ---
    df_diario = df_merged.copy()
    df_diario['data_dia'] = pd.to_datetime(df_diario['DataHora'].dt.date)
    
    agg_diario_base = df_diario.groupby('data_dia').agg(
        Consumo_kWh=('Consumo (kWh)', 'sum'),
        Media_OMIE_Simples=('OMIE', 'mean')
    ).sort_index()
    
    series_diario = []
    
    if not ciclo_a_usar:
        series_diario.insert(0, {"name": "Consumo por dia (kWh)", "type": "column", "data": agg_diario_base['Consumo_kWh'].round(2).where(pd.notna, None).tolist(), "yAxis": 0, "color": "#BFBFBF"})
    else:
        agg_consumo_periodos = df_diario.groupby(['data_dia', ciclo_a_usar])['Consumo (kWh)'].sum().unstack(fill_value=0)
        agg_consumo_periodos = agg_consumo_periodos.reindex(agg_diario_base.index)
        for p in periodos_ciclo:
            if p in agg_consumo_periodos.columns:
                cor_a_usar = cores_consumo_a_usar.get(p)
                if p == 'V':
                    chave_cor = 'V_tri' if oh_lower.startswith("tri") else 'V_bi'
                    cor_a_usar = cores_consumo_a_usar.get(chave_cor)

                series_diario.insert(0, {
                    "name": f"Consumo {nomes_periodos.get(p, p)} (kWh)", "type": "column",
                    "data": agg_consumo_periodos[p].round(2).where(pd.notna, None).tolist(),
                    "yAxis": 0, "color": cor_a_usar
                })

    # A mesma lógica de conversão para NaN -> None é aplicada aqui
    dados_omie_diario_simples_final = agg_diario_base['Media_OMIE_Simples'].round(2).where(pd.notna(agg_diario_base['Media_OMIE_Simples']), None).tolist()
    series_diario.append({"name": "Média diária OMIE (€/MWh)", "type": "line", "data": dados_omie_diario_simples_final, "yAxis": 1, "color": cores_omie.get('S')})
    
    if ciclo_a_usar:
        agg_omie_periodos = df_diario.groupby(['data_dia', ciclo_a_usar])['OMIE'].mean().unstack()
        agg_omie_periodos = agg_omie_periodos.reindex(agg_diario_base.index)
        for p in periodos_ciclo:
            if p in agg_omie_periodos.columns:
                dados_omie_p_diario_final = agg_omie_periodos[p].round(2).where(pd.notna(agg_omie_periodos[p]), None).tolist()
                series_diario.append({
                    "name": f"Média OMIE {nomes_periodos.get(p, p)} (€/MWh)", "type": "line",
                    "data": dados_omie_p_diario_final,
                    "yAxis": 1, "color": cores_omie.get(p), "visible": False
                })

    dados_grafico_diario = {
        'titulo': f'Consumo Diário vs. Preço Médio OMIE ({titulo_ciclo})',
        'titulo_eixo_y1': 'Consumo (kWh)',
        'titulo_eixo_y2': 'Média diária OMIE (€/MWh)',
        'categorias': agg_diario_base.index.strftime('%d/%m/%Y').tolist(),
        'series': series_diario
    }
    
    return dados_grafico_horario, dados_grafico_diario

def preparar_dados_dia_semana(df_merged):
    """
    Prepara os dados agregados por dia da semana.
    - O gráfico mostra o TOTAL de consumo (empilhado) e a MÉDIA de OMIE.
    - O tooltip do consumo mostra o TOTAL e a MÉDIA diária.
    """
    if df_merged.empty:
        return None

    df_semana = df_merged.copy()
    df_semana['dia_da_semana'] = df_semana['DataHora'].dt.dayofweek
    
    day_counts = df_semana.groupby(df_semana['DataHora'].dt.date)['dia_da_semana'].first().value_counts().reindex(range(7), fill_value=0)
    
    series_grafico = []
    
    oh_lower = st.session_state.get('sel_opcao_horaria', 'simples').lower()
    
    titulo_ciclo = "Simples"
    ciclo_a_usar = None
    periodos_ciclo = []
    
    if oh_lower.startswith("bi"):
        ciclo_a_usar = 'BD' if "diário" in oh_lower else 'BS'
        periodos_ciclo = ['V', 'F']
        titulo_ciclo = "Bi-Horário - Ciclo Diário" if "diário" in oh_lower else "Bi-Horário - Ciclo Semanal"
    elif oh_lower.startswith("tri"):
        ciclo_a_usar = 'TD' if "diário" in oh_lower else 'TS'
        periodos_ciclo = ['V', 'C', 'P']
        titulo_ciclo = "Tri-Horário - Ciclo Diário" if "diário" in oh_lower else "Tri-Horário - Ciclo Semanal"
    
    nomes_periodos = {'V': 'Vazio', 'F': 'Fora Vazio', 'C': 'Cheias', 'P': 'Ponta'}
    cores_consumo_diario = {'V_bi': '#A9D18E', 'V_tri': '#BF9000', 'F': '#E2EFDA', 'C': '#FFE699', 'P': '#FFF2CC'}
    cores_consumo_semanal = {'V_bi': '#8FAADC', 'V_tri': '#C55A11', 'F': '#DAE3F3', 'C': '#F4B183', 'P': '#FBE5D6'}
    cores_consumo_a_usar = cores_consumo_diario if "diário" in oh_lower else cores_consumo_semanal
    cores_omie = {'S': '#FF0000', 'V': '#000000', 'F': '#FFC000', 'C': '#2F5597', 'P': '#00B050'}

    if ciclo_a_usar and ciclo_a_usar in df_semana.columns:
        consumo_total_periodo = df_semana.groupby(['dia_da_semana', ciclo_a_usar])['Consumo (kWh)'].sum().unstack(fill_value=0)
        
        for p in reversed(periodos_ciclo):
            if p in consumo_total_periodo.columns:
                media_periodo = (consumo_total_periodo[p] / day_counts).fillna(0)
                data_points = [{'y': consumo_total_periodo[p].get(i, 0), 'media': media_periodo.get(i, 0)} for i in range(7)]

                cor_key = 'V_tri' if p == 'V' and oh_lower.startswith("tri") else ('V_bi' if p == 'V' else p)
                series_grafico.append({
                    "name": f"Consumo {nomes_periodos.get(p, p)} (kWh)", "type": "column",
                    "data": data_points,
                    "yAxis": 0, "color": cores_consumo_a_usar.get(cor_key)
                })
    else:
        agg_total_consumo = df_semana.groupby('dia_da_semana')['Consumo (kWh)'].sum()
        agg_media_consumo = (agg_total_consumo / day_counts).fillna(0)
        data_points = [{'y': agg_total_consumo.get(i, 0), 'media': agg_media_consumo.get(i, 0)} for i in range(7)]
        series_grafico.append({"name": "Consumo Total (kWh)", "type": "column", "data": data_points, "yAxis": 0, "color": "#BFBFBF"})
    
    # Adicionar as linhas OMIE (visível e ocultas)
    agg_media_omie_simples = df_semana.groupby('dia_da_semana')['OMIE'].mean().reindex(range(7))
    dados_omie_simples_final = agg_media_omie_simples.round(2).where(pd.notna(agg_media_omie_simples), None).tolist() # Converte NaN para None
    series_grafico.append({
        "name": "Média OMIE (€/MWh)", "type": "line", 
        "data": dados_omie_simples_final, "yAxis": 1, "color": cores_omie.get('S')
    })
    
    if ciclo_a_usar and ciclo_a_usar in df_semana.columns:
        agg_omie_semana_periodos = df_semana.groupby(['dia_da_semana', ciclo_a_usar])['OMIE'].mean().unstack()
        for p in periodos_ciclo:
            if p in agg_omie_semana_periodos.columns:
                dados_omie_p = agg_omie_semana_periodos[p].reindex(range(7))
                dados_omie_p_final = dados_omie_p.round(2).where(pd.notna(dados_omie_p), None).tolist() # Converte NaN para None
                series_grafico.append({
                    "name": f"Média OMIE {nomes_periodos.get(p, p)} (€/MWh)", "type": "line",
                    "data": dados_omie_p_final, "yAxis": 1, 
                    "color": cores_omie.get(p), "visible": False
                })

    return {
        'titulo': f'Consumo e Preço Médio OMIE por Dia da Semana ({titulo_ciclo})',
        'titulo_eixo_y1': 'Consumo Total (kWh)',
        'titulo_eixo_y2': 'Média OMIE (€/MWh)',
        'categorias': ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo'],
        'series': series_grafico
    }

# FUNÇÃO criar_tabela_analise_completa_html
def criar_tabela_analise_completa_html(consumos_agregados, omie_agregados):
    """
    Gera uma tabela HTML detalhada, com cores personalizadas de fundo e texto.
    """
    
    # --- Dicionário de Cores (ESTRUTURA MELHORADA) ---
    cores = {
        'header': {
            'S':  {'bg': '#A6A6A6'},
            'BD': {'bg': '#A9D08E'},
            'BS': {'bg': '#8EA9DB'},
            'TD': {'bg': '#BF8F00', 'text': '#FFFFFF'}, # <--- TEXTO BRANCO DEFINIDO AQUI
            'TS': {'bg': '#C65911', 'text': '#FFFFFF'}  # <--- TEXTO BRANCO DEFINIDO AQUI
        },
        'cell': {
            'S':    {'bg': '#D9D9D9'},
            'BD_V': {'bg': '#C6E0B4'}, 'BD_F': {'bg': '#E2EFDA'},
            'BS_V': {'bg': '#B4C6E7'}, 'BS_F': {'bg': '#D9E1F2'},
            'TD_V': {'bg': '#FFD966'}, 'TD_C': {'bg': '#FFE699'}, 'TD_P': {'bg': '#FFF2CC'},
            'TS_V': {'bg': '#F4B084'}, 'TS_C': {'bg': '#F8CBAD'}, 'TS_P': {'bg': '#FCE4D6'}
        }
    }
    
    # --- Função auxiliar para formatação de números ---
    def fnum(n, casas_decimais=0, sufixo=""):
        try:
            if isinstance(n, str): n = float(n.replace(',', '.'))
            return f"{n:,.{casas_decimais}f}".replace(",", " ") + sufixo
        except (ValueError, TypeError):
            return "-"

    # --- Geração do CSS ---
    html = "<style>"
    html += ".analise-table { width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 13px; font-family: sans-serif; text-align: center; }"
    html += ".analise-table th, .analise-table td { padding: 8px 10px; border: 1px solid #999; }"
    html += ".analise-table thead th { font-weight: bold; }"
    html += ".analise-table .header-main { vertical-align: middle; }"
    html += ".analise-table .row-label { text-align: left; font-weight: bold; background-color: #f8f9fa; }"
    
    for tipo_estilo, mapa_cores in cores.items():
        for chave, config_cor in mapa_cores.items():
            cor_fundo = config_cor['bg']
            cor_texto = config_cor.get('text') # Tenta obter a cor de texto personalizada
            
            if not cor_texto: # Se não houver cor de texto personalizada, calcula o contraste
                try:
                    r, g, b = int(cor_fundo[1:3], 16), int(cor_fundo[3:5], 16), int(cor_fundo[5:7], 16)
                    cor_texto = '#000000' if (r*0.299 + g*0.587 + b*0.114) > 140 else '#FFFFFF'
                except:
                    cor_texto = '#000000' # Fallback
            
            html += f".{tipo_estilo}-{chave} {{ background-color: {cor_fundo}; color: {cor_texto}; }}"
    html += "</style>"

    # --- 2. Extração e Cálculo de Todos os Valores ---
    data = {}
    total_kwh_geral = consumos_agregados.get('Simples', 0)
    ciclos_info = {'S': ['S'], 'BD': ['V', 'F'], 'BS': ['V', 'F'], 'TD': ['V', 'C', 'P'], 'TS': ['V', 'C', 'P']}
    for ciclo, periodos in ciclos_info.items():
        total_consumo_ciclo = sum(consumos_agregados.get(ciclo, {}).values()) if ciclo != 'S' else total_kwh_geral
        for periodo in periodos:
            chave_omie = f"{ciclo}_{periodo}" if ciclo != 'S' else 'S'
            chave_kwh = periodo if ciclo != 'S' else 'Simples'
            kwh = consumos_agregados.get(ciclo, {}).get(periodo, 0) if ciclo != 'S' else total_kwh_geral
            data[f"{ciclo}_{periodo}"] = {
                'omie': omie_agregados.get(chave_omie, 0),
                'kwh': kwh,
                'perc': (kwh / total_consumo_ciclo * 100) if total_consumo_ciclo > 0 else (100 if ciclo == 'S' else 0)
            }

    # --- 3. Construção da Tabela HTML ---
    def fnum(n, casas_decimais=0, sufixo=""):
        try:
            return f"{float(n):,.{casas_decimais}f}".replace(",", " ") + sufixo
        except (ValueError, TypeError):
            return "-"

    def criar_celula(valor, classe, casas_decimais=0, sufixo=""):
        return f"<td class='{classe}'>{fnum(valor, casas_decimais, sufixo)}</td>"
    
    html += "<table class='analise-table'>"
    html += "<thead>"
    html += f"<tr><th rowspan='2'></th><th rowspan='2' class='header-S'>Simples</th><th colspan='2' class='header-BD'>Bi-horário Diário</th><th colspan='2' class='header-BS'>Bi-horário Semanal</th><th colspan='3' class='header-TD'>Tri-horário Diário</th><th colspan='3' class='header-TS'>Tri-horário Semanal</th></tr>"
    html += f"<tr class='header-sub'><th class='cell-BD_V'>Vazio</th><th class='cell-BD_F'>Fora Vazio</th><th class='cell-BS_V'>Vazio</th><th class='cell-BS_F'>Fora Vazio</th><th class='cell-TD_V'>Vazio</th><th class='cell-TD_C'>Cheias</th><th class='cell-TD_P'>Ponta</th><th class='cell-TS_V'>Vazio</th><th class='cell-TS_C'>Cheias</th><th class='cell-TS_P'>Ponta</th></tr>"
    html += "</thead><tbody>"
    
    # Linha Média OMIE
    html += '<tr><td class="row-label">Média OMIE (€/MWh)</td>'
    html += f"{criar_celula(data['S_S']['omie'], 'cell-S', 2)}"
    html += f"{criar_celula(data['BD_V']['omie'], 'cell-BD_V', 2)}{criar_celula(data['BD_F']['omie'], 'cell-BD_F', 2)}"
    html += f"{criar_celula(data['BS_V']['omie'], 'cell-BS_V', 2)}{criar_celula(data['BS_F']['omie'], 'cell-BS_F', 2)}"
    html += f"{criar_celula(data['TD_V']['omie'], 'cell-TD_V', 2)}{criar_celula(data['TD_C']['omie'], 'cell-TD_C', 2)}{criar_celula(data['TD_P']['omie'], 'cell-TD_P', 2)}"
    html += f"{criar_celula(data['TS_V']['omie'], 'cell-TS_V', 2)}{criar_celula(data['TS_C']['omie'], 'cell-TS_C', 2)}{criar_celula(data['TS_P']['omie'], 'cell-TS_P', 2)}</tr>"
    
    # Linha Consumo Real (kWh)
    html += '<tr><td class="row-label">Consumo Real (kWh)</td>'
    html += f"{criar_celula(data['S_S']['kwh'], 'cell-S', 0)}"
    html += f"{criar_celula(data['BD_V']['kwh'], 'cell-BD_V', 0)}{criar_celula(data['BD_F']['kwh'], 'cell-BD_F', 0)}"
    html += f"{criar_celula(data['BS_V']['kwh'], 'cell-BS_V', 0)}{criar_celula(data['BS_F']['kwh'], 'cell-BS_F', 0)}"
    html += f"{criar_celula(data['TD_V']['kwh'], 'cell-TD_V', 0)}{criar_celula(data['TD_C']['kwh'], 'cell-TD_C', 0)}{criar_celula(data['TD_P']['kwh'], 'cell-TD_P', 0)}"
    html += f"{criar_celula(data['TS_V']['kwh'], 'cell-TS_V', 0)}{criar_celula(data['TS_C']['kwh'], 'cell-TS_C', 0)}{criar_celula(data['TS_P']['kwh'], 'cell-TS_P', 0)}</tr>"

    # Linha Consumo %
    html += '<tr><td class="row-label">Consumo %</td>'
    html += f"{criar_celula(data['S_S']['perc'], 'cell-S', 1, '%')}"
    html += f"{criar_celula(data['BD_V']['perc'], 'cell-BD_V', 1, '%')}{criar_celula(data['BD_F']['perc'], 'cell-BD_F', 1, '%')}"
    html += f"{criar_celula(data['BS_V']['perc'], 'cell-BS_V', 1, '%')}{criar_celula(data['BS_F']['perc'], 'cell-BS_F', 1, '%')}"
    html += f"{criar_celula(data['TD_V']['perc'], 'cell-TD_V', 1, '%')}{criar_celula(data['TD_C']['perc'], 'cell-TD_C', 1, '%')}{criar_celula(data['TD_P']['perc'], 'cell-TD_P', 1, '%')}"
    html += f"{criar_celula(data['TS_V']['perc'], 'cell-TS_V', 1, '%')}{criar_celula(data['TS_C']['perc'], 'cell-TS_C', 1, '%')}{criar_celula(data['TS_P']['perc'], 'cell-TS_P', 1, '%')}</tr>"
    
    html += "</tbody></table>"
    return html


# --- Inicializar lista de resultados ---
resultados_list = []

# --- Título e Botão de Limpeza Geral (Layout Revisto) ---

# Linha 1: Logo e Título
col_logo, col_titulo = st.columns([1, 5])

with col_logo:
    st.image("https://raw.githubusercontent.com/tiagofelicia/simulador-tarifarios-eletricidade/refs/heads/main/Logo_Tiago_Felicia.png", width=180)

with col_titulo:
    st.title("☀️ Simulador de Autoconsumo Fotovoltaico")

# ##################################################################
# INÍCIO DO BLOCO - GUIA RÁPIDO
# ##################################################################

with st.expander("❓ Como Usar este Simulador (Guia Rápido)"):
    st.markdown("""
    Esta ferramenta ajuda-o a perceber o impacto real de um sistema de painéis solares (e baterias) no seu consumo de eletricidade.
    
    1.  **Carregue o Ficheiro:** No campo abaixo, carregue o seu ficheiro de diagrama de carga da E-Redes (`.xlsx`). Este ficheiro contém os seus consumos reais a cada 15 minutos.
    2.  **Selecione o Período:** Após o carregamento, escolha as datas que pretende analisar.
    3.  **Configure o Sistema Solar:** Na secção "Configuração do Sistema Fotovoltaico", defina a potência dos painéis (kWp), a sua localização, inclinação e orientação.
    4.  **(Opcional) Simule uma Bateria:** Ative a simulação de baterias para perceber como o armazenamento de energia pode aumentar a sua poupança.
    5.  **Analise os Resultados:** Explore o 'Dashboard de Resultados' para ver um resumo da produção, consumo e poupança. Navegue pelos gráficos para uma análise visual detalhada.
    """)

# ##################################################################
# FIM DO BLOCO - GUIA RÁPIDO
# ##################################################################

# --- SELEÇÃO DE POTÊNCIA E OPÇÃO HORÁRIA ---

col1, col2 = st.columns(2)

with col1:
    # O valor de st.session_state.sel_potencia já está garantido pela inicialização.
    # O Streamlit guarda o valor do widget e atualiza o estado automaticamente.
    st.selectbox(
        "Potência Contratada (kVA)",
        POTENCIAS_VALIDAS,
        key="sel_potencia"  # A chave do session_state é a mesma do widget
    )

with col2:
    # 1. Determinar as opções horárias válidas com base na potência selecionada
    if st.session_state.sel_potencia >= 27.6:
        opcoes_validas_para_potencia = [
            "Tri-horário - Ciclo Diário",
            "Tri-horário - Ciclo Semanal"
        ]
    else:
        opcoes_validas_para_potencia = OPCOES_HORARIAS_TOTAIS

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
st.subheader("⚡ 1. Carregue o seu Diagrama de Carga da E-Redes")
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

    # 3. Guardar métricas na memória para a secção de comparação
    st.session_state.analise_real = {
        "consumo_rede": consumo_rede_real,
        "injecao_rede": injecao_rede_real,
        "injecao_total_upac": injecao_total_upac_real,
        "consumo_total_casa": consumo_total_casa_calculado,
        "autoconsumo_settlement": autoconsumo_settlement_real,
        "autoconsumo_total": autoconsumo_total_real
    }

    # 4. Apresentar o Dashboard correto para cada cenário
    if tem_upac_existente:
        # Layout completo para quem tem UPAC (3 colunas)
        col_real1, col_real2, col_real3 = st.columns(3)
        with col_real1:
            st.markdown("##### 🏠 Consumo no Local")
            gfx.exibir_metrica_personalizada("Consumo Total do Local", f"{consumo_total_casa_calculado:,.2f} kWh")
            gfx.exibir_metrica_personalizada("Consumo da Rede (após Settlement)", f"{consumo_rede_real:,.2f} kWh")
        with col_real2:
            st.markdown("##### ☀️ Autoconsumo Real")
            gfx.exibir_metrica_personalizada("Do Inversor (Instantâneo)", f"{autoconsumo_inversor_kwh:,.2f} kWh")
            gfx.exibir_metrica_personalizada("Do Settlement (E-Redes)", f"{autoconsumo_settlement_real:,.2f} kWh")
            st.markdown(f"<div style='background-color:#028E52; color:white; text-align:center; padding: 10px; border-radius: 6px; margin-top:5px;'>"
                        f"<div style='font-size: 0.9rem; opacity: 0.8;'>AUTOCONSUMO TOTAL</div>"
                        f"<div style='font-size: 1.2rem; font-weight: bold;'>{autoconsumo_total_real:,.2f} kWh</div>"
                        f"</div>", unsafe_allow_html=True)
        with col_real3:
            st.markdown("##### ⚡ Injeção na Rede")
            # ALTERAÇÃO: Adicionar a nova métrica aqui
            gfx.exibir_metrica_personalizada("Injeção Total (UPAC)", f"{injecao_total_upac_real:,.2f} kWh")
            gfx.exibir_metrica_personalizada("Injeção Excedente (Líquida)", f"{injecao_rede_real:,.2f} kWh")
            
    else:
        # Layout simplificado para quem NÃO tem UPAC
        st.markdown("##### 🏠 Consumo do Local")
        gfx.exibir_metrica_personalizada("Consumo Total da Rede", f"{consumo_rede_real:,.2f} kWh")

    # --- PASSO 2: ANÁLISE DE CONSUMOS E GRÁFICOS DO FICHEIRO ---
    st.markdown("##### Análise Detalhada de Consumos e Médias OMIE")
    consumos_agregados_brutos = proc_dados.agregar_consumos_por_periodo(df_consumos_bruto_filtrado, OMIE_CICLOS)
    omie_medios_para_tabela_bruta = proc_dados.calcular_medias_omie_para_todos_ciclos(df_consumos_bruto_filtrado, OMIE_CICLOS)
    tabela_analise_html_bruta = criar_tabela_analise_completa_html(consumos_agregados_brutos, omie_medios_para_tabela_bruta)
    st.markdown(tabela_analise_html_bruta, unsafe_allow_html=True)

    with st.expander("Ver Gráficos de Análise (Consumo do Ficheiro vs. OMIE)"):
        df_merged_bruto = pd.merge(df_consumos_bruto_filtrado, df_omie_filtrado_para_analise, on='DataHora', how='inner')
        dados_horario_bruto, dados_diario_bruto = preparar_dados_para_graficos(df_consumos_bruto_filtrado, df_omie_filtrado_para_analise, st.session_state.sel_opcao_horaria, dias)
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

    #df_consumos_final_para_calculos = df_consumos_bruto_filtrado.copy()
    simular_novo_cenario = st.checkbox("Ativar simulação de autoconsumo", key="chk_simular_cenario", value=False)
    if simular_novo_cenario:
        # PONTO 1: Títulos e descrições dinâmicos
        if tem_upac_existente:
            expander_title = "Simular uma Ampliação ou Alteração do Sistema"
            potencia_label = "Potência do Novo Sistema (kWp)"
        else:
            expander_title = "Simular um Novo Sistema de Autoconsumo"
            potencia_label = "Potência do Novo Sistema (kWp)"

        with st.expander(expander_title, expanded=True):
                distritos_regioes = ['Aveiro', 'Beja', 'Braga', 'Bragança', 'Castelo Branco', 'Coimbra', 'Évora', 'Faro', 'Guarda', 'Leiria', 'Lisboa', 'Portalegre', 'Porto', 'Santarém', 'Setúbal', 'Viana do Castelo', 'Vila Real', 'Viseu', 'Açores (Ponta Delgada)', 'Madeira (Funchal)']
                col1_ac, col2_ac, col3_ac, col4_ac = st.columns(4)
                with col1_ac:
                    potencia_kwp_input = st.number_input("Potência (kWp)", min_value=0.0, value=2.0, step=0.1, format="%.1f", key="solar_potencia")
                with col2_ac:
                    distrito_selecionado = st.selectbox("Distrito/Região", distritos_regioes, index=13, key="solar_distrito")
                with col3_ac:
                    inclinacao_input = st.number_input("Inclinação (°)", min_value=0, max_value=90, value=35, step=1, key="solar_inclinacao")
                with col4_ac:
                    orientacao_selecionada = st.selectbox("Orientação", ["Sul (Ótima)", "Sudeste / Sudoeste", "Este / Oeste"], key="solar_orientacao")

                df_base_simulacao = df_consumos_bruto_filtrado.copy()
                
                with st.spinner("A simular produção solar..."):
                    df_com_solar = calc.simular_autoconsumo_completo(
                        df_consumos=df_base_simulacao,
                        potencia_kwp=st.session_state.solar_potencia,
                        distrito=st.session_state.solar_distrito,
                        inclinacao=st.session_state.solar_inclinacao,
                        orientacao_str=st.session_state.solar_orientacao
                    )
                    # Guardamos o resultado completo da simulação na variável de estado correta
                    st.session_state.df_resultado_simulacao = df_com_solar
                
                    st.write("##### Resumo da Simulação")
                    res_col1, res_col2, res_col3 = st.columns(3)
                    with res_col1:
                        gfx.exibir_metrica_personalizada("Produção Solar", f"{df_com_solar['Producao_Solar_kWh'].sum():.0f} kWh")
                    with res_col2:
                        gfx.exibir_metrica_personalizada("Autoconsumo", f"{df_com_solar['Autoconsumo_kWh'].sum():.0f} kWh")
                    with res_col3:
                        gfx.exibir_metrica_personalizada("Excedente", f"{df_com_solar['Excedente_kWh'].sum():.0f} kWh")

                    if not df_com_solar.empty and df_com_solar['Producao_Solar_kWh'].sum() > 0:
                        dia_default_grafico = df_com_solar.groupby(df_com_solar['DataHora'].dt.date)['Producao_Solar_kWh'].sum().idxmax()
                        
                        dia_selecionado_para_grafico = st.date_input(
                            "Selecione um dia para visualizar no gráfico:",
                            value=dia_default_grafico, min_value=data_inicio, max_value=data_fim,
                            format="DD/MM/YYYY", key="date_input_grafico_solar"
                        )
                        df_dia_exemplo = df_com_solar[df_com_solar['DataHora'].dt.date == dia_selecionado_para_grafico].copy()
                        
                        dados_para_grafico_solar = {
                            'titulo': 'Produção Solar vs. Consumo Horário (no dia selecionado)',
                            'categorias': df_dia_exemplo['DataHora'].dt.strftime('%H:%M').tolist(),
                            'series': [
                                {"name": "Consumo (kWh)", "data": df_dia_exemplo['Consumo (kWh)'].round(3).tolist(), "color": "#2E75B6"},
                                {"name": "Produção Solar (kWh)", "data": df_dia_exemplo['Producao_Solar_kWh'].round(3).tolist(), "color": "#FFA500"}
                            ]
                        }
                        html_grafico_solar = gfx.gerar_grafico_solar('grafico_autoconsumo_solar', dados_para_grafico_solar)
                        st.components.v1.html(html_grafico_solar, height=420)

        # --- PASSO 4: APRESENTAÇÃO DA COMPARAÇÃO (SÓ APARECE DEPOIS DE SIMULAR) ---
        if 'df_resultado_simulacao' in st.session_state:
            st.markdown("##### **Comparação: Cenário Atual vs. Cenário Simulado**")
            
            df_simulado_final = st.session_state.df_resultado_simulacao
            analise_real = st.session_state.analise_real

            # --- Calcular métricas totais do cenário SIMULADO usando a TUA LÓGICA ---
            consumo_rede_simulado = df_simulado_final['Consumo_Rede_kWh'].sum()
            # O teu cálculo para injeção líquida
            injecao_rede_simulada = df_simulado_final['Excedente_kWh'].sum() + injecao_rede_real
            # O teu cálculo para autoconsumo total
            autoconsumo_simulado = df_simulado_final['Autoconsumo_kWh'].sum() + autoconsumo_settlement_real + autoconsumo_inversor_kwh
            # O teu cálculo para injeção total
            injecao_total_upac_simulada = df_simulado_final['Excedente_kWh'].sum() + injecao_total_upac_real

            # Calcular os deltas corretamente com base nos novos totais
            delta_consumo_rede = consumo_rede_simulado - analise_real['consumo_rede']
            delta_injecao_rede = injecao_rede_simulada - analise_real['injecao_rede']
            delta_autoconsumo = autoconsumo_simulado - analise_real['autoconsumo_total']
            delta_injecao_total = injecao_total_upac_simulada - analise_real['injecao_total_upac']

            col_comp1, col_comp2 = st.columns(2)
            with col_comp1:
                st.markdown("#### Cenário Atual (do Ficheiro)")
                gfx.exibir_metrica_personalizada("Consumo da Rede (após Settlement)", f"{analise_real['consumo_rede']:,.2f} kWh")
                if tem_upac_existente:
                    gfx.exibir_metrica_personalizada("Injeção Total (UPAC)", f"{analise_real['injecao_total_upac']:,.2f} kWh")
                gfx.exibir_metrica_personalizada("Injeção Excedente (Líquida)", f"{analise_real['injecao_rede']:,.2f} kWh")
                gfx.exibir_metrica_personalizada("Autoconsumo TOTAL", f"{analise_real['autoconsumo_total']:,.2f} kWh")
                
            with col_comp2:
                st.markdown("#### Cenário Simulado")
                st.metric("Consumo da Rede (após Settlement)", f"{consumo_rede_simulado:,.2f} kWh", delta=f"{delta_consumo_rede:,.2f} kWh", delta_color="inverse")
                if tem_upac_existente:
                    st.metric("Injeção Total (UPAC)", f"{injecao_total_upac_simulada:,.2f} kWh", delta=f"{delta_injecao_total:,.2f} kWh")
                st.metric("Injeção Excedente (Líquida)", f"{injecao_rede_simulada:,.2f} kWh", delta=f"{delta_injecao_rede:,.2f} kWh")
                st.metric("Autoconsumo Simulado", f"{autoconsumo_simulado:,.2f} kWh", delta=f"{delta_autoconsumo:,.2f} kWh")

            # --- ANÁLISE DO CONSUMO LÍQUIDO (AGORA REFERE-SE AO CENÁRIO SIMULADO) ---
            st.markdown("##### Análise Comparativa de Consumos (Inicial vs. Simulado)")
            
            # 1. Preparar os dados de consumo INICIAL (antes da simulação)
            df_para_tabela_inicial = df_analise_original.copy()
            consumos_agregados_inicial = proc_dados.agregar_consumos_por_periodo(df_para_tabela_inicial, OMIE_CICLOS)

            # 2. Preparar os dados de consumo SIMULADO (após simulação)
            df_para_tabela_simulada = st.session_state.df_resultado_simulacao.copy()
            # O consumo da rede no cenário simulado é a coluna 'Consumo_Rede_kWh'
            df_para_tabela_simulada['Consumo (kWh)'] = df_para_tabela_simulada['Consumo_Rede_kWh']
            consumos_agregados_simulado = proc_dados.agregar_consumos_por_periodo(df_para_tabela_simulada, OMIE_CICLOS)

            # 3. Gerar e exibir a nova tabela comparativa
            # A nova função está agora em 'graficos.py' (gfx)
            tabela_comparativa_html = gfx.criar_tabela_comparativa_html(consumos_agregados_inicial, consumos_agregados_simulado)
            st.markdown(tabela_comparativa_html, unsafe_allow_html=True)

            with st.expander("Ver Gráficos de Análise (Consumo Após Simulação vs. OMIE)"):
                df_merged_liquido = pd.merge(df_para_tabela_simulada, df_omie_filtrado_para_analise, on='DataHora', how='inner')
                dados_horario_liq, dados_diario_liq = preparar_dados_para_graficos(df_para_tabela_simulada, df_omie_filtrado_para_analise, st.session_state.sel_opcao_horaria, dias)
                dados_semana_liq = gfx.preparar_dados_dia_semana(df_merged_liquido, st.session_state)
                dados_mensal_liq = gfx.preparar_dados_mensais(df_merged_liquido, st.session_state)
                if dados_horario_liq:
                    st.components.v1.html(gfx.gerar_grafico_highcharts('grafico_liq_horario', dados_horario_liq), height=620)
                if dados_diario_liq:
                    st.components.v1.html(gfx.gerar_grafico_highcharts('grafico_liq_diario', dados_diario_liq), height=620)
                if dados_semana_liq:
                    st.components.v1.html(gfx.gerar_grafico_highcharts('grafico_liq_semana', dados_semana_liq), height=620)
                if dados_mensal_liq:
                    st.components.v1.html(gfx.gerar_grafico_highcharts('grafico_liq_mensal', dados_mensal_liq), height=620)

# ##################################################################
# ### SECÇÃO 3: DASHBOARD FINANCEIRO                             ###
# ##################################################################

# Esta secção só deve aparecer se tivermos um ficheiro carregado.
if is_diagram_mode:

    # CONDIÇÃO: A secção financeira só aparece se houver algo para analisar
    # (uma UPAC existente ou uma simulação ativa).
    if tem_upac_existente or simular_novo_cenario:
    
        st.markdown("---")
        st.subheader("💰 Análise Financeira e Poupança")

        # --- Bloco Único para Inputs Financeiros ---
        st.markdown("##### Preços do seu Tarifário de Eletricidade (para cálculo da compra à rede)")
        
        oh_selecionada_lower = st.session_state.get('sel_opcao_horaria', 'simples').lower()
        precos_energia_siva = {}

        if oh_selecionada_lower == "simples":
            precos_energia_siva['S'] = st.number_input(
                "Preço Energia (€/kWh, s/ IVA)",
                value=0.1658, step=0.0001, format="%.4f", key="preco_energia_simples_siva"
            )
        elif oh_selecionada_lower.startswith("bi"):
            col_preco1, col_preco2 = st.columns(2)
            with col_preco1:
                precos_energia_siva['V'] = st.number_input(
                    "Preço Vazio (€/kWh, s/ IVA)",
                    value=0.1094, step=0.0001, format="%.4f", key="preco_energia_vazio_siva"
                )
            with col_preco2:
                precos_energia_siva['F'] = st.number_input(
                    "Preço Fora Vazio (€/kWh, s/ IVA)",
                    value=0.2008, step=0.0001, format="%.4f", key="preco_energia_foravazio_siva"
                )
        else: # Tri-horário
            col_preco1, col_preco2, col_preco3 = st.columns(3)
            with col_preco1:
                precos_energia_siva['V'] = st.number_input(
                    "Preço Vazio (€/kWh, s/ IVA)",
                    value=0.1094, step=0.0001, format="%.4f", key="preco_energia_vazio_siva_tri"
                )
            with col_preco2:
                precos_energia_siva['C'] = st.number_input(
                    "Preço Cheias (€/kWh, s/ IVA)",
                    value=0.1777, step=0.0001, format="%.4f", key="preco_energia_cheias_siva"
                )
            with col_preco3:
                precos_energia_siva['P'] = st.number_input(
                    "Preço Ponta (€/kWh, s/ IVA)",
                    value=0.2448, step=0.0001, format="%.4f", key="preco_energia_ponta_siva"
                )

        # CONDIÇÃO: A checkbox "Família Numerosa" só aparece para potências <= 6.9 kVA
        is_familia_numerosa = False # Definir como Falso por defeito
        if st.session_state.sel_potencia <= 6.9:
            is_familia_numerosa = st.checkbox("Sou beneficiário de Família Numerosa", key="chk_familia_numerosa")

        st.markdown("##### Modelo de Venda do Excedente")
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
            if simular_novo_cenario and 'df_resultado_simulacao' in st.session_state:
                custo_instalacao = st.number_input("Custo da Nova Instalação / Ampliação (€)", value=2000.0, step=100.0, format="%.2f", key="custo_instalacao")
                
                df_simulado_para_financeiro = st.session_state.df_resultado_simulacao.rename(columns={
                    'Consumo_Rede_kWh': 'Consumo_Rede_Final_kWh',
                    'Excedente_kWh': 'Injecao_Rede_Final_kWh'
                })
                
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

        st.markdown("##### **Resultados Financeiros**")

        # --- Bloco de Apresentação dos Resultados ---
        # CASO 1: Apenas tem UPAC existente (sem simulação)
        if tem_upac_existente and not simular_novo_cenario:
            
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
                st.metric(poupanca_label, f"€ {poupanca_total:.2f}")
                st.caption(f"Por Autoconsumo: € {poupanca_dict['por_autoconsumo']:.2f}")

                st.caption(f"**↳ Preço Médio Compra: € {preco_medio_compra_kwh:.4f}/kWh** (c/IVA)")

                if poupanca_dict['por_venda_excedente'] > 0:
                    st.caption(f"Por Venda de Excedente: € {poupanca_dict['por_venda_excedente']:.2f}")
                
                if financeiro_atual['receita_venda'] > 0:
                    st.caption(f"**↳ Preço Médio Venda: € {financeiro_atual['preco_medio_venda']:.4f}/kWh**")
                                
            with col_res_fin2:
                st.metric("Balanço Energético Atual", f"€ {financeiro_atual['balanco_final']:.2f}")
                st.caption(f"Custo Compra: € {financeiro_atual['custo_compra_c_iva']:.2f}")
                st.caption(f"**↳ Preço Médio Compra: € {preco_medio_compra_kwh:.4f}/kWh** (c/IVA)")

                if financeiro_atual['receita_venda'] > 0:
                    st.caption(f"Receita Venda: € {financeiro_atual['receita_venda']:.2f}")
                    st.caption(f"**↳ Preço Médio Venda: € {financeiro_atual['preco_medio_venda']:.4f}/kWh**")

        # CASO 2: Tem simulação ativa
        elif simular_novo_cenario and 'financeiro_simulado' in st.session_state:
            financeiro_atual = st.session_state.financeiro_atual
            financeiro_simulado = st.session_state.financeiro_simulado
            
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

                st.metric(poupanca_existente_label, f"€ {poupanca_existente_total:.2f}")
                st.caption(f"Por Autoconsumo: € {poupanca_dict_existente['por_autoconsumo']:.2f}")
                st.caption(f"**↳ Preço Médio Compra: € {preco_medio_compra_atual_kwh:.4f}/kWh** (c/IVA)")
                if poupanca_dict_existente['por_venda_excedente'] > 0:
                    st.caption(f"Por Venda de Excedente: € {poupanca_dict_existente['por_venda_excedente']:.2f}")
                if financeiro_atual['receita_venda'] > 0:
                    st.caption(f"**↳ Preço Médio Venda: € {financeiro_atual['preco_medio_venda']:.4f}/kWh**")
                st.markdown("---") 

            # Cálculos da poupança da simulação
            poupanca_simulacao = financeiro_atual['balanco_final'] - financeiro_simulado['balanco_final']
            poupanca_anual_simulacao = poupanca_simulacao * (365.25 / dias) if dias > 0 else 0
            payback_anos = custo_instalacao / poupanca_anual_simulacao if poupanca_anual_simulacao > 0 else float('inf')
            
            # --- LÓGICA CORRIGIDA PARA A ETIQUETA ---
            if tem_upac_existente:
                # Se já havia UPAC, a poupança é "Adicional"
                poupanca_label = f"Poupança Adicional ({dias} dias)"
                if 28 <= dias <= 31: poupanca_label = "Poupança Adicional Mensal"
                elif 350 <= dias <= 380: poupanca_label = "Poupança Adicional Anual"
            else:
                # Se não havia UPAC, a poupança é a "da UPAC"
                poupanca_label = f"Poupança da UPAC ({dias} dias)"
                if 28 <= dias <= 31: poupanca_label = "Poupança Mensal da UPAC"
                elif 350 <= dias <= 380: poupanca_label = "Poupança Anual da UPAC"
            # --- FIM DA LÓGICA CORRIGIDA ---

            # Calcular preços médios para os balanços
            consumo_rede_atual = st.session_state.analise_real.get('consumo_rede', 0)
            preco_medio_compra_atual = (financeiro_atual['custo_compra_c_iva'] / consumo_rede_atual) if consumo_rede_atual > 0 else 0

            df_simulado_ref = st.session_state.df_resultado_simulacao
            consumo_rede_simulado = df_simulado_ref['Consumo_Rede_kWh'].sum()
            preco_medio_compra_simulado = (financeiro_simulado['custo_compra_c_iva'] / consumo_rede_simulado) if consumo_rede_simulado > 0 else 0

            col_res_fin1, col_res_fin2, col_res_fin3 = st.columns(3)
            with col_res_fin1:
                st.metric("Balanço Energético Atual", f"€ {financeiro_atual['balanco_final']:.2f}")
                st.caption(f"Custo Compra: € {financeiro_atual['custo_compra_c_iva']:.2f}")
                st.caption(f"**↳ Preço Médio Compra: € {preco_medio_compra_atual:.4f}/kWh** (c/IVA)")
                if financeiro_atual['receita_venda'] > 0:
                    st.caption(f"Receita Venda: € {financeiro_atual['receita_venda']:.2f}")
                    st.caption(f"**↳ Preço Médio Venda: € {financeiro_atual['preco_medio_venda']:.4f}/kWh**")

            with col_res_fin2:
                st.metric("Balanço Energético Simulado", f"€ {financeiro_simulado['balanco_final']:.2f}")
                st.caption(f"Custo Compra: € {financeiro_simulado['custo_compra_c_iva']:.2f}")
                st.caption(f"**↳ Preço Médio Compra: € {preco_medio_compra_simulado:.4f}/kWh** (c/IVA)")
                if financeiro_simulado['receita_venda'] > 0:
                    st.caption(f"Receita Venda: € {financeiro_simulado['receita_venda']:.2f}")
                    st.caption(f"**↳ Preço Médio Venda: € {financeiro_simulado['preco_medio_venda']:.4f}/kWh**")

            with col_res_fin3:
                # Usar a nova variável 'poupanca_label' que tem o texto correto
                st.metric(poupanca_label, f"€ {poupanca_simulacao:.2f}")
                st.metric("Payback Simples (Anos)", f"{payback_anos:.1f}" if payback_anos != float('inf') else "N/A")

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

        if is_trifasico:
            potencia_a_comparar *= 3
            nota_trifasico = "(estimativa para 3 fases)"

        col_p1, col_p2, col_p3 = st.columns(3)
        # ALTERAÇÃO: st.session_state.sel_potencia contém a potência selecionada
        potencia_contratada_valor = st.session_state.sel_potencia
        
        col_p1.metric("Potência Contratada", f"{potencia_contratada_valor} kVA")
        col_p2.metric(f"Pico Máximo Registado {nota_trifasico}", f"{potencia_a_comparar:.3f} kW")

        percentagem_uso = (potencia_a_comparar / potencia_contratada_valor) * 100 if potencia_contratada_valor > 0 else 0
        
        recomendacao = ""
        if percentagem_uso > 100:
            recomendacao = f"🔴 **Atenção:** O seu pico de consumo ({potencia_a_comparar:.2f} kW) ultrapassa a sua potência contratada. Considere aumentar a potência."
        elif percentagem_uso > 85:
            recomendacao = f"✅ **Adequado:** A sua potência contratada parece bem dimensionada."
        elif percentagem_uso > 60:
            recomendacao = f"💡 **Oportunidade de Poupança:** O seu pico de consumo utiliza entre 60% e 85% da potência contratada. Pode ser possível reduzir a potência."
        else:
            recomendacao = f"💰 **Forte Oportunidade de Poupança:** O seu pico de consumo utiliza menos de 60% da sua potência contratada. É muito provável que possa reduzir a potência e poupar na fatura."

        col_p3.metric("Utilização do Pico", f"{percentagem_uso:.1f} %")
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
