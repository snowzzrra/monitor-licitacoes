import os
import time
from datetime import datetime
import requests
from bs4 import BeautifulSoup

# Importa a nova biblioteca para o Chrome serverless
import chrome_aws_lambda

from flask import Flask, render_template, request, flash, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

app = Flask(__name__)

# --- CONFIGURAÇÃO DE AMBIENTE ROBUSTA ---
db_url = os.getenv('POSTGRES_URL') or os.getenv('DATABASE_URL')
if not db_url:
    raise ValueError("Nenhuma variável de banco de dados (POSTGRES_URL ou DATABASE_URL) foi encontrada.")

if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_recycle': 280,
    'pool_pre_ping': True
}

db = SQLAlchemy(app)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CRON_SECRET = os.getenv('CRON_SECRET')
URL_FORMULARIO = "https://www.comprasnet.ba.gov.br/inter/system/Licitacao/FormularioConsultaAcompanhamento.asp"

# ... (Modelos e funções de notificação permanecem os mesmos) ...
class Licitacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero_completo = db.Column(db.String, unique=True, nullable=False)
    orgao = db.Column(db.String)
    objeto = db.Column(db.String)
    status = db.Column(db.String)
    data_verificacao = db.Column(db.DateTime, default=datetime.utcnow)

class UsuarioTelegram(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.String, unique=True, nullable=False)
    notificacoes_ativas = db.Column(db.Boolean, default=True)

def enviar_notificacao_telegram(chat_id, mensagem):
    if not TELEGRAM_TOKEN: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': chat_id, 'text': mensagem, 'parse_mode': 'Markdown'}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Exceção ao enviar notificação: {e}")

def notificar_todos_usuarios(mensagem):
    with app.app_context():
        usuarios = UsuarioTelegram.query.filter_by(notificacoes_ativas=True).all()
        for usuario in usuarios:
            enviar_notificacao_telegram(usuario.chat_id, mensagem)

def configurar_driver_selenium():
    """
    Configura o Selenium para usar o chrome-aws-lambda,
    a forma correta para ambientes serverless como a Vercel.
    """
    options = webdriver.ChromeOptions()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280x1696")
    options.add_argument("--single-process")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-dev-tools")
    options.add_argument("--no-zygote")
    options.add_argument(f"user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36")
    
    # Aponta para os executáveis fornecidos pelo pacote chrome-aws-lambda
    options.binary_location = chrome_aws_lambda.chrome_executable_path
    
    driver = webdriver.Chrome(
        service=webdriver.ChromeService(chrome_aws_lambda.chromedriver_path),
        options=options
    )
    return driver

# ... (O restante do código, incluindo as funções de scraping e rotas, permanece o mesmo) ...
def buscar_licitacoes_por_data(data_busca):
    driver = None
    try:
        driver = configurar_driver_selenium()
        driver.get(URL_FORMULARIO)
        wait = WebDriverWait(driver, 30)
        wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, 'ifsys')))
        campo_data_inicio = wait.until(EC.presence_of_element_located((By.NAME, 'txtDataAberturaInicial')))
        campo_data_fim = driver.find_element(By.NAME, 'txtDataAberturaFinal')
        data_formatada = data_busca.strftime('%d/%m/%Y')
        driver.execute_script("arguments[0].value = arguments[1];", campo_data_inicio, data_formatada)
        driver.execute_script("arguments[0].value = arguments[1];", campo_data_fim, data_formatada)
        botao_pesquisar = wait.until(EC.element_to_be_clickable((By.ID, 'btnPesquisarAcompanhamentos')))
        driver.execute_script("arguments[0].click();", botao_pesquisar)
        wait.until(EC.presence_of_element_located((By.ID, 'tblListaAcompanhamento')))
        linhas_de_resultado = driver.find_elements(By.XPATH, "//table[@id='tblListaAcompanhamento']/tbody/tr")
        licitacoes_encontradas = []
        for linha in linhas_de_resultado:
            celulas = linha.find_elements(By.TAG_NAME, 'td')
            if len(celulas) > 6:
                licitacoes_encontradas.append({'numero_completo': celulas[0].text, 'orgao': celulas[1].text, 'status': celulas[5].text, 'objeto': celulas[6].text})
        return licitacoes_encontradas
    except Exception as e:
        print(f"Erro no scraping por data: {e}")
        return []
    finally:
        if driver: driver.quit()

