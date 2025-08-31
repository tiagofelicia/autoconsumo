import streamlit as st
import pandas as pd
import re
import requests
import numpy as np
from io import StringIO
import math
import constantes as C


# --- Função para obter valores da aba Constantes ---
def obter_constante(nome_constante, constantes_df):
    constante_row = constantes_df[constantes_df['constante'] == nome_constante]
    if not constante_row.empty:
        valor = constante_row['valor_unitário'].iloc[0]
        try:
            return float(valor)
        except (ValueError, TypeError):
            # st.warning(f"Valor não numérico para constante '{nome_constante}': {valor}")
            return 0.0
    else:
        # st.warning(f"Constante '{nome_constante}' não encontrada.")
        return 0.0

# --- Função: Calcular custo de energia com IVA (limite 200 ou 300 kWh/30 dias apenas <= 6.9 kVA), para diferentes opções horárias
def calcular_custo_energia_com_iva(
    consumo_kwh_total_periodo, preco_energia_final_sem_iva_simples,
    precos_energia_final_sem_iva_horario, dias_calculo, potencia_kva,
    opcao_horaria_str, consumos_horarios, familia_numerosa_bool
):
    if not isinstance(opcao_horaria_str, str):
        return {'custo_com_iva': 0.0, 'custo_sem_iva': 0.0, 'valor_iva_6': 0.0, 'valor_iva_23': 0.0}

    opcao_horaria_lower = opcao_horaria_str.lower()
    iva_normal_perc = 0.23
    iva_reduzido_perc = 0.06
    
    custo_total_com_iva = 0.0
    custo_total_sem_iva = 0.0
    total_iva_6_energia = 0.0
    total_iva_23_energia = 0.0

    precos_horarios = precos_energia_final_sem_iva_horario if isinstance(precos_energia_final_sem_iva_horario, dict) else {}
    consumos_periodos = consumos_horarios if isinstance(consumos_horarios, dict) else {}

    # Calcular custo total sem IVA primeiro
    if opcao_horaria_lower == "simples":
        consumo_s = float(consumo_kwh_total_periodo)
        preco_s = float(preco_energia_final_sem_iva_simples or 0.0)
        custo_total_sem_iva = consumo_s * preco_s
    else: # Bi ou Tri
        for periodo, consumo_p in consumos_periodos.items():
            consumo_p_float = float(consumo_p if consumo_p is not None else 0.0) # Forma mais segura
            preco_h = float(precos_horarios.get(periodo, 0.0)) # Removemos o 'or 0.0'
            custo_total_sem_iva += consumo_p_float * preco_h
            
    # Determinar limite para IVA reduzido
    limite_kwh_periodo_global = 0.0
    if potencia_kva <= 6.9:
        limite_kwh_mensal = 300 if familia_numerosa_bool else 200
        limite_kwh_periodo_global = (limite_kwh_mensal * dias_calculo / 30.0) if dias_calculo > 0 else 0.0

    if limite_kwh_periodo_global == 0.0: # Sem IVA reduzido, tudo a 23%
        total_iva_23_energia = custo_total_sem_iva * iva_normal_perc
        custo_total_com_iva = custo_total_sem_iva + total_iva_23_energia
    else: # Com IVA reduzido/Normal
        if opcao_horaria_lower == "simples":
            consumo_s = float(consumo_kwh_total_periodo)
            preco_s = float(preco_energia_final_sem_iva_simples or 0.0)

            
            consumo_para_iva_reduzido = min(consumo_s, limite_kwh_periodo_global)
            consumo_para_iva_normal = max(0.0, consumo_s - limite_kwh_periodo_global)
            
            base_iva_6 = consumo_para_iva_reduzido * preco_s
            base_iva_23 = consumo_para_iva_normal * preco_s
            
            total_iva_6_energia = base_iva_6 * iva_reduzido_perc
            total_iva_23_energia = base_iva_23 * iva_normal_perc
            custo_total_com_iva = base_iva_6 + total_iva_6_energia + base_iva_23 + total_iva_23_energia
        else: # Bi ou Tri rateado
            consumo_total_real_periodos = sum(float(v or 0.0) for v in consumos_periodos.values())
            if consumo_total_real_periodos > 0:
                for periodo, consumo_periodo in consumos_periodos.items():
                    consumo_periodo_float = float(consumo_periodo or 0.0)
                    preco_periodo = float(precos_horarios.get(periodo, 0.0) or 0.0)
                    
                    fracao_consumo_periodo = consumo_periodo_float / consumo_total_real_periodos
                    limite_para_este_periodo_rateado = limite_kwh_periodo_global * fracao_consumo_periodo
                    
                    consumo_periodo_iva_reduzido = min(consumo_periodo_float, limite_para_este_periodo_rateado)
                    consumo_periodo_iva_normal = max(0.0, consumo_periodo_float - limite_para_este_periodo_rateado)
                    
                    base_periodo_iva_6 = consumo_periodo_iva_reduzido * preco_periodo
                    base_periodo_iva_23 = consumo_periodo_iva_normal * preco_periodo
                    
                    iva_6_este_periodo = base_periodo_iva_6 * iva_reduzido_perc
                    iva_23_este_periodo = base_periodo_iva_23 * iva_normal_perc
                    
                    total_iva_6_energia += iva_6_este_periodo
                    total_iva_23_energia += iva_23_este_periodo
                    custo_total_com_iva += base_periodo_iva_6 + iva_6_este_periodo + base_periodo_iva_23 + iva_23_este_periodo
            else: # Se consumo_total_real_periodos for 0, tudo é zero
                 custo_total_com_iva = 0.0
                 # total_iva_6_energia e total_iva_23_energia permanecem 0.0

    return {
        'custo_com_iva': round(custo_total_com_iva, 4),
        'custo_sem_iva': round(custo_total_sem_iva, 4),
        'valor_iva_6': round(total_iva_6_energia, 4),
        'valor_iva_23': round(total_iva_23_energia, 4)
    }

    
