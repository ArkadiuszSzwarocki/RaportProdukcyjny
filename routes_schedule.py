"""Schedule and roster management routes (formerly routes_api.py OBSADA section)."""

from flask import Blueprint, request, redirect, url_for, flash, session, jsonify, current_app
from datetime import date
from db import get_db_connection
from decorators import login_required, roles_required
from utils.validation import require_field

schedule_bp = Blueprint('schedule', __name__)


@schedule_bp.route('/dodaj_obecnosc', methods=['POST'])
@login_required
def dodaj_obecnosc():
    conn = get_db_connection()
    cursor = conn.cursor()
    typ = request.form.get('typ')
    pracownik_id = request.form.get('pracownik_id')
    godziny = request.form.get('godziny', 0)
    try:
        godziny_val = float(str(godziny).replace(',', '.'))
    except Exception:
        godziny_val = 0.0
    komentarz = request.form.get('komentarz', '')
    # Server-side: walidacja wymaganych pól i czytelny komunikat
    missing = []
    if not pracownik_id:
        missing.append('Pracownik')
    if not typ:
        missing.append('Typ')
    if typ == 'Wyjscie prywatne':
        od = request.form.get('wyjscie_od')
        do = request.form.get('wyjscie_do')
        if not od: missing.append('Czas (od)')
        if not do: missing.append('Czas (do)')
    if missing:
        try:
            flash('Brakuje wymaganych pól: ' + ', '.join(missing), 'warning')
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        return redirect(url_for('index'))
    # Jeśli Wyjscie prywatne — wymagamy podania zakresu czasu
    od = None
    do = None
    if typ == 'Wyjscie prywatne':
        od = request.form.get('wyjscie_od')
        do = request.form.get('wyjscie_do')
        # Dołączamy zakres czasowy do komentarza dla zapisu (kompatybilność wsteczna)
        komentarz = f"Wyjście prywatne od {od} do {do}" + (f" — {komentarz}" if komentarz else '')

    # Zapisz też osobne kolumny wyjscie_od/wyjscie_do (mogą być NULL jeśli nie dotyczy)
    cursor.execute(
        "INSERT INTO obecnosc (data_wpisu, pracownik_id, typ, ilosc_godzin, komentarz, wyjscie_od, wyjscie_do) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (date.today(), pracownik_id, typ, godziny_val, komentarz, od, do)
    )
    conn.commit()
    conn.close()
    return redirect(url_for('index'))


@schedule_bp.route('/edytuj_godziny', methods=['POST'])
@login_required
def edytuj_godziny():
    """Edytuj/liczba godzin dla danego pracownika i daty (AJAX)."""
    try:
        pracownik_id = request.form.get('pracownik_id') or request.args.get('pracownik_id')
        date_str = request.form.get('date') or request.args.get('date')
        godziny = require_field(request.form, 'godziny')
        if not pracownik_id or not date_str:
            return jsonify({'success': False, 'message': 'Brak parametrów'}), 400
        try:
            pid = int(pracownik_id)
        except Exception:
            return jsonify({'success': False, 'message': 'Nieprawidłowy pracownik'}), 400

        # Uprawnienia: właściciel może edytować swoje godziny, lider/admin może edytować inne
        try:
            my_pid = session.get('pracownik_id')
            my_role = (session.get('rola') or '').lower()
        except Exception:
            my_pid = None; my_role = ''
        if my_pid != pid and my_role not in ('lider', 'admin'):
            return jsonify({'success': False, 'message': 'Brak uprawnień'}), 403

        try:
            hours_val = float(str(godziny).replace(',', '.'))
        except Exception:
            hours_val = 0.0

        conn = get_db_connection()
        cursor = conn.cursor()
        # Sprawdź czy istnieje wiersz obecnosc dla tej daty i pracownika
        cursor.execute("SELECT id FROM obecnosc WHERE pracownik_id=%s AND data_wpisu=%s LIMIT 1", (pid, date_str))
        res = cursor.fetchone()
        if res:
            cursor.execute("UPDATE obecnosc SET ilosc_godzin=%s WHERE id=%s", (hours_val, res[0]))
        else:
            cursor.execute("INSERT INTO obecnosc (data_wpisu, pracownik_id, typ, ilosc_godzin, komentarz) VALUES (%s, %s, %s, %s, %s)", (date_str, pid, 'Obecność', hours_val, 'Edytowano ręcznie'))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Godziny zapisane'})
    except Exception:
        current_app.logger.exception('Error editing hours')
        try:
            conn.close()
        except Exception:
            pass
        return jsonify({'success': False, 'message': 'Błąd serwera'}), 500
