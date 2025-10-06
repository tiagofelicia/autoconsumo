import streamlit as st
import json
import pandas as pd
from fpdf import FPDF
from datetime import datetime
from pathlib import Path
import io
import matplotlib.pyplot as plt
from pathlib import Path
import numpy as np
import requests

# --- CONSTANTES GLOBAIS PARA GRÁFICOS ---
NOMES_PERIODOS = {'V': 'Vazio', 'F': 'Fora Vazio', 'C': 'Cheias', 'P': 'Ponta'}
CORES_CONSUMO_DIARIO = {'V_bi': '#A9D18E', 'V_tri': '#BF9000', 'F': '#E2EFDA', 'C': '#FFE699', 'P': '#FFF2CC'}
CORES_CONSUMO_SEMANAL = {'V_bi': '#8FAADC', 'V_tri': '#C55A11', 'F': '#DAE3F3', 'C': '#F4B183', 'P': '#FBE5D6'}
COR_INJECAO = "#9966CC"
CORES_OMIE = {'S': '#FF0000','V': '#000000', 'F': '#FFC000', 'C': '#2F5597', 'P': '#00B050'}


def formatar_numero_pt(numero, casas_decimais=2, sufixo=""):
    """Formata um número para o padrão português (ex: 1 234,56)."""
    try:
        # Primeiro, formata com um ponto decimal e vírgula para milhares (padrão US)
        # Depois, substitui a vírgula por um espaço e o ponto por uma vírgula.
        formatado = f"{numero:,.{casas_decimais}f}".replace(",", " ").replace(".", ",")
        return f"{formatado}{sufixo}"
    except (ValueError, TypeError):
        return f"-{sufixo}"

def gerar_imagem_grafico_barras(dados, titulo, label_y, label_x='Cenários'):
    """Cria um gráfico de barras simples com matplotlib e retorna-o como bytes de uma imagem PNG."""
    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(10, 4))

    nomes = [item['name'] for item in dados]
    valores = [item['y'] for item in dados]

    ax.barh(nomes, valores, color='#007acc')

    ax.set_xlabel(label_y)
    ax.set_title(titulo, loc='left', fontsize=12, pad=10)
    ax.invert_yaxis() # O melhor resultado no topo
    ax.grid(axis='x', linestyle='--', alpha=0.7)
    ax.grid(axis='y', linestyle='', alpha=0)

    # Adicionar os valores no final das barras
    for i, v in enumerate(valores):
        ax.text(v + (max(valores) * 0.01), i, f" {v:,.1f}".replace(",", " ").replace(".", ","), va='center', color='black')

    fig.tight_layout()

    # Guardar a imagem num buffer de memória
    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format='png', dpi=150)
    plt.close(fig)
    img_buffer.seek(0)

    return img_buffer

def gerar_imagem_grafico_linha(anos, valores, titulo, label_y, label_x='Ano'):
    """Cria um gráfico de linha simples com matplotlib e retorna-o como bytes de uma imagem PNG."""
    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(10, 4))
    
    ax.plot(anos, valores, marker='o', linestyle='-', color='#007acc', linewidth=2, markersize=4)
    
    ax.set_xlabel(label_x)
    ax.set_ylabel(label_y)
    ax.set_title(titulo, loc='left', fontsize=12, pad=10)
    ax.grid(True, linestyle='--', alpha=0.7)
    
    # Adicionar linha horizontal no zero para referência
    ax.axhline(0, color='grey', linewidth=0.8, linestyle='--')

    fig.tight_layout()
    
    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format='png', dpi=150)
    plt.close(fig)
    img_buffer.seek(0)
    
    return img_buffer

def gerar_imagem_grafico_barras_agrupadas(dados_custos_mensais, titulo="Comparação de Custos Mensais (€)", label_y="Custo (€)"):
    """
    Cria um gráfico de barras agrupadas para comparar custos mensais entre cenários.
    Retorna a imagem PNG em bytes.
    """
    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(12, 6)) # Aumentar o tamanho para mais detalhes

    meses = dados_custos_mensais['meses']
    series = dados_custos_mensais['series']
    num_series = len(series)

    # Posições para as barras
    x = np.arange(len(meses))
    width = 0.8 / num_series # Largura de cada barra dentro do grupo

    # Cores personalizadas para as barras (pode ajustar)
    cores = ['#007acc', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']

    for i, serie in enumerate(series):
        offset = width * i - (width * (num_series - 1) / 2) # Calcula o offset para agrupar
        ax.bar(x + offset, serie['data'], width, label=serie['name'], color=cores[i % len(cores)])

    ax.set_ylabel(label_y)
    ax.set_title(titulo, loc='left', fontsize=14, pad=15)
    ax.set_xticks(x)
    ax.set_xticklabels(meses, rotation=45, ha='right')
    ax.legend(title="Cenário", bbox_to_anchor=(1.05, 1), loc='upper left')
    ax.grid(axis='x', linestyle='', alpha=0) # Remover grid vertical
    ax.grid(axis='y', linestyle='--', alpha=0.7)

    fig.tight_layout()
    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format='png', dpi=150)
    plt.close(fig)
    img_buffer.seek(0)
    
    return img_buffer

# --- Função: Formatação semelhante a st.info ---
def exibir_info_personalizada(mensagem):
    """Gera uma caixa de informação com estilo customizado."""
    st.markdown(f"""
    <div style='
        background-color: #d9edf7;
        padding: 8px;
        border-left: 5px solid #31708f;
        border-radius: 5px;
        color: #31708f;
        font-size: 0.9rem
        line-height: 1.2;
        margin-top: 5px;
        margin-bottom: 5px;
        '>
        {mensagem}
    </div>
    """,
    unsafe_allow_html=True)

# --- Função: Formatação semelhante a st.metric ---
def exibir_metrica_personalizada(label, value):
    """Gera uma caixa de métrica com estilo customizado e adaptável aos temas."""
    # Usando as variáveis de tema do Streamlit para compatibilidade automática com modo claro/escuro
    html_content = f"""
    <div style="
        padding: 10px; 
        border: 1px solid var(--secondary-background-color); /* Borda que se adapta ao tema */
        border-radius: 6px;      
        text-align: center;      
        background-color: var(--secondary-background-color); /* Fundo que se adapta */
    ">
        <div style="font-size: 0.9rem; color: var(--text-color); opacity: 0.7; text-align: center;">{label}</div>
        <div style="font-size: 1.2rem; color: var(--text-color); text-align: center;">{value}</div>
    </div>
    """
    st.markdown(html_content, unsafe_allow_html=True)