###############################################################
######################### AUTOCONSUMO #########################
###############################################################
def interpolar_perfis_para_quarto_horario(perfis_horarios):
    """
    Converte perfis horários em quarto-horários usando interpolação linear
    que preserva a energia total e cria uma curva de produção suave.
    """
    perfis_quarto_horarios = {}
    for distrito, perfis_mensais in perfis_horarios.items():
        perfis_quarto_horarios[distrito] = {}
        for mes, perfil_hora in perfis_mensais.items():
            novo_perfil_mes = {}
            horas_ordenadas = sorted(perfil_hora.keys())

            for i, hora_atual in enumerate(horas_ordenadas):
                # Obter os valores da hora anterior, atual e seguinte para calcular a tendência
                valor_anterior = perfil_hora.get(hora_atual - 1, 0)
                valor_atual = perfil_hora[hora_atual]
                valor_seguinte = perfil_hora.get(hora_atual + 1, 0)

                # Se for a primeira ou última hora de produção, a tendência é mais simples
                if i == 0: # Nascer do sol
                    valor_anterior = 0
                if i == len(horas_ordenadas) - 1: # Pôr do sol
                    valor_seguinte = 0

                # Calcular a "taxa de produção" no início e no fim da hora atual
                # A taxa no início da hora é a média entre a hora anterior e a atual
                taxa_inicio_hora = (valor_anterior + valor_atual) / 2.0
                # A taxa no fim da hora é a média entre a hora atual e a seguinte
                taxa_fim_hora = (valor_atual + valor_seguinte) / 2.0
                
                # Com base nestas taxas, calculamos a produção para cada intervalo de 15 minutos
                # usando a fórmula da área de um trapézio, o que garante uma interpolação linear.
                # O fator 0.25 representa o intervalo de 15 minutos (1/4 de hora).
                p00 = (taxa_inicio_hora + (taxa_inicio_hora * 0.75 + taxa_fim_hora * 0.25)) / 2.0 * 0.25
                p15 = ((taxa_inicio_hora * 0.75 + taxa_fim_hora * 0.25) + (taxa_inicio_hora * 0.5 + taxa_fim_hora * 0.5)) / 2.0 * 0.25
                p30 = ((taxa_inicio_hora * 0.5 + taxa_fim_hora * 0.5) + (taxa_inicio_hora * 0.25 + taxa_fim_hora * 0.75)) / 2.0 * 0.25
                p45 = ((taxa_inicio_hora * 0.25 + taxa_fim_hora * 0.75) + taxa_fim_hora) / 2.0 * 0.25
                
                # A soma de p00, p15, p30, p45 será muito próxima do valor_atual original.
                # Corrigimos para garantir que a energia é exatamente conservada.
                soma_calculada = p00 + p15 + p30 + p45
                if soma_calculada > 0:
                    fator_correcao = valor_atual / soma_calculada
                    novo_perfil_mes[(hora_atual, 0)] = p00 * fator_correcao
                    novo_perfil_mes[(hora_atual, 15)] = p15 * fator_correcao
                    novo_perfil_mes[(hora_atual, 30)] = p30 * fator_correcao
                    novo_perfil_mes[(hora_atual, 45)] = p45 * fator_correcao

            perfis_quarto_horarios[distrito][mes] = novo_perfil_mes
            
    return perfis_quarto_horarios


