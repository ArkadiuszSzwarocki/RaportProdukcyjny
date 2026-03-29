from flask import Blueprint, request, redirect, url_for, flash, session, render_template, current_app, jsonify, send_file
import logging
import os
import glob
from datetime import date, datetime
from app.db import get_db_connection, rollover_unfinished, sync_dosypka_notifications
from app.decorators import login_required, roles_required
from app.core.audit import audit_log

production_bp = Blueprint('production', __name__)

def bezpieczny_powrot():
    """Wraca do Planisty jeśli to on klikał, w przeciwnym razie na Dashboard"""
    if session.get('rola') == 'planista' or request.form.get('widok_powrotu') == 'planista':
        data = request.form.get('data_planu') or request.form.get('data_powrotu') or request.args.get('data') or str(date.today())
        return url_for('planista.panel_planisty', data=data)
    
    # Try to get sekcja from query string first (URL parameters), then from form
    sekcja = request.args.get('sekcja') or request.form.get('sekcja', 'Zasyp')
    data = request.form.get('data_planu') or request.form.get('data_powrotu') or request.args.get('data') or str(date.today())
    return url_for('main.index', sekcja=sekcja, data=data)


@production_bp.route('/start_zlecenie/<int:id>', methods=['POST'])
@login_required
def start_zlecenie(id):
    """Rozpocznij wykonywanie zlecenia (zmiana statusu na 'w toku')
    
    Workowanie może startować niezależnie - Zasyp to przygotowanie wsadu,
    Workowanie workuje z bufora. Jeśli na Zasyp jest inne zlecenie - pokaż info.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT produkt, tonaz, sekcja, data_planu, typ_produkcji, status, COALESCE(tonaz_rzeczywisty, 0) FROM plan_produkcji WHERE id=%s", (id,))
        z = cursor.fetchone()
        
        warning_info = None  # Informacja o tym co dzieje się na Zasyp
        
        if z:
            produkt, tonaz, sekcja, data_planu, typ, status_obecny, tonaz_rzeczywisty_zasyp = z
            
            # INFO ONLY (nie blokuje): jeśli na Workowanie, sprawdzić co dzieje się na Zasyp
            if sekcja == 'Workowanie':
                cursor.execute(
                    "SELECT id, produkt FROM plan_produkcji "
                    "WHERE sekcja='Zasyp' AND status='w toku' AND DATE(data_planu)=%s LIMIT 1",
                    (data_planu,)
                )
                active_on_zasyp = cursor.fetchone()
                
                if active_on_zasyp and active_on_zasyp[0] != id:
                    # Inne zlecenie aktywne na Zasyp - informuj ale nie blokuj
                    warning_info = {
                        'message': f"Na Zasyp trwa zlecenie: {active_on_zasyp[1]}",
                        'zasyp_order_id': active_on_zasyp[0],
                        'zasyp_order_name': active_on_zasyp[1]
                    }
            
            # Dodatkowa logika kolejki dla Workowanie:
            # Tylko produkt, który miał NAJWCZEŚNIEJ zakończone Zasyp tego dnia, może być uruchomiony jako pierwszy.
            if sekcja == 'Workowanie':
                    # Allow planners/admins to bypass queue restriction
                    role = session.get('rola', '')
                    if role in ('planista', 'admin'):
                        current_app.logger.debug(f'[KOLEJKA] bypass for role={role} plan_id={id} produkt={produkt}')
                    else:
                        try:
                            # Log context for debugging
                            current_app.logger.debug(f'[KOLEJKA] start_zlecenie called id={id} produkt="{produkt}" data_planu={data_planu} role={role}')
                            cursor.execute(
                                "SELECT id, produkt, real_stop FROM plan_produkcji WHERE sekcja='Zasyp' AND status='zakonczone' AND DATE(data_planu)=%s AND real_stop IS NOT NULL ORDER BY real_stop ASC",
                                (data_planu,)
                            )
                            all_closed = cursor.fetchall()
                            current_app.logger.debug(f'[KOLEJKA] closed_zasyp_count={len(all_closed)}')
                            for ac in all_closed:
                                try:
                                    current_app.logger.debug(f'[KOLEJKA] closed: id={ac[0]} produkt="{ac[1]}" real_stop={ac[2]}')
                                except Exception:
                                    current_app.logger.debug(f'[KOLEJKA] closed (raw): {ac}')
                            earliest = all_closed[0] if all_closed else None
                        except Exception as e:
                            current_app.logger.exception('[KOLEJKA] failed to query closed Zasyp: %s', e)
                            earliest = None
                        if earliest:
                            earliest_product = earliest[1]
                            # Normalize product names for robust comparison
                            try:
                                prod_norm = (produkt or '').strip().lower()
                                earliest_norm = (earliest_product or '').strip().lower()
                            except Exception:
                                prod_norm = produkt
                                earliest_norm = earliest_product
                            current_app.logger.debug(f'[KOLEJKA] produkt="{produkt}" earliest_from_zasyp="{earliest_product}" normalized: "{prod_norm}" vs "{earliest_norm}"')
                            if prod_norm != earliest_norm:
                                # Nie zezwalamy na uruchomienie innego produktu niż ten najwcześniej zakończony na Zasyp
                                flash(f"❌ Kolejkowanie Workowanie: aktualnie otwarty powinien być produkt zakończony najwcześniej na Zasyp: {earliest_product}. Najpierw zakończ ten produkt na Zasyp.", 'error')
                                return redirect(bezpieczny_powrot())

            # Zawsze wykonaj START - Workowanie pracuje niezależnie z bufora
            if status_obecny != 'w toku':
                cursor.execute("UPDATE plan_produkcji SET status='zaplanowane', real_stop=NULL WHERE sekcja=%s AND status='w toku'", (sekcja,))
                cursor.execute("UPDATE plan_produkcji SET status='w toku', real_start=NOW(), real_stop=NULL WHERE id=%s", (id,))
                current_app.logger.info('Uruchomiono zlecenie ID=%s, produkt=%s przez %s', id, produkt, session.get('login'))
                audit_log('Uruchomił zlecenie', f'ID={id}, produkt={produkt}, sekcja={sekcja}')
                flash(f"✅ Uruchomiono: {produkt}", 'success')
                try:
                    status_logger = logging.getLogger('status_changes')
                    status_logger.info(f"action=start_zlecenie plan_id={id} old={status_obecny} new=w_toku user={session.get('login')} endpoint={request.path} caller=production.start_zlecenie sekcja={sekcja}")
                except Exception:
                    pass

                # Jeśli jest warning info - dodaj do flash message
                if warning_info:
                    flash(f"ℹ️ {warning_info['message']}", 'info')
            
        conn.commit()
        # commit done — ensure status change logged if not already
        try:
            pass
        except Exception:
            pass
    except Exception as e:
        current_app.logger.error(f"Error starting order {id}: {e}", exc_info=True)
        try:
            conn.rollback()
        except Exception:
            pass
        flash(f"❌ Błąd uruchamiania zlecenia", 'danger')
    finally:
        try:
            conn.close()
        except Exception:
            pass
    
    return redirect(bezpieczny_powrot())


@production_bp.route('/koniec_zlecenie/<int:id>', methods=['POST'])
@login_required
def koniec_zlecenie(id):
    """Zakończ wykonywanie zlecenia"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        final_tonaz = request.form.get('final_tonaz')
        wyjasnienie = request.form.get('wyjasnienie')
        uszkodzone_worki = request.form.get('uszkodzone_worki')
        sekcja = request.form.get('sekcja')
        rzeczywista_waga = 0
        if final_tonaz:
            try:
                rzeczywista_waga = int(float(final_tonaz.replace(',', '.')))
            except Exception:
                pass

        sql = "UPDATE plan_produkcji SET status='zakonczone', real_stop=NOW()"
        params = []
        if rzeczywista_waga > 0:
            sql += ", tonaz_rzeczywisty=%s"
            params.append(rzeczywista_waga)
        if wyjasnienie:
            sql += ", wyjasnienie_rozbieznosci=%s"
            params.append(wyjasnienie)
        if uszkodzone_worki and sekcja == 'Workowanie':
            try:
                uszkodzone_count = int(uszkodzone_worki)
                sql += ", uszkodzone_worki=%s"
                params.append(uszkodzone_count)
            except (ValueError, TypeError):
                pass
        sql += " WHERE id=%s"
        params.append(id)
        cursor.execute(sql, tuple(params))
        
        # Zasyp i Workowanie działają NIEZALEŻNIE
        # Brak automatycznego aktualizowania Workowania gdy kończy się Zasyp
        conn.commit()
        current_app.logger.info('Zakończono zlecenie ID=%s przez %s', id, session.get('login'))
        audit_log('Zakończył zlecenie', f'ID={id}, tonaz_rz={rzeczywista_waga} kg')
        try:
            status_logger = logging.getLogger('status_changes')
            status_logger.info(f"action=koniec_zlecenie plan_id={id} new=zakonczone user={session.get('login')} endpoint={request.path} caller=production.koniec_zlecenie sekcja={sekcja}")
        except Exception:
            pass
        
        # WAŻNE: Odśwież bufor teraz, żeby kolejka się przesuniała
        try:
            from app.db import refresh_bufor_queue
            refresh_bufor_queue(conn)
        except Exception as e:
            current_app.logger.warning(f'Failed to refresh bufor after koniec_zlecenie: {e}')
    except Exception as e:
        current_app.logger.error(f"Error completing order {id}: {e}", exc_info=True)
        try:
            conn.rollback()
        except Exception:
            pass
        flash(f"❌ Błąd zakończenia zlecenia", 'danger')
    finally:
        try:
            conn.close()
        except Exception:
            pass
    
    return redirect(bezpieczny_powrot())


