# Aracruz RE - Pipeline de Dados Imobiliários

Pipeline automatizado em Python para coleta, processamento e envio de dados do mercado imobiliário.

## Stack

- **Python 3** - Linguagem principal
- **Selenium** - Web scraping com navegador automatizado
- **Data Processing** - Scripts de tratamento e comparação de dados (clientes, vendas, holds)
- **Webhooks** - Integração com n8n para orquestração de fluxos

## Estrutura

```
acessar_pagina.py        # Scraper principal - coleta de dados via navegador
processar_clientes.py    # Limpeza e envio de dados de clientes
processar_sales.py       # Processamento de dados de vendas
processar_holds.py       # Processamento de dados de holds
instalar_chrome.sh       # Setup do Chrome para ambientes Linux/WSL
```

## Como funciona

1. O scraper acessa o portal imobiliário e coleta dados estruturados
2. Scripts de processamento limpam, comparam e formatam os dados
3. Resultados são enviados via webhook para pipelines n8n

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Configuração

Crie um arquivo `.env` com as credenciais necessárias (veja `.env.example`).

## Notas

- Requer Google Chrome instalado (modo headless disponível)
- webdriver-manager gerencia o ChromeDriver automaticamente
- Compatível com WSL (script de instalação do Chrome incluso)