def calcular_valor_financeiro_cenario(
    df_cenario,
    df_omie_completo,
    precos_compra_kwh_siva, # Dicionário com preços por período
    dias_calculo,
    potencia_kva,
    opcao_horaria_str,
    familia_numerosa_bool,
    # --- Para venda ---
    modelo_venda,
    tipo_comissao,
    valor_comissao
):
    """
    Calcula o valor financeiro de um cenário de autoconsumo, com cálculo detalhado
    do custo de compra da rede e da receita de venda do excedente.
    """
    if df_cenario.empty:
        return {'custo_compra_c_iva': 0, 'receita_venda': 0, 'balanco_final': 0, 'preco_medio_venda': 0}

    # --- 1. CÁLCULO DETALHADO DO CUSTO DE COMPRA DA REDE ---
    
    # 1.1. Juntar os dados do cenário com os ciclos horários para saber em que período cada consumo ocorreu
    df_merged = pd.merge(df_cenario, df_omie_completo, on='DataHora', how='left')
    
    # 1.2. Agregar o consumo da rede por cada período horário (V, F, C, P, etc.)
    consumos_rede_por_periodo = {}
    oh_lower = opcao_horaria_str.lower()
    
    ciclo_map = {
        'bi-horário - ciclo diário': 'BD', 'bi-horário - ciclo semanal': 'BS',
        'tri-horário - ciclo diário': 'TD', 'tri-horário - ciclo semanal': 'TS'
    }
    ciclo_col = ciclo_map.get(oh_lower)

    if oh_lower == "simples":
        consumos_rede_por_periodo['S'] = df_merged['Consumo_Rede_Final_kWh'].sum()
    elif ciclo_col and ciclo_col in df_merged.columns:
        # Agrupa o consumo da rede pelo ciclo (ex: 'BD') e soma os kWh para cada período ('V', 'F')
        somas = df_merged.groupby(ciclo_col)['Consumo_Rede_Final_kWh'].sum().to_dict()
        consumos_rede_por_periodo.update(somas)

    # 1.3. Chamar a sua função de cálculo de custo de energia com os dados corretos
    consumo_rede_total = df_merged['Consumo_Rede_Final_kWh'].sum()
    
    # Extrair o preço simples ou o dicionário de preços horários
    preco_simples = precos_compra_kwh_siva.get('S')
    precos_horarios = {k: v for k, v in precos_compra_kwh_siva.items() if k != 'S'}

    # Usamos a sua função já existente!
    resultado_custo_energia = calcular_custo_energia_com_iva(
        consumo_kwh_total_periodo=consumo_rede_total,
        preco_energia_final_sem_iva_simples=preco_simples,
        precos_energia_final_sem_iva_horario=precos_horarios,
        dias_calculo=dias_calculo,
        potencia_kva=potencia_kva,
        opcao_horaria_str=opcao_horaria_str,
        consumos_horarios=consumos_rede_por_periodo,
        familia_numerosa_bool=familia_numerosa_bool
    )
    
    custo_compra_final_com_iva = resultado_custo_energia['custo_com_iva']

    # --- 2. CÁLCULO DA RECEITA DE VENDA ---
    injecao_rede_total = df_cenario['Injecao_Rede_Final_kWh'].sum()
    receita_venda = 0
    preco_medio_venda = 0

    if injecao_rede_total > 0:
        if modelo_venda == 'Preço Fixo':
            receita_venda = injecao_rede_total * valor_comissao
            preco_medio_venda = valor_comissao
        
        elif modelo_venda == 'Indexado ao OMIE':
            df_merged['OMIE'] = df_merged['OMIE'].fillna(0)
            
            if tipo_comissao == 'Percentual (%)':
                df_merged['Preco_Venda_kWh'] = (df_merged['OMIE'] / 1000) * (1 - valor_comissao / 100)
            else:
                df_merged['Preco_Venda_kWh'] = (df_merged['OMIE'] - valor_comissao) / 1000
            
            df_merged['Preco_Venda_kWh'] = df_merged['Preco_Venda_kWh'].clip(lower=0)
            df_merged['Receita_Intervalo'] = df_merged['Injecao_Rede_Final_kWh'] * df_merged['Preco_Venda_kWh']
            receita_venda = df_merged['Receita_Intervalo'].sum()
            
            preco_medio_venda = receita_venda / injecao_rede_total if injecao_rede_total > 0 else 0

    # 3. Balanço Final
    balanco_final = custo_compra_final_com_iva - receita_venda

    return {
        'custo_compra_c_iva': custo_compra_final_com_iva,
        'receita_venda': receita_venda,
        'balanco_final': balanco_final,
        'preco_medio_venda': preco_medio_venda
    }

