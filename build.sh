#!/bin/bash

# Define a saída para ser detalhada e parar em caso de erro
set -ex

# Vercel já instalou as dependências do Python a partir do requirements.txt.
# A única tarefa deste script é instalar o Google Chrome e o Chromedriver.

# 1. Instala as dependências do sistema para o Chrome (GConf2 foi removido)
echo "Instalando dependências do sistema para o Chrome..."
yum install -y alsa-lib atk at-spi2-atk cups-libs gtk3 libX11-xcb libXcomposite libXcursor libXdamage libXext libXfixes libXi libXrandr libXScrnSaver libXtst pango liberation-sans-fonts xdg-utils

# 2. Baixa e instala o Google Chrome
echo "Baixando Google Chrome..."
wget https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/127.0.6533.72/linux64/chrome-linux64.zip -q -O chrome.zip
unzip -q chrome.zip
rm chrome.zip
mv chrome-linux64 /opt/google/chrome
echo "Google Chrome instalado."

# 3. Baixa, instala e torna executável o Chromedriver em um caminho padrão
echo "Baixando e instalando Chromedriver..."
wget https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/127.0.6533.72/linux64/chromedriver-linux64.zip -q -O chromedriver.zip
unzip -q chromedriver.zip
rm chromedriver.zip
mv chromedriver-linux64/chromedriver /usr/local/bin/chromedriver
chmod +x /usr/local/bin/chromedriver
echo "Chromedriver instalado em /usr/local/bin/chromedriver."

echo "Build finalizado com sucesso!"
