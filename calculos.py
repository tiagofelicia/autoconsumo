import streamlit as st
import pandas as pd
import re
import requests
import numpy as np
from io import StringIO


# Importar as constantes e funções que são necessárias dentro deste módulo
# Assumimos que a variável CONSTANTES e outras como FINANCIAMENTO_TSE_VAL
# serão passadas como argumentos para as funções que as usam,
# ou então terá de as passar do ficheiro principal.
# Por agora, vamos manter assim, pois as funções já recebem os dataframes necessários.

IDENTIFICADORES_COMERCIALIZADORES_CAV_FIXA = [
    "CUR",
    "EDP",
    "Galp",
    "Goldenergy",
    "Ibelectra",
    "Iberdrola",
    "Luzigás",
    "Plenitude",
    "YesEnergy"     
    # Adicionar outros identificadores conforme necessário
]


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

# --- Função para obter valor da TAR energia por período ---
def obter_tar_energia_periodo(opcao_horaria_str, periodo_str, potencia_kva, constantes_df):
    nome_constante = ""
    opcao_lower = str(opcao_horaria_str).lower()
    periodo_upper = str(periodo_str).upper()

    if opcao_lower == "simples": nome_constante = "TAR_Energia_Simples"
    elif opcao_lower.startswith("bi"):
        if periodo_upper == 'V': nome_constante = "TAR_Energia_Bi_Vazio"
        elif periodo_upper == 'F': nome_constante = "TAR_Energia_Bi_ForaVazio"
    elif opcao_lower.startswith("tri"):
        if potencia_kva <= 20.7:
            if periodo_upper == 'V': nome_constante = "TAR_Energia_Tri_Vazio"
            elif periodo_upper == 'C': nome_constante = "TAR_Energia_Tri_Cheias"
            elif periodo_upper == 'P': nome_constante = "TAR_Energia_Tri_Ponta"
        else: # > 20.7 kVA
            if periodo_upper == 'V': nome_constante = "TAR_Energia_Tri_27.6_Vazio"
            elif periodo_upper == 'C': nome_constante = "TAR_Energia_Tri_27.6_Cheias"
            elif periodo_upper == 'P': nome_constante = "TAR_Energia_Tri_27.6_Ponta"

    if nome_constante:
        return obter_constante(nome_constante, constantes_df)
    return 0.0

# --- Função: Obter valor da TAR potência para a potência contratada ---
def obter_tar_dia(potencia_kva, constantes_df):
    potencia_str = str(float(potencia_kva)) # Formato consistente
    constante_potencia = f'TAR_Potencia {potencia_str}'
    return obter_constante(constante_potencia, constantes_df)


# Função para calcular a expressão de consumo (apenas para somas, resultado inteiro)
def calcular_expressao_matematica_simples(expressao_str, periodo_label=""):
    """
    Calcula uma expressão matemática simples de adição e subtração, 
    arredondando o resultado para o inteiro mais próximo.
    Ex: '10+20-5', '10.5 - 2.5 + 0.5'
    """
    if not expressao_str or not isinstance(expressao_str, str):
        return 0, f"Nenhum valor introduzido para {periodo_label}." if periodo_label else "Nenhum valor introduzido."

    # 1. Validação de caracteres permitidos
    # Permite dígitos, ponto decimal, operadores + e -, e espaços.
    valid_chars = set('0123456789.+- ')
    if not all(char in valid_chars for char in expressao_str):
        return 0, f"Expressão inválida para {periodo_label}: '{expressao_str}'. Use apenas números, '.', '+', '-'. O resultado será arredondado."

    expressao_limpa = expressao_str.replace(" ", "") # Remove todos os espaços
    if not expressao_limpa: # Se após remover espaços a string estiver vazia
        return 0, f"Expressão vazia para {periodo_label}."

    # 2. Normalizar operadores duplos (ex: -- para +, +- para -)
    # Este loop garante que sequências como "---" ou "-+-" são corretamente simplificadas.
    temp_expr = expressao_limpa
    while True:
        prev_expr = temp_expr
        temp_expr = temp_expr.replace("--", "+")
        temp_expr = temp_expr.replace("+-", "-")
        temp_expr = temp_expr.replace("-+", "-")
        temp_expr = temp_expr.replace("++", "+")
        if temp_expr == prev_expr: # Termina quando não há mais alterações
            break
    expressao_limpa = temp_expr

    # 3. Verificar se a expressão é apenas um operador ou termina/começa invalidamente com um
    if expressao_limpa in ["+", "-"] or \
       expressao_limpa.endswith(("+", "-")) or \
       (expressao_limpa.startswith(("+", "-")) and len(expressao_limpa) > 1 and expressao_limpa[1] in "+-"): # Ex: "++5", "-+5" já normalizado, mas evita "+5", "-5" aqui
        if not ( (expressao_limpa.startswith(("+", "-")) and len(expressao_limpa) > 1 and expressao_limpa[1].isdigit()) or \
                 (expressao_limpa.startswith(("+", "-")) and len(expressao_limpa) > 2 and expressao_limpa[1] == '.' and expressao_limpa[2].isdigit() ) ): # Permite "+5", "-5", "+.5", "-.5"
            return 0, f"Expressão inválida para {periodo_label}: '{expressao_str}'. Formato de operador inválido."


    # 4. Adicionar um '+' no início se a expressão começar com um número ou ponto decimal, para facilitar a divisão.
    #    Ex: "10-5" -> "+10-5"; ".5+2" -> "+.5+2"
    if expressao_limpa and (expressao_limpa[0].isdigit() or \
        (expressao_limpa.startswith('.') and len(expressao_limpa) > 1 and expressao_limpa[1].isdigit())):
        expressao_limpa = "+" + expressao_limpa
    elif expressao_limpa.startswith('.') and not (len(expressao_limpa) > 1 and (expressao_limpa[1].isdigit() or expressao_limpa[1] in "+-")): # Casos como "." ou ".+"
         return 0, f"Expressão inválida para {periodo_label}: '{expressao_str}'. Ponto decimal mal formatado."

    # 5. Dividir a expressão em operadores ([+\-]) e os operandos que se seguem.
    #    Ex: "+10.5-5" -> ['', '+', '10.5', '-', '5'] (o primeiro '' é por causa do split no início)
    #    Ex: "-5+3" -> ['', '-', '5', '+', '3']
    partes = re.split(r'([+\-])', expressao_limpa)
    
    # Filtrar strings vazias resultantes do split (principalmente a primeira se existir)
    partes_filtradas = [p for p in partes if p]

    if not partes_filtradas:
        return 0, f"Expressão inválida para {periodo_label}: '{expressao_str}'. Não resultou em operandos válidos."

    # A estrutura deve ser [operador, operando, operador, operando, ...]
    # Portanto, o comprimento da lista filtrada deve ser par e pelo menos 2 (ex: ['+', '10'])
    if len(partes_filtradas) % 2 != 0 or len(partes_filtradas) == 0:
        return 0, f"Expressão mal formada para {periodo_label}: '{expressao_str}'. Estrutura de operadores/operandos inválida."

    total = 0.0
    try:
        for i in range(0, len(partes_filtradas), 2):
            operador = partes_filtradas[i]
            operando_str = partes_filtradas[i+1]

            if not operando_str : # Operando em falta
                return 0, f"Expressão mal formada para {periodo_label}: '{expressao_str}'. Operando em falta após operador '{operador}'."

            # Validação robusta do operando antes de converter para float
            # Deve ser um número, pode conter um ponto decimal. Não pode ser apenas "."
            if operando_str == '.' or not operando_str.replace('.', '', 1).isdigit():
                 return 0, f"Operando inválido '{operando_str}' na expressão para {periodo_label}."
            
            valor_operando = float(operando_str)

            if operador == '+':
                total += valor_operando
            elif operador == '-':
                total -= valor_operando
            else: 
                # Esta condição não deve ser atingida devido ao re.split('([+\-])')
                return 0, f"Operador desconhecido '{operador}' na expressão para {periodo_label}."

    except ValueError: # Erro ao converter operando_str para float
        return 0, f"Expressão inválida para {periodo_label}: '{expressao_str}'. Contém valor não numérico ou mal formatado."
    except IndexError: # Falha ao aceder partes_filtradas[i+1], indica erro de parsing não apanhado antes.
        return 0, f"Expressão mal formada para {periodo_label}: '{expressao_str}'. Estrutura inesperada."
    except Exception as e: # Captura outras exceções inesperadas
        return 0, f"Erro ao calcular expressão para {periodo_label} ('{expressao_str}'): {e}"

    # Arredondar para o inteiro mais próximo
    total_arredondado = int(round(total))

    # Manter a lógica original de não permitir consumo negativo
    if total_arredondado < 0:
        return 0, f"Consumo calculado para {periodo_label} não pode ser negativo ({total_arredondado} kWh, calculado de {total:.4f} kWh)."
    
    return total_arredondado, None # Retorna o valor inteiro arredondado e nenhum erro

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
        consumo_s = float(consumos_periodos.get('S', 0.0) or 0.0)
        preco_s = float(preco_energia_final_sem_iva_simples or 0.0)
        custo_total_sem_iva = consumo_s * preco_s
    else: # Bi ou Tri
        for periodo, consumo_p in consumos_periodos.items():
            consumo_p_float = float(consumo_p or 0.0)
            preco_h = float(precos_horarios.get(periodo, 0.0) or 0.0)
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
            consumo_s = float(consumos_periodos.get('S', 0.0) or 0.0)
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

# --- Função: Calcular custo da potência com IVA ---
def calcular_custo_potencia_com_iva_final(preco_comercializador_dia_sem_iva, tar_potencia_final_dia_sem_iva, dias, potencia_kva):
    iva_normal_perc = 0.23
    iva_reduzido_perc = 0.06
    
    preco_comercializador_dia_sem_iva = float(preco_comercializador_dia_sem_iva or 0.0)
    tar_potencia_final_dia_sem_iva = float(tar_potencia_final_dia_sem_iva or 0.0) # Esta TAR já tem TS, se aplicável
    dias = int(dias or 0)

    if dias <= 0:
        return {'custo_com_iva': 0.0, 'custo_sem_iva': 0.0, 'valor_iva_6': 0.0, 'valor_iva_23': 0.0}

    custo_comerc_siva_periodo = preco_comercializador_dia_sem_iva * dias
    custo_tar_siva_periodo = tar_potencia_final_dia_sem_iva * dias
    custo_total_potencia_siva = custo_comerc_siva_periodo + custo_tar_siva_periodo

    iva_6_pot = 0.0
    iva_23_pot = 0.0
    custo_total_com_iva = 0.0

    # Aplicar IVA separado: 23% no comercializador, 6% na TAR final
    if potencia_kva <= 3.45:
        iva_23_pot = custo_comerc_siva_periodo * iva_normal_perc
        iva_6_pot = custo_tar_siva_periodo * iva_reduzido_perc
        custo_total_com_iva = (custo_comerc_siva_periodo + iva_23_pot) + (custo_tar_siva_periodo + iva_6_pot)
    else: # potencia_kva > 3.45
    # Aplicar IVA normal (23%) à soma das componentes finais
        iva_23_pot = custo_total_potencia_siva * iva_normal_perc
        custo_total_com_iva = custo_total_potencia_siva + iva_23_pot
        # iva_6_pot permanece 0.0

    return {
        'custo_com_iva': round(custo_total_com_iva, 4),
        'custo_sem_iva': round(custo_total_potencia_siva, 4),
        'valor_iva_6': round(iva_6_pot, 4),
        'valor_iva_23': round(iva_23_pot, 4)
    }
    return round(custo_total_com_iva, 4)

# --- Função: Calcular taxas adicionais ---
def calcular_taxas_adicionais(
    consumo_kwh,
    dias_simulacao,
    tarifa_social_bool,
    valor_dgeg_mensal,
    valor_cav_mensal,
    nome_comercializador_atual,
    aplica_taxa_fixa_mensal, # NOVO PARÂMETRO
    valor_iec=0.001
):
    """
    Calcula taxas adicionais (IEC, DGEG, CAV) com lógica ajustada para CAV mensal fixa
    para comercializadores específicos.
    A decisão de aplicar a taxa fixa é agora controlada pelo parâmetro 'aplica_taxa_fixa_mensal'.
    """
    iva_normal_perc = 0.23
    iva_reduzido_perc = 0.06 # IVA da CAV é 6%

    consumo_kwh_float = float(consumo_kwh or 0.0)
    dias_simulacao_int = int(dias_simulacao or 0)
    valor_dgeg_mensal_float = float(valor_dgeg_mensal or 0.0)
    valor_cav_mensal_float = float(valor_cav_mensal or 0.0) # Renomeado para consistência
    valor_iec_float = float(valor_iec or 0.0)

    if dias_simulacao_int <= 0:
        return {
            'custo_com_iva': 0.0, 'custo_sem_iva': 0.0,
            'iec_sem_iva': 0.0, 'dgeg_sem_iva': 0.0, 'cav_sem_iva': 0.0,
            'valor_iva_6': 0.0, 'valor_iva_23': 0.0
        }

    # Custos Sem IVA
    # IEC (Imposto Especial de Consumo)
    iec_siva = 0.0 if tarifa_social_bool else (consumo_kwh_float * valor_iec_float)

    # DGEG (Taxa de Exploração da Direção-Geral de Energia e Geologia) - sempre proporcional
    dgeg_siva = (valor_dgeg_mensal_float * 12 / 365.25 * dias_simulacao_int)
    
    cav_siva = 0.0
    
    # LÓGICA ALTERADA: A decisão vem de fora da função
    aplica_cav_fixa_mensal_final = False
    if nome_comercializador_atual and isinstance(nome_comercializador_atual, str):
        nome_comerc_lower_para_verificacao = nome_comercializador_atual.lower()
        if any(identificador.lower() in nome_comerc_lower_para_verificacao for identificador in IDENTIFICADORES_COMERCIALIZADORES_CAV_FIXA):
            # Se for um comercializador da lista, a decisão depende do parâmetro externo
            if aplica_taxa_fixa_mensal:
                aplica_cav_fixa_mensal_final = True

    if aplica_cav_fixa_mensal_final:
        cav_siva = valor_cav_mensal_float  # Aplica o valor mensal total da CAV
    else:
        # Cálculo proporcional padrão para os outros casos
        cav_siva = (valor_cav_mensal_float * 12 / 365.25 * dias_simulacao_int)

    # Valores de IVA (lógica mantém-se)
    iva_iec = 0.0 if tarifa_social_bool else (iec_siva * iva_normal_perc)
    iva_dgeg = dgeg_siva * iva_normal_perc
    iva_cav = cav_siva * iva_reduzido_perc

    custo_total_siva = iec_siva + dgeg_siva + cav_siva
    custo_total_com_iva = (iec_siva + iva_iec) + (dgeg_siva + iva_dgeg) + (cav_siva + iva_cav)
    
    total_iva_6_calculado = iva_cav
    total_iva_23_calculado = iva_iec + iva_dgeg

    return {
        'custo_com_iva': round(custo_total_com_iva, 4),
        'custo_sem_iva': round(custo_total_siva, 4),
        'iec_sem_iva': round(iec_siva, 4),
        'dgeg_sem_iva': round(dgeg_siva, 4),
        'cav_sem_iva': round(cav_siva, 4),
        'valor_iva_6': round(total_iva_6_calculado, 4),
        'valor_iva_23': round(total_iva_23_calculado, 4)
    }

    