def calcular_poupanca_upac_existente(analise_real, financeiro_atual, preco_compra_kwh):
    """
    Calcula a poupança gerada por um sistema UPAC já existente e retorna o detalhe.
    """
    # Custo que o utilizador TERIA se não tivesse painéis (teria de comprar todo o consumo)
    custo_sem_upac = analise_real['consumo_total_casa'] * preco_compra_kwh

    # Custo que o utilizador TEM com a sua UPAC atual (o seu balanço final)
    custo_com_upac = financeiro_atual['balanco_final']
    
    poupanca_gerada_total = custo_sem_upac - custo_com_upac

    # --- Detalhe da Poupança ---
    # 1. Poupança por evitar comprar energia (valor do autoconsumo)
    valor_do_autoconsumo = analise_real['autoconsumo_total'] * preco_compra_kwh
    
    # 2. Receita da venda de excedente (já calculada no balanço financeiro)
    receita_da_venda = financeiro_atual['receita_venda']
    
    # Retorna um dicionário com todos os valores
    return {
        'total': poupanca_gerada_total,
        'por_autoconsumo': valor_do_autoconsumo,
        'por_venda_excedente': receita_da_venda
    }

@st.cache_data(show_spinner="A simular comportamento da bateria...")
def simular_bateria(df_com_solar, capacidade_kwh, potencia_kw, eficiencia_perc, dod_perc):
    """
    Simula o comportamento de uma bateria, usando o excedente solar para carregar
    e descarregando para cobrir o consumo da casa.
    """
    if df_com_solar.empty:
        return df_com_solar

    df = df_com_solar.copy()

    # --- Parâmetros da Bateria ---
    capacidade_util_kwh = capacidade_kwh * (dod_perc / 100.0)
    potencia_max_intervalo_kwh = potencia_kw / 4.0 # Potência máxima em 15 minutos
    # A eficiência é dividida: uma parte na carga, outra na descarga
    eficiencia_lado_unico = math.sqrt(eficiencia_perc / 100.0)

    # --- Inicialização de novas colunas ---
    estado_carga_kwh = 0.0
    df['Bateria_SoC_kWh'] = 0.0
    df['Bateria_Carga_kWh'] = 0.0
    df['Bateria_Descarga_kWh'] = 0.0

    # --- Loop de Simulação (linha a linha) ---
    for i in df.index:
        # Excedente solar e consumo da rede calculados na simulação solar
        excedente_solar_intervalo = df.at[i, 'Excedente_kWh']
        consumo_rede_intervalo = df.at[i, 'Consumo_Rede_kWh']

        # --- LÓGICA DE CARGA (com excedente solar) ---
        if excedente_solar_intervalo > 0:
            espaco_disponivel = capacidade_util_kwh - estado_carga_kwh
            # A energia a carregar é limitada pelo excedente, potência e espaço na bateria
            energia_para_carregar = min(excedente_solar_intervalo, potencia_max_intervalo_kwh, espaco_disponivel / eficiencia_lado_unico)
            
            # Atualizar estado da bateria (considerando perdas na carga)
            estado_carga_kwh += energia_para_carregar * eficiencia_lado_unico
            
            # Atualizar consumo e injeção FINAIS
            df.at[i, 'Excedente_kWh'] = excedente_solar_intervalo - energia_para_carregar
            df.at[i, 'Bateria_Carga_kWh'] = energia_para_carregar
            
        # --- LÓGICA DE DESCARGA (para abater consumo da rede) ---
        elif consumo_rede_intervalo > 0:
            # A energia a descarregar é limitada pelo consumo, potência e carga disponível
            energia_para_descarregar = min(consumo_rede_intervalo / eficiencia_lado_unico, potencia_max_intervalo_kwh, estado_carga_kwh)
            
            # Energia que efetivamente chega à casa (considerando perdas na descarga)
            energia_entregue = energia_para_descarregar * eficiencia_lado_unico
            
            # Atualizar estado da bateria
            estado_carga_kwh -= energia_para_descarregar

            df.at[i, 'Consumo_Rede_kWh'] = consumo_rede_intervalo - energia_entregue
            df.at[i, 'Bateria_Descarga_kWh'] = energia_para_descarregar
            df.at[i, 'Bateria_Energia_Entregue_kWh'] = energia_entregue

        # Registar o estado de carga da bateria no final do intervalo
        df.at[i, 'Bateria_SoC_kWh'] = estado_carga_kwh


    return df