@st.cache_data
def preparar_dados_para_graficos(df_consumos_filtrado, df_omie_filtrado, opcao_horaria_selecionada, dias_periodo):
    """
    Prepara os dados para gráficos de consumo (empilhado) e injeção (separado), lado a lado.
    """
    if df_consumos_filtrado.empty or df_omie_filtrado.empty:
        return None, None

    df_merged = pd.merge(df_consumos_filtrado, df_omie_filtrado, on='DataHora', how='inner')
    if df_merged.empty:
        st.warning("Não foi possível alinhar dados de consumo e OMIE para os gráficos.")
        return None, None
    
    # --- Lógica do Título do Ciclo e Períodos ---
    oh_lower = opcao_horaria_selecionada.lower()
    titulo_ciclo = "Simples"
    ciclo_a_usar = None
    periodos_ciclo = []

    cores_consumo_a_usar = CORES_CONSUMO_DIARIO if "diário" in oh_lower else CORES_CONSUMO_SEMANAL

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

    # --- Gráfico Horário ---
    df_horario = df_merged.copy()
    df_horario['HoraParaAgrupar'] = (df_horario['DataHora'] - pd.Timedelta(seconds=1)).dt.hour
    series_horario = []
    
    # 1. Agregação do Consumo (igual a antes)
    if not ciclo_a_usar:
        agg_horario_consumo = df_horario.groupby('HoraParaAgrupar')['Consumo (kWh)'].sum().reindex(range(24), fill_value=0)
        series_horario.append({"name": "Consumo da Rede", "type": "column", "data": agg_horario_consumo.round(3).tolist(), "yAxis": 0, "color": "#BFBFBF", "stack": "consumo"})
    else:
        agg_consumo_periodo = df_horario.groupby(['HoraParaAgrupar', ciclo_a_usar])['Consumo (kWh)'].sum().unstack(fill_value=0)
        for p in reversed(periodos_ciclo):
            if p in agg_consumo_periodo.columns:
                dados_p = agg_consumo_periodo[p].reindex(range(24), fill_value=0)
                cor_key = 'V_tri' if p == 'V' and oh_lower.startswith("tri") else ('V_bi' if p == 'V' else p)
                cor_a_usar = cores_consumo_a_usar.get(cor_key)
                series_horario.append({"name": f"Consumo {NOMES_PERIODOS.get(p, p)}", "type": "column", "data": dados_p.round(3).tolist(), "yAxis": 0, "color": cor_a_usar, "stack": "consumo"})

    # 2. Agregação da Injeção (nova série, com stack diferente)
    agg_horario_injecao = df_horario.groupby('HoraParaAgrupar')['Injecao_Rede_kWh'].sum().reindex(range(24), fill_value=0)
    if agg_horario_injecao.sum() > 0:
        series_horario.append({
            "name": "Excedente (para venda)", "type": "column", 
            "data": agg_horario_injecao.round(3).tolist(), # Valores positivos
            "yAxis": 0, "color": COR_INJECAO, "stack": "injecao" # Stack diferente para ficar ao lado
        })

    # 3. Séries OMIE Diárias
    agg_omie_horario_simples = df_horario.groupby('HoraParaAgrupar')['OMIE'].mean().reindex(range(24))
    dados_omie_simples_final = agg_omie_horario_simples.round(2).where(pd.notna(agg_omie_horario_simples), None).tolist() # Converte NaN para None
    series_horario.append({
        "name": "Média horária OMIE (€/MWh)", "type": "line", 
        "data": dados_omie_simples_final, "yAxis": 1, "color": CORES_OMIE.get('S')
    })
    
    if ciclo_a_usar:
        agg_omie_horario_periodos = df_horario.groupby(['HoraParaAgrupar', ciclo_a_usar])['OMIE'].mean().unstack()
        for p in periodos_ciclo:
            if p in agg_omie_horario_periodos.columns:
                dados_omie_p = agg_omie_horario_periodos[p].reindex(range(24))
                dados_omie_p_final = dados_omie_p.round(2).where(pd.notna(dados_omie_p), None).tolist() # Converte NaN para None
                series_horario.append({
                    "name": f"Média OMIE {NOMES_PERIODOS.get(p, p)} (€/MWh)", "type": "line",
                    "data": dados_omie_p_final, "yAxis": 1, 
                    "color": CORES_OMIE.get(p), "visible": False
                })

    dados_grafico_horario = {
        'titulo': f'Consumo & Excedente por Hora vs. Preço OMIE Horário ({titulo_ciclo})',
        'titulo_eixo_y1': 'Energia (kWh)',
        'titulo_eixo_y2': 'Média horária OMIE (€/MWh)',
        'categorias': [f"{h}h-24h" if h == 23 else f"{h}h-{h + 1}h" for h in range(24)],
        'series': series_horario
    }

    # --- Gráfico Diário ---
    df_diario = df_merged.copy()
    df_diario['data_dia'] = pd.to_datetime(df_diario['DataHora'].dt.date)
    categorias_diario = sorted(df_diario['data_dia'].unique())
    series_diario = []

    agg_diario_base = df_diario.groupby('data_dia').agg(
        Consumo_kWh=('Consumo (kWh)', 'sum'),
        Media_OMIE_Simples=('OMIE', 'mean')
    ).sort_index()

    # 1. Consumo Diário (igual a antes)
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
                    "name": f"Consumo {NOMES_PERIODOS.get(p, p)} (kWh)", "type": "column",
                    "data": agg_consumo_periodos[p].round(2).where(pd.notna, None).tolist(),
                    "yAxis": 0, "color": cor_a_usar
                })
                    
    # 2. Injeção Diária
    agg_diario_injecao = df_diario.groupby('data_dia')['Injecao_Rede_kWh'].sum().reindex(categorias_diario, fill_value=0)
    if agg_diario_injecao.sum() > 0:
        series_diario.append({"name": "Excedente (para venda)", "type": "column", "data": agg_diario_injecao.round(3).tolist(), "yAxis": 0, "color": COR_INJECAO, "stack": "injecao"})
        
    # 3. Séries OMIE Diárias (mantêm-se iguais)
    dados_omie_diario_simples_final = agg_diario_base['Media_OMIE_Simples'].round(2).where(pd.notna(agg_diario_base['Media_OMIE_Simples']), None).tolist()
    series_diario.append({"name": "Média diária OMIE (€/MWh)", "type": "line", "data": dados_omie_diario_simples_final, "yAxis": 1, "color": CORES_OMIE.get('S')})
    
    if ciclo_a_usar:
        agg_omie_periodos = df_diario.groupby(['data_dia', ciclo_a_usar])['OMIE'].mean().unstack()
        agg_omie_periodos = agg_omie_periodos.reindex(agg_diario_base.index)
        for p in periodos_ciclo:
            if p in agg_omie_periodos.columns:
                dados_omie_p_diario_final = agg_omie_periodos[p].round(2).where(pd.notna(agg_omie_periodos[p]), None).tolist()
                series_diario.append({
                    "name": f"Média OMIE {NOMES_PERIODOS.get(p, p)} (€/MWh)", "type": "line",
                    "data": dados_omie_p_diario_final,
                    "yAxis": 1, "color": CORES_OMIE.get(p), "visible": False
                })

    dados_grafico_diario = {
        'titulo': f'Consumo & Excedente Diário vs. Preço Médio OMIE ({titulo_ciclo})',
        'titulo_eixo_y1': 'Energia (kWh)',
        'titulo_eixo_y2': 'Média diária OMIE (€/MWh)',
        'categorias': agg_diario_base.index.strftime('%d/%m/%Y').tolist(),
        'series': series_diario
    }
    
    return dados_grafico_horario, dados_grafico_diario

def gerar_grafico_highcharts(chart_id, chart_data):
    """
    Gera o código HTML/JS para um gráfico de consumo (empilhado) e injeção (agrupado).
    """
    categorias_json = json.dumps(chart_data['categorias'])
    series_json = json.dumps(chart_data['series'])
    titulo_grafico = chart_data['titulo']
    titulo_eixo_y1 = chart_data['titulo_eixo_y1']
    titulo_eixo_y2 = chart_data['titulo_eixo_y2']

    html_code = f"""
    <html>
    <head>
        <script src="https://code.highcharts.com/highcharts.js"></script>
        <style>
            #{chart_id} {{ height: 600px; margin: 0 auto; }}
        </style>
    </head>
    <body>
        <figure class="highcharts-figure"><div id="{chart_id}"></div></figure>
        <script>
            Highcharts.setOptions({{
                lang: {{
                    decimalPoint: ',',
                    thousandsSep: ' '
                }}
            }});
            Highcharts.chart('{chart_id}', {{
                chart: {{ type: 'column', zoomType: 'xy' }},
                title: {{ text: '{titulo_grafico}', align: 'left' }},
                xAxis: [{{ categories: {categorias_json}, crosshair: true }}],
                yAxis: [
                    {{ title: {{ text: '{titulo_eixo_y1}' }}, min: 0, labels: {{ format: '{{value}} kWh' }} }}, 
                    {{ title: {{ text: '{titulo_eixo_y2}' }}, labels: {{ format: '{{value}} €/MWh' }}, opposite: true }}
                ],
                legend: {{ align: 'left', verticalAlign: 'top', y: 40, floating: true, backgroundColor: 'white' }},
                
                plotOptions: {{
                    column: {{
                        stacking: 'normal'
                    }}
                }},
                
                tooltip: {{
                    shared: true,
                    formatter: function () {{
                        //  Usa this.points[0].key para obter a hora/dia, tal como nos outros gráficos
                        let s = '<b>' + (this.points[0] ? this.points[0].key : this.x) + '</b>';
                        let consumoTotal = 0;
                        let omiePoints = [];
                        let consumoPoints = [];
                        let injecaoPoints = [];

                        // Separar os pontos por tipo
                        this.points.forEach(function(point) {{
                            if (point.series.type === 'line') {{
                                omiePoints.push(point);
                            }} else if (point.series.options.stack === 'injecao') {{
                                injecaoPoints.push(point);
                            }} else {{
                                consumoPoints.push(point);
                                if (point.y > 0) {{
                                    consumoTotal += point.y;
                                }}
                            }}
                        }});

                        // 1. Apresentar os detalhes do consumo
                        consumoPoints.forEach(function(point) {{
                             if (point.y > 0.001) {{
                                s += '<br/><span style="color:'+ point.series.color +'">●</span> ' + point.series.name + ': <b>' + Highcharts.numberFormat(point.y, 2) + ' kWh</b>';
                             }}
                        }});
                        // 2. Apresentar o Total do Consumo
                        if (consumoTotal > 0.001) {{
                            s += '<br/><b>Total Consumo: ' + Highcharts.numberFormat(consumoTotal, 2) + ' kWh</b>';
                        }}

                        // 3. Apresentar os detalhes da Injeção
                        injecaoPoints.forEach(function(point) {{
                             if (point.y > 0.001) {{
                                s += '<br/><span style="color:'+ point.series.color +'">●</span> ' + point.series.name + ': <b>' + Highcharts.numberFormat(point.y, 2) + ' kWh</b>';
                             }}
                        }});

                        // 4. Apresentar as linhas OMIE
                        omiePoints.forEach(function(point) {{
                            s += '<br/><span style="color:'+ point.series.color +'">●</span> ' + point.series.name + ': <b>' + Highcharts.numberFormat(point.y, 2) + ' €/MWh</b>';
                        }});

                        return s;
                    }}
                }},
                
                series: {series_json}
            }});
        </script>
    </body>
    </html>
    """
    return html_code


