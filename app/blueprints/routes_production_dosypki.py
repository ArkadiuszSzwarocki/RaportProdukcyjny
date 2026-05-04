from datetime import date

from flask import current_app, flash, jsonify, redirect, render_template, request, session

from app.core.audit import audit_log
from app.db import get_db_connection, get_table_name, list_unconfirmed_dosypki, sync_dosypka_notifications
from app.decorators import roles_required


def register_production_dosypki_routes(
    production_bp,
    bezpieczny_powrot,
    get_allowed_dosypka_materials,
    mark_dosypki_updated,
    notify_agro_operator_dosypka_added,
):
    @production_bp.route('/dosypka_page/<int:plan_id>', methods=['GET'])
    @roles_required('laborant', 'laboratorium', 'planista', 'admin')
    def dosypka_page(plan_id):
        """Render form to add up to 4 dosypki for an active Zasyp plan."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        conn = get_db_connection()
        try:
            linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
            table_plan = get_table_name('plan_produkcji', linia)
            table_dosypki = get_table_name('dosypki', linia)
            cursor = conn.cursor()
            cursor.execute(f"SELECT produkt, typ_produkcji, status FROM {table_plan} WHERE id=%s AND sekcja='Zasyp'", (plan_id,))
            plan = cursor.fetchone()
            if not plan:
                msg = 'Plan nie znaleziony'
                if is_ajax:
                    return f'<div class="p-15 text-danger">{msg}</div>', 404
                flash(msg, 'error')
                return redirect(bezpieczny_powrot())

            produkt, typ_produkcji, status = plan[0], plan[1], plan[2]
            if status != 'w toku':
                msg = 'Dosypki można dodawać tylko do aktywnego zlecenia (status "w toku")'
                if is_ajax:
                    return f'<div class="p-15 text-warning">{msg}</div>', 400
                flash(msg, 'warning')
                return redirect(bezpieczny_powrot())

            szarza_id = request.args.get('szarza_id')
            szarza_id_int = None
            if szarza_id:
                try:
                    szarza_id_int = int(szarza_id)
                except ValueError:
                    szarza_id_int = None

            if szarza_id_int:
                cursor.execute(
                    f"""
                    SELECT id, nazwa, kg, data_zlecenia, potwierdzone, COALESCE(anulowana, 0), anulowal_login, data_anulowania
                    FROM {table_dosypki}
                    WHERE plan_id=%s AND szarza_id=%s
                    ORDER BY COALESCE(anulowana, 0) ASC, data_zlecenia DESC
                    """,
                    (plan_id, szarza_id_int),
                )
            else:
                cursor.execute(
                    f"""
                    SELECT id, nazwa, kg, data_zlecenia, potwierdzone, COALESCE(anulowana, 0), anulowal_login, data_anulowania
                    FROM {table_dosypki}
                    WHERE plan_id=%s
                    ORDER BY COALESCE(anulowana, 0) ASC, data_zlecenia DESC
                    """,
                    (plan_id,),
                )

            existing_dosypki = [
                {
                    'id': row[0],
                    'nazwa': row[1],
                    'kg': float(row[2]) if row[2] is not None else 0,
                    'data_zlecenia': str(row[3]) if row[3] is not None else '',
                    'potwierdzone': bool(row[4]),
                    'anulowana': bool(row[5]),
                    'anulowal_login': row[6],
                    'data_anulowania': str(row[7]) if row[7] is not None else '',
                }
                for row in cursor.fetchall()
            ]

            try:
                dostepne_surowce = get_allowed_dosypka_materials(cursor, linia)
            except Exception:
                current_app.logger.warning('dosypka_page: failed to load raw material suggestions', exc_info=True)
                dostepne_surowce = []

            return render_template(
                'dodaj_dosypke_popup.html',
                plan_id=plan_id,
                produkt=produkt,
                typ=typ_produkcji,
                szarza_id=szarza_id,
                existing_dosypki=existing_dosypki,
                linia=linia,
                dostepne_surowce=dostepne_surowce,
            )
        except Exception as e:
            current_app.logger.error(f'Error in dosypka_page: {e}', exc_info=True)
            msg = 'Błąd pobierania danych planu'
            if is_ajax:
                return f'<div class="p-15 text-danger">{msg}</div>', 500
            flash(msg, 'error')
            return redirect(bezpieczny_powrot())
        finally:
            try:
                conn.close()
            except Exception:
                pass

    @production_bp.route('/dodaj_dosypke', methods=['POST'])
    @roles_required('laborant', 'laboratorium', 'admin')
    def dodaj_dosypke():
        """Handle POST from dosypka form and insert rows into `dosypki` table."""
        plan_id = request.form.get('plan_id')
        if not plan_id:
            flash('Brak identyfikatora zlecenia', 'error')
            return redirect(bezpieczny_powrot())
        try:
            plan_id = int(plan_id)
        except Exception:
            flash('Nieprawidłowe ID zlecenia', 'error')
            return redirect(bezpieczny_powrot())

        szarza_id = request.form.get('szarza_id')
        if szarza_id:
            try:
                szarza_id = int(szarza_id)
            except ValueError:
                szarza_id = None

        linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
        brak_dosypki = request.form.get('brak_dosypki') == '1'

        entries = []
        for i in range(1, 11):
            name = (request.form.get(f'nazwa_{i}') or '').strip()
            kg_raw = request.form.get(f'kg_{i}')
            if name and kg_raw:
                try:
                    kg = float(str(kg_raw).replace(',', '.'))
                except Exception:
                    kg = 0
                if kg > 0:
                    entries.append((name, kg))

        if brak_dosypki:
            entries = [('Brak dosypki', 0)]
        elif not entries:
            flash('Brak poprawnych pozycji dosypki do zapisania', 'warning')
            return redirect(bezpieczny_powrot())

        conn = get_db_connection()
        try:
            table_plan = get_table_name('plan_produkcji', linia)
            table_dosypki = get_table_name('dosypki', linia)
            table_szarze = get_table_name('szarze', linia)
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT id, produkt, data_planu, status FROM {table_plan} WHERE id=%s AND sekcja='Zasyp'",
                (plan_id,),
            )
            r = cursor.fetchone()
            if not r or r[3] != 'w toku':
                flash('Dosypki można dodawać tylko do aktywnego zlecenia (status "w toku")', 'warning')
                return redirect(bezpieczny_powrot())
            produkt = str(r[1] or '').strip() if r else ''

            if szarza_id and not brak_dosypki:
                cursor.execute(
                    f"SELECT id FROM {table_szarze} WHERE id=%s AND plan_id=%s LIMIT 1",
                    (szarza_id, plan_id),
                )
                id_match = cursor.fetchone()
                if not id_match:
                    cursor.execute(
                        f"SELECT id FROM {table_szarze} WHERE plan_id=%s ORDER BY data_dodania ASC, id ASC",
                        (plan_id,),
                    )
                    szarza_ids_for_plan = [int(row[0]) for row in cursor.fetchall() if row and row[0] is not None]
                    if szarza_ids_for_plan and 1 <= int(szarza_id) <= len(szarza_ids_for_plan):
                        szarza_id = int(szarza_ids_for_plan[int(szarza_id) - 1])

            if not szarza_id and not brak_dosypki:
                cursor.execute(
                    f"SELECT id FROM {table_szarze} WHERE plan_id=%s ORDER BY data_dodania DESC, id DESC LIMIT 1",
                    (plan_id,),
                )
                latest_szarza = cursor.fetchone()
                if latest_szarza and latest_szarza[0]:
                    szarza_id = int(latest_szarza[0])

            if not brak_dosypki:
                allowed_surowce = get_allowed_dosypka_materials(cursor, linia)
                if not allowed_surowce:
                    flash('Brak dostępnego słownika surowców magazynu. Nie można zapisać własnych nazw.', 'warning')
                    return redirect(bezpieczny_powrot())

                allowed_map = {str(name).strip().lower(): name for name in allowed_surowce if str(name).strip()}
                invalid_entries = [name for name, _ in entries if str(name).strip().lower() not in allowed_map]
                if invalid_entries:
                    invalid_label = ', '.join(sorted(set(invalid_entries))[:3])
                    flash(f'Niedozwolona nazwa surowca: {invalid_label}. Wybierz pozycję z listy magazynu.', 'warning')
                    return redirect(bezpieczny_powrot())

                entries = [(allowed_map[str(name).strip().lower()], kg) for name, kg in entries]

            pracownik_id = session.get('pracownik_id') if 'pracownik_id' in session else None
            created_by_user_id = session.get('user_id') if 'user_id' in session else None
            target_szarza_nr = None
            if szarza_id:
                try:
                    cursor.execute(f"SELECT nr_szarzy FROM {table_szarze} WHERE id=%s LIMIT 1", (szarza_id,))
                    sz_row = cursor.fetchone()
                    if sz_row and sz_row[0] is not None:
                        target_szarza_nr = int(sz_row[0])
                except Exception:
                    target_szarza_nr = None

            for name, kg in entries:
                cursor.execute(
                    f"INSERT INTO {table_dosypki} (plan_id, szarza_id, nazwa, kg, pracownik_id, potwierdzone) VALUES (%s, %s, %s, %s, %s, 0)",
                    (plan_id, szarza_id, name, kg, pracownik_id),
                )
                try:
                    audit_log('Dodał dosypkę', f'nazwa={name}, kg={kg}, plan_id={plan_id}')
                except Exception:
                    current_app.logger.debug('audit_log failed for dosypka insert', exc_info=True)

            sync_dosypka_notifications(
                plan_id=plan_id,
                author_name=session.get('imie_nazwisko') or session.get('login'),
                created_by_user_id=created_by_user_id,
                conn=conn,
                cursor=cursor,
                linia=linia,
            )

            conn.commit()
            mark_dosypki_updated(linia)

            if str(linia or '').upper() == 'AGRO' and not brak_dosypki:
                try:
                    notify_agro_operator_dosypka_added(
                        linia=linia,
                        plan_id=plan_id,
                        produkt=produkt,
                        szarza_nr=target_szarza_nr,
                        dosypki_count=len(entries),
                    )
                except Exception:
                    current_app.logger.exception('Failed to notify AGRO operator about dosypka list update')

            if brak_dosypki:
                flash('Oznaczono, że brak dosypki dla tego zlecenia.', 'success')
            else:
                flash(f'Zapisano {len(entries)} pozycji dosypki.', 'success')
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            current_app.logger.error(f'Failed to insert dosypki: {e}', exc_info=True)
            flash('Błąd zapisu dosypki', 'error')
        finally:
            try:
                conn.close()
            except Exception:
                pass

        return redirect(bezpieczny_powrot())

    @production_bp.route('/potwierdz_dosypke/<int:dosypka_id>', methods=['POST'])
    @roles_required('operator', 'pracownik', 'produkcja', 'lider', 'admin', 'zarzad')
    def potwierdz_dosypke(dosypka_id):
        """Operator potwierdza odczytanie dosypki - mark as confirmed."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
        table_plan = get_table_name('plan_produkcji', linia)
        table_dosypki = get_table_name('dosypki', linia)
        table_szarze = get_table_name('szarze', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(f"SELECT id FROM {table_dosypki} WHERE id=%s AND potwierdzone=0 AND COALESCE(anulowana, 0)=0", (dosypka_id,))
            r = cursor.fetchone()
            if not r:
                if is_ajax:
                    return jsonify({'success': False, 'message': 'Pozycja nieznaleziona lub już potwierdzona'}), 404
                flash('Pozycja nieznaleziona lub już potwierdzona', 'warning')
                return redirect(bezpieczny_powrot())

            pracownik_id = session.get('pracownik_id') if 'pracownik_id' in session else None

            cursor.execute(f"SELECT plan_id FROM {table_dosypki} WHERE id=%s", (dosypka_id,))
            dosypka_row = cursor.fetchone()
            plan_id = dosypka_row[0] if dosypka_row else None

            cursor.execute(
                f"UPDATE {table_dosypki} SET potwierdzone=1, potwierdzil_pracownik_id=%s, data_potwierdzenia=NOW() WHERE id=%s",
                (pracownik_id, dosypka_id),
            )

            if plan_id:
                cursor.execute(
                    f"UPDATE {table_plan} SET tonaz_rzeczywisty = "
                    f"COALESCE((SELECT SUM(waga) FROM {table_szarze} WHERE plan_id = %s), 0) + "
                    f"COALESCE((SELECT SUM(kg) FROM {table_dosypki} WHERE plan_id = %s AND potwierdzone = 1 AND COALESCE(anulowana, 0) = 0), 0) "
                    f"WHERE id = %s",
                    (plan_id, plan_id, plan_id),
                )
                sync_dosypka_notifications(
                    plan_id=plan_id,
                    author_name=session.get('imie_nazwisko') or session.get('login'),
                    created_by_user_id=session.get('user_id'),
                    conn=conn,
                    cursor=cursor,
                    linia=linia,
                )

            conn.commit()
            mark_dosypki_updated(linia)
            if is_ajax:
                return jsonify({'success': True, 'message': 'Potwierdzono dosypkę.', 'plan_id': plan_id})
            flash('Potwierdzono dosypkę.', 'success')
            try:
                audit_log('Potwierdził dosypkę', f'id={dosypka_id}, plan_id={plan_id}')
            except Exception:
                current_app.logger.debug('audit_log failed for dosypka confirm', exc_info=True)
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            current_app.logger.error(f'Failed to confirm dosypka: {e}', exc_info=True)
            if is_ajax:
                return jsonify({'success': False, 'message': 'Błąd podczas potwierdzania'}), 500
            flash('Błąd podczas potwierdzania', 'error')
        finally:
            try:
                conn.close()
            except Exception:
                pass

        return redirect(bezpieczny_powrot())

    @production_bp.route('/anuluj_dosypke/<int:dosypka_id>', methods=['POST'])
    @roles_required('laborant', 'laboratorium', 'admin')
    def anuluj_dosypke(dosypka_id):
        """Mark dosypka as anulowana instead of deleting it."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
        table_dosypki = get_table_name('dosypki', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT id, plan_id FROM {table_dosypki} WHERE id=%s AND potwierdzone=0 AND COALESCE(anulowana, 0)=0",
                (dosypka_id,),
            )
            row = cursor.fetchone()
            if not row:
                if is_ajax:
                    return jsonify({'success': False, 'message': 'Pozycja nie istnieje, została już potwierdzona albo anulowana'}), 404
                flash('Pozycja nie istnieje, została już potwierdzona albo anulowana', 'warning')
                return redirect(bezpieczny_powrot())

            anulowal_login = session.get('login') or session.get('imie_nazwisko') or 'unknown'
            cursor.execute(
                f"UPDATE {table_dosypki} SET anulowana=1, data_anulowania=NOW(), anulowal_login=%s WHERE id=%s",
                (anulowal_login, dosypka_id),
            )
            sync_dosypka_notifications(
                plan_id=row[1],
                author_name=session.get('imie_nazwisko') or session.get('login'),
                created_by_user_id=session.get('user_id'),
                conn=conn,
                cursor=cursor,
                linia=linia,
            )
            conn.commit()
            mark_dosypki_updated(linia)
            if is_ajax:
                return jsonify(
                    {
                        'success': True,
                        'message': 'Dosypka została anulowana.',
                        'plan_id': row[1],
                        'anulowal_login': anulowal_login,
                    }
                )
            flash('Dosypka została anulowana.', 'success')
            try:
                audit_log('Anulował dosypkę', f'id={dosypka_id}, plan_id={row[1]}, anulowal={anulowal_login}')
            except Exception:
                current_app.logger.debug('audit_log failed for dosypka cancel', exc_info=True)
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            current_app.logger.error(f'Failed to cancel dosypka: {e}', exc_info=True)
            if is_ajax:
                return jsonify({'success': False, 'message': 'Błąd podczas anulowania'}), 500
            flash('Błąd podczas anulowania', 'error')
        finally:
            try:
                conn.close()
            except Exception:
                pass

        return redirect(bezpieczny_powrot())

    @production_bp.route('/api/dosypki', methods=['GET'])
    @roles_required('laborant', 'laboratorium', 'operator', 'pracownik', 'produkcja', 'lider', 'admin', 'zarzad')
    def api_dosypki():
        """Return JSON of active unconfirmed dosypki for operators."""
        current_app.logger.debug(f"[api_dosypki] Endpoint reached by user role: {session.get('rola')}")
        plan_id = request.args.get('plan_id', None)
        linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
        table_dosypki = get_table_name('dosypki', linia)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            if plan_id:
                cursor.execute(
                    f"""
                    SELECT id, plan_id, nazwa, kg, data_zlecenia,
                           COALESCE(anulowana, 0), anulowal_login, data_anulowania
                    FROM {table_dosypki}
                    WHERE potwierdzone = 0 AND COALESCE(anulowana, 0) = 0 AND plan_id = %s
                    ORDER BY data_zlecenia ASC
                    """,
                    (plan_id,),
                )
            else:
                cursor.execute(
                    f"""
                    SELECT id, plan_id, nazwa, kg, data_zlecenia,
                           COALESCE(anulowana, 0), anulowal_login, data_anulowania
                    FROM {table_dosypki}
                    WHERE potwierdzone = 0 AND COALESCE(anulowana, 0) = 0
                    ORDER BY data_zlecenia ASC
                    """
                )
            rows = cursor.fetchall()
            role = session.get('rola', '')
            result = []
            visible_roles = ('laborant', 'operator', 'pracownik', 'produkcja', 'lider', 'admin', 'zarzad')
            for r in rows:
                if role in visible_roles:
                    nazwa = r[2]
                else:
                    nazwa = None
                result.append(
                    {
                        'id': r[0],
                        'plan_id': r[1],
                        'nazwa': nazwa,
                        'kg': float(r[3]),
                        'data_zlecenia': str(r[4]),
                        'anulowana': bool(r[5]),
                        'anulowal_login': r[6],
                        'data_anulowania': str(r[7]) if r[7] is not None else '',
                    }
                )
            return jsonify({'success': True, 'dosypki': result})
        except Exception as e:
            current_app.logger.error(f'api/dosypki failed: {e}', exc_info=True)
            return jsonify({'success': False, 'message': 'Błąd serwera'}), 500
        finally:
            try:
                conn.close()
            except Exception:
                pass

    @production_bp.route('/dosypki_list', methods=['GET'])
    @roles_required('laborant', 'laboratorium', 'operator', 'pracownik', 'produkcja', 'lider', 'admin', 'zarzad')
    def dosypki_list():
        """Render slide-over page with list of active unconfirmed dosypki for operators."""
        plan_id = request.args.get('plan_id', None)
        linia = request.args.get('linia') or session.get('selected_hall_view') or 'PSD'
        rows = list_unconfirmed_dosypki(linia=linia)
        role = session.get('rola', '')
        visible_roles = ('laborant', 'operator', 'pracownik', 'produkcja', 'lider', 'admin', 'zarzad')
        dosypki = []
        for r in rows:
            if plan_id and str(r[1]) != str(plan_id):
                continue
            if role in visible_roles:
                nazwa = r[2]
            else:
                nazwa = None
            dosypki.append(
                {
                    'id': r[0],
                    'plan_id': r[1],
                    'nazwa': nazwa,
                    'kg': float(r[3]) if r[3] is not None else None,
                    'data_zlecenia': str(r[4]) if r[4] is not None else '',
                }
            )
        return render_template('dosypki_list.html', dosypki=dosypki, plan_id=plan_id, rola=role, linia=linia)