@production_bp.route('/zapisz_wyjasnienie/<int:id>', methods=['POST'])
@login_required
def zapisz_wyjasnienie(id):
    """Zapisz wyjaśnienie rozbieżności"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE plan_produkcji SET wyjasnienie_rozbieznosci=%s WHERE id=%s", (request.form.get('wyjasnienie'), id))
        conn.commit()
    except Exception as e:
        current_app.logger.error(f"Error saving explanation for {id}: {e}", exc_info=True)
        try:
            conn.rollback()
        except Exception:
            pass
        flash(f"❌ Błąd zapisania wyjaśnienia", 'danger')
    finally:
        try:
            conn.close()
        except Exception:
            pass
    
    return redirect(bezpieczny_powrot())


@production_bp.route('/koniec_zlecenie_page/<int:id>', methods=['GET'])
@login_required
def koniec_zlecenie_page(id):
    """Render confirmation fragment for ending job order"""
    sekcja = request.args.get('sekcja', request.form.get('sekcja', 'Zasyp'))
    produkt = None
    tonaz_rzeczywisty = None
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT produkt, tonaz_rzeczywisty FROM plan_produkcji WHERE id=%s", (id,))
        row = cursor.fetchone()
        if row:
            produkt, tonaz_rzeczywisty = row[0], row[1]
    except Exception as e:
        current_app.logger.error(f'Failed to fetch plan {id} for koniec_zlecenie_page: {e}', exc_info=True)
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return render_template('koniec_zlecenie.html', id=id, sekcja=sekcja, produkt=produkt, tonaz=tonaz_rzeczywisty)


@production_bp.route('/test-pobierz-raport', methods=['GET'])
@login_required
def api_test_pobierz_raport():
    """Test endpoint: return most recent file from raporty/ directory as attachment"""
    try:
        rap_dir = os.path.join(current_app.root_path, 'raporty')
        if not os.path.isdir(rap_dir):
            current_app.logger.warning(f'Reports directory not found: {rap_dir}')
            return jsonify({'error': 'raporty directory not found'}), 404
        files = glob.glob(os.path.join(rap_dir, '*'))
        if not files:
            current_app.logger.warning('No reports available in raporty directory')
            return jsonify({'error': 'no reports available'}), 404
        latest = max(files, key=os.path.getmtime)
        return send_file(latest, as_attachment=True, download_name=os.path.basename(latest))
    except Exception as e:
        current_app.logger.error(f'Failed to send report: {e}', exc_info=True)
        return jsonify({'error': 'failed to send file'}), 500


@production_bp.route('/szarza_page/<int:plan_id>', methods=['GET'])
@login_required
def szarza_page(plan_id):
    """Render form to add a szarża (charge) for Zasyp plan"""
    current_app.logger.debug(f'[SZARZA_PAGE] Called with plan_id={plan_id}')
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT produkt, typ_produkcji FROM plan_produkcji WHERE id=%s AND sekcja='Zasyp'",
            (plan_id,)
        )
        plan = cursor.fetchone()
        if not plan:
            current_app.logger.warning(f'[SZARZA_PAGE] Plan {plan_id} not found')
            flash('Plan nie znaleziony', 'error')
            return redirect('/')
        
        produkt, typ_produkcji = plan[0], plan[1]
        current_app.logger.debug(f'[SZARZA_PAGE] Rendering form for plan_id={plan_id}, produkt={produkt}, typ={typ_produkcji}')
        return render_template('dodaj_palete_popup.html', 
                     plan_id=plan_id, 
                     sekcja='Zasyp',
                     produkt=produkt,
                     typ=typ_produkcji)
    except Exception as e:
        current_app.logger.error(f'[SZARZA_PAGE] Error in szarza_page: {e}', exc_info=True)
        flash('Błąd pobierania danych planu', 'error')
        return redirect('/')
    finally:
        try:
            conn.close()
        except Exception:
            pass


@production_bp.route('/wyjasnij_page/<int:id>', methods=['GET'])
@login_required
def wyjasnij_page(id):
    """Render form to submit explanation via zapisz_wyjasnienie"""
    # If this endpoint is requested directly (not via AJAX/data-slide),
    # rendering the raw fragment results in a bare page. Redirect back
    # to a safe location to avoid showing an unstyled fragment.
    if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
        return redirect(bezpieczny_powrot())
    return render_template('wyjasnij.html', id=id)


@production_bp.route('/manual_rollover', methods=['POST'])
@roles_required('lider', 'admin')
def manual_rollover():
    """Manually rollover unfinished jobs from one date to another"""
    from_date = request.form.get('from_date') or request.args.get('from_date')
    to_date = request.form.get('to_date') or request.args.get('to_date')
    if not from_date or not to_date:
        flash('Brakuje daty źródłowej lub docelowej', 'error')
        return redirect(bezpieczny_powrot())

    try:
        added = rollover_unfinished(from_date, to_date)
        flash(f'Przeniesiono {added} zleceń z {from_date} na {to_date}', 'success')
    except Exception as e:
        current_app.logger.exception('manual_rollover failed: %s', e)
        flash('Błąd podczas przenoszenia zleceń', 'error')

    return redirect(bezpieczny_powrot())


@production_bp.route('/obsada_page', methods=['GET'])
@production_bp.route('/api/obsada_page', methods=['GET'])
@login_required
def obsada_page():
    """Render slide-over for managing obsada (workers on shift) for a sekcja"""
    sekcja = request.args.get('sekcja', request.form.get('sekcja', 'Workowanie'))
    # allow optional date parameter (YYYY-MM-DD) to view/modify obsada for other dates
    date_str = request.args.get('date') or request.form.get('date')
    try:
        qdate = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today()
    except Exception:
        qdate = date.today()

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # all obsada entries for given date (grouped by sekcja)
        cursor.execute("SELECT oz.sekcja, oz.id, p.imie_nazwisko, p.id FROM obsada_zmiany oz JOIN pracownicy p ON oz.pracownik_id = p.id WHERE oz.data_wpisu = %s ORDER BY oz.sekcja, p.imie_nazwisko", (qdate,))
        rows = cursor.fetchall()
        obsady_map = {}
        for r in rows:
            sekc, oz_id, name, pracownik_id = r[0], r[1], r[2], r[3]
            obsady_map.setdefault(sekc, []).append((oz_id, name, pracownik_id))
        # available employees: exclude those already assigned for that date (any sekcja),
        # those marked absent in obecnosc, and those on approved leave (wnioski_wolne)
        cursor.execute(
            "SELECT id, imie_nazwisko FROM pracownicy "
            "WHERE id NOT IN (SELECT pracownik_id FROM obsada_zmiany WHERE data_wpisu=%s) "
            "AND id NOT IN (SELECT pracownik_id FROM obecnosc WHERE data_wpisu=%s AND typ IN ('Nieobecnosc','Urlop','L4','Opieka')) "
            "AND id NOT IN (SELECT pracownik_id FROM wnioski_wolne WHERE status='approved' AND data_od <= %s AND data_do >= %s) "
            "AND id NOT IN (SELECT pracownik_id FROM uzytkownicy WHERE rola IN ('admin','zarzad') AND pracownik_id IS NOT NULL) "
            "ORDER BY imie_nazwisko",
            (qdate, qdate, qdate, qdate)
        )
        wszyscy = cursor.fetchall()
        # pełna lista pracowników (dla wyboru liderów) - tylko liderzy
        cursor.execute("SELECT p.id, p.imie_nazwisko FROM pracownicy p JOIN uzytkownicy u ON p.id = u.pracownik_id WHERE u.rola='lider' ORDER BY p.imie_nazwisko")
        all_pracownicy = cursor.fetchall()
        # pobierz liderów dla tej daty (jeśli istnieją)
        cursor.execute("SELECT lider_psd_id, lider_agro_id FROM obsada_liderzy WHERE data_wpisu=%s", (qdate,))
        lider_row = cursor.fetchone()
        lider_psd_id = lider_row[0] if lider_row else None
        lider_agro_id = lider_row[1] if lider_row else None
    finally:
        try: conn.close()
        except Exception: pass

    # If requested via AJAX or the explicit API route, return only the fragment
    try:
        is_ajax = request.headers.get('X-Requested-With', '') == 'XMLHttpRequest' or request.path.startswith('/api/') or request.args.get('fragment') == 'true'
    except Exception:
        is_ajax = False

    if is_ajax:
        return render_template('obsada_fragment.html', sekcja=sekcja, obsady_map=obsady_map, pracownicy=wszyscy, rola=session.get('rola'), qdate=qdate, lider_psd_id=lider_psd_id, lider_agro_id=lider_agro_id, all_pracownicy=all_pracownicy)

    return render_template('obsada.html', sekcja=sekcja, obsady_map=obsady_map, pracownicy=wszyscy, rola=session.get('rola'), qdate=qdate, lider_psd_id=lider_psd_id, lider_agro_id=lider_agro_id, all_pracownicy=all_pracownicy)


@production_bp.route('/dosypka_page/<int:plan_id>', methods=['GET'])
@roles_required('laborant', 'planista', 'admin')
def dosypka_page(plan_id):
    """Render form to add up to 4 dosypki for an active Zasyp plan."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT produkt, typ_produkcji, status FROM plan_produkcji WHERE id=%s AND sekcja='Zasyp'", (plan_id,))
        plan = cursor.fetchone()
        if not plan:
            flash('Plan nie znaleziony', 'error')
            return redirect('/')
        
        produkt, typ_produkcji, status = plan[0], plan[1], plan[2]
        # Only allow adding dosypki to active orders
        if status != 'w toku':
            flash('Dosypki można dodawać tylko do aktywnego zlecenia (status "w toku")', 'warning')
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
                """
                SELECT id, nazwa, kg, data_zlecenia, COALESCE(anulowana, 0), anulowal_login, data_anulowania
                FROM dosypki
                WHERE plan_id=%s AND szarza_id=%s
                ORDER BY COALESCE(anulowana, 0) ASC, data_zlecenia DESC
                """,
                (plan_id, szarza_id_int)
            )
        else:
            cursor.execute(
                """
                SELECT id, nazwa, kg, data_zlecenia, COALESCE(anulowana, 0), anulowal_login, data_anulowania
                FROM dosypki
                WHERE plan_id=%s
                ORDER BY COALESCE(anulowana, 0) ASC, data_zlecenia DESC
                """,
                (plan_id,)
            )

        existing_dosypki = [
            {
                'id': row[0],
                'nazwa': row[1],
                'kg': float(row[2]) if row[2] is not None else 0,
                'data_zlecenia': str(row[3]) if row[3] is not None else '',
                'anulowana': bool(row[4]),
                'anulowal_login': row[5],
                'data_anulowania': str(row[6]) if row[6] is not None else '',
            }
            for row in cursor.fetchall()
        ]

        return render_template(
            'dodaj_dosypke_popup.html',
            plan_id=plan_id,
            produkt=produkt,
            typ=typ_produkcji,
            szarza_id=szarza_id,
            existing_dosypki=existing_dosypki,
        )
    except Exception as e:
        current_app.logger.error(f'Error in dosypka_page: {e}', exc_info=True)
        flash('Błąd pobierania danych planu', 'error')
        return redirect('/')
    finally:
        try:
            conn.close()
        except Exception:
            pass