### NOVO: Função de cálculo dedicada para o Tarifário Personalizado ###
def calcular_custo_personalizado(precos_energia_pers, preco_potencia_pers, consumos_para_calculo, flags_pers, CONSTANTES, FINANCIAMENTO_TSE_VAL,**kwargs):
    """
    Função reutilizável para calcular o custo de uma estrutura tarifária personalizada.
    Agora também retorna os dicionários completos para os tooltips.
    """
    # Extrair parâmetros globais
    dias = kwargs.get('dias')
    potencia = kwargs.get('potencia')
    tarifa_social = kwargs.get('tarifa_social')
    familia_numerosa = kwargs.get('familia_numerosa')
    valor_dgeg_user = kwargs.get('valor_dgeg_user')
    valor_cav_user = kwargs.get('valor_cav_user')
    opcao_horaria_ref = kwargs.get('opcao_horaria_ref')

    # 1. Obter componentes base (sem IVA)
    tar_energia_reg = {p: obter_tar_energia_periodo(opcao_horaria_ref, p, potencia, CONSTANTES) for p in consumos_para_calculo.keys()}
    tar_potencia_reg = obter_tar_dia(potencia, CONSTANTES)
    
    comerc_energia = {p: (preco - tar_energia_reg.get(p, 0)) if flags_pers['tar_energia'] else preco for p, preco in precos_energia_pers.items()}
    comerc_potencia = (preco_potencia_pers - tar_potencia_reg) if flags_pers['tar_potencia'] else preco_potencia_pers
    
    financiamento_tse_a_somar = FINANCIAMENTO_TSE_VAL if not flags_pers['tse_incluido'] else 0.0

    # 2. Preços finais sem IVA (já com descontos TS)
    preco_final_siva = {}
    desconto_ts_energia = obter_constante('Desconto TS Energia', CONSTANTES) if tarifa_social else 0
    for p, comp_comerc in comerc_energia.items():
        preco_final_siva[p] = comp_comerc + tar_energia_reg.get(p, 0) - desconto_ts_energia + financiamento_tse_a_somar

    desconto_ts_potencia_bruto = obter_constante(f'Desconto TS Potencia {potencia}', CONSTANTES) if tarifa_social else 0
    desconto_ts_potencia_aplicado = min(tar_potencia_reg, desconto_ts_potencia_bruto) if tarifa_social else 0.0
    preco_potencia_final_siva = comerc_potencia + tar_potencia_reg - desconto_ts_potencia_aplicado

    # 3. Calcular custos totais com IVA
    consumo_total = sum(consumos_para_calculo.values())
    decomposicao_energia = calcular_custo_energia_com_iva(consumo_total, preco_final_siva.get('S'), {k:v for k,v in preco_final_siva.items() if k!='S'}, dias, potencia, opcao_horaria_ref, consumos_para_calculo, familia_numerosa)
    
    tar_potencia_final_com_ts = tar_potencia_reg - desconto_ts_potencia_aplicado
    decomposicao_potencia = calcular_custo_potencia_com_iva_final(comerc_potencia, tar_potencia_final_com_ts, dias, potencia)
    
    is_billing_month = 28 <= dias <= 31
    decomposicao_taxas = calcular_taxas_adicionais(consumo_total, dias, tarifa_social, valor_dgeg_user, valor_cav_user, "Personalizado", is_billing_month)
    
    custo_total = decomposicao_energia['custo_com_iva'] + decomposicao_potencia['custo_com_iva'] + decomposicao_taxas['custo_com_iva']
    
    # 4. Construir dicionários para os tooltips
    componentes_tooltip_energia = {}
    for p_key in preco_final_siva.keys():
        componentes_tooltip_energia[f'tooltip_energia_{p_key}_comerc_sem_tar'] = comerc_energia.get(p_key, 0.0)
        componentes_tooltip_energia[f'tooltip_energia_{p_key}_tar_bruta'] = tar_energia_reg.get(p_key, 0.0)
        componentes_tooltip_energia[f'tooltip_energia_{p_key}_tse_declarado_incluido'] = flags_pers['tse_incluido']
        componentes_tooltip_energia[f'tooltip_energia_{p_key}_tse_valor_nominal'] = FINANCIAMENTO_TSE_VAL
        componentes_tooltip_energia[f'tooltip_energia_{p_key}_ts_aplicada_flag'] = tarifa_social
        componentes_tooltip_energia[f'tooltip_energia_{p_key}_ts_desconto_valor'] = desconto_ts_energia

    componentes_tooltip_potencia = {
        'tooltip_pot_comerc_sem_tar': comerc_potencia,
        'tooltip_pot_tar_bruta': tar_potencia_reg,
        'tooltip_pot_ts_aplicada': tarifa_social,
        'tooltip_pot_desconto_ts_valor': desconto_ts_potencia_aplicado
    }
    
    componentes_tooltip_total = {
        'tt_cte_energia_siva': decomposicao_energia['custo_sem_iva'],
        'tt_cte_potencia_siva': decomposicao_potencia['custo_sem_iva'],
        'tt_cte_iec_siva': decomposicao_taxas['iec_sem_iva'],
        'tt_cte_dgeg_siva': decomposicao_taxas['dgeg_sem_iva'],
        'tt_cte_cav_siva': decomposicao_taxas['cav_sem_iva'],
        'tt_cte_total_siva': decomposicao_energia['custo_sem_iva'] + decomposicao_potencia['custo_sem_iva'] + decomposicao_taxas['custo_sem_iva'],
        'tt_cte_valor_iva_6_total': decomposicao_energia['valor_iva_6'] + decomposicao_potencia['valor_iva_6'] + decomposicao_taxas['valor_iva_6'],
        'tt_cte_valor_iva_23_total': decomposicao_energia['valor_iva_23'] + decomposicao_potencia['valor_iva_23'] + decomposicao_taxas['valor_iva_23'],
        'tt_cte_subtotal_civa': decomposicao_energia['custo_com_iva'] + decomposicao_potencia['custo_com_iva'] + decomposicao_taxas['custo_com_iva'],
        'tt_cte_desc_finais_valor': 0.0,
        'tt_cte_acres_finais_valor': 0.0,
        **{f"tt_preco_unit_energia_{p}_siva": v for p, v in preco_final_siva.items()},
        'tt_preco_unit_potencia_siva': preco_potencia_final_siva
    }

    return {
        'Total (€)': custo_total,
        'PrecosFinaisSemIVA': preco_final_siva,
        'PrecoPotenciaFinalSemIVA': preco_potencia_final_siva,
        'componentes_tooltip_custo_total_dict': componentes_tooltip_total,
        'componentes_tooltip_energia_dict': componentes_tooltip_energia,
        'componentes_tooltip_potencia_dict': componentes_tooltip_potencia
    }

#Função Tarifário Fixo para comparação
def calcular_detalhes_custo_tarifario_fixo(
    dados_tarifario_linha,
    opcao_horaria_para_calculo,
    consumos_repartidos_dict,
    potencia_contratada_kva,
    dias_calculo,
    tarifa_social_ativa,
    familia_numerosa_ativa,
    valor_dgeg_user_input,
    valor_cav_user_input,
    incluir_quota_acp_input,
    desconto_continente_input,
    CONSTANTES_df,
    dias_no_mes_selecionado_dict,
    mes_selecionado_pelo_user_str,
    ano_atual_calculo,
    data_inicio_periodo_obj,
    data_fim_periodo_obj,
    FINANCIAMENTO_TSE_VAL,
    VALOR_QUOTA_ACP_MENSAL
):
    """
    Calcula o custo total e os componentes de tooltip para um DADO TARIFÁRIO FIXO.
    """
    try:
        nome_comercializador_para_taxas = str(dados_tarifario_linha.get('comercializador', 'Desconhecido'))
        nome_tarifario_original = str(dados_tarifario_linha['nome'])
        nome_a_exibir_final = nome_tarifario_original

        # --- Obter Preços e Flags do Tarifário para a OPÇÃO HORÁRIA DE CÁLCULO ---
        # Esta parte é crucial: os preços devem ser os corretos para a 'opcao_horaria_para_calculo'
        preco_energia_input_tf = {}
        oh_calc_lower = opcao_horaria_para_calculo.lower()

        if oh_calc_lower == "simples":
            preco_s = dados_tarifario_linha.get('preco_energia_simples')
            if pd.notna(preco_s): preco_energia_input_tf['S'] = float(preco_s)
            else: return None
        elif oh_calc_lower.startswith("bi-horário"):
            preco_v_bi = dados_tarifario_linha.get('preco_energia_vazio_bi')
            preco_f_bi = dados_tarifario_linha.get('preco_energia_fora_vazio')
            if pd.notna(preco_v_bi) and pd.notna(preco_f_bi):
                preco_energia_input_tf['V'] = float(preco_v_bi)
                preco_energia_input_tf['F'] = float(preco_f_bi)
            else: return None
        elif oh_calc_lower.startswith("tri-horário"):
            if pd.notna(dados_tarifario_linha.get('preco_energia_vazio_tri')) and pd.notna(dados_tarifario_linha.get('preco_energia_cheias')) and pd.notna(dados_tarifario_linha.get('preco_energia_ponta')):
                preco_energia_input_tf['V'] = float(dados_tarifario_linha.get('preco_energia_vazio_tri', 0.0))
                preco_energia_input_tf['C'] = float(dados_tarifario_linha.get('preco_energia_cheias', 0.0))
                preco_energia_input_tf['P'] = float(dados_tarifario_linha.get('preco_energia_ponta', 0.0))
            else: return None
        else: return None
        
        # --- NOVO: Define se é um mês de faturação completo DENTRO da função ---
        is_billing_month = 28 <= dias_calculo <= 31

        preco_potencia_input_tf = float(dados_tarifario_linha.get('preco_potencia_dia', 0.0))
        tar_incluida_energia_tf = dados_tarifario_linha.get('tar_incluida_energia', True)
        tar_incluida_potencia_tf = dados_tarifario_linha.get('tar_incluida_potencia', True)
        financiamento_tse_incluido_tf = dados_tarifario_linha.get('financiamento_tse_incluido', True)

        # --- Passo 1: Identificar Componentes Base (Sem IVA, Sem TS) ---
        tar_energia_regulada_tf = {}
        for periodo_consumo_key in consumos_repartidos_dict.keys(): # S, V, F, C, P
            tar_energia_regulada_tf[periodo_consumo_key] = obter_tar_energia_periodo(
                opcao_horaria_para_calculo, periodo_consumo_key, potencia_contratada_kva, CONSTANTES_df
            )

        tar_potencia_regulada_tf = obter_tar_dia(potencia_contratada_kva, CONSTANTES_df)

        preco_comercializador_energia_tf = {}
        for periodo_preco_key, preco_val_tf in preco_energia_input_tf.items():
            if periodo_preco_key not in consumos_repartidos_dict: continue # Só se houver consumo nesse período
            if tar_incluida_energia_tf:
                preco_comercializador_energia_tf[periodo_preco_key] = preco_val_tf - tar_energia_regulada_tf.get(periodo_preco_key, 0.0)
            else:
                preco_comercializador_energia_tf[periodo_preco_key] = preco_val_tf
        
        if tar_incluida_potencia_tf:
            preco_comercializador_potencia_tf = preco_potencia_input_tf - tar_potencia_regulada_tf
        else:
            preco_comercializador_potencia_tf = preco_potencia_input_tf
        preco_comercializador_potencia_tf = max(0.0, preco_comercializador_potencia_tf)

        financiamento_tse_a_adicionar_tf = FINANCIAMENTO_TSE_VAL if not financiamento_tse_incluido_tf else 0.0

        # --- Passo 2: Calcular Componentes TAR Finais (Com Desconto TS, Sem IVA) ---
        tar_energia_final_tf = {}
        tar_potencia_final_dia_tf = tar_potencia_regulada_tf
        desconto_ts_energia_aplicado_val = 0.0
        desconto_ts_potencia_aplicado_val = 0.0

        if tarifa_social_ativa:
            desconto_ts_energia_bruto = obter_constante('Desconto TS Energia', CONSTANTES_df)
            desconto_ts_potencia_dia_bruto = obter_constante(f'Desconto TS Potencia {potencia_contratada_kva}', CONSTANTES_df)
            for periodo_calc, tar_reg_val in tar_energia_regulada_tf.items():
                tar_energia_final_tf[periodo_calc] = tar_reg_val - desconto_ts_energia_bruto
            desconto_ts_energia_aplicado_val = desconto_ts_energia_bruto # Para tooltip
            
            tar_potencia_final_dia_tf = max(0.0, tar_potencia_regulada_tf - desconto_ts_potencia_dia_bruto)
            desconto_ts_potencia_aplicado_val = min(tar_potencia_regulada_tf, desconto_ts_potencia_dia_bruto) # Para tooltip
        else:
            tar_energia_final_tf = tar_energia_regulada_tf.copy()

        # --- Passo 3: Calcular Preço Final Energia (€/kWh, Sem IVA) ---
        preco_energia_final_sem_iva_tf_dict = {}
        for periodo_calc in consumos_repartidos_dict.keys(): # Iterar sobre os períodos COM CONSUMO
            if periodo_calc in preco_comercializador_energia_tf: # Verificar se há preço definido para este período
                preco_energia_final_sem_iva_tf_dict[periodo_calc] = (
                    preco_comercializador_energia_tf.get(periodo_calc, 0.0) +
                    tar_energia_final_tf.get(periodo_calc, 0.0) +
                    financiamento_tse_a_adicionar_tf
                )

        # --- Passo 4: Calcular Componentes Finais Potência (€/dia, Sem IVA) ---
        preco_comercializador_potencia_final_sem_iva_tf = preco_comercializador_potencia_tf

        # --- Passo 5 & 6: Calcular Custo Total Energia e Potência (Com IVA) ---
        consumo_total_neste_oh = sum(float(v or 0) for v in consumos_repartidos_dict.values())

        decomposicao_custo_energia_tf = calcular_custo_energia_com_iva(
            consumo_total_neste_oh,
            preco_energia_final_sem_iva_tf_dict.get('S') if opcao_horaria_para_calculo.lower() == "simples" else None,
            {p: v for p, v in preco_energia_final_sem_iva_tf_dict.items() if p != 'S'},
            dias_calculo, potencia_contratada_kva, opcao_horaria_para_calculo,
            consumos_repartidos_dict, # Usar os consumos repartidos para esta opção horária
            familia_numerosa_ativa
        )
        
        decomposicao_custo_potencia_tf_calc = calcular_custo_potencia_com_iva_final(
            preco_comercializador_potencia_final_sem_iva_tf,
            tar_potencia_final_dia_tf,  # <--- USE DIRETAMENTE A VARIÁVEL CORRETA
            dias_calculo, potencia_contratada_kva
        )

        # --- Passo 7: Calcular Taxas Adicionais ---
        decomposicao_taxas_tf = calcular_taxas_adicionais(
            consumo_total_neste_oh,
            dias_calculo,
            tarifa_social_ativa,
            valor_dgeg_user_input,
            valor_cav_user_input,
            nome_comercializador_para_taxas,
            aplica_taxa_fixa_mensal=is_billing_month # Usa a variável que definimos acima
        )

        e_mes_completo_selecionado_calc = is_billing_month # Substituição direta

        # --- Passo 8: Calcular Custo Total Final e aplicar descontos específicos ---
        custo_total_antes_desc_fatura_tf = (
            decomposicao_custo_energia_tf['custo_com_iva'] +
            decomposicao_custo_potencia_tf_calc['custo_com_iva'] +
            decomposicao_taxas_tf['custo_com_iva']
        )

        # Desconto de fatura do Excel
        desconto_fatura_mensal_excel = float(dados_tarifario_linha.get('desconto_fatura_mes', 0.0) or 0.0)
        desconto_fatura_periodo_aplicado = 0.0
        if desconto_fatura_mensal_excel > 0:
            nome_a_exibir_final += f" (INCLUI desc. fat. {desconto_fatura_mensal_excel:.2f}€/mês)"
            desconto_fatura_periodo_aplicado = (desconto_fatura_mensal_excel / 30.0) * dias_calculo if not e_mes_completo_selecionado_calc else desconto_fatura_mensal_excel
        
        custo_apos_desc_fatura_excel = custo_total_antes_desc_fatura_tf - desconto_fatura_periodo_aplicado
        
        # Quota ACP
        custo_apos_acp = custo_apos_desc_fatura_excel
        quota_acp_periodo_aplicada = 0.0
        if incluir_quota_acp_input and nome_tarifario_original.startswith("Goldenergy - ACP"):
            quota_acp_a_aplicar = (VALOR_QUOTA_ACP_MENSAL / 30.0) * dias_calculo if not e_mes_completo_selecionado_calc else VALOR_QUOTA_ACP_MENSAL
            custo_apos_acp += quota_acp_a_aplicar
            nome_a_exibir_final += f" (INCLUI Quota ACP - {VALOR_QUOTA_ACP_MENSAL:.2f} €/mês)"
            quota_acp_periodo_aplicada = quota_acp_a_aplicar

        # Desconto MEO
        custo_antes_desconto_meo = custo_apos_acp
        desconto_meo_periodo_aplicado = 0.0
        if "meo energia - tarifa fixa - clientes meo" in nome_tarifario_original.lower() and \
           (consumo_total_neste_oh / dias_calculo * 30.0 if dias_calculo > 0 else 0) >= 216:
            desconto_meo_mensal_base = 0.0
            if opcao_horaria_para_calculo.lower() == "simples": desconto_meo_mensal_base = 2.95
            elif opcao_horaria_para_calculo.lower().startswith("bi-horário"): desconto_meo_mensal_base = 3.50
            elif opcao_horaria_para_calculo.lower().startswith("tri-horário"): desconto_meo_mensal_base = 6.27
            if desconto_meo_mensal_base > 0 and dias_calculo > 0:
                desconto_meo_periodo_aplicado = (desconto_meo_mensal_base / 30.0) * dias_calculo
                custo_antes_desconto_meo -= desconto_meo_periodo_aplicado
                nome_a_exibir_final += f" (Desc. MEO {desconto_meo_periodo_aplicado:.2f}€ incl.)"
        
        # Desconto Continente
        custo_base_para_continente = custo_antes_desconto_meo
        custo_total_final = custo_base_para_continente 
        valor_X_desconto_continente_aplicado = 0.0

        if desconto_continente_input and nome_tarifario_original.startswith("Galp & Continente"):
    
            # CALCULAR O CUSTO BRUTO (SEM TARIFA SOCIAL) APENAS PARA ESTE DESCONTO
    
            # 1. Preço unitário bruto da energia (sem IVA e sem desconto TS)
            preco_energia_bruto_sem_iva = {}
            for p in consumos_repartidos_dict.keys():
                if p in preco_comercializador_energia_tf:
                    preco_energia_bruto_sem_iva[p] = (
                        preco_comercializador_energia_tf[p] + 
                        tar_energia_regulada_tf.get(p, 0.0) + # <--- USA A TAR BRUTA, sem desconto TS
                        financiamento_tse_a_adicionar_tf
                    )

            # 2. Preço unitário bruto da potência (sem IVA e sem desconto TS)
            preco_comerc_pot_bruto = preco_comercializador_potencia_tf
            tar_potencia_bruta = tar_potencia_regulada_tf # <--- USA A TAR BRUTA, sem desconto TS

            # 3. Calcular o custo bruto COM IVA para a energia e potência
            custo_energia_bruto_cIVA = calcular_custo_energia_com_iva(
                consumo_total_neste_oh,
                preco_energia_bruto_sem_iva.get('S'),
                {k: v for k, v in preco_energia_bruto_sem_iva.items() if k != 'S'},
                dias_calculo, potencia_contratada_kva, opcao_horaria_para_calculo,
                consumos_repartidos_dict, familia_numerosa_ativa
            )
            custo_potencia_bruto_cIVA = calcular_custo_potencia_com_iva_final(
                preco_comerc_pot_bruto,
                tar_potencia_bruta,
                dias_calculo, potencia_contratada_kva
            )

            # ### DESCONTO DE 10% ###
            if nome_tarifario_original.startswith("Galp & Continente (-10% DD)"):
                valor_X_desconto_continente_aplicado = (custo_energia_bruto_cIVA['custo_com_iva'] + custo_potencia_bruto_cIVA['custo_com_iva']) * 0.10
                custo_total_final = custo_base_para_continente - valor_X_desconto_continente_aplicado
                nome_a_exibir_final += f" (INCLUI desc. Cont. de {valor_X_desconto_continente_aplicado:.2f}€, s/ desc. Cont.={custo_base_para_continente:.2f}€)"
            
            # ### DESCONTO DE 7% ###
            elif nome_tarifario_original.startswith("Galp & Continente (-7%)"):
                valor_X_desconto_continente_aplicado = (custo_energia_bruto_cIVA['custo_com_iva'] + custo_potencia_bruto_cIVA['custo_com_iva']) * 0.07
                custo_total_final = custo_base_para_continente - valor_X_desconto_continente_aplicado
                nome_a_exibir_final += f" (INCLUI desc. Cont. de {valor_X_desconto_continente_aplicado:.2f}€, s/ desc. Cont.={custo_base_para_continente:.2f}€)"

        # --- Construir Dicionários de Tooltip ---
        # Tooltip Energia
        componentes_tooltip_energia_dict = {}
        for p_key_tt_energia in preco_energia_final_sem_iva_tf_dict.keys():
            componentes_tooltip_energia_dict[f'tooltip_energia_{p_key_tt_energia}_comerc_sem_tar'] = preco_comercializador_energia_tf.get(p_key_tt_energia, 0.0)
            componentes_tooltip_energia_dict[f'tooltip_energia_{p_key_tt_energia}_tar_bruta'] = tar_energia_regulada_tf.get(p_key_tt_energia, 0.0)
            componentes_tooltip_energia_dict[f'tooltip_energia_{p_key_tt_energia}_tse_declarado_incluido'] = financiamento_tse_incluido_tf
            componentes_tooltip_energia_dict[f'tooltip_energia_{p_key_tt_energia}_tse_valor_nominal'] = FINANCIAMENTO_TSE_VAL
            componentes_tooltip_energia_dict[f'tooltip_energia_{p_key_tt_energia}_ts_aplicada_flag'] = tarifa_social_ativa
            componentes_tooltip_energia_dict[f'tooltip_energia_{p_key_tt_energia}_ts_desconto_valor'] = obter_constante('Desconto TS Energia', CONSTANTES_df) if tarifa_social_ativa else 0.0
        
        # Tooltip Potência
        componentes_tooltip_potencia_dict = {
            'tooltip_pot_comerc_sem_tar': preco_comercializador_potencia_tf, # Já após desconto %, mas antes de TS
            'tooltip_pot_tar_bruta': tar_potencia_regulada_tf,
            'tooltip_pot_ts_aplicada': tarifa_social_ativa,
            'tooltip_pot_desconto_ts_valor': desconto_ts_potencia_aplicado_val # Valor efetivo do desconto TS na TAR
        }

        # Preço unitário da potência s/IVA (comercializador + TAR final)
        preco_unit_potencia_siva_tf = preco_comercializador_potencia_final_sem_iva_tf + tar_potencia_final_dia_tf # Esta é a soma correta

        # Tooltip Custo Total
        componentes_tooltip_total_dict = {
            'tt_cte_energia_siva': decomposicao_custo_energia_tf['custo_sem_iva'],
            'tt_cte_potencia_siva': decomposicao_custo_potencia_tf_calc['custo_sem_iva'],
            'tt_cte_iec_siva': decomposicao_taxas_tf['iec_sem_iva'],
            'tt_cte_dgeg_siva': decomposicao_taxas_tf['dgeg_sem_iva'],
            'tt_cte_cav_siva': decomposicao_taxas_tf['cav_sem_iva'],
            'tt_cte_total_siva': decomposicao_custo_energia_tf['custo_sem_iva'] + decomposicao_custo_potencia_tf_calc['custo_sem_iva'] + decomposicao_taxas_tf['custo_sem_iva'],
            'tt_cte_valor_iva_6_total': decomposicao_custo_energia_tf['valor_iva_6'] + decomposicao_custo_potencia_tf_calc['valor_iva_6'] + decomposicao_taxas_tf['valor_iva_6'],
            'tt_cte_valor_iva_23_total': decomposicao_custo_energia_tf['valor_iva_23'] + decomposicao_custo_potencia_tf_calc['valor_iva_23'] + decomposicao_taxas_tf['valor_iva_23'],
            'tt_cte_subtotal_civa': custo_total_antes_desc_fatura_tf,
            'tt_cte_desc_finais_valor': desconto_fatura_periodo_aplicado + desconto_meo_periodo_aplicado + valor_X_desconto_continente_aplicado,
            'tt_cte_acres_finais_valor': quota_acp_periodo_aplicada,
            **{f"tt_preco_unit_energia_{p}_siva": v for p, v in preco_energia_final_sem_iva_tf_dict.items()},
            'tt_preco_unit_potencia_siva': preco_unit_potencia_siva_tf
        }
        
        # Para ter a certeza que retornamos algo, vamos simplificar o retorno por agora
        return {
            'Total (€)': custo_total_final,
            'NomeParaExibirAjustado': nome_a_exibir_final,
            'componentes_tooltip_custo_total_dict': componentes_tooltip_total_dict,
            'componentes_tooltip_energia_dict': componentes_tooltip_energia_dict,
            'componentes_tooltip_potencia_dict': componentes_tooltip_potencia_dict
        }
    
    except Exception as e:
        st.error(f"!!! ERRO DENTRO de `calcular_detalhes_custo_tarifario_fixo` para '{dados_tarifario_linha.get('nome', 'Desconhecido')}' na opção '{opcao_horaria_para_calculo}':")
        st.exception(e) # Isto vai imprimir o traceback completo do erro
        return None
    
    
