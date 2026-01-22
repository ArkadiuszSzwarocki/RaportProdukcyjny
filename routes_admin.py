from flask import Blueprint, render_template, request, redirect, flash
from datetime import date
from db import get_db_connection
from werkzeug.security import generate_password_hash
# Importujemy dekorator
from decorators import admin_required

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin')
@admin_required
def admin_panel():
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT * FROM pracownicy ORDER BY imie_nazwisko"); pracownicy = cursor.fetchall()
    # Pobierz również kolumnę haslo, aby wykryć starsze formaty hashy wymagające resetu
    cursor.execute("SELECT id, login, rola, haslo FROM uzytkownicy ORDER BY login"); konta_raw = cursor.fetchall()
    # Konta przekazane do szablonu (bez hasel)
    konta = [(r[0], r[1], r[2]) for r in konta_raw]
    # Wylicz listę loginów, które mają hashe w formacie nie-pbkdf2 (np. scrypt)
    needs_reset = [r[1] for r in konta_raw if r[3] and (str(r[3]).startswith('scrypt:') or not str(r[3]).startswith('pbkdf2:'))]
    cursor.execute("SELECT id, data_planu, sekcja, produkt, tonaz, tonaz_rzeczywisty, status FROM plan_produkcji ORDER BY data_planu DESC LIMIT 50"); zlecenia = cursor.fetchall()
    cursor.execute("SELECT o.id, p.imie_nazwisko, o.typ, o.ilosc_godzin, o.komentarz FROM obecnosc o JOIN pracownicy p ON o.pracownik_id = p.id WHERE o.data_wpisu = %s", (date.today(),)); raporty_hr = cursor.fetchall()
    conn.close()
    return render_template('admin.html', pracownicy=pracownicy, konta=konta, raporty_hr=raporty_hr, dzisiaj=date.today(), zlecenia=zlecenia, needs_reset=needs_reset)

@admin_bp.route('/admin/pracownik/dodaj', methods=['POST'])
@admin_required
def admin_dodaj_pracownika():
    conn = get_db_connection(); cursor = conn.cursor(); cursor.execute("INSERT INTO pracownicy (imie_nazwisko) VALUES (%s)", (request.form['imie_nazwisko'],)); conn.commit(); conn.close(); flash("Dodano.", "success"); return redirect('/admin')

@admin_bp.route('/admin/pracownik/edytuj', methods=['POST'])
@admin_required
def admin_edytuj_pracownika():
    conn = get_db_connection(); cursor = conn.cursor(); cursor.execute("UPDATE pracownicy SET imie_nazwisko=%s WHERE id=%s", (request.form['imie_nazwisko'], request.form['id'])); conn.commit(); conn.close(); flash("Zaktualizowano.", "success"); return redirect('/admin')

@admin_bp.route('/admin/pracownik/usun/<int:id>', methods=['POST'])
@admin_required
def admin_usun_pracownika(id):
    conn = get_db_connection(); cursor = conn.cursor()
    try: cursor.execute("DELETE FROM pracownicy WHERE id=%s", (id,)); flash("Usunięto.", "info")
    except: flash("Nie można usunąć (historia).", "error")
    conn.commit(); conn.close(); return redirect('/admin')

@admin_bp.route('/admin/konto/dodaj', methods=['POST'])
@admin_required
def admin_dodaj_konto():
    conn = get_db_connection(); cursor = conn.cursor()
    try:
        pwd = request.form.get('haslo', '')
        # Używaj spójnego algorytmu PBKDF2-SHA256 przy tworzeniu nowych kont
        hashed = generate_password_hash(pwd, method='pbkdf2:sha256') if pwd else ''
        cursor.execute("INSERT INTO uzytkownicy (login, haslo, rola) VALUES (%s, %s, %s)", (request.form['login'], hashed, request.form['rola']))
        flash("Dodano.", "success")
    except: flash("Login zajęty!", "error")
    conn.commit(); conn.close(); return redirect('/admin')


@admin_bp.route('/admin/konto/edytuj', methods=['POST'])
@admin_required
def admin_edytuj_konto():
    conn = get_db_connection(); cursor = conn.cursor()
    uid = request.form.get('id')
    login = request.form.get('login')
    rola = request.form.get('rola')
    haslo = request.form.get('haslo', '').strip()
    try:
        if haslo:
            cursor.execute("UPDATE uzytkownicy SET login=%s, haslo=%s, rola=%s WHERE id=%s", (login, generate_password_hash(haslo, method='pbkdf2:sha256'), rola, uid))
        else:
            cursor.execute("UPDATE uzytkownicy SET login=%s, rola=%s WHERE id=%s", (login, rola, uid))
        conn.commit(); flash("Zaktualizowano.", "success")
    except Exception:
        conn.rollback(); flash("Błąd aktualizacji (login może być zajęty).", "error")
    conn.close(); return redirect('/admin?tab=users')

@admin_bp.route('/admin/konto/usun/<int:id>', methods=['POST'])
@admin_required
def admin_usun_konto(id):
    conn = get_db_connection(); cursor = conn.cursor(); cursor.execute("DELETE FROM uzytkownicy WHERE id=%s", (id,)); conn.commit(); conn.close(); flash("Usunięto.", "info"); return redirect('/admin')