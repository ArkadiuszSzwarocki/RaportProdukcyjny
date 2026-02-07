from flask import Blueprint, render_template, request, redirect, flash, current_app, session, jsonify
from datetime import date
from app.db import get_db_connection
from werkzeug.security import generate_password_hash
# Importujemy dekorator
from app.decorators import admin_required


def _load_roles(cursor):
    try:
        cursor.execute("SELECT name, label FROM roles ORDER BY id ASC")
        return cursor.fetchall()
    except Exception:
        return [('admin', 'admin'), ('planista', 'planista'), ('pracownik', 'pracownik'), ('magazynier', 'magazynier'), ('dur', 'dur'), ('zarzad', 'zarzad'), ('laboratorium', 'laboratorium')]

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin')
@admin_required
def admin_panel():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pracownicy ORDER BY imie_nazwisko")
    pracownicy = cursor.fetchall()
    # Pobierz również kolumnę haslo, aby wykryć starsze formaty hashy wymagające resetu
    cursor.execute("SELECT id, login, rola, haslo FROM uzytkownicy ORDER BY login")
    konta_raw = cursor.fetchall()
    # Konta przekazane do szablonu (bez hasel)
    konta = [(r[0], r[1], r[2]) for r in konta_raw]
    # Wylicz listę loginów, które mają hashe w formacie nie-pbkdf2 (np. scrypt)
    needs_reset = [r[1] for r in konta_raw if r[3] and (str(r[3]).startswith('scrypt:') or not str(r[3]).startswith('pbkdf2:'))]
    cursor.execute("SELECT id, data_planu, sekcja, produkt, tonaz, tonaz_rzeczywisty, status FROM plan_produkcji ORDER BY data_planu DESC LIMIT 50")
    zlecenia_rows = cursor.fetchall()
    # Convert tuples to objects with attribute access for templates
    class _Z:
        def __init__(self, r):
            self.id = r[0]
            self.data_planu = r[1]
            self.sekcja = r[2]
            self.produkt = r[3]
            self.tonaz = r[4]
            self.tonaz_rzeczywisty = r[5]
            self.status = r[6]
    zlecenia = [_Z(r) for r in zlecenia_rows]
    cursor.execute("SELECT o.id, p.imie_nazwisko, o.typ, o.ilosc_godzin, o.komentarz FROM obecnosc o JOIN pracownicy p ON o.pracownik_id = p.id WHERE o.data_wpisu = %s", (date.today(),))
    raporty_hr = cursor.fetchall()
    roles = _load_roles(cursor)
    conn.close()
    return render_template('admin.html', pracownicy=pracownicy, konta=konta, raporty_hr=raporty_hr, dzisiaj=date.today(), zlecenia=zlecenia, needs_reset=needs_reset, roles=roles)


@admin_bp.route('/admin/users')
@admin_required
def admin_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, login, rola, haslo FROM uzytkownicy ORDER BY login")
    rows = cursor.fetchall()
    konta = [(r[0], r[1], r[2]) for r in rows]
    needs_reset = [r[1] for r in rows if r[3] and (str(r[3]).startswith('scrypt:') or not str(r[3]).startswith('pbkdf2:'))]
    roles = _load_roles(cursor)
    conn.close()
    return render_template('admin_users.html', konta=konta, needs_reset=needs_reset, roles=roles)


@admin_bp.route('/admin/ustawienia')
@admin_required
def admin_ustawienia():
    # Show selection tiles (Użytkownicy / Pracownicy)
    return render_template('ustawienia_index.html')


@admin_bp.route('/admin/ustawienia/uzytkownicy')
@admin_required
def admin_ustawienia_uzytkownicy():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, login, rola, grupa, haslo FROM uzytkownicy ORDER BY login")
    rows = cursor.fetchall()
    konta = [(r[0], r[1], r[2], r[3]) for r in rows]
    needs_reset = [r[1] for r in rows if r[4] and (str(r[4]).startswith('scrypt:') or not str(r[4]).startswith('pbkdf2:'))]
    # Compute suggested free pracownik id to help admin create/match accounts
    try:
        cursor.execute("SELECT id FROM pracownicy ORDER BY id ASC")
        used = [int(r[0]) for r in cursor.fetchall()]
        suggested_prac_id = 1
        for u in used:
            if u == suggested_prac_id:
                suggested_prac_id += 1
            elif u > suggested_prac_id:
                break
    except Exception:
        suggested_prac_id = 1
    roles = _load_roles(cursor)
    conn.close()
    return render_template('ustawienia_uzytkownicy.html', konta=konta, needs_reset=needs_reset, suggested_prac_id=suggested_prac_id, roles=roles)


