import os
import uuid
import base64
from typing import Optional, List, Dict, Any
from flask import render_template, request, redirect, url_for, flash, session, current_app, jsonify
from datetime import date, datetime, timedelta
from app.db import get_db_connection, get_table_name
from app.decorators import login_required, roles_required
from app.core.audit import audit_log
from app.repositories.downtime_repository import DowntimeRepository

downtime_repo = DowntimeRepository()

def _save_przestoj_photo(req) -> Optional[str]:
    """Zapisuje przesłane zdjęcie z dysku/aparatu (file) lub ze schowka/screena (base64)."""
    upload_dir = os.path.join(current_app.root_path, '..', 'static', 'uploads', 'przestoje')
    upload_dir = os.path.abspath(upload_dir)
    os.makedirs(upload_dir, exist_ok=True)

    # 1. Sprawdź plik z request.files (z dysku lub aparatu)
    file = req.files.get('zdjecie_file') or req.files.get('zdjecie_camera')
    if file and file.filename:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ['.jpg', '.jpeg', '.png', '.webp', '.gif']:
            ext = '.jpg'
        filename = f"przestoj_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{ext}"
        save_path = os.path.join(upload_dir, filename)
        file.save(save_path)
        return f"/static/uploads/przestoje/{filename}"

    # 2. Sprawdź base64 (ze schowka / PrintScreen / zrzut ekranu)
    base64_data = (req.form.get('zdjecie_base64') or '').strip()
    if base64_data and base64_data.startswith('data:image'):
        try:
            header, encoded = base64_data.split(',', 1)
            ext = '.png'
            if 'image/jpeg' in header or 'image/jpg' in header:
                ext = '.jpg'
            elif 'image/webp' in header:
                ext = '.webp'
            file_bytes = base64.b64decode(encoded)
            filename = f"przestoj_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{ext}"
            save_path = os.path.join(upload_dir, filename)
            with open(save_path, 'wb') as f:
                f.write(file_bytes)
            return f"/static/uploads/przestoje/{filename}"
        except Exception as e:
            current_app.logger.error(f"Error saving base64 downtime photo: {e}")

    # 3. Jeśli usunięto zdjęcie w edycji
    if req.form.get('remove_zdjecie') == '1':
        return ''

    return None

