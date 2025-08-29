import streamlit as st
import pandas as pd
import datetime
from calendar import monthrange

# --- Carregar ficheiro Excel do GitHub ---
@st.cache_data(ttl=1800, show_spinner=False) # Cache por 30 minutos (1800 segundos)
def carregar_dados_excel(url):
    xls = pd.ExcelFile(url)
    omie_ciclos = xls.parse("OMIE_CICLOS")
    # Limpar nomes das colunas em OMIE_CICLOS
    omie_ciclos.columns = [str(c).strip() for c in omie_ciclos.columns]
    
    # GARANTIR QUE TEMOS COLUNAS DE DATA E HORA SEPARADAS
    if 'Data' not in omie_ciclos.columns and 'DataHora' in omie_ciclos.columns:
        temp_dt = pd.to_datetime(omie_ciclos['DataHora'])
        omie_ciclos['Data'] = temp_dt.dt.strftime('%m/%d/%Y')
        omie_ciclos['Hora'] = temp_dt.dt.strftime('%H:%M')

    if 'Data' in omie_ciclos.columns and 'Hora' in omie_ciclos.columns:
        # CORREÇÃO: Forçar a leitura com o formato exato MM/DD/YYYY HH:MM
        omie_ciclos['DataHora'] = pd.to_datetime(
            omie_ciclos['Data'].astype(str) + ' ' + omie_ciclos['Hora'].astype(str),
            format='%m/%d/%Y %H:%M',  # Formato Americano
            errors='coerce'
        ).dt.tz_localize(None)
        
        omie_ciclos.dropna(subset=['DataHora'], inplace=True)
        omie_ciclos.drop_duplicates(subset=['DataHora'], keep='first', inplace=True)
    else:
        st.error("Colunas 'Data' e 'Hora' não encontradas na aba OMIE_CICLOS.")

    constantes = xls.parse("Constantes")
    return omie_ciclos, constantes

def processar_ficheiro_consumos(ficheiro_excel):
    """
    Lê um ficheiro Excel da E-Redes, deteta se é de uma instalação com ou sem UPAC,
    extrai os dados relevantes de consumo e injeção, e retorna um DataFrame padronizado.
    """
    try:
        # 1. Encontrar a linha do cabeçalho (lógica mantida)
        df_temp = pd.read_excel(ficheiro_excel, header=None, nrows=20)
        header_row_index = -1
        for i, row in df_temp.iterrows():
            if "Data" in row.values and "Hora" in row.values:
                header_row_index = i
                break
        if header_row_index == -1:
            return None, "Não foi possível encontrar a linha de cabeçalho com 'Data' e 'Hora'."

        df = pd.read_excel(ficheiro_excel, header=header_row_index)
        df.columns = [str(c).strip() for c in df.columns]

        # 2. Deteção do tipo de instalação (com ou sem UPAC)
        colunas_df = df.columns
        tem_injecao = any("Injeção" in col for col in colunas_df)
        
        df_final = pd.DataFrame()

        # 3. Mapeamento de colunas para nomes padronizados
        MAPA_COLUNAS = {
            # Consumo
            'Consumo_Rede_kWh': ["Consumo medido na IC, Ativa (kW)"],
            'Consumo_Total_Casa_kWh': ["Consumo registado (kW)", "Consumo registado, Ativa (kW)"],
            # Injeção
            'Injecao_Rede_kWh': ["Injeção na rede medida na IC, Ativa (kW)"],
            'Injecao_Total_UPAC_kWh': ["Injeção registada (kW)", "Injeção registada, Ativa (kW)"],
            # Potência (para análise)
            'Potencia_kW_Para_Analise': ["Consumo registado (kW)", "Consumo registado, Ativa (kW)", "Consumo medido na IC, Ativa (kW)"]
        }

        for nome_padrao, nomes_possiveis in MAPA_COLUNAS.items():
            for nome_col in nomes_possiveis:
                if nome_col in colunas_df:
                    # Converte para kWh (divide por 4) e guarda com nome padronizado
                    df_final[nome_padrao] = pd.to_numeric(df[nome_col], errors='coerce') / 4.0
                    break # Para ao encontrar a primeira correspondência
        
        # Lógica especial para o caso SEM UPAC
        if not tem_injecao:
            # O consumo total da casa é o que vem da rede
            if 'Consumo_Total_Casa_kWh' in df_final.columns:
                 df_final['Consumo_Rede_kWh'] = df_final['Consumo_Total_Casa_kWh']
            
        # Garantir que todas as colunas essenciais existem, preenchendo com 0 se faltarem
        colunas_essenciais = ['Consumo_Rede_kWh', 'Consumo_Total_Casa_kWh', 'Injecao_Rede_kWh', 'Injecao_Total_UPAC_kWh', 'Potencia_kW_Para_Analise']
        for col in colunas_essenciais:
            if col not in df_final.columns:
                df_final[col] = 0.0

        # 4. Processamento de Data e Hora (lógica mantida)
        df_final['DataHora'] = pd.to_datetime(
            df['Data'].astype(str) + ' ' + df['Hora'].astype(str),
            errors='coerce'
        ).dt.tz_localize(None)

        # Ajuste para o timestamp 00:00
        df_final['DataHora'] = df_final['DataHora'].apply(
            lambda ts: ts - pd.Timedelta(minutes=1) if ts and ts.time() == datetime.time(0, 0) else ts
        )
        
        df_final.dropna(subset=['DataHora'], inplace=True)

        # 5. Cálculo dos valores derivados
        # Autoconsumo = O que a casa consumiu no total - O que foi preciso ir buscar à rede
        df_final['Autoconsumo_Settlement_kWh'] = (df_final['Consumo_Total_Casa_kWh'] - df_final['Consumo_Rede_kWh']).round(5)
        # Garante que não há valores negativos por imprecisões de float
        df_final['Autoconsumo_Settlement_kWh'] = df_final['Autoconsumo_Settlement_kWh'].clip(lower=0)
        
        # Renomear a coluna principal de consumo para consistência com o resto do simulador
        df_final.rename(columns={'Consumo_Rede_kWh': 'Consumo (kWh)'}, inplace=True)
        
        colunas_de_retorno = [
            'DataHora', 
            'Consumo (kWh)', # Consumo líquido da rede
            'Injecao_Rede_kWh', # Injeção líquida na rede
            'Consumo_Total_Casa_kWh', # Consumo bruto da casa
            'Injecao_Total_UPAC_kWh', # Injeção bruta da UPAC
            'Autoconsumo_Settlement_kWh', # Autoconsumo de Settlement/Netmetering
            'Potencia_kW_Para_Analise'
        ]

        return df_final[colunas_de_retorno], None

    except Exception as e:
        return None, f"Erro ao processar ficheiro: {e}"
    