def preparar_consumos_para_cada_opcao_destino(
    opcao_horaria_principal_str,
    consumos_input_atuais_dict,
    opcoes_destino_db_nomes_list
):
    """
    Prepara os dicionários de consumo para cada opção horária de destino,
    convertendo os consumos manuais da opção principal para as estruturas de destino.
    """
    consumos_para_calculo_por_oh_destino = {}
    oh_principal_lower = opcao_horaria_principal_str.lower()

    # Ler os consumos da opção principal selecionada pelo utilizador
    c_s_in = float(consumos_input_atuais_dict.get('S', 0))
    c_v_in = float(consumos_input_atuais_dict.get('V', 0))
    c_f_in = float(consumos_input_atuais_dict.get('F', 0)) # Para Bi
    c_c_in = float(consumos_input_atuais_dict.get('C', 0)) # Para Tri
    c_p_in = float(consumos_input_atuais_dict.get('P', 0)) # Para Tri

    for oh_destino_str in opcoes_destino_db_nomes_list:
        oh_destino_lower = oh_destino_str.lower()
        consumos_finais_para_este_destino = {}

        # Calcular os consumos para a opção de destino com base na opção principal
        if oh_destino_lower == "simples":
            if oh_principal_lower.startswith("simples"):
                consumos_finais_para_este_destino['S'] = c_s_in
            elif oh_principal_lower.startswith("bi-horário"):
                consumos_finais_para_este_destino['S'] = c_v_in + c_f_in
            elif oh_principal_lower.startswith("tri-horário"):
                consumos_finais_para_este_destino['S'] = c_v_in + c_c_in + c_p_in

        elif oh_destino_lower.startswith("bi-horário"):
            # A conversão para Bi-horário só é necessária se a origem for Tri-horário ou Bi-horário
            if oh_principal_lower.startswith("tri-horário"):
                consumos_finais_para_este_destino['V'] = c_v_in
                consumos_finais_para_este_destino['F'] = c_c_in + c_p_in
            elif oh_principal_lower.startswith("bi-horário"):
                consumos_finais_para_este_destino['V'] = c_v_in
                consumos_finais_para_este_destino['F'] = c_f_in
        
        elif oh_destino_lower.startswith("tri-horário"):
             # A conversão para Tri-horário só é possível se a origem também for Tri-horário
             if oh_principal_lower.startswith("tri-horário"):
                consumos_finais_para_este_destino['V'] = c_v_in
                consumos_finais_para_este_destino['C'] = c_c_in
                consumos_finais_para_este_destino['P'] = c_p_in
        
        # Adicionar ao dicionário final apenas se houver consumos calculados
        if consumos_finais_para_este_destino and sum(v for v in consumos_finais_para_este_destino.values() if v is not None) > 0:
            consumos_para_calculo_por_oh_destino[oh_destino_str] = consumos_finais_para_este_destino
            
    return consumos_para_calculo_por_oh_destino
#FIM DETERMINAÇÃO DE OPÇÕES HORÁRIAS

#DETERMINAÇÃO DE OPÇÕES HORÁRIAS
def determinar_opcoes_horarias_destino_e_ordenacao(
    opcao_horaria_principal_str,
    potencia_kva_num,
    opcoes_horarias_existentes_lista,
    is_file_loaded: bool
):
    """
    Determina as opções horárias de destino para a tabela de comparação,
    seguindo as regras específicas para o modo com e sem ficheiro da E-Redes.
    """
    oh_principal_lower = opcao_horaria_principal_str.lower()
    destino_cols_nomes_unicos = []
    coluna_ordenacao_inicial_aggrid = None

    # Nomes EXATOS da base de dados (Excel) para consistência
    SIMPLES_DB = "Simples"
    BI_DIARIO_DB = "Bi-horário - Ciclo Diário"
    BI_SEMANAL_DB = "Bi-horário - Ciclo Semanal"
    TRI_DIARIO_DB = "Tri-horário - Ciclo Diário"
    TRI_SEMANAL_DB = "Tri-horário - Ciclo Semanal"
    TRI_DIARIO_ALTA_DB = "Tri-horário > 20.7 kVA - Ciclo Diário"
    TRI_SEMANAL_ALTA_DB = "Tri-horário > 20.7 kVA - Ciclo Semanal"
    
    opcoes_bi_horario = [BI_DIARIO_DB, BI_SEMANAL_DB]
    opcoes_tri_horario_normal = [TRI_DIARIO_DB, TRI_SEMANAL_DB]
    opcoes_tri_horario_alta = [TRI_DIARIO_ALTA_DB, TRI_SEMANAL_ALTA_DB]

    if is_file_loaded:
        # Lógica para QUANDO HÁ ficheiro (esta parte MANTÉM-SE IGUAL)
        if potencia_kva_num > 20.7:
            destino_cols_nomes_unicos.extend(opcoes_tri_horario_alta)
        else: # <= 20.7 kVA
            destino_cols_nomes_unicos.append(SIMPLES_DB)
            destino_cols_nomes_unicos.extend(opcoes_bi_horario)
            destino_cols_nomes_unicos.extend(opcoes_tri_horario_normal)
    else:
        # LÓGICA NOVA (SEM FICHEIRO) - Implementa as suas 4 regras
        if oh_principal_lower.startswith("tri-horário > 20.7 kva"):
            # Regra 4: se Opção Horária e Ciclo = Tri-horário > 20.7 kVA -> apenas Tri-horário.
            destino_cols_nomes_unicos.extend(opcoes_tri_horario_alta)
        
        elif oh_principal_lower.startswith("tri-horário"):
            # Regra 3: se Opção Horária e Ciclo = Tri-horário <= 20.7 kVA -> Simples, Bi-horário e Tri-horário.
            destino_cols_nomes_unicos.append(SIMPLES_DB)
            destino_cols_nomes_unicos.extend(opcoes_bi_horario)
            destino_cols_nomes_unicos.extend(opcoes_tri_horario_normal)
            
        elif oh_principal_lower.startswith("bi-horário"):
            # Regra 2: se Opção Horária e Ciclo = Bi-horário -> Simples e Bi-horário.
            destino_cols_nomes_unicos.append(SIMPLES_DB)
            destino_cols_nomes_unicos.extend(opcoes_bi_horario)
            
        elif oh_principal_lower == "simples":
            # Regra 1: se Opção Horária e Ciclo = Simples -> apenas Simples.
            destino_cols_nomes_unicos.append(SIMPLES_DB)

    # Filtrar para garantir que apenas opções que realmente existem no ficheiro Excel são incluídas
    destino_cols_nomes_unicos = [
        opt for opt in destino_cols_nomes_unicos if opt in opcoes_horarias_existentes_lista
    ]

    # Ordenar as opções de destino encontradas de forma consistente
    ordem_preferencial = {
        SIMPLES_DB: 0, BI_DIARIO_DB: 1, BI_SEMANAL_DB: 2,
        TRI_DIARIO_DB: 3, TRI_SEMANAL_DB: 4,
        TRI_DIARIO_ALTA_DB: 5, TRI_SEMANAL_ALTA_DB: 6
    }
    destino_cols_nomes_unicos = sorted(
        list(set(destino_cols_nomes_unicos)), # Garante unicidade e ordena
        key=lambda x: ordem_preferencial.get(x, 99)
    )

    # Definir a coluna de ordenação inicial da tabela
    if opcao_horaria_principal_str in destino_cols_nomes_unicos:
        coluna_ordenacao_inicial_aggrid = f"Total {opcao_horaria_principal_str} (€)"
    elif destino_cols_nomes_unicos: # Se a lista não estiver vazia, ordena pela primeira coluna disponível
        coluna_ordenacao_inicial_aggrid = f"Total {destino_cols_nomes_unicos[0]} (€)"
    
    colunas_formatadas = [f"Total {op} (€)" for op in destino_cols_nomes_unicos]

    return destino_cols_nomes_unicos, colunas_formatadas, coluna_ordenacao_inicial_aggrid
    
###############################################################
######################### AUTOCONSUMO #########################
###############################################################
def interpolar_perfis_para_quarto_horario(perfis_horarios):
    """
    Converte um dicionário de perfis de produção horários para perfis quarto-horários
    através de interpolação linear, garantindo que a produção noturna é zero.
    """
    perfis_quarto_horarios = {}
    for distrito, perfis_mensais in perfis_horarios.items():
        perfis_quarto_horarios[distrito] = {}
        for mes, perfil_hora in perfis_mensais.items():
            novo_perfil_mes = {}
            horas_ordenadas = sorted(perfil_hora.keys())
            
            for i, hora_atual in enumerate(horas_ordenadas):
                valor_hora_atual = perfil_hora[hora_atual]
                
                # Encontrar a próxima hora com produção para interpolar
                valor_hora_seguinte = 0
                if i + 1 < len(horas_ordenadas):
                    hora_seguinte = horas_ordenadas[i+1]
                    # Só interpola se as horas forem consecutivas
                    if hora_seguinte == hora_atual + 1:
                        valor_hora_seguinte = perfil_hora[hora_seguinte]

                # O valor da hora cheia (ex: 09:00) representa a média da primeira metade da hora.
                # O valor da próxima hora (ex: 10:00) a da segunda metade.
                # Ajustamos a interpolação para criar uma curva mais suave.
                ponto_00 = valor_hora_atual
                ponto_15 = valor_hora_atual * 0.75 + valor_hora_seguinte * 0.25
                ponto_30 = valor_hora_atual * 0.50 + valor_hora_seguinte * 0.50
                ponto_45 = valor_hora_atual * 0.25 + valor_hora_seguinte * 0.75
                
                # Estes fatores ainda representam uma TAXA HORÁRIA.
                # O fator final para o dicionário deve ser o valor para um intervalo de 15 minutos.
                # Portanto, dividimos cada um por 4.
                novo_perfil_mes[(hora_atual, 0)] = ponto_00 / 4.0
                if ponto_15 > 0: novo_perfil_mes[(hora_atual, 15)] = ponto_15 / 4.0
                if ponto_30 > 0: novo_perfil_mes[(hora_atual, 30)] = ponto_30 / 4.0
                if ponto_45 > 0: novo_perfil_mes[(hora_atual, 45)] = ponto_45 / 4.0

            perfis_quarto_horarios[distrito][mes] = novo_perfil_mes
            
    return perfis_quarto_horarios