def aplicar_simulacao_solar_aos_dados_base(df_original, df_solar_novo):
    df_final = df_original.copy()

    # Sem simulação -> manter cenário base
    if df_solar_novo is None or df_solar_novo.empty:
        df_final['Producao_Solar_kWh_Nova'] = 0.0
        df_final['Autoconsumo_kWh_Novo']   = 0.0
        df_final['Excedente_kWh_Novo']     = 0.0
        df_final['Consumo_Rede_Final_kWh'] = df_final['Consumo (kWh)']
        df_final['Injecao_Rede_Final_kWh'] = df_final.get('Injecao_Rede_kWh', 0.0)
        return df_final

    # Garantir tipos/únicos no lado solar
    solar = df_solar_novo.copy()
    solar['DataHora'] = pd.to_datetime(solar['DataHora'])
    solar = (solar
             .groupby('DataHora', as_index=False)[
                 ['Producao_Solar_kWh','Autoconsumo_kWh','Excedente_kWh']
             ].sum())

    # Left-merge para alinhar 1:1 com o base
    base = df_final[['DataHora']].copy()
    base['DataHora'] = pd.to_datetime(base['DataHora'])
    out = (base.merge(solar, on='DataHora', how='left')
                .fillna({'Producao_Solar_kWh': 0.0,
                         'Autoconsumo_kWh':     0.0,
                         'Excedente_kWh':       0.0}))

    # Copiar valores já ALINHADOS
    df_final['Producao_Solar_kWh_Nova'] = out['Producao_Solar_kWh'].values
    df_final['Autoconsumo_kWh_Novo']    = out['Autoconsumo_kWh'].values
    df_final['Excedente_kWh_Novo']      = out['Excedente_kWh'].values

    # Cálculos finais (com “clip” para nunca dar negativo na rede)
    inj_base = df_final.get('Injecao_Rede_kWh', 0.0)
    df_final['Consumo_Rede_Final_kWh'] = (df_final['Consumo (kWh)'] - df_final['Autoconsumo_kWh_Novo']).clip(lower=0)
    df_final['Injecao_Rede_Final_kWh'] = inj_base + df_final['Excedente_kWh_Novo']

    return df_final

def calcular_custos_mensais(df_original, lista_cenarios_simulados, **kwargs):
    """
    Calcula os custos mensais para o cenário original e uma lista de cenários simulados,
    retornando dados prontos para um gráfico comparativo.
    """
    # Extrair todos os parâmetros necessários recebidos via kwargs
    omie_ciclos = kwargs.get('df_omie_completo')
    precos_energia = kwargs.get('precos_compra_kwh_siva')
    potencia = kwargs.get('potencia_kva')
    opcao_horaria = kwargs.get('opcao_horaria_str')
    familia_numerosa = kwargs.get('familia_numerosa_bool')
    modelo_venda = kwargs.get('modelo_venda')
    tipo_comissao = kwargs.get('tipo_comissao')
    valor_comissao = kwargs.get('valor_comissao')

    df_original['AnoMes'] = pd.to_datetime(df_original['DataHora']).dt.to_period('M')
    meses_unicos = sorted(df_original['AnoMes'].unique())
    
    if len(meses_unicos) < 1:
        return None

    # Estrutura de dados para o gráfico
    labels_meses = [mes.strftime('%b %Y') for mes in meses_unicos]
    series_grafico = []
    
    # 1. Calcular a série do Custo Atual
    custos_atuais = []
    for mes in meses_unicos:
        df_mes_original = df_original[df_original['AnoMes'] == mes]
        dias_no_mes = (df_mes_original['DataHora'].max() - df_mes_original['DataHora'].min()).days + 1
        df_cenario_atual_formatado = df_mes_original.rename(columns={'Consumo (kWh)': 'Consumo_Rede_Final_kWh', 'Injecao_Rede_kWh': 'Injecao_Rede_Final_kWh'})
        
        financeiro_mes_atual = calcular_valor_financeiro_cenario(df_cenario=df_cenario_atual_formatado, dias_calculo=dias_no_mes, **kwargs)
        custos_atuais.append(round(financeiro_mes_atual['balanco_final'], 2))
    
    series_grafico.append({'name': 'Custo Atual', 'data': custos_atuais, 'color': '#757575'})

    # 2. Calcular a série para cada cenário simulado
    for cenario in lista_cenarios_simulados:
        df_simulado = cenario['dataframe_resultado']
        nome_cenario = cenario['nome']
        
        if 'DataHora' in df_simulado.columns:
            df_simulado['AnoMes'] = pd.to_datetime(df_simulado['DataHora']).dt.to_period('M')
        
        custos_cenario = []
        for mes in meses_unicos:
            df_mes_simulado = df_simulado[df_simulado['AnoMes'] == mes]
            if df_mes_simulado.empty:
                custos_cenario.append(0)
                continue
            
            dias_no_mes = (df_mes_simulado['DataHora'].max() - df_mes_simulado['DataHora'].min()).days + 1
            financeiro_mes_simulado = calcular_valor_financeiro_cenario(df_cenario=df_mes_simulado, dias_calculo=dias_no_mes, **kwargs)
            custos_cenario.append(round(financeiro_mes_simulado['balanco_final'], 2))
        
        series_grafico.append({'name': nome_cenario, 'data': custos_cenario})

    return {
        'meses': labels_meses,
        'series': series_grafico
    }