@production_bp.route('/dodaj_dosypke', methods=['POST'])
@roles_required('laborant', 'admin')
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

    # Check if "brak dosypki" (no supplement) was selected
    brak_dosypki = request.form.get('brak_dosypki') == '1'

    # Collect up to 10 pairs of name/kg from the form
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

    # If "brak dosypki" is selected, create special entry
    if brak_dosypki:
        entries = [('Brak dosypki', 0)]
    elif not entries:
        flash('Brak poprawnych pozycji dosypki do zapisania', 'warning')
        return redirect(bezpieczny_powrot())

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Validate plan exists and is active
        cursor.execute(
            "SELECT id, produkt, data_planu, status FROM plan_produkcji WHERE id=%s AND sekcja='Zasyp'",
            (plan_id,)
        )
        r = cursor.fetchone()
        if not r or r[3] != 'w toku':
            flash('Dosypki można dodawać tylko do aktywnego zlecenia (status "w toku")', 'warning')
            return redirect(bezpieczny_powrot())

        pracownik_id = session.get('pracownik_id') if 'pracownik_id' in session else None
        created_by_user_id = session.get('user_id') if 'user_id' in session else None
        for name, kg in entries:
            cursor.execute("INSERT INTO dosypki (plan_id, szarza_id, nazwa, kg, pracownik_id, potwierdzone) VALUES (%s, %s, %s, %s, %s, 0)", (plan_id, szarza_id, name, kg, pracownik_id))
            try:
                # Log individual dosypka creation to audit log
                audit_log('Dodał dosypkę', f'nazwa={name}, kg={kg}, plan_id={plan_id}')
            except Exception:
                # don't break on audit logging failure
                current_app.logger.debug('audit_log failed for dosypka insert', exc_info=True)
        sync_dosypka_notifications(
            plan_id=plan_id,
            author_name=session.get('imie_nazwisko') or session.get('login'),
            created_by_user_id=created_by_user_id,
            conn=conn,
            cursor=cursor,
        )

        conn.commit()
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
@roles_required('pracownik', 'produkcja', 'lider', 'admin')
def potwierdz_dosypke(dosypka_id):
    """Operator potwierdza odczytanie dosypki - mark as confirmed."""
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM dosypki WHERE id=%s AND potwierdzone=0 AND COALESCE(anulowana, 0)=0", (dosypka_id,))
        r = cursor.fetchone()
        if not r:
            if is_ajax:
                return jsonify({'success': False, 'message': 'Pozycja nieznaleziona lub już potwierdzona'}), 404
            flash('Pozycja nieznaleziona lub już potwierdzona', 'warning')
            return redirect(bezpieczny_powrot())

        pracownik_id = session.get('pracownik_id') if 'pracownik_id' in session else None
        
        # First, get the plan_id from dosypka to update tonaz_rzeczywisty
        cursor.execute("SELECT plan_id FROM dosypki WHERE id=%s", (dosypka_id,))
        dosypka_row = cursor.fetchone()
        plan_id = dosypka_row[0] if dosypka_row else None
        
        cursor.execute("UPDATE dosypki SET potwierdzone=1, potwierdzil_pracownik_id=%s, data_potwierdzenia=NOW() WHERE id=%s", (pracownik_id, dosypka_id))
        
        # Synchronize plan's tonaz_rzeczywisty = SUM(szarże) + SUM(dosypki potwierdzone)
        if plan_id:
            cursor.execute(
                "UPDATE plan_produkcji SET tonaz_rzeczywisty = "
                "COALESCE((SELECT SUM(waga) FROM szarze WHERE plan_id = %s), 0) + "
                "COALESCE((SELECT SUM(kg) FROM dosypki WHERE plan_id = %s AND potwierdzone = 1 AND COALESCE(anulowana, 0) = 0), 0) "
                "WHERE id = %s",
                (plan_id, plan_id, plan_id)
            )
            sync_dosypka_notifications(
                plan_id=plan_id,
                author_name=session.get('imie_nazwisko') or session.get('login'),
                created_by_user_id=session.get('user_id'),
                conn=conn,
                cursor=cursor,
            )
        
        conn.commit()
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
@roles_required('laborant', 'admin')
def anuluj_dosypke(dosypka_id):
    """Mark dosypka as anulowana instead of deleting it."""
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, plan_id FROM dosypki WHERE id=%s AND potwierdzone=0 AND COALESCE(anulowana, 0)=0",
            (dosypka_id,)
        )
        row = cursor.fetchone()
        if not row:
            if is_ajax:
                return jsonify({'success': False, 'message': 'Pozycja nie istnieje, została już potwierdzona albo anulowana'}), 404
            flash('Pozycja nie istnieje, została już potwierdzona albo anulowana', 'warning')
            return redirect(bezpieczny_powrot())

        anulowal_login = session.get('login') or session.get('imie_nazwisko') or 'unknown'
        cursor.execute(
            "UPDATE dosypki SET anulowana=1, data_anulowania=NOW(), anulowal_login=%s WHERE id=%s",
            (anulowal_login, dosypka_id)
        )
        sync_dosypka_notifications(
            plan_id=row[1],
            author_name=session.get('imie_nazwisko') or session.get('login'),
            created_by_user_id=session.get('user_id'),
            conn=conn,
            cursor=cursor,
        )
        conn.commit()
        if is_ajax:
            return jsonify({
                'success': True,
                'message': 'Dosypka została anulowana.',
                'plan_id': row[1],
                'anulowal_login': anulowal_login,
            })
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
@roles_required('laborant', 'pracownik', 'produkcja', 'lider', 'admin')
def api_dosypki():
    """Return JSON of active unconfirmed dosypki for operators."""
    current_app.logger.debug(f"[api_dosypki] Endpoint reached by user role: {session.get('rola')}")
    plan_id = request.args.get('plan_id', None)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        if plan_id:
            cursor.execute(
                """
                SELECT id, plan_id, nazwa, kg, data_zlecenia,
                       COALESCE(anulowana, 0), anulowal_login, data_anulowania
                FROM dosypki
                WHERE potwierdzone = 0 AND COALESCE(anulowana, 0) = 0 AND plan_id = %s
                ORDER BY data_zlecenia ASC
                """,
                (plan_id,)
            )
        else:
            cursor.execute(
                """
                SELECT id, plan_id, nazwa, kg, data_zlecenia,
                       COALESCE(anulowana, 0), anulowal_login, data_anulowania
                FROM dosypki
                  WHERE potwierdzone = 0 AND COALESCE(anulowana, 0) = 0
                  ORDER BY data_zlecenia ASC
                """
            )
        rows = cursor.fetchall()
        role = session.get('rola', '')
        result = []
        # Roles that should see the detailed `nazwa` because they need to execute the dosypka
        visible_roles = ('laborant', 'pracownik', 'produkcja', 'lider', 'admin')
        for r in rows:
            if role in visible_roles:
                nazwa = r[2]
            else:
                nazwa = None
            result.append({
                'id': r[0],
                'plan_id': r[1],
                'nazwa': nazwa,
                'kg': float(r[3]),
                'data_zlecenia': str(r[4]),
                'anulowana': bool(r[5]),
                'anulowal_login': r[6],
                'data_anulowania': str(r[7]) if r[7] is not None else '',
            })
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
@roles_required('laborant', 'pracownik', 'produkcja', 'lider', 'admin')
def dosypki_list():
    """Render slide-over page with list of active unconfirmed dosypki for operators."""
    # Accept optional plan_id to filter dosypki for a specific zlecenie
    plan_id = request.args.get('plan_id', None)
    # Fetch unconfirmed dosypki server-side so fragment shows data even if client JS doesn't run
    from app.db import list_unconfirmed_dosypki
    rows = list_unconfirmed_dosypki()
    role = session.get('rola', '')
    visible_roles = ('laborant', 'pracownik', 'produkcja', 'lider', 'admin')
    dosypki = []
    for r in rows:
        # Filter by plan_id if provided
        if plan_id and str(r[1]) != str(plan_id):
            continue
        if role in visible_roles:
            nazwa = r[2]
        else:
            nazwa = None
        dosypki.append({'id': r[0], 'plan_id': r[1], 'nazwa': nazwa, 'kg': float(r[3]) if r[3] is not None else None, 'data_zlecenia': str(r[4]) if r[4] is not None else ''})
    # Always return the fragment regardless of X-Requested-With
    # because the quick popup JS via fetch expects just the fragment HTML.
    return render_template('dosypki_list.html', dosypki=dosypki, plan_id=plan_id, rola=role)