@admin_bp.route('/admin/ustawienia/pracownicy')
@admin_required
def admin_ustawienia_pracownicy():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, imie_nazwisko, grupa FROM pracownicy ORDER BY imie_nazwisko")
    pracownicy = cursor.fetchall()
    # Compute first free positive integer id (suggestion only)
    try:
        cursor.execute("SELECT id FROM pracownicy ORDER BY id ASC")
        used = [int(r[0]) for r in cursor.fetchall()]
        suggested = 1
        for u in used:
            if u == suggested:
                suggested += 1
            elif u > suggested:
                break
    except Exception:
        suggested = 1
    conn.close()
    return render_template('ustawienia_pracownicy.html', pracownicy=pracownicy, suggested_id=suggested)


@admin_bp.route('/admin/ustawienia/roles')
@admin_required
def admin_ustawienia_roles():
    # pages and roles
    pages = ['dashboard','ustawienia','jakosc','planista','plan','zasyp','workowanie','magazyn','moje_godziny','awarie','wyniki']
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT name, label FROM roles ORDER BY id ASC")
        roles = cursor.fetchall()
    except Exception:
        roles = [('admin','admin'),('planista','planista'),('pracownik','pracownik'),('magazynier','magazynier'),('dur','dur'),('zarzad','zarzad'),('laboratorium','laboratorium'),('produkcja','produkcja'),('lider','lider')]
    conn.close()

    # load existing perms from file
    import os, json
    cfg_path = os.path.join(current_app.root_path, '..', 'config', 'role_permissions.json')
    cfg_path = os.path.abspath(cfg_path)
    perms = {}
    try:
        with open(cfg_path, 'r', encoding='utf-8') as f:
            perms = json.load(f)
    except Exception as e:
        current_app.logger.error('Error loading role_permissions.json from %s: %s', cfg_path, str(e))
        perms = {}
    
    # Rebuild perms in correct page order to ensure consistent rendering
    ordered_perms = {}
    for p in pages:
        if p in perms:
            ordered_perms[p] = perms[p]
        else:
            ordered_perms[p] = {}
    
    # Ensure full matrix: all pages × all roles (fill missing with access:false, readonly:false)
    for p in pages:
        for r in roles:
            role_name = r[0]
            if role_name not in ordered_perms[p]:
                ordered_perms[p][role_name] = {'access': False, 'readonly': False}

    # pass JSON to template
    return render_template('ustawienia_roles.html', pages=pages, roles=roles, perms_json=ordered_perms)


