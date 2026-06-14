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

    @admin_bp.route('/admin/ustawienia/qr-generator')
    @dynamic_role_required('ustawienia')
    def admin_qr_generator():
        """Generator kodów QR dla loginów i haseł."""
        return render_template('qr_generator.html')

    @admin_bp.route('/admin/ustawienia/qr-generator/drukuj', methods=['POST'])
    @dynamic_role_required('ustawienia')
    def admin_qr_generator_drukuj():
        """Wydrukuj małą etykietę QR z loginem i hasłem na drukarce Zebra ZPL."""
        try:
            data = request.get_json(silent=True) or {}
            login = str(data.get('login', '')).strip()
            password = str(data.get('password', '')).strip()
            format_type = str(data.get('format', 'simple')).strip()

            if not login or not password:
                return jsonify({'success': False, 'message': 'Brak loginu lub hasła'}), 400

            # Przygotuj dane QR
            if format_type == 'json':
                import json
                qr_data = json.dumps({'login': login, 'pass': password})
            else:
                qr_data = f"LOGIN:{login}:{password}"

            # Zbuduj ZPL dla małej etykiety QR (1cm x 1cm)
            from app.services.print_server import get_printer
            printer = get_printer()
            zpl = printer.build_login_qr_label_zpl(qr_data, login)

            # Wyślij do drukarki
            ok, msg = printer.print_zpl_label(zpl)

            if ok:
                return jsonify({
                    'success': True,
                    'message': 'Etykieta wysłana do drukarki Zebra',
                    'printer_name': printer.printer_name,
                    'printer_ip': printer.printer_ip
                })
            else:
                return jsonify({
                    'success': False,
                    'message': f'Błąd druku: {msg}'
                }), 500
        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'Wyjątek: {str(e)}'
            }), 500

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
        from flask import session
        from datetime import datetime
        target_db = (request.form.get('database') or '').strip()
        previous_db = get_active_database_name()
        
        session_id = session.get('session_tracking_id')
        session_row = None
        user_row = None
        pracownik_row = None
        
        user_id = session.get('user_id')
        if session_id or user_id:
            conn = None
            try:
                conn = get_db_connection()
                cursor = conn.cursor(dictionary=True)
                if session_id:
                    cursor.execute(
                        "SELECT user_id, login, rola, pracownik_id, display_name, ip_address, last_path, logged_in_at, last_seen, is_active FROM aktywne_sesje WHERE session_id = %s",
                        (session_id,)
                    )
                    session_row = cursor.fetchone()
                
                # Fetch user record to prevent foreign key errors on target database
                u_id = (session_row.get('user_id') if session_row else None) or user_id
                if u_id:
                    cursor.execute("SELECT id, login, haslo, rola, pracownik_id, grupa FROM uzytkownicy WHERE id = %s", (u_id,))
                    user_row = cursor.fetchone()
                    if user_row and user_row.get('pracownik_id'):
                        cursor.execute("SELECT id, imie_nazwisko FROM pracownicy WHERE id = %s", (user_row['pracownik_id'],))
                        pracownik_row = cursor.fetchone()
                
                cursor.close()
                conn.close()
            except Exception as e:
                if conn:
                    try: conn.close()
                    except Exception: pass

        try:
            selected_db = set_active_database_name(target_db, verify_connection=True)
            
            # Replicate user context to the new database to satisfy foreign key constraints
            if user_id or user_row:
                conn = None
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    
                    if pracownik_row:
                        cursor.execute("SELECT id FROM pracownicy WHERE id = %s", (pracownik_row['id'],))
                        if not cursor.fetchone():
                            cursor.execute(
                                "INSERT INTO pracownicy (id, imie_nazwisko) VALUES (%s, %s)",
                                (pracownik_row['id'], pracownik_row['imie_nazwisko'])
                            )
                            
                    if user_row:
                        cursor.execute("SELECT id FROM uzytkownicy WHERE id = %s", (user_row['id'],))
                        if not cursor.fetchone():
                            cursor.execute(
                                "INSERT INTO uzytkownicy (id, login, haslo, rola, pracownik_id, grupa) VALUES (%s, %s, %s, %s, %s, %s)",
                                (user_row['id'], user_row['login'], user_row['haslo'], user_row['rola'], user_row['pracownik_id'], user_row['grupa'])
                            )
                        else:
                            cursor.execute(
                                "UPDATE uzytkownicy SET login = %s, haslo = %s, rola = %s, pracownik_id = %s, grupa = %s WHERE id = %s",
                                (user_row['login'], user_row['haslo'], user_row['rola'], user_row['pracownik_id'], user_row['grupa'], user_row['id'])
                            )
                    
                    conn.commit()
                    cursor.close()
                    conn.close()
                except Exception as e:
                    print(f"[WARN] Failed to replicate user context to {target_db}: {e}")
                    if conn:
                        try: conn.rollback(); conn.close()
                        except Exception: pass

            # Copy active session to the new database to prevent session invalidation / automatic logout
            if session_id:
                u_id = (session_row.get('user_id') if session_row else None) or session.get('user_id')
                u_login = (session_row.get('login') if session_row else None) or session.get('login')
                u_rola = (session_row.get('rola') if session_row else None) or session.get('rola')
                u_prac = (session_row.get('pracownik_id') if session_row else None) or session.get('pracownik_id')
                u_name = (session_row.get('display_name') if session_row else None) or session.get('imie_nazwisko') or u_login
                u_ip = (session_row.get('ip_address') if session_row else None) or request.remote_addr
                u_path = (session_row.get('last_path') if session_row else None) or request.path
                u_logged = (session_row.get('logged_in_at') if session_row else None) or datetime.now()
                u_seen = (session_row.get('last_seen') if session_row else None) or datetime.now()
                u_active = (session_row.get('is_active') if session_row else 1)
                
                conn = None
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO aktywne_sesje 
                        (session_id, user_id, login, rola, pracownik_id, display_name, ip_address, last_path, logged_in_at, last_seen, is_active)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE 
                        is_active = VALUES(is_active),
                        last_seen = VALUES(last_seen),
                        last_path = VALUES(last_path),
                        ip_address = VALUES(ip_address)
                    """, (
                        session_id,
                        u_id,
                        u_login,
                        u_rola,
                        u_prac,
                        u_name,
                        u_ip,
                        u_path,
                        u_logged,
                        u_seen,
                        u_active
                    ))
                    conn.commit()
                    cursor.close()
                    conn.close()
                except Exception as e:
                    import traceback
                    print("[ERROR] Failed to copy active session to target database:")
                    traceback.print_exc()
                    if conn:
                        try: conn.rollback(); conn.close()
                        except Exception: pass
            
            flash(f'Przełączono bazę: {previous_db} → {selected_db}', 'success')
        except ValueError as error:
            flash(str(error), 'error')
        except Exception as error:
            flash(f'Nie udało się przełączyć bazy na {target_db}: {error}', 'error')
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

    @admin_bp.route('/admin/api/diagnostics/instances')
    @dynamic_role_required('ustawienia')
    def admin_instance_diagnostics_api():
        from app.db import get_db_connection
        from app.core.daemon import get_instance_identity

        conn = get_db_connection()
        rows = []
        message = ''
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT
                    instance_id,
                    hostname,
                    pid,
                    component,
                    status,
                    started_at,
                    last_heartbeat,
                    extra,
                    TIMESTAMPDIFF(SECOND, last_heartbeat, NOW()) AS heartbeat_age_s
                FROM app_instance_heartbeat
                ORDER BY last_heartbeat DESC
                LIMIT 200
                """
            )
            rows = cursor.fetchall() or []
            for row in rows:
                age = int(row.get('heartbeat_age_s') or 0)
                row['is_online'] = age <= 30
                for field in ('started_at', 'last_heartbeat'):
                    value = row.get(field)
                    if hasattr(value, 'strftime'):
                        row[field] = value.strftime('%Y-%m-%d %H:%M:%S')
        except Exception as e:
            message = f'Brak danych heartbeat: {e}'
        finally:
            conn.close()

        return jsonify(
            {
                'success': True,
                'local_instance': get_instance_identity(),
                'instances': rows,
                'message': message,
            }
        )

    @admin_bp.route('/admin/api/printer-server/status')
    @dynamic_role_required('ustawienia')
    def admin_printer_server_status():
        import os
        import requests
        import urllib3
        from urllib.parse import urlparse

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        base_value = str(os.getenv('PRINTER_BRIDGE_URL', 'http://127.0.0.1:3001') or '').strip().rstrip('/')
        if base_value.lower().endswith('/drukuj-zpl'):
            base_value = base_value[:-11]
        elif base_value.lower().endswith('/status'):
            base_value = base_value[:-7]
        if '://' not in base_value:
            base_value = f'https://{base_value}'

        candidates = []

        def _append(candidate):
            value = str(candidate or '').strip().rstrip('/')
            if not value:
                return
            if value.lower() in {item.lower() for item in candidates}:
                return
            candidates.append(value)

        _append(base_value)
        parsed = urlparse(base_value)
        scheme = (parsed.scheme or '').lower()
        if scheme in ('http', 'https'):
            alt_scheme = 'http' if scheme == 'https' else 'https'
            _append(f"{alt_scheme}://{parsed.netloc}{parsed.path or ''}")

        for bridge_base in candidates:
            try:
                resp = requests.get(f'{bridge_base}/status', timeout=1.5, verify=False)
                if resp.status_code == 200:
                    return jsonify({'success': True, 'running': True, 'message': 'Serwer druku działa.'})
            except Exception:
                continue

        return jsonify({'success': True, 'running': False, 'message': 'Serwer druku jest wyłączony.'})

    @admin_bp.route('/admin/api/printer-server/start', methods=['POST'])
    @dynamic_role_required('ustawienia')
    def admin_printer_server_start():
        import subprocess
        import sys
        import os
        import time

        # os.path.dirname(__file__) is app/blueprints/admin
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
        server_path = os.path.join(project_root, 'printer_server', 'server.py')
        
        if not os.path.exists(server_path):
            return jsonify({'success': False, 'message': f'Nie znaleziono pliku serwera: {server_path}'}), 404

        try:
            creation_flags = 0
            show_console = str(os.getenv('PRINTER_SERVER_SHOW_CONSOLE', 'false')).strip().lower() in ('1', 'true', 'yes')
            if os.name == 'nt' and show_console:
                creation_flags = 0x00000010

            env = os.environ.copy()
            env.pop('WERKZEUG_SERVER_FD', None)
            env.pop('WERKZEUG_RUN_MAIN', None)

            subprocess.Popen(
                [sys.executable, server_path],
                cwd=os.path.dirname(server_path),
                creationflags=creation_flags,
                start_new_session=True,
                env=env,
            )
            time.sleep(1.5)
            return jsonify({'success': True, 'message': 'Wysłano polecenie startu serwera druku.'})
        except Exception as e:
            return jsonify({'success': False, 'message': f'Błąd startu: {str(e)}'}), 500

    @admin_bp.route('/admin/ustawienia/drukarki')
    @dynamic_role_required('ustawienia')
    def admin_ustawienia_drukarki():
        from app.db import get_db_connection
        conn = get_db_connection()
        printers = []
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM drukarki ORDER BY id ASC")
            printers = cursor.fetchall()
        except Exception as e:
            flash(f"Błąd pobierania drukarek: {e}", "error")
        finally:
            conn.close()
        return render_template('ustawienia_drukarki.html', printers=printers)

    @admin_bp.route('/admin/ustawienia/drukarki-biurowe')
    @dynamic_role_required('ustawienia')
    def admin_ustawienia_drukarki_biurowe():
        from app.db import get_db_connection
        
        # Fetch system printers
        system_printers = []
        try:
            import win32print
            system_printers = [p[2] for p in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)]
        except ImportError:
            # We are on Linux or win32print is not installed
            import subprocess
            try:
                # Try to list printers on Linux using lpstat
                result = subprocess.run(['lpstat', '-p'], capture_output=True, text=True)
                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        if line.startswith('printer '):
                            parts = line.split(' ')
                            if len(parts) >= 2:
                                system_printers.append(parts[1])
            except Exception:
                pass
        except Exception as e:
            flash(f"Błąd pobierania drukarek z systemu: {e}", "warning")
            
        # Fetch report assignments
        conn = get_db_connection()
        assignments = []
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM przypisania_raportow ORDER BY id ASC")
            assignments = cursor.fetchall()
        except Exception as e:
            flash(f"Błąd bazy danych: {e}", "error")
        finally:
            conn.close()
            
        return render_template('ustawienia_drukarki_biurowe.html', system_printers=system_printers, assignments=assignments)

    @admin_bp.route('/admin/ustawienia/drukarki-biurowe/zapisz', methods=['POST'])
    @dynamic_role_required('ustawienia')
    def admin_ustawienia_drukarki_biurowe_zapisz():
        from app.db import get_db_connection
        data = request.form
        
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            # In order to handle multiple assignments from the form, we can iterate over them.
            # Assuming form sends arrays or specific names like: printer_raport_palet_agro, active_raport_palet_agro
            cursor.execute("SELECT typ_raportu FROM przypisania_raportow")
            for row in cursor.fetchall():
                typ_rap = row[0]
                nazwa_drukarki = data.get(f'printer_{typ_rap}', '')
                aktywne = 1 if data.get(f'active_{typ_rap}') else 0
                cursor.execute(
                    "UPDATE przypisania_raportow SET nazwa_drukarki = %s, aktywne = %s WHERE typ_raportu = %s",
                    (nazwa_drukarki, aktywne, typ_rap)
                )
            conn.commit()
            flash("Zapisano przypisania drukarek biurowych.", "success")
        except Exception as e:
            flash(f"Błąd zapisu: {e}", "error")
        finally:
            conn.close()
            
        return redirect(url_for('admin.admin_ustawienia_drukarki_biurowe'))

    @admin_bp.route('/admin/ustawienia/drukarki/add', methods=['POST'])
    @dynamic_role_required('ustawienia')
    def admin_add_printer():
        nazwa = request.form.get('nazwa', '').strip()
        ip = request.form.get('ip', '').strip()
        lokalizacja = request.form.get('lokalizacja', '').strip()
        typ_drukarki = request.form.get('typ_drukarki', 'etykiet').strip()
        aktywna = 1 if request.form.get('aktywna') else 0
        
        if not nazwa or not ip:
            flash("Nazwa i adres IP są wymagane.", "error")
            return redirect(url_for('admin.admin_ustawienia_drukarki'))
            
        from app.db import get_db_connection
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO drukarki (nazwa, ip, lokalizacja, aktywna, typ_drukarki) VALUES (%s, %s, %s, %s, %s)",
                (nazwa, ip, lokalizacja, aktywna, typ_drukarki)
            )
            conn.commit()
            flash(f"Dodano drukarkę: {nazwa}", "success")
        except Exception as e:
            flash(f"Błąd podczas dodawania drukarki: {e}", "error")
        finally:
            conn.close()
            
        return redirect(url_for('admin.admin_ustawienia_drukarki'))

    @admin_bp.route('/admin/ustawienia/drukarki/delete/<int:printer_id>', methods=['POST'])
    @dynamic_role_required('ustawienia')
    def admin_delete_printer(printer_id):
        from app.db import get_db_connection
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM drukarki WHERE id = %s", (printer_id,))
            conn.commit()
            flash("Drukarka została usunięta.", "success")
        except Exception as e:
            flash(f"Błąd podczas usuwania drukarki: {e}", "error")
        finally:
            conn.close()
            
        return redirect(url_for('admin.admin_ustawienia_drukarki'))

    @admin_bp.route('/admin/zpl-test', methods=['GET', 'POST'])
    @masteradmin_required
    def admin_zpl_test():
        from flask import render_template_string
        import socket
        
        HTML_TEST_PAGE = """
        <html>
            <head>
                <title>Zebra ZPL Test</title>
                <style>
                    body { font-family: sans-serif; padding: 20px; }
                    table { border-collapse: collapse; width: 100%; max-width: 800px; margin-top: 20px; }
                    th, td { border: 1px solid #ccc; padding: 10px; text-align: left; }
                    th { background-color: #f4f4f4; }
                    button { padding: 8px 16px; cursor: pointer; background-color: #007bff; color: white; border: none; border-radius: 4px; }
                    button:hover { background-color: #0056b3; }
                    .pdf-section { margin-top: 30px; padding: 20px; border: 2px dashed #007bff; border-radius: 8px; max-width: 800px; background-color: #f8fbff; }
                </style>
            </head>
            <body>
                <h1>Test Drukarki Zebra (ZPL i PDF)</h1>
                <p>Ustaw IP drukarki docelowej, a następnie kliknij "Drukuj" obok wybranej palety (ZPL) lub prześlij plik PDF (Direct PDF).</p>
                
                <form action="{{ url_for('admin.admin_zpl_test') }}" method="POST" id="printForm" enctype="multipart/form-data">
                    <label><strong>Drukarka (IP):</strong></label><br>
                    <input type="text" name="ip" id="printer_ip" value="192.168.0.44" style="padding: 8px; width: 250px; font-size: 16px;"><br><br>
                    <input type="hidden" name="dane" id="zpl_data" value="">
                    
                    <div class="pdf-section">
                        <h3 style="margin-top: 0;">Wgraj i wydrukuj plik PDF (Opcja Direct PDF)</h3>
                        <p style="font-size: 0.9em; color: #666;">Jeśli Twoja drukarka wspiera funkcję PDF Direct (port 9100), możesz wysłać plik PDF bezpośrednio.</p>
                        <input type="file" name="pdf_file" accept=".pdf" style="padding: 10px 0;">
                        <br><br>
                        <button type="button" onclick="drukujPdf()" style="background-color: #28a745;">Wyślij PDF do Drukarki</button>
                    </div>
                </form>

                <table>
                    <tr>
                        <th>Paleta</th>
                        <th>Akcja (Wyślij ZPL)</th>
                    </tr>
                    <tr>
                        <td><strong>Paleta 1</strong> - Mleko W Proszku</td>
                        <td><button type="button" onclick="drukuj('^XA^FO50,50^A0N,50,50^FDTEST ZEBRA - MLEKO W PROSZKU^FS^XZ')">Drukuj ZPL</button></td>
                    </tr>
                    <tr>
                        <td><strong>Paleta 2</strong> - Cukier Kryształ</td>
                        <td><button type="button" onclick="drukuj('^XA^FO50,50^A0N,50,50^FDTEST ZEBRA - CUKIER KRYSZTAL^FS^XZ')">Drukuj ZPL</button></td>
                    </tr>
                    <tr>
                        <td><strong>Paleta 3</strong> - Serwatka</td>
                        <td><button type="button" onclick="drukuj('^XA^FO50,50^A0N,50,50^FDTEST ZEBRA - SERWATKA^FS^XZ')">Drukuj ZPL</button></td>
                    </tr>
                    <tr>
                        <td><strong>Paleta 4</strong> - Kakao</td>
                        <td><button type="button" onclick="drukuj('^XA^FO50,50^A0N,50,50^FDTEST ZEBRA - KAKAO^FS^XZ')">Drukuj ZPL</button></td>
                    </tr>
                    <tr>
                        <td><strong>Paleta 5</strong> - Mąka Pszenna</td>
                        <td><button type="button" onclick="drukuj('^XA^FO50,50^A0N,50,50^FDTEST ZEBRA - MAKA PSZENNA^FS^XZ')">Drukuj ZPL</button></td>
                    </tr>
                </table>
                <br>
                <a href="{{ url_for('admin.admin_panel') }}" style="display: inline-block; margin-top: 20px; color: #555; text-decoration: none;">&larr; Powrót do panelu admina</a>

                <script>
                function checkIp() {
                    var ip = document.getElementById('printer_ip').value;
                    if (!ip) {
                        alert('Podaj adres IP drukarki!');
                        return false;
                    }
                    return true;
                }
                function drukuj(zpl) {
                    if (!checkIp()) return;
                    document.getElementById('zpl_data').value = zpl;
                    document.querySelector('input[name="pdf_file"]').value = '';
                    document.getElementById('printForm').submit();
                }
                function drukujPdf() {
                    if (!checkIp()) return;
                    var fileInput = document.querySelector('input[name="pdf_file"]');
                    if (!fileInput.value) {
                        alert('Wybierz najpierw plik PDF z dysku!');
                        return;
                    }
                    document.getElementById('zpl_data').value = '';
                    document.getElementById('printForm').submit();
                }
                </script>
            </body>
        </html>
        """
        
        if request.method == 'GET':
            return render_template_string(HTML_TEST_PAGE)
            
        ip = request.json.get('ip') if request.is_json else request.form.get('ip')
        if not ip:
            return jsonify({"success": False, "message": "Brak IP"}), 400
            
        pdf_file = request.files.get('pdf_file')
        
        if pdf_file and pdf_file.filename.lower().endswith('.pdf'):
            data_to_send = pdf_file.read()
        else:
            zpl = request.json.get('dane') if request.is_json else request.form.get('dane')
            if not zpl:
                return jsonify({"success": False, "message": "Brak danych ZPL ani pliku PDF"}), 400
            data_to_send = zpl.encode('utf-8')
            
        try:
            with socket.create_connection((ip, 9100), timeout=5) as s:
                s.sendall(data_to_send)
            if request.is_json:
                return jsonify({"success": True, "message": "✅ OK - Wysłano do drukarki!"})
            else:
                return f"✅ OK - Wysłano dane do {ip}!<br><br><a href='{url_for('admin.admin_zpl_test')}'>Wróć do testów</a>"
        except Exception as e:
            if request.is_json:
                return jsonify({"success": False, "message": f"❌ BŁĄD: {str(e)}"}), 500
            else:
                return f"❌ BŁĄD podczas komunikacji z {ip}: {str(e)}<br><br><a href='{url_for('admin.admin_zpl_test')}'>Wróć do testów</a>"
