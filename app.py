from flask import Flask, render_template, request, flash, redirect, url_for
from bs4 import BeautifulSoup
import os
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

app = Flask(__name__)
app.secret_key = os.urandom(24)
URL_FORMULARIO = "https://www.comprasnet.ba.gov.br/inter/system/Licitacao/FormularioConsultaAcompanhamento.asp"

def extrair_dados_licitacao(numero_busca, index_para_clicar=None):
    # ==================== CONFIGURAÇÃO ANTI-DETECÇÃO HEADLESS ====================
    options = webdriver.ChromeOptions()
    
    options.add_argument('--headless=new')
    
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
    options.add_argument(f'user-agent={user_agent}')
    
    options.add_argument("--window-size=1920,1080")
    
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    
    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': '''
                Object.defineProperty(navigator, 'webdriver', {
                  get: () => undefined
                })
            '''
        })
        
        driver.get(URL_FORMULARIO)
        wait = WebDriverWait(driver, 30)
        
        wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, 'ifsys')))
        
        campo_licitacao = wait.until(EC.element_to_be_clickable((By.NAME, 'txtNumeroLicitacao')))
        campo_licitacao.clear()
        campo_licitacao.send_keys(numero_busca)
        
        botao_pesquisar = wait.until(EC.element_to_be_clickable((By.ID, 'btnPesquisarAcompanhamentos')))
        driver.execute_script("arguments[0].click();", botao_pesquisar)

        wait.until(EC.presence_of_element_located((By.ID, 'tblListaAcompanhamento')))
        
        linhas_de_resultado = driver.find_elements(By.XPATH, "//table[@id='tblListaAcompanhamento']/tbody/tr")

        if not linhas_de_resultado:
            return 'erro', f"Nenhuma licitação encontrada para a busca '{numero_busca}'."

        if index_para_clicar is None and len(linhas_de_resultado) == 1:
            index_para_clicar = 0

        if index_para_clicar is not None:
            if index_para_clicar < len(linhas_de_resultado):
                link_licitacao = linhas_de_resultado[index_para_clicar].find_element(By.XPATH, ".//td[1]/a")
                driver.execute_script("arguments[0].click();", link_licitacao)
                
                wait.until(EC.presence_of_element_located((By.ID, 'ConteudoPrint')))
                
                soup = BeautifulSoup(driver.page_source, 'lxml')
                dados_gerais = {}
                
                tabela_detalhes = soup.find('table', id='ConteudoPrint')
                if tabela_detalhes:
                    for linha in tabela_detalhes.find_all('tr'):
                        celulas_th = linha.find_all('th')
                        if len(celulas_th) >= 2:
                            chave = celulas_th[0].get_text(strip=True).replace(':', '')
                            valor = celulas_th[1].get_text(strip=True)
                            dados_gerais[chave] = valor
                
                eventos = []
                titulo_eventos = soup.find('th', string='EVENTOS')
                if titulo_eventos:
                    tabela_eventos = titulo_eventos.find_parent('table').find_next_sibling('table')
                    if tabela_eventos:
                        for linha in tabela_eventos.find_all('tr'):
                            celulas = linha.find_all('td')
                            if len(celulas) >= 2:
                                eventos.append({'data_hora': celulas[0].get_text(strip=True), 'descricao': celulas[1].get_text(strip=True)})
                
                return 'detalhes', {'dados_gerais': dados_gerais, 'eventos': eventos}
            else:
                return 'erro', 'Índice da licitação inválido.'
        else:
            lista_para_escolha = []
            for linha in linhas_de_resultado:
                celulas = linha.find_elements(By.TAG_NAME, 'td')
                if len(celulas) > 6:
                    lista_para_escolha.append({
                        'numero': celulas[0].text,
                        'orgao': celulas[1].text,
                        'objeto': celulas[6].text,
                    })
            return 'lista', lista_para_escolha

    except TimeoutException:
        return 'erro', "Erro de Timeout. A página demorou para responder ou o modo headless foi detectado."
    except Exception as e:
        return 'erro', f"Ocorreu um erro inesperado: {str(e).splitlines()[0]}"
    finally:
        if driver:
            driver.quit()

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/consultar', methods=['POST'])
def consultar():
    numero_busca = request.form.get('numero_licitacao')
    if not numero_busca:
        flash('Por favor, informe o número da licitação.', 'warning')
        return redirect(url_for('index'))

    tipo_resultado, dados = extrair_dados_licitacao(numero_busca)

    if tipo_resultado == 'erro':
        flash(dados, 'danger')
        return render_template('index.html', numero_pesquisado=numero_busca)
    
    elif tipo_resultado == 'lista':
        return render_template('resultados.html', licitacoes=dados, numero_busca=numero_busca)
        
    elif tipo_resultado == 'detalhes':
        return render_template('detalhes.html', dados=dados['dados_gerais'], eventos=dados['eventos'], numero_licitacao=numero_busca)
    
    return redirect(url_for('index'))

@app.route('/detalhes', methods=['GET'])
def detalhes():
    numero_busca = request.args.get('busca')
    index_str = request.args.get('index')

    if not numero_busca or index_str is None:
        flash('Informações insuficientes para buscar os detalhes.', 'danger')
        return redirect(url_for('index'))

    try:
        index_para_clicar = int(index_str)
        tipo_resultado, dados = extrair_dados_licitacao(numero_busca, index_para_clicar=index_para_clicar)

        if tipo_resultado == 'detalhes':
            return render_template('detalhes.html', dados=dados['dados_gerais'], eventos=dados['eventos'], numero_licitacao=numero_busca)
        else:
            flash(dados, 'danger')
            return redirect(url_for('index'))

    except ValueError:
        flash('Índice inválido.', 'danger')
        return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)