@admin_bp.route('/admin/ustawienia/roles/save', methods=['POST'])
@admin_required
def admin_ustawienia_roles_save():
    import os, json
    try:
        current_app.logger.info('admin_ustawienia_roles_save invoked by user=%s remote=%s', session.get('login'), request.remote_addr)
        data = request.get_json(force=True)
    except Exception:
        data = None
    if data is None:
        return ('Bad request', 400)
    # Clean the payload: remove any page with empty roles dict
    # This prevents sending {"page": {}} for pages with no roles checked
    try:
        cleaned_data = {}
        for page, roles in data.items():
            if isinstance(roles, dict) and len(roles) > 0:
                cleaned_data[page] = roles
        data = cleaned_data
    except Exception:
        pass
    
    # Server-side safeguard: refuse to overwrite config if payload contains
    # no role with access=True (prevents accidental global-deny overwrites).
    try:
        def _payload_has_access(d):
            if not isinstance(d, dict):
                return False
            for page, roles in d.items():
                if isinstance(roles, dict):
                    for role, perms in roles.items():
                        if isinstance(perms, dict):
                            try:
                                if bool(perms.get('access')):
                                    return True
                            except Exception:
                                # permissive fallback
                                continue
            return False
        if not _payload_has_access(data):
            current_app.logger.warning('Rejected roles save: payload contains no access=true entries (user=%s)', session.get('login'))
            return (jsonify({'error': 'Payload contains no access=true entries; refusing to overwrite config.'}), 400)
    except Exception:
        # If our check fails for unexpected reasons, proceed cautiously and reject.
        current_app.logger.exception('Error validating roles payload; rejecting save request')
        return (jsonify({'error': 'Validation error'}), 400)
    cfg_dir = os.path.join(current_app.root_path, '..', 'config')
    cfg_dir = os.path.abspath(cfg_dir)
    os.makedirs(cfg_dir, exist_ok=True)
    cfg_path = os.path.join(cfg_dir, 'role_permissions.json')
    
    # Load existing config to merge with incoming data (don't overwrite!)
    existing_config = {}
    try:
        with open(cfg_path, 'r', encoding='utf-8') as f:
            existing_config = json.load(f)
    except Exception:
        existing_config = {}
    
    # Merge incoming data with existing config
    # For pages in the payload: REPLACE entire page (not merge roles!)
    # This way if admin unchecked a role, it gets removed
    # For pages NOT in payload: keep existing config
    merged_config = existing_config.copy()
    for page, roles in data.items():
        if isinstance(roles, dict):
            # Replace entire page with what came from UI
            merged_config[page] = roles
    
    # Reorder merged_config to match pages order for consistency
    # Define canonical page order
    pages = ['dashboard','ustawienia','jakosc','planista','plan','zasyp','workowanie','magazyn','moje_godziny','awarie','wyniki']
    ordered_merged = {}
    for p in pages:
        if p in merged_config:
            ordered_merged[p] = merged_config[p]
    # Keep any pages not in canonical list (shouldn't happen but preserve them)
    for p in merged_config:
        if p not in ordered_merged:
            ordered_merged[p] = merged_config[p]
    merged_config = ordered_merged
    
    current_app.logger.info('Reordered config pages: %s', list(merged_config.keys()))
    
    # Make a timestamped backup if file exists
    try:
        import shutil
        from datetime import datetime as _dt
        bak_name = None
        if os.path.exists(cfg_path):
            bak_name = cfg_path + '.bak.' + _dt.now().strftime('%Y%m%d-%H%M%S')
            try:
                shutil.copy2(cfg_path, bak_name)
                current_app.logger.info('Created backup of role_permissions: %s', bak_name)
            except Exception:
                current_app.logger.exception('Failed to create backup of role_permissions')

        with open(cfg_path, 'w', encoding='utf-8') as f:
            json.dump(merged_config, f, ensure_ascii=False, indent=2)
        
        # Verify written order
        with open(cfg_path, 'r', encoding='utf-8') as f:
            verify_order = json.load(f)
            saved_order = list(verify_order.keys())
            current_app.logger.info('Verified config page order after save: %s', saved_order)
        
        try:
            current_app.logger.info('Role permissions saved to %s by user=%s', cfg_path, session.get('login'))
        except Exception:
            current_app.logger.info('Role permissions saved to %s', cfg_path)
        return (jsonify({'ok': True, 'backup': bak_name}), 200)
    except Exception as e:
        try:
            current_app.logger.exception('Failed to save role_permissions to %s', cfg_path)
        except Exception:
            pass
        return (jsonify({'error': str(e)}), 500)