def preparar_dados_dia_semana(df_merged, st_session_state):
    """
    Prepara os dados para gráficos de consumo (empilhado) e injeção (separado), por dia da semana.
    """
    if df_merged.empty:
        return None

    df_semana = df_merged.copy()
    df_semana['dia_da_semana'] = df_semana['DataHora'].dt.dayofweek
    
    
    day_counts = df_semana.groupby(df_semana['DataHora'].dt.date)['dia_da_semana'].first().value_counts().reindex(range(7), fill_value=0)
    
    series_grafico = []
    
    oh_lower = st_session_state.get('sel_opcao_horaria', 'simples').lower()
    
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
    
    cores_consumo_a_usar = CORES_CONSUMO_DIARIO if "diário" in oh_lower else CORES_CONSUMO_SEMANAL
    
    # 1. Agregação do Consumo (lógica semelhante à anterior)
    if ciclo_a_usar and ciclo_a_usar in df_semana.columns:
        consumo_total_periodo = df_semana.groupby(['dia_da_semana', ciclo_a_usar])['Consumo (kWh)'].sum().unstack(fill_value=0)
        for p in reversed(periodos_ciclo):
            if p in consumo_total_periodo.columns:
                dados_p = consumo_total_periodo[p].reindex(range(7), fill_value=0)
                cor_key = 'V_tri' if p == 'V' and oh_lower.startswith("tri") else ('V_bi' if p == 'V' else p)
                cor_a_usar = cores_consumo_a_usar.get(cor_key)
                series_grafico.append({"name": f"Consumo {NOMES_PERIODOS.get(p, p)}", "type": "column", "data": dados_p.round(3).tolist(), "yAxis": 0, "color": cor_a_usar, "stack": "consumo"})
    else:
        agg_total_consumo = df_semana.groupby('dia_da_semana')['Consumo (kWh)'].sum().reindex(range(7), fill_value=0)
        series_grafico.append({"name": "Consumo da Rede", "type": "column", "data": agg_total_consumo.round(3).tolist(), "yAxis": 0, "color": "#BFBFBF", "stack": "consumo"})
    
    # 2. Agregação da Injeção (nova série)
    agg_semana_injecao = df_semana.groupby('dia_da_semana')['Injecao_Rede_kWh'].sum().reindex(range(7), fill_value=0)
    if agg_semana_injecao.sum() > 0:
        series_grafico.append({
            "name": "Excedente (para venda)", "type": "column",
            "data": agg_semana_injecao.round(3).tolist(),
            "yAxis": 0, "color": COR_INJECAO, "stack": "injecao"
        })

    # 3. Adicionar as linhas OMIE
    agg_media_omie_simples = df_semana.groupby('dia_da_semana')['OMIE'].mean().reindex(range(7))
    dados_omie_simples_final = agg_media_omie_simples.round(2).where(pd.notna(agg_media_omie_simples), None).tolist()
    series_grafico.append({
        "name": "Média OMIE (€/MWh)", "type": "line", "data": dados_omie_simples_final, "yAxis": 1, "color": CORES_OMIE.get('S')
    })
    
    if ciclo_a_usar and ciclo_a_usar in df_semana.columns:
        agg_omie_semana_periodos = df_semana.groupby(['dia_da_semana', ciclo_a_usar])['OMIE'].mean().unstack()
        for p in periodos_ciclo:
            if p in agg_omie_semana_periodos.columns:
                dados_omie_p = agg_omie_semana_periodos[p].reindex(range(7))
                dados_omie_p_final = dados_omie_p.round(2).where(pd.notna(dados_omie_p), None).tolist()
                series_grafico.append({
                    "name": f"Média OMIE {NOMES_PERIODOS.get(p, p)} (€/MWh)", "type": "line",
                    "data": dados_omie_p_final, "yAxis": 1, "color": CORES_OMIE.get(p), "visible": False
                })

    return {
        'titulo': f'Consumo & Excedente vs OMIE por Dia da Semana ({titulo_ciclo})',
        'titulo_eixo_y1': 'Energia (kWh)',
        'titulo_eixo_y2': 'Média OMIE (€/MWh)',
        'categorias': ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo'],
        'series': series_grafico
    }


def gerar_grafico_solar(chart_id, chart_data):
    """
    Gera o código HTML/JS para um gráfico Highcharts de Consumo vs. Produção Solar.
    Usa o tipo 'area' para uma melhor visualização da sobreposição.
    """
    # Conversão dos dados Python para JSON, que o JavaScript consegue ler
    categorias_json = json.dumps(chart_data['categorias'])
    series_json = json.dumps(chart_data['series'])
    titulo_grafico = chart_data['titulo']

    # Código HTML e JavaScript para o gráfico
    html_code = f"""
    <html>
    <head>
        <script src="https://code.highcharts.com/highcharts.js"></script>
        <style>
            #{chart_id} {{ height: 400px; margin: 0 auto; }}
        </style>
    </head>
    <body>
        <figure class="highcharts-figure"><div id="{chart_id}"></div></figure>
        <script>
            Highcharts.setOptions({{
                lang: {{
                    decimalPoint: ',',
                    thousandsSep: ' '
                }}
            }});
            Highcharts.chart('{chart_id}', {{
                chart: {{ type: 'area', zoomType: 'x' }},
                title: {{ text: '{titulo_grafico}', align: 'left' }},
                xAxis: {{ 
                    categories: {categorias_json}, 
                    crosshair: true 
                }},
                yAxis: {{
                    title: {{ text: '(kWh)' }},
                    min: 0
                }},
                tooltip: {{
                    shared: true,
                    headerFormat: '<b>Hora: {{point.key}}</b><br>',
                    pointFormat: '<span style="color:{{series.color}}">●</span> {{series.name}}: <b>{{point.y:.3f}} kWh</b><br/>'
                }},
                plotOptions: {{
                    area: {{
                        stacking: null, // As áreas não se sobrepõem, ficam transparentes
                        marker: {{
                            enabled: false,
                            symbol: 'circle',
                            radius: 2,
                            states: {{ hover: {{ enabled: true }} }}
                        }},
                        lineWidth: 2,
                        fillOpacity: 0.2 // Uma ligeira opacidade para ver a sobreposição
                    }}
                }},
                series: {series_json}
            }});
        </script>
    </body>
    </html>
    """
    return html_code


#### Gráficos Mensais ####
def preparar_dados_mensais(df_consumos, st_session_state):
    """
    Prepara os dados para gráficos de consumo (empilhado) e injeção (separado), por mês.
    """
    if df_consumos.empty or 'DataHora' not in df_consumos.columns:
        return None

    df_mensal = df_consumos.copy()
    df_mensal['AnoMes'] = df_mensal['DataHora'].dt.to_period('M')

    if df_mensal['AnoMes'].nunique() <= 1:
        return None

    # --- Lógica para obter ciclo, períodos e cores (mantém-se) ---
    oh_lower = st_session_state.get('sel_opcao_horaria', 'simples').lower()
    
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
    
    cores_consumo_a_usar = CORES_CONSUMO_DIARIO if "diário" in oh_lower else CORES_CONSUMO_SEMANAL
    
    series_grafico = []
    todos_os_meses = sorted(df_mensal['AnoMes'].unique())
    
    # 1. Agregação do Consumo Mensal
    if ciclo_a_usar and ciclo_a_usar in df_mensal.columns:
        consumo_mensal_periodo = df_mensal.groupby(['AnoMes', ciclo_a_usar])['Consumo (kWh)'].sum().unstack(fill_value=0).reindex(todos_os_meses, fill_value=0)
        for p in reversed(periodos_ciclo):
            if p in consumo_mensal_periodo.columns:
                cor_key = 'V_tri' if p == 'V' and oh_lower.startswith("tri") else ('V_bi' if p == 'V' else p)
                cor_a_usar = cores_consumo_a_usar.get(cor_key)
                series_grafico.append({"name": f"Consumo {NOMES_PERIODOS.get(p, p)}", "type": "column", "data": consumo_mensal_periodo[p].round(2).tolist(), "yAxis": 0, "color": cor_a_usar, "stack": "consumo"})
    else:
        consumo_mensal_total = df_mensal.groupby('AnoMes')['Consumo (kWh)'].sum().reindex(todos_os_meses, fill_value=0)
        series_grafico.append({"name": "Consumo da Rede", "type": "column", "data": consumo_mensal_total.round(2).tolist(), "yAxis": 0, "color": "#BFBFBF", "stack": "consumo"})

    # 2. Agregação da Injeção Mensal (nova série)
    agg_mensal_injecao = df_mensal.groupby('AnoMes')['Injecao_Rede_kWh'].sum().reindex(todos_os_meses, fill_value=0)
    if agg_mensal_injecao.sum() > 0:
        series_grafico.append({
            "name": "Excedente (para venda)", "type": "column",
            "data": agg_mensal_injecao.round(3).tolist(),
            "yAxis": 0, "color": COR_INJECAO, "stack": "injecao"
        })

    # 3. Adicionar as linhas OMIE (como antes)
    if 'OMIE' in df_mensal.columns:
        # 1. Média OMIE Simples (sempre visível)
        media_omie_mensal_simples = df_mensal.groupby('AnoMes')['OMIE'].mean().reindex(todos_os_meses)
        dados_omie_simples_finais = media_omie_mensal_simples.round(2).where(pd.notna(media_omie_mensal_simples), None).tolist()
        series_grafico.append({
            "name": "Média OMIE (€/MWh)", "type": "line",
            "data": dados_omie_simples_finais, "yAxis": 1, 
            "color": CORES_OMIE.get('S'), "tooltip": { "valueSuffix": " €/MWh" }
        })

        # 2. Médias OMIE por período (Vazio, Cheias, etc.), escondidas por defeito
        if ciclo_a_usar and ciclo_a_usar in df_mensal.columns:
            media_omie_mensal_periodos = df_mensal.groupby(['AnoMes', ciclo_a_usar])['OMIE'].mean().unstack()
            media_omie_mensal_periodos = media_omie_mensal_periodos.reindex(todos_os_meses)
            
            for p in periodos_ciclo:
                if p in media_omie_mensal_periodos.columns:
                    dados_omie_p = media_omie_mensal_periodos[p]
                    dados_omie_p_finais = dados_omie_p.round(2).where(pd.notna(dados_omie_p), None).tolist()
                    series_grafico.append({
                        "name": f"Média OMIE {NOMES_PERIODOS.get(p, p)} (€/MWh)",
                        "type": "line",
                        "data": dados_omie_p_finais,
                        "yAxis": 1,
                        "color": CORES_OMIE.get(p),
                        "visible": False, # <-- ESCONDIDO POR DEFEITO
                        "tooltip": { "valueSuffix": " €/MWh" }
                    })
    
    categorias_eixo_x = [mes.strftime('%b %Y') for mes in todos_os_meses]

    return {
        'titulo': f'Consumo & Excedente vs OMIE Mensal ({titulo_ciclo})',
        'titulo_eixo_y1': 'Energia (kWh)',
        'titulo_eixo_y2': 'Média Mensal OMIE (€/MWh)',
        'categorias': categorias_eixo_x,
        'series': series_grafico
    }

