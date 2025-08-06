#!/bin/bash

# Define a saída para ser detalhada e parar em caso de erro
set -ex

# 1. Instala as ferramentas necessárias (wget para baixar, unzip para extrair)
echo "Instalando wget e unzip..."
yum install -y wget unzip

# 2. Instala as dependências do sistema para o Chrome
echo "Instalando dependências do sistema para o Chrome..."
yum install -y alsa-lib atk at-spi2-atk cups-libs gtk3 libX11-xcb libXcomposite libXcursor libXdamage libXext libXfixes libXi libXrandr libXScrnSaver libXtst pango liberation-sans-fonts xdg-utils

# --- A CORREÇÃO FINAL ---
# 3. Cria os diretórios de destino antes de mover os arquivos
echo "Criando diretórios de destino..."
mkdir -p /opt/google
mkdir -p /opt/chromedriver

# 4. Baixa e instala o Google Chrome
echo "Baixando Google Chrome..."
wget https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/127.0.6533.72/linux64/chrome-linux64.zip -q -O chrome.zip
unzip -q chrome.zip
rm chrome.zip
mv chrome-linux64 /opt/google/chrome
echo "Google Chrome instalado."

# 5. Baixa, instala e torna executável o Chromedriver em um caminho padrão
echo "Baixando e instalando Chromedriver..."
wget https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/127.0.6533.72/linux64/chromedriver-linux64.zip -q -O chromedriver.zip
unzip -q chromedriver.zip
rm chromedriver.zip
mv chromedriver-linux64/chromedriver /opt/chromedriver/chromedriver
chmod +x /opt/chromedriver/chromedriver
echo "Chromedriver instalado."

echo "Build finalizado com sucesso!"
