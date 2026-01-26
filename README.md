# Projeto de Acesso a Página Web

Projeto Python básico para acessar uma página web usando Selenium.

## Instalação

1. Crie um ambiente virtual (se ainda não criou):
```bash
python3 -m venv venv
```

2. Ative o ambiente virtual:
```bash
source venv/bin/activate
```

3. Instale as dependências:
```bash
pip install -r requirements.txt
```

## Uso

1. Ative o ambiente virtual (se ainda não estiver ativado):
```bash
source venv/bin/activate
```

2. Execute o script:
```bash
python acessar_pagina.py
```

O script irá:
- Abrir o navegador Chrome
- Acessar a página especificada
- Preencher os campos de login (usuário: EAndriao, senha: Dudu2e25)
- Exibir informações da página
- Fechar o navegador após alguns segundos

## Instalação do Google Chrome (WSL)

Se você estiver usando WSL e o Chrome não estiver instalado, execute:

```bash
./instalar_chrome.sh
```

Ou instale manualmente:

```bash
sudo apt-get update
sudo apt-get install -y wget gnupg
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list
sudo apt-get update
sudo apt-get install -y google-chrome-stable
```

## Notas

- **IMPORTANTE**: É necessário ter o Google Chrome instalado no sistema
- O webdriver-manager irá baixar automaticamente o ChromeDriver compatível
- Para executar em modo headless (sem abrir o navegador), descomente a linha no código
- No WSL, você pode precisar configurar o display para ver o navegador (ou usar modo headless)