def validar_e_juntar_ficheiros(lista_de_ficheiros):
    """
    Processa uma lista de ficheiros da E-Redes, verifica se há sobreposição de datas
    e, se não houver, junta todos os dados num único DataFrame.
    """
    if not lista_de_ficheiros:
        return None, "Nenhum ficheiro carregado."

    dataframes_processados = []
    intervalos_de_datas = []
    data_limite = datetime.date(2024, 1, 1)

    for ficheiro in lista_de_ficheiros:
        df_individual, erro = processar_ficheiro_consumos(ficheiro)
        if erro:
            return None, f"Erro ao processar o ficheiro '{ficheiro.name}': {erro}"
        
        if df_individual.empty:
            continue

        dataframes_processados.append(df_individual)
        min_data = df_individual['DataHora'].min()
        if min_data.date() < data_limite:
            erro_msg = (
                f"Erro no ficheiro '{ficheiro.name}': Contém dados de '{min_data.strftime('%d/%m/%Y')}', "
                f"que é anterior à data mínima permitida de 01/01/2024. Remova-o!"
            )
            return None, erro_msg
        max_data = df_individual['DataHora'].max()
        intervalos_de_datas.append((min_data, max_data))

    if not dataframes_processados:
        return None, "Nenhum dos ficheiros continha dados válidos."

    if len(intervalos_de_datas) > 1:
        intervalos_ordenados = sorted(intervalos_de_datas, key=lambda x: x[0])
        
        for i in range(1, len(intervalos_ordenados)):
            inicio_atual = intervalos_ordenados[i][0]
            fim_anterior = intervalos_ordenados[i-1][1]
            
            if inicio_atual < fim_anterior:
                erro_msg = (
                    f"Erro: Sobreposição de datas detetada! O período que começa em "
                    f"{inicio_atual.strftime('%d/%m/%Y')} sobrepõe-se ao período que termina em "
                    f"{fim_anterior.strftime('%d/%m/%Y')}. Por favor, carregue ficheiros com períodos distintos."
                )
                return None, erro_msg

    df_final_combinado = pd.concat(dataframes_processados, ignore_index=True)
    df_final_combinado = df_final_combinado.sort_values(by='DataHora').reset_index(drop=True)
    df_final_combinado = df_final_combinado.drop_duplicates(subset=['DataHora'], keep='first')

    return df_final_combinado, None

def agregar_consumos_por_periodo(df_consumos, df_omie_ciclos):
    if df_consumos is None or df_consumos.empty: return {}

    df_merged = pd.merge(df_consumos, df_omie_ciclos, on='DataHora', how='left')

    consumos_agregados = {'Simples': df_merged['Consumo (kWh)'].sum()}
    
    for ciclo in ['BD', 'BS', 'TD', 'TS']:
        if ciclo in df_merged.columns:
            df_merged[ciclo] = df_merged[ciclo].fillna('Desconhecido')
            soma_por_periodo = df_merged.groupby(ciclo)['Consumo (kWh)'].sum().to_dict()
            consumos_agregados[ciclo] = soma_por_periodo
            
    return consumos_agregados

def calcular_medias_omie_para_todos_ciclos(df_consumos_periodo, df_omie_completo):
    """
    Calcula as médias OMIE para todos os ciclos, com base no intervalo de datas
    do dataframe de consumos fornecido.
    """
    if df_consumos_periodo.empty:
        return {}
    
    min_date = df_consumos_periodo['DataHora'].min()
    max_date = df_consumos_periodo['DataHora'].max()
    
    df_omie_filtrado = df_omie_completo[
        (df_omie_completo['DataHora'] >= min_date) & 
        (df_omie_completo['DataHora'] <= max_date)
    ].copy()

    if df_omie_filtrado.empty:
        return {}

    omie_medios = {'S': df_omie_filtrado['OMIE'].mean()}
    for ciclo in ['BD', 'BS', 'TD', 'TS']:
        if ciclo in df_omie_filtrado.columns:
            agrupado = df_omie_filtrado.groupby(ciclo)['OMIE'].mean()
            for periodo, media in agrupado.items():
                omie_medios[f"{ciclo}_{periodo}"] = media
    return omie_medios