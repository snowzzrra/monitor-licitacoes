#!/bin/bash

# Define que o script deve parar se algum comando falhar
set -e

# 1. Instala as dependências do Python
echo "Instalando dependências do Python..."
pip install pipenv
pipenv install --system --deploy

# 2. Instala os navegadores do Playwright
echo "Instalando o navegador Chromium..."
playwright install --with-deps chromium

echo "Build finalizado com sucesso!"