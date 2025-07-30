from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import uuid
from flask_login import UserMixin

# Inicializa a instância do SQLAlchemy.
# IMPORTANTE: Esta linha deve ser executada APENAS UMA VEZ no seu projeto.
# Ela será inicializada com o app Flask em app.py via db.init_app(app).
db = SQLAlchemy()

class Guest(db.Model):
    """
    Representa um grupo de convidados (ex: Família Silva) identificado por um token único.
    Um grupo pode estar associado a uma ou ambas as festas.
    """
    id = db.Column(db.Integer, primary_key=True)
    unique_token = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    group_name = db.Column(db.String(100), nullable=False) # Ex: "Família Silva", "João e Maria"
    
    # Define o tipo de festa ao qual este grupo pertence
    # 'talita_joaquim' para 30/08 ou 'talita_29_08' para 29/08
    party_type = db.Column(db.String(50), nullable=False, default='talita_joaquim') 

    # Relacionamento One-to-Many: Um Guest (grupo) pode ter vários GuestMembers
    # cascade="all, delete-orphan" garante que ao deletar um Guest, seus GuestMembers também são deletados.
    # order_by="GuestMember.id" garante que os membros são sempre ordenados por ID.
    members = db.relationship('GuestMember', backref='group', lazy=True, cascade="all, delete-orphan", order_by="GuestMember.id")
    
    # Relacionamento One-to-Many: Um Guest pode ter várias Confirmações (geralmente 1:1 na prática de RSVP)
    # cascade="all, delete-orphan" garante que ao deletar um Guest, suas Confirmações também são deletadas.
    confirmations = db.relationship('Confirmation', backref='guest', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"Guest('{self.group_name}', '{self.unique_token}', '{self.party_type}')"

class GuestMember(db.Model):
    """
    Representa um membro individual dentro de um grupo de convidados.
    Pode ser um membro principal da família ou um acompanhante extra (plus one).
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    guest_id = db.Column(db.Integer, db.ForeignKey('guest.id'), nullable=False)
    is_confirmed = db.Column(db.Boolean, default=False) # Status de confirmação individual
    is_plus_one = db.Column(db.Boolean, default=False) # Indica se é um acompanhante extra

    def __repr__(self):
        return f"GuestMember('{self.name}', Confirmed: {self.is_confirmed}, PlusOne: {self.is_plus_one})"

class Confirmation(db.Model):
    """
    Registra a confirmação de presença para um Guest (grupo).
    Armazena o nome do acompanhante extra e links para fotos/vídeos enviados.
    """
    id = db.Column(db.Integer, primary_key=True)
    # unique=True aqui garante que há apenas UMA confirmação por Guest.
    guest_id = db.Column(db.Integer, db.ForeignKey('guest.id'), nullable=False, unique=True) 
    plus_one_name = db.Column(db.String(100), nullable=True) # Nome do acompanhante extra se houver
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow) # Data/hora da confirmação (nome correto)
    
    # Relacionamentos One-to-Many com fotos e vídeos enviados
    # cascade="all, delete-orphan" garante que ao deletar uma Confirmação, suas fotos/vídeos também são deletados.
    photos = db.relationship('Photo', backref='confirmation', lazy=True, cascade="all, delete-orphan")
    videos = db.relationship('Video', backref='confirmation', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"Confirmation(Guest ID: {self.guest_id}, Plus One: {self.plus_one_name}, Timestamp: {self.timestamp.strftime('%Y-%m-%d %H:%M')})"

class Photo(db.Model):
    """
    Representa uma foto enviada por um convidado.
    """
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(120), nullable=False) # Nome do arquivo no sistema de arquivos
    confirmation_id = db.Column(db.Integer, db.ForeignKey('confirmation.id'), nullable=False)
    upload_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f"Photo('{self.filename}', Conf ID: {self.confirmation_id})"

class Video(db.Model):
    """
    Representa um vídeo enviado por um convidado.
    """
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(120), nullable=False) # Nome do arquivo no sistema de arquivos
    confirmation_id = db.Column(db.Integer, db.ForeignKey('confirmation.id'), nullable=False)
    upload_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    duration_seconds = db.Column(db.Integer, nullable=True) # Duração do vídeo (pode ser preenchido por JS/backend)

    def __repr__(self):
        return f"Video('{self.filename}', Conf ID: {self.confirmation_id})"

class AdminUser(db.Model, UserMixin): # UserMixin para integração com Flask-Login
    """
    Representa um usuário administrador para acessar o painel de controle.
    """
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False) # Username deve ser único e não nulo
    password_hash = db.Column(db.String(128), nullable=False) # Hash da senha
    email = db.Column(db.String(120), unique=True, nullable=False) # Email deve ser único e não nulo

    def __repr__(self):
        return f"AdminUser('{self.username}', '{self.email}')"

    # Métodos exigidos pelo Flask-Login
    def get_id(self):
        return str(self.id)
    
    # is_authenticated, is_active, is_anonymous são fornecidos pelo UserMixin

class ConfigSetting(db.Model):
    """
    Armazena configurações dinâmicas da aplicação (textos do convite, URLs, nomes de arquivos).
    Permite que o administrador edite esses valores sem alterar o código.
    """
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False) # Chave da configuração (ex: 'welcome_title'), deve ser única
    value = db.Column(db.Text, nullable=True) # Valor da configuração (texto, URL, nome de arquivo)

    def __repr__(self):
        return f"ConfigSetting('{self.key}', '{self.value[:50] + '...' if self.value and len(self.value) > 50 else self.value}')"

# NOVO MODELO: Para fotos do local da festa (venue)
class VenuePhoto(db.Model):
    """
    Representa uma foto do local da festa (venue), gerenciada pelo admin.
    """
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(120), nullable=False) # Nome do arquivo no sistema de arquivos
    description = db.Column(db.String(255), nullable=True) # Breve descrição da foto
    order = db.Column(db.Integer, default=0) # Ordem de exibição na galeria (menor número = primeiro)
    upload_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f"VenuePhoto('{self.filename}', Desc: '{self.description}')"