def calcular_producao_anual_pvgis_base(dados_pvgis):
    """
    Calcula a produção anual base (kWh/kWp) e a média diária para cada distrito.
    """
    producao_anual = {}
    dias_no_mes = {1: 31, 2: 28.25, 3: 31, 4: 30, 5: 31, 6: 30, 7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}

    for distrito, dados_mensais in dados_pvgis.items():
        producao_total_anual_distrito = 0
        for mes, prod_diaria_media in dados_mensais.items():
            producao_total_anual_distrito += prod_diaria_media * dias_no_mes.get(mes, 30)
        
        # Calcular a média diária para o ano
        media_diaria_anual = producao_total_anual_distrito / 365.25
        
        producao_anual[distrito] = {
            "total": round(producao_total_anual_distrito),
            "media_diaria": round(media_diaria_anual, 2)
        }
            
    return producao_anual


def calcular_producao_mensal_pvgis_base(dados_pvgis, mes_num):
    """
    Calcula a produção total para um mês específico (kWh/kWp) e a média diária para cada distrito.
    """
    producao_mensal = {}
    dias_no_mes = {1: 31, 2: 28.25, 3: 31, 4: 30, 5: 31, 6: 30, 7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}
    
    if mes_num not in dias_no_mes:
        return {}

    for distrito, dados_mensais in dados_pvgis.items():
        prod_diaria_media_base = dados_mensais.get(mes_num, 0)
        producao_total_mes = prod_diaria_media_base * dias_no_mes[mes_num]
        
        producao_mensal[distrito] = {
            "total": round(producao_total_mes),
            "media_diaria": round(prod_diaria_media_base, 2)
        }
            
    return producao_mensal

@st.cache_data(show_spinner="A obter e processar dados de produção solar da API do PVGIS...", ttl=3600)
def obter_perfil_producao_horaria_pvgis(latitude, longitude, inclinacao, orientacao_graus, system_loss, posicao_montagem, distrito_backup):
    """
    Função atualizada: Contacta a API e cria um perfil de produção com granularidade diária
    (média para cada dia específico do mês), em vez de uma média mensal.
    """
    url_base = "https://re.jrc.ec.europa.eu/api/seriescalc"
    params = {
        'lat': latitude, 'lon': longitude, 'peakpower': 1, 'loss': system_loss,
        'mountingplace': posicao_montagem, 'angle': inclinacao, 'aspect': orientacao_graus,
        'outputformat': 'json', 'pvcalculation': 1, 'browser': 0
        # Por defeito, a API retorna todos os anos disponíveis (2005-2023)
    }
    try:
        response = requests.get(url_base, params=params, timeout=30)
        response.raise_for_status()
        dados_json = response.json()
        
        df_hourly_raw = pd.DataFrame(dados_json['outputs']['hourly'])
        df_hourly_raw['Producao_kWh_por_kWp'] = pd.to_numeric(df_hourly_raw['P'], errors='coerce') / 1000.0
        
        timestamp = pd.to_datetime(df_hourly_raw['time'], format='%Y%m%d:%H%M')
        
        # --- ALTERAÇÃO PRINCIPAL AQUI ---
        # 1. Extrair mês, DIA e hora
        df_hourly_raw['mes'] = timestamp.dt.month
        df_hourly_raw['dia'] = timestamp.dt.day # Nova coluna
        df_hourly_raw['hora'] = timestamp.dt.hour
        
        # 2. Agrupar por mês, DIA e hora para criar o perfil diário
        perfil_horario_kwh = df_hourly_raw.groupby(['mes', 'dia', 'hora'])['Producao_kWh_por_kWp'].mean().to_dict()
        
        return perfil_horario_kwh, None

    except requests.exceptions.RequestException as e:
        return None, f"Erro ao contactar a API: {e}"
    except (KeyError, TypeError):
        return None, "A resposta da API foi inválida."