def simular_autoconsumo_completo(df_consumos, potencia_kwp, distrito, inclinacao, orientacao_str):
    """
    Função completa e rigorosa para simular a produção solar, usando:
    1. Dados de produção diária média por mês do PVGIS para cada distrito.
    2. Perfis de distribuição horária distintos para cada mês e para cada distrito.
    """
    if df_consumos is None or df_consumos.empty:
        return df_consumos.copy()

    # Fonte: PVGIS PVdata. Produção diária média (kWh) para um sistema de 1 kWp otimizado.
    DADOS_PVGIS_DISTRITO = {
        'Aveiro': {1:3.55, 2:4.43, 3:4.79, 4:5.34, 5:5.66, 6:5.66, 7:5.97, 8:5.92, 9:5.44, 10:4.31, 11:3.53, 12:3.34},
        'Beja': {1: 4.09, 2: 4.76, 3: 5.18, 4: 5.46, 5: 5.74, 6: 5.89, 7: 6.29, 8: 6.2, 9: 5.69, 10: 4.8, 11: 4.13, 12: 3.78},
        'Braga': {1: 3.18, 2: 4.01, 3: 4.45, 4: 4.91, 5: 5.35, 6: 5.43, 7: 5.88, 8: 5.84, 9: 5.25, 10: 3.98, 11: 3.18, 12: 2.95},
        'Bragança': {1: 3.22, 2: 4.41, 3: 4.89, 4: 5.25, 5: 5.73, 6: 5.92, 7: 6.41, 8: 6.26, 9: 5.62, 10: 4.28, 11: 3.37, 12: 2.88},
        'Castelo Branco': {1: 3.8, 2: 4.68, 3: 5.06, 4: 5.45, 5: 5.78, 6: 5.94, 7: 6.32, 8: 6.23, 9: 5.64, 10: 4.5, 11: 3.73, 12: 3.48},
        'Coimbra': {1: 3.27, 2: 4.12, 3: 4.5, 4: 4.92, 5: 5.37, 6: 5.37, 7: 5.9, 8: 5.86, 9: 5.31, 10: 4.13, 11: 3.29, 12: 3.05},
        'Évora': {1: 4.03, 2: 4.73, 3: 5.13, 4: 5.37, 5: 5.75, 6: 5.88, 7: 6.3, 8: 6.23, 9: 5.66, 10: 4.66, 11: 4.01, 12: 3.73},
        'Faro': {1: 4.56, 2: 5.11, 3: 5.62, 4: 6.02, 5: 6.26, 6: 6.31, 7: 6.52, 8: 6.42, 9: 6.07, 10: 5.14, 11: 4.51, 12: 4.19},
        'Guarda': {1: 3.5, 2: 4.4, 3: 4.89, 4: 5.23, 5: 5.68, 6: 5.91, 7: 6.45, 8: 6.33, 9: 5.59, 10: 4.37, 11: 3.45, 12: 3.17},
        'Leiria': {1: 3.53, 2: 4.32, 3: 4.72, 4: 5.1, 5: 5.5, 6: 5.52, 7: 5.98, 8: 6.0, 9: 5.47, 10: 4.32, 11: 3.53, 12: 3.32},
        'Lisboa': {1: 3.47, 2: 4.33, 3: 4.96, 4: 5.43, 5: 5.83, 6: 5.93, 7: 6.32, 8: 6.33, 9: 5.77, 10: 4.46, 11: 3.52, 12: 3.23},
        'Portalegre': {1: 3.83, 2: 4.61, 3: 5.0, 4: 5.31, 5: 5.73, 6: 5.93, 7: 6.39, 8: 6.3, 9: 5.6, 10: 4.54, 11: 3.76, 12: 3.54},
        'Porto': {1: 3.37, 2: 4.31, 3: 4.71, 4: 5.34, 5: 5.74, 6: 5.77, 7: 6.08, 8: 5.96, 9: 5.51, 10: 4.24, 11: 3.4, 12: 3.18},
        'Santarém': {1: 3.79, 2: 4.58, 3: 5.09, 4: 5.42, 5: 5.76, 6: 5.87, 7: 6.26, 8: 6.27, 9: 5.71, 10: 4.55, 11: 3.73, 12: 3.54},
        'Setúbal': {1: 3.9, 2: 4.61, 3: 5.19, 4: 5.58, 5: 5.91, 6: 5.99, 7: 6.31, 8: 6.34, 9: 5.88, 10: 4.7, 11: 3.91, 12: 3.66},
        'Viana do Castelo': {1: 3.17, 2: 4.15, 3: 4.62, 4: 5.32, 5: 5.71, 6: 5.81, 7: 6.11, 8: 5.96, 9: 5.47, 10: 4.1, 11: 3.28, 12: 2.95},
        'Vila Real': {1: 3.07, 2: 4.13, 3: 4.66, 4: 5.03, 5: 5.59, 6: 5.76, 7: 6.32, 8: 6.21, 9: 5.57, 10: 4.11, 11: 3.1, 12: 2.76},
        'Viseu': {1: 3.52, 2: 4.31, 3: 4.74, 4: 5.06, 5: 5.51, 6: 5.61, 7: 6.2, 8: 6.13, 9: 5.46, 10: 4.29, 11: 3.43, 12: 3.35},
        'Açores (Ponta Delgada)': {1: 2.9, 2: 3.59, 3: 4.23, 4: 4.63, 5: 4.98, 6: 5.03, 7: 5.11, 8: 5.29, 9: 4.81, 10: 3.8, 11: 3.04, 12: 2.52},
        'Madeira (Funchal)': {1: 3.74, 2: 4.08, 3: 4.8, 4: 4.79, 5: 4.87, 6: 4.64, 7: 5.2, 8: 5.32, 9: 4.48, 10: 4.18, 11: 3.66, 12: 3.49}
    }
    
    # Coordenadas utilizadas
    #    'Aveiro': (40.6405, -8.6538),
    #    'Beja': (38.0151, -7.8632),
    #    'Braga': (41.5454, -8.4265),
    #    'Bragança': (41.8060, -6.7567),
    #    'Castelo Branco': (39.8222, -7.4918),
    #    'Coimbra': (40.2115, -8.4292),
    #    'Évora': (38.5667, -7.9000),
    #    'Faro': (37.0194, -7.9304)
    #    'Guarda': (40.5373, -7.2676),
    #    'Leiria': (39.7436, -8.8071),
    #    'Lisboa': (38.7169, -9.1399),
    #    'Portalegre': (39.2922, -7.4289),
    #    'Porto': (41.1496, -8.6109),
    #    'Santarém': (39.2362, -8.6851),
    #    'Setúbal': (38.5260, -8.8902),
    #    'Viana do Castelo': (41.6918, -8.8345),
    #    'Vila Real': (41.3006, -7.7486),
    #    'Viseu': (40.6566, -7.9120),
    #    'Açores': (37.7412, -25.6756)
    #    'Madeira': (32.6669, -16.9241),

    # Perfis horários por distrito PVGIS TMYPVdata
    PERFIS_HORARIOS_MENSAIS_POR_DISTRITO = {
        'Aveiro': {
            1: {8: 0.0053, 9: 0.0707, 10: 0.1123, 11: 0.1452, 12: 0.1551, 13: 0.1612, 14: 0.1434, 15: 0.1171, 16: 0.0792, 17: 0.0104},
            2: {8: 0.0234, 9: 0.0703, 10: 0.1040, 11: 0.1327, 12: 0.1536, 13: 0.1513, 14: 0.1304, 15: 0.1159, 16: 0.0828, 17: 0.0357},
            3: {7: 0.0028, 8: 0.0369, 9: 0.0793, 10: 0.1116, 11: 0.1350, 12: 0.1423, 13: 0.1387, 14: 0.1271, 15: 0.1065, 16: 0.0748, 17: 0.0403, 18: 0.0046},
            4: {6: 0.0006, 7: 0.0156, 8: 0.0478, 9: 0.0814, 10: 0.1038, 11: 0.1233, 12: 0.1352, 13: 0.1333, 14: 0.1275, 15: 0.1021, 16: 0.0768, 17: 0.0424, 18: 0.0103},
            5: {6: 0.0042, 7: 0.0209, 8: 0.0524, 9: 0.0787, 10: 0.1021, 11: 0.1278, 12: 0.1359, 13: 0.1249, 14: 0.1118, 15: 0.1046, 16: 0.0778, 17: 0.0440, 18: 0.0132, 19: 0.0018},
            6: {6: 0.0063, 7: 0.0206, 8: 0.0476, 9: 0.0687, 10: 0.0919, 11: 0.1190, 12: 0.1323, 13: 0.1339, 14: 0.1208, 15: 0.1091, 16: 0.0815, 17: 0.0477, 18: 0.0165, 19: 0.0044},
            7: {6: 0.0042, 7: 0.0172, 8: 0.0436, 9: 0.0722, 10: 0.0949, 11: 0.1178, 12: 0.1326, 13: 0.1325, 14: 0.1219, 15: 0.1078, 16: 0.0819, 17: 0.0519, 18: 0.0175, 19: 0.0038},
            8: {6: 0.0010, 7: 0.0137, 8: 0.0425, 9: 0.0736, 10: 0.1020, 11: 0.1263, 12: 0.1342, 13: 0.1357, 14: 0.1254, 15: 0.1047, 16: 0.0797, 17: 0.0468, 18: 0.0133, 19: 0.0011},
            9: {7: 0.0051, 8: 0.0343, 9: 0.0629, 10: 0.0956, 11: 0.1244, 12: 0.1374, 13: 0.1454, 14: 0.1368, 15: 0.1115, 16: 0.0890, 17: 0.0502, 18: 0.0075},
            10: {7: 0.0052, 8: 0.0472, 9: 0.0875, 10: 0.1235, 11: 0.1391, 12: 0.1444, 13: 0.1376, 14: 0.1133, 15: 0.1120, 16: 0.0701, 17: 0.0201},
            11: {8: 0.0403, 9: 0.0935, 10: 0.1321, 11: 0.1514, 12: 0.1498, 13: 0.1470, 14: 0.1208, 15: 0.1025, 16: 0.0625, 17: 0.0002},
            12: {8: 0.0055, 9: 0.0842, 10: 0.1327, 11: 0.1584, 12: 0.1638, 13: 0.1543, 14: 0.1386, 15: 0.1030, 16: 0.0596}
        },
        'Beja': {
            1: {8: 0.0184, 9: 0.0786, 10: 0.1164, 11: 0.1464, 12: 0.1540, 13: 0.1529, 14: 0.1328, 15: 0.1044, 16: 0.0794, 17: 0.0168},
            2: {8: 0.0302, 9: 0.0754, 10: 0.1207, 11: 0.1357, 12: 0.1468, 13: 0.1359, 14: 0.1356, 15: 0.1076, 16: 0.0780, 17: 0.0340},
            3: {7: 0.0047, 8: 0.0434, 9: 0.0865, 10: 0.1150, 11: 0.1392, 12: 0.1263, 13: 0.1336, 14: 0.1223, 15: 0.1095, 16: 0.0736, 17: 0.0416, 18: 0.0044},
            4: {6: 0.0007, 7: 0.0175, 8: 0.0533, 9: 0.0888, 10: 0.1018, 11: 0.1236, 12: 0.1298, 13: 0.1244, 14: 0.1163, 15: 0.1084, 16: 0.0796, 17: 0.0460, 18: 0.0100},
            5: {6: 0.0042, 7: 0.0214, 8: 0.0573, 9: 0.0874, 10: 0.1122, 11: 0.1271, 12: 0.1323, 13: 0.1287, 14: 0.1147, 15: 0.0953, 16: 0.0696, 17: 0.0386, 18: 0.0100, 19: 0.0010},
            6: {6: 0.0055, 7: 0.0210, 8: 0.0563, 9: 0.0866, 10: 0.1071, 11: 0.1234, 12: 0.1294, 13: 0.1249, 14: 0.1150, 15: 0.1000, 16: 0.0725, 17: 0.0425, 18: 0.0127, 19: 0.0030},
            7: {6: 0.0038, 7: 0.0172, 8: 0.0502, 9: 0.0837, 10: 0.1055, 11: 0.1212, 12: 0.1298, 13: 0.1308, 14: 0.1194, 15: 0.1000, 16: 0.0773, 17: 0.0450, 18: 0.0131, 19: 0.0029},
            8: {6: 0.0012, 7: 0.0165, 8: 0.0509, 9: 0.0798, 10: 0.1044, 11: 0.1231, 12: 0.1363, 13: 0.1303, 14: 0.1180, 15: 0.1042, 16: 0.0783, 17: 0.0446, 18: 0.0117, 19: 0.0005},
            9: {7: 0.0151, 8: 0.0531, 9: 0.0871, 10: 0.1123, 11: 0.1285, 12: 0.1363, 13: 0.1373, 14: 0.1234, 15: 0.0984, 16: 0.0710, 17: 0.0345, 18: 0.0031},
            10: {7: 0.0086, 8: 0.0564, 9: 0.0828, 10: 0.1152, 11: 0.1414, 12: 0.1412, 13: 0.1459, 14: 0.1229, 15: 0.1032, 16: 0.0634, 17: 0.0190},
            11: {8: 0.0443, 9: 0.0862, 10: 0.1391, 11: 0.1571, 12: 0.1653, 13: 0.1386, 14: 0.1152, 15: 0.1008, 16: 0.0527, 17: 0.0007},
            12: {8: 0.0260, 9: 0.0804, 10: 0.1091, 11: 0.1617, 12: 0.1540, 13: 0.1692, 14: 0.1354, 15: 0.1064, 16: 0.0578}
        },
        'Braga': {
            1: {8: 0.0003, 9: 0.0743, 10: 0.1167, 11: 0.1572, 12: 0.1613, 13: 0.1448, 14: 0.1391, 15: 0.1241, 16: 0.0730, 17: 0.0092},
            2: {8: 0.0255, 9: 0.0779, 10: 0.1225, 11: 0.1387, 12: 0.1456, 13: 0.1428, 14: 0.1294, 15: 0.1041, 16: 0.0792, 17: 0.0343},
            3: {7: 0.0045, 8: 0.0447, 9: 0.0866, 10: 0.1108, 11: 0.1350, 12: 0.1333, 13: 0.1273, 14: 0.1257, 15: 0.1051, 16: 0.0773, 17: 0.0432, 18: 0.0064},
            4: {6: 0.0010, 7: 0.0182, 8: 0.0531, 9: 0.0853, 10: 0.1115, 11: 0.1193, 12: 0.1349, 13: 0.1314, 14: 0.1141, 15: 0.1017, 16: 0.0745, 17: 0.0440, 18: 0.0111},
            5: {6: 0.0049, 7: 0.0242, 8: 0.0591, 9: 0.0896, 10: 0.1078, 11: 0.1252, 12: 0.1253, 13: 0.1264, 14: 0.1100, 15: 0.0971, 16: 0.0725, 17: 0.0441, 18: 0.0123, 19: 0.0015},
            6: {6: 0.0064, 7: 0.0233, 8: 0.0545, 9: 0.0787, 10: 0.1043, 11: 0.1171, 12: 0.1279, 13: 0.1288, 14: 0.1182, 15: 0.0975, 16: 0.0761, 17: 0.0471, 18: 0.0162, 19: 0.0038},
            7: {6: 0.0042, 7: 0.0178, 8: 0.0495, 9: 0.0782, 10: 0.1022, 11: 0.1213, 12: 0.1284, 13: 0.1270, 14: 0.1193, 15: 0.1035, 16: 0.0793, 17: 0.0492, 18: 0.0163, 19: 0.0037},
            8: {6: 0.0014, 7: 0.0149, 8: 0.0447, 9: 0.0706, 10: 0.0982, 11: 0.1221, 12: 0.1337, 13: 0.1344, 14: 0.1226, 15: 0.1080, 16: 0.0852, 17: 0.0493, 18: 0.0138, 19: 0.0011},
            9: {7: 0.0130, 8: 0.0526, 9: 0.0836, 10: 0.1068, 11: 0.1261, 12: 0.1327, 13: 0.1381, 14: 0.1170, 15: 0.1081, 16: 0.0820, 17: 0.0360, 18: 0.0040},
            10: {7: 0.0053, 8: 0.0534, 9: 0.0953, 10: 0.1241, 11: 0.1395, 12: 0.1439, 13: 0.1422, 14: 0.1207, 15: 0.0942, 16: 0.0633, 17: 0.0181},
            11: {8: 0.0343, 9: 0.0968, 10: 0.1316, 11: 0.1482, 12: 0.1461, 13: 0.1494, 14: 0.1293, 15: 0.1006, 16: 0.0635, 17: 0.0002},
            12: {8: 0.0004, 9: 0.0777, 10: 0.1319, 11: 0.1586, 12: 0.1658, 13: 0.1660, 14: 0.1315, 15: 0.1101, 16: 0.0578}
        },
        'Bragança': {
            1: {8: 0.0088, 9: 0.0759, 10: 0.1134, 11: 0.1386, 12: 0.1616, 13: 0.1600, 14: 0.1567, 15: 0.1157, 16: 0.0690, 17: 0.0002},
            2: {8: 0.0283, 9: 0.0767, 10: 0.1129, 11: 0.1432, 12: 0.1491, 13: 0.1501, 14: 0.1375, 15: 0.0950, 16: 0.0791, 17: 0.0282},
            3: {7: 0.0068, 8: 0.0467, 9: 0.0867, 10: 0.1072, 11: 0.1314, 12: 0.1372, 13: 0.1349, 14: 0.1248, 15: 0.1088, 16: 0.0760, 17: 0.0377, 18: 0.0018},
            4: {6: 0.0013, 7: 0.0195, 8: 0.0533, 9: 0.0868, 10: 0.1180, 11: 0.1242, 12: 0.1227, 13: 0.1354, 14: 0.1242, 15: 0.0982, 16: 0.0723, 17: 0.0368, 18: 0.0071},
            5: {6: 0.0062, 7: 0.0281, 8: 0.0626, 9: 0.0909, 10: 0.1108, 11: 0.1230, 12: 0.1229, 13: 0.1183, 14: 0.1133, 15: 0.0992, 16: 0.0727, 17: 0.0392, 18: 0.0114, 19: 0.0013},
            6: {5: 0.0001, 6: 0.0075, 7: 0.0278, 8: 0.0605, 9: 0.0849, 10: 0.1094, 11: 0.1222, 12: 0.1210, 13: 0.1237, 14: 0.1132, 15: 0.0935, 16: 0.0767, 17: 0.0431, 18: 0.0130, 19: 0.0035},
            7: {6: 0.0055, 7: 0.0221, 8: 0.0546, 9: 0.0809, 10: 0.1003, 11: 0.1186, 12: 0.1331, 13: 0.1271, 14: 0.1189, 15: 0.1017, 16: 0.0758, 17: 0.0435, 18: 0.0146, 19: 0.0032},
            8: {6: 0.0022, 7: 0.0193, 8: 0.0537, 9: 0.0865, 10: 0.1134, 11: 0.1245, 12: 0.1304, 13: 0.1300, 14: 0.1174, 15: 0.0990, 16: 0.0732, 17: 0.0400, 18: 0.0098, 19: 0.0005},
            9: {7: 0.0192, 8: 0.0590, 9: 0.0887, 10: 0.1175, 11: 0.1305, 12: 0.1349, 13: 0.1356, 14: 0.1140, 15: 0.0999, 16: 0.0690, 17: 0.0291, 18: 0.0025},
            10: {7: 0.0114, 8: 0.0546, 9: 0.0918, 10: 0.1362, 11: 0.1456, 12: 0.1423, 13: 0.1472, 14: 0.1189, 15: 0.0925, 16: 0.0493, 17: 0.0102},
            11: {8: 0.0455, 9: 0.0867, 10: 0.1294, 11: 0.1484, 12: 0.1677, 13: 0.1508, 14: 0.1303, 15: 0.0951, 16: 0.0461},
            12: {8: 0.0150, 9: 0.0761, 10: 0.1154, 11: 0.1469, 12: 0.1700, 13: 0.1645, 14: 0.1470, 15: 0.1087, 16: 0.0565}
        },
        'Castelo Branco': {
            1: {8: 0.0128, 9: 0.0756, 10: 0.1104, 11: 0.1456, 12: 0.1498, 13: 0.1634, 14: 0.1354, 15: 0.1209, 16: 0.0773, 17: 0.0087},
            2: {8: 0.0272, 9: 0.0761, 10: 0.1095, 11: 0.1508, 12: 0.1453, 13: 0.1382, 14: 0.1331, 15: 0.1068, 16: 0.0826, 17: 0.0304},
            3: {7: 0.0053, 8: 0.0449, 9: 0.0807, 10: 0.1111, 11: 0.1266, 12: 0.1475, 13: 0.1316, 14: 0.1176, 15: 0.1103, 16: 0.0778, 17: 0.0426, 18: 0.0040},
            4: {6: 0.0009, 7: 0.0196, 8: 0.0586, 9: 0.0877, 10: 0.1136, 11: 0.1337, 12: 0.1291, 13: 0.1294, 14: 0.1052, 15: 0.0977, 16: 0.0748, 17: 0.0420, 18: 0.0077},
            5: {6: 0.0049, 7: 0.0245, 8: 0.0608, 9: 0.0917, 10: 0.1061, 11: 0.1263, 12: 0.1219, 13: 0.1216, 14: 0.1122, 15: 0.1058, 16: 0.0760, 17: 0.0358, 18: 0.0112, 19: 0.0011},
            6: {6: 0.0064, 7: 0.0248, 8: 0.0588, 9: 0.0880, 10: 0.1087, 11: 0.1221, 12: 0.1267, 13: 0.1221, 14: 0.1121, 15: 0.0958, 16: 0.0730, 17: 0.0443, 18: 0.0138, 19: 0.0034},
            7: {6: 0.0044, 7: 0.0183, 8: 0.0512, 9: 0.0828, 10: 0.1069, 11: 0.1210, 12: 0.1272, 13: 0.1250, 14: 0.1187, 15: 0.1036, 16: 0.0767, 17: 0.0467, 18: 0.0143, 19: 0.0031},
            8: {6: 0.0014, 7: 0.0166, 8: 0.0506, 9: 0.0825, 10: 0.1064, 11: 0.1251, 12: 0.1313, 13: 0.1332, 14: 0.1194, 15: 0.1029, 16: 0.0768, 17: 0.0427, 18: 0.0106, 19: 0.0005},
            9: {7: 0.0152, 8: 0.0538, 9: 0.0891, 10: 0.1163, 11: 0.1283, 12: 0.1310, 13: 0.1345, 14: 0.1234, 15: 0.1008, 16: 0.0717, 17: 0.0332, 18: 0.0027},
            10: {7: 0.0091, 8: 0.0511, 9: 0.0908, 10: 0.1179, 11: 0.1475, 12: 0.1489, 13: 0.1396, 14: 0.1170, 15: 0.1004, 16: 0.0614, 17: 0.0162},
            11: {8: 0.0444, 9: 0.0800, 10: 0.1257, 11: 0.1592, 12: 0.1559, 13: 0.1531, 14: 0.1303, 15: 0.0952, 16: 0.0560, 17: 0.0002},
            12: {8: 0.0251, 9: 0.0943, 10: 0.1341, 11: 0.1497, 12: 0.1642, 13: 0.1471, 14: 0.1303, 15: 0.1009, 16: 0.0542}
        },
        'Coimbra': {
            1: {8: 0.0004, 9: 0.0127, 10: 0.1251, 11: 0.1648, 12: 0.1644, 13: 0.1674, 14: 0.1471, 15: 0.1236, 16: 0.0815, 17: 0.0131},
            2: {8: 0.0046, 9: 0.0741, 10: 0.1129, 11: 0.1355, 12: 0.1571, 13: 0.1488, 14: 0.1350, 15: 0.1119, 16: 0.0844, 17: 0.0358},
            3: {7: 0.0023, 8: 0.0318, 9: 0.0775, 10: 0.1189, 11: 0.1415, 12: 0.1463, 13: 0.1388, 14: 0.1260, 15: 0.0991, 16: 0.0752, 17: 0.0388, 18: 0.0039},
            4: {6: 0.0006, 7: 0.0152, 8: 0.0503, 9: 0.0833, 10: 0.1082, 11: 0.1257, 12: 0.1312, 13: 0.1343, 14: 0.1198, 15: 0.1010, 16: 0.0779, 17: 0.0424, 18: 0.0101},
            5: {6: 0.0045, 7: 0.0214, 8: 0.0532, 9: 0.0866, 10: 0.1090, 11: 0.1223, 12: 0.1334, 13: 0.1249, 14: 0.1150, 15: 0.0977, 16: 0.0756, 17: 0.0423, 18: 0.0124, 19: 0.0016},
            6: {6: 0.0072, 7: 0.0239, 8: 0.0533, 9: 0.0860, 10: 0.0974, 11: 0.1158, 12: 0.1163, 13: 0.1148, 14: 0.1218, 15: 0.1055, 16: 0.0834, 17: 0.0514, 18: 0.0186, 19: 0.0047},
            7: {6: 0.0046, 7: 0.0192, 8: 0.0479, 9: 0.0758, 10: 0.0953, 11: 0.1206, 12: 0.1297, 13: 0.1282, 14: 0.1180, 15: 0.1084, 16: 0.0822, 17: 0.0494, 18: 0.0169, 19: 0.0037},
            8: {6: 0.0011, 7: 0.0143, 8: 0.0422, 9: 0.0738, 10: 0.1031, 11: 0.1244, 12: 0.1337, 13: 0.1345, 14: 0.1250, 15: 0.1056, 16: 0.0814, 17: 0.0466, 18: 0.0133, 19: 0.0009},
            9: {7: 0.0109, 8: 0.0458, 9: 0.0758, 10: 0.1028, 11: 0.1230, 12: 0.1296, 13: 0.1327, 14: 0.1320, 15: 0.1176, 16: 0.0849, 17: 0.0405, 18: 0.0044},
            10: {7: 0.0023, 8: 0.0313, 9: 0.0948, 10: 0.1216, 11: 0.1494, 12: 0.1478, 13: 0.1561, 14: 0.1219, 15: 0.0968, 16: 0.0613, 17: 0.0169},
            11: {8: 0.0064, 9: 0.0835, 10: 0.1411, 11: 0.1590, 12: 0.1524, 13: 0.1613, 14: 0.1353, 15: 0.0953, 16: 0.0653, 17: 0.0005},
            12: {8: 0.0012, 9: 0.0146, 10: 0.1374, 11: 0.1618, 12: 0.1748, 13: 0.1837, 14: 0.1569, 15: 0.1143, 16: 0.0554}
        },
        'Évora': {
            1: {8: 0.0147, 9: 0.0724, 10: 0.1177, 11: 0.1412, 12: 0.1572, 13: 0.1494, 14: 0.1375, 15: 0.1200, 16: 0.0739, 17: 0.0160},
            2: {8: 0.0238, 9: 0.0680, 10: 0.1163, 11: 0.1398, 12: 0.1324, 13: 0.1469, 14: 0.1406, 15: 0.1121, 16: 0.0846, 17: 0.0354},
            3: {7: 0.0044, 8: 0.0425, 9: 0.0793, 10: 0.1080, 11: 0.1314, 12: 0.1261, 13: 0.1390, 14: 0.1272, 15: 0.1137, 16: 0.0801, 17: 0.0431, 18: 0.0051},
            4: {6: 0.0007, 7: 0.0185, 8: 0.0563, 9: 0.0898, 10: 0.1165, 11: 0.1279, 12: 0.1263, 13: 0.1122, 14: 0.1218, 15: 0.0982, 16: 0.0798, 17: 0.0432, 18: 0.0088},
            5: {6: 0.0047, 7: 0.0241, 8: 0.0567, 9: 0.0877, 10: 0.1088, 11: 0.1242, 12: 0.1312, 13: 0.1238, 14: 0.1127, 15: 0.0992, 16: 0.0720, 17: 0.0424, 18: 0.0113, 19: 0.0012},
            6: {6: 0.0061, 7: 0.0218, 8: 0.0562, 9: 0.0857, 10: 0.1092, 11: 0.1240, 12: 0.1201, 13: 0.1255, 14: 0.1185, 15: 0.0977, 16: 0.0743, 17: 0.0440, 18: 0.0136, 19: 0.0034},
            7: {6: 0.0038, 7: 0.0172, 8: 0.0506, 9: 0.0818, 10: 0.1059, 11: 0.1205, 12: 0.1285, 13: 0.1254, 14: 0.1212, 15: 0.1030, 16: 0.0783, 17: 0.0468, 18: 0.0138, 19: 0.0030},
            8: {6: 0.0011, 7: 0.0156, 8: 0.0498, 9: 0.0819, 10: 0.1073, 11: 0.1241, 12: 0.1313, 13: 0.1300, 14: 0.1222, 15: 0.1027, 16: 0.0776, 17: 0.0448, 18: 0.0110, 19: 0.0006},
            9: {7: 0.0154, 8: 0.0552, 9: 0.0900, 10: 0.1129, 11: 0.1273, 12: 0.1343, 13: 0.1325, 14: 0.1216, 15: 0.1012, 16: 0.0735, 17: 0.0327, 18: 0.0033},
            10: {7: 0.0074, 8: 0.0538, 9: 0.0985, 10: 0.1195, 11: 0.1302, 12: 0.1450, 13: 0.1411, 14: 0.1258, 15: 0.1006, 16: 0.0606, 17: 0.0175},
            11: {8: 0.0420, 9: 0.0821, 10: 0.1313, 11: 0.1467, 12: 0.1376, 13: 0.1601, 14: 0.1351, 15: 0.1061, 16: 0.0577, 17: 0.0013},
            12: {8: 0.0209, 9: 0.0835, 10: 0.1270, 11: 0.1381, 12: 0.1619, 13: 0.1612, 14: 0.1252, 15: 0.1163, 16: 0.0659}
        },
        'Faro': {
            1: {8: 0.0207, 9: 0.0776, 10: 0.1219, 11: 0.1428, 12: 0.1560, 13: 0.1519, 14: 0.1361, 15: 0.1053, 16: 0.0728, 17: 0.0150},
            2: {8: 0.0237, 9: 0.0721, 10: 0.1108, 11: 0.1345, 12: 0.1480, 13: 0.1433, 14: 0.1364, 15: 0.1146, 16: 0.0808, 17: 0.0357},
            3: {7: 0.0050, 8: 0.0432, 9: 0.0828, 10: 0.1134, 11: 0.1272, 12: 0.1383, 13: 0.1409, 14: 0.1306, 15: 0.1032, 16: 0.0726, 17: 0.0382, 18: 0.0047},
            4: {6: 0.0004, 7: 0.0141, 8: 0.0513, 9: 0.0803, 10: 0.1104, 11: 0.1274, 12: 0.1294, 13: 0.1326, 14: 0.1206, 15: 0.1062, 16: 0.0801, 17: 0.0394, 18: 0.0078},
            5: {6: 0.0041, 7: 0.0205, 8: 0.0511, 9: 0.0825, 10: 0.1060, 11: 0.1173, 12: 0.1289, 13: 0.1325, 14: 0.1258, 15: 0.1054, 16: 0.0743, 17: 0.0398, 18: 0.0110, 19: 0.0008},
            6: {6: 0.0052, 7: 0.0196, 8: 0.0525, 9: 0.0839, 10: 0.1034, 11: 0.1199, 12: 0.1298, 13: 0.1305, 14: 0.1194, 15: 0.1016, 16: 0.0746, 17: 0.0434, 18: 0.0131, 19: 0.0030},
            7: {6: 0.0033, 7: 0.0157, 8: 0.0494, 9: 0.0812, 10: 0.1062, 11: 0.1215, 12: 0.1299, 13: 0.1291, 14: 0.1215, 15: 0.1032, 16: 0.0782, 17: 0.0455, 18: 0.0128, 19: 0.0026},
            8: {6: 0.0008, 7: 0.0144, 8: 0.0474, 9: 0.0824, 10: 0.1084, 11: 0.1212, 12: 0.1276, 13: 0.1321, 14: 0.1257, 15: 0.1059, 16: 0.0783, 17: 0.0445, 18: 0.0109, 19: 0.0005},
            9: {7: 0.0132, 8: 0.0460, 9: 0.0831, 10: 0.1129, 11: 0.1243, 12: 0.1396, 13: 0.1408, 14: 0.1242, 15: 0.1032, 16: 0.0740, 17: 0.0355, 18: 0.0031},
            10: {7: 0.0094, 8: 0.0493, 9: 0.0880, 10: 0.1199, 11: 0.1358, 12: 0.1454, 13: 0.1392, 14: 0.1245, 15: 0.1005, 16: 0.0662, 17: 0.0218},
            11: {8: 0.0369, 9: 0.0889, 10: 0.1330, 11: 0.1474, 12: 0.1516, 13: 0.1609, 14: 0.1276, 15: 0.0972, 16: 0.0549, 17: 0.0017},
            12: {8: 0.0222, 9: 0.0814, 10: 0.1214, 11: 0.1456, 12: 0.1593, 13: 0.1649, 14: 0.1405, 15: 0.1055, 16: 0.0591}
        },
        'Guarda': {
            1: {8: 0.0103, 9: 0.0601, 10: 0.1470, 11: 0.1210, 12: 0.1906, 13: 0.1275, 14: 0.1706, 15: 0.0815, 16: 0.0875, 17: 0.0038},
            2: {8: 0.0323, 9: 0.0790, 10: 0.1082, 11: 0.1297, 12: 0.1482, 13: 0.1462, 14: 0.1348, 15: 0.1112, 16: 0.0774, 17: 0.0331},
            3: {7: 0.0061, 8: 0.0464, 9: 0.0836, 10: 0.1109, 11: 0.1336, 12: 0.1417, 13: 0.1461, 14: 0.1235, 15: 0.0955, 16: 0.0742, 17: 0.0359, 18: 0.0024},
            4: {6: 0.0010, 7: 0.0179, 8: 0.0527, 9: 0.0868, 10: 0.1129, 11: 0.1313, 12: 0.1352, 13: 0.1229, 14: 0.1182, 15: 0.1015, 16: 0.0700, 17: 0.0415, 18: 0.0079},
            5: {6: 0.0050, 7: 0.0249, 8: 0.0600, 9: 0.0909, 10: 0.1138, 11: 0.1274, 12: 0.1297, 13: 0.1235, 14: 0.1162, 15: 0.0939, 16: 0.0637, 17: 0.0391, 18: 0.0107, 19: 0.0011},
            6: {6: 0.0040, 7: 0.0201, 8: 0.0513, 9: 0.0817, 10: 0.1054, 11: 0.1219, 12: 0.1310, 13: 0.1277, 14: 0.1155, 15: 0.0976, 16: 0.0759, 17: 0.0475, 18: 0.0148, 19: 0.0057},
            7: {6: 0.0045, 7: 0.0204, 8: 0.0553, 9: 0.0818, 10: 0.1037, 11: 0.1225, 12: 0.1306, 13: 0.1257, 14: 0.1155, 15: 0.1015, 16: 0.0775, 17: 0.0445, 18: 0.0136, 19: 0.0030},
            8: {6: 0.0017, 7: 0.0177, 8: 0.0521, 9: 0.0850, 10: 0.1092, 11: 0.1251, 12: 0.1319, 13: 0.1295, 14: 0.1184, 15: 0.1007, 16: 0.0756, 17: 0.0421, 18: 0.0105, 19: 0.0006},
            9: {7: 0.0164, 8: 0.0556, 9: 0.0903, 10: 0.1130, 11: 0.1288, 12: 0.1370, 13: 0.1365, 14: 0.1174, 15: 0.1011, 16: 0.0689, 17: 0.0322, 18: 0.0027},
            10: {7: 0.0090, 8: 0.0514, 9: 0.0889, 10: 0.1228, 11: 0.1437, 12: 0.1374, 13: 0.1419, 14: 0.1287, 15: 0.1044, 16: 0.0579, 17: 0.0139},
            11: {8: 0.0526, 9: 0.0891, 10: 0.1164, 11: 0.1507, 12: 0.1567, 13: 0.1455, 14: 0.1381, 15: 0.1017, 16: 0.0493},
            12: {8: 0.0134, 9: 0.0775, 10: 0.1242, 11: 0.1457, 12: 0.1612, 13: 0.1680, 14: 0.1347, 15: 0.1152, 16: 0.0601}
        },
        'Leiria': {
            1: {8: 0.0004, 9: 0.0765, 10: 0.1209, 11: 0.1549, 12: 0.1551, 13: 0.1474, 14: 0.1343, 15: 0.1218, 16: 0.0779, 17: 0.0109},
            2: {8: 0.0216, 9: 0.0691, 10: 0.1219, 11: 0.1396, 12: 0.1460, 13: 0.1492, 14: 0.1328, 15: 0.1007, 16: 0.0792, 17: 0.0399},
            3: {7: 0.0025, 8: 0.0371, 9: 0.0758, 10: 0.1100, 11: 0.1268, 12: 0.1400, 13: 0.1392, 14: 0.1322, 15: 0.1111, 16: 0.0815, 17: 0.0385, 18: 0.0053},
            4: {6: 0.0005, 7: 0.0156, 8: 0.0519, 9: 0.0828, 10: 0.1001, 11: 0.1209, 12: 0.1368, 13: 0.1339, 14: 0.1213, 15: 0.1064, 16: 0.0744, 17: 0.0443, 18: 0.0110},
            5: {6: 0.0043, 7: 0.0202, 8: 0.0527, 9: 0.0862, 10: 0.1069, 11: 0.1184, 12: 0.1262, 13: 0.1238, 14: 0.1203, 15: 0.1035, 16: 0.0780, 17: 0.0441, 18: 0.0137, 19: 0.0015},
            6: {6: 0.0059, 7: 0.0206, 8: 0.0438, 9: 0.0742, 10: 0.1007, 11: 0.1146, 12: 0.1320, 13: 0.1299, 14: 0.1210, 15: 0.1070, 16: 0.0827, 17: 0.0475, 18: 0.0159, 19: 0.0042},
            7: {6: 0.0041, 7: 0.0171, 8: 0.0447, 9: 0.0716, 10: 0.0980, 11: 0.1166, 12: 0.1269, 13: 0.1309, 14: 0.1308, 15: 0.1078, 16: 0.0822, 17: 0.0483, 18: 0.0172, 19: 0.0040},
            8: {6: 0.0041, 7: 0.0171, 8: 0.0447, 9: 0.0716, 10: 0.0980, 11: 0.1166, 12: 0.1269, 13: 0.1309, 14: 0.1308, 15: 0.1078, 16: 0.0822, 17: 0.0483, 18: 0.0172, 19: 0.0040},
            9: {7: 0.0113, 8: 0.0423, 9: 0.0766, 10: 0.1125, 11: 0.1311, 12: 0.1376, 13: 0.1373, 14: 0.1279, 15: 0.1050, 16: 0.0756, 17: 0.0382, 18: 0.0046},
            10: {7: 0.0061, 8: 0.0550, 9: 0.0954, 10: 0.1142, 11: 0.1342, 12: 0.1384, 13: 0.1353, 14: 0.1222, 15: 0.1077, 16: 0.0677, 17: 0.0238},
            11: {8: 0.0322, 9: 0.0826, 10: 0.1261, 11: 0.1643, 12: 0.1599, 13: 0.1450, 14: 0.1368, 15: 0.1031, 16: 0.0498, 17: 0.0003},
            12: {8: 0.0010, 9: 0.0821, 10: 0.1319, 11: 0.1623, 12: 0.1649, 13: 0.1548, 14: 0.1359, 15: 0.1101, 16: 0.0570}
        },
        'Lisboa': {
            1: {8: 0.0007, 9: 0.0250, 10: 0.1228, 11: 0.1654, 12: 0.1579, 13: 0.1770, 14: 0.1551, 15: 0.1155, 16: 0.0777, 17: 0.0028},
            2: {8: 0.0047, 9: 0.0780, 10: 0.1118, 11: 0.1364, 12: 0.1370, 13: 0.1451, 14: 0.1389, 15: 0.1274, 16: 0.0806, 17: 0.0401},
            3: {7: 0.0015, 8: 0.0336, 9: 0.0747, 10: 0.1036, 11: 0.1345, 12: 0.1428, 13: 0.1372, 14: 0.1339, 15: 0.1075, 16: 0.0814, 17: 0.0446, 18: 0.0046},
            4: {6: 0.0005, 7: 0.0157, 8: 0.0527, 9: 0.0795, 10: 0.1164, 11: 0.1150, 12: 0.1154, 13: 0.1265, 14: 0.1156, 15: 0.1119, 16: 0.0829, 17: 0.0536, 18: 0.0141},
            5: {6: 0.0041, 7: 0.0189, 8: 0.0512, 9: 0.0829, 10: 0.0973, 11: 0.1149, 12: 0.1203, 13: 0.1279, 14: 0.1241, 15: 0.1094, 16: 0.0819, 17: 0.0504, 18: 0.0147, 19: 0.0019},
            6: {6: 0.0052, 7: 0.0189, 8: 0.0481, 9: 0.0766, 10: 0.0972, 11: 0.1110, 12: 0.1227, 13: 0.1282, 14: 0.1303, 15: 0.1064, 16: 0.0834, 17: 0.0507, 18: 0.0169, 19: 0.0044},
            7: {6: 0.0036, 7: 0.0149, 8: 0.0427, 9: 0.0695, 10: 0.0975, 11: 0.1168, 12: 0.1298, 13: 0.1274, 14: 0.1270, 15: 0.1110, 16: 0.0856, 17: 0.0521, 18: 0.0181, 19: 0.0040},
            8: {6: 0.0006, 7: 0.0120, 8: 0.0459, 9: 0.0772, 10: 0.1008, 11: 0.1187, 12: 0.1278, 13: 0.1346, 14: 0.1235, 15: 0.1116, 16: 0.0835, 17: 0.0491, 18: 0.0137, 19: 0.0009},
            9: {7: 0.0050, 8: 0.0479, 9: 0.0834, 10: 0.1090, 11: 0.1247, 12: 0.1403, 13: 0.1426, 14: 0.1295, 15: 0.1030, 16: 0.0733, 17: 0.0371, 18: 0.0041},
            10: {7: 0.0016, 8: 0.0443, 9: 0.0861, 10: 0.1268, 11: 0.1436, 12: 0.1340, 13: 0.1381, 14: 0.1282, 15: 0.1071, 16: 0.0716, 17: 0.0187},
            11: {8: 0.0058, 9: 0.0974, 10: 0.1321, 11: 0.1637, 12: 0.1494, 13: 0.1528, 14: 0.1309, 15: 0.1065, 16: 0.0611, 17: 0.0004},
            12: {8: 0.0020, 9: 0.0439, 10: 0.1348, 11: 0.1612, 12: 0.1783, 13: 0.1597, 14: 0.1501, 15: 0.1099, 16: 0.0600}
        },
        'Portalegre': {
            1: {8: 0.0025, 9: 0.0772, 10: 0.1156, 11: 0.1452, 12: 0.1584, 13: 0.1549, 14: 0.1366, 15: 0.1211, 16: 0.0766, 17: 0.0119},
            2: {8: 0.0249, 9: 0.0777, 10: 0.1051, 11: 0.1420, 12: 0.1475, 13: 0.1521, 14: 0.1410, 15: 0.0980, 16: 0.0778, 17: 0.0339},
            3: {7: 0.0043, 8: 0.0419, 9: 0.0765, 10: 0.1044, 11: 0.1273, 12: 0.1467, 13: 0.1483, 14: 0.1305, 15: 0.1036, 16: 0.0742, 17: 0.0381, 18: 0.0042},
            4: {6: 0.0007, 7: 0.0182, 8: 0.0535, 9: 0.0857, 10: 0.1103, 11: 0.1352, 12: 0.1371, 13: 0.1296, 14: 0.1130, 15: 0.1011, 16: 0.0675, 17: 0.0398, 18: 0.0082},
            5: {6: 0.0050, 7: 0.0249, 8: 0.0630, 9: 0.0959, 10: 0.1067, 11: 0.1277, 12: 0.1347, 13: 0.1236, 14: 0.1130, 15: 0.0888, 16: 0.0647, 17: 0.0403, 18: 0.0107, 19: 0.0010},
            6: {6: 0.0065, 7: 0.0240, 8: 0.0569, 9: 0.0760, 10: 0.1039, 11: 0.1216, 12: 0.1280, 13: 0.1286, 14: 0.1182, 15: 0.0993, 16: 0.0756, 17: 0.0438, 18: 0.0141, 19: 0.0035},
            7: {6: 0.0042, 7: 0.0186, 8: 0.0527, 9: 0.0851, 10: 0.1056, 11: 0.1228, 12: 0.1288, 13: 0.1254, 14: 0.1176, 15: 0.1025, 16: 0.0778, 17: 0.0428, 18: 0.0131, 19: 0.0028},
            8: {6: 0.0015, 7: 0.0171, 8: 0.0510, 9: 0.0828, 10: 0.1101, 11: 0.1258, 12: 0.1302, 13: 0.1293, 14: 0.1206, 15: 0.1027, 16: 0.0753, 17: 0.0424, 18: 0.0106, 19: 0.0005},
            9: {7: 0.0174, 8: 0.0546, 9: 0.0892, 10: 0.1148, 11: 0.1285, 12: 0.1322, 13: 0.1284, 14: 0.1210, 15: 0.1015, 16: 0.0736, 17: 0.0355, 18: 0.0032},
            10: {7: 0.0071, 8: 0.0549, 9: 0.0927, 10: 0.1290, 11: 0.1298, 12: 0.1446, 13: 0.1416, 14: 0.1270, 15: 0.0959, 16: 0.0610, 17: 0.0163},
            11: {8: 0.0408, 9: 0.0875, 10: 0.1196, 11: 0.1463, 12: 0.1637, 13: 0.1445, 14: 0.1287, 15: 0.1048, 16: 0.0638, 17: 0.0002},
            12: {8: 0.0144, 9: 0.0886, 10: 0.1252, 11: 0.1510, 12: 0.1634, 13: 0.1557, 14: 0.1338, 15: 0.1077, 16: 0.0601,},
        },
        'Porto': {
            1: {8: 0.0009, 9: 0.0682, 10: 0.1137, 11: 0.1449, 12: 0.1638, 13: 0.1640, 14: 0.1359, 15: 0.1223, 16: 0.0807, 17: 0.0057},
            2: {8: 0.0180, 9: 0.0712, 10: 0.1063, 11: 0.1400, 12: 0.1601, 13: 0.1466, 14: 0.1327, 15: 0.1112, 16: 0.0792, 17: 0.0348},
            3: {7: 0.0042, 8: 0.0358, 9: 0.0687, 10: 0.1136, 11: 0.1335, 12: 0.1445, 13: 0.1404, 14: 0.1336, 15: 0.1071, 16: 0.0783, 17: 0.0360, 18: 0.0042},
            4: {6: 0.0006, 7: 0.0146, 8: 0.0491, 9: 0.0820, 10: 0.1038, 11: 0.1279, 12: 0.1422, 13: 0.1336, 14: 0.1149, 15: 0.1014, 16: 0.0768, 17: 0.0425, 18: 0.0104},
            5: {6: 0.0045, 7: 0.0219, 8: 0.0496, 9: 0.0788, 10: 0.1010, 11: 0.1205, 12: 0.1280, 13: 0.1339, 14: 0.1207, 15: 0.1055, 16: 0.0759, 17: 0.0443, 18: 0.0135, 19: 0.0019},
            6: {6: 0.0062, 7: 0.0215, 8: 0.0478, 9: 0.0712, 10: 0.0921, 11: 0.1140, 12: 0.1346, 13: 0.1322, 14: 0.1251, 15: 0.1074, 16: 0.0792, 17: 0.0473, 18: 0.0168, 19: 0.0046},
            7: {6: 0.0042, 7: 0.0173, 8: 0.0482, 9: 0.0773, 10: 0.0982, 11: 0.1196, 12: 0.1250, 13: 0.1265, 14: 0.1246, 15: 0.1065, 16: 0.0831, 17: 0.0488, 18: 0.0169, 19: 0.0038},
            8: {6: 0.0011, 7: 0.0132, 8: 0.0442, 9: 0.0761, 10: 0.1024, 11: 0.1211, 12: 0.1258, 13: 0.1330, 14: 0.1283, 15: 0.1104, 16: 0.0830, 17: 0.0469, 18: 0.0135, 19: 0.0009},
            9: {7: 0.0057, 8: 0.0356, 9: 0.0716, 10: 0.1004, 11: 0.1251, 12: 0.1346, 13: 0.1442, 14: 0.1275, 15: 0.1124, 16: 0.0877, 17: 0.0483, 18: 0.0070},
            10: {7: 0.0051, 8: 0.0483, 9: 0.0870, 10: 0.1230, 11: 0.1398, 12: 0.1478, 13: 0.1447, 14: 0.1280, 15: 0.0962, 16: 0.0638, 17: 0.0163},
            11: {8: 0.0373, 9: 0.0896, 10: 0.1259, 11: 0.1551, 12: 0.1394, 13: 0.1542, 14: 0.1362, 15: 0.1052, 16: 0.0571, 17: 0.0001},
            12: {8: 0.0039, 9: 0.0903, 10: 0.1354, 11: 0.1593, 12: 0.1702, 13: 0.1595, 14: 0.1314, 15: 0.1049, 16: 0.0451}
        },
        'Santarém': {
            1: {8: 0.0055, 9: 0.0714, 10: 0.1297, 11: 0.1522, 12: 0.1579, 13: 0.1550, 14: 0.1329, 15: 0.1166, 16: 0.0731, 17: 0.0057},
            2: {8: 0.0259, 9: 0.0687, 10: 0.1074, 11: 0.1249, 12: 0.1448, 13: 0.1529, 14: 0.1376, 15: 0.1216, 16: 0.0813, 17: 0.0348},
            3: {7: 0.0038, 8: 0.0367, 9: 0.0732, 10: 0.1085, 11: 0.1254, 12: 0.1372, 13: 0.1495, 14: 0.1386, 15: 0.1077, 16: 0.0751, 17: 0.0387, 18: 0.0057},
            4: {6: 0.0006, 7: 0.0148, 8: 0.0504, 9: 0.0865, 10: 0.1133, 11: 0.1289, 12: 0.1235, 13: 0.1343, 14: 0.1268, 15: 0.0975, 16: 0.0747, 17: 0.0386, 18: 0.0100},
            5: {6: 0.0038, 7: 0.0207, 8: 0.0546, 9: 0.0815, 10: 0.1045, 11: 0.1157, 12: 0.1264, 13: 0.1232, 14: 0.1274, 15: 0.1077, 16: 0.0762, 17: 0.0437, 18: 0.0130, 19: 0.0015},
            6: {6: 0.0059, 7: 0.0210, 8: 0.0546, 9: 0.0726, 10: 0.1026, 11: 0.1205, 12: 0.1285, 13: 0.1253, 14: 0.1220, 15: 0.1044, 16: 0.0770, 17: 0.0456, 18: 0.0159, 19: 0.0042},
            7: {6: 0.0035, 7: 0.0160, 8: 0.0466, 9: 0.0751, 10: 0.0995, 11: 0.1187, 12: 0.1288, 13: 0.1317, 14: 0.1236, 15: 0.1067, 16: 0.0817, 17: 0.0487, 18: 0.0157, 19: 0.0037},
            8: {6: 0.0010, 7: 0.0149, 8: 0.0489, 9: 0.0819, 10: 0.1064, 11: 0.1235, 12: 0.1334, 13: 0.1285, 14: 0.1207, 15: 0.1048, 16: 0.0772, 17: 0.0459, 18: 0.0121, 19: 0.0009},
            9: {7: 0.0140, 8: 0.0531, 9: 0.0910, 10: 0.1154, 11: 0.1297, 12: 0.1379, 13: 0.1373, 14: 0.1154, 15: 0.1001, 16: 0.0667, 17: 0.0354, 18: 0.0040},
            10: {7: 0.0061, 8: 0.0510, 9: 0.0789, 10: 0.1188, 11: 0.1453, 12: 0.1402, 13: 0.1452, 14: 0.1234, 15: 0.1049, 16: 0.0662, 17: 0.0200},
            11: {8: 0.0374, 9: 0.0855, 10: 0.1249, 11: 0.1616, 12: 0.1509, 13: 0.1483, 14: 0.1215, 15: 0.1030, 16: 0.0650, 17: 0.0018},
            12: {8: 0.0105, 9: 0.0716, 10: 0.1196, 11: 0.1540, 12: 0.1762, 13: 0.1647, 14: 0.1381, 15: 0.1079, 16: 0.0574}
        },
        'Setúbal': {
            1: {8: 0.0041, 9: 0.0683, 10: 0.1091, 11: 0.1481, 12: 0.1650, 13: 0.1496, 14: 0.1420, 15: 0.1153, 16: 0.0799, 17: 0.0187},
            2: {8: 0.0250, 9: 0.0745, 10: 0.1175, 11: 0.1312, 12: 0.1445, 13: 0.1454, 14: 0.1265, 15: 0.1143, 16: 0.0805, 17: 0.0407},
            3: {7: 0.0032, 8: 0.0356, 9: 0.0763, 10: 0.0997, 11: 0.1325, 12: 0.1430, 13: 0.1379, 14: 0.1333, 15: 0.1128, 16: 0.0791, 17: 0.0409, 18: 0.0056},
            4: {6: 0.0005, 7: 0.0146, 8: 0.0502, 9: 0.0876, 10: 0.1032, 11: 0.1189, 12: 0.1402, 13: 0.1297, 14: 0.1212, 15: 0.1071, 16: 0.0739, 17: 0.0438, 18: 0.0091},
            5: {6: 0.0035, 7: 0.0195, 8: 0.0507, 9: 0.0774, 10: 0.0999, 11: 0.1215, 12: 0.1283, 13: 0.1306, 14: 0.1222, 15: 0.1079, 16: 0.0794, 17: 0.0455, 18: 0.0121, 19: 0.0015},
            6: {6: 0.0052, 7: 0.0192, 8: 0.0501, 9: 0.0803, 10: 0.1018, 11: 0.1151, 12: 0.1287, 13: 0.1245, 14: 0.1191, 15: 0.1064, 16: 0.0801, 17: 0.0496, 18: 0.0157, 19: 0.0044},
            7: {6: 0.0033, 7: 0.0156, 8: 0.0486, 9: 0.0765, 10: 0.1026, 11: 0.1227, 12: 0.1270, 13: 0.1295, 14: 0.1183, 15: 0.1069, 16: 0.0818, 17: 0.0482, 18: 0.0156, 19: 0.0033},
            8: {6: 0.0006, 7: 0.0129, 8: 0.0466, 9: 0.0774, 10: 0.1007, 11: 0.1218, 12: 0.1311, 13: 0.1340, 14: 0.1255, 15: 0.1080, 16: 0.0812, 17: 0.0469, 18: 0.0125, 19: 0.0008},
            9: {7: 0.0127, 8: 0.0497, 9: 0.0827, 10: 0.1093, 11: 0.1220, 12: 0.1308, 13: 0.1362, 14: 0.1276, 15: 0.1090, 16: 0.0783, 17: 0.0374, 18: 0.0044},
            10: {7: 0.0059, 8: 0.0498, 9: 0.0875, 10: 0.1141, 11: 0.1264, 12: 0.1440, 13: 0.1472, 14: 0.1282, 15: 0.1037, 16: 0.0707, 17: 0.0225},
            11: {8: 0.0350, 9: 0.0822, 10: 0.1132, 11: 0.1480, 12: 0.1487, 13: 0.1583, 14: 0.1444, 15: 0.1094, 16: 0.0597, 17: 0.0013},
            12: {8: 0.0092, 9: 0.0784, 10: 0.1156, 11: 0.1516, 12: 0.1710, 13: 0.1702, 14: 0.1390, 15: 0.1069, 16: 0.0581}
        },
        'Viana do Castelo': {
            1: {8: 0.0001, 9: 0.0665, 10: 0.1112, 11: 0.1372, 12: 0.1627, 13: 0.1590, 14: 0.1558, 15: 0.1243, 16: 0.0760, 17: 0.0074},
            2: {8: 0.0240, 9: 0.0703, 10: 0.1041, 11: 0.1356, 12: 0.1503, 13: 0.1577, 14: 0.1404, 15: 0.1103, 16: 0.0720, 17: 0.0352},
            3: {7: 0.0036, 8: 0.0398, 9: 0.0795, 10: 0.1009, 11: 0.1273, 12: 0.1381, 13: 0.1340, 14: 0.1338, 15: 0.1120, 16: 0.0819, 17: 0.0435, 18: 0.0056},
            4: {6: 0.0006, 7: 0.0159, 8: 0.0522, 9: 0.0891, 10: 0.1041, 11: 0.1321, 12: 0.1261, 13: 0.1237, 14: 0.1177, 15: 0.1078, 16: 0.0763, 17: 0.0434, 18: 0.0110},
            5: {6: 0.0021, 7: 0.0165, 8: 0.0462, 9: 0.0779, 10: 0.0885, 11: 0.1126, 12: 0.1332, 13: 0.1258, 14: 0.1249, 15: 0.1133, 16: 0.0858, 17: 0.0513, 18: 0.0172, 19: 0.0047},
            6: {6: 0.0059, 7: 0.0199, 8: 0.0468, 9: 0.0730, 10: 0.0967, 11: 0.1140, 12: 0.1248, 13: 0.1348, 14: 0.1263, 15: 0.1072, 16: 0.0830, 17: 0.0471, 18: 0.0160, 19: 0.0045},
            7: {6: 0.0041, 7: 0.0166, 8: 0.0458, 9: 0.0728, 10: 0.0953, 11: 0.1139, 12: 0.1265, 13: 0.1310, 14: 0.1248, 15: 0.1106, 16: 0.0842, 17: 0.0520, 18: 0.0182, 19: 0.0041},
            8: {6: 0.0011, 7: 0.0134, 8: 0.0472, 9: 0.0780, 10: 0.1040, 11: 0.1227, 12: 0.1309, 13: 0.1355, 14: 0.1229, 15: 0.1040, 16: 0.0796, 17: 0.0460, 18: 0.0139, 19: 0.0010},
            9: {7: 0.0130, 8: 0.0481, 9: 0.0764, 10: 0.1104, 11: 0.1282, 12: 0.1329, 13: 0.1371, 14: 0.1250, 15: 0.1073, 16: 0.0771, 17: 0.0397, 18: 0.0047},
            10: {7: 0.0043, 8: 0.0473, 9: 0.0873, 10: 0.1214, 11: 0.1315, 12: 0.1484, 13: 0.1484, 14: 0.1241, 15: 0.1043, 16: 0.0641, 17: 0.0189},
            11: {8: 0.0372, 9: 0.0895, 10: 0.1250, 11: 0.1512, 12: 0.1409, 13: 0.1537, 14: 0.1381, 15: 0.1055, 16: 0.0587, 17: 0.0001},
            12: {8: 0.0050, 9: 0.0809, 10: 0.1302, 11: 0.1522, 12: 0.1745, 13: 0.1601, 14: 0.1449, 15: 0.0984, 16: 0.0537}
        },
        'Vila Real': {
            1: {8: 0.0005, 9: 0.0758, 10: 0.1131, 11: 0.1384, 12: 0.1553, 13: 0.1554, 14: 0.1463, 15: 0.1353, 16: 0.0788, 17: 0.0013},
            2: {8: 0.0143, 9: 0.0770, 10: 0.1152, 11: 0.1435, 12: 0.1502, 13: 0.1385, 14: 0.1382, 15: 0.1112, 16: 0.0794, 17: 0.0325},
            3: {7: 0.0041, 8: 0.0440, 9: 0.0837, 10: 0.1054, 11: 0.1305, 12: 0.1383, 13: 0.1342, 14: 0.1279, 15: 0.1088, 16: 0.0786, 17: 0.0407, 18: 0.0037},
            4: {6: 0.0010, 7: 0.0201, 8: 0.0548, 9: 0.0893, 10: 0.1193, 11: 0.1362, 12: 0.1352, 13: 0.1305, 14: 0.1081, 15: 0.0888, 16: 0.0688, 17: 0.0395, 18: 0.0083},
            5: {6: 0.0026, 7: 0.0188, 8: 0.0523, 9: 0.0870, 10: 0.1021, 11: 0.1291, 12: 0.1208, 13: 0.1194, 14: 0.1139, 15: 0.1078, 16: 0.0781, 17: 0.0480, 18: 0.0163, 19: 0.0039},
            6: {6: 0.0064, 7: 0.0242, 8: 0.0552, 9: 0.0816, 10: 0.1018, 11: 0.1194, 12: 0.1294, 13: 0.1253, 14: 0.1135, 15: 0.1036, 16: 0.0748, 17: 0.0463, 18: 0.0148, 19: 0.0037},
            7: {6: 0.0047, 7: 0.0195, 8: 0.0535, 9: 0.0841, 10: 0.1080, 11: 0.1190, 12: 0.1258, 13: 0.1243, 14: 0.1160, 15: 0.1022, 16: 0.0773, 17: 0.0461, 18: 0.0156, 19: 0.0037},
            8: {6: 0.0015, 7: 0.0160, 8: 0.0526, 9: 0.0856, 10: 0.1105, 11: 0.1254, 12: 0.1322, 13: 0.1301, 14: 0.1173, 15: 0.0999, 16: 0.0735, 17: 0.0430, 18: 0.0116, 19: 0.0008},
            9: {7: 0.0180, 8: 0.0556, 9: 0.0850, 10: 0.1181, 11: 0.1360, 12: 0.1359, 13: 0.1315, 14: 0.1154, 15: 0.0973, 16: 0.0679, 17: 0.0361, 18: 0.0033},
            10: {7: 0.0045, 8: 0.0556, 9: 0.0927, 10: 0.1309, 11: 0.1341, 12: 0.1454, 13: 0.1435, 14: 0.1217, 15: 0.0944, 16: 0.0618, 17: 0.0153},
            11: {8: 0.0361, 9: 0.0997, 10: 0.1373, 11: 0.1598, 12: 0.1482, 13: 0.1375, 14: 0.1299, 15: 0.0963, 16: 0.0552},
            12: {8: 0.0011, 9: 0.0625, 10: 0.1196, 11: 0.1647, 12: 0.1799, 13: 0.1538, 14: 0.1373, 15: 0.1142, 16: 0.0670}
        },
        'Viseu': {
            1: {8: 0.0079, 9: 0.0686, 10: 0.1108, 11: 0.1390, 12: 0.1537, 13: 0.1591, 14: 0.1518, 15: 0.1245, 16: 0.0736, 17: 0.0110},
            2: {8: 0.0240, 9: 0.0732, 10: 0.1117, 11: 0.1362, 12: 0.1585, 13: 0.1529, 14: 0.1346, 15: 0.1094, 16: 0.0717, 17: 0.0278},
            3: {7: 0.0049, 8: 0.0420, 9: 0.0827, 10: 0.1220, 11: 0.1379, 12: 0.1420, 13: 0.1294, 14: 0.1168, 15: 0.0987, 16: 0.0766, 17: 0.0422, 18: 0.0048},
            4: {6: 0.0008, 7: 0.0181, 8: 0.0550, 9: 0.0837, 10: 0.1073, 11: 0.1255, 12: 0.1338, 13: 0.1325, 14: 0.1163, 15: 0.1033, 16: 0.0735, 17: 0.0407, 18: 0.0093},
            5: {6: 0.0023, 7: 0.0178, 8: 0.0521, 9: 0.0808, 10: 0.1033, 11: 0.1132, 12: 0.1299, 13: 0.1237, 14: 0.1255, 15: 0.1077, 16: 0.0700, 17: 0.0527, 18: 0.0166, 19: 0.0043},
            6: {6: 0.0065, 7: 0.0223, 8: 0.0544, 9: 0.0763, 10: 0.0989, 11: 0.1159, 12: 0.1266, 13: 0.1284, 14: 0.1237, 15: 0.0987, 16: 0.0775, 17: 0.0500, 18: 0.0164, 19: 0.0044},
            7: {6: 0.0048, 7: 0.0197, 8: 0.0484, 9: 0.0781, 10: 0.0943, 11: 0.1138, 12: 0.1285, 13: 0.1294, 14: 0.1235, 15: 0.1075, 16: 0.0825, 17: 0.0486, 18: 0.0170, 19: 0.0039},
            8: {6: 0.0015, 7: 0.0162, 8: 0.0496, 9: 0.0797, 10: 0.1019, 11: 0.1214, 12: 0.1301, 13: 0.1316, 14: 0.1237, 15: 0.1045, 16: 0.0806, 17: 0.0462, 18: 0.0122, 19: 0.0008},
            9: {7: 0.0171, 8: 0.0605, 9: 0.0920, 10: 0.1134, 11: 0.1377, 12: 0.1335, 13: 0.1266, 14: 0.1229, 15: 0.0951, 16: 0.0669, 17: 0.0306, 18: 0.0037},
            10: {7: 0.0071, 8: 0.0555, 9: 0.0852, 10: 0.1258, 11: 0.1419, 12: 0.1415, 13: 0.1420, 14: 0.1189, 15: 0.1003, 16: 0.0635, 17: 0.0181},
            11: {8: 0.0420, 9: 0.0836, 10: 0.1054, 11: 0.1395, 12: 0.1719, 13: 0.1463, 14: 0.1320, 15: 0.1190, 16: 0.0603, 17: 0.0001},
            12: {8: 0.0106, 9: 0.0802, 10: 0.1246, 11: 0.1535, 12: 0.1697, 13: 0.1574, 14: 0.1442, 15: 0.1029, 16: 0.0571}
        },
        'Açores (Ponta Delgada)': {
            1: {9: 0.0002, 10: 0.0516, 11: 0.1002, 12: 0.1548, 13: 0.1644, 14: 0.1524, 15: 0.1606, 16: 0.1277, 17: 0.0672, 18: 0.0209},
            2: {9: 0.0030, 10: 0.0418, 11: 0.0744, 12: 0.1061, 13: 0.1456, 14: 0.1709, 15: 0.1571, 16: 0.1400, 17: 0.0955, 18: 0.0595, 19: 0.0062},
            3: {9: 0.0194, 10: 0.0542, 11: 0.0949, 12: 0.1348, 13: 0.1536, 14: 0.1261, 15: 0.1353, 16: 0.1231, 17: 0.0882, 18: 0.0554, 19: 0.0151},
            4: {7: 0.0001, 8: 0.0119, 9: 0.0402, 10: 0.0765, 11: 0.1134, 12: 0.1139, 13: 0.1363, 14: 0.1416, 15: 0.1142, 16: 0.1037, 17: 0.0848, 18: 0.0501, 19: 0.0134},
            5: {7: 0.0031, 8: 0.0189, 9: 0.0476, 10: 0.0807, 11: 0.1050, 12: 0.1298, 13: 0.1299, 14: 0.1244, 15: 0.1210, 16: 0.1063, 17: 0.0735, 18: 0.0424, 19: 0.0155, 20: 0.0019},
            6: {7: 0.0048, 8: 0.0194, 9: 0.0462, 10: 0.0720, 11: 0.1037, 12: 0.1172, 13: 0.1280, 14: 0.1341, 15: 0.1327, 16: 0.0988, 17: 0.0755, 18: 0.0464, 19: 0.0177, 20: 0.0034},
            7: {7: 0.0029, 8: 0.0149, 9: 0.0376, 10: 0.0682, 11: 0.0969, 12: 0.1147, 13: 0.1325, 14: 0.1352, 15: 0.1271, 16: 0.1151, 17: 0.0856, 18: 0.0484, 19: 0.0177, 20: 0.0032},
            8: {7: 0.0002, 8: 0.0123, 9: 0.0384, 10: 0.0713, 11: 0.1048, 12: 0.1180, 13: 0.1202, 14: 0.1214, 15: 0.1357, 16: 0.1230, 17: 0.0906, 18: 0.0473, 19: 0.0157, 20: 0.0012},
            9: {8: 0.0102, 9: 0.0471, 10: 0.0877, 11: 0.1086, 12: 0.1162, 13: 0.1381, 14: 0.1156, 15: 0.1357, 16: 0.1123, 17: 0.0810, 18: 0.0423, 19: 0.0052},
            10: {8: 0.0026, 9: 0.0355, 10: 0.0855, 11: 0.1132, 12: 0.1405, 13: 0.1541, 14: 0.1539, 15: 0.1317, 16: 0.1006, 17: 0.0612, 18: 0.0211},
            11: {9: 0.0097, 10: 0.0545, 11: 0.0920, 12: 0.1420, 13: 0.1400, 14: 0.1536, 15: 0.1603, 16: 0.1399, 17: 0.0798, 18: 0.0282},
            12: {9: 0.0042, 10: 0.0631, 11: 0.1145, 12: 0.1440, 13: 0.1786, 14: 0.1659, 15: 0.1390, 16: 0.1171, 17: 0.0712, 18: 0.0022}
        },
        'Madeira (Funchal)': {
            1: {9: 0.0534, 10: 0.1116, 11: 0.1373, 12: 0.1382, 13: 0.1508, 14: 0.1406, 15: 0.1095, 16: 0.1006, 17: 0.0524, 18: 0.0056},
            2: {8: 0.0021, 9: 0.0551, 10: 0.1115, 11: 0.1372, 12: 0.1493, 13: 0.1204, 14: 0.1252, 15: 0.1455, 16: 0.0802, 17: 0.0562, 18: 0.0172},
            3: {8: 0.0214, 9: 0.0547, 10: 0.1007, 11: 0.1209, 12: 0.1185, 13: 0.1315, 14: 0.1294, 15: 0.1168, 16: 0.1036, 17: 0.0730, 18: 0.0294},
            4: {7: 0.0031, 8: 0.0311, 9: 0.0744, 10: 0.0920, 11: 0.1028, 12: 0.1266, 13: 0.1261, 14: 0.1376, 15: 0.1200, 16: 0.0911, 17: 0.0678, 18: 0.0251, 19: 0.0023},
            5: {7: 0.0079, 8: 0.0413, 9: 0.0715, 10: 0.0735, 11: 0.1035, 12: 0.1323, 13: 0.1377, 14: 0.1170, 15: 0.1167, 16: 0.1010, 17: 0.0598, 18: 0.0314, 19: 0.0065},
            6: {7: 0.0104, 8: 0.0466, 9: 0.0906, 10: 0.0985, 11: 0.0977, 12: 0.1211, 13: 0.1193, 14: 0.1199, 15: 0.0986, 16: 0.0921, 17: 0.0603, 18: 0.0350, 19: 0.0099},
            7: {7: 0.0063, 8: 0.0292, 9: 0.0702, 10: 0.1004, 11: 0.1222, 12: 0.1234, 13: 0.1296, 14: 0.1159, 15: 0.1068, 16: 0.0958, 17: 0.0622, 18: 0.0299, 19: 0.0079},
            8: {7: 0.0007, 8: 0.0210, 9: 0.0561, 10: 0.0910, 11: 0.1162, 12: 0.1327, 13: 0.1379, 14: 0.1241, 15: 0.1147, 16: 0.0947, 17: 0.0672, 18: 0.0364, 19: 0.0074},
            9: {7: 0.0011, 8: 0.0391, 9: 0.0897, 10: 0.1060, 11: 0.1154, 12: 0.1354, 13: 0.1297, 14: 0.1251, 15: 0.1091, 16: 0.0709, 17: 0.0573, 18: 0.0208, 19: 0.0002},
            10: {8: 0.0338, 9: 0.0766, 10: 0.1169, 11: 0.1164, 12: 0.1550, 13: 0.1310, 14: 0.1212, 15: 0.1112, 16: 0.0783, 17: 0.0532, 18: 0.0064},
            11: {8: 0.0237, 9: 0.0674, 10: 0.1254, 11: 0.1369, 12: 0.1430, 13: 0.1517, 14: 0.1381, 15: 0.1060, 16: 0.0693, 17: 0.0384},
            12: {8: 0.0001, 9: 0.0673, 10: 0.1285, 11: 0.1408, 12: 0.1557, 13: 0.1443, 14: 0.1241, 15: 0.1106, 16: 0.0789, 17: 0.0497}
        },
    }

    # --- GERAR OS PERFIS QUARTO-HORÁRIOS ---
    PERFIS_QUARTO_HORARIOS = interpolar_perfis_para_quarto_horario(PERFIS_HORARIOS_MENSAIS_POR_DISTRITO)

    # Fatores de ajuste
    fator_inclinacao = 1.0 - (abs(inclinacao - 35) / 100) * 0.5
    fator_orientacao = 1.0
    if "Sudeste / Sudoeste" in orientacao_str: fator_orientacao = 0.95
    elif "Este / Oeste" in orientacao_str: fator_orientacao = 0.80
    FATOR_PERDAS_SISTEMA = 0.14

    df_resultado = df_consumos.copy()

    # Seleciona os dados de produção diária para o distrito, com fallback para 'Santarém'
    if distrito not in DADOS_PVGIS_DISTRITO:
        print(f"Atenção: distrito '{distrito}' não encontrado. Assumido 'Santarém'")
        producao_diaria_base_por_mes = DADOS_PVGIS_DISTRITO['Santarém']
    else:
        producao_diaria_base_por_mes = DADOS_PVGIS_DISTRITO[distrito]

    def calcular_producao_por_linha(row):
        # Define o tempo de referência como o início do intervalo (15 min antes do carimbo de data/hora)
        timestamp_inicio_intervalo = row['DataHora'] - pd.Timedelta(minutes=15)
        
        # Usa o mês, a hora e minuto do início do intervalo para os cálculos
        mes = timestamp_inicio_intervalo.month
        hora = timestamp_inicio_intervalo.hour
        minuto = timestamp_inicio_intervalo.minute

        # Calcula a energia diária total para o sistema
        energia_diaria_total_sistema = (
            producao_diaria_base_por_mes.get(mes, 0) * potencia_kwp *
            fator_inclinacao * fator_orientacao * (1 - FATOR_PERDAS_SISTEMA)
        )

        perfis_do_distrito = PERFIS_QUARTO_HORARIOS.get(distrito, PERFIS_QUARTO_HORARIOS.get('Santarém', {}))
        perfil_mensal = perfis_do_distrito.get(mes, {})
        
        # A chave de procura é agora uma combinação de (hora, minuto)
        chave_quarto_horaria = (hora, minuto)
        fator_distribuicao = perfil_mensal.get(chave_quarto_horaria, 0)
        
        # O fator já está ajustado para 15 minutos, por isso não dividimos por 4
        producao_kwh_intervalo = energia_diaria_total_sistema * fator_distribuicao
        
        return producao_kwh_intervalo

    # Aplica a função a cada linha do DataFrame para calcular a produção
    df_resultado['Producao_Solar_kWh'] = df_resultado.apply(calcular_producao_por_linha, axis=1)
    
    # Calcula as restantes colunas como antes
    df_resultado['Autoconsumo_kWh'] = np.minimum(df_resultado['Consumo (kWh)'], df_resultado['Producao_Solar_kWh'])
    df_resultado['Excedente_kWh'] = np.maximum(0, df_resultado['Producao_Solar_kWh'] - df_resultado['Consumo (kWh)'])
    df_resultado['Consumo_Rede_kWh'] = np.maximum(0, df_resultado['Consumo (kWh)'] - df_resultado['Producao_Solar_kWh'])

    return df_resultado

