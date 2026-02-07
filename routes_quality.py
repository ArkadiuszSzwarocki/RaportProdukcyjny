"""Quality control routes (jakosc, DUR/awarie)."""

from flask import Blueprint, render_template, request, redirect, flash, url_for, session, send_file, current_app
from datetime import date
import os
from werkzeug.utils import secure_filename

from decorators import roles_required
from db import get_db_connection

quality_bp = Blueprint('quality', __name__)


@quality_bp.route('/jakosc')
@roles_required('laboratorium', 'lider', 'zarzad', 'admin', 'planista')
def jakosc_index():
    """Lista zleceń jakościowych (typ_zlecenia = 'jakosc')."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, produkt, data_planu, sekcja, tonaz, status, real_start, real_stop, tonaz_rzeczywisty
            FROM plan_produkcji
            WHERE COALESCE(typ_zlecenia, '') = 'jakosc' OR sekcja = 'Jakosc'
            ORDER BY data_planu DESC, id DESC
        """)
        zlecenia = [list(r) for r in cursor.fetchall()]
        # Format real_start/real_stop as HH:MM
        for z in zlecenia:
            try:
                z[6] = z[6].strftime('%H:%M') if z[6] else ''
            except Exception:
                z[6] = str(z[6]) if z[6] else ''
            try:
                z[7] = z[7].strftime('%H:%M') if z[7] else ''
            except Exception:
                z[7] = str(z[7]) if z[7] else ''
        conn.close()
        return render_template('jakosc.html', zlecenia=zlecenia, rola=session.get('rola'))
    except Exception:
        current_app.logger.exception('Failed to render /jakosc')
        return redirect('/')


@quality_bp.route('/jakosc/dodaj', methods=['POST'])
@roles_required('laboratorium', 'lider', 'zarzad', 'admin')
def jakosc_dodaj():
    """Utwórz nowe zlecenie jakościowe (sekcja 'Jakosc', typ_zlecenia='jakosc')."""
    try:
        produkt = request.form.get('produkt')
        if not produkt:
            flash('Podaj nazwę produktu', 'warning')
            return redirect(url_for('quality.jakosc_index'))
        data_planu = request.form.get('data_planu') or str(date.today())
        try:
            tonaz = int(float(request.form.get('tonaz') or 0))
        except Exception:
            tonaz = 0
        typ = request.form.get('typ_produkcji') or 'worki_zgrzewane_25'

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(kolejnosc) FROM plan_produkcji WHERE data_planu=%s", (data_planu,))
        res = cursor.fetchone()
        nk = (res[0] if res and res[0] else 0) + 1
        cursor.execute("INSERT INTO plan_produkcji (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, typ_zlecenia) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", (data_planu, produkt, tonaz, 'zaplanowane', 'Jakosc', nk, typ, 'jakosc'))
        conn.commit()
        conn.close()
        flash('Zlecenie jakościowe utworzone', 'success')
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        current_app.logger.exception('Failed to create jakosc order')
        flash('Błąd podczas tworzenia zlecenia jakościowego', 'danger')
    return redirect(url_for('quality.jakosc_index'))


@quality_bp.route('/jakosc/<int:plan_id>', methods=['GET', 'POST'])
@roles_required('laboratorium', 'lider', 'zarzad', 'admin', 'planista')
def jakosc_detail(plan_id):
    """Szczegóły zlecenia jakościowego i upload dokumentów."""
    docs_dir = os.path.join('raporty', 'jakosc_docs', str(plan_id))
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, produkt, data_planu, sekcja, tonaz, status, real_start, real_stop, tonaz_rzeczywisty, wyjasnienie_rozbieznosci FROM plan_produkcji WHERE id=%s", (plan_id,))
        plan = cursor.fetchone()
        conn.close()

        if request.method == 'POST':
            # Tylko role laboratorum/lider/zarzad/admin mogą przesyłać pliki.
            if session.get('rola') not in ['laboratorium', 'lider', 'zarzad', 'admin']:
                flash('Brak uprawnień do przesyłania plików', 'danger')
                return redirect(url_for('quality.jakosc_detail', plan_id=plan_id))
            f = request.files.get('file')
            if f and f.filename:
                filename = secure_filename(f.filename)
                os.makedirs(docs_dir, exist_ok=True)
                save_path = os.path.join(docs_dir, filename)
                f.save(save_path)
                flash('Plik przesłany', 'success')
            else:
                flash('Brak pliku do przesłania', 'warning')
            return redirect(url_for('quality.jakosc_detail', plan_id=plan_id))

        files = []
        if os.path.exists(docs_dir):
            files = sorted(os.listdir(docs_dir), reverse=True)

        return render_template('jakosc_detail.html', plan=plan, files=files, plan_id=plan_id, rola=session.get('rola'))
    except Exception:
        current_app.logger.exception('Failed to render /jakosc/%s', plan_id)
        return redirect('/jakosc')