# FUNÇÃO criar_tabela_analise_completa_html
def criar_tabela_analise_completa_html(consumos_agregados, omie_agregados):
    """
    Gera uma tabela HTML detalhada, com cores personalizadas de fundo e texto
    que se adaptam ao tema claro/escuro do Streamlit.
    """
    
    # --- Deteção do Tema Atual do Streamlit ---
    is_dark_theme = st.get_option('theme.base') == 'dark'

    # --- Definição de DUAS paletas de cores ---
    
    # Paleta para o Tema Claro (a sua original)
    cores_light = {
        'header': {
            'S':  {'bg': '#A6A6A6'}, 'BD': {'bg': '#A9D08E'}, 'BS': {'bg': '#8EA9DB'},
            'TD': {'bg': '#BF8F00', 'text': '#FFFFFF'}, 'TS': {'bg': '#C65911', 'text': '#FFFFFF'}
        },
        'cell': {
            'S':    {'bg': '#D9D9D9'},
            'BD_V': {'bg': '#C6E0B4'}, 'BD_F': {'bg': '#E2EFDA'},
            'BS_V': {'bg': '#B4C6E7'}, 'BS_F': {'bg': '#D9E1F2'},
            'TD_V': {'bg': '#FFD966'}, 'TD_C': {'bg': '#FFE699'}, 'TD_P': {'bg': '#FFF2CC'},
            'TS_V': {'bg': '#F4B084'}, 'TS_C': {'bg': '#F8CBAD'}, 'TS_P': {'bg': '#FCE4D6'}
        }
    }
    
    # Paleta para o Tema Escuro ( cores com melhor contraste)
    cores_dark = {
        'header': {
            'S':  {'bg': '#5A5A5A'}, 'BD': {'bg': '#4B6140'}, 'BS': {'bg': '#3E4C6D'},
            'TD': {'bg': '#8C6600'}, 'TS': {'bg': '#95430D'}
        },
        'cell': {
            'S':    {'bg': '#404040'},
            'BD_V': {'bg': '#384E30'}, 'BD_F': {'bg': '#2E3F27'},
            'BS_V': {'bg': '#2D3850'}, 'BS_F': {'bg': '#242C40'},
            'TD_V': {'bg': '#665000'}, 'TD_C': {'bg': '#594600'}, 'TD_P': {'bg': '#4D3C00'},
            'TS_V': {'bg': '#6F3A1D'}, 'TS_C': {'bg': '#613319'}, 'TS_P': {'bg': '#542C15'}
        }
    }

    # --- Selecionar a paleta e cores de base com base no tema ---
    if is_dark_theme:
        cores = cores_dark
        row_label_bg = '#1E2128'   # Fundo escuro para os rótulos
        row_label_text = '#FFFFFF' # Texto branco
        border_color = '#3E414B'   # Borda mais escura
    else:
        cores = cores_light
        row_label_bg = '#f8f9fa'   # O seu fundo claro original
        row_label_text = '#212529' # Texto preto
        border_color = '#999'      # A sua borda original

    # --- Geração do CSS (agora usa as variáveis de cor dinâmicas) ---
    html = "<style>"
    html += ".analise-table { width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 13px; font-family: sans-serif; text-align: center; }"
    # --- ALTERADO: Usa a cor da borda dinâmica ---
    html += f".analise-table th, .analise-table td {{ padding: 8px 10px; border: 1px solid {border_color}; }}"
    html += ".analise-table thead th { font-weight: bold; }"
    html += ".analise-table .header-main { vertical-align: middle; }"
    # --- ALTERADO: Usa as cores de fundo e texto dinâmicas para os rótulos das linhas ---
    html += f".analise-table .row-label {{ text-align: center; font-weight: bold; background-color: {row_label_bg}; color: {row_label_text}; }}"
    
    # Este loop agora usa a paleta de cores correta (clara ou escura)
    for tipo_estilo, mapa_cores in cores.items():
        for chave, config_cor in mapa_cores.items():
            cor_fundo = config_cor['bg']
            cor_texto = config_cor.get('text')
            
            if not cor_texto: # A sua lógica de contraste continua perfeita!
                try:
                    r, g, b = int(cor_fundo[1:3], 16), int(cor_fundo[3:5], 16), int(cor_fundo[5:7], 16)
                    cor_texto = '#000000' if (r*0.299 + g*0.587 + b*0.114) > 140 else '#FFFFFF'
                except:
                    cor_texto = '#000000' if is_dark_theme else '#FFFFFF' # Fallback adaptado
            
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
            return f"{float(n):,.{casas_decimais}f}".replace(",", " ").replace(".", ",") + sufixo
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


