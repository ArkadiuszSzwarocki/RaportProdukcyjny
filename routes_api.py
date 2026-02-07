from flask import Blueprint, request, redirect, url_for, flash, session, render_template, current_app, jsonify, send_file
from utils.validation import require_field
import logging
import json
import os
import sys
import zipfile
from datetime import date, datetime, timedelta, time
from io import BytesIO
from db import get_db_connection, rollover_unfinished, log_plan_history
from dto.paleta import PaletaDTO
from decorators import login_required, roles_required
from services.raport_service import RaportService

api_bp = Blueprint('api', __name__)

def bezpieczny_powrot():
    """Wraca do Planisty jeśli to on klikał, w przeciwnym razie na Dashboard"""
    if session.get('rola') == 'planista' or request.form.get('widok_powrotu') == 'planista':
        data = request.form.get('data_powrotu') or request.args.get('data') or str(date.today())
        return url_for('planista.panel_planisty', data=data)
    
    # Try to get sekcja from query string first (URL parameters), then from form
    sekcja = request.args.get('sekcja') or request.form.get('sekcja', 'Zasyp')
    data = request.form.get('data_powrotu') or request.args.get('data') or str(date.today())
    return url_for('index', sekcja=sekcja, data=data)

# ================= LANGUAGE SETTINGS =================

@api_bp.route('/set_language', methods=['POST'])
@login_required
def set_language():
    """Zmień język interfejsu aplikacji"""
    try:
        from flask import make_response
        
        data = request.get_json()
        language = data.get('language', 'pl')
        
        # Walidacja języka
        if language not in ['pl', 'uk', 'en']:
            language = 'pl'
        
        session['app_language'] = language
        session.modified = True
        
        # Odpowiedź z cookie
        response = jsonify({
            'success': True,
            'message': f'Język zmieniony na {language}',
            'language': language
        })
        # Ustaw cookie na 365 dni
        response.set_cookie('app_language', language, max_age=365*24*60*60, path='/')
        
        current_app.logger.info(f'Language changed to {language} for user {session.get("login")}')
        
        return response
    except Exception as e:
        current_app.logger.error(f'Error changing language: {e}')
        return jsonify({
            'success': False,
            'message': f'Błąd: {str(e)}'
        }), 400

# ================= DZIENNIK =================

@api_bp.route('/dodaj_wpis', methods=['POST'])
@login_required
def dodaj_wpis():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        from utils.validation import require_field, optional_field
        sekcja = require_field(request.form, 'sekcja')
        kategoria = require_field(request.form, 'kategoria')
        problem = optional_field(request.form, 'problem', default=None)
        pracownik_id = session.get('pracownik_id')
        # Automatyczne wartości: data i czas z bazy, status='zgłoszone' (domyślnie dla nowych)
        # Ustawiamy status_zglosnienia=NULL aby pokazać że kolumna jest deprecated
        cursor.execute("INSERT INTO dziennik_zmiany (data_wpisu, sekcja, problem, czas_start, status, kategoria, status_zglosnienia, pracownik_id) VALUES (%s, %s, %s, NOW(), 'zgłoszone', %s, NULL, %s)", 
                       (date.today(), sekcja, problem, kategoria, pracownik_id))
        conn.commit()
        conn.close()
        # Zwróć JSON dla AJAX
        return jsonify({'success': True, 'message': '✓ Awarię dodano pomyślnie'}), 200
    except Exception as e:
        conn.close()
        current_app.logger.error(f"Błąd przy dodawaniu wpisu: {str(e)}")
        # Zwróć JSON z błędem dla AJAX
        return jsonify({'success': False, 'message': f'❌ Błąd: {str(e)}'}), 400

@api_bp.route('/usun_wpis/<int:id>', methods=['POST'])
@login_required
def usun_wpis(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM dziennik_zmiany WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect(bezpieczny_powrot())

@api_bp.route('/edytuj/<int:id>', methods=['GET', 'POST'])
@login_required
def edytuj(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if request.method == 'POST':
            # If no end time provided when editing, set end time to now (click time)
            czas_start_val = request.form.get('czas_start') or None
            czas_stop_form = request.form.get('czas_stop')
            if czas_stop_form:
                czas_stop_val = czas_stop_form
            else:
                # set to current datetime — DB column accepts time/datetime
                from datetime import datetime as _dt
                czas_stop_val = _dt.now()
            
            status = request.form.get('status', 'w_trakcie_naprawy')
            data_zakonczenia = request.form.get('data_zakonczenia') or None

            cursor.execute(
                "UPDATE dziennik_zmiany SET problem=%s, kategoria=%s, czas_start=%s, czas_stop=%s, status=%s, data_zakonczenia=%s WHERE id=%s",
                (request.form.get('problem'), request.form.get('kategoria'), czas_start_val, czas_stop_val, status, data_zakonczenia, id)
            )
            conn.commit()
            conn.close()
            return redirect('/')

        cursor.execute("SELECT * FROM dziennik_zmiany WHERE id = %s", (id,))
        wpis = cursor.fetchone()
        if not wpis:
            # brak wpisu — przyjazne przekierowanie
            conn.close()
            from flask import flash
            flash('Wpis nie został odnaleziony.', 'warning')
            return redirect(bezpieczny_powrot())

        # Format time fields for the template (HH:MM). db may return timedelta or datetime
        wpis_display = list(wpis)
        for ti in (4, 5):
            try:
                val = wpis[ti]
                if val is None:
                    wpis_display[ti] = ''
                elif isinstance(val, datetime):
                    wpis_display[ti] = val.strftime('%H:%M')
                elif isinstance(val, time):
                    wpis_display[ti] = val.strftime('%H:%M')
                elif isinstance(val, timedelta):
                    total_seconds = int(val.total_seconds())
                    h = total_seconds // 3600
                    m = (total_seconds % 3600) // 60
                    wpis_display[ti] = f"{h:02d}:{m:02d}"
                else:
                    # fallback to string, try to extract HH:MM
                    s = str(val)
                    if ':' in s:
                        parts = s.split(':')
                        wpis_display[ti] = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
                    else:
                        wpis_display[ti] = s
            except Exception:
                wpis_display[ti] = ''

        conn.close()
        return render_template('edycja.html', wpis=wpis_display)
    except Exception:
        # Zaloguj i pokaż przyjazny komunikat zamiast 500
        app = None
        try:
            from flask import current_app
            app = current_app._get_current_object()
            app.logger.exception('Error in edytuj endpoint for id=%s', id)
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        from flask import flash
        flash('Wystąpił błąd podczas ładowania wpisu.', 'danger')


# Ręczne wyzwalanie przypomnień dla niepotwierdzonych palet
@api_bp.route('/remind_unconfirmed_palety', methods=['POST'])
@roles_required('lider', 'admin')
def remind_unconfirmed_palety():
    try:
        try:
            threshold = int(request.form.get('threshold_minutes', 10))
        except Exception:
            threshold = 10
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT pw.id, pw.plan_id, p.produkt, pw.data_dodania FROM palety_workowanie pw JOIN plan_produkcji p ON pw.plan_id = p.id WHERE pw.waga = 0 AND TIMESTAMPDIFF(MINUTE, pw.data_dodania, NOW()) >= %s",
            (threshold,)
        )
        raw = cursor.fetchall()
        rows = []
        for r in raw:
            # map tuple (id, plan_id, produkt, data_dodania) explicitly
            dto = PaletaDTO.from_db_row(r, columns=('id', 'plan_id', 'produkt', 'data_dodania'))
            dt = dto.data_dodania
            try:
                sdt = dt.strftime('%Y-%m-%d %H:%M:%S') if hasattr(dt, 'strftime') else str(dt)
            except Exception:
                sdt = str(dt)
            rows.append((dto.id, dto.plan_id, dto.produkt, sdt))
        conn.close()

        palety_logger = logging.getLogger('palety_logger')
        count = 0
        for r in rows:
            msg = f"Manual reminder: Niepotwierdzona paleta id={r[0]}, plan_id={r[1]}, produkt={r[2]}, dodana={r[3]} - brak potwierdzenia >= {threshold}min"
            palety_logger.warning(msg)
            try:
                current_app.logger.warning(msg)
            except Exception:
                pass
            count += 1

        # Jeśli żądanie JSON, zwróć JSON, inaczej przekieruj z komunikatem
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'reminded': count})
        flash(f'Wysłano przypomnienia dla {count} palet.', 'info')
        return redirect(bezpieczny_powrot())
    except Exception:
        current_app.logger.exception('Error in remind_unconfirmed_palety')
        flash('Wystąpił błąd podczas wysyłania przypomnień.', 'danger')
        return redirect(bezpieczny_powrot())
        return redirect(bezpieczny_powrot())


