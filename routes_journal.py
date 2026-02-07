"""Journal and notes routes (formerly in routes_api.py DZIENNIK section)."""

from flask import Blueprint, request, redirect, url_for, flash, session, render_template, current_app, jsonify
from datetime import date, datetime, timedelta, time
from db import get_db_connection
from decorators import login_required, roles_required
from dto.paleta import PaletaDTO
import logging

journal_bp = Blueprint('journal', __name__)


@journal_bp.route('/dodaj_wpis', methods=['POST'])
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


@journal_bp.route('/usun_wpis/<int:id>', methods=['POST'])
@login_required
def usun_wpis(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM dziennik_zmiany WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))


@journal_bp.route('/edytuj/<int:id>', methods=['GET', 'POST'])
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
            return redirect('/')

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
        try:
            current_app.logger.exception('Error in edytuj endpoint for id=%s', id)
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        from flask import flash
        flash('Wystąpił błąd podczas ładowania wpisu.', 'danger')


@journal_bp.route('/remind_unconfirmed_palety', methods=['POST'])
@roles_required('lider', 'admin')
def remind_unconfirmed_palety():
    """Ręczne wyzwalanie przypomnień dla niepotwierdzonych palet."""
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
        return redirect('/')
    except Exception:
        current_app.logger.exception('Error in remind_unconfirmed_palety')
        flash('Wystąpił błąd podczas wysyłania przypomnień.', 'danger')
        return redirect('/')


@journal_bp.route('/ustawienia', methods=['GET'])
@login_required
def ustawienia():
    """Prosty widok ustawień (placeholder)."""
    try:
        return render_template('ustawienia.html')
    except Exception:
        from flask import flash
        flash('Nie można otworzyć strony ustawień.', 'danger')
        return redirect('/')


@journal_bp.route('/zapisz_tonaz_deprecated/<int:id>', methods=['POST'])
def zapisz_tonaz_deprecated(id):
    """Deprecated endpoint for compatibility."""
    return redirect('/')
