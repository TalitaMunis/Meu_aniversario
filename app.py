import os
import secrets
from datetime import datetime
from functools import wraps
import uuid

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    abort,
    send_from_directory
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# Importa as configurações da sua classe Config
from config import Config

# Importa o db e todos os modelos do seu models.py
# Adicione VenuePhoto aqui
from models import db, Guest, GuestMember, Confirmation, Photo, Video, AdminUser, ConfigSetting, VenuePhoto

# --- Flask-Login: Instanciação Correta para Padrão de Fábrica ---
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
login_manager = LoginManager()

# --- Padrão de Fábrica do Aplicativo Flask ---
def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Inicializa as extensões com o aplicativo Flask
    db.init_app(app)
    login_manager.init_app(app)

    # --- Configuração do Flask-Login ---
    login_manager.login_view = 'admin_login'
    login_manager.login_message_category = 'warning'

    @login_manager.user_loader
    def load_user(user_id):
        return AdminUser.query.get(int(user_id))

    # Garante que os diretórios de upload e static/img existem.
    # Adicione também a pasta para fotos do local (venue_photos)
    with app.app_context():
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        os.makedirs(os.path.join(app.config['STATIC_FOLDER'], 'img', 'venue_photos'), exist_ok=True)


    # --- Decorador de Autenticação Customizado para Admin ---
    def admin_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get('admin_logged_in'):
                flash('Você precisa fazer login para acessar esta página.', 'warning')
                return redirect(url_for('admin_login'))
            return f(*args, **kwargs)
        return decorated_function
    
    # --- Funções Auxiliares Comuns ---
    def get_invite_details():
        """
        Busca todas as configurações dinâmicas do banco de dados (ConfigSetting).
        Fornece valores padrão se as configurações não existirem no DB.
        """
        settings_query = ConfigSetting.query.all()
        details = {setting.key: setting.value for setting in settings_query}

        try:
            details['max_video_duration_seconds'] = int(details.get('max_video_duration_seconds', 20))
        except (ValueError, TypeError):
            details['max_video_duration_seconds'] = 20

        details.setdefault('welcome_title', 'Celebre Conosco!')
        details.setdefault('welcome_message', 'Estamos muito felizes em<br />convidá-lo(a) para celebrar conosco!')
        details.setdefault('main_photo_filename', 'sua_foto_do_aniversario.jpg')
        details.setdefault('party_date_talita_joaquim', '30 de Agosto')
        details.setdefault('party_date_other', '29 de Agosto')
        details.setdefault('party_location_name', 'ESTÂNCIA NA SERRA, CASA DE TEMPORADA Santa Bárbara do Sapucaí, Piranguinho')
        # NOVO: Define o link para abrir no Google Maps (não mais o embed)
        details.setdefault('party_location_url', 'http://googleusercontent.com/maps/search/EST%C3%82NCIA+NA+SERRA,+CASA+DE+TEMPORADA+Santa+B%C3%A1rbara+do+Sapuca%C3%AD,+Piranguinho')

        return details

    def allowed_file(filename, file_type='image'):
        """Verifica se a extensão do arquivo é permitida com base no tipo."""
        if file_type == 'image':
            return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}
        elif file_type == 'video':
            return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'mp4', 'mov', 'avi', 'wmv', 'flv', 'webm'}
        return False

    # --- ROTAS PÚBLICAS DA APLICAÇÃO ---

    @app.route("/")
    def home():
        return render_template("home.html")

    @app.route("/confirm/<token>")
    def confirm_presence(token):
        guest_group = Guest.query.filter_by(unique_token=token).first_or_404()
        members = guest_group.members
        
        confirmation_record = Confirmation.query.filter_by(guest_id=guest_group.id).first()
        already_confirmed = confirmation_record is not None and \
                            (any(m.is_confirmed for m in guest_group.members if not m.is_plus_one) or \
                             (confirmation_record.plus_one_name is not None and confirmation_record.plus_one_name != ''))

        invite_details = get_invite_details()
        
        # NOVO: Pega as fotos do local para exibir na página de confirmação
        venue_photos = VenuePhoto.query.order_by(VenuePhoto.order, VenuePhoto.upload_date.desc()).all()


        return render_template(
            "confirm.html",
            guest_group=guest_group,
            members=members,
            already_confirmed=already_confirmed,
            invite_details=invite_details,
            venue_photos=venue_photos # Passa as fotos do local para o template
        )

    @app.route("/confirm_presence_submit", methods=["POST"])
    def confirm_presence_submit():
        token = request.form.get("token")
        guest_group = Guest.query.filter_by(unique_token=token).first_or_404()

        confirmation = Confirmation.query.filter_by(guest_id=guest_group.id).first()
        if not confirmation:
            confirmation = Confirmation(guest_id=guest_group.id, timestamp=datetime.utcnow())
            db.session.add(confirmation)
            db.session.flush()

        is_first_submission_of_presence = not (any(m.is_confirmed for m in guest_group.members if not m.is_plus_one) or \
                                                (confirmation.plus_one_name is not None and confirmation.plus_one_name != ''))

        if is_first_submission_of_presence:
            confirmed_member_ids = request.form.getlist("members_confirmed")
            
            for member in guest_group.members:
                if not member.is_plus_one:
                    member.is_confirmed = False
            db.session.commit()

            for member_id in confirmed_member_ids:
                member = GuestMember.query.get(member_id)
                if member and member.guest_id == guest_group.id:
                    member.is_confirmed = True
            db.session.commit()

            plus_one_name = request.form.get("plus_one_name", "").strip()
            plus_one_member = GuestMember.query.filter_by(guest_id=guest_group.id, is_plus_one=True).first()

            if plus_one_name:
                if not plus_one_member:
                    plus_one_member = GuestMember(guest_id=guest_group.id, name=plus_one_name, is_plus_one=True, is_confirmed=True)
                    db.session.add(plus_one_member)
                else:
                    plus_one_member.name = plus_one_name
                    plus_one_member.is_confirmed = True
            elif plus_one_member:
                db.session.delete(plus_one_member)
            
            confirmation.plus_one_name = plus_one_name if plus_one_name else None
            db.session.commit()

            flash("Sua presença foi confirmada com sucesso! Agradecemos!", "success")
        else:
            flash('Sua presença já havia sido confirmada. Processando novos arquivos, se houver.', 'info')

        invite_details = get_invite_details()
        max_video_duration_seconds = invite_details.get('max_video_duration_seconds', 20)

        if 'photos' in request.files:
            for file in request.files.getlist('photos'):
                if file.filename == '':
                    continue
                if allowed_file(file.filename, 'image'):
                    filename_secure = secure_filename(file.filename)
                    unique_filename = f"{uuid.uuid4().hex}_{filename_secure}"
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                    try:
                        file.save(filepath)
                        new_photo = Photo(confirmation_id=confirmation.id, filename=unique_filename, upload_date=datetime.utcnow())
                        db.session.add(new_photo)
                        flash(f'Foto "{filename_secure}" enviada com sucesso!', 'success')
                    except Exception as e:
                        flash(f"Erro ao salvar foto {filename_secure}: {e}", 'danger')
                else:
                    flash(f"Tipo de arquivo não permitido para foto: {file.filename}", 'warning')

        if 'videos' in request.files:
            for file in request.files.getlist('videos'):
                if file.filename == '':
                    continue
                if allowed_file(file.filename, 'video'):
                    filename_secure = secure_filename(file.filename)
                    unique_filename = f"{uuid.uuid4().hex}_{filename_secure}"
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                    try:
                        file.save(filepath)
                        new_video = Video(confirmation_id=confirmation.id, filename=unique_filename, upload_date=datetime.utcnow(), duration_seconds=None)
                        db.session.add(new_video)
                        flash(f'Vídeo "{filename_secure}" enviado com sucesso!', 'success')
                    except Exception as e:
                        flash(f"Erro ao salvar vídeo {filename_secure}: {e}", 'danger')
                else:
                    flash(f"Tipo de arquivo não permitido para vídeo: {file.filename}", 'warning')
        
        db.session.commit()

        return redirect(url_for("confirm_presence", token=token))

    @app.route('/uploads/<filename>')
    def uploads(filename):
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

    @app.route('/download/<filename>')
    @admin_required
    def download_file(filename):
        try:
            return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)
        except FileNotFoundError:
            flash(f"Arquivo '{filename}' não encontrado.", 'danger')
            return redirect(url_for('admin_media'))
        except Exception as e:
            flash(f"Erro ao baixar arquivo: {e}", 'danger')
            return redirect(url_for('admin_dashboard'))

    # --- ROTAS DO PAINEL DE ADMINISTRAÇÃO ---

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if session.get('admin_logged_in'):
            return redirect(url_for('admin_dashboard'))

        if request.method == "POST":
            username = request.form.get("username")
            password = request.form.get("password")

            admin_user = AdminUser.query.filter_by(username=username).first()

            if admin_user and check_password_hash(admin_user.password_hash, password):
                session['admin_logged_in'] = True
                flash('Login de administrador bem-sucedido!', 'success')
                
                next_page = request.args.get('next')
                return redirect(next_page or url_for('admin_dashboard'))
            else:
                flash('Nome de usuário ou senha inválidos.', 'danger')
        return render_template("admin/login.html")

    @app.route("/admin/logout")
    @admin_required
    def admin_logout():
        session.pop('admin_logged_in', None)
        flash('Você foi desconectado.', 'info')
        return redirect(url_for('admin_login'))

    @app.route("/admin")
    @admin_required
    def admin_dashboard():
        total_guests = GuestMember.query.count()
        total_confirmed = GuestMember.query.filter_by(is_confirmed=True).count()
        total_unconfirmed = total_guests - total_confirmed

        total_plus_one = GuestMember.query.filter_by(is_plus_one=True, is_confirmed=True).count()

        total_guests_joint = GuestMember.query.join(Guest).filter(Guest.party_type == 'talita_joaquim').count()
        total_confirmed_joint = GuestMember.query.join(Guest).filter(Guest.party_type == 'talita_joaquim', GuestMember.is_confirmed == True).count()

        total_guests_talita = GuestMember.query.join(Guest).filter(Guest.party_type == 'talita_29_08').count()
        total_confirmed_talita = GuestMember.query.join(Guest).filter(Guest.party_type == 'talita_29_08', GuestMember.is_confirmed == True).count()

        total_photos = Photo.query.count()
        total_videos = Video.query.count()
        total_venue_photos = VenuePhoto.query.count() # NOVO: Contagem de fotos do local

        all_guest_groups = Guest.query.order_by(Guest.group_name).all()

        return render_template("admin/dashboard.html",
                               total_guests=total_guests,
                               total_confirmed=total_confirmed,
                               total_unconfirmed=total_unconfirmed,
                               total_plus_one=total_plus_one,
                               total_guests_joint=total_guests_joint,
                               total_confirmed_joint=total_confirmed_joint,
                               total_guests_talita=total_guests_talita,
                               total_confirmed_talita=total_confirmed_talita,
                               total_photos=total_photos,
                               total_videos=total_videos,
                               total_venue_photos=total_venue_photos, # NOVO: Passa a contagem de fotos do local
                               all_guest_groups=all_guest_groups
                               )

    @app.route("/admin/settings", methods=["GET", "POST"])
    @admin_required
    def admin_settings():
        invite_details = get_invite_details()

        if request.method == "POST":
            settings_to_update = {
                'welcome_title': request.form.get('welcome_title'),
                'welcome_message': request.form.get('welcome_message'),
                'party_date_talita_joaquim': request.form.get('party_date_talita_joaquim'),
                'party_date_other': request.form.get('party_date_other'),
                'party_location_name': request.form.get('party_location_name'),
                'party_location_url': request.form.get('party_location_url'), # NOVO: Campo para o link clicável
                'max_video_duration_seconds': request.form.get('max_video_duration_seconds'),
            }

            for key, value in settings_to_update.items():
                setting_obj = ConfigSetting.query.filter_by(key=key).first()
                if setting_obj:
                    setting_obj.value = value
                else:
                    setting_obj = ConfigSetting(key=key, value=value)
                    db.session.add(setting_obj)

            if 'main_photo_filename' in request.files:
                photo_file = request.files['main_photo_filename']
                if photo_file and photo_file.filename != '' and allowed_file(photo_file.filename, 'image'):
                    new_filename = secure_filename(f"{uuid.uuid4().hex}_{photo_file.filename}")
                    filepath = os.path.join(app.config['STATIC_FOLDER'], 'img', new_filename)

                    old_filename_setting = ConfigSetting.query.filter_by(key='main_photo_filename').first()
                    if old_filename_setting and old_filename_setting.value and \
                       old_filename_setting.value != 'sua_foto_do_aniversario.jpg':
                        try:
                            os.remove(os.path.join(app.config['STATIC_FOLDER'], 'img', old_filename_setting.value))
                        except OSError as e:
                            print(f"Erro ao deletar imagem antiga: {e}")

                    photo_file.save(filepath)
                    
                    setting_obj = ConfigSetting.query.filter_by(key='main_photo_filename').first()
                    if setting_obj:
                        setting_obj.value = new_filename
                    else:
                        db.session.add(ConfigSetting(key='main_photo_filename', value=new_filename))
                    flash('Foto principal do convite atualizada!', 'success')
                elif photo_file.filename != '':
                    flash('Nenhum arquivo de foto selecionado ou tipo de arquivo não permitido.', 'warning')

            if request.form.get('remove_main_photo') == 'true':
                setting_obj = ConfigSetting.query.filter_by(key='main_photo_filename').first()
                if setting_obj and setting_obj.value and setting_obj.value != 'sua_foto_do_aniversario.jpg':
                    try:
                        os.remove(os.path.join(app.config['STATIC_FOLDER'], 'img', setting_obj.value))
                        setting_obj.value = None
                        flash('Foto principal do convite removida.', 'info')
                    except OSError as e:
                        flash(f"Erro ao remover foto: {e}", 'danger')
                else:
                    flash('Nenhuma foto para remover ou foto é a padrão.', 'info')

            db.session.commit()
            flash('Configurações atualizadas com sucesso!', 'success')
            return redirect(url_for('admin_settings'))

        return render_template("admin/settings.html", invite_details=invite_details)

    @app.route("/admin/guests")
    @admin_required
    def admin_guests():
        guests = Guest.query.order_by(Guest.group_name).all()
        return render_template("admin/guests.html", guests=guests)

    @app.route("/admin/guests/add", methods=["GET", "POST"])
    @admin_required
    def admin_add_guest():
        if request.method == "POST":
            group_name = request.form.get("group_name")
            party_type = request.form.get("party_type")
            
            member_names_dynamic = request.form.getlist("member_name[]")
            is_confirmed_dynamic_checkboxes = request.form.getlist("is_confirmed[]") 

            plus_one_name = request.form.get("plus_one_name", "").strip()

            if not group_name or not party_type:
                flash('Nome do grupo e tipo de festa são obrigatórios.', 'danger')
                return render_template('admin/guest_form.html', guest=None, members=[], plus_one_name='', form_action='add')

            new_guest_group = Guest(group_name=group_name, party_type=party_type, unique_token=secrets.token_urlsafe(16))
            db.session.add(new_guest_group)
            db.session.commit()

            for i, name in enumerate(member_names_dynamic):
                if name.strip():
                    is_confirmed = (str(i) in is_confirmed_dynamic_checkboxes)
                    member = GuestMember(guest_id=new_guest_group.id, name=name.strip(), is_plus_one=False, is_confirmed=is_confirmed)
                    db.session.add(member)

            if plus_one_name:
                plus_one_member = GuestMember(guest_id=new_guest_group.id, name=plus_one_name, is_plus_one=True, is_confirmed=False)
                db.session.add(plus_one_member)

            new_confirmation = Confirmation(guest_id=new_guest_group.id, plus_one_name=plus_one_name if plus_one_name else None, timestamp=datetime.utcnow())
            db.session.add(new_confirmation)

            db.session.commit()
            flash(f'Grupo "{group_name}" adicionado com sucesso! Link: {url_for("confirm_presence", token=new_guest_group.unique_token, _external=True)}', 'success')
            return redirect(url_for('admin_guests'))

        return render_template("admin/guest_form.html", form_action='add', guest=None, members=[], plus_one_name='')

    @app.route("/admin/guests/edit/<int:guest_id>", methods=["GET", "POST"])
    @admin_required
    def admin_edit_guest(guest_id):
        guest = Guest.query.options(db.joinedload(Guest.members), db.joinedload(Guest.confirmations)).get_or_404(guest_id)
        confirmation = guest.confirmations[0] if guest.confirmations else None

        if request.method == "POST":
            guest.group_name = request.form.get("group_name")
            guest.party_type = request.form.get("party_type")

            submitted_member_ids = request.form.getlist("member_id[]")
            submitted_member_names = request.form.getlist("member_name[]")
            submitted_is_confirmed_checkboxes = request.form.getlist("is_confirmed[]")

            members_data_from_form = []
            for i, name_from_form in enumerate(submitted_member_names):
                if name_from_form.strip():
                    member_id_val = submitted_member_ids[i]
                    is_confirmed_val = (member_id_val in submitted_is_confirmed_checkboxes) # For existing members
                    if member_id_val.startswith('new_'): # For dynamically added new members
                        is_confirmed_val = (f"new_member_checkbox_{i}" in submitted_is_confirmed_checkboxes) # Check specific name for new ones
                    
                    members_data_from_form.append({
                        'id': int(member_id_val) if member_id_val.isdigit() else member_id_val,
                        'name': name_from_form.strip(),
                        'is_confirmed': is_confirmed_val
                    })
            
            current_main_members = [m for m in guest.members if not m.is_plus_one]
            for current_member_obj in current_main_members:
                found_in_form = False
                for form_member_data in members_data_from_form:
                    if form_member_data['id'] == current_member_obj.id:
                        found_in_form = True
                        break
                if not found_in_form:
                    db.session.delete(current_member_obj)

            for form_member_data in members_data_from_form:
                if isinstance(form_member_data['id'], int):
                    member_obj = next((m for m in current_main_members if m.id == form_member_data['id']), None)
                    if member_obj:
                        member_obj.name = form_member_data['name']
                        member_obj.is_confirmed = form_member_data['is_confirmed']
                else:
                    new_member = GuestMember(guest_id=guest.id, name=form_member_data['name'], is_plus_one=False, is_confirmed=form_member_data['is_confirmed'])
                    db.session.add(new_member)

            plus_one_name_from_form = request.form.get("plus_one_name", "").strip()
            plus_one_member_obj = next((m for m in guest.members if m.is_plus_one), None)

            if plus_one_name_from_form:
                if not plus_one_member_obj:
                    new_plus_one_member = GuestMember(guest_id=guest.id, name=plus_one_name_from_form, is_plus_one=True, is_confirmed=True)
                    db.session.add(new_plus_one_member)
                else:
                    plus_one_member_obj.name = plus_one_name_from_form
                    plus_one_member_obj.is_confirmed = True
            elif plus_one_member_obj:
                db.session.delete(plus_one_member_obj)

            if confirmation:
                confirmation.plus_one_name = plus_one_name_from_form if plus_one_name_from_form else None

            db.session.commit()
            flash(f'Grupo "{guest.group_name}" atualizado com sucesso!', 'success')
            return redirect(url_for('admin_guests'))

        members_for_form = [m for m in guest.members if not m.is_plus_one]
        plus_one_member_obj_get = GuestMember.query.filter_by(guest_id=guest.id, is_plus_one=True).first()
        current_plus_one_name = plus_one_member_obj_get.name if plus_one_member_obj_get else ''

        return render_template("admin/guest_form.html",
                               form_action='edit',
                               guest=guest,
                               members=members_for_form,
                               plus_one_name=current_plus_one_name)

    @app.route("/admin/guests/delete/<int:guest_id>", methods=["POST"])
    @admin_required
    def admin_delete_guest(guest_id):
        guest = Guest.query.get_or_404(guest_id)

        try:
            for confirmation_obj in guest.confirmations:
                for photo_obj in confirmation_obj.photos:
                    try:
                        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], photo_obj.filename))
                    except OSError:
                        pass
                for video_obj in confirmation_obj.videos:
                    try:
                        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], video_obj.filename))
                    except OSError:
                        pass
            
            db.session.delete(guest)
            db.session.commit()
            flash(f'Grupo "{guest.group_name}" e todos os dados associados excluídos com sucesso!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao excluir grupo: {e}', 'danger')
        return redirect(url_for('admin_guests'))

    @app.route("/admin/media")
    @admin_required
    def admin_media():
        photos = Photo.query.order_by(Photo.upload_date.desc()).all()
        videos = Video.query.order_by(Video.upload_date.desc()).all()
        return render_template("admin/media.html", photos=photos, videos=videos)

    @app.route("/admin/media/delete/<string:media_type>/<int:media_id>", methods=["POST"])
    @admin_required
    def admin_delete_media(media_type, media_id): # <-- ESTES SÃO OS NOMES CORRETOS DOS PARÂMETROS
        """Exclui uma mídia (foto ou vídeo) e seu arquivo."""
        media_item = None
        if media_type == 'photo':
            media_item = Photo.query.get_or_404(media_id)
        elif media_type == 'video':
            media_item = Video.query.get_or_404(media_id)
        else:
            flash('Tipo de mídia inválido.', 'danger')
            return redirect(url_for('admin_media'))

        try:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], media_item.filename)
            if os.path.exists(filepath):
                os.remove(filepath)
                flash(f'Arquivo "{media_item.filename}" removido do servidor.', 'info')
            else:
                flash(f'Arquivo "{media_item.filename}" não encontrado no servidor, mas o registro será removido.', 'warning')

            db.session.delete(media_item)
            db.session.commit()
            flash(f'{media_type.capitalize()} excluído(a) com sucesso do banco de dados!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao excluir mídia: {e}', 'danger')
        return redirect(url_for('admin_media'))


    # --- NOVO: Rotas para Gerenciamento de Fotos do Local (Venue Photos) ---
    @app.route("/admin/venue_photos")
    @admin_required
    def admin_venue_photos():
        """Lista e gerencia as fotos do local da festa."""
        photos = VenuePhoto.query.order_by(VenuePhoto.order, VenuePhoto.upload_date.desc()).all()
        return render_template("admin/venue_photos.html", photos=photos)

    @app.route("/admin/venue_photos/add", methods=["GET", "POST"])
    @admin_required
    def admin_add_venue_photo():
        """Adiciona uma nova foto do local."""
        if request.method == "POST":
            description = request.form.get("description", "").strip()
            order_str = request.form.get("order", "0").strip()
            order = int(order_str) if order_str.isdigit() else 0

            if 'photo_file' not in request.files:
                flash('Nenhum arquivo de foto selecionado.', 'danger')
                return redirect(url_for('admin_venue_photos'))
            
            file = request.files['photo_file']
            if file.filename == '':
                flash('Nenhum arquivo selecionado.', 'danger')
                return redirect(url_for('admin_venue_photos'))

            if file and allowed_file(file.filename, 'image'):
                filename_secure = secure_filename(f"{uuid.uuid4().hex}_{file.filename}")
                filepath = os.path.join(app.config['STATIC_FOLDER'], 'img', 'venue_photos', filename_secure)
                try:
                    file.save(filepath)
                    new_photo = VenuePhoto(filename=filename_secure, description=description, order=order, upload_date=datetime.utcnow())
                    db.session.add(new_photo)
                    db.session.commit()
                    flash('Foto do local adicionada com sucesso!', 'success')
                except Exception as e:
                    db.session.rollback()
                    flash(f"Erro ao adicionar foto do local: {e}", 'danger')
            else:
                flash('Tipo de arquivo não permitido para foto do local.', 'danger')
            
            return redirect(url_for('admin_venue_photos'))
        
        return render_template("admin/venue_photo_add.html") # Template para o formulário de adicionar foto

    @app.route("/admin/venue_photos/edit/<int:photo_id>", methods=["GET", "POST"])
    @admin_required
    def admin_edit_venue_photo(photo_id):
        """Edita a descrição e ordem de uma foto do local existente."""
        photo = VenuePhoto.query.get_or_404(photo_id)

        if request.method == "POST":
            photo.description = request.form.get("description", "").strip()
            order_str = request.form.get("order", "0").strip()
            photo.order = int(order_str) if order_str.isdigit() else 0
            
            # Não permite alterar o arquivo da foto por esta rota. Seria uma rota separada ou delete/re-upload.

            db.session.commit()
            flash('Foto do local atualizada com sucesso!', 'success')
            return redirect(url_for('admin_venue_photos'))
        
        return render_template("admin/venue_photo_edit.html", photo=photo)

    @app.route("/admin/venue_photos/delete/<int:photo_id>", methods=["POST"])
    @admin_required
    def admin_delete_venue_photo(photo_id):
        """Exclui uma foto do local e seu arquivo físico."""
        photo = VenuePhoto.query.get_or_404(photo_id)
        filepath = os.path.join(app.config['STATIC_FOLDER'], 'img', 'venue_photos', photo.filename)

        try:
            db.session.delete(photo)
            db.session.commit()
            if os.path.exists(filepath):
                os.remove(filepath)
                flash(f'Arquivo "{photo.filename}" removido do servidor.', 'info')
            else:
                flash(f'Arquivo "{photo.filename}" não encontrado no servidor, mas o registro foi removido.', 'warning')
            flash('Foto do local excluída com sucesso!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao excluir foto do local: {e}', 'danger')
        
        return redirect(url_for('admin_venue_photos'))


    # --- Rotas de Inicialização/Exemplo (apenas para desenvolvimento) ---
    # !!! ATENÇÃO: Essas rotas devem ser REMOVIDAS ou PROTEGIDAS em ambiente de PRODUÇÃO !!!

    @app.route("/create_db_and_admin")
    def create_db_and_admin():
        """
        Rota para criar todas as tabelas do banco de dados e um usuário administrador inicial.
        Também popula as configurações padrão do convite.
        DEVE SER EXECUTADA APENAS UMA VEZ.
        """
        with app.app_context():
            db.create_all()

            if not AdminUser.query.first():
                admin_username = os.environ.get('ADMIN_USERNAME', 'admin')
                admin_password = os.environ.get('ADMIN_PASSWORD', 'adminpass') # <<< MUDE ESTA SENHA EM PRODUÇÃO! >>>
                admin_email = os.environ.get('ADMIN_EMAIL', 'admin@example.com') 
                hashed_password = generate_password_hash(admin_password)
                
                default_admin = AdminUser(username=admin_username, password_hash=hashed_password, email=admin_email) 
                db.session.add(default_admin)
                db.session.commit()
                flash(f'Usuário admin padrão "{admin_username}" criado com sucesso! Senha: "{admin_password}". POR FAVOR, ALTERE A SENHA APÓS O PRIMEIRO LOGIN!', 'warning')
            else:
                flash('Usuário admin já existe. Não foi criado um novo.', 'info')

            default_settings_to_create = {
                'welcome_title': 'Celebre Conosco!',
                'welcome_message': 'Estamos muito felizes em<br />convidá-lo(a) para celebrar conosco!',
                'main_photo_filename': 'sua_foto_do_aniversario.jpg',
                'party_date_talita_joaquim': '30 de Agosto',
                'party_date_other': '29 de Agosto',
                'party_location_name': 'ESTÂNCIA NA SERRA, CASA DE TEMPORADA Santa Bárbara do Sapucaí, Piranguinho',
                'party_location_url': 'http://googleusercontent.com/maps/search/EST%C3%82NCIA+NA+SERRA,+CASA+DE+TEMPORADA+Santa+B%C3%A1rbara+do+Sapuca%C3%AD,+Piranguinho', # NOVO: URL padrão para o link clicável
                'max_video_duration_seconds': '20',
            }

            for key, value in default_settings_to_create.items():
                if not ConfigSetting.query.filter_by(key=key).first():
                    setting = ConfigSetting(key=key, value=value)
                    db.session.add(setting)
            
            # NOVO: Adiciona uma foto de exemplo para o local se não houver
            if not VenuePhoto.query.first():
                # Certifique-se de ter uma imagem chamada 'venue_placeholder.jpg' em static/img/venue_photos/
                # ou remova este bloco se não quiser uma foto padrão.
                if not os.path.exists(os.path.join(app.config['STATIC_FOLDER'], 'img', 'venue_photos', 'venue_placeholder.jpg')):
                    print("AVISO: Crie 'static/img/venue_photos/venue_placeholder.jpg' para a foto padrão do local.")
                    # Pode criar um arquivo dummy para evitar erro se quiser:
                    # with open(os.path.join(app.config['STATIC_FOLDER'], 'img', 'venue_photos', 'venue_placeholder.jpg'), 'w') as f: f.write("dummy")

                default_venue_photo = VenuePhoto(
                    filename='venue_placeholder.jpg',
                    description='Foto do local (placeholder)',
                    order=1
                )
                db.session.add(default_venue_photo)
                flash('Foto de local padrão adicionada. Altere-a no painel!', 'info')


            db.session.commit()
            flash('Setup inicial de banco de dados e admin concluído!', 'success')
        return redirect(url_for('home'))

    @app.route("/add_sample_guests")
    def add_sample_guests():
        """Adiciona alguns convidados de exemplo para testes. DEVE SER REMOVIDA EM PRODUÇÃO."""
        with app.app_context():
            if Guest.query.count() == 0: 
                guest1 = Guest(group_name='Família Silva', party_type='talita_joaquim', unique_token=secrets.token_urlsafe(16))
                guest2 = Guest(group_name='Amigos da Talita', party_type='talita_29_08', unique_token=secrets.token_urlsafe(16))
                guest3 = Guest(group_name='Família Santos', party_type='talita_joaquim', unique_token=secrets.token_urlsafe(16))

                db.session.add_all([guest1, guest2, guest3])
                db.session.commit()

                member1_1 = GuestMember(guest_id=guest1.id, name='João Silva', is_plus_one=False)
                member1_2 = GuestMember(guest_id=guest1.id, name='Maria Silva', is_plus_one=False)
                member1_3 = GuestMember(guest_id=guest1.id, name='Pedrinho Silva', is_plus_one=False)
                db.session.add_all([member1_1, member1_2, member1_3])

                member2_1 = GuestMember(guest_id=guest2.id, name='Ana Paula', is_plus_one=False)
                member2_2 = GuestMember(guest_id=guest2.id, name='Carlos Eduardo', is_plus_one=False)
                db.session.add_all([member2_1, member2_2])

                member3_1 = GuestMember(guest_id=guest3.id, name='Roberto Santos', is_plus_one=False)
                member3_2 = GuestMember(guest_id=guest3.id, name='Carla Santos', is_plus_one=False)
                db.session.add_all([member3_1, member3_2])

                db.session.add(Confirmation(guest_id=guest1.id, timestamp=datetime.utcnow()))
                db.session.add(Confirmation(guest_id=guest2.id, timestamp=datetime.utcnow()))
                db.session.add(Confirmation(guest_id=guest3.id, timestamp=datetime.utcnow()))

                db.session.commit()
                flash('Convidados de exemplo adicionados com sucesso!', 'success')
            else:
                flash('Convidados de exemplo já existem no banco de dados. Não foram adicionados novos.', 'info')
            
            guests_for_links = Guest.query.all()
            guest_links_html = []
            for guest in guests_for_links:
                guest_links_html.append(f"<li><a href='{url_for('confirm_presence', token=guest.unique_token, _external=True)}'>{guest.group_name} (Festa: {guest.party_type})</a></li>")
            
            flash(f'Links gerados para convidados de teste: <ul>{"".join(guest_links_html)}</ul>', 'info')

        return redirect(url_for('home'))

    return app # Retorna a instância do aplicativo configurado

# --- EXECUÇÃO DO APLICATIVO (Entry Point) ---
if __name__ == "__main__":
    app = create_app() # Chama a função de fábrica para criar e configurar o app
    app.run() # Inicia o servidor Flask em modo debug