#!/bin/bash

# Define a saída para ser detalhada e parar em caso de erro
set -ex

# 1. Instala as dependências do Python
echo "Instalando dependências do Python..."
python3.9 -m pip install -r requirements.txt

# 2. Instala as dependências do sistema para o Chrome
echo "Instalando dependências do sistema para o Chrome..."
yum install -y alsa-lib atk at-spi2-atk cups-libs GConf2 gtk3 libX11-xcb libXcomposite libXcursor libXdamage libXext libXfixes libXi libXrandr libXScrnSaver libXtst pango liberation-sans-fonts xdg-utils

# 3. Baixa e instala o Google Chrome
echo "Baixando Google Chrome..."
wget https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/127.0.6533.72/linux64/chrome-linux64.zip -q -O chrome.zip
unzip -q chrome.zip
rm chrome.zip
mv chrome-linux64 /opt/google/chrome
echo "Google Chrome instalado."

# 4. Baixa, instala e TORNA EXECUTÁVEL o Chromedriver
echo "Baixando Chromedriver..."
wget https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/127.0.6533.72/linux64/chromedriver-linux64.zip -q -O chromedriver.zip
unzip -q chromedriver.zip
rm chromedriver.zip
mv chromedriver-linux64 /opt/chromedriver
chmod +x /opt/chromedriver/chromedriver # <-- A CORREÇÃO CRUCIAL
echo "Chromedriver instalado e configurado."

echo "Build finalizado com sucesso!"
