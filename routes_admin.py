from flask import Blueprint, render_template, request, redirect, flash
from datetime import date
from db import get_db_connection
from werkzeug.security import generate_password_hash
# Importujemy dekorator
from decorators import admin_required


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
        cursor.execute("INSERT INTO pracownicy (id, imie_nazwisko, grupa) VALUES (%s, %s, %s)", (eid, request.form['imie_nazwisko'], grupa))
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
        cursor.execute("INSERT INTO pracownicy (imie_nazwisko, grupa) VALUES (%s, %s)", (request.form['imie_nazwisko'], grupa))
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
            cursor.execute("SELECT id FROM pracownicy WHERE imie_nazwisko=%s ORDER BY id DESC LIMIT 1", (request.form['imie_nazwisko'],))
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
    cursor.execute("UPDATE pracownicy SET imie_nazwisko=%s, grupa=%s WHERE id=%s", (request.form['imie_nazwisko'], grupa, request.form['id']))
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
        login = request.form['login'].strip()
        cursor.execute("INSERT INTO uzytkownicy (login, haslo, rola, grupa) VALUES (%s, %s, %s, %s)", (login, hashed, request.form['rola'], grupa))
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