def simular_autoconsumo_completo(df_consumos, potencia_kwp, latitude, longitude, inclinacao, orientacao_graus, system_loss, posicao_montagem, distrito_backup, fator_sombra):
    """
    Versão final que remove toda a correção de fuso horário, fazendo uma
    correspondência direta entre a hora local do consumo e a hora UTC da API.
    """
    if df_consumos is None or df_consumos.empty:
        return df_consumos.copy(), "Dados de consumo vazios.", None
    """
    Função atualizada para usar o novo perfil de produção com granularidade diária.
    """
    perfil_horario_kwh, erro_api = obter_perfil_producao_horaria_pvgis(
        latitude, longitude, inclinacao, orientacao_graus, system_loss, posicao_montagem, distrito_backup
    )

    if erro_api:
        # O backup, que já funciona com hora local, permanece inalterado.
        df_resultado = simular_com_dados_distrito(
            df_consumos, potencia_kwp, inclinacao, orientacao_graus, distrito_backup, system_loss
        )
        return df_resultado, "Backup por Distrito", erro_api

    # --- CAMINHO DA API (SEM CORREÇÃO DE FUSO HORÁRIO) ---
    df_resultado = df_consumos.copy()
    
    # 1. Extrair mês, DIA e hora DIRETAMENTE da hora local do ficheiro
    df_resultado['DataHora'] = pd.to_datetime(df_resultado['DataHora'])
    interval_start = df_resultado['DataHora'] - pd.Timedelta(minutes=15)
    df_resultado['mes'] = interval_start.dt.month
    df_resultado['dia'] = interval_start.dt.day
    df_resultado['hora'] = interval_start.dt.hour
    
    # 2. Juntar os dados usando a chave de hora local com a chave de hora UTC da API
    df_perfil = pd.DataFrame(perfil_horario_kwh.items(), columns=['mes_dia_hora', 'Prod_Horaria_Base'])
    df_perfil[['mes', 'dia', 'hora']] = pd.DataFrame(df_perfil['mes_dia_hora'].tolist(), index=df_perfil.index)
    df_resultado = pd.merge(df_resultado, df_perfil[['mes', 'dia', 'hora', 'Prod_Horaria_Base']], on=['mes', 'dia', 'hora'], how='left')
    
    df_resultado['Prod_Horaria_Base'] = df_resultado['Prod_Horaria_Base'].fillna(0)
    df_resultado['Producao_Solar_kWh'] = (df_resultado['Prod_Horaria_Base'] / 4.0) * potencia_kwp

    fator_reducao = 1 - (fator_sombra / 100.0)
    df_resultado['Producao_Solar_kWh'] *= fator_reducao

    # 3. Limpeza e cálculos finais
    df_resultado.drop(columns=['mes', 'dia', 'hora', 'Prod_Horaria_Base'], inplace=True)
    
    soma_original_precisa = df_resultado['Producao_Solar_kWh'].sum()
    df_resultado['Producao_Solar_kWh'] = df_resultado['Producao_Solar_kWh'].rolling(window=4, center=False, min_periods=1).mean()
    soma_apos_suavizar = df_resultado['Producao_Solar_kWh'].sum()
    if soma_apos_suavizar > 0:
        fator_correcao = soma_original_precisa / soma_apos_suavizar
        df_resultado['Producao_Solar_kWh'] *= fator_correcao

    df_resultado['Autoconsumo_kWh'] = np.minimum(df_resultado['Consumo (kWh)'], df_resultado['Producao_Solar_kWh'])
    df_resultado['Excedente_kWh'] = np.maximum(0, df_resultado['Producao_Solar_kWh'] - df_resultado['Consumo (kWh)'])
    df_resultado['Consumo_Rede_kWh'] = np.maximum(0, df_resultado['Consumo (kWh)'] - df_resultado['Autoconsumo_kWh'])

    return df_resultado, "API PVGIS", None

def simular_com_dados_distrito(df_consumos, potencia_kwp, inclinacao, orientacao_graus, distrito, system_loss):
    """
    Função de backup que simula a produção solar usando os dados estáticos por distrito.
    """
    dados_producao_distrito = C.DADOS_PVGIS_DISTRITO.get(distrito)
    perfis_horarios_distrito = C.PERFIS_HORARIOS_MENSAIS_POR_DISTRITO.get(distrito)

    if not dados_producao_distrito or not perfis_horarios_distrito:
        st.error(f"Não foram encontrados dados de backup para o distrito '{distrito}'.")
        return None

    df_resultado = df_consumos.copy()
    
    perfis_quarto_horarios = interpolar_perfis_para_quarto_horario({distrito: perfis_horarios_distrito})[distrito]

    # --- FATORES DE AJUSTE (DA SUA VERSÃO ORIGINAL) ---
    fator_inclinacao = 1.0 - (abs(inclinacao - 35) / 100) * 0.5
    fator_orientacao = 1.0 # Sul (0°)
    if abs(orientacao_graus) > 70: # Próximo de Este/Oeste
        fator_orientacao = 0.80
    elif abs(orientacao_graus) > 25: # Próximo de Sudeste/Sudoeste
        fator_orientacao = 0.95
    
    # --- FATOR DE PERDAS ---
    fator_perdas_sistema = system_loss / 100.0

    def calcular_producao_por_linha(row):
        timestamp_inicio = row['DataHora'] - pd.Timedelta(minutes=15)
        mes, hora, minuto = timestamp_inicio.month, timestamp_inicio.hour, timestamp_inicio.minute

        energia_diaria_base = dados_producao_distrito.get(mes, 0)
        
        # Fórmula de cálculo da sua versão original
        energia_diaria_total_sistema = (
            energia_diaria_base * potencia_kwp *
            fator_inclinacao * fator_orientacao *
            (1 - fator_perdas_sistema)
        )
        
        perfil_mensal = perfis_quarto_horarios.get(mes, {})
        fator_distribuicao = perfil_mensal.get((hora, minuto), 0)
        
        producao_kwh_intervalo = energia_diaria_total_sistema * fator_distribuicao
        return producao_kwh_intervalo

    df_resultado['Producao_Solar_kWh'] = df_resultado.apply(calcular_producao_por_linha, axis=1)

    # Bloco de suavização e cálculo final (mantém-se igual)
    soma_original_precisa = df_resultado['Producao_Solar_kWh'].sum()
    df_resultado['Producao_Solar_kWh'] = df_resultado['Producao_Solar_kWh'].rolling(window=4, center=False, min_periods=1).mean()
    soma_apos_suavizar = df_resultado['Producao_Solar_kWh'].sum()
    if soma_apos_suavizar > 0:
        fator_correcao = soma_original_precisa / soma_apos_suavizar
        df_resultado['Producao_Solar_kWh'] *= fator_correcao

    df_resultado['Autoconsumo_kWh'] = np.minimum(df_resultado['Consumo (kWh)'], df_resultado['Producao_Solar_kWh'])
    df_resultado['Excedente_kWh'] = np.maximum(0, df_resultado['Producao_Solar_kWh'] - df_resultado['Consumo (kWh)'])
    df_resultado['Consumo_Rede_kWh'] = np.maximum(0, df_resultado['Consumo (kWh)'] - df_resultado['Autoconsumo_kWh'])

    return df_resultado