def register_production_przestoje_routes(bp, bezpieczny_powrot):

    @bp.route('/agro/przestoje/zglos', methods=['GET', 'POST'], endpoint='zglos_przestoj_page')
    @bp.route('/przestoje/zglos', methods=['GET', 'POST'], endpoint='zglos_przestoj_page')
    @login_required
    def zglos_przestoj_page():
        if request.method == 'POST':
            linia = (request.form.get('linia') or 'AGRO').strip().upper()
            sekcja = (request.form.get('sekcja') or 'Workowanie').strip()
            data_przestoju = request.form.get('data_przestoju') or str(date.today())
            godzina_start = (request.form.get('godzina_start') or datetime.now().strftime('%H:%M')).strip()
            godzina_stop = request.form.get('godzina_stop')
            if godzina_stop is not None:
                godzina_stop = godzina_stop.strip()
                if not godzina_stop:
                    godzina_stop = None

            kategoria = (request.form.get('kategoria') or 'Inne').strip()
            opis = (request.form.get('opis') or '').strip()
            plan_id_raw = request.form.get('plan_id')

            plan_id = None
            produkt = None
            if plan_id_raw not in (None, '', 'None'):
                try:
                    plan_id = int(plan_id_raw)
                except Exception:
                    plan_id = None

            czas_trwania_min = None
            czas_min_raw = request.form.get('czas_trwania_min')
            if czas_min_raw not in (None, '', 'None'):
                try:
                    czas_trwania_min = int(czas_min_raw)
                except Exception:
                    czas_trwania_min = None

            # Auto-calculate duration if start and stop time are provided
            if czas_trwania_min is None and godzina_start and godzina_stop:
                try:
                    fmt = '%H:%M'
                    t1 = datetime.strptime(godzina_start[:5], fmt)
                    t2 = datetime.strptime(godzina_stop[:5], fmt)
                    diff = (t2 - t1).total_seconds() / 60
                    if diff < 0:
                        diff += 24 * 60  # handle overnight downtime
                    czas_trwania_min = int(diff)
                except Exception:
                    pass

            zdjecie_url = _save_przestoj_photo(request)
            if zdjecie_url == '':
                zdjecie_url = None

            conn = get_db_connection()
            try:
                if plan_id:
                    cursor = conn.cursor(dictionary=True)
                    table_plan = get_table_name('plan_produkcji', linia)
                    cursor.execute(f"SELECT produkt FROM {table_plan} WHERE id = %s", (plan_id,))
                    p_row = cursor.fetchone()
                    if p_row:
                        produkt = p_row['produkt']

                zglaszajacy = session.get('imie_nazwisko') or session.get('login') or 'pracownik'

                downtime_repo.insert_downtime(
                    linia=linia,
                    sekcja=sekcja,
                    plan_id=plan_id,
                    produkt=produkt,
                    data_przestoju=data_przestoju,
                    godzina_start=godzina_start,
                    godzina_stop=godzina_stop,
                    czas_trwania_min=czas_trwania_min,
                    kategoria=kategoria,
                    opis=opis,
                    zglaszajacy=zglaszajacy,
                    zdjecie_url=zdjecie_url
                )

                audit_log('Zgłoszono przestój', f'{linia} - {sekcja}: {kategoria} ({godzina_start}-{godzina_stop or "?"}) - {opis[:50]}')
                flash(f"✅ Zgłoszono przestój dla sekcji {sekcja} ({linia})!", "success")

                redirect_url = request.form.get('redirect_url')
                if redirect_url:
                    return redirect(redirect_url)
                return redirect(url_for('production.przestoje_list', linia=linia, sekcja=sekcja))
            except Exception as e:
                current_app.logger.exception(f"Error saving downtime report: {e}")
                flash(f"❌ Błąd podczas zapisywania przestoju: {str(e)}", "danger")
                return redirect(request.url)
            finally:
                conn.close()

        # GET request - prepare form data
        linia = (request.args.get('linia') or 'AGRO').strip().upper()
        sekcja = (request.args.get('sekcja') or 'Workowanie').strip()
        plan_id_raw = request.args.get('plan_id')
        plan_id = None
        if plan_id_raw:
            try:
                plan_id = int(plan_id_raw)
            except Exception:
                plan_id = None

        dzisiaj = str(date.today())
        teraz_hm = datetime.now().strftime('%H:%M')

        conn = get_db_connection()
        plany = []
        wybrane_zlecenie = None
        aktywne_zlecenie = None
        try:
            cursor = conn.cursor(dictionary=True)
            table_plan = get_table_name('plan_produkcji', linia)
            cursor.execute(f"""
                SELECT id, produkt, tonaz, status, data_planu 
                FROM {table_plan} 
                WHERE sekcja = %s AND data_planu >= %s - INTERVAL 2 DAY 
                  AND (is_deleted = 0 OR is_deleted IS NULL)
                ORDER BY data_planu DESC, id DESC
            """, (sekcja, dzisiaj))
            plany = cursor.fetchall()

            # Auto-detect currently active order (status 'w toku')
            aktywne_zlecenie = next(
                (p for p in plany if (p.get('status') or '').lower() == 'w toku'),
                None
            )

            if plan_id:
                wybrane_zlecenie = next((p for p in plany if p['id'] == plan_id), None)
            elif aktywne_zlecenie:
                # Auto-select active order when no explicit plan_id provided
                wybrane_zlecenie = aktywne_zlecenie
                plan_id = aktywne_zlecenie['id']
        except Exception as e:
            current_app.logger.error(f"Error loading plans for downtime form: {e}")
        finally:
            conn.close()

        kategorie = [
            'Awaria mechaniczna',
            'Awaria elektryczna',
            'Zacięcie zgrzewarki / podajnika',
            'Brak folii / zmiana rolki',
            'Brak etykiet',
            'Przezbrojenie / Czyszczenie',
            'Brak materiału z Zasypu',
            'Brak obsady / pracowników',
            'Brak zasilania / mediów',
            'Inne'
        ]

        return render_template(
            'production/zglos_przestoj.html',
            is_edit=False,
            linia=linia,
            sekcja=sekcja,
            plan_id=plan_id,
            wybrane_zlecenie=wybrane_zlecenie,
            aktywne_zlecenie=aktywne_zlecenie,
            plany=plany,
            dzisiaj=dzisiaj,
            teraz_hm=teraz_hm,
            kategorie=kategorie
        )

    @bp.route('/agro/przestoje/edytuj/<int:id>', methods=['GET', 'POST'], endpoint='edytuj_przestoj_page')
    @bp.route('/przestoje/edytuj/<int:id>', methods=['GET', 'POST'], endpoint='edytuj_przestoj_page')
    @login_required
    def edytuj_przestoj_page(id):
        sekcja_arg = request.args.get('sekcja')
        przestoj = downtime_repo.get_downtime_by_id(id, sekcja=sekcja_arg)
        if not przestoj:
            flash("❌ Nie znaleziono wpisu przestoju", "danger")
            return redirect(url_for('production.przestoje_list'))

        if request.method == 'POST':
            linia = (request.form.get('linia') or przestoj['linia']).strip().upper()
            sekcja = (request.form.get('sekcja') or przestoj['sekcja']).strip()
            data_przestoju = request.form.get('data_przestoju') or str(przestoj['data_przestoju'])
            godzina_start = (request.form.get('godzina_start') or '').strip()
            godzina_stop = request.form.get('godzina_stop')
            if godzina_stop is not None:
                godzina_stop = godzina_stop.strip()
                if not godzina_stop:
                    godzina_stop = None

            kategoria = (request.form.get('kategoria') or 'Inne').strip()
            opis = (request.form.get('opis') or '').strip()
            plan_id_raw = request.form.get('plan_id')

            plan_id = None
            produkt = None
            if plan_id_raw not in (None, '', 'None'):
                try:
                    plan_id = int(plan_id_raw)
                except Exception:
                    plan_id = None

            czas_trwania_min = None
            czas_min_raw = request.form.get('czas_trwania_min')
            if czas_min_raw not in (None, '', 'None'):
                try:
                    czas_trwania_min = int(czas_min_raw)
                except Exception:
                    czas_trwania_min = None

            if czas_trwania_min is None and godzina_start and godzina_stop:
                try:
                    fmt = '%H:%M'
                    t1 = datetime.strptime(godzina_start[:5], fmt)
                    t2 = datetime.strptime(godzina_stop[:5], fmt)
                    diff = (t2 - t1).total_seconds() / 60
                    if diff < 0:
                        diff += 24 * 60
                    czas_trwania_min = int(diff)
                except Exception:
                    pass

            if plan_id:
                conn = get_db_connection()
                try:
                    cursor = conn.cursor(dictionary=True)
                    table_plan = get_table_name('plan_produkcji', linia)
                    cursor.execute(f"SELECT produkt FROM {table_plan} WHERE id = %s", (plan_id,))
                    p_row = cursor.fetchone()
                    if p_row:
                        produkt = p_row['produkt']
                finally:
                    conn.close()

            zdjecie_result = _save_przestoj_photo(request)
            zdjecie_to_update = None
            if zdjecie_result == '':
                # Explicit removal
                zdjecie_to_update = ''
            elif zdjecie_result:
                zdjecie_to_update = zdjecie_result

            downtime_repo.update_downtime(
                downtime_id=id,
                linia=linia,
                sekcja=sekcja,
                plan_id=plan_id,
                produkt=produkt,
                data_przestoju=data_przestoju,
                godzina_start=godzina_start,
                godzina_stop=godzina_stop,
                czas_trwania_min=czas_trwania_min,
                kategoria=kategoria,
                opis=opis,
                zdjecie_url=zdjecie_to_update
            )

            audit_log('Zaktualizowano wpis przestoju', f'ID={id}: {kategoria} ({godzina_start}-{godzina_stop or "?"})')
            flash("✅ Zaktualizowano wpis przestoju!", "success")
            return redirect(url_for('production.przestoje_list', linia=linia, sekcja=sekcja))

        # GET request - prepare data for template
        g_start = przestoj.get('godzina_start')
        if isinstance(g_start, timedelta):
            sec = int(g_start.total_seconds())
            przestoj['godzina_start'] = f"{sec // 3600:02d}:{(sec % 3600) // 60:02d}"
        elif g_start is not None:
            przestoj['godzina_start'] = str(g_start)[:5]

        g_stop = przestoj.get('godzina_stop')
        if isinstance(g_stop, timedelta):
            sec = int(g_stop.total_seconds())
            przestoj['godzina_stop'] = f"{sec // 3600:02d}:{(sec % 3600) // 60:02d}"
        elif g_stop is not None:
            przestoj['godzina_stop'] = str(g_stop)[:5]

        linia = przestoj['linia']
        sekcja = przestoj['sekcja']
        dzisiaj = str(date.today())

        conn = get_db_connection()
        plany = []
        wybrane_zlecenie = None
        try:
            cursor = conn.cursor(dictionary=True)
            table_plan = get_table_name('plan_produkcji', linia)
            cursor.execute(f"""
                SELECT id, produkt, tonaz, status, data_planu 
                FROM {table_plan} 
                WHERE sekcja = %s AND data_planu >= %s - INTERVAL 7 DAY 
                  AND (is_deleted = 0 OR is_deleted IS NULL)
                ORDER BY data_planu DESC, id DESC
            """, (sekcja, dzisiaj))
            plany = cursor.fetchall()
            if przestoj['plan_id']:
                wybrane_zlecenie = next((p for p in plany if p['id'] == przestoj['plan_id']), None)
        except Exception as e:
            current_app.logger.error(f"Error loading plans for downtime edit: {e}")
        finally:
            conn.close()

        kategorie = [
            'Awaria mechaniczna',
            'Awaria elektryczna',
            'Zacięcie zgrzewarki / podajnika',
            'Brak folii / zmiana rolki',
            'Brak etykiet',
            'Przezbrojenie / Czyszczenie',
            'Brak materiału z Zasypu',
            'Brak obsady / pracowników',
            'Brak zasilania / mediów',
            'Inne'
        ]

        return render_template(
            'production/zglos_przestoj.html',
            is_edit=True,
            przestoj=przestoj,
            linia=linia,
            sekcja=sekcja,
            plan_id=przestoj['plan_id'],
            wybrane_zlecenie=wybrane_zlecenie,
            plany=plany,
            dzisiaj=str(przestoj['data_przestoju']),
            teraz_hm=przestoj['godzina_start'] or '',
            kategorie=kategorie
        )

    @bp.route('/agro/przestoje', methods=['GET'], endpoint='przestoje_list')
    @bp.route('/przestoje', methods=['GET'], endpoint='przestoje_list')
    @login_required
    def przestoje_list():
        linia = (request.args.get('linia') or 'AGRO').strip().upper()
        sekcja = request.args.get('sekcja')
        if sekcja:
            sekcja = sekcja.strip()
            if sekcja.lower() not in ('zasyp', 'workowanie'):
                sekcja = None

        data_od = request.args.get('data_od') or str(date.today() - timedelta(days=7))
        data_do = request.args.get('data_do') or str(date.today())

        przestoje = downtime_repo.get_downtimes(linia=linia, data_od=data_od, data_do=data_do, sekcja=sekcja)
        for p in przestoje:
            g_start = p.get('godzina_start')
            if isinstance(g_start, timedelta):
                sec = int(g_start.total_seconds())
                p['godzina_start'] = f"{sec // 3600:02d}:{(sec % 3600) // 60:02d}"
            elif g_start is not None:
                p['godzina_start'] = str(g_start)[:5]
            else:
                p['godzina_start'] = ''

            g_stop = p.get('godzina_stop')
            if isinstance(g_stop, timedelta):
                sec = int(g_stop.total_seconds())
                p['godzina_stop'] = f"{sec // 3600:02d}:{(sec % 3600) // 60:02d}"
            elif g_stop is not None:
                p['godzina_stop'] = str(g_stop)[:5]
            else:
                p['godzina_stop'] = ''

        suma_minut = sum(p.get('czas_trwania_min') or 0 for p in przestoje)

        return render_template(
            'production/przestoje_list.html',
            przestoje=przestoje,
            linia=linia,
            sekcja=sekcja,
            data_od=data_od,
            data_do=data_do,
            suma_minut=suma_minut,
            dzisiaj=str(date.today())
        )

    @bp.route('/agro/przestoje/usun/<int:id>', methods=['POST'], endpoint='usun_przestoj')
    @bp.route('/przestoje/usun/<int:id>', methods=['POST'], endpoint='usun_przestoj')
    @login_required
    @roles_required('lider', 'admin', 'masteradmin')
    def usun_przestoj(id):
        sekcja = request.form.get('sekcja') or request.args.get('sekcja')
        try:
            success = downtime_repo.delete_downtime(id, sekcja=sekcja)
            if success:
                audit_log('Usunięto zgłoszenie przestoju', f'ID przestoju: {id}')
                flash("✅ Usunięto wpis przestoju", "success")
            else:
                flash("❌ Nie znaleziono wpisu do usunięcia", "warning")
        except Exception as e:
            flash(f"❌ Błąd usuwania: {e}", "danger")
        return redirect(request.referrer or url_for('production.przestoje_list'))