def calcular_detalhes_custo_meu_tarifario(
    st_session_state,
    opcao_horaria,
    consumos_para_calculo,
    potencia,
    dias,
    tarifa_social,
    familia_numerosa,
    valor_dgeg_user,
    valor_cav_user,
    CONSTANTES,
    FINANCIAMENTO_TSE_VAL
):
    """
    Calcula o custo completo para a funcionalidade "O Meu Tarifário",
    usando os inputs guardados no st.session_state.
    """
    try:
        # --- PASSO 1: EXTRAIR INPUTS DO st.session_state ---
        # Preços de Energia e Potência
        energia_meu_s = st_session_state.get("energia_meu_s_input_val", 0.0)
        potencia_meu = st_session_state.get("potencia_meu_input_val", 0.0)
        energia_meu_v = st_session_state.get("energia_meu_v_input_val", 0.0)
        energia_meu_f = st_session_state.get("energia_meu_f_input_val", 0.0)
        energia_meu_c = st_session_state.get("energia_meu_c_input_val", 0.0)
        energia_meu_p = st_session_state.get("energia_meu_p_input_val", 0.0)
        # Checkboxes TAR/TSE
        tar_incluida_energia_meu = st_session_state.get("meu_tar_energia_val", True)
        tar_incluida_potencia_meu = st_session_state.get("meu_tar_potencia_val", True)
        checkbox_tse_incluido_estado = st_session_state.get("meu_fin_tse_incluido_val", True)
        adicionar_financiamento_tse_meu = not checkbox_tse_incluido_estado
        # Descontos e Acréscimos
        desconto_energia = st_session_state.get("meu_desconto_energia_val", 0.0)
        desconto_potencia = st_session_state.get("meu_desconto_potencia_val", 0.0)
        desconto_fatura_input_meu = st_session_state.get("meu_desconto_fatura_val", 0.0)
        acrescimo_fatura_input_meu = st_session_state.get("meu_acrescimo_fatura_val", 0.0)

        # --- PASSO 2: PREPARAR DICIONÁRIOS DE PREÇOS E CONSUMOS ---
        is_billing_month = 28 <= dias <= 31
        preco_energia_input_meu = {}
        
        oh_lower = opcao_horaria.lower()
        if oh_lower == "simples":
            preco_energia_input_meu['S'] = float(energia_meu_s or 0.0)
            preco_potencia_input_meu = float(potencia_meu or 0.0)
        elif oh_lower.startswith("bi"):
            preco_energia_input_meu['V'] = float(energia_meu_v or 0.0)
            preco_energia_input_meu['F'] = float(energia_meu_f or 0.0)
            preco_potencia_input_meu = float(potencia_meu or 0.0)
        elif oh_lower.startswith("tri"):
            preco_energia_input_meu['V'] = float(energia_meu_v or 0.0)
            preco_energia_input_meu['C'] = float(energia_meu_c or 0.0)
            preco_energia_input_meu['P'] = float(energia_meu_p or 0.0)
            preco_potencia_input_meu = float(potencia_meu or 0.0)
        
        # --- PASSO 3: CÁLCULO DETALHADO (Lógica que já tinha) ---
        # (Esta parte é uma adaptação direta do seu código original)
        
        tar_energia_regulada_periodo_meu = {p: obter_tar_energia_periodo(opcao_horaria, p, potencia, CONSTANTES) for p in preco_energia_input_meu.keys()}
        tar_potencia_regulada_meu_base = obter_tar_dia(potencia, CONSTANTES)

        energia_meu_periodo_comercializador_base = {}
        for p_key, preco_input_val in preco_energia_input_meu.items():
            preco_input_val_float = float(preco_input_val or 0.0)
            energia_meu_periodo_comercializador_base[p_key] = preco_input_val_float - tar_energia_regulada_periodo_meu.get(p_key, 0.0) if tar_incluida_energia_meu else preco_input_val_float

        potencia_meu_comercializador_base = (float(preco_potencia_input_meu or 0.0) - tar_potencia_regulada_meu_base) if tar_incluida_potencia_meu else float(preco_potencia_input_meu or 0.0)
        
        financiamento_tse_a_somar_base = FINANCIAMENTO_TSE_VAL if adicionar_financiamento_tse_meu else 0.0

        desconto_monetario_ts_energia = obter_constante('Desconto TS Energia', CONSTANTES) if tarifa_social else 0.0
        preco_energia_final_unitario_sem_iva = {}
        for p_key in energia_meu_periodo_comercializador_base.keys():
            base_desc_perc = energia_meu_periodo_comercializador_base.get(p_key, 0.0) + tar_energia_regulada_periodo_meu.get(p_key, 0.0) + financiamento_tse_a_somar_base
            apos_desc_comerc = base_desc_perc * (1 - (desconto_energia or 0.0) / 100.0)
            preco_energia_final_unitario_sem_iva[p_key] = apos_desc_comerc - desconto_monetario_ts_energia if tarifa_social else apos_desc_comerc
            
        desconto_monetario_ts_potencia = obter_constante(f'Desconto TS Potencia {potencia}', CONSTANTES) if tarifa_social else 0.0
        base_desc_pot_perc = potencia_meu_comercializador_base + tar_potencia_regulada_meu_base
        apos_desc_pot_comerc = base_desc_pot_perc * (1 - (desconto_potencia or 0.0) / 100.0)
        preco_potencia_final_unitario_sem_iva = apos_desc_pot_comerc - desconto_monetario_ts_potencia if tarifa_social else apos_desc_pot_comerc

        consumo_total = sum(consumos_para_calculo.values())
        decomposicao_energia = calcular_custo_energia_com_iva(consumo_total, preco_energia_final_unitario_sem_iva.get('S'), {k:v for k,v in preco_energia_final_unitario_sem_iva.items() if k!='S'}, dias, potencia, opcao_horaria, consumos_para_calculo, familia_numerosa)
        
        comerc_pot_para_iva = potencia_meu_comercializador_base * (1 - (desconto_potencia or 0.0) / 100.0)
        tar_pot_bruta_apos_desc = tar_potencia_regulada_meu_base * (1 - (desconto_potencia or 0.0) / 100.0)
        tar_pot_final_para_iva = tar_pot_bruta_apos_desc - desconto_monetario_ts_potencia if tarifa_social else tar_pot_bruta_apos_desc
        decomposicao_potencia = calcular_custo_potencia_com_iva_final(comerc_pot_para_iva, tar_pot_final_para_iva, dias, potencia)
        
        decomposicao_taxas = calcular_taxas_adicionais(consumo_total, dias, tarifa_social, valor_dgeg_user, valor_cav_user, "Pessoal", is_billing_month)
        
        custo_total_antes_desc_fatura = decomposicao_energia['custo_com_iva'] + decomposicao_potencia['custo_com_iva'] + decomposicao_taxas['custo_com_iva']
        custo_final = custo_total_antes_desc_fatura - float(desconto_fatura_input_meu or 0.0) + float(acrescimo_fatura_input_meu or 0.0)

        # --- PASSO 4: MONTAR O DICIONÁRIO DE RETORNO ---
        nome_para_exibir = "O Meu Tarifário"
        sufixo = ""
        desconto = float(desconto_fatura_input_meu or 0.0)
        acrescimo = float(acrescimo_fatura_input_meu or 0.0)
        if desconto > 0 or acrescimo > 0:
            liquido = desconto - acrescimo
            if liquido > 0: sufixo = f" (Inclui desc. líquido de {liquido:.2f}€)"
            elif liquido < 0: sufixo = f" (Inclui acréscimo líquido de {abs(liquido):.2f}€)"
        nome_para_exibir += sufixo

        return { 'Total (€)': custo_final, 'NomeParaExibir': nome_para_exibir }

    except Exception as e:
        st.error(f"Erro ao calcular 'O Meu Tarifário': {e}")
        return None