def calcular_analise_longo_prazo(
    custo_instalacao, 
    poupanca_autoconsumo_anual_base,
    poupanca_venda_anual_base,
    anos_analise, 
    taxa_degradacao_perc, 
    taxa_inflacao_energia_perc,
    taxa_variacao_venda_perc
):
    """
    Calcula o payback detalhado, o fluxo de caixa e o ROI simples anual.
    """
    if custo_instalacao <= 0:
        payback_imediato = True
    else:
        payback_imediato = False

    # --- NOVO: Cálculo do ROI Simples Anual ---
    poupanca_anual_total_base = poupanca_autoconsumo_anual_base + poupanca_venda_anual_base
    if custo_instalacao > 0 and poupanca_anual_total_base > 0:
        roi_simples_anual = (poupanca_anual_total_base / custo_instalacao) * 100
    else:
        # Se não há custo ou não há poupança, o ROI é 0 ou indefinido. Retornamos 0.
        roi_simples_anual = 0.0
    # --- FIM DO NOVO CÓDIGO ---

    taxa_degradacao = taxa_degradacao_perc / 100.0
    taxa_inflacao = taxa_inflacao_energia_perc / 100.0
    taxa_venda = taxa_variacao_venda_perc / 100.0

    fluxo_caixa_anual = []
    fluxo_caixa_acumulado_lista = []
    poupanca_acumulada = 0
    payback_anos_detalhado = 0.0 if payback_imediato else float('inf')

    for ano in range(1, int(anos_analise) + 1):
        fator_producao = (1 - taxa_degradacao) ** (ano - 1)
        fator_preco_compra = (1 + taxa_inflacao) ** (ano - 1)
        poupanca_autoconsumo_ano = poupanca_autoconsumo_anual_base * fator_producao * fator_preco_compra

        fator_preco_venda = (1 + taxa_venda) ** (ano - 1)
        poupanca_venda_ano = poupanca_venda_anual_base * fator_producao * fator_preco_venda

        poupanca_ano_corrente = poupanca_autoconsumo_ano + poupanca_venda_ano
        fluxo_caixa_anual.append(poupanca_ano_corrente)

        poupanca_acumulada_anterior = poupanca_acumulada
        poupanca_acumulada += poupanca_ano_corrente
        fluxo_caixa_acumulado_lista.append(poupanca_acumulada)

        if payback_anos_detalhado == float('inf') and poupanca_acumulada >= custo_instalacao:
            if poupanca_ano_corrente > 0:
                valor_em_falta_no_inicio_do_ano = custo_instalacao - poupanca_acumulada_anterior
                fracao_do_ano = valor_em_falta_no_inicio_do_ano / poupanca_ano_corrente
                payback_anos_detalhado = (ano - 1) + fracao_do_ano
            else:
                payback_anos_detalhado = ano

    if payback_anos_detalhado == float('inf') and anos_analise > 0:
         payback_anos_detalhado = float('inf')

    # --- NOVO: Adicionar o ROI ao dicionário de retorno ---
    return {
        "payback_detalhado": payback_anos_detalhado,
        "poupanca_total_periodo": poupanca_acumulada,
        "fluxo_caixa_anual": fluxo_caixa_anual,
        "fluxo_caixa_acumulado": fluxo_caixa_acumulado_lista,
        "anos_analise": anos_analise,
        "roi_simples_anual": roi_simples_anual # <-- NOVA CHAVE
    }