@api_bp.route('/ustawienia', methods=['GET'])
@login_required
def ustawienia():
    """Prosty widok ustawień (placeholder)."""
    try:
        return render_template('ustawienia.html')
    except Exception:
        from flask import flash
        flash('Nie można otworzyć strony ustawień.', 'danger')
        return redirect('/')

@api_bp.route('/zapisz_tonaz_deprecated/<int:id>', methods=['POST'])
def zapisz_tonaz_deprecated(id): return redirect(bezpieczny_powrot())

# ================= OBSADA I INNE =================
@api_bp.route('/dodaj_obecnosc', methods=['POST'])
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
        return redirect(bezpieczny_powrot())
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
    return redirect(bezpieczny_powrot())


@api_bp.route('/edytuj_godziny', methods=['POST'])
@login_required
def edytuj_godziny():
    """Edytuj/liczba godzin dla danego pracownika i daty (AJAX)."""
    try:
        pracownik_id = request.form.get('pracownik_id') or request.args.get('pracownik_id')
        date_str = request.form.get('date') or request.args.get('date')
        from utils.validation import require_field
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


# =============== WNIOSKI O WOLNE ================
@api_bp.route('/wnioski/submit', methods=['POST'])
@login_required
def submit_wniosek():
    conn = get_db_connection()
    cursor = conn.cursor()
    pid = session.get('pracownik_id') or request.form.get('pracownik_id')
    if not pid:
        try:
            flash('Brak przypisanego pracownika do konta. Skontaktuj się z administratorem.', 'warning')
        except Exception:
            pass
        return redirect(bezpieczny_powrot())

    typ = request.form.get('typ') or 'Urlop'
    data_od = request.form.get('data_od')
    data_do = request.form.get('data_do')
    czas_od = request.form.get('czas_od') or None
    czas_do = request.form.get('czas_do') or None
    powod = request.form.get('powod') or ''

    # Jeśli to Wyjście prywatne — akceptujemy również pojedynczy dzień (data_do może być pusta)
    if typ and typ.lower().startswith('wyj'):
        if not data_od:
            try:
                flash('Podaj datę wniosku.', 'warning')
            except Exception:
                pass
            return redirect(bezpieczny_powrot())
        # jeśli brak data_do, ustawiamy na tę samą datę (pojedynczy dzień z godzinami)
        if not data_do:
            data_do = data_od
    else:
        if not data_od or not data_do:
            try:
                flash('Podaj zakres dat wniosku.', 'warning')
            except Exception:
                pass
            return redirect(bezpieczny_powrot())

    cursor.execute("INSERT INTO wnioski_wolne (pracownik_id, typ, data_od, data_do, czas_od, czas_do, powod) VALUES (%s, %s, %s, %s, %s, %s, %s)", (pid, typ, data_od, data_do, czas_od, czas_do, powod))
    conn.commit()
    conn.close()
    try:
        flash('Wniosek złożony pomyślnie.', 'success')
    except Exception:
        pass
    return redirect(url_for('moje_godziny'))


@api_bp.route('/wnioski/<int:wid>/approve', methods=['POST'])
@roles_required('lider', 'admin')
def approve_wniosek(wid):
    conn = get_db_connection()
    cursor = conn.cursor()
    lider_pid = session.get('pracownik_id')
    cursor.execute("UPDATE wnioski_wolne SET status='approved', decyzja_dnia=NOW(), lider_id=%s WHERE id=%s", (lider_pid, wid))
    conn.commit()
    # After approving, increment employee's leave counters by number of days in the request
    try:
        cursor.execute("SELECT pracownik_id, data_od, data_do, typ FROM wnioski_wolne WHERE id=%s", (wid,))
        r = cursor.fetchone()
        if r:
            pid = int(r[0])
            data_od = r[1]
            data_do = r[2]
            typ = (r[3] or '').lower()
            # compute inclusive days
            try:
                days = (data_do - data_od).days + 1 if (data_od and data_do) else 0
            except Exception:
                days = 0
            if days > 0:
                # Ensure columns exist (best-effort)
                try:
                    cursor.execute("ALTER TABLE pracownicy ADD COLUMN IF NOT EXISTS urlop_biezacy INT DEFAULT 0")
                    cursor.execute("ALTER TABLE pracownicy ADD COLUMN IF NOT EXISTS urlop_zalegly INT DEFAULT 0")
                except Exception:
                    # some MySQL versions may not support IF NOT EXISTS; ignore errors
                    try:
                        cursor.execute("ALTER TABLE pracownicy ADD COLUMN urlop_biezacy INT DEFAULT 0")
                        cursor.execute("ALTER TABLE pracownicy ADD COLUMN urlop_zalegly INT DEFAULT 0")
                    except Exception:
                        pass
                # Decide which counter to increment — default to current-year ('urlop_biezacy')
                if 'zaleg' in typ:
                    cursor.execute("UPDATE pracownicy SET urlop_zalegly = COALESCE(urlop_zalegly,0) + %s WHERE id=%s", (days, pid))
                else:
                    cursor.execute("UPDATE pracownicy SET urlop_biezacy = COALESCE(urlop_biezacy,0) + %s WHERE id=%s", (days, pid))
                conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
    conn.close()
    try:
        flash('Wniosek zatwierdzony.', 'success')
    except Exception:
        pass
    # If this is an AJAX request, return JSON instead of redirect
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('Accept', '').find('application/json') != -1:
        return jsonify({'success': True, 'message': 'Wniosek zatwierdzony.'})
    return redirect(bezpieczny_powrot())


@api_bp.route('/wnioski/<int:wid>/reject', methods=['POST'])
@roles_required('lider', 'admin')
def reject_wniosek(wid):
    conn = get_db_connection()
    cursor = conn.cursor()
    lider_pid = session.get('pracownik_id')
    cursor.execute("UPDATE wnioski_wolne SET status='rejected', decyzja_dnia=NOW(), lider_id=%s WHERE id=%s", (lider_pid, wid))
    conn.commit()
    conn.close()
    try:
        flash('Wniosek odrzucony.', 'info')
    except Exception:
        pass
    # If this is an AJAX request, return JSON instead of redirect
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('Accept', '').find('application/json') != -1:
        return jsonify({'success': True, 'message': 'Wniosek odrzucony.'})
    return redirect(bezpieczny_powrot())


@api_bp.route('/wnioski/day', methods=['GET'])
@roles_required('lider', 'admin')
def wnioski_for_day():
    """Zwraca JSON listę wniosków dla danego pracownika i daty (YYYY-MM-DD)."""
    pracownik_id = request.args.get('pracownik_id')
    date_str = request.args.get('date')
    try:
        if not pracownik_id or not date_str:
            return jsonify({'error': 'missing parameters'}), 400
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, typ, data_od, data_do, czas_od, czas_do, powod, status, zlozono FROM wnioski_wolne WHERE pracownik_id=%s AND data_od <= %s AND data_do >= %s ORDER BY zlozono DESC", (pracownik_id, date_str, date_str))
        rows = cursor.fetchall()
        conn.close()
        items = []
        for r in rows:
            items.append({'id': r[0], 'typ': r[1], 'data_od': str(r[2]), 'data_do': str(r[3]), 'czas_od': str(r[4]) if r[4] else None, 'czas_do': str(r[5]) if r[5] else None, 'powod': r[6], 'status': r[7], 'zlozono': str(r[8])})
        return jsonify({'wnioski': items})
    except Exception:
        current_app.logger.exception('Error fetching wnioski for day')
        try:
            conn.close()
        except Exception:
            pass
        return jsonify({'error': 'server error'}), 500


