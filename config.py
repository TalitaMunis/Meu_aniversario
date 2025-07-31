import os
from dotenv import load_dotenv

# Carrega as variáveis de ambiente do arquivo .env
# Este arquivo (.env) deve estar na raiz do seu projeto e conter:
# SECRET_KEY=sua_chave_secreta_longa_e_aleatoria
# DATABASE_URL=sqlite:///site.db (ou sua URL de banco de dados real para produção)
# ADMIN_USERNAME=admin (opcional, para usuário padrão do setup)
# ADMIN_PASSWORD=adminpass (opcional, para senha padrão do setup)
# ADMIN_EMAIL=admin@example.com (opcional, para email padrão do setup)
# GCS_BUCKET_NAME=nome_do_seu_bucket_gcs_aqui
load_dotenv()

class Config:
    """
    Classe de configuração para o aplicativo Flask.
    Define variáveis de ambiente e caminhos de pastas.
    """
    # Chave secreta para segurança do Flask (sessões, CSRF, etc.)
    # É carregada do .env. Use uma chave forte e secreta em produção!
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'MeuAniversario2025'

    # URI do banco de dados principal (para desenvolvimento/produção)
    # Carregada do .env. Fallback para SQLite local 'site.db'.
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///site.db'
    
    # URI do banco de dados de teste (SQLite em memória)
    # Usado exclusivamente para rodar os testes, garantindo isolamento.
    SQLALCHEMY_DATABASE_URI_TEST = 'sqlite:///:memory:' 
    
    # Desativa o rastreamento de modificações do SQLAlchemy.
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Caminho absoluto para a pasta onde os arquivos enviados pelos convidados serão armazenados (uploads/)
    # No deploy, essa pasta não será usada para uploads reais, mas é necessária para a lógica de `pytest` e desenvolvimento.
    UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'uploads')
    
    # Caminho absoluto para a pasta 'static/' do seu projeto Flask
    STATIC_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static')

    # Configuração de tamanho máximo para uploads de arquivos em bytes (ex: 16 MB)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024 # 16 Megabytes

    # Duração máxima padrão de vídeo em segundos.
    MAX_VIDEO_DURATION_SECONDS = 20 # 20 segundos para vídeos
    
    # --- Configurações do Google Cloud Storage ---
    # Carregado do .env. Estes valores são cruciais para o deploy.
    GCS_PROJECT_ID = os.environ.get('GCS_PROJECT_ID')
    GCS_BUCKET_NAME = os.environ.get('GCS_BUCKET_NAME')
    # Nota: GOOGLE_APPLICATION_CREDENTIALS_JSON é lido diretamente do os.environ no app.py
