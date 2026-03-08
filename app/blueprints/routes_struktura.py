from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.db import get_db_connection
from app.decorators import login_required, zarzad_required

struktura_bp = Blueprint('struktura', __name__, url_prefix='/struktura')

DEFAULT_DEPARTMENTS = ('Handel', 'Laboratorium', 'Produkcja', 'Transport')


def _ensure_default_departments(cursor):
    for department_name in DEFAULT_DEPARTMENTS:
        cursor.execute("INSERT IGNORE INTO dzialy (nazwa) VALUES (%s)", (department_name,))


def _get_departments(cursor):
    cursor.execute("SELECT id, nazwa, lider_id FROM dzialy")
    all_departments = cursor.fetchall()
    
    # Sortowanie: najpierw domyślne w kolejności DEFAULT_DEPARTMENTS, nast. reszta wg alfabetu
    def dept_sort_key(dept):
        try:
            order = DEFAULT_DEPARTMENTS.index(dept['nazwa'])
            return (0, order)
        except ValueError:
            return (1, dept['nazwa'])
            
    all_departments.sort(key=dept_sort_key)
    return all_departments


def _get_board_members(cursor):
    cursor.execute(
        """
        SELECT p.id, p.imie_nazwisko, u.rola, p.dzial_id, p.przelozony_id
        FROM pracownicy p
        JOIN uzytkownicy u ON u.pracownik_id = p.id
        WHERE u.rola IN ('zarzad', 'admin')
        ORDER BY p.imie_nazwisko
        """
    )
    return cursor.fetchall()


def _get_all_employees(cursor):
    cursor.execute(
        """
        SELECT p.id,
               p.imie_nazwisko,
               COALESCE(NULLIF(u.rola, ''), 'pracownik') AS rola,
               p.dzial_id,
               p.przelozony_id
        FROM pracownicy p
        LEFT JOIN uzytkownicy u ON u.pracownik_id = p.id
        ORDER BY p.imie_nazwisko
        """
    )
    return cursor.fetchall()


def _build_structure_view_model(cursor):
    _ensure_default_departments(cursor)

    board_members = _get_board_members(cursor)
    employees = _get_all_employees(cursor)
    departments = _get_departments(cursor)

    employee_by_id = {employee['id']: employee for employee in employees}
    board_ids = {member['id'] for member in board_members}

    departments_view = []
    for department in departments:
        # Znalezienie wszystkich liderów w tym dziale
        liderzy = [
            emp for emp in employees
            if emp['dzial_id'] == department['id'] and emp['rola'] == 'lider'
        ]
        liderzy.sort(key=lambda employee: employee['imie_nazwisko'])
        liderzy_ids = {l['id'] for l in liderzy}
        
        # Główni liderzy to ci, którzy nie mają przełożonego będącego innym liderem w tym dziale
        glowni_liderzy = [l for l in liderzy if l['przelozony_id'] not in liderzy_ids]
        
        zespoly = []
        for glowny in glowni_liderzy:
            wspolliderzy = [l for l in liderzy if l['przelozony_id'] == glowny['id']]
            
            team_leaders = [glowny] + wspolliderzy
            team_leader_ids = {l['id'] for l in team_leaders}

            members = [
                employee for employee in employees
                if employee['przelozony_id'] in team_leader_ids
                and employee['id'] not in team_leader_ids
                and employee['rola'] != 'lider'
            ]
            members.sort(key=lambda employee: employee['imie_nazwisko'])
            member_ids = {member['id'] for member in members}

            member_options = [
                employee for employee in employees
                if employee['id'] not in board_ids
                and employee['rola'] != 'lider'
                and employee['id'] not in team_leader_ids
                and employee['id'] not in member_ids
            ]
            member_options.sort(key=lambda employee: employee['imie_nazwisko'])

            zespoly.append({
                'liderzy': team_leaders,
                'glowny_lider_id': glowny['id'],
                'members': members,
                'member_options': member_options,
            })

        leader_options = [
            employee for employee in employees
            if employee['id'] not in board_ids
            and employee['id'] not in liderzy_ids
        ]
        leader_options.sort(key=lambda employee: employee['imie_nazwisko'])

        nieprzypisani = [
            employee for employee in employees
            if employee['dzial_id'] == department['id']
            and employee['rola'] not in ['zarzad', 'admin', 'lider']
            and not any(employee['przelozony_id'] == l['id'] for l in liderzy)
        ]

        departments_view.append({
            'id': department['id'],
            'nazwa': department['nazwa'],
            'zespoly': zespoly,
            'leader_options': leader_options,
            'nieprzypisani': nieprzypisani
        })

    return board_members, departments_view