@api_bp.route('/wnioski/summary', methods=['GET'])
@login_required
def wnioski_summary():
    """Zwraca JSON z podsumowaniem godzin dla pracownika (obecnosci, wyjscia_hours, typy)"""
    try:
        pracownik_id = request.args.get('pracownik_id') or session.get('pracownik_id')
        if not pracownik_id:
            return jsonify({'error': 'missing pracownik_id'}), 400
        try:
            pid = int(pracownik_id)
        except Exception:
            return jsonify({'error': 'invalid pracownik_id'}), 400

        # zakres: obecny miesiąc
        from datetime import datetime, date
        teraz = datetime.now()
        d_od = date(teraz.year, teraz.month, 1)
        d_do = date(teraz.year, teraz.month, teraz.day)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(1) FROM obsada_zmiany WHERE pracownik_id=%s AND data_wpisu BETWEEN %s AND %s", (pid, d_od, d_do))
        obecnosci = int(cursor.fetchone()[0] or 0)

        cursor.execute("SELECT COALESCE(typ, ''), COALESCE(SUM(ilosc_godzin),0) FROM obecnosc WHERE pracownik_id=%s AND data_wpisu BETWEEN %s AND %s GROUP BY typ", (pid, d_od, d_do))
        typy = {r[0]: float(r[1] or 0) for r in cursor.fetchall()}

        try:
            cursor.execute("SELECT COALESCE(SUM(TIME_TO_SEC(wyjscie_do)-TIME_TO_SEC(wyjscie_od))/3600,0) FROM obecnosc WHERE pracownik_id=%s AND typ='Wyjscie prywatne' AND data_wpisu BETWEEN %s AND %s", (pid, d_od, d_do))
            wyjscia_hours = float(cursor.fetchone()[0] or 0)
        except Exception:
            wyjscia_hours = 0.0

        # also include leave counters from pracownicy (if available)
        try:
            cursor.execute("SELECT COALESCE(urlop_biezacy,0), COALESCE(urlop_zalegly,0) FROM pracownicy WHERE id=%s", (pid,))
            rr = cursor.fetchone()
            urlop_biezacy = int(rr[0] or 0) if rr else 0
            urlop_zalegly = int(rr[1] or 0) if rr else 0
        except Exception:
            urlop_biezacy = 0
            urlop_zalegly = 0
        conn.close()
        return jsonify({'obecnosci': obecnosci, 'typy': typy, 'wyjscia_hours': wyjscia_hours, 'urlop_biezacy': urlop_biezacy, 'urlop_zalegly': urlop_zalegly})
    except Exception:
        current_app.logger.exception('Error building summary')


@api_bp.route('/panel/wnioski', methods=['GET'])
@roles_required('lider', 'admin')
def panel_wnioski():
    """Zwraca fragment HTML z listą oczekujących wniosków (slide-over)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT w.id, p.imie_nazwisko, w.typ, w.data_od, w.data_do, w.czas_od, w.czas_do, w.powod, w.zlozono FROM wnioski_wolne w JOIN pracownicy p ON w.pracownik_id = p.id WHERE w.status = 'pending' ORDER BY w.zlozono DESC LIMIT 200")
        raw = cursor.fetchall()
        wnioski = []
        for r in raw:
            wnioski.append({'id': r[0], 'pracownik': r[1], 'typ': r[2], 'data_od': r[3], 'data_do': r[4], 'czas_od': r[5], 'czas_do': r[6], 'powod': r[7], 'zlozono': r[8]})
        try:
            conn.close()
        except Exception:
            pass
        return render_template('panels/wnioski_panel.html', wnioski=wnioski)
    except Exception:
        current_app.logger.exception('Failed to build wnioski panel')
        return render_template('panels/wnioski_panel.html', wnioski=[])


@api_bp.route('/panel/planowane', methods=['GET'])
@login_required
def panel_planowane():
    """Zwraca fragment HTML z planowanymi urlopami (następne 60 dni)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        end_date = date.today() + timedelta(days=60)
        cursor.execute("SELECT w.id, p.imie_nazwisko, w.typ, w.data_od, w.data_do, w.czas_od, w.czas_do, w.status FROM wnioski_wolne w JOIN pracownicy p ON w.pracownik_id = p.id WHERE w.data_od <= %s AND w.data_do >= %s ORDER BY w.data_od ASC LIMIT 500", (end_date, date.today()))
        raw = cursor.fetchall()
        planned = []
        for r in raw:
            planned.append({'id': r[0], 'pracownik': r[1], 'typ': r[2], 'data_od': r[3], 'data_do': r[4], 'czas_od': r[5], 'czas_do': r[6], 'status': r[7]})
        try:
            conn.close()
        except Exception:
            pass
        return render_template('panels/planowane_panel.html', planned_leaves=planned)
    except Exception:
        current_app.logger.exception('Failed to build planned leaves panel')
        return render_template('panels/planowane_panel.html', planned_leaves=[])


