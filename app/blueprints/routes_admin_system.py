from flask import flash, jsonify, redirect, render_template, request, url_for

from app.db import get_active_database_name, get_runtime_switchable_databases, set_active_database_name
from app.decorators import admin_required, dynamic_role_required, masteradmin_required


def register_admin_system_routes(admin_bp, *, list_online_users):
    @admin_bp.route('/admin')
    @admin_required
    def admin_panel():
        """Redirect legacy admin panel to the new modern settings dashboard."""
        return redirect(url_for('admin.admin_ustawienia'))

    @admin_bp.route('/admin/users')
    @admin_required
    def admin_users():
        """Redirect legacy users management to the new modern settings dashboard."""
        return redirect(url_for('admin.admin_ustawienia_uzytkownicy'))

    @admin_bp.route('/admin/centrum')
    @dynamic_role_required('centrum')
    def admin_centrum_systemowe():
        return render_template('centrum_index.html')

    @admin_bp.route('/admin/centrum/audyt')
    @dynamic_role_required('centrum')
    def admin_centrum_audyt():
        from app.services.agro_warehouse_service import AgroWarehouseService

        linia = request.args.get('linia', 'Agro')
        history = AgroWarehouseService.get_history(limit=50, linia=linia)
        return render_template('centrum_audyt.html', history=history)

    @admin_bp.route('/admin/centrum/visual-inspector')
    @dynamic_role_required('centrum')
    def admin_visual_inspector():
        return render_template('admin/visual_inspector.html')

    @admin_bp.route('/admin/ustawienia')
    @dynamic_role_required('ustawienia')
    def admin_ustawienia():
        return render_template('ustawienia_index.html')

    @admin_bp.route('/admin/sekretna-baza')
    @dynamic_role_required('baza_danych')
    def admin_secret_db():
        current_db = get_active_database_name()
        allowed_databases = get_runtime_switchable_databases()
        return render_template(
            'admin/sekretna_baza.html',
            current_db=current_db,
            allowed_databases=allowed_databases,
        )

    @admin_bp.route('/admin/sekretna-baza/switch', methods=['POST'])
    @admin_required
    def admin_secret_db_switch():
        target_db = (request.form.get('database') or '').strip()
        previous_db = get_active_database_name()
        try:
            selected_db = set_active_database_name(target_db, verify_connection=True)
            flash(f'PrzeĹ‚Ä…czono bazÄ™: {previous_db} â†’ {selected_db}', 'success')
        except ValueError as error:
            flash(str(error), 'error')
        except Exception as error:
            flash(f'Nie udaĹ‚o siÄ™ przeĹ‚Ä…czyÄ‡ bazy na {target_db}: {error}', 'error')
        return redirect(url_for('admin.admin_secret_db'))

    @admin_bp.route('/admin/ustawienia/zalogowani')
    @dynamic_role_required('ustawienia')
    def admin_ustawienia_zalogowani():
        online_users = list_online_users(active_within_minutes=30)
        return render_template('ustawienia_zalogowani.html', online_users=online_users, active_window_minutes=30)

    @admin_bp.route('/admin/api/save-ui-overrides', methods=['POST'])
    @dynamic_role_required('ustawienia')
    def admin_save_ui_overrides():
        import os
        from flask import current_app
        data = request.get_json(silent=True) or {}
        css_content = data.get('css', '')
        
        # Ensure we don't write malicious files
        css_path = os.path.join(current_app.static_folder, 'css', 'custom_overrides.css')
        try:
            with open(css_path, 'w', encoding='utf-8') as f:
                f.write(css_content)
            return jsonify({'success': True, 'message': 'Ustawienia wizualne zostaĹ‚y zapisane na staĹ‚e!'})
        except Exception as e:
            return jsonify({'success': False, 'message': f'BĹ‚Ä…d zapisu: {str(e)}'}), 500

    @admin_bp.route('/admin/api/clear-ui-overrides', methods=['POST'])
    @dynamic_role_required('ustawienia')
    def admin_clear_ui_overrides():
        import os
        from flask import current_app
        css_path = os.path.join(current_app.static_folder, 'css', 'custom_overrides.css')
        try:
            with open(css_path, 'w', encoding='utf-8') as f:
                f.write('/* AGRO UI Overrides - Cleared */\n')
            return jsonify({'success': True, 'message': 'Wszystkie zmiany zostaĹ‚y usuniÄ™te!'})
        except Exception as e:
            return jsonify({'success': False, 'message': f'BĹ‚Ä…d: {str(e)}'}), 500

    @admin_bp.route('/admin/api/online-users')
    @dynamic_role_required('ustawienia')
    def admin_online_users_api():
        online_users = list_online_users(active_within_minutes=30)
        result = []
        for row in online_users:
            logged_in_at = row.get('logged_in_at')
            last_seen = row.get('last_seen')
            result.append(
                {
                    'session_id': row.get('session_id'),
                    'user_id': row.get('user_id'),
                    'login': row.get('login'),
                    'rola': row.get('rola'),
                    'display_name': row.get('display_name') or row.get('login'),
                    'ip_address': row.get('ip_address') or '',
                    'last_path': row.get('last_path') or '',
                    'logged_in_at': logged_in_at.strftime('%Y-%m-%d %H:%M:%S') if logged_in_at else '',
                    'last_seen': last_seen.strftime('%Y-%m-%d %H:%M:%S') if last_seen else '',
                    'idle_seconds': int(row.get('idle_seconds') or 0),
                    'is_active': bool(row.get('is_active')),
                }
            )
        return jsonify({'success': True, 'online_users': result, 'active_window_minutes': 30})
    @admin_bp.route('/admin/api/printer-server/status')
    @dynamic_role_required('ustawienia')
    def admin_printer_server_status():
        import requests
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        try:
            resp = requests.get('https://127.0.0.1:3001/status', timeout=1.5, verify=False)
            if resp.status_code == 200:
                return jsonify({'success': True, 'running': True, 'message': 'Serwer druku działa.'})
        except Exception:
            pass
        return jsonify({'success': True, 'running': False, 'message': 'Serwer druku jest wyłączony.'})

    @admin_bp.route('/admin/api/printer-server/start', methods=['POST'])
    @dynamic_role_required('ustawienia')
    def admin_printer_server_start():
        import subprocess
        import sys
        import os
        import time

        server_path = os.path.abspath(os.path.join(os.getcwd(), 'printer_server', 'server.py'))
        if not os.path.exists(server_path):
            return jsonify({'success': False, 'message': f'Nie znaleziono pliku serwera: {server_path}'}), 404

        try:
            creation_flags = 0
            if os.name == 'nt':
                creation_flags = 0x00000010

            subprocess.Popen([sys.executable, server_path], cwd=os.path.dirname(server_path), creationflags=creation_flags, start_new_session=True)
            time.sleep(1.5)
            return jsonify({'success': True, 'message': 'Wysłano polecenie startu serwera druku.'})
        except Exception as e:
            return jsonify({'success': False, 'message': f'Błąd startu: {str(e)}'}), 500