def criar_tabela_comparativa_html(consumos_agregados_inicial, consumos_agregados_simulado):
    """
    Gera uma tabela HTML comparativa detalhada que se adapta
    ao tema claro/escuro do Streamlit.
    """
    
    # --- Deteção do Tema Atual do Streamlit ---
    is_dark_theme = st.get_option('theme.base') == 'dark'

    # --- Definição de DUAS paletas de cores ---

    # Paleta para o Tema Claro (a sua original)
    cores_light = {
        'header': {
            'S':  {'bg': '#A6A6A6'}, 'BD': {'bg': '#A9D08E'}, 'BS': {'bg': '#8EA9DB'},
            'TD': {'bg': '#BF8F00', 'text': '#FFFFFF'}, 'TS': {'bg': '#C65911', 'text': '#FFFFFF'}
        },
        'cell_light': {
            'S': {'bg': '#D9D9D9'}, 'BD_V': {'bg': '#C6E0B4'}, 'BD_F': {'bg': '#E2EFDA'},
            'BS_V': {'bg': '#B4C6E7'}, 'BS_F': {'bg': '#D9E1F2'}, 'TD_V': {'bg': '#FFD966'},
            'TD_C': {'bg': '#FFE699'}, 'TD_P': {'bg': '#FFF2CC'}, 'TS_V': {'bg': '#F4B084'},
            'TS_C': {'bg': '#F8CBAD'}, 'TS_P': {'bg': '#FCE4D6'}
        },
        'cell_dark': { # Para o efeito de linhas alternadas (zebra)
            'S': {'bg': '#C0C0C0'}, 'BD_V': {'bg': '#B5D6A3'}, 'BD_F': {'bg': '#D1E6CA'},
            'BS_V': {'bg': '#A3B8D6'}, 'BS_F': {'bg': '#C8D2E7'}, 'TD_V': {'bg': '#F0CF5A'},
            'TD_C': {'bg': '#F0D68A'}, 'TD_P': {'bg': '#F0E7BE'}, 'TS_V': {'bg': '#E9A06F'},
            'TS_C': {'bg': '#EBB99C'}, 'TS_P': {'bg': '#F0D8C9'}
        }
    }

    # Paleta para o Tema Escuro
    cores_dark = {
        'header': {
            'S':  {'bg': '#5A5A5A'}, 'BD': {'bg': '#4B6140'}, 'BS': {'bg': '#3E4C6D'},
            'TD': {'bg': '#8C6600'}, 'TS': {'bg': '#95430D'}
        },
        'cell_light': { # Linhas "claras" no modo escuro
            'S': {'bg': '#333333'}, 'BD_V': {'bg': '#2E3F27'}, 'BD_F': {'bg': '#2E3F27'},
            'BS_V': {'bg': '#242C40'}, 'BS_F': {'bg': '#242C40'}, 'TD_V': {'bg': '#4D3C00'},
            'TD_C': {'bg': '#4D3C00'}, 'TD_P': {'bg': '#4D3C00'}, 'TS_V': {'bg': '#542C15'},
            'TS_C': {'bg': '#542C15'}, 'TS_P': {'bg': '#542C15'}
        },
        'cell_dark': { # Linhas "escuras" no modo escuro (um pouco diferentes para o efeito zebra)
            'S': {'bg': '#2C2C2C'}, 'BD_V': {'bg': '#384E30'}, 'BD_F': {'bg': '#384E30'},
            'BS_V': {'bg': '#2D3850'}, 'BS_F': {'bg': '#2D3850'}, 'TD_V': {'bg': '#594600'},
            'TD_C': {'bg': '#594600'}, 'TD_P': {'bg': '#594600'}, 'TS_V': {'bg': '#613319'},
            'TS_C': {'bg': '#613319'}, 'TS_P': {'bg': '#613319'}
        }
    }

    # --- Selecionar a paleta e cores de base com base no tema ---
    if is_dark_theme:
        cores = cores_dark
        row_label_bg = '#1E2128'
        row_label_text = '#FFFFFF'
        border_color = '#3E414B'
        diff_pos_color = '#28a745'  # Verde mais vivo
        diff_neg_color = '#FF6666'  # Vermelho claro e legível
    else:
        cores = cores_light
        row_label_bg = '#f2f2f2'
        row_label_text = '#212529'
        border_color = '#999'
        diff_pos_color = '#00b050'  # O seu verde original
        diff_neg_color = '#c00000'  # O seu vermelho original

    # --- Geração do CSS (agora dinâmico) ---
    html = "<style>"
    html += ".comp-table { width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 13px; font-family: sans-serif; text-align: center; }"
    # --- ALTERADO: Usa variáveis de cor ---
    html += f".comp-table th, .comp-table td {{ padding: 6px 8px; border: 1px solid {border_color}; }}"
    html += ".comp-table .header-main { vertical-align: middle; }"
    html += ".comp-table .header-sub { font-weight: bold; }"
    html += f".comp-table .row-label {{ text-align: center; font-weight: bold; background-color: {row_label_bg}; color: {row_label_text}; }}"
    html += f".comp-table .diff-pos {{ color: {diff_pos_color}; }}"
    html += f".comp-table .diff-neg {{ color: {diff_neg_color}; }}"
    
    # Este loop agora usa a paleta de cores correta
    for tipo_estilo, mapa_cores in cores.items():
        for chave, config_cor in mapa_cores.items():
            cor_fundo = config_cor['bg']
            cor_texto = config_cor.get('text')
            if not cor_texto:
                try:
                    r, g, b = int(cor_fundo[1:3], 16), int(cor_fundo[3:5], 16), int(cor_fundo[5:7], 16)
                    cor_texto = '#000000' if (r*0.299 + g*0.587 + b*0.114) > 140 else '#FFFFFF'
                except: cor_texto = '#FFFFFF' if is_dark_theme else '#000000'
            
            if tipo_estilo == 'header': html += f".header-{chave} {{ background-color: {cor_fundo}; color: {cor_texto}; }}"
            elif tipo_estilo == 'cell_light': html += f".cell-light-{chave} {{ background-color: {cor_fundo}; color: {row_label_text}; }}"
            elif tipo_estilo == 'cell_dark': html += f".cell-dark-{chave} {{ background-color: {cor_fundo}; color: {row_label_text}; }}"
    html += "</style>"

    # --- Processamento dos Dados ---
    data = {}
    ciclos_info = {'S': ['S'], 'BD': ['V', 'F'], 'BS': ['V', 'F'], 'TD': ['V', 'C', 'P'], 'TS': ['V', 'C', 'P']}
    for ciclo, periodos in ciclos_info.items():
        total_inicial_ciclo = sum(consumos_agregados_inicial.get(ciclo, {}).values()) if ciclo != 'S' else consumos_agregados_inicial.get('Simples', 0)
        total_simulado_ciclo = sum(consumos_agregados_simulado.get(ciclo, {}).values()) if ciclo != 'S' else consumos_agregados_simulado.get('Simples', 0)
        for periodo in periodos:
            kwh_inicial = consumos_agregados_inicial.get(ciclo, {}).get(periodo, 0) if ciclo != 'S' else total_inicial_ciclo
            kwh_simulado = consumos_agregados_simulado.get(ciclo, {}).get(periodo, 0) if ciclo != 'S' else total_simulado_ciclo
            diff_abs = kwh_simulado - kwh_inicial
            if kwh_inicial > 0: diff_rel = (diff_abs / kwh_inicial) * 100
            elif kwh_simulado > 0: diff_rel = float('inf')
            else: diff_rel = 0.0
            data[f"{ciclo}_{periodo}"] = {'kwh_i': kwh_inicial, 'perc_i': (kwh_inicial / total_inicial_ciclo * 100) if total_inicial_ciclo > 0 else 0, 'kwh_s': kwh_simulado, 'perc_s': (kwh_simulado / total_simulado_ciclo * 100) if total_simulado_ciclo > 0 else 0, 'diff_abs': diff_abs, 'diff_rel': diff_rel}

    # --- Construção da Tabela HTML ---

    # Funções de formatação atualizadas
    def formatar_numero_tabela(valor, casas_decimais=0):
        """Função interna para formatar números no padrão PT."""
        return f"{valor:,.{casas_decimais}f}".replace(",", " ").replace(".", ",")

    def formatar_diff(valor, casas_decimais=0):
        valor_str = formatar_numero_tabela(valor, casas_decimais)
        if valor > 0.001: return f"<span class='diff-pos'>+{valor_str}</span>"
        if valor < -0.001: return f"<span class='diff-neg'>{valor_str}</span>"
        return valor_str

    def formatar_diff_rel(valor):
        if valor == float('inf'): return "<span class='diff-pos'>+inf</span>"
        return formatar_diff(valor, 1)

    html += "<table class='comp-table'>"
    html += "<thead><tr><th rowspan='2'>Métrica</th>"
    for ciclo, nome in [('S', 'Simples'), ('BD', 'Bi-horário Diário'), ('BS', 'Bi-horário Semanal'), ('TD', 'Tri-horário Diário'), ('TS', 'Tri-horário Semanal')]:
        html += f"<th colspan='{len(ciclos_info[ciclo])}' class='header-main header-{ciclo}'>{nome}</th>"
    html += "</tr><tr class='header-sub'>"
    nomes_periodos = {'S': 'Total', 'V': 'Vazio', 'F': 'Fora Vazio', 'C': 'Cheias', 'P': 'Ponta'}
    for ciclo in ['S', 'BD', 'BS', 'TD', 'TS']:
        for p in ciclos_info[ciclo]:
            nome_p = nomes_periodos.get(p, p)
            chave_classe = f"{ciclo}_{p}" if ciclo != 'S' else 'S'
            html += f"<th class='cell-light-{chave_classe}'>{nome_p}</th>"
    html += "</tr></thead><tbody>"

    # Lista de métricas
    metricas = [
        ('Consumo Inicial (kWh)', 'kwh_i', 0, '', False),
        ('Consumo Inicial (%)', 'perc_i', 1, '', False),
        ('Consumo Simulado (kWh)', 'kwh_s', 0, '', False),
        ('Consumo Simulado (%)', 'perc_s', 1, '', False),
        ('Diferença (kWh)', 'diff_abs', 0, '', True),
        ('Diferença (%)', 'diff_rel', 1, '', True)
    ]

    for i, (label, chave, decimais, sufixo, is_diff) in enumerate(metricas):
        cor_base = 'dark' if i % 2 else 'light'
        html += f"<tr><td class='row-label'>{label}</td>"
        for ciclo in ['S', 'BD', 'BS', 'TD', 'TS']:
            for periodo in ciclos_info[ciclo]:
                valor = data[f"{ciclo}_{periodo}"][chave]
                chave_classe = f"{ciclo}_{periodo}" if ciclo != 'S' else 'S'
                classe_celula = f"cell-{cor_base}-{chave_classe}"
                if not is_diff:
                    valor_formatado = f"{valor:,.{decimais}f}".replace(',', ' ').replace('.', ',')
                    html += f"<td class='{classe_celula}'>{valor_formatado}</td>"
                else:
                    is_percent_row = (chave == 'diff_rel')
                    formatador = formatar_diff_rel if is_percent_row else lambda v: formatar_diff(v, decimais)
                    html += f"<td class='{classe_celula}'>{formatador(valor)}</td>"
        html += "</tr>"
    
    html += "</tbody></table>"
    return html