def calcular_valor_financeiro_cenario(
    df_cenario,
    df_omie_completo,
    # --- NOVOS PARÂMETROS ---
    precos_compra_kwh_siva, # Dicionário com preços por período
    dias_calculo,
    potencia_kva,
    opcao_horaria_str,
    familia_numerosa_bool,
    # --- PARÂMETROS ANTIGOS (para venda) ---
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
        consumos_horarios=consumos_rede_por_periodo, # <--- Os consumos da rede por período
        familia_numerosa_bool=familia_numerosa_bool
    )
    
    custo_compra_final_com_iva = resultado_custo_energia['custo_com_iva']

    # --- 2. CÁLCULO DA RECEITA DE VENDA (Lógica Mantida) ---
    injecao_rede_total = df_cenario['Injecao_Rede_Final_kWh'].sum()
    receita_venda = 0
    preco_medio_venda = 0

    if injecao_rede_total > 0:
        if modelo_venda == 'Preço Fixo':
            receita_venda = injecao_rede_total * valor_comissao
            preco_medio_venda = valor_comissao
        
        elif modelo_venda == 'Indexado ao OMIE':
            # Nota: df_merged já foi criado acima, podemos reutilizá-lo
            df_merged['OMIE'].fillna(0, inplace=True)
            
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
        'custo_compra_c_iva': custo_compra_final_com_iva, # Nome alterado para clareza
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