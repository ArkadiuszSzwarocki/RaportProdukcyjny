"""Schedule and roster management routes (formerly routes_api.py OBSADA section)."""

from flask import Blueprint, request, redirect, url_for, flash, session, jsonify, current_app
from datetime import date, datetime, timedelta
from app.db import get_db_connection
from app.decorators import login_required, roles_required
from app.utils.validation import require_field

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
        flash('Brakuje wymaganych pól: ' + ', '.join(missing), 'warning')
        return redirect(url_for('index'))
    # Jeśli Wyjscie prywatne — wymagamy podania zakresu czasu
    od = None
    do = None
    if typ == 'Wyjscie prywatne':
        od = request.form.get('wyjscie_od')
        do = request.form.get('wyjscie_do')
        # Dołączamy zakres czasowy do komentarza dla zapisu (kompatybilność wsteczna)
        komentarz = f"Wyjście prywatne od {od} do {do}" + (f" — {komentarz}" if komentarz else '')

    data_wpisu_str = request.form.get('data')
    if data_wpisu_str:
        try:
            from datetime import datetime
            data_wpisu = datetime.strptime(data_wpisu_str, '%Y-%m-%d').date()
        except:
            data_wpisu = date.today()
    else:
        data_wpisu = date.today()

    # Zapisz też osobne kolumny wyjscie_od/wyjscie_do (mogą być NULL jeśli nie dotyczy)
    cursor.execute(
        "INSERT INTO obecnosc (data_wpisu, pracownik_id, typ, ilosc_godzin, komentarz, wyjscie_od, wyjscie_do) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (data_wpisu, pracownik_id, typ, godziny_val, komentarz, od, do)
    )
    conn.commit()
    conn.close()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': 'Wpis zapisany pomyślnie'})
        
    return redirect(url_for('panels.panel_obecnosci_page'))


@schedule_bp.route('/dodaj_l4_zakres', methods=['POST'])
@login_required
@roles_required('lider', 'admin', 'zarzad')
def dodaj_l4_zakres():
    """Szybkie dodanie L4 dla pracownika na zakres dat (po jednym wpisie na dzień)."""
    pracownik_id = request.form.get('pracownik_id')
    data_od_str = request.form.get('data_od')
    data_do_str = request.form.get('data_do')
    komentarz = request.form.get('komentarz', '').strip() or 'Zwolnienie lekarskie'
    if not pracownik_id or not data_od_str or not data_do_str:
        flash('Uzupełnij wszystkie pola (pracownik, data od, data do).', 'warning')
        return redirect(url_for('panels.panel_obecnosci_page'))
    try:
        pid = int(pracownik_id)
        d_od = datetime.strptime(data_od_str, '%Y-%m-%d').date()
        d_do = datetime.strptime(data_do_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        flash('Nieprawidłowy format daty.', 'warning')
        return redirect(url_for('panels.panel_obecnosci_page'))
    if d_do < d_od:
        flash('Data końcowa musi być >= dacie początkowej.', 'warning')
        return redirect(url_for('panels.panel_obecnosci_page'))
    if (d_do - d_od).days > 365:
        flash('Zakres dat nie może przekraczać 365 dni.', 'warning')
        return redirect(url_for('panels.panel_obecnosci_page'))
    conn = get_db_connection()
    cursor = conn.cursor()
    added = 0
    cur_d = d_od
    try:
        while cur_d <= d_do:
            cursor.execute(
                "SELECT id FROM obecnosc WHERE pracownik_id=%s AND data_wpisu=%s AND typ='L4'",
                (pid, cur_d)
            )
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO obecnosc (data_wpisu, pracownik_id, typ, ilosc_godzin, komentarz) "
                    "VALUES (%s, %s, 'L4', 8, %s)",
                    (cur_d, pid, komentarz)
                )
                added += 1
            cur_d += timedelta(days=1)
        conn.commit()
        current_app.logger.info(
            f"[L4] Dodano L4 dla pracownik_id={pid} od {d_od} do {d_do}, dodano {added} wpisów"
        )
        flash(f'Dodano L4: {added} {'dzień' if added == 1 else 'dni'}.', 'success')
    except Exception as e:
        conn.rollback()
        current_app.logger.exception('Error in dodaj_l4_zakres')
        flash('Błąd podczas dodawania L4.', 'error')
    finally:
        conn.close()
    return redirect(url_for('panels.panel_obecnosci_page'))


@schedule_bp.route('/dodaj_obecnosc_zakres', methods=['POST'])
@login_required
@roles_required('lider', 'admin', 'zarzad')
def dodaj_obecnosc_zakres():
    """Dodanie dowolnego typu nieobecności dla pracownika na zakres dat (po jednym wpisie na dzień)."""
    pracownik_id = request.form.get('pracownik_id')
    data_od_str = request.form.get('data_od')
    data_do_str = request.form.get('data_do')
    typ = (request.form.get('typ') or '').strip()
    komentarz = request.form.get('komentarz', '').strip()
    try:
        godziny_val = float(str(request.form.get('godziny', 8)).replace(',', '.'))
    except (ValueError, TypeError):
        godziny_val = 8.0
    if not pracownik_id or not data_od_str or not data_do_str or not typ:
        flash('Uzupełnij wszystkie wymagane pola.', 'warning')
        return redirect(url_for('panels.panel_obecnosci_page'))
    try:
        pid = int(pracownik_id)
        d_od = datetime.strptime(data_od_str, '%Y-%m-%d').date()
        d_do = datetime.strptime(data_do_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        flash('Nieprawidłowy format daty.', 'warning')
        return redirect(url_for('panels.panel_obecnosci_page'))
    if d_do < d_od:
        flash('Data końcowa musi być >= dacie początkowej.', 'warning')
        return redirect(url_for('panels.panel_obecnosci_page'))
    if (d_do - d_od).days > 365:
        flash('Zakres dat nie może przekraczać 365 dni.', 'warning')
        return redirect(url_for('panels.panel_obecnosci_page'))
    conn = get_db_connection()
    cursor = conn.cursor()
    added = 0
    cur_d = d_od
    try:
        while cur_d <= d_do:
            cursor.execute(
                "SELECT id FROM obecnosc WHERE pracownik_id=%s AND data_wpisu=%s AND typ=%s",
                (pid, cur_d, typ)
            )
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO obecnosc (data_wpisu, pracownik_id, typ, ilosc_godzin, komentarz) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (cur_d, pid, typ, godziny_val, komentarz)
                )
                added += 1
            cur_d += timedelta(days=1)
        conn.commit()
        current_app.logger.info(
            f"[OBECNOSC_ZAKRES] Dodano {typ} dla pracownik_id={pid} od {d_od} do {d_do}, {added} wpisów"
        )
        flash(f'Dodano {typ}: {added} {"dzień" if added == 1 else "dni"}.', 'success')
    except Exception:
        conn.rollback()
        current_app.logger.exception('Error in dodaj_obecnosc_zakres')
        flash('Błąd podczas dodawania wpisu.', 'error')
    finally:
        conn.close()
    return redirect(url_for('panels.panel_obecnosci_page'))


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
    except Exception as e:
        current_app.logger.error(f'Error editing hours: {e}', exc_info=True)
        return jsonify({'success': False, 'message': 'Błąd serwera'}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