@api_bp.route('/panel/obecnosci', methods=['GET'])
@login_required
def panel_obecnosci():
    """Zwraca fragment HTML z ostatnimi nieobecnościami (ostatnie 30 dni)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        since = date.today() - timedelta(days=30)
        cursor.execute("SELECT o.id, p.imie_nazwisko, o.typ, o.data_wpisu, o.ilosc_godzin, o.komentarz FROM obecnosc o JOIN pracownicy p ON o.pracownik_id = p.id WHERE o.data_wpisu BETWEEN %s AND %s ORDER BY o.data_wpisu DESC LIMIT 500", (since, date.today()))
        raw = cursor.fetchall()
        recent = []
        for r in raw:
            recent.append({'id': r[0], 'pracownik': r[1], 'typ': r[2], 'data': r[3], 'godziny': r[4], 'komentarz': r[5]})
        try:
            conn.close()
        except Exception:
            pass
        return render_template('panels/obecnosci_panel.html', recent_absences=recent)
    except Exception:
        current_app.logger.exception('Failed to build absences panel')
        return render_template('panels/obecnosci_panel.html', recent_absences=[])
        try:
            conn.close()
        except Exception:
            pass
        return jsonify({'error': 'server error'}), 500


@api_bp.route('/usun_obecnosc/<int:id>', methods=['POST'])
@login_required
def usun_obecnosc(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM obecnosc WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect(bezpieczny_powrot())

@api_bp.route('/dodaj_do_obsady', methods=['POST'])
@login_required
def dodaj_do_obsady():
    conn = get_db_connection()
    cursor = conn.cursor()
    sekcja = request.form.get('sekcja')
    pracownik_id = request.form.get('pracownik_id')
    # allow optional date parameter to assign obsada for a specific day
    date_str = request.form.get('date') or request.args.get('date')
    try:
        add_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today()
    except Exception:
        add_date = date.today()
    if not sekcja or not pracownik_id:
        # brak wymaganych pól — nie powodujemy 500, a pokazujemy informację i wracamy
        try:
            flash('Brak wybranego pracownika lub sekcji przy dodawaniu do obsady.', 'warning')
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        return redirect(bezpieczny_powrot())
    try:
        cursor.execute("INSERT INTO obsada_zmiany (data_wpisu, sekcja, pracownik_id) VALUES (%s, %s, %s)", (add_date, sekcja, pracownik_id))
        # Attempt to retrieve the inserted row id for AJAX clients
        try:
            cursor.execute("SELECT id FROM obsada_zmiany WHERE data_wpisu=%s AND sekcja=%s AND pracownik_id=%s ORDER BY id DESC LIMIT 1", (add_date, sekcja, pracownik_id))
            inserted_row = cursor.fetchone()
            inserted_id = inserted_row[0] if inserted_row else None
        except Exception:
            inserted_id = None
        # Automatyczne zapisanie obecności przy dodaniu do obsady (jeśli brak już wpisu)
        try:
            default_hours = 8
            cursor.execute("SELECT COUNT(1) FROM obecnosc WHERE pracownik_id=%s AND data_wpisu=%s", (pracownik_id, add_date))
            exists = int(cursor.fetchone()[0] or 0)
            if not exists:
                cursor.execute("INSERT INTO obecnosc (data_wpisu, pracownik_id, typ, ilosc_godzin, komentarz) VALUES (%s, %s, %s, %s, %s)", (add_date, pracownik_id, 'Obecność', default_hours, 'Automatyczne z obsady'))
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
        conn.commit()
    finally:
        try: conn.close()
        except Exception: pass
    # If called via AJAX, return JSON with inserted id so frontend can update UI without reload
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            # try to fetch worker name for convenience
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT imie_nazwisko FROM pracownicy WHERE id=%s", (pracownik_id,))
            row = cur.fetchone()
            name = row[0] if row else ''
            try: conn.close()
            except: pass
        except Exception:
            name = ''
        return jsonify({'success': True, 'id': inserted_id, 'pracownik_id': pracownik_id, 'name': name})

    return redirect(bezpieczny_powrot())


@api_bp.route('/zapisz_liderow_obsady', methods=['POST'])
@login_required
@roles_required(['lider', 'admin'])
def zapisz_liderow_obsady():
    date_str = request.form.get('date') or request.args.get('date')
    try:
        qdate = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today()
    except Exception:
        qdate = date.today()
    lider_psd = request.form.get('lider_psd') or None
    lider_agro = request.form.get('lider_agro') or None

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # upsert leaders for that date
        cur.execute("INSERT INTO obsada_liderzy (data_wpisu, lider_psd_id, lider_agro_id) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE lider_psd_id=VALUES(lider_psd_id), lider_agro_id=VALUES(lider_agro_id)", (qdate, lider_psd, lider_agro))
        conn.commit()
    finally:
        try: conn.close()
        except Exception: pass

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True})
    return redirect(bezpieczny_powrot())

@api_bp.route('/usun_z_obsady/<int:id>', methods=['POST'])
@login_required
def usun_z_obsady(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # pobierz informacje o usuwanym wierszu i usuń wszystkie powielone wpisy
        cursor.execute("SELECT pracownik_id, data_wpisu, sekcja FROM obsada_zmiany WHERE id=%s", (id,))
        row = cursor.fetchone()
        if row:
            pracownik_id, data_wpisu, sekcja = row[0], row[1], row[2]
            cursor.execute("DELETE FROM obsada_zmiany WHERE pracownik_id=%s AND data_wpisu=%s AND sekcja=%s", (pracownik_id, data_wpisu, sekcja))
            # Usuń automatyczny wpis w tabeli obecnosc utworzony przy dodaniu do obsady
            try:
                cursor.execute("DELETE FROM obecnosc WHERE pracownik_id=%s AND data_wpisu=%s AND komentarz=%s", (pracownik_id, data_wpisu, 'Automatyczne z obsady'))
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
        else:
            cursor.execute("DELETE FROM obsada_zmiany WHERE id=%s", (id,))
        conn.commit()
    finally:
        try: conn.close()
        except Exception: pass

    # dla AJAX zwracamy JSON, dla zwykłego formularza redirect
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True})
    return redirect(bezpieczny_powrot())
@api_bp.route('/zamknij-zmiane', methods=['GET'])
@login_required
@roles_required(['lider', 'admin'])
def zamknij_zmiane():
    """Wyświetl stronę podsumowania i zamknięcia zmiany - KONKRETNA SEKCJA"""
    dzisiaj = date.today()
    sekcja = request.args.get('sekcja', 'Workowanie')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Pobierz dane o zmianach dzisiaj
    cursor.execute("""
        SELECT id, produkt, tonaz, status, real_start, real_stop, tonaz_rzeczywisty, typ_produkcji
        FROM plan_produkcji
        WHERE data_planu = %s AND sekcja = %s
        ORDER BY real_start DESC
    """, (dzisiaj, sekcja))
    
    plany = []
    for row in cursor.fetchall():
        plan_id, produkt, tonaz, status, real_start, real_stop, tonaz_wykonania, typ_prod = row
        
        # Pobierz palety
        cursor.execute("""
            SELECT id, waga, data_dodania, status, czas_potwierdzenia_s
            FROM palety_workowanie
            WHERE plan_id = %s
            ORDER BY data_dodania DESC
        """, (plan_id,))
        
        palety = []
        for p in cursor.fetchall():
            palety.append({
                'id': p[0],
                'waga': p[1],
                'data_dodania': p[2].strftime('%Y-%m-%d %H:%M:%S') if p[2] else 'N/A',
                'status': p[3],
                'czas_potwierdzenia_s': p[4]
            })
        
        plany.append({
            'id': plan_id,
            'produkt': produkt,
            'tonaz': tonaz,
            'tonaz_wykonania': tonaz_wykonania or 0,
            'status': status,
            'real_start': real_start.strftime('%H:%M:%S') if real_start else 'N/A',
            'real_stop': real_stop.strftime('%H:%M:%S') if real_stop else 'N/A',
            'typ_produkcji': typ_prod,
            'palety': palety
        })
    
    # Pobierz pracowników na zmianie
    cursor.execute("""
        SELECT DISTINCT pw.id, pw.imie_nazwisko
        FROM (
            SELECT DISTINCT pracownik_id FROM obsada_zmiany WHERE data_wpisu = %s AND sekcja = %s
        ) ozm
        JOIN pracownicy pw ON ozm.pracownik_id = pw.id
    """, (dzisiaj, sekcja))
    
    pracownicy = []
    for row in cursor.fetchall():
        pracownicy.append({
            'id': row[0],
            'imie': row[1]
        })
    
    # Pobierz informacje o liderze
    lider_id = session.get('pracownik_id')
    lider_name = session.get('login', 'N/A')
    
    conn.close()
    
    zmiana_data = {
        'data': dzisiaj.strftime('%Y-%m-%d'),
        'sekcja': sekcja,
        'lider_name': lider_name,
        'lider_id': lider_id,
        'plany': plany,
        'pracownicy': pracownicy,
        'notatki': ''
    }
    
    return render_template('podsumowanie_zmiany.html',
                          zmiana_data=zmiana_data,
                          sekcja=sekcja,
                          rola=session.get('rola'))

@api_bp.route('/zamknij-zmiane-global', methods=['POST', 'GET'])
@login_required
@roles_required('lider', 'admin')
def zamknij_zmiane_global():
    """
    Endpoint to close shift and download reports as ZIP.
    Orchestrates the report generation workflow.
    """
    import sys
    from services.report_service import (
        load_shift_notes, 
        get_leader_name, 
        generate_and_download_reports
    )
    
    print("\n[ROUTE] ################# ROUTE HANDLER CALLED #################", file=sys.stderr)
    sys.stderr.flush()
    
    # Parse date from request
    date_str = request.values.get('data') or request.args.get('data')
    if date_str:
        try:
            dzisiaj = datetime.strptime(date_str, '%Y-%m-%d').date()
        except Exception:
            dzisiaj = date.today()
    else:
        dzisiaj = date.today()
    
    date_str = dzisiaj.strftime('%Y-%m-%d')
    
    print("\n" + "="*60)
    print("[ROUTE] /zamknij-zmiane-global called")
    print(f"[ROUTE] Method: {request.method}")
    print(f"[ROUTE] Date: {date_str}")
    print("="*60)
    
    try:
        # Load shift notes
        uwagi = load_shift_notes(dzisiaj)
        
        # Get leader name
        session_data = {
            'pracownik_id': session.get('pracownik_id'),
            'login': session.get('login', 'nieznany')
        }
        form_data = {
            'lider_id': request.form.get('lider_id') or request.values.get('lider_id'),
            'lider_prowadzacy_id': request.form.get('lider_prowadzacy_id') or request.values.get('lider_prowadzacy_id')
        }
        lider_name, uwagi_addition = get_leader_name(session_data, form_data)
        uwagi = (uwagi or '') + uwagi_addition
        
        # Generate reports and create ZIP
        zip_buffer, zip_filename = generate_and_download_reports(date_str, uwagi, lider_name)
        
        # Return ZIP for download
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=zip_filename
        )
        
    except Exception as e:
        print(f"[ROUTE] EXCEPTION CAUGHT IN MAIN HANDLER: {str(e)}", file=sys.stderr)
        sys.stderr.flush()
        print(f"[ROUTE] ERROR {str(e)}")
        import traceback
        traceback.print_exc()
        flash(f'ERROR Blad przy generowaniu raportow: {str(e)}', 'error')
        print("="*60 + "\n")
        return redirect('/')


@api_bp.route('/obsada-for-date')
@login_required
def obsada_for_date():
    """Zwraca listę przypisanych pracowników dla podanej daty (parametr `date` YYYY-MM-DD)."""
    date_str = request.args.get('date')
    try:
        if date_str:
            qdate = datetime.strptime(date_str, '%Y-%m-%d').date()
        else:
            qdate = date.today()
    except Exception:
        qdate = date.today()

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT oz.sekcja, pw.id, pw.imie_nazwisko
            FROM obsada_zmiany oz
            JOIN pracownicy pw ON oz.pracownik_id = pw.id
            WHERE oz.data_wpisu = %s
            ORDER BY oz.sekcja, pw.imie_nazwisko
        """, (qdate,))
        rows = []
        for r in cursor.fetchall():
            rows.append({'sekcja': r[0], 'id': r[1], 'imie_nazwisko': r[2]})
        conn.close()
        return jsonify({'date': qdate.isoformat(), 'rows': rows})
    except Exception as e:
        try:
            current_app.logger.exception('obsada_for_date error')
        except Exception:
            pass
        return jsonify({'date': qdate.isoformat(), 'rows': [], 'error': str(e)}), 500


