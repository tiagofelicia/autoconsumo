import streamlit as st
import json
import pandas as pd


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
        <div style="font-size: 0.9rem; color: var(--text-color); opacity: 0.7;">{label}</div>
        <div style="font-size: 1.2rem; color: var(--text-color); ">{value}</div>
    </div>
    """
    st.markdown(html_content, unsafe_allow_html=True)

def gerar_grafico_highcharts(chart_id, chart_data):
    """
    Gera o código HTML/JS para um gráfico Highcharts com múltiplas séries e colunas empilhadas.
    O tooltip foi customizado para mostrar valores totais e médios, e o total do dia para barras empilhadas.
    Séries com valor 0.00 são omitidas do tooltip.
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
            Highcharts.chart('{chart_id}', {{
                chart: {{ zoomType: 'xy' }},
                title: {{ text: '{titulo_grafico}', align: 'left' }},
                xAxis: [{{ categories: {categorias_json}, crosshair: true }}],
                yAxis: [
                    {{ labels: {{ format: '{{value}} kWh' }}, title: {{ text: '{titulo_eixo_y1}' }} }}, 
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
                        let s = '<b>' + this.x + '</b>';
                        let isStacked = false;

                        this.points.forEach(function (point) {{
                            // ALTERAÇÃO: Adiciona a linha ao tooltip apenas se o valor for maior que 0
                            if (point.y > 0) {{
                                let nomeSerie = point.series.name;
                                let valorTotal = point.y;
                                let valorMedio = point.point.options.media;

                                s += '<br/>' + nomeSerie + ': <b>' + valorTotal.toFixed(2) + '</b>';
                                
                                if (typeof valorMedio !== 'undefined') {{
                                    s += ' <span style="font-size: 0.9em;">(Média: ' + valorMedio.toFixed(2) + ')</span>';
                                }}
                            }}

                            // A lógica para detetar se o gráfico é empilhado continua igual
                            if (point.series.type === 'column' && point.series.options.stacking === 'normal') {{
                                isStacked = true;
                            }}
                        }});

                        // O total continua a ser mostrado corretamente para gráficos empilhados
                        if (isStacked && typeof this.total !== 'undefined' && this.total > 0) {{
                            s += '<br/>--------------------';
                            s += '<br/><b>Total Consumo: <b>' + this.total.toFixed(2) + ' kWh</b>';
                        }}

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

def gerar_grafico_omie_diario(chart_id, dados, titulo_grafico):
    """
    Gera o código HTML/JS para um gráfico de linha simples da evolução diária do OMIE.
    """
    categorias_json = json.dumps(dados['categorias'])
    valores_json = json.dumps(dados['valores'])

    html_code = f"""
    <html>
    <head>
        <script src="https://code.highcharts.com/highcharts.js"></script>
        <style>
            #{chart_id} {{ height: 300px; margin: 10px auto; }}
        </style>
    </head>
    <body>
        <figure class="highcharts-figure">
            <div id="{chart_id}"></div>
        </figure>

        <script>
            Highcharts.chart('{chart_id}', {{
                chart: {{ type: 'line' }},
                title: {{ text: '{titulo_grafico}' }},
                xAxis: {{ categories: {categorias_json} }},
                yAxis: {{
                    title: {{ text: 'Preço Médio (€/MWh)' }}
                }},
                series: [{{
                    name: 'OMIE Diário',
                    data: {valores_json},
                    color: '#FF0000',
                    tooltip: {{ valueSuffix: ' €/MWh' }}
                }}],
                legend: {{ enabled: false }}
            }});
        </script>
    </body>
    </html>
    """
    return html_code

### Função de geração de gráficos mais avançada ###
def gerar_grafico_highcharts_multi_serie(chart_id, chart_data):
    """
    Gera o código HTML/JS para um gráfico Highcharts com múltiplas séries de linha.
    """
    categorias_json = json.dumps(chart_data['categorias'])
    series_json = json.dumps(chart_data['series'])
    
    html_code = f"""
    <html>
    <head>
        <script src="https://code.highcharts.com/highcharts.js"></script>
        <style>
            #{chart_id} {{ height: 300px; margin: 10px auto; }}
        </style>
    </head>
    <body>
        <figure class="highcharts-figure"><div id="{chart_id}"></div></figure>
        <script>
            Highcharts.chart('{chart_id}', {{
                chart: {{ type: 'line' }},
                title: {{ text: '{chart_data["titulo"]}' }},
                xAxis: {{ categories: {categorias_json}, crosshair: true }},
                yAxis: {{ title: {{ text: 'Preço Médio (€/MWh)' }} }},
                tooltip: {{ shared: true }},
                plotOptions: {{
                    line: {{
                        dataLabels: {{ enabled: false }},
                        enableMouseTracking: true
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
    Prepara os dados agregados por dia da semana.
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
                    "data": data_points, "yAxis": 0, "color": cores_consumo_a_usar.get(cor_key)
                })
    else:
        agg_total_consumo = df_semana.groupby('dia_da_semana')['Consumo (kWh)'].sum()
        agg_media_consumo = (agg_total_consumo / day_counts).fillna(0)
        data_points = [{'y': agg_total_consumo.get(i, 0), 'media': agg_media_consumo.get(i, 0)} for i in range(7)]
        series_grafico.append({"name": "Consumo Total (kWh)", "type": "column", "data": data_points, "yAxis": 0, "color": "#BFBFBF"})
    
    agg_media_omie_simples = df_semana.groupby('dia_da_semana')['OMIE'].mean().reindex(range(7))
    dados_omie_simples_final = agg_media_omie_simples.round(2).where(pd.notna(agg_media_omie_simples), None).tolist()
    series_grafico.append({
        "name": "Média OMIE (€/MWh)", "type": "line", "data": dados_omie_simples_final, "yAxis": 1, "color": cores_omie.get('S')
    })
    
    if ciclo_a_usar and ciclo_a_usar in df_semana.columns:
        agg_omie_semana_periodos = df_semana.groupby(['dia_da_semana', ciclo_a_usar])['OMIE'].mean().unstack()
        for p in periodos_ciclo:
            if p in agg_omie_semana_periodos.columns:
                dados_omie_p = agg_omie_semana_periodos[p].reindex(range(7))
                dados_omie_p_final = dados_omie_p.round(2).where(pd.notna(dados_omie_p), None).tolist()
                series_grafico.append({
                    "name": f"Média OMIE {nomes_periodos.get(p, p)} (€/MWh)", "type": "line",
                    "data": dados_omie_p_final, "yAxis": 1, "color": cores_omie.get(p), "visible": False
                })

    return {
        'titulo': f'Consumo e Preço Médio OMIE por Dia da Semana ({titulo_ciclo})',
        'titulo_eixo_y1': 'Consumo Total (kWh)', 'titulo_eixo_y2': 'Média OMIE (€/MWh)',
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
    Prepara os dados de consumo E MÉDIA OMIE agregados por mês, 
    com barras empilhadas por período horário e múltiplas linhas para o OMIE (simples e por período).
    """
    if df_consumos.empty or 'DataHora' not in df_consumos.columns:
        return None

    df_mensal = df_consumos.copy()
    
    df_mensal['AnoMes'] = df_mensal['DataHora'].dt.to_period('M')

    if df_mensal['AnoMes'].nunique() <= 1:
        return None

    series_grafico = []
    
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
    
    nomes_periodos = {'V': 'Vazio', 'F': 'Fora Vazio', 'C': 'Cheias', 'P': 'Ponta'}
    cores_consumo_diario = {'V_bi': '#A9D18E', 'V_tri': '#BF9000', 'F': '#E2EFDA', 'C': '#FFE699', 'P': '#FFF2CC'}
    cores_consumo_semanal = {'V_bi': '#8FAADC', 'V_tri': '#C55A11', 'F': '#DAE3F3', 'C': '#F4B183', 'P': '#FBE5D6'}
    cores_consumo_a_usar = cores_consumo_diario if "diário" in oh_lower else cores_consumo_semanal
    cores_omie = {'S': '#FF0000', 'V': '#000000', 'F': '#FFC000', 'C': '#2F5597', 'P': '#00B050'}
    
    todos_os_meses = sorted(df_mensal['AnoMes'].unique())
    
    # --- Agrupar dados de CONSUMO (esta parte mantém-se igual) ---
    if ciclo_a_usar and ciclo_a_usar in df_mensal.columns:
        consumo_mensal_periodo = df_mensal.groupby(['AnoMes', ciclo_a_usar])['Consumo (kWh)'].sum().unstack(fill_value=0)
        consumo_mensal_periodo = consumo_mensal_periodo.reindex(todos_os_meses, fill_value=0)
        
        for p in reversed(periodos_ciclo):
            if p in consumo_mensal_periodo.columns:
                cor_key = 'V_tri' if p == 'V' and oh_lower.startswith("tri") else ('V_bi' if p == 'V' else p)
                series_grafico.append({
                    "name": f"Consumo {nomes_periodos.get(p, p)} (kWh)", "type": "column",
                    "data": consumo_mensal_periodo[p].round(2).tolist(), "yAxis": 0,
                    "color": cores_consumo_a_usar.get(cor_key)
                })
    else: # Modo Simples
        consumo_mensal_total = df_mensal.groupby('AnoMes')['Consumo (kWh)'].sum()
        consumo_mensal_total = consumo_mensal_total.reindex(todos_os_meses, fill_value=0)
        series_grafico.append({
            "name": "Consumo Total (kWh)", "type": "column",
            "data": consumo_mensal_total.round(2).tolist(), "yAxis": 0,
            "color": "#BFBFBF"
        })

    # --- Agrupar dados de OMIE (AGORA COM TODOS OS PERÍODOS) ---
    if 'OMIE' in df_mensal.columns:
        # 1. Média OMIE Simples (sempre visível)
        media_omie_mensal_simples = df_mensal.groupby('AnoMes')['OMIE'].mean().reindex(todos_os_meses)
        dados_omie_simples_finais = media_omie_mensal_simples.round(2).where(pd.notna(media_omie_mensal_simples), None).tolist()
        series_grafico.append({
            "name": "Média OMIE (€/MWh)", "type": "line",
            "data": dados_omie_simples_finais, "yAxis": 1, 
            "color": cores_omie.get('S'), "tooltip": { "valueSuffix": " €/MWh" }
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
                        "name": f"Média OMIE {nomes_periodos.get(p, p)} (€/MWh)",
                        "type": "line",
                        "data": dados_omie_p_finais,
                        "yAxis": 1,
                        "color": cores_omie.get(p),
                        "visible": False, # <-- ESCONDIDO POR DEFEITO
                        "tooltip": { "valueSuffix": " €/MWh" }
                    })
    
    # Formatar as categorias do eixo X
    categorias_eixo_x = [mes.strftime('%b %Y') for mes in todos_os_meses]

    return {
        'titulo': f'Consumo Mensal vs. Preço Médio OMIE ({titulo_ciclo})',
        'titulo_eixo_y1': 'Consumo Total (kWh)',
        'titulo_eixo_y2': 'Média Mensal OMIE (€/MWh)',
        'categorias': categorias_eixo_x,
        'series': series_grafico
    }

def criar_tabela_comparativa_html(consumos_agregados_inicial, consumos_agregados_simulado):
    """
    Gera uma tabela HTML comparativa detalhada entre o consumo inicial e o simulado.
    """
    
    # --- Dicionário de Cores ---
    cores = {
        'header': {
            'S':  {'bg': '#A6A6A6'}, 'BD': {'bg': '#A9D08E'}, 'BS': {'bg': '#8EA9DB'},
            'TD': {'bg': '#BF8F00', 'text': '#FFFFFF'},
            'TS': {'bg': '#C65911', 'text': '#FFFFFF'}
        },
        'cell_light': {
            'S': {'bg': '#D9D9D9'}, 'BD_V': {'bg': '#C6E0B4'}, 'BD_F': {'bg': '#E2EFDA'},
            'BS_V': {'bg': '#B4C6E7'}, 'BS_F': {'bg': '#D9E1F2'}, 'TD_V': {'bg': '#FFD966'},
            'TD_C': {'bg': '#FFE699'}, 'TD_P': {'bg': '#FFF2CC'}, 'TS_V': {'bg': '#F4B084'},
            'TS_C': {'bg': '#F8CBAD'}, 'TS_P': {'bg': '#FCE4D6'}
        },
        'cell_dark': {
            'S': {'bg': '#C0C0C0'}, 'BD_V': {'bg': '#B5D6A3'}, 'BD_F': {'bg': '#D1E6CA'},
            'BS_V': {'bg': '#A3B8D6'}, 'BS_F': {'bg': '#C8D2E7'}, 'TD_V': {'bg': '#F0CF5A'},
            'TD_C': {'bg': '#F0D68A'}, 'TD_P': {'bg': '#F0E7BE'}, 'TS_V': {'bg': '#E9A06F'},
            'TS_C': {'bg': '#EBB99C'}, 'TS_P': {'bg': '#F0D8C9'}
        }
    }

    # --- Geração do CSS ---
    html = "<style>"
    html += ".comp-table { width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 13px; font-family: sans-serif; text-align: center; }"
    html += ".comp-table th, .comp-table td { padding: 6px 8px; border: 1px solid #999; }"
    html += ".comp-table .header-main { vertical-align: middle; }"
    html += ".comp-table .header-sub { font-weight: bold; }"
    html += ".comp-table .row-label { text-align: left; font-weight: bold; background-color: #f2f2f2; }"
    html += ".comp-table .diff-pos { color: #00b050; }"
    html += ".comp-table .diff-neg { color: #c00000; }"
    for tipo_estilo, mapa_cores in cores.items():
        for chave, config_cor in mapa_cores.items():
            cor_fundo = config_cor['bg']
            cor_texto = config_cor.get('text')
            if not cor_texto:
                try:
                    r, g, b = int(cor_fundo[1:3], 16), int(cor_fundo[3:5], 16), int(cor_fundo[5:7], 16)
                    cor_texto = '#000000' if (r*0.299 + g*0.587 + b*0.114) > 140 else '#FFFFFF'
                except: cor_texto = '#000000'
            if tipo_estilo == 'header': html += f".header-{chave} {{ background-color: {cor_fundo}; color: {cor_texto}; }}"
            elif tipo_estilo == 'cell_light': html += f".cell-light-{chave} {{ background-color: {cor_fundo}; }}"
            elif tipo_estilo == 'cell_dark': html += f".cell-dark-{chave} {{ background-color: {cor_fundo}; }}"
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

    # ALTERAÇÃO 1: Funções de formatação atualizadas
    def formatar_diff(valor, casas_decimais=0):
        valor_str = f"{valor:,.{casas_decimais}f}".replace(',', ' ')
        if valor > 0.001: return f"<span class='diff-pos'>+{valor_str}</span>"
        if valor < -0.001: return f"<span class='diff-neg'>{valor_str}</span>"
        return valor_str

    def formatar_diff_rel(valor):
        if valor == float('inf'): return "<span class='diff-pos'>+inf</span>"
        # Chama a função base para consistência de formato
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

    # ALTERAÇÃO 2: Lista de métricas
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
                    # ALTERAÇÃO 3: Formatação de número aplicada aqui
                    valor_formatado = f"{valor:,.{decimais}f}".replace(',', ' ')
                    html += f"<td class='{classe_celula}'>{valor_formatado}</td>"
                else:
                    is_percent_row = (chave == 'diff_rel')
                    formatador = formatar_diff_rel if is_percent_row else lambda v: formatar_diff(v, decimais)
                    html += f"<td class='{classe_celula}'>{formatador(valor)}</td>"
        html += "</tr>"
    
    html += "</tbody></table>"
    return html