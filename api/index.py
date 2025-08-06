import os
import subprocess

# ==================== O SEGREDO ESTÁ AQUI ====================
# Definimos o caminho de instalação ANTES de qualquer outro import
# Isso garante que o Playwright, quando for importado, já saiba onde procurar.
INSTALL_PATH = "/tmp/playwright-install"
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = INSTALL_PATH
# ==============================================================

# Agora, importamos o resto dos módulos
from flask import Flask, render_template, request, flash, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from bs4 import BeautifulSoup
from datetime import datetime
import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# --- Função de Setup ---
def setup_playwright():
    lock_file_path = f"{INSTALL_PATH}/installed.lock"

    if not os.path.exists(lock_file_path):
        print("Instalando navegador Chromium (isso só acontece uma vez)...")
        
        # O comando agora é mais simples, pois a variável de ambiente já foi definida
        command = ["python3.12", "-m", "playwright", "install", "chromium"]
        
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        
        if result.returncode == 0:
            print("Navegador instalado com sucesso.")
            # Cria o arquivo de trava para não instalar de novo
            os.makedirs(INSTALL_PATH, exist_ok=True)
            with open(lock_file_path, 'w') as f:
                f.write('installed')
        else:
            print("### ERRO na instalação do Playwright ###")
            print(result.stdout)
            print(result.stderr)
            # Lança uma exceção para parar a execução se a instalação falhar
            raise RuntimeError("Falha ao instalar o navegador Playwright.")
    else:
        print("Navegador Chromium já está em cache.")

# Roda a função de setup quando o servidor inicia
setup_playwright()


# --- O RESTO DO SEU CÓDIGO (sem alterações) ---

# Configuração do Flask
app = Flask(__name__, template_folder='../templates')
db_url = os.getenv('POSTGRES_URL') or os.getenv('DATABASE_URL')
if not db_url:
    raise ValueError("Nenhuma variável de banco de dados (POSTGRES_URL ou DATABASE_URL) foi encontrada.")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_recycle': 280, 'pool_pre_ping': True}
db = SQLAlchemy(app)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CRON_SECRET = os.getenv('CRON_SECRET')
URL_FORMULARIO = "https://www.comprasnet.ba.gov.br/inter/system/Licitacao/FormularioConsultaAcompanhamento.asp"

# Modelos do Banco
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

# Funções de Notificação
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

# Funções de Scraping (sem alterações na lógica interna)
def buscar_licitacoes_por_data(data_busca):
    with sync_playwright() as p:
        try:
            # Agora o launch() vai respeitar a variável de ambiente
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(URL_FORMULARIO, timeout=60000)
            frame = page.frame_locator("#ifsys")
            data_formatada = data_busca.strftime('%d/%m/%Y')
            frame.locator("input[name='txtDataAberturaInicial']").fill(data_formatada)
            frame.locator("input[name='txtDataAberturaFinal']").fill(data_formatada)
            frame.locator("#btnPesquisarAcompanhamentos").click()
            frame.locator("#tblListaAcompanhamento").wait_for(timeout=30000)
            linhas_de_resultado = frame.locator("//table[@id='tblListaAcompanhamento']/tbody/tr").all()
            licitacoes_encontradas = []
            for linha in linhas_de_resultado:
                celulas = linha.locator('td').all_inner_texts()
                if len(celulas) > 6:
                    licitacoes_encontradas.append({'numero_completo': celulas[0],'orgao': celulas[1],'status': celulas[5],'objeto': celulas[6]})
            browser.close()
            return licitacoes_encontradas
        except Exception as e:
            print(f"Erro no scraping por data com Playwright: {e}")
            if 'browser' in locals() and browser.is_connected():
                browser.close()
            return []

def buscar_detalhes_licitacao(numero_completo):
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(URL_FORMULARIO, timeout=60000)
            frame = page.frame_locator("#ifsys")
            frame.locator("input[name='txtNumeroLicitacao']").fill(numero_completo)
            frame.locator("#btnPesquisarAcompanhamentos").click()
            frame.locator("//table[@id='tblListaAcompanhamento']/tbody/tr[1]/td[1]/a").click()
            frame.locator("#ConteudoPrint").wait_for(timeout=30000)
            soup = BeautifulSoup(page.content(), 'lxml')
            frame_soup = BeautifulSoup(str(soup.find(id='ifsys')), 'lxml')
            dados_gerais, eventos = {}, []
            tabela_detalhes = frame_soup.find('table', id='ConteudoPrint')
            if tabela_detalhes:
                for linha in tabela_detalhes.find_all('tr'):
                    celulas_th = linha.find_all('th')
                    if len(celulas_th) >= 2:
                        dados_gerais[celulas_th[0].get_text(strip=True).replace(':', '')] = celulas_th[1].get_text(strip=True)
            titulo_eventos = frame_soup.find('th', string='EVENTOS')
            if titulo_eventos:
                tabela_eventos = titulo_eventos.find_parent('table').find_next_sibling('table')
                if tabela_eventos:
                    for linha in tabela_eventos.find_all('tr'):
                        celulas_td = linha.find_all('td')
                        if len(celulas_td) >= 2:
                            eventos.append({'data_hora': celulas_td[0].get_text(strip=True), 'descricao': celulas_td[1].get_text(strip=True)})
            browser.close()
            return {'dados_gerais': dados_gerais, 'eventos': eventos}, None
        except Exception as e:
            if 'browser' in locals() and browser.is_connected():
                browser.close()
            return None, f"Erro ao buscar detalhes com Playwright: {e}"

# Rotas do Flask (sem alterações)
@app.route('/')
def index():
    try:
        hoje = datetime.now().date()
        licitacoes_hoje = Licitacao.query.filter(db.func.date(Licitacao.data_verificacao) >= hoje).order_by(Licitacao.id.desc()).all()
    except Exception as e:
        print(f"Erro ao conectar ao banco de dados: {e}")
        flash("Erro ao conectar ao banco de dados.", "danger")
        licitacoes_hoje = []
    return render_template('index.html', licitacoes_hoje=licitacoes_hoje)

@app.route('/api/cron/verificar-licitacoes')
def tarefa_diaria_verificacao():
    # ... seu código da tarefa cron ...
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