def gerar_grafico_bateria(chart_id, chart_data):
    """
    Gera o código HTML/JS para um gráfico Highcharts do comportamento da bateria.
    Mostra o Estado de Carga (SoC) como área e o Fluxo (Carga/Descarga) como colunas.
    """
    categorias_json = json.dumps(chart_data['categorias'])
    series_json = json.dumps(chart_data['series'])
    titulo_grafico = chart_data['titulo']
    capacidade_util = chart_data['capacidade_util']

    html_code = f"""
    <html>
    <head>
        <script src="https://code.highcharts.com/highcharts.js"></script>
        <style>
            #{chart_id} {{ height: 400px; margin: 0 auto; }}
        </style>
    </head>
    <body>
        <figure class="highcharts-figure"><div id="{chart_id}"></div></figure>
        <script>
            Highcharts.setOptions({{
                lang: {{
                    decimalPoint: ',',
                    thousandsSep: ' '
                }}
            }});
            Highcharts.chart('{chart_id}', {{
                chart: {{ zoomType: 'x' }},
                title: {{ text: '{titulo_grafico}', align: 'left' }},
                xAxis: [{{ categories: {categorias_json}, crosshair: true }}],
                yAxis: [
                    {{ 
                        title: {{ text: 'Estado de Carga (SoC)' }},
                        labels: {{ format: '{{value}} kWh' }},
                        max: {capacidade_util}
                    }}, 
                    {{ 
                        title: {{ text: 'Fluxo da Bateria (kW)' }},
                        labels: {{ format: '{{value}} kW' }},
                        opposite: true
                    }}
                ],
                
                tooltip: {{
                    shared: true,
                    formatter: function () {{
                        try {{
                            // Acede diretamente à "chave" da categoria a partir do primeiro ponto de dados.
                            let s = '<b>Hora: ' + this.points[0].key + '</b>';
                            
                            this.points.forEach(function (point) {{
                                let unit = '';
                                if (point.series.yAxis.index === 0) {{
                                    unit = ' kWh';
                                }} else if (point.series.yAxis.index === 1) {{
                                    unit = ' kW';
                                }}
                                
                                s += '<br/><span style="color:'+ point.series.color +'">●</span> ' 
                                   + point.series.name + ': <b>' + point.y.toFixed(2) + unit + '</b>';
                            }});
                            return s;
                        }} catch (e) {{
                            console.error("Erro no tooltip da bateria:", e);
                            return "Erro ao gerar tooltip."
                            
                        }}
                    }}
                }},

                series: {series_json}
            }});
        </script>
    </body>
    </html>
    """
    return html_code

def gerar_grafico_comparacao_custos(chart_id, chart_data):
    """
    Gera o código HTML/JS para um gráfico de barras comparativo dos custos mensais
    para múltiplos cenários.
    """
    categorias_json = json.dumps(chart_data['meses'])
    # Agora, as séries vêm prontas da função de cálculo
    series_json = json.dumps(chart_data['series'])

    html_code = f"""
    <html>
    <head>
        <script src="https://code.highcharts.com/highcharts.js"></script>
        <style>
            #{chart_id} {{ height: 400px; margin: 0 auto; }}
        </style>
    </head>
    <body>
        <figure class="highcharts-figure"><div id="{chart_id}"></div></figure>
        <script>
            Highcharts.setOptions({{
                lang: {{
                    decimalPoint: ',',
                    thousandsSep: ' '
                }}
            }});
            Highcharts.chart('{chart_id}', {{
                chart: {{ type: 'column' }},
                title: {{ text: 'Comparação de Custos Mensais', align: 'left' }},
                xAxis: {{ categories: {categorias_json}, crosshair: true }},
                yAxis: {{ title: {{ text: 'Balanço Energético (€)' }} }},
                tooltip: {{
                    headerFormat: '<span style="font-size:10px">{{point.key}}</span><table>',
                    pointFormat: '<tr><td style="color:{{series.color}};padding:0">{{series.name}}: </td>' +
                                 '<td style="padding:0"><b>{{point.y:.2f}} €</b></td></tr>',
                    footerFormat: '</table>',
                    shared: true,
                    useHTML: true
                }},
                plotOptions: {{
                    column: {{
                        pointPadding: 0.2,
                        borderWidth: 0
                    }}
                }},
                series: {series_json}
            }});
        </script>
    </body>
    </html>
    """
    return html_code

def gerar_grafico_payback(chart_id, chart_data):
    """
    Gera o código HTML/JS para um gráfico de barras horizontais que
    classifica os cenários de simulação pelo seu payback.
    """
    # Os dados já vêm ordenados, basta convertê-los para JSON
    series_data_json = json.dumps(chart_data['series_data'])
    titulo_grafico = chart_data['titulo']

    html_code = f"""
    <html>
    <head>
        <script src="https://code.highcharts.com/highcharts.js"></script>
        <style>
            #{chart_id} {{ min-height: 300px; margin: 0 auto; }}
        </style>
    </head>
    <body>
        <figure class="highcharts-figure"><div id="{chart_id}"></div></figure>
        <script>
            Highcharts.setOptions({{
                lang: {{
                    decimalPoint: ',',
                    thousandsSep: ' '
                }}
            }});
            Highcharts.chart('{chart_id}', {{
                chart: {{ type: 'bar' }},
                title: {{ text: '{titulo_grafico}', align: 'left' }},
                xAxis: {{
                    type: 'category',
                    title: {{ text: null }},
                    labels: {{
                        style: {{
                            fontSize: '11px',
                            fontWeight: 'bold'
                        }}
                    }}
                }},
                yAxis: {{
                    min: 0,
                    title: {{ text: 'Payback (Anos)', align: 'high' }},
                    labels: {{ overflow: 'justify' }}
                }},
                legend: {{ enabled: false }},
                plotOptions: {{
                    bar: {{
                        dataLabels: {{
                            enabled: true,
                            format: '{{point.y:.1f}} anos'
                        }},
                        colorByPoint: true, // Dá uma cor diferente a cada barra
                        colors: ['#50B432', '#ED561B', '#DDDF00', '#24CBE5', '#64E572', '#FF9655', '#FFF263', '#6AF9C4']
                    }}
                }},
                tooltip: {{
                    pointFormat: 'Payback: <b>{{point.y:.1f}} anos</b>'
                }},
                series: [{{
                    name: 'Payback',
                    data: {series_data_json}
                }}]
            }});
        </script>
    </body>
    </html>
    """
    return html_code

def gerar_mapa_solar(chart_id, chart_data):
    """
    Gera o código HTML/JS para um mapa solar interativo de Portugal,
    com subtítulo, unidade de tooltip dinâmica e funcionalidade de exportação.
    """
    titulo = chart_data['titulo']
    subtitulo = chart_data.get('subtitulo', '')
    map_data_json = json.dumps(chart_data['dados_mapa'])
    map_url = chart_data['map_url']
    unidade = chart_data['unidade']

    html_code = f"""
    <html>
    <head>
        <script src="https://code.highcharts.com/maps/highmaps.js"></script>
        <script src="https://code.highcharts.com/maps/modules/data.js"></script>
        <script src="https://code.highcharts.com/maps/modules/exporting.js"></script>
        <style>
            #{chart_id} {{ height: 650px; margin: 0 auto; }}
        </style>
    </head>
    <body>
        <figure class="highcharts-figure"><div id="{chart_id}"></div></figure>
        <script>
            Highcharts.setOptions({{
                lang: {{
                    decimalPoint: ',',
                    thousandsSep: ' '
                }}
            }});
        (async () => {{
            const topology = await fetch('{map_url}').then(response => response.json());
            const data = {map_data_json};

            Highcharts.mapChart('{chart_id}', {{
                chart: {{ map: topology }},
                title: {{ text: '{titulo}', align: 'left' }},
                
                // --- SUBTÍTULO ---
                subtitle: {{
                    text: '{subtitulo}',
                    align: 'left'
                }},

                mapNavigation: {{ enabled: true, buttonOptions: {{ verticalAlign: 'bottom' }} }},
                colorAxis: {{
                    min: {chart_data['min_color']}, max: {chart_data['max_color']},
                    minColor: '#FFF1C5', maxColor: '#E54C00',
                    stops: [[0, '#FFF1C5'], [0.5, '#FFC700'], [1, '#E54C00']]
                }},
                
                // --- TOOLTIP ---
                tooltip: {{
                    headerFormat: '<b>{{point.name}}</b><br>',
                    pointFormat: 'Produção Total: <b>{{point.value:,.0f}} {unidade}</b><br>' +
                                 'Média Diária: <b>{{point.media_diaria:.2f}} kWh/dia</b>'
                }},

                exporting: {{ enabled: true }},

                // --- BLOCO DE CRÉDITOS ---
                credits: {{
                    enabled: true,
                    text: 'Fonte dos Dados Base: PVGIS (Photovoltaic Geographical Information System)',
                    style: {{
                        fontSize: '10px'
                    }}
                }},
                // --- FIM DO BLOCO DE CRÉDITOS ---

                series: [{{
                    data: data,
                    joinBy: 'hc-key', name: 'Produção Solar',
                    states: {{ hover: {{ color: '#a4edba' }} }},
                    dataLabels: {{
                        enabled: true, format: '{{point.name}}',
                        style: {{ color: 'black', fontSize: '10px', fontWeight: 'normal', textOutline: '1px white' }}
                    }}
                }}]
            }});
        }})();
        </script>
    </body>
    </html>
    """
    return html_code

