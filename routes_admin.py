from flask import Blueprint, render_template, request, redirect, flash
from datetime import date
from db import get_db_connection
# Importujemy dekorator
from decorators import admin_required

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin')
@admin_required
def admin_panel():
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT * FROM pracownicy ORDER BY imie_nazwisko"); pracownicy = cursor.fetchall()
    cursor.execute("SELECT id, login, rola FROM uzytkownicy ORDER BY login"); konta = cursor.fetchall()
    cursor.execute("SELECT o.id, p.imie_nazwisko, o.typ, o.ilosc_godzin, o.komentarz FROM obecnosc o JOIN pracownicy p ON o.pracownik_id = p.id WHERE o.data_wpisu = %s", (date.today(),)); raporty_hr = cursor.fetchall()
    conn.close()
    return render_template('admin.html', pracownicy=pracownicy, konta=konta, raporty_hr=raporty_hr, dzisiaj=date.today())

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
    try: cursor.execute("INSERT INTO uzytkownicy (login, haslo, rola) VALUES (%s, %s, %s)", (request.form['login'], request.form['haslo'], request.form['rola'])); flash("Dodano.", "success")
    except: flash("Login zajęty!", "error")
    conn.commit(); conn.close(); return redirect('/admin')

@admin_bp.route('/admin/konto/usun/<int:id>', methods=['POST'])
@admin_required
def admin_usun_konto(id):
    conn = get_db_connection(); cursor = conn.cursor(); cursor.execute("DELETE FROM uzytkownicy WHERE id=%s", (id,)); conn.commit(); conn.close(); flash("Usunięto.", "info"); return redirect('/admin')