def buscar_detalhes_licitacao(numero_completo):
    driver = None
    try:
        driver = configurar_driver_selenium()
        driver.get(URL_FORMULARIO)
        wait = WebDriverWait(driver, 40)
        wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, 'ifsys')))
        campo_licitacao = wait.until(EC.element_to_be_clickable((By.NAME, 'txtNumeroLicitacao')))
        campo_licitacao.clear()
        campo_licitacao.send_keys(numero_completo)
        botao_pesquisar = wait.until(EC.element_to_be_clickable((By.ID, 'btnPesquisarAcompanhamentos')))
        driver.execute_script("arguments[0].click();", botao_pesquisar)
        wait.until(EC.presence_of_element_located((By.ID, 'tblListaAcompanhamento')))
        link_licitacao = wait.until(EC.element_to_be_clickable((By.XPATH, "//table[@id='tblListaAcompanhamento']/tbody/tr[1]/td[1]/a")))
        driver.execute_script("arguments[0].click();", link_licitacao)
        wait.until(EC.presence_of_element_located((By.ID, 'ConteudoPrint')))
        soup = BeautifulSoup(driver.page_source, 'lxml')
        dados_gerais = {}
        tabela_detalhes = soup.find('table', id='ConteudoPrint')
        if tabela_detalhes:
            for linha in tabela_detalhes.find_all('tr'):
                celulas_th = linha.find_all('th')
                if len(celulas_th) >= 2:
                    dados_gerais[celulas_th[0].get_text(strip=True).replace(':', '')] = celulas_th[1].get_text(strip=True)
        eventos = []
        titulo_eventos = soup.find('th', string='EVENTOS')
        if titulo_eventos:
            tabela_eventos = titulo_eventos.find_parent('table').find_next_sibling('table')
            if tabela_eventos:
                for linha in tabela_eventos.find_all('tr'):
                    celulas = linha.find_all('td')
                    if len(celulas) >= 2:
                        eventos.append({'data_hora': celulas[0].get_text(strip=True), 'descricao': celulas[1].get_text(strip=True)})
        return {'dados_gerais': dados_gerais, 'eventos': eventos}, None
    except Exception as e:
        return None, f"Erro ao buscar detalhes: {e}"
    finally:
        if driver: driver.quit()

@app.route('/')
def index():
    try:
        hoje = datetime.now().date()
        licitacoes_hoje = Licitacao.query.filter(db.func.date(Licitacao.data_verificacao) >= hoje).order_by(Licitacao.id.desc()).all()
    except Exception as e:
        print(f"Erro ao conectar ao banco de dados: {e}")
        flash("Erro ao conectar ao banco de dados. As tabelas foram criadas? Tente acessar /init-db.", "danger")
        licitacoes_hoje = []
    return render_template('index.html', licitacoes_hoje=licitacoes_hoje)

@app.route('/inscrever', methods=['POST'])
def inscrever():
    chat_id = request.form.get('chat_id')
    if not chat_id or not chat_id.isdigit():
        flash('Por favor, insira um Chat ID do Telegram válido (apenas números).', 'danger')
        return redirect(url_for('index'))
    usuario_existente = UsuarioTelegram.query.filter_by(chat_id=chat_id).first()
    if usuario_existente:
        flash('Este Chat ID já está cadastrado!', 'warning')
    else:
        novo_usuario = UsuarioTelegram(chat_id=chat_id)
        db.session.add(novo_usuario)
        db.session.commit()
        flash('Inscrição realizada com sucesso!', 'success')
        enviar_notificacao_telegram(chat_id, "✅ Olá! Você se inscreveu com sucesso no Monitor de Licitações BA.")
    return redirect(url_for('index'))

@app.route('/detalhes/<path:numero_completo>')
def detalhes(numero_completo):
    dados, erro = buscar_detalhes_licitacao(numero_completo)
    if erro:
        flash(f"Não foi possível carregar os detalhes. Erro: {erro}", 'danger')
        return redirect(url_for('index'))
    return render_template('detalhes.html', dados=dados['dados_gerais'], eventos=dados['eventos'], numero_licitacao=numero_completo)