def gerar_grafico_fluxo_caixa(chart_id, chart_data):
    """
    Gera um gráfico de fluxo de caixa anual e acumulado, com linha de investimento.
    """
    series_json = json.dumps(chart_data['series'])
    categorias_json = json.dumps(chart_data['categorias'])
    custo_investimento = chart_data['investimento']

    html_code = f"""
    <html>
    <head>
        <script src="https://code.highcharts.com/highcharts.js"></script>
    </head>
    <body>
        <figure class="highcharts-figure"><div id="{chart_id}" style="height: 400px;"></div></figure>
        <script>
            Highcharts.chart('{chart_id}', {{
                chart: {{ zoomType: 'x' }},
                title: {{ text: 'Projeção Financeira a Longo Prazo da Simulação Atual', align: 'left' }},
                xAxis: [{{ categories: {categorias_json}, crosshair: true }}],
                yAxis: [
                    {{ // Eixo Primário (Esquerda) para €
                        title: {{ text: 'Euros (€)' }},
                        labels: {{ format: '{{value:,.0f}} €' }}
                    }}
                ],
                tooltip: {{
                    shared: true,
                    formatter: function () {{
                        // Usamos this.points[0].key para garantir que obtemos o nome da categoria (ex: "Ano 1")
                        let s = '<b>' + this.points[0].key + '</b>';
                        this.points.forEach(function (point) {{
                            s += '<br/><span style="color:'+ point.series.color +'">●</span> ' + point.series.name + ': <b>' + Highcharts.numberFormat(point.y, 2, ',', ' ') + ' €</b>';
                        }});

                        return s;
                    }}
                }},
                plotOptions: {{
                    column: {{
                        grouping: false,
                        shadow: false,
                        borderWidth: 0
                    }}
                }},
                series: {series_json}
            }});
        </script>
    </body>
    </html>
    """
    return html_code

# Classe auxiliar para criar PDFs com cabeçalho e rodapé automáticos
class PDF(FPDF):
    def header(self):
        url_logo = "https://raw.githubusercontent.com/tiagofelicia/simulador-tarifarios-eletricidade/refs/heads/main/Logo_Tiago_Felicia.png"
        try:
            response = requests.get(url_logo)
            if response.status_code == 200:
                # Usa o conteúdo da imagem em memória
                self.image(io.BytesIO(response.content), 10, 8, 33)
        except Exception as e:
            print(f"Não foi possível carregar o logo do URL: {e}")

        self.set_font('Arial', 'B', 15)
        # Ajustar a posição do título para não colidir com o logo
        self.cell(15) # Move 15 unidades para a direita
        self.cell(0, 10, 'Relatório de Simulação de Autoconsumo', 0, 1, 'C')
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        texto_rodape = f"Gerado por Simulador de Autoconsumo (por Tiago Felícia) - www.tiagofelicia.pt em {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        self.cell(0, 10, texto_rodape, 0, 0, 'L')
        self.cell(0, 10, 'Página ' + str(self.page_no()), 0, 0, 'R')