@quality_bp.route('/jakosc/download/<int:plan_id>/<path:filename>')
@roles_required('laboratorium', 'lider', 'zarzad', 'admin', 'planista')
def jakosc_download(plan_id, filename):
    """Download quality document."""
    docs_dir = os.path.join('raporty', 'jakosc_docs', str(plan_id))
    file_path = os.path.join(docs_dir, filename)
    if not os.path.exists(file_path):
        return ("Plik nie znaleziony", 404)
    return send_file(file_path, as_attachment=True)


@quality_bp.route('/dur/awarie')
@roles_required('admin', 'planista', 'pracownik', 'magazynier', 'dur', 'zarzad', 'laboratorium')
def dur_awarie():
    """DUR - przegląd i zatwierdzanie awarii"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Pobierz wszystkie awarie z ostatnich 30 dni
        query = """
            SELECT 
                id, 
                data_wpisu, 
                sekcja, 
                kategoria, 
                problem, 
                status, 
                czas_start, 
                czas_stop,
                pracownik_id,
                data_zakonczenia
            FROM dziennik_zmiany 
            WHERE data_wpisu >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
            ORDER BY data_wpisu DESC, czas_start DESC
        """
        cursor.execute(query)
        awarie = cursor.fetchall()
        
        # Pobierz pracowników do wyświetlenia
        cursor.execute("SELECT id, imie_nazwisko FROM pracownicy ORDER BY imie_nazwisko")
        pracownicy_raw = cursor.fetchall()
        pracownicy_map = {r['id']: r['imie_nazwisko'] for r in pracownicy_raw} if pracownicy_raw else {}
        
        cursor.close()
        conn.close()
        
        # Mapuj pracownika do każdej awarii i pobierz komentarze
        for awaria in awarie:
            awaria['pracownik_name'] = pracownicy_map.get(awaria['pracownik_id'], 'Nieznany')
            # Formatuj czas_start / czas_stop jako HH:MM (bez błędnego zakładania timedelta)
            def _fmt_time_field(val):
                # Accept datetime-like or string values; return zero-padded HH:MM or HH:MM:SS
                try:
                    if hasattr(val, 'strftime'):
                        return val.strftime('%H:%M')
                    if isinstance(val, (int, float)):
                        # unlikely, but handle seconds-since-midnight
                        h = int(val) // 3600
                        m = (int(val) % 3600) // 60
                        return f"{h:02d}:{m:02d}"
                    s = str(val).strip()
                    if not s:
                        return '??:??'
                    # Normalize common formats like H:MM:SS or HH:MM:SS or HH:MM
                    parts = s.split(':')
                    if len(parts) == 3:
                        h = int(parts[0])
                        mm = int(parts[1])
                        ss = int(parts[2])
                        return f"{h:02d}:{mm:02d}:{ss:02d}"
                    if len(parts) == 2:
                        h = int(parts[0])
                        mm = int(parts[1])
                        return f"{h:02d}:{mm:02d}"
                    # fallback
                    return s
                except Exception:
                    try:
                        return str(val)
                    except Exception:
                        return '??:??'

            awaria['czas_start_str'] = _fmt_time_field(awaria.get('czas_start'))
            awaria['czas_stop_str'] = _fmt_time_field(awaria.get('czas_stop'))
            
            # Pobierz komentarze do tej awarii
            conn_kom = get_db_connection()
            cursor_kom = conn_kom.cursor(dictionary=True)
            cursor_kom.execute("""
                SELECT dk.id, dk.tresc, dk.created_at, p.imie_nazwisko 
                FROM dur_komentarze dk 
                LEFT JOIN pracownicy p ON dk.autor_id = p.id 
                WHERE dk.awaria_id = %s 
                ORDER BY dk.created_at DESC
            """, (awaria['id'],))
            awaria['komentarze'] = cursor_kom.fetchall()
            current_app.logger.debug(f"DEBUG: Pobrano {len(awaria['komentarze'])} komentarzy dla awarii #{awaria['id']}")
            cursor_kom.close()
            conn_kom.close()
            
            # Pobierz historię zmian statusu
            conn_hist = get_db_connection()
            cursor_hist = conn_hist.cursor(dictionary=True)
            cursor_hist.execute("""
                SELECT dz.id, dz.stary_status, dz.nowy_status, p.imie_nazwisko, dz.data_zmiany
                FROM dziennik_zmian_statusu dz
                LEFT JOIN pracownicy p ON dz.zmieniony_przez = p.id
                WHERE dz.awaria_id = %s
                ORDER BY dz.data_zmiany DESC
            """, (awaria['id'],))
            awaria['historia_statusu'] = cursor_hist.fetchall()
            cursor_hist.close()
            conn_hist.close()
        
        return render_template('dur_awarie.html', awarie=awarie)
    except Exception as e:
        current_app.logger.exception(f'Error in dur_awarie: {e}')
        return redirect('/')