@app.route('/api/cron/verificar-licitacoes')
def tarefa_diaria_verificacao():
    auth_header = request.headers.get('Authorization')
    if not auth_header or auth_header != f'Bearer {CRON_SECRET}':
        return jsonify({'status': 'unauthorized'}), 401
    
    print(f"[{datetime.now()}] Cron Job acionado. Iniciando verificação...")
    hoje = datetime.now()
    licitacoes_do_dia = buscar_licitacoes_por_data(hoje)
    if not licitacoes_do_dia:
        print("Nenhuma licitação encontrada para hoje.")
        return jsonify({'status': 'nenhuma licitação encontrada'}), 200
    
    novas_encontradas = 0
    atualizadas = 0
    for licitacao_nova in licitacoes_do_dia:
        licitacao_existente = Licitacao.query.filter_by(numero_completo=licitacao_nova['numero_completo']).first()
        if not licitacao_existente:
            novas_encontradas += 1
            nova = Licitacao(numero_completo=licitacao_nova['numero_completo'], orgao=licitacao_nova['orgao'], status=licitacao_nova['status'], objeto=licitacao_nova['objeto'])
            db.session.add(nova)
            mensagem = (f"📢 *Nova Licitação Encontrada!*\n\n*Número:* `{licitacao_nova['numero_completo']}`\n*Órgão:* {licitacao_nova['orgao']}\n*Objeto:* {licitacao_nova['objeto']}\n*Status:* {licitacao_nova['status']}")
            notificar_todos_usuarios(mensagem)
        elif licitacao_existente.status != licitacao_nova['status']:
            atualizadas += 1
            status_antigo = licitacao_existente.status
            licitacao_existente.status = licitacao_nova['status']
            licitacao_existente.data_verificacao = datetime.utcnow()
            mensagem = (f"🔄 *Atualização de Licitação!*\n\n*Número:* `{licitacao_nova['numero_completo']}`\n*Órgão:* {licitacao_nova['orgao']}\n*Status alterado de:* {status_antigo}\n*Novo Status:* {licitacao_nova['status']}")
            notificar_todos_usuarios(mensagem)
    db.session.commit()
    print(f"Verificação concluída. Novas: {novas_encontradas}. Atualizadas: {atualizadas}.")
    return jsonify({'status': 'success', 'novas': novas_encontradas, 'atualizadas': atualizadas}), 200

@app.route('/forcar-busca')
def forcar_busca():
    flash('A verificação diária é executada automaticamente às 8:30 (BRT). Para testar, acione o Cron Job manualmente no dashboard da Vercel.', 'info')
    return redirect(url_for('index'))

@app.route('/testar-notificacoes')
def testar_notificacoes():
    hoje = datetime.now().date()
    licitacoes_hoje = Licitacao.query.filter(db.func.date(Licitacao.data_verificacao) >= hoje).all()
    if not licitacoes_hoje:
        flash('Nenhuma licitação encontrada no banco de dados para hoje. Force uma verificação primeiro.', 'warning')
        return redirect(url_for('index'))
    mensagem_geral = f"📋 *(TESTE)* Resumo das Licitações de Hoje ({hoje.strftime('%d/%m/%Y')})\n\n"
    for lic in licitacoes_hoje:
        mensagem_geral += f"• `{lic.numero_completo}` ({lic.status})\n"
    notificar_todos_usuarios(mensagem_geral)
    flash(f'Tentativa de envio de {len(licitacoes_hoje)} licitações para os usuários inscritos.', 'info')
    return redirect(url_for('index'))

@app.route('/limpar-db')
def limpar_db():
    try:
        num_rows_deleted = db.session.query(Licitacao).delete()
        db.session.commit()
        flash(f'{num_rows_deleted} registros de licitações foram apagados do banco de dados.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao limpar o banco de dados: {e}', 'danger')
    return redirect(url_for('index'))

@app.route('/init-db')
def init_db():
    with app.app_context():
        db.create_all()
    return "Banco de dados inicializado com sucesso. As tabelas 'licitacao' e 'usuario_telegram' foram criadas."
