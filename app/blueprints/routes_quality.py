"""Quality control routes (jakosc, DUR/awarie)."""

from flask import Blueprint, render_template, request, redirect, flash, url_for, session, send_file, current_app, jsonify
from datetime import date, datetime
import os
from werkzeug.utils import secure_filename

from app.decorators import roles_required, login_required
from app.db import get_db_connection

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


@quality_bp.route('/api/dur/zmien_status/<int:awaria_id>', methods=['POST'])
@roles_required('dur', 'admin', 'zarzad')
def dur_zmien_status(awaria_id):
    """Zmień status awarii i zaloguj zmianę jako komentarz."""
    try:
        nowy_status = request.form.get('status', '').strip()
        if not nowy_status:
            return jsonify({'success': False, 'message': 'Status nie może być pusty'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Pobierz obecny status
        cursor.execute("SELECT status FROM dziennik_zmiany WHERE id = %s", (awaria_id,))
        awaria = cursor.fetchone()
        if not awaria:
            conn.close()
            return jsonify({'success': False, 'message': 'Awaria nie znaleziona'}), 404
        
        stary_status = awaria.get('status')
        
        # Zaktualizuj status
        cursor.execute("UPDATE dziennik_zmiany SET status = %s WHERE id = %s", (nowy_status, awaria_id))
        
        # Zaloguj zmianę jako komentarz
        pracownik_id = session.get('pracownik_id')
        status_msg = f"🔄 Status zmieniony: {stary_status} → {nowy_status} ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})"
        cursor.execute(
            "INSERT INTO dur_komentarze (awaria_id, autor_id, tresc) VALUES (%s, %s, %s)",
            (awaria_id, pracownik_id, status_msg)
        )
        
        # Zaloguj również w dziennik_zmian_statusu (dla historii)
        cursor.execute("""
            INSERT INTO dziennik_zmian_statusu (awaria_id, stary_status, nowy_status, zmieniony_przez, data_zmiany)
            VALUES (%s, %s, %s, %s, NOW())
        """, (awaria_id, stary_status, nowy_status, pracownik_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True, 
            'message': f'Status zmieniony na "{nowy_status}"',
            'old_status': stary_status,
            'new_status': nowy_status
        }), 200
    except Exception as e:
        current_app.logger.exception(f'Error in dur_zmien_status: {e}')
        return jsonify({'success': False, 'message': f'Błąd: {str(e)}'}), 500


@quality_bp.route('/api/dur/zatwierdz_awarię/<int:awaria_id>', methods=['POST'])
@login_required
def dur_zatwierdz_awarię(awaria_id):
    """Zatwierdź awarie - zmień status i dodaj komentarz."""
    try:
        rola = session.get('rola')
        pracownik_id = session.get('pracownik_id')
        current_app.logger.info(f"=== dur_zatwierdz_awarię START ===")
        current_app.logger.info(f"  awaria_id={awaria_id}, rola={rola}, pracownik_id={pracownik_id}")
        
        status = request.form.get('status', '').strip()
        komentarz = request.form.get('komentarz', '').strip()
        
        current_app.logger.info(f"  Form data: status='{status}' (len={len(status)}), komentarz='{komentarz}' (len={len(komentarz)})")
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Pobierz obecny status przed zmianą
        cursor.execute("SELECT status FROM dziennik_zmiany WHERE id = %s", (awaria_id,))
        awaria_przed = cursor.fetchone()
        
        # Jeśli awaria nie istnieje - zwróć błąd
        if not awaria_przed:
            current_app.logger.warning(f"DEBUG: Awaria #{awaria_id} nie znaleziona w database")
            return jsonify({'success': False, 'message': 'Awaria nie znaleziona'}), 404
        
        stary_status = awaria_przed.get('status')
        current_app.logger.info(f"  stary_status='{stary_status}'")
        
        # Aktualizuj status
        status_zmieniony = False
        if status and stary_status != status:
            current_app.logger.info(f"  ✓ Status się zmienił: '{stary_status}' → '{status}'")
            cursor.execute("UPDATE dziennik_zmiany SET status = %s WHERE id = %s", (status, awaria_id))
            conn.commit()
            status_zmieniony = True
            
            # Jeśli status = 'zakończone', ustaw data_zakonczenia na dzisiaj
            if status == 'zakończone':
                cursor.execute("UPDATE dziennik_zmiany SET data_zakonczenia = %s WHERE id = %s", (date.today(), awaria_id))
                conn.commit()
        else:
            current_app.logger.info(f"  ✗ Status nie zmienił się: status='{status}', stary_status='{stary_status}'")
        
        # Dodaj automatyczny komentarz jeśli zmienił się status
        if status_zmieniony:
            status_msg = f"🔄 Status: {stary_status} → {status} ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})"
            current_app.logger.info(f"DEBUG: Dodawanie auto-komentarza dla awarii #{awaria_id}: {status_msg}")
            
            cursor.execute(
                "INSERT INTO dur_komentarze (awaria_id, autor_id, tresc) VALUES (%s, %s, %s)",
                (awaria_id, pracownik_id, status_msg)
            )
            conn.commit()
            current_app.logger.info(f"DEBUG: Auto-komentarz dodany i zacommit'owany")
        
        # Dodaj komentarz użytkownika jeśli jest wpisany
        if komentarz:
            current_app.logger.info(f"DEBUG: Dodawanie ręcznego komentarza dla awarii #{awaria_id}: {komentarz}")
            cursor.execute(
                "INSERT INTO dur_komentarze (awaria_id, autor_id, tresc) VALUES (%s, %s, %s)",
                (awaria_id, pracownik_id, komentarz)
            )
            conn.commit()
            current_app.logger.info(f"DEBUG: Ręczny komentarz dodany i zacommit'owany")
        
        cursor.close()
        conn.close()
        
        msg = f'✓ Awaria #{awaria_id} zaktualizowana'
        if status_zmieniony:
            msg += f' (status: {status})'
        if komentarz:
            msg += ' (komentarz dodany)'
        
        # Zwróć JSON zamiast redirect, aby formularz mógł być AJAX
        return jsonify({'success': True, 'message': msg}), 200
    except Exception as e:
        current_app.logger.exception(f'Error in dur_zatwierdz_awarię: {e}')
        return jsonify({'success': False, 'message': f'⚠️ Błąd: {str(e)}'}), 500