def gerar_relatorio_pdf(dados_relatorio):
    pdf = PDF()

    try:
        caminho_fonte_regular = Path(__file__).parent / "NotoSans-Regular.ttf"
        caminho_fonte_bold = Path(__file__).parent / "NotoSans-Bold.ttf"

        pdf.add_font('NotoSans', '', str(caminho_fonte_regular), uni=True)
        pdf.add_font('NotoSans', 'B', str(caminho_fonte_bold), uni=True)
        pdf.set_font('NotoSans', '', 11)
    except FileNotFoundError as e:
        st.error(f"ERRO CRÍTICO: Não foi possível encontrar um ficheiro de fonte necessário: {e}")
        st.error("Por favor, verifique se os ficheiros 'NotoSans-Regular.ttf' e 'NotoSans-Bold.ttf' estão na pasta do projeto.")
        return None # Para a execução se as fontes não forem encontradas

    # Agora que as fontes estão carregadas, podemos criar a página
    pdf.add_page()
    pdf.set_font('NotoSans', '', 11)

    # --- Secção 1: Parâmetros da Simulação ---
    pdf.set_font('NotoSans', 'B', 12)
    pdf.cell(0, 10, '1. Parâmetros da Simulação', 0, 1, 'L')
    pdf.set_font('NotoSans', '', 9)
    params = dados_relatorio['parametros']

    # --- LÓGICA DINÂMICA PARA CONSTRUIR O TEXTO ---
    # 1. Começamos com uma lista que contém a informação base (sempre presente)
    linhas_parametros = []
    linhas_parametros.append(f"Período de Análise: {params['data_inicio']} a {params['data_fim']} ({params['dias']} dias)")

    # 2. Verificamos se a simulação de painéis foi ativada para adicionar os detalhes
    if params.get('simulou_paineis', False):
        linhas_parametros.append(f"Localização: Lat {params['latitude']:.4f}, Lon {params['longitude']:.4f} (Distrito: {params['distrito']})")
        linhas_parametros.append(f"Sistema Solar: {params['paineis_kwp']:.2f} kWp, Inclinação {params['inclinacao']}°, Orientação {params['orientacao']}°, Perdas {params['perdas']}%, Sombreamento {params['sombra']}%")

    # 3. Verificamos se a simulação de bateria foi ativada para adicionar os seus detalhes
    if params.get('simulou_bateria', False):
        linhas_parametros.append(f"Bateria: {params['bateria_kwh']:.2f} kWh de capacidade, {params['bateria_kw']:.2f} kW de potência")

    # 4. Juntamos todas as linhas da lista com um caracter de nova linha
    texto_final_parametros = "\n".join(linhas_parametros)
    
    # 5. Escrevemos o texto final no PDF
    pdf.multi_cell(0, 5, texto_final_parametros)
    pdf.ln(5)

    # --- Secção 2: Resumo Energético ---
    pdf.set_font('NotoSans', 'B', 12)
    pdf.cell(0, 10, '2. Resumo Energético (Anualizado)', 0, 1, 'L')
    
    # Cabeçalho da tabela
    pdf.set_fill_color(220, 220, 220) # Cinzento claro
    pdf.set_text_color(0, 0, 0)       # Texto preto
    pdf.set_font('NotoSans', 'B', 9)
    pdf.cell(80, 7, 'Métrica', 1, 0, 'L', 1)
    pdf.cell(50, 7, 'Cenário Atual', 1, 0, 'C', 1)
    pdf.cell(50, 7, dados_relatorio['cenarios_simulados'][0]['nome'], 1, 1, 'C', 1)
    
    pdf.set_font('NotoSans', '', 9)
    metricas_energia_labels = {
        'consumo_rede': 'Consumo da Rede (kWh/ano)',
        'autoconsumo_total': 'Autoconsumo Total (kWh/ano)',
        'excedente_venda': 'Excedente para Venda (kWh/ano)',
    }
    for chave, label in metricas_energia_labels.items():
        pdf.cell(80, 6, label, 1)
        pdf.cell(50, 6, formatar_numero_pt(dados_relatorio['cenario_atual_energia'][chave], 0), 1, 0, 'C')
        pdf.cell(50, 6, formatar_numero_pt(dados_relatorio['cenarios_simulados'][0]['metricas_energia'][chave], 0), 1, 1, 'C')
    pdf.ln(5)

    # --- Secção 3: Análise Financeira por Cenário ---
    pdf.set_font('NotoSans', 'B', 12)
    pdf.cell(0, 10, '3. Análise Financeira por Cenário', 0, 1, 'L')

    for cenario in dados_relatorio['cenarios_simulados']:
        pdf.set_font('NotoSans', 'B', 10)
        pdf.cell(0, 8, f"Cenário: {cenario['nome']}", 0, 1, 'L')

        pdf.set_font('NotoSans', '', 9)
        financeiro = cenario['resultados_financeiros']
        projecao = cenario['projecao']
        payback_str = f"{projecao['payback_detalhado']:.1f} anos" if projecao['payback_detalhado'] != float('inf') else "> 30 anos"

        texto_financeiro = (
            f"  Custo do Investimento: {formatar_numero_pt(financeiro['custo_investimento'], 2, ' €')}\n"
            f"  Poupança Anual Estimada: {formatar_numero_pt(financeiro['poupanca_anual'], 2, ' €')}\n"
            f"    -> Poupança por Autoconsumo: {formatar_numero_pt(financeiro.get('poupanca_autoconsumo', 0), 2, ' €')}\n"
            f"    -> Receita Adicional por Venda: {formatar_numero_pt(financeiro.get('poupanca_venda', 0), 2, ' €')}\n"
            f"    -> Preço Médio Compra: {formatar_numero_pt(financeiro['preco_medio_compra'], 4, ' €/kWh')}\n"
            f"    -> Preço Médio Venda: {formatar_numero_pt(financeiro['preco_medio_venda'], 4, ' €/kWh')}\n"
            f"  Payback Detalhado: {payback_str}\n"
            f"  Poupança Total em {int(projecao['anos_analise'])} anos: {formatar_numero_pt(projecao['poupanca_total_periodo'], 2, ' €')}"
        )
        pdf.multi_cell(0, 5, texto_financeiro)
        pdf.ln(3)

    # --- Secção 4: Análise Comparativa de Consumos (Tabela) ---
    if 'dados_tabela_consumos' in dados_relatorio:
        pdf.add_page()
        pdf.set_font('NotoSans', 'B', 12)
        pdf.cell(0, 10, '4. Análise Comparativa de Consumos (Inicial vs. Simulado)', 0, 1, 'L')
        pdf.set_font('NotoSans', 'B', 9)
        # Cabeçalhos
        pdf.set_fill_color(220, 220, 220)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(40, 7, 'Período', 1, 0, 'C', 1)
        pdf.cell(50, 7, 'Consumo Inicial (kWh)', 1, 0, 'C', 1)
        pdf.cell(50, 7, 'Consumo Simulado (kWh)', 1, 0, 'C', 1)
        pdf.cell(40, 7, 'Diferença (%)', 1, 1, 'C', 1)
        pdf.set_text_color(0, 0, 0)
        # Lógica da tabela de consumos
        opcao_horaria_lower = dados_relatorio['parametros']['opcao_horaria'].lower()
        ciclo_map = {'diário': 'D', 'semanal': 'S'}
        ciclo_sufixo = ciclo_map.get('diário' if 'diário' in opcao_horaria_lower else 'semanal', 'S')

        if 'tri-horário' in opcao_horaria_lower:
            ciclo_a_usar = 'T' + ciclo_sufixo
            periodos = ['P', 'C', 'V']
        elif 'bi-horário' in opcao_horaria_lower:
            ciclo_a_usar = 'B' + ciclo_sufixo
            periodos = ['F', 'V']
        else: # Simples
            ciclo_a_usar = 'Simples'
            periodos = ['Simples']

        pdf.set_font('NotoSans', '', 9)
        dados = dados_relatorio['dados_tabela_consumos']

        for periodo in periodos:
            nome_periodo = "Total" if periodo == "Simples" else NOMES_PERIODOS.get(periodo)
            inicial = dados['inicial'].get(ciclo_a_usar, {}).get(periodo, 0) if periodo != "Simples" else dados['inicial'].get('Simples', 0)
            simulado = dados['simulado'].get(ciclo_a_usar, {}).get(periodo, 0) if periodo != "Simples" else dados['simulado'].get('Simples', 0)
            diff = ((simulado - inicial) / inicial * 100) if inicial > 0 else float('inf')

            pdf.cell(40, 6, nome_periodo, 1)
            pdf.cell(50, 6, formatar_numero_pt(inicial, 0), 1, 0, 'C')
            pdf.cell(50, 6, formatar_numero_pt(simulado, 0), 1, 0, 'C')
            pdf.cell(40, 6, formatar_numero_pt(diff, 1, ' %') if diff != float('inf') else "+inf %", 1, 1, 'C')
        pdf.ln(5)

    # --- Secção 5: Projeção Financeira (Tabela e Gráfico) ---
    if 'cenarios_simulados' in dados_relatorio and dados_relatorio['cenarios_simulados']:
        primeiro_cenario = dados_relatorio['cenarios_simulados'][0]
        if primeiro_cenario['projecao']['fluxo_caixa_acumulado']:
            if pdf.get_y() > 150: pdf.add_page() # Nova página para não cortar
            
            pdf.set_font('NotoSans', 'B', 12)
            pdf.cell(0, 10, f"5. Projeção Financeira ({primeiro_cenario['nome']})", 0, 1, 'L')
            
            # --- TABELA COM OS VALORES ---
            pdf.set_font('NotoSans', 'B', 10)
            pdf.set_fill_color(220, 220, 220)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(30, 7, 'Ano', 1, 0, 'C', 1)
            pdf.cell(80, 7, 'Poupança Anual (€)', 1, 0, 'C', 1)
            pdf.cell(80, 7, 'Poupança Acumulada (€)', 1, 1, 'C', 1)
            pdf.set_text_color(0, 0, 0)
            
            pdf.set_font('NotoSans', '', 8)
            projecao = primeiro_cenario['projecao']
            for i, (poup_anual, poup_acum) in enumerate(zip(projecao['fluxo_caixa_anual'], projecao['fluxo_caixa_acumulado'])):
                pdf.cell(30, 6, str(i + 1), 1, 0, 'C')
                pdf.cell(80, 6, formatar_numero_pt(poup_anual, 2), 1, 0, 'C')
                pdf.cell(80, 6, formatar_numero_pt(poup_acum, 2), 1, 1, 'C')
            pdf.ln(5)
            # --- FIM DA TABELA ---

            anos = list(range(1, len(projecao['fluxo_caixa_acumulado']) + 1))
            imagem_projecao = gerar_imagem_grafico_linha(
                anos, projecao['fluxo_caixa_acumulado'],
                titulo=f"Fluxo de Caixa Acumulado ({primeiro_cenario['nome']})",
                label_y='Poupanca Acumulada (€)'
            )
            pdf.image(imagem_projecao, w=190)
            pdf.ln(5)

    # --- Secção 6: Comparação de Custos Mensais (Tabela e Gráfico) ---
    # --- TABELA COM OS VALORES ---
    if dados_relatorio.get('dados_custos_mensais'):
        # Adicionar uma nova página se necessário
        if pdf.get_y() > 200: pdf.add_page() 

        pdf.set_font('NotoSans', 'B', 12)
        pdf.cell(0, 10, '6. Comparacao de Custos Mensais (€)', 0, 1, 'L')

        pdf.set_font('NotoSans', 'B', 9)
        dados = dados_relatorio['dados_custos_mensais']
        num_cenarios = len(dados['series'])
        largura_col = 180 / (num_cenarios + 1)

        # Cabeçalhos
        pdf.set_fill_color(220, 220, 220) # Cinzento claro
        pdf.set_text_color(0, 0, 0) # <-- Forçar cor do texto a preto
        pdf.cell(largura_col, 7, 'Mês', 1, 0, 'C', 1)
        for serie in dados['series']:
            pdf.cell(largura_col, 7, serie['name'], 1, 0, 'C', 1)
        pdf.ln()

        pdf.set_font('NotoSans', '', 8)
        for i, mes in enumerate(dados['meses']):
            pdf.cell(largura_col, 6, mes, 1)
            for serie in dados['series']:
                pdf.cell(largura_col, 6, formatar_numero_pt(serie['data'][i], 2), 1, 0, 'C')
            pdf.ln()
        pdf.ln(5)

        # Adicionar uma nova página se o gráfico anterior já ocupou muito espaço
        if pdf.get_y() > 200: pdf.add_page()

        imagem_custos_mensais = gerar_imagem_grafico_barras_agrupadas(
            dados_relatorio['dados_custos_mensais']
        )
        pdf.image(imagem_custos_mensais, w=190)
        pdf.ln(5)

    # --- Secção 7: Ranking de Payback (Tabela e Gráfico) ---
    if dados_relatorio.get('dados_ranking_payback') and len(dados_relatorio['dados_ranking_payback']) > 1:
        pdf.set_font('NotoSans', 'B', 12)
        pdf.cell(0, 10, '7. Classificação de Cenários por Payback', 0, 1, 'L')
        pdf.set_font('NotoSans', 'B', 9)

        # --- TABELA COM OS VALORES ---
        pdf.cell(120, 7, 'Cenário', 1, 0, 'C', 1)
        pdf.cell(60, 7, 'Payback (Anos)', 1, 1, 'C', 1)

        pdf.set_font('NotoSans', '', 9)
        # Ordena os cenários pelo payback
        cenarios_ordenados = sorted(dados_relatorio['dados_ranking_payback'], key=lambda x: x['y'])
        for cenario in cenarios_ordenados:
            pdf.cell(120, 6, cenario['name'], 1)
            pdf.cell(60, 6, formatar_numero_pt(cenario['y'], 1), 1, 1, 'C')
        pdf.ln(5)
        # --- FIM DA TABELA ---

        #Gráfico
        dados_payback_ordenados = sorted(dados_relatorio['dados_ranking_payback'], key=lambda x: x['y'])

        imagem_payback = gerar_imagem_grafico_barras(
            dados_payback_ordenados,
            titulo='Comparação do Payback entre Cenários',
            label_y='Payback (Anos)'
        )
        pdf.image(imagem_payback, w=190)
        pdf.ln(5)

    return bytes(pdf.output())