@api_bp.route('/zapisz-raport-koncowy', methods=['POST'])
@login_required
@roles_required(['lider', 'admin'])
def zapisz_raport_koncowy():
    """Zapisz raport końcowy i zamknij zmianę - KONKRETNA SEKCJA"""
    dzisiaj = date.today()
    sekcja = request.form.get('sekcja', 'Workowanie')
    notatki = request.form.get('notatki', '')
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Pobierz dane zmiany
        cursor.execute("""
            SELECT id, produkt, tonaz, tonaz_rzeczywisty
            FROM plan_produkcji
            WHERE data_planu = %s AND sekcja = %s
        """, (dzisiaj, sekcja))
        
        plany_data = []
        for row in cursor.fetchall():
            plany_data.append({
                'id': row[0],
                'produkt': row[1],
                'tonaz': row[2],
                'tonaz_wykonania': row[3] or 0
            })
        
        # Pobierz pracowników
        cursor.execute("""
            SELECT pw.id, pw.imie_nazwisko
            FROM obsada_zmiany oz
            JOIN pracownicy pw ON oz.pracownik_id = pw.id
            WHERE oz.data_wpisu = %s AND oz.sekcja = %s
        """, (dzisiaj, sekcja))
        
        pracownicy_data = []
        for row in cursor.fetchall():
            pracownicy_data.append({
                'id': row[0],
                'imie': row[1]
            })
        
        lider_id = session.get('pracownik_id')
        
        # Przygotuj dane do zapisania
        zmiana_summary = {
            'data': dzisiaj.isoformat(),
            'sekcja': sekcja,
            'lider_id': lider_id,
            'plany': plany_data,
            'pracownicy': pracownicy_data,
            'notatki': notatki
        }
        
        # Zapisz raport do bazy
        import json
        cursor.execute("""
            INSERT INTO raporty_koncowe (data_raportu, sekcja, lider_id, lider_uwagi, summary_json)
            VALUES (%s, %s, %s, %s, %s)
        """, (dzisiaj, sekcja, lider_id, notatki, json.dumps(zmiana_summary)))
        
        # Oznacz plany jako zamknięte
        cursor.execute("""
            UPDATE plan_produkcji
            SET status = 'zamknieta'
            WHERE data_planu = %s AND sekcja = %s AND status != 'zamknieta'
        """, (dzisiaj, sekcja))
        
        conn.commit()
        conn.close()
        
        flash(f"✅ Zmiana w sekcji {sekcja} została zamknięta!", 'success')
        return redirect(url_for('index', sekcja=sekcja, data=dzisiaj.isoformat()))
        
    except Exception as e:
        current_app.logger.error(f"Błąd przy zamykaniu zmiany: {e}")
        flash(f"❌ Błąd: {str(e)}", 'danger')
        return redirect(url_for('index', sekcja=sekcja))

@api_bp.route('/zapisz-raport-koncowy-global', methods=['POST'])
@login_required
@roles_required(['lider', 'admin'])
def zapisz_raport_koncowy_global():
    """Zapisz raport końcowy i zamknij zmianę - WSZYSTKIE SEKCJE"""
    dzisiaj = date.today()
    notatki = request.form.get('notatki', '')
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Pobierz dane dla ALL sekcji z paletami
        wszystkie_plany = {}
        sekcje = ['Zasyp', 'Workowanie', 'Magazyn', 'Hala Agro']
        
        for sekcja in sekcje:
            cursor.execute("""
                SELECT id, produkt, tonaz, tonaz_rzeczywisty, status
                FROM plan_produkcji
                WHERE data_planu = %s AND sekcja = %s
            """, (dzisiaj, sekcja))
            
            plany_data = []
            for row in cursor.fetchall():
                plan_id = row[0]
                
                # Pobierz palety dla tego planu
                cursor.execute("""
                    SELECT waga, data_dodania, status
                    FROM palety_workowanie
                    WHERE plan_id = %s
                    ORDER BY data_dodania DESC
                """, (plan_id,))
                
                palety = []
                for p_row in cursor.fetchall():
                    palety.append({
                        'waga': p_row[0],
                        'data_dodania': p_row[1].isoformat() if p_row[1] else 'N/A',
                        'status': p_row[2]
                    })
                
                plany_data.append({
                    'id': plan_id,
                    'produkt': row[1],
                    'tonaz': row[2],
                    'tonaz_wykonania': row[3] or 0,
                    'status': row[4],
                    'palety': palety
                })
            wszystkie_plany[sekcja] = plany_data
        
        # Pobierz obsadę per sekcja
        wszystkie_obsady = {}
        for sekcja in sekcje:
            cursor.execute("""
                SELECT DISTINCT pw.id, pw.imie_nazwisko
                FROM obsada_zmiany oz
                JOIN pracownicy pw ON oz.pracownik_id = pw.id
                WHERE oz.data_wpisu = %s AND oz.sekcja = %s
                ORDER BY pw.imie_nazwisko
            """, (dzisiaj, sekcja))
            
            obsada = []
            for row in cursor.fetchall():
                obsada.append({
                    'id': row[0],
                    'imie_nazwisko': row[1],
                    'rola': 'pracownik'  # Brak kolumny rola w obsada_zmiany
                })
            wszystkie_obsady[sekcja] = obsada
        
        # Pobierz wpisy o awariach/usterkach
        cursor.execute("""
            SELECT DISTINCT sekcja, typ, opis, data_wpisu, pracownik_id
            FROM dziennik_wpisy
            WHERE data_wpisu = %s AND typ IN ('awaria', 'usterka', 'nieobecność', 'przerwa')
            ORDER BY sekcja, data_wpisu DESC
        """, (dzisiaj,))
        
        awarie = []
        for row in cursor.fetchall():
            sekcja, typ, opis, data_wpisu, pracownik_id = row
            pracownik_name = 'N/A'
            if pracownik_id:
                cursor.execute("SELECT imie_nazwisko FROM pracownicy WHERE id = %s", (pracownik_id,))
                p_row = cursor.fetchone()
                pracownik_name = p_row[0] if p_row else 'N/A'
            
            awarie.append({
                'sekcja': sekcja,
                'typ': typ,
                'opis': opis,
                'data_wpisu': data_wpisu.strftime('%H:%M:%S') if data_wpisu else 'N/A',
                'pracownik': pracownik_name
            })
        
        lider_id = session.get('pracownik_id')
        
        # Przygotuj dane do zapisania
        zmiana_summary = {
            'data': dzisiaj.isoformat(),
            'sekcje': sekcje,
            'lider_id': lider_id,
            'wszystkie_plany': wszystkie_plany,
            'wszystkie_obsady': wszystkie_obsady,
            'awarie': awarie,
            'notatki': notatki
        }
        
        # Zapisz raport do bazy (bez konkretnej sekcji)
        import json
        cursor.execute("""
            INSERT INTO raporty_koncowe (data_raportu, sekcja, lider_id, lider_uwagi, summary_json)
            VALUES (%s, %s, %s, %s, %s)
        """, (dzisiaj, 'Wszystkie sekcje', lider_id, notatki, json.dumps(zmiana_summary)))
        
        # Oznacz WSZYSTKIE plany jako zamknięte
        for sekcja in sekcje:
            cursor.execute("""
                UPDATE plan_produkcji
                SET status = 'zamknieta'
                WHERE data_planu = %s AND sekcja = %s AND status != 'zamknieta'
            """, (dzisiaj, sekcja))
        
        conn.commit()
        conn.close()
        
        flash(f"✅ Zmiana została zamknięta dla wszystkich sekcji!", 'success')
        return redirect(url_for('index'))
        
    except Exception as e:
        current_app.logger.error(f"Błąd przy zamykaniu zmiany: {e}")
        flash(f"❌ Błąd: {str(e)}", 'danger')
        return redirect(url_for('index'))

