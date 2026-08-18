"""
Moduł obsługujący endpointy API dla konfiguracji SMTP, testowania połączenia e-mail oraz wysyłania raportów.
"""
from flask import jsonify, request, session, current_app
from app.decorators import login_required
from app.services.email_service import EmailService
from app.repositories.user_email_settings_repository import UserEmailSettingsRepository

email_service = EmailService()
settings_repo = UserEmailSettingsRepository()


def register_api_email_routes(api_bp):

    @api_bp.route('/email/test', methods=['POST'])
    @login_required
    def test_email_connection():
        """Testuje nawiązanie połączenia SMTP z podanymi parametrami."""
        data = request.get_json(silent=True) or request.form
        smtp_server = data.get('smtp_server') or 'smtp.wp.pl'
        smtp_port = data.get('smtp_port') or 465
        smtp_security = data.get('smtp_security') or 'SSL'
        smtp_username = data.get('smtp_username')
        smtp_password = data.get('smtp_password')

        if not smtp_username or not smtp_password:
            return jsonify({'success': False, 'message': 'Wymagany jest login oraz hasło e-mail.'}), 400

        success, message = email_service.test_connection(
            smtp_server=smtp_server,
            smtp_port=smtp_port,
            smtp_security=smtp_security,
            smtp_username=smtp_username,
            smtp_password=smtp_password
        )
        return jsonify({'success': success, 'message': message})

    @api_bp.route('/email/config', methods=['GET', 'POST'])
    @login_required
    def user_email_config():
        """Pobiera lub zapisuje indywidualne ustawienia SMTP użytkownika."""
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'message': 'Brak identyfikatora użytkownika w sesji.'}), 401

        if request.method == 'GET':
            config = settings_repo.get_by_user_id(user_id)
            if config:
                return jsonify({
                    'success': True,
                    'is_custom': True,
                    'smtp_server': config.smtp_server,
                    'smtp_port': config.smtp_port,
                    'smtp_security': config.smtp_security,
                    'smtp_username': config.smtp_username,
                    'sender_name': config.sender_name or ''
                })
            else:
                default_info = email_service.get_smtp_config_for_user(None)
                return jsonify({
                    'success': True,
                    'is_custom': False,
                    'smtp_server': default_info['server'],
                    'smtp_port': default_info['port'],
                    'smtp_security': default_info['security'],
                    'smtp_username': default_info['username'],
                    'sender_name': default_info['sender_name']
                })

        # POST - Zapis nowych ustawień
        data = request.get_json(silent=True) or request.form
        smtp_server = (data.get('smtp_server') or 'smtp.wp.pl').strip()
        smtp_port = data.get('smtp_port') or 465
        smtp_security = (data.get('smtp_security') or 'SSL').strip().upper()
        smtp_username = (data.get('smtp_username') or '').strip()
        smtp_password = (data.get('smtp_password') or '').strip()
        sender_name = (data.get('sender_name') or '').strip()

        if not smtp_username or not smtp_password:
            return jsonify({'success': False, 'message': 'Nazwa użytkownika (e-mail) i hasło są wymagane.'}), 400

        # Weryfikacja połączenia przed zapisem
        test_ok, test_msg = email_service.test_connection(
            smtp_server=smtp_server,
            smtp_port=smtp_port,
            smtp_security=smtp_security,
            smtp_username=smtp_username,
            smtp_password=smtp_password
        )

        if not test_ok:
            return jsonify({'success': False, 'message': f"Zapis odrzucony. {test_msg}"}), 400

        saved = settings_repo.save_or_update(
            user_id=user_id,
            smtp_server=smtp_server,
            smtp_port=smtp_port,
            smtp_security=smtp_security,
            smtp_username=smtp_username,
            smtp_password=smtp_password,
            sender_name=sender_name
        )

        return jsonify({'success': True, 'message': '✅ Ustawienia konta e-mail zostały zapisane!', 'username': saved.smtp_username})

    @api_bp.route('/email/send_report', methods=['POST'])
    @login_required
    def send_report_email_endpoint():
        """Wysyła wiadomość z raportem do podanych odbiorców."""
        data = request.get_json(silent=True) or request.form
        raw_to = data.get('to_emails') or ''

        if isinstance(raw_to, str):
            to_emails = [e.strip() for e in raw_to.replace(';', ',').split(',') if e.strip()]
        else:
            to_emails = [str(e).strip() for e in raw_to if str(e).strip()]

        if not to_emails:
            return jsonify({'success': False, 'message': 'Proszę podać co najmniej jeden adres e-mail odbiorcy.'}), 400

        subject = (data.get('subject') or 'Raport Produkcyjny AGRO').strip()
        body_html = data.get('body_html') or f"<p>Dzień dobry,</p><p>W załączeniu przesyłam raport z aplikacji Raport Produkcyjny.</p><p>Zgłaszający: <strong>{session.get('imie_nazwisko') or session.get('login')}</strong></p>"

        user_id = session.get('user_id')
        success, message = email_service.send_report_email(
            to_emails=to_emails,
            subject=subject,
            body_html=body_html,
            user_id=user_id
        )

        return jsonify({'success': success, 'message': message})