@struktura_bp.route('/', methods=['GET'])
@login_required
def widok_struktury():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        zarzad, departments = _build_structure_view_model(cursor)
        return render_template(
            'struktura.html',
            zarzad=zarzad,
            departments=departments,
            rola=session.get('rola'),
            can_manage=session.get('rola') in ['admin', 'zarzad']
        )
    except Exception as e:
        flash(f"Błąd ładowania struktury: {str(e)}", "danger")
        return redirect(url_for('admin.admin_ustawienia'))
    finally:
        conn.close()

@struktura_bp.route('/dzialy/dodaj', methods=['POST'])
@zarzad_required
def dodaj_dzial():
    nazwa = request.form.get('nazwa')
    if not nazwa:
        flash("Nazwa działu jest wymagana.", "warning")
        return redirect(url_for('struktura.widok_struktury'))

    nazwa = nazwa.strip()
    if nazwa in DEFAULT_DEPARTMENTS:
        flash("Ten pion już istnieje w strukturze.", "info")
        return redirect(url_for('struktura.widok_struktury'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO dzialy (nazwa) VALUES (%s)", (nazwa,))
        conn.commit()
        flash(f"Dodano nowy dział: {nazwa}", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Błąd przy dodawaniu działu: {str(e)}", "danger")
    finally:
        conn.close()
    return redirect(url_for('struktura.widok_struktury'))

@struktura_bp.route('/dzialy/edytuj/<int:dzial_id>', methods=['POST'])
@zarzad_required
def edytuj_dzial(dzial_id):
    nazwa = request.form.get('nazwa')
    if not nazwa:
        flash("Nazwa działu jest wymagana.", "warning")
        return redirect(url_for('struktura.widok_struktury'))

    nazwa = nazwa.strip()
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT nazwa FROM dzialy WHERE id = %s", (dzial_id,))
        department = cursor.fetchone()
        if not department:
            flash("Nie znaleziono działu.", "warning")
            return redirect(url_for('struktura.widok_struktury'))
        if department['nazwa'] in DEFAULT_DEPARTMENTS:
            flash("Nazwy podstawowych pionów są stałe.", "warning")
            return redirect(url_for('struktura.widok_struktury'))
        cursor.execute("UPDATE dzialy SET nazwa = %s WHERE id = %s", (nazwa, dzial_id))
        conn.commit()
        flash("Dział zaktualizowany.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Błąd przy edycji działu: {str(e)}", "danger")
    finally:
        conn.close()
    return redirect(url_for('struktura.widok_struktury'))

@struktura_bp.route('/dzialy/usun/<int:dzial_id>', methods=['POST'])
@zarzad_required
def usun_dzial(dzial_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT nazwa FROM dzialy WHERE id = %s", (dzial_id,))
        department = cursor.fetchone()
        if not department:
            flash("Nie znaleziono działu.", "warning")
            return redirect(url_for('struktura.widok_struktury'))
        if department['nazwa'] in DEFAULT_DEPARTMENTS:
            flash("Podstawowe piony nie mogą zostać usunięte.", "warning")
            return redirect(url_for('struktura.widok_struktury'))
        cursor.execute("DELETE FROM dzialy WHERE id = %s", (dzial_id,))
        conn.commit()
        flash("Dział usunięty.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Błąd przy usuwaniu działu (często powiązany z przypisanymi pracownikami): {str(e)}", "danger")
    finally:
        conn.close()
    return redirect(url_for('struktura.widok_struktury'))

@struktura_bp.route('/pracownik/przypisz/<int:pracownik_id>', methods=['POST'])
@zarzad_required
def przypisz_pracownika(pracownik_id):
    dzial_id = request.form.get('dzial_id')
    rola = request.form.get('rola')
    przelozony_id = request.form.get('przelozony_id')

    dzial_id = int(dzial_id) if dzial_id and str(dzial_id).isdigit() else None
    przelozony_id = int(przelozony_id) if przelozony_id and str(przelozony_id).isdigit() else None

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("UPDATE pracownicy SET dzial_id = %s, przelozony_id = %s WHERE id = %s", (dzial_id, przelozony_id, pracownik_id))

        cursor.execute("SELECT id FROM uzytkownicy WHERE pracownik_id = %s", (pracownik_id,))
        u = cursor.fetchone()

        if u:
            if rola:
                cursor.execute("UPDATE uzytkownicy SET rola = %s WHERE id = %s", (rola, u['id']))
        else:
            if rola and rola != 'pracownik':
                flash("Pracownik nie posiada powiązanego loginu. Zmieniono Dział, ale Rola wymaga konta w systemie (stwórz je w module Użytkownicy).", "warning")

        conn.commit()
        if not (not u and rola and rola != 'pracownik'):
            flash("Zaktualizowano pozycję pracownika w strukturze.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Błąd przypisania: {str(e)}", "danger")
    finally:
        conn.close()

    return redirect(url_for('struktura.widok_struktury'))


@struktura_bp.route('/dzial/<int:dzial_id>/lider/dodaj', methods=['POST'])
@zarzad_required
def dodaj_lidera_dzialu(dzial_id):
    lider_id_raw = request.form.get('lider_id')
    lider_id = int(lider_id_raw) if lider_id_raw and str(lider_id_raw).isdigit() else None

    if not lider_id:
        flash("Musisz wybrać osobę by przypisać jako lidera.", "warning")
        return redirect(url_for('struktura.widok_struktury'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        _ensure_default_departments(cursor)
        cursor.execute("SELECT id, nazwa FROM dzialy WHERE id = %s", (dzial_id,))
        department = cursor.fetchone()
        if not department:
            flash("Nie znaleziono pionu.", "warning")
            return redirect(url_for('struktura.widok_struktury'))

        cursor.execute("SELECT id, imie_nazwisko FROM pracownicy WHERE id = %s", (lider_id,))
        leader = cursor.fetchone()
        if not leader:
            flash("Wybrany pracownik nie istnieje.", "warning")
            return redirect(url_for('struktura.widok_struktury'))

        cursor.execute("SELECT id, rola FROM uzytkownicy WHERE pracownik_id = %s", (lider_id,))
        u = cursor.fetchone()
        if u:
            if u['rola'] in ['zarzad', 'admin']:
                flash("Członek zarządu nie może zostać pomniejszony do lidera pionu.", "warning")
                return redirect(url_for('struktura.widok_struktury'))
            cursor.execute("UPDATE uzytkownicy SET rola = 'lider' WHERE id = %s", (u['id'],))

        cursor.execute("UPDATE pracownicy SET dzial_id = %s, przelozony_id = NULL WHERE id = %s", (dzial_id, lider_id))
        conn.commit()
        flash(f"Dodano menedżera {leader['imie_nazwisko']} jako Lidera do pionu {department['nazwa']}.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Błąd ustawiania lidera: {str(e)}", "danger")
    finally:
        conn.close()

    return redirect(url_for('struktura.widok_struktury'))


@struktura_bp.route('/dzial/<int:dzial_id>/lider/usun', methods=['POST'])
@zarzad_required
def usun_lidera_dzialu(dzial_id):
    lider_id_raw = request.form.get('lider_id')
    lider_id = int(lider_id_raw) if lider_id_raw and str(lider_id_raw).isdigit() else None

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT przelozony_id FROM pracownicy WHERE id = %s", (lider_id,))
        zwalniany = cursor.fetchone()
        szef_id = zwalniany['przelozony_id'] if zwalniany else None

        cursor.execute("UPDATE pracownicy SET dzial_id = NULL WHERE id = %s AND dzial_id = %s", (lider_id, dzial_id))
        
        if szef_id:
            cursor.execute("UPDATE pracownicy SET przelozony_id = %s WHERE przelozony_id = %s", (szef_id, lider_id))
        else:
            cursor.execute("UPDATE pracownicy SET przelozony_id = NULL WHERE przelozony_id = %s", (lider_id,))
            
        conn.commit()
        flash(f"Odłączono lidera z pionu. Przełożeni jego podwładnych zostali rozszadani automatycznie.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Błąd odpinania lidera: {str(e)}", "danger")
    finally:
        conn.close()

    return redirect(url_for('struktura.widok_struktury'))


@struktura_bp.route('/lider/<int:lider_id>/wspollider/dodaj', methods=['POST'])
@zarzad_required
def dodaj_wspollidera(lider_id):
    wspollider_id_raw = request.form.get('wspollider_id')
    wspollider_id = int(wspollider_id_raw) if wspollider_id_raw and str(wspollider_id_raw).isdigit() else None

    if not wspollider_id:
        flash("Musisz wybrać osobę z oddziału by przypisać jako współlidera.", "warning")
        return redirect(url_for('struktura.widok_struktury'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id, dzial_id, imie_nazwisko FROM pracownicy WHERE id = %s", (lider_id,))
        glowny_lider = cursor.fetchone()
        if not glowny_lider:
            flash("Główny lider nie istnieje.", "warning")
            return redirect(url_for('struktura.widok_struktury'))

        cursor.execute("SELECT id, imie_nazwisko FROM pracownicy WHERE id = %s", (wspollider_id,))
        new_leader = cursor.fetchone()
        if not new_leader:
            flash("Wybrany pracownik nie istnieje.", "warning")
            return redirect(url_for('struktura.widok_struktury'))

        cursor.execute("SELECT id, rola FROM uzytkownicy WHERE pracownik_id = %s", (wspollider_id,))
        u = cursor.fetchone()
        if u:
            if u['rola'] in ['zarzad', 'admin']:
                flash("Członek zarządu nie może zostać pomniejszony do współlidera.", "warning")
                return redirect(url_for('struktura.widok_struktury'))
            cursor.execute("UPDATE uzytkownicy SET rola = 'lider' WHERE id = %s", (u['id'],))

        cursor.execute(
            "UPDATE pracownicy SET dzial_id = %s, przelozony_id = %s WHERE id = %s", 
            (glowny_lider['dzial_id'], lider_id, wspollider_id)
        )
        conn.commit()
        flash(f"Dodano menedżera {new_leader['imie_nazwisko']} jako Współlidera do zespołu Głównego Lidera {glowny_lider['imie_nazwisko']}.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Błąd ustawiania współlidera: {str(e)}", "danger")
    finally:
        conn.close()

    return redirect(url_for('struktura.widok_struktury'))


@struktura_bp.route('/lider/<int:lider_id>/pracownicy/dodaj', methods=['POST'])
@zarzad_required
def dodaj_pracownika_do_lidera(lider_id):
    pracownik_id_raw = request.form.get('pracownik_id')
    pracownik_id = int(pracownik_id_raw) if pracownik_id_raw and str(pracownik_id_raw).isdigit() else None
    
    if not pracownik_id:
        flash("Wybierz pracownika z listy.", "warning")
        return redirect(url_for('struktura.widok_struktury'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id, dzial_id FROM pracownicy WHERE id = %s", (lider_id,))
        lid = cursor.fetchone()
        if not lid:
            flash("Lider nie istnieje w bazie.", "warning")
            return redirect(url_for('struktura.widok_struktury'))

        cursor.execute("SELECT id, imie_nazwisko FROM pracownicy WHERE id = %s", (pracownik_id,))
        employee = cursor.fetchone()
        if not employee:
            flash("Wybrany pracownik nie istnieje.", "warning")
            return redirect(url_for('struktura.widok_struktury'))

        cursor.execute("SELECT 1 FROM uzytkownicy WHERE pracownik_id = %s AND rola IN ('admin', 'zarzad')", (pracownik_id,))
        if cursor.fetchone():
            flash("Członek zarządu nie może podlegać kierownictwu pionu.", "warning")
            return redirect(url_for('struktura.widok_struktury'))

        cursor.execute(
            "UPDATE pracownicy SET dzial_id = %s, przelozony_id = %s WHERE id = %s",
            (lid['dzial_id'], lider_id, pracownik_id)
        )
        conn.commit()
        flash(f"Dodano pracownika {employee['imie_nazwisko']} do zespołu.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Błąd przypisywania pracownika: {str(e)}", "danger")
    finally:
        conn.close()

    return redirect(url_for('struktura.widok_struktury'))


@struktura_bp.route('/pracownik/<int:pracownik_id>/odlacz', methods=['POST'])
@zarzad_required
def odlacz_pracownika(pracownik_id):
    calkowicie_z_dzialu = request.form.get('calkowite_usuniecie')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id, imie_nazwisko FROM pracownicy WHERE id = %s", (pracownik_id,))
        employee = cursor.fetchone()
        if not employee:
            flash("Nie znaleziono pracownika.", "warning")
            return redirect(url_for('struktura.widok_struktury'))

        if calkowicie_z_dzialu == '1':
            cursor.execute("UPDATE pracownicy SET przelozony_id = NULL, dzial_id = NULL WHERE id = %s", (pracownik_id,))
            flash(f"Wyrzucono pracownika {employee['imie_nazwisko']} całkowicie ze struktur pionowych.", "success")
        else:
            cursor.execute("UPDATE pracownicy SET przelozony_id = NULL WHERE id = %s", (pracownik_id,))
            flash(f"Odpięto pracownika {employee['imie_nazwisko']} z zespołu. Znajduje się teraz w puli wolnych rąk tego pionu.", "success")
            
        conn.commit()
    except Exception as e:
        conn.rollback()
        flash(f"Błąd odpinania pracownika: {str(e)}", "danger")
    finally:
        conn.close()

    return redirect(url_for('struktura.widok_struktury'))