@api_bp.route('/pobierz-raport', methods=['GET', 'POST'])
@login_required
@roles_required(['lider', 'admin'])
def pobierz_raport():
    """Pobierz wygenerowany raport (PDF, Excel, TXT)

    Obsługa zarówno POST (formularz) jak i GET (querystring) —
    frontend używa GET w kilku miejscach (window.location.href), więc
    zaakceptujemy oba mechanizmy.
    
    Najpierw próbuje wygenerować raport bezpośrednio z DB (jak /api/zamknij-zmiane-global),
    jeśli się nie powiedzie, próbuje czytać z bazy raporty_koncowe.
    """
    try:
        if request.method == 'POST':
            raport_format = request.form.get('format', 'email')
            data_param = request.form.get('data')
        else:
            raport_format = request.args.get('format', 'email')
            data_param = request.args.get('data')
        
        # Pobierz ostatni raport dla dzisiaj z bazy
        # Pozwól nadpisać datę przez parametr (format YYYY-MM-DD), domyślnie dzisiaj
        if data_param:
            try:
                dzisiaj = datetime.strptime(data_param, '%Y-%m-%d').date()
            except Exception:
                dzisiaj = date.today()
        else:
            dzisiaj = date.today()
        
        # NAJPIERW: Spróbuj wygenerować raport bezpośrednio z DB
        print(f"[POBIERZ-RAPORT] Attempting to generate report for {dzisiaj}")
        try:
            from generator_raportow import generuj_paczke_raportow
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Pobierz uwagi lidera z ostatniego wpisu
            cursor.execute("""
                SELECT lider_uwagi FROM raporty_koncowe
                WHERE data_raportu = %s
                ORDER BY id DESC
                LIMIT 1
            """, (dzisiaj,))
            result = cursor.fetchone()
            uwagi = result[0] if result else ''
            
            conn.close()
            
            lider_name = session.get('zalogowany', 'Nieznany')
            
            xls_path, txt_path, pdf_path = generuj_paczke_raportow(str(dzisiaj), uwagi or '', lider_name)
            print(f"[POBIERZ-RAPORT] Generated: xls={xls_path}, txt={txt_path}, pdf={pdf_path}")
            
            # Zwróć raport w zależy od formatu
            if raport_format == 'email':
                with open(txt_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                return content, 200, {
                    'Content-Type': 'text/plain; charset=utf-8',
                    'Content-Disposition': f'attachment; filename="Raport_{dzisiaj}.txt"'
                }
            elif raport_format == 'excel' and xls_path:
                with open(xls_path, 'rb') as f:
                    content = f.read()
                return send_file(
                    BytesIO(content),
                    mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    as_attachment=True,
                    download_name=f'Raport_{dzisiaj}.xlsx'
                )
            elif raport_format == 'pdf' and pdf_path:
                with open(pdf_path, 'rb') as f:
                    content = f.read()
                return send_file(
                    BytesIO(content),
                    mimetype='application/pdf',
                    as_attachment=True,
                    download_name=f'Raport_{dzisiaj}.pdf'
                )
            else:
                # Jeśli żaden format nie pasuje, zwróć TXT
                with open(txt_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                return content, 200, {
                    'Content-Type': 'text/plain; charset=utf-8',
                    'Content-Disposition': f'attachment; filename="Raport_{dzisiaj}.txt"'
                }
        except Exception as e:
            print(f"[POBIERZ-RAPORT] Generator failed: {e}, falling back to RaportService")
        
        # FALLBACK: Jeśli generator się nie powiedzie, czytaj z bazy
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT summary_json, sekcja, data_raportu, lider_id
            FROM raporty_koncowe 
            WHERE data_raportu = %s 
            ORDER BY id DESC 
            LIMIT 1
        """, (dzisiaj,))
        result = cursor.fetchone()
        
        if not result:
            conn.close()
            flash("❌ Raport nie znaleziony!", 'danger')
            return redirect(url_for('index'))
        
        raw_data = json.loads(result[0])
        sekcja = result[1]
        data_raportu = result[2]
        lider_id = result[3]
        
        # Pobierz dane lidera
        cursor.execute("SELECT imie_nazwisko FROM pracownicy WHERE id = %s", (lider_id,))
        lider_row = cursor.fetchone()
        lider_name = lider_row[0] if lider_row else 'N/A'
        conn.close()
        
        # Transform danych do formatu oczekiwanego przez RaportService
        if 'wszystkie_plany' in raw_data:
            # Global report - wszystkie sekcje
            plany_flatten = []
            for sekcja_name, sekcja_plany in raw_data.get('wszystkie_plany', {}).items():
                for plan in sekcja_plany:
                    plan_copy = plan.copy()
                    plan_copy['sekcja'] = sekcja_name
                    # Dodaj domyślne wartości dla starych raportów bez status/palety
                    if 'status' not in plan_copy:
                        plan_copy['status'] = 'zamknieta'
                    if 'palety' not in plan_copy:
                        plan_copy['palety'] = []
                    plany_flatten.append(plan_copy)
            
            zmiana_data = {
                'data': raw_data.get('data', dzisiaj.isoformat()),
                'sekcja': 'Wszystkie sekcje',
                'lider_name': lider_name,
                'pracownicy': raw_data.get('pracownicy', []),
                'plany': plany_flatten,
                'notatki': raw_data.get('notatki', '')
            }
        else:
            # Single sekcja report
            plany = raw_data.get('plany', [])
            for plan in plany:
                # Dodaj domyślne wartości dla starych raportów
                if 'status' not in plan:
                    plan['status'] = 'zamknieta'
                if 'palety' not in plan:
                    plan['palety'] = []
            
            zmiana_data = {
                'data': raw_data.get('data', dzisiaj.isoformat()),
                'sekcja': raw_data.get('sekcja', sekcja),
                'lider_name': lider_name,
                'pracownicy': raw_data.get('pracownicy', []),
                'plany': plany,
                'notatki': raw_data.get('notatki', '')
            }
        
        if raport_format == 'email':
            content = RaportService.generate_email_text(zmiana_data)
            return content, 200, {
                'Content-Type': 'text/plain; charset=utf-8',
                'Content-Disposition': f'attachment; filename="Raport_{data_raportu}.txt"'
            }
        
        elif raport_format == 'excel':
            try:
                content = RaportService.generate_excel(zmiana_data)
                return send_file(
                    BytesIO(content),
                    mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    as_attachment=True,
                    download_name=f'Raport_{data_raportu}.xlsx'
                )
            except Exception as e:
                current_app.logger.error(f"Błąd generowania Excel: {e}")
                flash("❌ Excel nie zainstalowany. Spróbuj formatu txt.", 'warning')
                return redirect(url_for('index'))
        
        elif raport_format == 'pdf':
            try:
                content = RaportService.generate_pdf(zmiana_data)
                return send_file(
                    BytesIO(content),
                    mimetype='application/pdf',
                    as_attachment=True,
                    download_name=f'Raport_{data_raportu}.pdf'
                )
            except Exception as e:
                current_app.logger.error(f"Błąd generowania PDF: {e}")
                flash("❌ ReportLab nie zainstalowany. Spróbuj formatu txt.", 'warning')
                return redirect(url_for('index'))
        
        else:
            flash("❌ Nieznany format raportu!", 'danger')
            return redirect(url_for('index'))
        
    except Exception as e:
        current_app.logger.error(f"Błąd przy pobieraniu raportu: {e}")
        flash(f"❌ Błąd: {str(e)}", 'danger')
        return redirect(url_for('index'))

# ================= EMAIL CONFIGURATION =================

@api_bp.route('/email-config', methods=['GET'])
@login_required
def get_email_config():
    """
    Endpoint zwracający konfigurację odbiorców raportów email.
    Przydatny dla frontenda aby dynamicznie pobierać listę odbiorców.
    
    Response JSON:
    {
        "recipients": ["osoba1@example.com", "osoba2@example.com"],
        "subject_template": "Raport produkcyjny z dnia {date}",
        "configured": true
    }
    """
    try:
        from config import EMAIL_RECIPIENTS
        
        return jsonify({
            "recipients": EMAIL_RECIPIENTS,
            "subject_template": "Raport produkcyjny z dnia {date}",
            "configured": len(EMAIL_RECIPIENTS) > 0,
            "count": len(EMAIL_RECIPIENTS)
        }), 200
    except Exception as e:
        current_app.logger.error(f"[EMAIL-CONFIG] Błąd pobierania konfiguracji: {e}")
        return jsonify({
            "error": "Błąd pobierania konfiguracji",
            "recipients": [],
            "configured": False
        }), 500


# ================= WZNOWIENIE ZLECEŃ Z POPRZEDNIEGO DNIA =================

@api_bp.route('/wznow_zlecenia_z_wczoraj', methods=['POST'])
@login_required
def wznow_zlecenia_z_wczoraj():
    """
    Endpoint wznawia wszystkie zlecenia ze statusem 'wstrzymane' 
    z poprzedniego dnia (zmieniam status na 'w toku').
    """
    try:
        print(f"[WZNOW-WCZORAJ] Starting auto-resume handler")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Poprzedni dzień
        wczoraj = date.today() - timedelta(days=1)
        wczoraj_str = wczoraj.strftime('%Y-%m-%d')
        
        print(f"[WZNOW-WCZORAJ] Querying for plans from {wczoraj_str}")
        
        # Wznów wszystkie zlecenia w statusie 'wstrzymane' z poprzedniego dnia
        resume_query = """
            UPDATE plan_produkcji 
            SET status = 'w toku' 
            WHERE DATE(data_planu) = %s 
            AND status = 'wstrzymane'
        """
        
        cursor.execute(resume_query, (wczoraj_str,))
        resumed_count = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"[WZNOW-WCZORAJ] OK Success: Resumed {resumed_count} plans from {wczoraj_str}")
        
        return jsonify({
            "success": True,
            "resumed_count": resumed_count,
            "message": f"Wznowiono {resumed_count} zleceń z poprzedniego dnia ({wczoraj_str})",
            "date_resumed": wczoraj_str
        }), 200
        
    except Exception as e:
        print(f"[WZNOW-WCZORAJ] ERROR Error: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            "success": False,
            "error": str(e),
            "message": "Błąd przy wznowienia zleceń z poprzedniego dnia"
        }), 500


# ================= RĘCZNE WZNOWIENIE ZLECEŃ DLA SEKCJI =================

@api_bp.route('/wznow_zlecenia_sekcji/<sekcja>', methods=['POST'])
@login_required
def wznow_zlecenia_sekcji(sekcja):
    """
    Endpoint ręcznego wznowienia wszystkich zleceń 'wstrzymane' 
    z poprzedniego dnia dla wybranej sekcji.
    """
    try:
        print(f"[WZNOW-SEKCJA] Starting handler for sekcja={sekcja}")
        
        # Walidacja sekcji
        if sekcja not in ['Zasyp', 'Workowanie', 'Pakowanie', 'Magazyn']:
            print(f"[WZNOW-SEKCJA] ✗ Invalid sekcja: {sekcja}")
            return jsonify({
                "success": False,
                "error": f"Nieznana sekcja: {sekcja}",
                "message": "Sekcja musi być jedną z: Zasyp, Workowanie, Pakowanie, Magazyn"
            }), 400
        
        print(f"[WZNOW-SEKCJA] Sekcja valid: {sekcja}")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Poprzedni dzień
        wczoraj = date.today() - timedelta(days=1)
        wczoraj_str = wczoraj.strftime('%Y-%m-%d')
        
        print(f"[WZNOW-SEKCJA] Querying plans from {wczoraj_str} for sekcja={sekcja}")
        
        # Wznów wszystkie zlecenia 'wstrzymane' z poprzedniego dnia dla tej sekcji
        resume_query = """
            UPDATE plan_produkcji 
            SET status = 'w toku' 
            WHERE DATE(data_planu) = %s 
            AND sekcja = %s 
            AND status = 'wstrzymane'
        """
        
        cursor.execute(resume_query, (wczoraj_str, sekcja))
        resumed_count = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"[WZNOW-SEKCJA] ✓ Success: Resumed {resumed_count} plans for sekcja={sekcja} from {wczoraj_str}")
        
        return jsonify({
            "success": True,
            "resumed_count": resumed_count,
            "sekcja": sekcja,
            "message": f"✅ Wznowiono {resumed_count} zleceń dla {sekcja} z poprzedniego dnia ({wczoraj_str})",
            "date_resumed": wczoraj_str
        }), 200
        
    except Exception as e:
        print(f"[WZNOW-SEKCJA] ✗ Error for sekcja={sekcja}: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            "success": False,
            "error": str(e),
            "message": f"Błąd przy wznowienia zleceń dla {sekcja}"
        }), 500


# ================= MAGAZYN - AJAX ENDPOINTS =================

@api_bp.route('/edytuj_palete_ajax', methods=['POST'])
@login_required
def edytuj_palete_ajax():
    """Edytuj wagę palet w magazynie via AJAX"""
    try:
        data = request.get_json() or {}
        palete_id = data.get('id')
        nowa_waga = data.get('waga')
        data_powrotu = data.get('data_powrotu') or str(date.today())
        
        if not palete_id or nowa_waga is None:
            return jsonify({"success": False, "message": "Brakuje id lub wagi"}), 400
        
        nowa_waga = float(nowa_waga)
        if nowa_waga <= 0:
            return jsonify({"success": False, "message": "Waga musi być większa od 0"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Pobierz plan_id i sekcję palet
        cursor.execute("SELECT plan_id, sekcja FROM palety_workowanie WHERE id=%s", (palete_id,))
        result = cursor.fetchone()
        if not result:
            cursor.close()
            conn.close()
            return jsonify({"success": False, "message": "Paleta nie znaleziona"}), 404
        
        plan_id, sekcja = result
        
        # Aktualizuj wagę
        cursor.execute("UPDATE palety_workowanie SET waga=%s WHERE id=%s", (nowa_waga, palete_id))
        
        # Przelicz buffer (tonaz_rzeczywisty) dla Workowania
        if sekcja == 'Workowanie':
            cursor.execute(
                "UPDATE plan_produkcji SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga), 0) FROM palety_workowanie WHERE plan_id = %s AND status != 'przyjeta') WHERE id = %s",
                (plan_id, plan_id)
            )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Paleta edytowana"}), 200
    
    except Exception as e:
        logger = logging.getLogger('werkzeug')
        logger.error(f"Error in edytuj_palete_ajax: {str(e)}")
        return jsonify({"success": False, "message": f"Błąd: {str(e)}"}), 500


@api_bp.route('/usun_palete_ajax', methods=['POST'])
@login_required
def usun_palete_ajax():
    """Usuń paletę z magazynu via AJAX"""
    try:
        data = request.get_json() or {}
        palete_id = data.get('id')
        data_powrotu = data.get('data_powrotu') or str(date.today())
        
        if not palete_id:
            return jsonify({"success": False, "message": "Brakuje id palet"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Pobierz plan_id i sekcję palet
        cursor.execute("SELECT plan_id, sekcja FROM palety_workowanie WHERE id=%s", (palete_id,))
        result = cursor.fetchone()
        if not result:
            cursor.close()
            conn.close()
            return jsonify({"success": False, "message": "Paleta nie znaleziona"}), 404
        
        plan_id, sekcja = result
        
        # Usuń paletę
        cursor.execute("DELETE FROM palety_workowanie WHERE id=%s", (palete_id,))
        
        # Przelicz buffer (tonaz_rzeczywisty) dla Workowania
        if sekcja == 'Workowanie':
            cursor.execute(
                "UPDATE plan_produkcji SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga), 0) FROM palety_workowanie WHERE plan_id = %s AND status != 'przyjeta') WHERE id = %s",
                (plan_id, plan_id)
            )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Paleta usunięta"}), 200
    
    except Exception as e:
        logger = logging.getLogger('werkzeug')
        logger.error(f"Error in usun_palete_ajax: {str(e)}")
        return jsonify({"success": False, "message": f"Błąd: {str(e)}"}), 500


# ================= TEST ENDPOINTS FOR DOWNLOAD =================

@api_bp.route('/test-download-page')
@login_required
def test_download_page():
    """Strona testowa do pobrania raportów"""
    return render_template('test_download.html')


@api_bp.route('/test-generate-report')
@login_required
def test_generate_report():
    """Test endpoint - Wygeneruj raport bez pobierania"""
    try:
        data_str = request.args.get('data') or str(date.today())
        
        print(f"\n[TEST-GENERATE] Starting report generation for {data_str}")
        sys.stdout.flush()
        
        # Import generator
        from generator_raportow import generuj_paczke_raportow
        
        # Generate reports
        xls_path, txt_path, pdf_path = generuj_paczke_raportow(data_str, "Test raport", "Admin")
        
        # Check if files exist
        xls_exists = os.path.exists(xls_path) if xls_path else False
        txt_exists = os.path.exists(txt_path) if txt_path else False
        pdf_exists = os.path.exists(pdf_path) if pdf_path else False
        
        print(f"[TEST-GENERATE] XLS: {xls_path} (exists={xls_exists})")
        print(f"[TEST-GENERATE] TXT: {txt_path} (exists={txt_exists})")
        print(f"[TEST-GENERATE] PDF: {pdf_path} (exists={pdf_exists})")
        sys.stdout.flush()
        
        return jsonify({
            "success": True,
            "message": f"OK Raport wygenerowany dla {data_str}",
            "xls": xls_path,
            "xls_exists": xls_exists,
            "txt": txt_path,
            "txt_exists": txt_exists,
            "pdf": pdf_path,
            "pdf_exists": pdf_exists
        }), 200
        
    except Exception as e:
        print(f"[TEST-GENERATE] ERROR: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.stderr.flush()
        
        return jsonify({
            "success": False,
            "error": str(e),
            "message": f"ERROR Blad: {str(e)}"
        }), 500


@api_bp.route('/test-download-zip')
@login_required
def test_download_zip():
    """Test endpoint - Zwróć prosty ZIP do pobrania"""
    try:
        data_str = request.args.get('data') or str(date.today())
        
        print(f"\n[TEST-ZIP] Starting ZIP creation for {data_str}")
        sys.stdout.flush()
        
        # Create test ZIP with dummy file
        zip_buffer = BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Add test file
            test_content = f"Test raport dla daty: {data_str}\nGodzina: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            zip_file.writestr("test_raport.txt", test_content)
            
            # Try to add real reports if they exist
            raporty_dir = 'raporty'
            if os.path.exists(raporty_dir):
                for file in os.listdir(raporty_dir):
                    if data_str in file and file.endswith(('.xlsx', '.txt', '.pdf')):
                        file_path = os.path.join(raporty_dir, file)
                        zip_file.write(file_path, arcname=file)
                        print(f"[TEST-ZIP] Added: {file}")
                        sys.stdout.flush()
        
        zip_buffer.seek(0)
        
        print(f"[TEST-ZIP] ZIP created, size: {len(zip_buffer.getvalue())} bytes")
        sys.stdout.flush()
        
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f"Test_Raporty_{data_str}.zip"
        )
        
    except Exception as e:
        print(f"[TEST-ZIP] ERROR: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.stderr.flush()
        
        return jsonify({
            "success": False,
            "error": str(e),
            "message": f"ERROR Blad: {str(e)}"
        }), 500

# ================= NOTATKI/WPISY NA DASHBOARD =================

@api_bp.route('/wpisy_na_date')
@login_required
def wpisy_na_date():
    """Pobierz wpisy dla wybranej daty i sekcji (AJAX)"""
    from utils.queries import QueryHelper
    
    try:
        data_str = request.args.get('data', str(date.today()))
        sekcja = request.args.get('sekcja', 'Zasyp')
        
        # Parse data
        data_obj = datetime.strptime(data_str, '%Y-%m-%d').date()
        
        # Get wpisy
        wpisy = QueryHelper.get_dziennik_zmiany(data_obj, sekcja)
        
        # Format czas_start/czas_stop as HH:MM strings
        for w in wpisy:
            try:
                w[3] = w[3].strftime('%H:%M') if w[3] else ''
            except Exception:
                w[3] = str(w[3]) if w[3] else ''
            try:
                w[4] = w[4].strftime('%H:%M') if w[4] else ''
            except Exception:
                w[4] = str(w[4]) if w[4] else ''
        
        return jsonify({
            'success': True,
            'wpisy': wpisy,
            'data': data_str,
            'sekcja': sekcja
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 400


@api_bp.route('/shift_notes_na_date')
@login_required
def shift_notes_na_date():
    """Pobierz shift notes dla wybranej daty (AJAX)"""
    try:
        data_str = request.args.get('data', str(date.today()))
        
        # Parse data
        data_obj = datetime.strptime(data_str, '%Y-%m-%d').date()
        
        # Get shift notes
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = "SELECT id, note, author, created FROM shift_notes WHERE DATE(created) = %s ORDER BY created DESC"
        cursor.execute(query, (data_obj,))
        shift_notes = cursor.fetchall()
        cursor.close()
        conn.close()
        
        # Format notes
        formatted_notes = []
        for n in shift_notes:
            formatted_notes.append({
                'id': n['id'],
                'note': n['note'],
                'author': n['author'],
                'date': n['created'].strftime('%Y-%m-%d'),
                'time': n['created'].strftime('%H:%M:%S') if n['created'] else ''
            })
        
        return jsonify({
            'success': True,
            'notes': formatted_notes,
            'data': data_str
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 400


@api_bp.route('/update_uszkodzone_worki', methods=['POST'])
@login_required
def update_uszkodzone_worki():
    """Aktualizuj ilość uszkodzonych worków dla planu Workowania"""
    try:
        data = request.get_json()
        plan_id = data.get('plan_id')
        uszkodzone_worki = int(data.get('uszkodzone_worki', 0))
        
        if not plan_id:
            return jsonify({'success': False, 'message': 'Brak plan_id'}), 400
        
        if uszkodzone_worki < 0:
            return jsonify({'success': False, 'message': 'Ilość nie może być ujemna'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Aktualizuj pole uszkodzone_worki
        cursor.execute(
            "UPDATE plan_produkcji SET uszkodzone_worki = %s WHERE id = %s AND sekcja = 'Workowanie'",
            (uszkodzone_worki, plan_id)
        )
        
        if cursor.rowcount == 0:
            conn.close()
            return jsonify({'success': False, 'message': 'Plan nie znaleziony'}), 404
        
        # Loguj zmianę
        cursor.execute(
            "INSERT INTO plan_history (plan_id, action, changes, user_login, created_at) VALUES (%s, %s, %s, %s, NOW())",
            (plan_id, 'uszkodzone_worki_update', f'Uszkodzono: {uszkodzone_worki} worków', session.get('login'), )
        )
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'Zaktualizowano: {uszkodzone_worki} uszkodzonych worków',
            'uszkodzone_worki': uszkodzone_worki
        })
    except ValueError:
        return jsonify({'success': False, 'message': 'Nieprawidłowa liczba'}), 400
    except Exception as e:
        current_app.logger.exception(f'Error updating uszkodzone_worki: {e}')
        return jsonify({'success': False, 'message': str(e)}), 500


@api_bp.route('/get_deleted_plans/<date>', methods=['GET'])
@roles_required('planista', 'admin')
def get_deleted_plans(date):
    """Pobierz usunięte (soft-deleted) zlecenia na dany dzień"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id, produkt, tonaz, status, deleted_at FROM plan_produkcji WHERE DATE(data_planu) = %s AND is_deleted = 1 ORDER BY deleted_at DESC",
            (date,)
        )
        deleted_plans = cursor.fetchall()
        conn.close()
        
        result = []
        for row in deleted_plans:
            result.append({
                'id': row[0],
                'produkt': row[1],
                'tonaz': row[2],
                'status': row[3],
                'deleted_at': str(row[4]) if row[4] else None
            })
        
        return jsonify({'success': True, 'plans': result}), 200
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        current_app.logger.exception('Failed to get deleted plans for %s', date)
        return jsonify({'success': False, 'message': str(e)}), 500