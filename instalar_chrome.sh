#!/bin/bash
# Script para instalar Google Chrome no WSL

echo "Instalando dependências necessárias..."
sudo apt-get update
sudo apt-get install -y wget gnupg

echo "Baixando e instalando Google Chrome..."
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list
sudo apt-get update
sudo apt-get install -y google-chrome-stable

echo "Chrome instalado com sucesso!"
google-chrome --version


