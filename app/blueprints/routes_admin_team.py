from datetime import date

from flask import current_app, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash

from app.core.audit import audit_log
from app.db import get_db_connection
from app.decorators import dynamic_role_required


def register_admin_team_routes(admin_bp, *, load_roles):
    @admin_bp.route('/admin/ustawienia/zespol')
    @dynamic_role_required('ustawienia')
    def admin_ustawienia_zespol():
        """Unified Team Management: Employees + Optional System Accounts."""
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT p.id, p.imie_nazwisko, p.grupa as prac_hall, "
            "       u.id as user_id, u.login, u.rola, u.grupa as user_hall "
            "FROM pracownicy p "
            "LEFT JOIN uzytkownicy u ON p.id = u.pracownik_id "
            "ORDER BY p.imie_nazwisko"
        )
        rows = cursor.fetchall()

        roles = load_roles(cursor)
        roles_map = {role[0]: role[1] for role in roles}

        team = []
        for row in rows:
            team.append(
                {
                    'id': row[0],
                    'imie_nazwisko': row[1],
                    'prac_hall': row[2],
                    'user_id': row[3],
                    'login': row[4],
                    'rola': row[5],
                    'role_label': roles_map.get(row[5] or '', 'Pracownik'),
                    'user_hall': row[6],
                }
            )

        conn.close()
        return render_template('ustawienia_zespol.html', team=team, roles=roles)

    @admin_bp.route('/admin/ustawienia/uzytkownicy')
    @dynamic_role_required('ustawienia')
    def admin_ustawienia_uzytkownicy():
        """Redirect legacy users management to the new unified team view."""
        return redirect(url_for('admin.admin_ustawienia_zespol'))

    @admin_bp.route('/admin/ustawienia/pracownicy')
    @dynamic_role_required('ustawienia')
    def admin_ustawienia_pracownicy():
        """Redirect legacy employees management to the new unified team view."""
        return redirect(url_for('admin.admin_ustawienia_zespol'))

    @admin_bp.route('/api/zespol/person/<int:id>')
    @dynamic_role_required('ustawienia')
    def api_zespol_person(id):
        """Fetch single person data for editing."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, imie_nazwisko, grupa FROM pracownicy WHERE id = %s", (id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return jsonify({'success': False, 'message': 'Nie znaleziono osoby'})

        return jsonify(
            {
                'success': True,
                'person': {
                    'id': row[0],
                    'imie_nazwisko': row[1],
                    'grupa': row[2],
                },
            }
        )

    @admin_bp.route('/api/zespol/person/update', methods=['POST'])
    @dynamic_role_required('ustawienia')
    def api_zespol_person_update():
        """Update personnel basic data (physical record)."""
        person_id = request.form.get('id')
        name = request.form.get('imie_nazwisko')
        grupa = request.form.get('grupa')

        if not person_id or not name:
            flash('Błąd danych', 'danger')
            return redirect(url_for('admin.admin_ustawienia_zespol'))

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE pracownicy SET imie_nazwisko = %s, grupa = %s WHERE id = %s", (name, grupa, person_id))
        conn.commit()
        conn.close()

        flash('Zaktualizowano dane pracownika', 'success')
        return redirect(url_for('admin.admin_ustawienia_zespol'))

    @admin_bp.route('/api/zespol/dodaj', methods=['POST'])
    @dynamic_role_required('ustawienia')
    def api_zespol_dodaj():
        """Unified Add Person helper (optionally creates system account too)."""
        name = request.form.get('imie_nazwisko')
        grupa = request.form.get('grupa', 'ALL')
        explicit_id = request.form.get('explicit_id')

        create_acc = request.form.get('create_account') == 'on'
        login = request.form.get('login')
        haslo = request.form.get('haslo')
        rola = request.form.get('rola', 'pracownik')

        if not name:
            flash('Nazwisko jest wymagane', 'danger')
            return redirect(url_for('admin.admin_ustawienia_zespol'))

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            if explicit_id:
                cursor.execute("INSERT INTO pracownicy (id, imie_nazwisko, grupa) VALUES (%s, %s, %s)", (explicit_id, name, grupa))
                new_prac_id = explicit_id
            else:
                cursor.execute("INSERT INTO pracownicy (imie_nazwisko, grupa) VALUES (%s, %s)", (name, grupa))
                new_prac_id = cursor.lastrowid

            if create_acc and login and haslo:
                hashed = generate_password_hash(haslo)
                cursor.execute(
                    "INSERT INTO uzytkownicy (login, haslo, rola, grupa, pracownik_id) VALUES (%s, %s, %s, %s, %s)",
                    (login, hashed, rola, grupa, new_prac_id),
                )

            conn.commit()
            flash(f'Dodano {name} do zespołu.', 'success')
        except Exception as error:
            conn.rollback()
            flash(f'Błąd podczas dodawania: {str(error)}', 'danger')
        finally:
            conn.close()

        return redirect(url_for('admin.admin_ustawienia_zespol'))

    @admin_bp.route('/admin/pracownik/dodaj', methods=['POST'])
    @dynamic_role_required('ustawienia')
    def admin_dodaj_pracownika():
        conn = get_db_connection()
        cursor = conn.cursor()
        grupa = request.form.get('grupa', '').strip()
        use_id = request.form.get('use_id')
        explicit_id = request.form.get('explicit_id')
        if use_id and explicit_id:
            try:
                employee_id = int(explicit_id)
            except ValueError:
                flash('Błędne ID.', 'error')
                conn.close()
                return redirect(url_for('admin.admin_ustawienia_zespol'))
            cursor.execute("SELECT 1 FROM pracownicy WHERE id=%s", (employee_id,))
            if cursor.fetchone():
                flash(f'ID {employee_id} już istnieje.', 'error')
                conn.close()
                return redirect(url_for('admin.admin_ustawienia_zespol'))
            try:
                from app.utils.validation import require_field

                imie_nazwisko = require_field(request.form, 'imie_nazwisko').strip()
            except Exception as error:
                flash(str(error), 'danger')
                conn.close()
                return redirect(url_for('admin.admin_ustawienia_zespol'))
            cursor.execute("INSERT INTO pracownicy (id, imie_nazwisko, grupa) VALUES (%s, %s, %s)", (employee_id, imie_nazwisko, grupa))
            conn.commit()
            new_id = employee_id
            try:
                cursor.execute("SELECT COALESCE(MAX(id),0) FROM pracownicy")
                max_row = cursor.fetchone()
                max_id = int(max_row[0]) if max_row else 0
                next_ai = max_id + 1
                cursor.execute("ALTER TABLE pracownicy AUTO_INCREMENT = %s", (next_ai,))
                conn.commit()
            except Exception:
                conn.rollback()
        else:
            try:
                from app.utils.validation import require_field

                imie_nazwisko = require_field(request.form, 'imie_nazwisko').strip()
            except Exception as error:
                flash(str(error), 'danger')
                conn.close()
                return redirect(url_for('admin.admin_ustawienia_zespol'))
            cursor.execute("INSERT INTO pracownicy (imie_nazwisko, grupa) VALUES (%s, %s)", (imie_nazwisko, grupa))
            conn.commit()
            new_id = None

        try:
            if not new_id:
                try:
                    new_id = int(cursor.lastrowid)
                except Exception:
                    new_id = None
            if not new_id:
                cursor.execute("SELECT id FROM pracownicy WHERE imie_nazwisko=%s ORDER BY id DESC LIMIT 1", (imie_nazwisko,))
                row = cursor.fetchone()
                new_id = int(row[0]) if row else None

            if new_id:
                try:
                    cursor.execute(
                        "INSERT INTO obsada_zmiany (data_wpisu, sekcja, pracownik_id) VALUES (%s, %s, %s)",
                        (date.today(), 'Nieprzydzielony', new_id),
                    )
                except Exception:
                    conn.rollback()
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            conn.close()
        flash('Dodano.', 'success')
        return redirect(url_for('admin.admin_ustawienia_zespol'))

    @admin_bp.route('/admin/pracownik/edytuj', methods=['POST'])
    @dynamic_role_required('ustawienia')
    def admin_edytuj_pracownika():
        conn = get_db_connection()
        cursor = conn.cursor()
        grupa = request.form.get('grupa', '').strip()
        imie_nazwisko = request.form.get('imie_nazwisko', '').strip()
        person_id = request.form.get('id')
        if not imie_nazwisko or not person_id:
            flash('Brak wymaganych pól.', 'danger')
            conn.close()
            return redirect(url_for('admin.admin_ustawienia_zespol'))
        cursor.execute("UPDATE pracownicy SET imie_nazwisko=%s, grupa=%s WHERE id=%s", (imie_nazwisko, grupa, person_id))
        conn.commit()
        conn.close()
        flash('Zaktualizowano.', 'success')
        return redirect(url_for('admin.admin_ustawienia_zespol'))

    @admin_bp.route('/admin/pracownik/usun/<int:id>', methods=['POST'])
    @dynamic_role_required('ustawienia')
    def admin_usun_pracownika(id):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM pracownicy WHERE id=%s", (id,))
            flash('Usunięto.', 'info')
        except Exception:
            flash('Nie można usunąć (historia).', 'error')
        conn.commit()
        conn.close()
        return redirect(url_for('admin.admin_ustawienia_zespol'))

    @admin_bp.route('/admin/konto/dodaj', methods=['POST'])
    @dynamic_role_required('ustawienia')
    def admin_dodaj_konto():
        conn = get_db_connection()
        cursor = conn.cursor()
        login = ''
        rola_field = ''
        try:
            pwd = request.form.get('haslo', '')
            hashed = generate_password_hash(pwd, method='pbkdf2:sha256') if pwd else ''
            grupa = request.form.get('grupa', '').strip()
            imie_nazwisko = request.form.get('imie_nazwisko', '').strip()
            try:
                from app.utils.validation import optional_field, require_field

                login = require_field(request.form, 'login').strip()
                rola_field = optional_field(request.form, 'rola', default='').strip()
            except Exception as error:
                flash(str(error), 'danger')
                conn.close()
                return redirect(url_for('admin.admin_ustawienia_zespol'))
            cursor.execute("INSERT INTO uzytkownicy (login, haslo, rola, grupa) VALUES (%s, %s, %s, %s)", (login, hashed, rola_field, grupa))
            try:
                import re

                login_raw = login.lower()
                login_alpha = re.sub(r"[^a-ząćęłńóśżź ]+", ' ', login_raw)
                tokens = [token.strip() for token in re.split(r"\s+|[_\.\-]", login_alpha) if token.strip()]

                cursor.execute("SELECT id FROM pracownicy WHERE LOWER(imie_nazwisko) = %s LIMIT 1", (login_raw,))
                row = cursor.fetchone()
                if not row and tokens:
                    where_clauses = " AND ".join(["LOWER(imie_nazwisko) LIKE %s" for _ in tokens])
                    params = tuple([f"%{token}%" for token in tokens])
                    query = f"SELECT id FROM pracownicy WHERE {where_clauses} LIMIT 2"
                    cursor.execute(query, params)
                    rows = cursor.fetchall()
                    if len(rows) == 1:
                        row = rows[0]
                    else:
                        row = None

                if row:
                    prac_id = int(row[0])
                    cursor.execute("UPDATE uzytkownicy SET pracownik_id=%s WHERE login=%s", (prac_id, login))
                    if imie_nazwisko:
                        try:
                            cursor.execute("UPDATE pracownicy SET imie_nazwisko=%s WHERE id=%s", (imie_nazwisko, prac_id))
                            conn.commit()
                        except Exception:
                            conn.rollback()
                    flash(f'Dodano i powiązano z pracownikiem id={prac_id}', 'success')
                else:
                    flash('Dodano.', 'success')
                assign_prac = request.form.get('assign_prac')
                assign_prac_id = request.form.get('assign_prac_id')
                if assign_prac:
                    assign_id = None
                    if assign_prac_id:
                        try:
                            assign_id = int(assign_prac_id)
                        except Exception:
                            assign_id = None
                    if not assign_id:
                        try:
                            cursor.execute("SELECT id FROM pracownicy ORDER BY id ASC")
                            used = [int(existing_row[0]) for existing_row in cursor.fetchall()]
                            suggested = 1
                            for used_id in used:
                                if used_id == suggested:
                                    suggested += 1
                                elif used_id > suggested:
                                    break
                            assign_id = suggested
                        except Exception:
                            assign_id = None

                    if assign_id:
                        cursor.execute("SELECT id FROM pracownicy WHERE id=%s", (assign_id,))
                        if not cursor.fetchone():
                            try:
                                cursor.execute(
                                    "INSERT INTO pracownicy (id, imie_nazwisko, grupa) VALUES (%s, %s, %s)",
                                    (assign_id, imie_nazwisko if imie_nazwisko else login, ''),
                                )
                                conn.commit()
                                try:
                                    cursor.execute("SELECT COALESCE(MAX(id),0) FROM pracownicy")
                                    max_row = cursor.fetchone()
                                    max_id = int(max_row[0]) if max_row else 0
                                    next_ai = max_id + 1
                                    cursor.execute("ALTER TABLE pracownicy AUTO_INCREMENT = %s", (next_ai,))
                                    conn.commit()
                                except Exception:
                                    conn.rollback()
                            except Exception:
                                conn.rollback()
                        try:
                            cursor.execute("UPDATE uzytkownicy SET pracownik_id=%s WHERE login=%s", (assign_id, login))
                            conn.commit()
                            flash(f'Przypisano konto do pracownika id={assign_id}', 'success')
                        except Exception:
                            conn.rollback()
            except Exception:
                flash('Dodano.', 'success')
        except Exception:
            flash('Login zajęty!', 'error')
        conn.commit()
        conn.close()
        audit_log('Dodał konto użytkownika', f'login={login}, rola={rola_field}')
        current_app.logger.info('Admin %s dodał konto: login=%s, rola=%s', session.get('login'), login, rola_field)
        return redirect(url_for('admin.admin_ustawienia_zespol'))

    @admin_bp.route('/admin/konto/edytuj', methods=['POST'])
    @dynamic_role_required('ustawienia')
    def admin_edytuj_konto():
        conn = get_db_connection()
        cursor = conn.cursor()
        user_id = request.form.get('id')
        login = request.form.get('login')
        rola = request.form.get('rola')
        grupa = request.form.get('grupa', '').strip()
        haslo = request.form.get('haslo', '').strip()
        try:
            if haslo:
                new_haslo = generate_password_hash(haslo, method='pbkdf2:sha256')
                cursor.execute("UPDATE uzytkownicy SET login=%s, haslo=%s, rola=%s, grupa=%s WHERE id=%s", (login, new_haslo, rola, grupa, user_id))
            else:
                cursor.execute("UPDATE uzytkownicy SET login=%s, rola=%s, grupa=%s WHERE id=%s", (login, rola, grupa, user_id))
            conn.commit()
            change_summary = f'login={login}, rola={rola}' + (', zmiana hasła' if haslo else '')
            audit_log('Edytował konto użytkownika', change_summary)
            current_app.logger.info('Admin %s edytował konto ID=%s: %s', session.get('login'), user_id, change_summary)
            flash('Zaktualizowano.', 'success')
        except Exception as error:
            conn.rollback()
            current_app.logger.error(f'Error updating account: {str(error)}')
            flash('Błąd aktualizacji (login może być zajęty).', 'error')
        finally:
            conn.close()
        return redirect(url_for('admin.admin_ustawienia_zespol'))

    @admin_bp.route('/admin/konto/usun/<int:id>', methods=['POST'])
    @dynamic_role_required('ustawienia')
    def admin_usun_konto(id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT login, rola FROM uzytkownicy WHERE id=%s", (id,))
        row = cursor.fetchone()
        cursor.execute("DELETE FROM uzytkownicy WHERE id=%s", (id,))
        conn.commit()
        conn.close()
        if row:
            audit_log('Usunął konto użytkownika', f'login={row[0]}, rola={row[1]}')
            current_app.logger.info('Admin %s usunął konto ID=%s (login=%s)', session.get('login'), id, row[0])
        flash('Usunięto.', 'info')
        return redirect(url_for('admin.admin_ustawienia_zespol'))