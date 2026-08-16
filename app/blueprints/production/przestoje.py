from flask import render_template, request, redirect, url_for, flash, session, current_app, jsonify
from datetime import date, datetime, timedelta
from app.db import get_db_connection, get_table_name
from app.decorators import login_required, roles_required
from app.core.audit import audit_log

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

            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                if plan_id:
                    table_plan = get_table_name('plan_produkcji', linia)
                    cursor.execute(f"SELECT produkt FROM {table_plan} WHERE id = %s", (plan_id,))
                    p_row = cursor.fetchone()
                    if p_row:
                        produkt = p_row['produkt']

                zglaszajacy = session.get('imie_nazwisko') or session.get('login') or 'pracownik'

                cursor.execute("""
                    INSERT INTO przestoje_produkcyjne 
                    (linia, sekcja, plan_id, produkt, data_przestoju, godzina_start, godzina_stop, czas_trwania_min, kategoria, opis, zglaszajacy, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """, (linia, sekcja, plan_id, produkt, data_przestoju, godzina_start, godzina_stop, czas_trwania_min, kategoria, opis, zglaszajacy))
                conn.commit()

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
            if plan_id:
                wybrane_zlecenie = next((p for p in plany if p['id'] == plan_id), None)
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
            plany=plany,
            dzisiaj=dzisiaj,
            teraz_hm=teraz_hm,
            kategorie=kategorie
        )

    @bp.route('/agro/przestoje/edytuj/<int:id>', methods=['GET', 'POST'], endpoint='edytuj_przestoj_page')
    @bp.route('/przestoje/edytuj/<int:id>', methods=['GET', 'POST'], endpoint='edytuj_przestoj_page')
    @login_required
    def edytuj_przestoj_page(id):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT * FROM przestoje_produkcyjne WHERE id = %s", (id,))
            przestoj = cursor.fetchone()
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
                    table_plan = get_table_name('plan_produkcji', linia)
                    cursor.execute(f"SELECT produkt FROM {table_plan} WHERE id = %s", (plan_id,))
                    p_row = cursor.fetchone()
                    if p_row:
                        produkt = p_row['produkt']

                cursor.execute("""
                    UPDATE przestoje_produkcyjne 
                    SET linia = %s, sekcja = %s, plan_id = %s, produkt = %s, 
                        data_przestoju = %s, godzina_start = %s, godzina_stop = %s, 
                        czas_trwania_min = %s, kategoria = %s, opis = %s
                    WHERE id = %s
                """, (linia, sekcja, plan_id, produkt, data_przestoju, godzina_start, godzina_stop, czas_trwania_min, kategoria, opis, id))
                conn.commit()

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

            table_plan = get_table_name('plan_produkcji', linia)
            cursor.execute(f"""
                SELECT id, produkt, tonaz, status, data_planu 
                FROM {table_plan} 
                WHERE sekcja = %s AND data_planu >= %s - INTERVAL 7 DAY 
                  AND (is_deleted = 0 OR is_deleted IS NULL)
                ORDER BY data_planu DESC, id DESC
            """, (sekcja, dzisiaj))
            plany = cursor.fetchall()
            wybrane_zlecenie = None
            if przestoj['plan_id']:
                wybrane_zlecenie = next((p for p in plany if p['id'] == przestoj['plan_id']), None)

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
        except Exception as e:
            current_app.logger.exception(f"Error editing downtime report: {e}")
            flash(f"❌ Błąd edycji przestoju: {str(e)}", "danger")
            return redirect(url_for('production.przestoje_list'))
        finally:
            conn.close()

    @bp.route('/agro/przestoje', methods=['GET'], endpoint='przestoje_list')
    @bp.route('/przestoje', methods=['GET'], endpoint='przestoje_list')
    @login_required
    def przestoje_list():
        linia = (request.args.get('linia') or 'AGRO').strip().upper()
        data_od = request.args.get('data_od') or str(date.today() - timedelta(days=7))
        data_do = request.args.get('data_do') or str(date.today())

        conn = get_db_connection()
        przestoje = []
        suma_minut = 0
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT * FROM przestoje_produkcyjne 
                WHERE linia = %s AND data_przestoju BETWEEN %s AND %s
                ORDER BY data_przestoju DESC, godzina_start DESC
            """, (linia, data_od, data_do))
            przestoje = cursor.fetchall()
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
        except Exception as e:
            current_app.logger.error(f"Error fetching przestoje list: {e}")
        finally:
            conn.close()

        return render_template(
            'production/przestoje_list.html',
            przestoje=przestoje,
            linia=linia,
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
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM przestoje_produkcyjne WHERE id = %s", (id,))
            conn.commit()
            audit_log('Usunięto zgłoszenie przestoju', f'ID przestoju: {id}')
            flash("✅ Usunięto wpis przestoju", "success")
        except Exception as e:
            flash(f"❌ Błąd usuwania: {e}", "danger")
        finally:
            conn.close()
        return redirect(request.referrer or url_for('production.przestoje_list'))
