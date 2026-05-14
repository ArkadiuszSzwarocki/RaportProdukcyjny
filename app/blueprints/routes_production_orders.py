import glob
import logging
import os
from flask import current_app, flash, jsonify, redirect, render_template, request, send_file, session
from app.core.audit import audit_log
from app.db import get_db_connection, get_table_name
from app.decorators import login_required
from app.services.zasyp_etapy_service import ZasypEtapyService

def register_production_order_routes(production_bp, bezpieczny_powrot):
    from app.services.mqtt_service import get_latest_data

    @production_bp.route('/start_zlecenie/<int:id>', methods=['POST'])
    @login_required
    def start_zlecenie(id):
        """Rozpocznij wykonywanie zlecenia (zmiana statusu na 'w toku')

        Workowanie może startować niezależnie - Zasyp to przygotowanie wsadu,
        Workowanie workuje z bufora. Jeśli na Zasyp jest inne zlecenie - pokaż info.
        """
        conn = get_db_connection()
        try:
            role_lc = str(session.get('rola') or '').strip().lower()
            if role_lc in ['laborant', 'laboratorium']:
                flash('❌ Brak uprawnień: laborant nie może uruchamiać zleceń.', 'warning')
                return redirect(bezpieczny_powrot())

            linia_input = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
            linia = str(linia_input).upper()
            table_plan = get_table_name('plan_produkcji', linia)
            cursor = conn.cursor()
            cursor.execute(f"SELECT produkt, tonaz, sekcja, data_planu, typ_produkcji, status, COALESCE(tonaz_rzeczywisty, 0) FROM {table_plan} WHERE id=%s", (id,))
            z = cursor.fetchone()

            warning_info = None

            if z:
                produkt, tonaz, sekcja, data_planu, typ, status_obecny, tonaz_rzeczywisty_zasyp = z

                if sekcja == 'Workowanie':
                    cursor.execute(
                        f"SELECT id, produkt FROM {table_plan} "
                        "WHERE sekcja='Zasyp' AND status='w toku' AND DATE(data_planu)=%s LIMIT 1",
                        (data_planu,),
                    )
                    active_on_zasyp = cursor.fetchone()

                    if active_on_zasyp and active_on_zasyp[0] != id:
                        warning_info = {
                            'message': f"Na Zasyp trwa zlecenie: {active_on_zasyp[1]}",
                            'zasyp_order_id': active_on_zasyp[0],
                            'zasyp_order_name': active_on_zasyp[1],
                        }

                if sekcja == 'Workowanie':
                    # Role is normalized here to avoid case/whitespace mismatches.
                    if role_lc in ('planista', 'admin', 'zarzad'):
                        current_app.logger.debug(f'[KOLEJKA] bypass for role={role_lc} plan_id={id} produkt={produkt}')
                    else:
                        try:
                            table_bufor = get_table_name('bufor', linia)
                            current_app.logger.debug(f'[KOLEJKA] start_zlecenie check id={id} produkt="{produkt}" data_planu={data_planu}')

                            cursor.execute(
                                f"""
                                SELECT MIN(b.kolejka)
                                FROM {table_bufor} b
                                WHERE DATE(b.data_planu) = %s AND b.status = 'aktywny'
                                  AND EXISTS (
                                      SELECT 1 FROM {table_plan} w
                                      WHERE w.sekcja = 'Workowanie' AND w.status IN ('zaplanowane', 'w toku')
                                        AND w.produkt = b.produkt AND w.data_planu = b.data_planu
                                  )
                                """,
                                (data_planu,),
                            )
                            min_q_row = cursor.fetchone()
                            global_min_queue = min_q_row[0] if min_q_row else None

                            if global_min_queue is not None:
                                cursor.execute(
                                    f"""
                                    SELECT kolejka FROM {table_bufor}
                                    WHERE produkt = %s AND DATE(data_planu) = %s AND status = 'aktywny'
                                    """,
                                    (produkt, data_planu),
                                )
                                my_q_row = cursor.fetchone()
                                my_q = my_q_row[0] if my_q_row else None

                                if my_q is not None and my_q > global_min_queue:
                                    cursor.execute(
                                        f"SELECT produkt FROM {table_bufor} WHERE kolejka = %s AND status = 'aktywny' AND DATE(data_planu) = %s LIMIT 1",
                                        (global_min_queue, data_planu),
                                    )
                                    earliest_row = cursor.fetchone()
                                    earliest_produkt = earliest_row[0] if earliest_row else '?'

                                    # Bypass FIFO for selected roles
                                    role_lc = str(session.get('rola') or '').strip().lower()
                                    can_bypass = role_lc in ['admin', 'lider', 'planista', 'zarzad']

                                    if not can_bypass:
                                        flash(
                                            f"❌ Kolejkowanie Workowanie: W buforze znajduje się produkt przewidziany wcześniej do startu: {earliest_produkt}. Zalecana kolejność FIFO.",
                                            'error',
                                        )
                                        return redirect(bezpieczny_powrot())
                        except Exception as e:
                            current_app.logger.exception('[KOLEJKA] FIFO check failed: %s', e)

                if status_obecny != 'w toku':
                    # Capture machine counter for AGRO Workowanie
                    start_counter = 0
                    if sekcja == 'Workowanie' and linia == 'AGRO':
                        try:
                            start_counter = get_latest_data().get('counter', 0)
                        except Exception:
                            pass

                    # Ensure only one active plan per section in this hall
                    cursor.execute(f"UPDATE {table_plan} SET status='zaplanowane', real_stop=NULL WHERE sekcja=%s AND status='w toku'", (sekcja,))
                    cursor.execute(f"UPDATE {table_plan} SET status='w toku', real_start=NOW(), real_stop=NULL, start_machine_counter=%s WHERE id=%s", (start_counter, id))
                    current_app.logger.info('Uruchomiono zlecenie ID=%s, produkt=%s przez %s', id, produkt, session.get('login'))
                    audit_log('Uruchomił zlecenie', f'ID={id}, produkt={produkt}, sekcja={sekcja}')
                    flash(f"✅ Uruchomiono: {produkt}", 'success')
                    try:
                        status_logger = logging.getLogger('status_changes')
                        status_logger.info(f"action=start_zlecenie plan_id={id} old={status_obecny} new=w_toku user={session.get('login')} endpoint={request.path} caller=production.start_zlecenie sekcja={sekcja}")
                    except Exception:
                        pass

                    if warning_info:
                        flash(f"ℹ️ {warning_info['message']}", 'info')

                    if sekcja == 'Zasyp':
                        try:
                            from app.db import refresh_bufor_queue

                            conn.commit()
                            refresh_bufor_queue(linia=linia)
                            current_app.logger.info('[BUFOR] refresh po starcie Zasypu id=%s produkt=%s', id, produkt)
                        except Exception as _rb_err:
                            current_app.logger.warning('[BUFOR] refresh_bufor_queue po starcie Zasypu failed: %s', _rb_err)

            conn.commit()
            try:
                pass
            except Exception:
                pass
        except Exception as e:
            current_app.logger.error(f'Error starting order {id}: {e}', exc_info=True)
            try:
                conn.rollback()
            except Exception:
                pass
            flash('❌ Błąd uruchamiania zlecenia', 'danger')
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
            linia = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
            table_plan = get_table_name('plan_produkcji', linia)

            cursor.execute(f"SELECT produkt, data_planu FROM {table_plan} WHERE id=%s", (id,))
            plan_meta = cursor.fetchone() or (None, None)
            produkt, data_planu = plan_meta[0], plan_meta[1]

            rzeczywista_waga = 0
            if final_tonaz:
                try:
                    rzeczywista_waga = int(float(final_tonaz.replace(',', '.')))
                except Exception:
                    pass

            sql = f"UPDATE {table_plan} SET status='zakonczone', real_stop=NOW()"
            params = []
            if rzeczywista_waga > 0:
                sql += ', tonaz_rzeczywisty=%s'
                params.append(rzeczywista_waga)
            if wyjasnienie:
                sql += ', wyjasnienie_rozbieznosci=%s'
                params.append(wyjasnienie)
            if uszkodzone_worki and sekcja == 'Workowanie':
                try:
                    uszkodzone_count = int(uszkodzone_worki)
                    sql += ', uszkodzone_worki=%s'
                    params.append(uszkodzone_count)
                except (ValueError, TypeError):
                    pass
            sql += ' WHERE id=%s'
            params.append(id)
            cursor.execute(sql, tuple(params))

            if sekcja == 'Zasyp' and rzeczywista_waga > 0:
                try:
                    if str(linia).upper() == 'AGRO':
                        cursor.execute(
                            f"UPDATE {table_plan} SET tonaz = %s WHERE produkt = %s AND data_planu = %s AND sekcja = 'Workowanie' AND status != 'zakonczone'",
                            (rzeczywista_waga, produkt, data_planu),
                        )
                    else:
                        cursor.execute(
                            f"UPDATE {table_plan} SET tonaz = %s WHERE zasyp_id = %s AND sekcja = 'Workowanie' AND status != 'zakonczone'",
                            (rzeczywista_waga, id),
                        )
                    current_app.logger.info('[SYNC] Zaktualizowano tonaz Workowania na %s kg po zakończeniu Zasypu id=%s', rzeczywista_waga, id)
                except Exception as _sync_err:
                    current_app.logger.warning('[SYNC] Błąd synchronizacji tonaz Workowania: %s', _sync_err)

            if linia == 'AGRO' and sekcja == 'Workowanie':
                from app.services.agro_warehouse_service import AgroWarehouseService
                packaging_results = []
                for key, value in request.form.items():
                    if key.startswith('stan_po_'):
                        parts = key.split('_')
                        if len(parts) == 4:
                            try:
                                packaging_results.append({
                                    'link_id': int(parts[3]),
                                    'stan_po': float(value or 0)
                                })
                            except: pass
                
                if packaging_results:
                    szt_na_palecie = int(request.form.get('szt_na_palecie', 40))
                    AgroWarehouseService.finalize_packaging_usage(id, szt_na_palecie, packaging_results, session.get('login'))

            conn.commit()
            current_app.logger.info('Zakończono zlecenie ID=%s przez %s', id, session.get('login'))
            audit_log('Zakończył zlecenie', f'ID={id}, tonaz_rz={rzeczywista_waga} kg')
            try:
                status_logger = logging.getLogger('status_changes')
                status_logger.info(f"action=koniec_zlecenie plan_id={id} new=zakonczone user={session.get('login')} endpoint={request.path} caller=production.koniec_zlecenie sekcja={sekcja}")
            except Exception:
                pass

            if sekcja == 'Zasyp':
                try:
                    ZasypEtapyService.stop_any_running_etap(
                        plan_id=id,
                        linia=linia,
                        user_login=session.get('login') or 'system',
                    )
                except Exception as e:
                    current_app.logger.warning('stop_any_running_etap failed for id=%s: %s', id, e)

            try:
                from app.db import refresh_bufor_queue

                refresh_bufor_queue(conn, linia=linia)
            except Exception as e:
                current_app.logger.warning(f'Failed to refresh bufor after koniec_zlecenie: {e}')
        except Exception as e:
            current_app.logger.error(f'Error completing order {id}: {e}', exc_info=True)
            try:
                conn.rollback()
            except Exception:
                pass
            flash('❌ Błąd zakończenia zlecenia', 'danger')
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
            linia = request.args.get('linia') or request.form.get('linia', 'PSD')
            table_plan = get_table_name('plan_produkcji', linia)
            cursor = conn.cursor()
            cursor.execute(f"UPDATE {table_plan} SET wyjasnienie_rozbieznosci=%s WHERE id=%s", (request.form.get('wyjasnienie'), id))
            conn.commit()
        except Exception as e:
            current_app.logger.error(f'Error saving explanation for {id}: {e}', exc_info=True)
            try:
                conn.rollback()
            except Exception:
                pass
            flash('❌ Błąd zapisania wyjaśnienia', 'danger')
        finally:
            try:
                conn.close()
            except Exception:
                pass

        return redirect(bezpieczny_powrot())

    @production_bp.route('/koniec_zlecenie_page/<int:id>', methods=['GET'])
    @login_required
    def koniec_zlecenie_page(id):
        """Widok potwierdzenia zakończenia zlecenia (analogicznie do dawnego modalu)."""
        linia_input = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
        linia = str(linia_input).upper()
        sekcja = request.args.get('sekcja', request.form.get('sekcja', 'Zasyp'))
        produkt = None
        tonaz_rzeczywisty = None
        conn = get_db_connection()
        try:
            table_plan = get_table_name('plan_produkcji', linia)
            cursor = conn.cursor()
            cursor.execute(f"SELECT produkt, tonaz_rzeczywisty FROM {table_plan} WHERE id=%s", (id,))
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

        linked_packaging = []
        if linia == 'AGRO' and sekcja == 'Workowanie':
            from app.services.agro_warehouse_service import AgroWarehouseService
            linked_packaging = AgroWarehouseService.get_linked_packaging(id)

        return render_template('koniec_zlecenie.html', id=id, sekcja=sekcja, produkt=produkt, tonaz=tonaz_rzeczywisty, linked_packaging=linked_packaging, linia=linia)

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

    @production_bp.route('/szarza_page/<int:plan_id>', methods=['GET'], endpoint='szarza_page')
    @production_bp.route('/zasyp_page/<int:plan_id>', methods=['GET'], endpoint='zasyp_page')
    @login_required
    def szarza_page(plan_id):
        """Strona dodawania nowego zasypu dla konkretnego planu."""
        linia_input = request.args.get('linia') or request.form.get('linia') or session.get('selected_hall_view') or 'PSD'
        linia = str(linia_input).upper()
        role = (session.get('rola') or '').lower()
        is_admin_role = role in ['admin', 'zarzad', 'planista']
        is_ops_role = role in ['operator', 'pracownik', 'lider', 'stepnpio']
        if not is_admin_role and not is_ops_role:
            flash('Brak uprawnień do dodawania zasypów.', 'warning')
            return redirect('/')
        current_app.logger.debug(f'[SZARZA_PAGE] Called with plan_id={plan_id}')

        conn = get_db_connection()
        try:
            table_plan = get_table_name('plan_produkcji', linia)
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT produkt, typ_produkcji FROM {table_plan} WHERE id=%s AND sekcja='Zasyp'",
                (plan_id,),
            )
            plan = cursor.fetchone()
            if not plan:
                current_app.logger.warning(f'[SZARZA_PAGE] Plan {plan_id} not found')
                flash('Plan nie znaleziony', 'error')
                return redirect('/')

            produkt, typ_produkcji = plan[0], plan[1]

            table_szarze = get_table_name('szarze', linia)
            cursor.execute(f"SELECT MAX(nr_szarzy) FROM {table_szarze} WHERE plan_id=%s", (plan_id,))
            max_nr = cursor.fetchone()[0]
            next_nr = (max_nr or 0) + 1

            current_app.logger.debug(f'[SZARZA_PAGE] Rendering form for plan_id={plan_id}, produkt={produkt}, typ={typ_produkcji}, linia={linia}, next_nr={next_nr}')
            return render_template(
                'warehouse/popups/add_pallet.html',
                plan_id=plan_id,
                sekcja='Zasyp',
                produkt=produkt,
                typ=typ_produkcji,
                linia=linia,
                next_nr_szarzy=next_nr,
            )
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
        if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
            return redirect(bezpieczny_powrot())
        return render_template('wyjasnij.html', id=id)