@admin_bp.route('/admin/ustawienia/roles/add', methods=['POST'])
@admin_required
def admin_ustawienia_roles_add():
    """Dodaj nową rolę"""
    import os, json
    
    try:
        data = request.get_json(force=True)
        role_name = data.get('role_name', '').strip().lower()
        
        if not role_name:
            return jsonify({'success': False, 'error': 'Nazwa roli nie może być pusta'}), 400
        
        # Walidacja: tylko litery, liczby, podkreślnik
        if not all(c.isalnum() or c == '_' for c in role_name):
            return jsonify({'success': False, 'error': 'Nazwa roli może zawierać tylko litery, liczby i podkreślnik'}), 400
        
        cfg_path = os.path.join(current_app.root_path, 'config', 'role_permissions.json')
        
        # Czytaj obecną konfigurację
        config = {}
        if os.path.exists(cfg_path):
            with open(cfg_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        
        # Sprawdź czy rola już istnieje
        for page in config.values():
            if isinstance(page, dict) and role_name in page:
                return jsonify({'success': False, 'error': f'Rola "{role_name}" już istnieje'}), 400
        
        # Dodaj nową rolę do wszystkich stron bez dostępu (domyślnie)
        for page in config:
            if isinstance(config[page], dict):
                config[page][role_name] = {'access': False, 'readonly': False}
        
        # Stwórz backup
        import shutil
        from datetime import datetime as _dt
        if os.path.exists(cfg_path):
            bak_path = cfg_path + '.bak.' + _dt.now().strftime('%Y%m%d-%H%M%S')
            shutil.copy2(cfg_path, bak_path)
        
        # Zapisz nową konfigurację
        with open(cfg_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        current_app.logger.info('Added new role "%s" by user=%s', role_name, session.get('login'))
        return jsonify({'success': True, 'message': f'Rola "{role_name}" została dodana'}), 200
        
    except Exception as e:
        current_app.logger.exception('Error adding new role')
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_bp.route('/admin/pracownik/dodaj', methods=['POST'])
@admin_required
def admin_dodaj_pracownika():
    conn = get_db_connection()
    cursor = conn.cursor()
    grupa = request.form.get('grupa', '').strip()
    # Optional explicit id handling
    use_id = request.form.get('use_id')
    explicit_id = request.form.get('explicit_id')
    if use_id and explicit_id:
        try:
            eid = int(explicit_id)
        except ValueError:
            flash("Błędne ID.", "error")
            conn.close()
            return redirect('/admin')
        # Ensure id not already used
        cursor.execute("SELECT 1 FROM pracownicy WHERE id=%s", (eid,))
        if cursor.fetchone():
            flash(f"ID {eid} już istnieje.", "error")
            conn.close()
            return redirect('/admin')
        try:
            from app.utils.validation import require_field
            imie_nazwisko = require_field(request.form, 'imie_nazwisko')
            imie_nazwisko = imie_nazwisko.strip()
        except Exception as e:
            flash(str(e), 'danger')
            conn.close()
            return redirect('/admin')
        cursor.execute("INSERT INTO pracownicy (id, imie_nazwisko, grupa) VALUES (%s, %s, %s)", (eid, imie_nazwisko, grupa))
        conn.commit()
        new_id = eid
        # Update AUTO_INCREMENT to at least max(id)+1
        try:
            cursor.execute("SELECT COALESCE(MAX(id),0) FROM pracownicy")
            m = cursor.fetchone()
            maxid = int(m[0]) if m else 0
            next_ai = maxid + 1
            cursor.execute("ALTER TABLE pracownicy AUTO_INCREMENT = %s", (next_ai,))
            conn.commit()
        except Exception:
            conn.rollback()
    else:
        try:
            from app.utils.validation import require_field
            imie_nazwisko = require_field(request.form, 'imie_nazwisko')
            imie_nazwisko = imie_nazwisko.strip()
        except Exception as e:
            flash(str(e), 'danger')
            conn.close()
            return redirect('/admin')
        cursor.execute("INSERT INTO pracownicy (imie_nazwisko, grupa) VALUES (%s, %s)", (imie_nazwisko, grupa))
        conn.commit()
        new_id = None
    # If new_id not set yet (standard insert), try to retrieve it
    try:
        if not new_id:
            try:
                new_id = int(cursor.lastrowid)
            except Exception:
                new_id = None
        if not new_id:
            cursor.execute("SELECT id FROM pracownicy WHERE imie_nazwisko=%s ORDER BY id DESC LIMIT 1", (imie_nazwisko,))
            r = cursor.fetchone()
            new_id = int(r[0]) if r else None

        # Provision a minimal obsada_zmiany entry so the calendar shows up for the new employee
        if new_id:
            try:
                cursor.execute("INSERT INTO obsada_zmiany (data_wpisu, sekcja, pracownik_id) VALUES (%s, %s, %s)", (date.today(), 'Nieprzydzielony', new_id))
            except Exception:
                conn.rollback()
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        conn.close()
    flash("Dodano.", "success")
    return redirect('/admin')

@admin_bp.route('/admin/pracownik/edytuj', methods=['POST'])
@admin_required
def admin_edytuj_pracownika():
    conn = get_db_connection()
    cursor = conn.cursor()
    grupa = request.form.get('grupa', '').strip()
    imie_nazwisko = request.form.get('imie_nazwisko','').strip()
    pid = request.form.get('id')
    if not imie_nazwisko or not pid:
        flash('Brak wymaganych pól.', 'danger')
        conn.close()
        return redirect('/admin')
    cursor.execute("UPDATE pracownicy SET imie_nazwisko=%s, grupa=%s WHERE id=%s", (imie_nazwisko, grupa, pid))
    conn.commit()
    conn.close()
    flash("Zaktualizowano.", "success")
    return redirect('/admin')

@admin_bp.route('/admin/pracownik/usun/<int:id>', methods=['POST'])
@admin_required
def admin_usun_pracownika(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM pracownicy WHERE id=%s", (id,))
        flash("Usunięto.", "info")
    except Exception:
        flash("Nie można usunąć (historia).", "error")
    conn.commit()
    conn.close()
    return redirect('/admin')

@admin_bp.route('/admin/konto/dodaj', methods=['POST'])
@admin_required
def admin_dodaj_konto():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        pwd = request.form.get('haslo', '')
        # Używaj spójnego algorytmu PBKDF2-SHA256 przy tworzeniu nowych kont
        hashed = generate_password_hash(pwd, method='pbkdf2:sha256') if pwd else ''
        grupa = request.form.get('grupa','').strip()
        imie_nazwisko = request.form.get('imie_nazwisko','').strip()
        try:
            from app.utils.validation import require_field, optional_field
            login = require_field(request.form, 'login').strip()
            rola_field = optional_field(request.form, 'rola', default='').strip()
        except Exception as e:
            flash(str(e), 'danger')
            conn.close()
            return redirect('/admin')
        cursor.execute("INSERT INTO uzytkownicy (login, haslo, rola, grupa) VALUES (%s, %s, %s, %s)", (login, hashed, rola_field, grupa))
        # Spróbuj automatycznie powiązać konto z rekordem pracownika jeśli istnieje dopasowanie
        try:
            # Prepare a set of search tokens from the login (strip digits, separators)
            import re
            l_raw = login.lower()
            l_alpha = re.sub(r"[^a-ząćęłńóśżź ]+", ' ', l_raw)
            tokens = [t.strip() for t in re.split(r"\s+|[_\.\-]", l_alpha) if t.strip()]

            # 1) Exact case-insensitive full match
            cursor.execute("SELECT id FROM pracownicy WHERE LOWER(imie_nazwisko) = %s LIMIT 1", (l_raw,))
            r = cursor.fetchone()
            # 2) If not exact, try matching all tokens using LIKE (AND for tokens)
            if not r and tokens:
                where_clauses = " AND ".join(["LOWER(imie_nazwisko) LIKE %s" for _ in tokens])
                params = tuple([f"%{t}%" for t in tokens])
                q = f"SELECT id FROM pracownicy WHERE {where_clauses} LIMIT 2"
                cursor.execute(q, params)
                rows = cursor.fetchall()
                if len(rows) == 1:
                    r = rows[0]
                else:
                    r = None

            if r:
                prac_id = int(r[0])
                cursor.execute("UPDATE uzytkownicy SET pracownik_id=%s WHERE login=%s", (prac_id, login))
                # If admin provided a name, update the pracownicy record with it
                if imie_nazwisko:
                    try:
                        cursor.execute("UPDATE pracownicy SET imie_nazwisko=%s WHERE id=%s", (imie_nazwisko, prac_id))
                        conn.commit()
                    except Exception:
                        conn.rollback()
                flash(f"Dodano i powiązano z pracownikiem id={prac_id}", "success")
            else:
                flash("Dodano.", "success")
            # If admin provided assign_prac, create or assign specified pracownik id
            assign_prac = request.form.get('assign_prac')
            assign_prac_id = request.form.get('assign_prac_id')
            if assign_prac:
                # If admin checked the box but the numeric field wasn't submitted (disabled inputs),
                # compute a suggested free id on the server and use it.
                aid = None
                if assign_prac_id:
                    try:
                        aid = int(assign_prac_id)
                    except Exception:
                        aid = None
                if not aid:
                    try:
                        cursor.execute("SELECT id FROM pracownicy ORDER BY id ASC")
                        used = [int(r[0]) for r in cursor.fetchall()]
                        suggested = 1
                        for u in used:
                            if u == suggested:
                                suggested += 1
                            elif u > suggested:
                                break
                        aid = suggested
                    except Exception:
                        aid = None

                if aid:
                    # Ensure pracownicy exists with that id; if not, create it
                    cursor.execute("SELECT id FROM pracownicy WHERE id=%s", (aid,))
                    if not cursor.fetchone():
                        try:
                            # Insert using provided full name when available, fallback to login
                            cursor.execute("INSERT INTO pracownicy (id, imie_nazwisko, grupa) VALUES (%s, %s, %s)", (aid, imie_nazwisko if imie_nazwisko else login, ''))
                            conn.commit()
                            # update AUTO_INCREMENT
                            try:
                                cursor.execute("SELECT COALESCE(MAX(id),0) FROM pracownicy")
                                m = cursor.fetchone()
                                maxid = int(m[0]) if m else 0
                                next_ai = maxid + 1
                                cursor.execute("ALTER TABLE pracownicy AUTO_INCREMENT = %s", (next_ai,))
                                conn.commit()
                            except Exception:
                                conn.rollback()
                        except Exception:
                            conn.rollback()
                    # Finally assign to account
                    try:
                        cursor.execute("UPDATE uzytkownicy SET pracownik_id=%s WHERE login=%s", (aid, login))
                        conn.commit()
                        flash(f"Przypisano konto do pracownika id={aid}", "success")
                    except Exception:
                        conn.rollback()
        except Exception:
            # Jeśli mapping się nie udał, nie przerywamy tworzenia konta
            flash("Dodano.", "success")
    except Exception:
        flash("Login zajęty!", "error")
    conn.commit()
    conn.close()
    return redirect('/admin')


@admin_bp.route('/admin/konto/edytuj', methods=['POST'])
@admin_required
def admin_edytuj_konto():
    conn = get_db_connection()
    cursor = conn.cursor()
    uid = request.form.get('id')
    login = request.form.get('login')
    rola = request.form.get('rola')
    grupa = request.form.get('grupa','').strip()
    haslo = request.form.get('haslo', '').strip()
    try:
        if haslo:
            cursor.execute("UPDATE uzytkownicy SET login=%s, haslo=%s, rola=%s, grupa=%s WHERE id=%s", (login, generate_password_hash(haslo, method='pbkdf2:sha256'), rola, grupa, uid))
        else:
            cursor.execute("UPDATE uzytkownicy SET login=%s, rola=%s, grupa=%s WHERE id=%s", (login, rola, grupa, uid))
        conn.commit()
        flash("Zaktualizowano.", "success")
    except Exception:
        conn.rollback()
        flash("Błąd aktualizacji (login może być zajęty).", "error")
    conn.close()
    return redirect('/admin?tab=users')

@admin_bp.route('/admin/konto/usun/<int:id>', methods=['POST'])
@admin_required
def admin_usun_konto(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM uzytkownicy WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    flash("Usunięto.", "info")
    return redirect('/admin')


# ============= WORKOWANIE PROCESSING TIMES =============

@admin_bp.route('/admin/ustawienia/workowanie_times', methods=['GET'])
@admin_required
def admin_workowanie_times():
    """Wyświetl ustawienia czasów przetwarzania dla Workowania"""
    import os, json
    cfg_path = os.path.join(current_app.root_path, 'config', 'workowanie_processing_times.json')
    times_config = {}
    try:
        if os.path.exists(cfg_path):
            with open(cfg_path, 'r', encoding='utf-8') as f:
                times_config = json.load(f)
        else:
            times_config = {"processing_times_minutes": {}}
    except Exception as e:
        current_app.logger.error(f'Error loading workowanie_processing_times.json: {e}')
        times_config = {"processing_times_minutes": {}}
    
    return render_template('ustawienia_workowanie_times.html', times_config=times_config)


@admin_bp.route('/admin/ustawienia/workowanie_times/update', methods=['POST'])
@admin_required
def admin_workowanie_times_update():
    """Zaktualizuj czasy przetwarzania dla Workowania"""
    import os, json, shutil, re
    from datetime import datetime
    cfg_path = os.path.join(current_app.root_path, 'config', 'workowanie_processing_times.json')
    
    try:
        # Odczytaj aktualne ustawienia
        times_config = {}
        if os.path.exists(cfg_path):
            with open(cfg_path, 'r', encoding='utf-8') as f:
                times_config = json.load(f)
        
        # Utwórz backup
        if os.path.exists(cfg_path):
            backup_path = cfg_path + f'.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
            shutil.copy2(cfg_path, backup_path)
        
        # Zaktualizuj czasy na podstawie formularza
        processing_times = times_config.get("processing_times_minutes", {})
        
        # Zlicz istniejące nowe wpisy
        new_entry_counter = 0
        
        # Przetwórz wszystkie klucze z formularza (istniejące i nowe)
        for key in list(processing_times.keys()):
            prefix = f"{key}_"
            # Aktualizuj istniejące wpisy
            time_minutes = request.form.get(f"{prefix}time_minutes", "").strip()
            description = request.form.get(f"{prefix}description", "").strip()
            name = request.form.get(f"{prefix}name", "").strip()
            weight_kg = request.form.get(f"{prefix}weight_kg", "").strip()
            
            if time_minutes:
                try:
                    processing_times[key]["processing_time_minutes"] = int(time_minutes)
                except ValueError:
                    pass
            
            if description:
                processing_times[key]["description"] = description
            
            if name:
                processing_times[key]["name"] = name
                
            if weight_kg:
                try:
                    processing_times[key]["weight_kg"] = int(weight_kg)
                except ValueError:
                    pass
        
        # Przetwórz nowe wpisy (new_N_*)
        for field_name in request.form.keys():
            match = re.match(r'(new_\d+)_(\w+)', field_name)
            if match:
                new_key = match.group(1)
                field_type = match.group(2)
                
                if new_key not in processing_times:
                    processing_times[new_key] = {
                        "name": "",
                        "weight_kg": 0,
                        "processing_time_minutes": 15,
                        "description": ""
                    }
                
                value = request.form.get(field_name, "").strip()
                
                if field_type == 'name':
                    processing_times[new_key]["name"] = value
                elif field_type == 'weight_kg':
                    try:
                        processing_times[new_key]["weight_kg"] = int(value) if value else 0
                    except ValueError:
                        pass
                elif field_type == 'time_minutes':
                    try:
                        processing_times[new_key]["processing_time_minutes"] = int(value) if value else 15
                    except ValueError:
                        pass
                elif field_type == 'description':
                    processing_times[new_key]["description"] = value
        
        times_config["processing_times_minutes"] = processing_times
        
        # Zapisz nową konfigurację
        with open(cfg_path, 'w', encoding='utf-8') as f:
            json.dump(times_config, f, ensure_ascii=False, indent=2)
        
        current_app.logger.info('Updated workowanie_processing_times.json')
        flash("✓ Czasy przetwarzania Workowania zostały zaktualizowane!", "success")
    
    except Exception as e:
        current_app.logger.exception(f'Error updating workowanie_processing_times.json: {e}')
        flash(f"❌ Błąd podczas zapisu: {str(e)}", "error")
    
    return redirect('/admin/ustawienia/workowanie_times')


