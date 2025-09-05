# Simulador de Autoconsumo Solar Fotovoltaico - Portugal

![Logo](https://raw.githubusercontent.com/tiagofelicia/simulador-tarifarios-eletricidade/refs/heads/main/Logo_Tiago_Felicia.png)

Bem-vindo ao Simulador de Autoconsumo, uma ferramenta de análise energética e financeira desenhada para ajudar consumidores e empresas em Portugal a tomar a melhor decisão sobre um investimento em energia solar fotovoltaica.

O objetivo deste projeto é desmistificar o autoconsumo, permitindo simulações detalhadas de sistemas com painéis solares e baterias para calcular a poupança real, o tempo de retorno do investimento (Payback) e a viabilidade financeira de cada cenário.

**➡️ [Aceda aqui à versão ao vivo do simulador](https://www.tiagofelicia.pt/autoconsumo-tiagofelicia.html)**

---

## 🚀 Funcionalidades Principais

* **Simulação de Alta Precisão:** Utiliza o seu **diagrama de carga da E-Redes** (dados de consumo a cada 15 minutos) como base para todos os cálculos.
* **Produção Solar Realista:**
    * ☀️ **API PVGIS:** Simula a produção solar com base na sua localização geográfica exata, usando a conceituada API PVGIS da Comissão Europeia.
    * 🗺️ **Backup por Distrito:** Utiliza perfis de produção médios para cada distrito de Portugal caso a API não esteja disponível.
* **Simulação de Baterias:** Modele o comportamento de um sistema de armazenamento, definindo a capacidade (kWh), potência (kW), profundidade de descarga (DoD) e eficiência.
* **Análise Financeira Completa:**
    * 💰 **Payback Detalhado:** Calcula o tempo de retorno do investimento considerando a inflação do preço da energia e a degradação da eficiência dos painéis.
    * 📈 **Retorno do Investimento (ROI):** Estima o retorno anual do seu investimento.
    * 📊 **Fluxo de Caixa:** Visualize a projeção da sua poupança anual e acumulada ao longo de 25 anos.
* **Comparação de Cenários:** Guarde múltiplas simulações (diferentes potências de painéis, com/sem bateria) e compare os resultados energéticos e financeiros lado a lado.
* **Assistente de Dimensionamento:** Teste dezenas de combinações de painéis e baterias de uma só vez para encontrar a configuração ideal.
* **Comparador de Propostas:** Introduza os dados de propostas comerciais reais de instaladores e compare-as de forma justa e transparente.
* **Relatórios Profissionais:**
    * 📄 **Exportação para PDF:** Gere um relatório completo com todos os parâmetros, resumos e gráficos da sua simulação.
    * 💹 **Exportação para Excel:** Descarregue os dados detalhados para análise posterior.

---

## 💻 Tecnologias Utilizadas

* **Frontend:** [Streamlit](https://streamlit.io/)
* **Manipulação de Dados:** [Pandas](https://pandas.pydata.org/), [NumPy](https://numpy.org/)
* **Mapas:** [Folium](https://python-visualization.github.io/folium/) (via `streamlit-folium`)
* **Geração de PDF:** [FPDF2](https://github.com/py-pdf/fpdf2)
* **Gráficos:** [Highcharts](https://www.highcharts.com/) (via HTML/JS), [Matplotlib](https://matplotlib.org/) (para os relatórios)
* **Interação com Excel:** [Openpyxl](https://openpyxl.readthedocs.io/)
* **Comunicação API:** [Requests](https://requests.readthedocs.io/)

---

## ❤️ Apoie o Projeto

Se esta ferramenta lhe foi útil, considere apoiar a sua manutenção e desenvolvimento contínuo.

* [☕ Compre-me um café (BuyMeACoffee)](https://buymeacoffee.com/tiagofelicia)
* [🅿️ Doe via PayPal](https://www.paypal.com/donate?hosted_button_id=W6KZHVL53VFJC)

---

## 📧 Contacto

Tiago Felícia - [www.tiagofelicia.pt](https://www.tiagofelicia.pt)

Encontre-me nas redes sociais: [X/Twitter](https://x.com/tiagofelicia) | [Facebook](https://www.facebook.com/profile.php?id=61555007360529) | [YouTube](https://youtube.com/@tiagofelicia)
