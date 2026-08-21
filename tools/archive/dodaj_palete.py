    def dodaj_palete(plan_id):
        """Add paleta (package) to Workowanie buffer."""
        linia = resolve_request_linia()
        table_plan = get_table_name('plan_produkcji', linia)
        table_pal = get_table_name('palety_workowanie', linia)
        table_zasypy = get_table_name('szarze', linia)
    
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            current_app.logger.debug('dodaj_palete: plan_id=%s', plan_id)
        except Exception:
            pass
    
        try:
            waga_input = int(float(request.form.get('waga_palety', '0').replace(',', '.')))
        except Exception:
            waga_input = 0
    
        nr_plomby = str(request.form.get('nr_plomby') or '').strip()
        if not nr_plomby:
            nr_plomby = None
        elif len(nr_plomby) > 100:
            nr_plomby = nr_plomby[:100]
    
        cursor.execute(f"SELECT sekcja, data_planu, produkt, data_produkcji, zasyp_id FROM {table_plan} WHERE id=%s", (plan_id,))
        plan_row = cursor.fetchone()
    
        if not plan_row:
            conn.close()
            return ('Błąd: Plan nie znaleziony', 404)
    
        now_ts = datetime.now()
        plan_sekcja, _plan_data, plan_produkt, plan_data_produkcji, plan_zasyp_id = plan_row
    
        input_data_produkcji = str(request.form.get('data_produkcji') or '').strip()
        if input_data_produkcji:
            try:
                datetime.strptime(input_data_produkcji, '%Y-%m-%d')
            except ValueError:
                conn.close()
                return ('Błąd: Nieprawidłowy format daty produkcji (oczekiwano RRRR-MM-DD)', 400)
            selected_data_produkcji = input_data_produkcji
        elif plan_data_produkcji:
            if hasattr(plan_data_produkcji, 'strftime'):
                selected_data_produkcji = plan_data_produkcji.strftime('%Y-%m-%d')
            else:
                selected_data_produkcji = str(plan_data_produkcji)
        elif _plan_data:
            if hasattr(_plan_data, 'strftime'):
                selected_data_produkcji = _plan_data.strftime('%Y-%m-%d')
            else:
                selected_data_produkcji = str(_plan_data)
        else:
            selected_data_produkcji = now_ts.strftime('%Y-%m-%d')
    
        if plan_sekcja not in ('Workowanie', 'Czyszczenie'):
            conn.close()
            try:
                current_app.logger.warning('REJECTED: Cannot add paleta to sekcja=%s', plan_sekcja)
            except Exception:
                pass
            return ('Błąd: Paletki można dodawać tylko do Workowania (bufora) lub Czyszczenia', 400)
    
        if waga_input <= 0:
            conn.close()
            return ('Błąd: Waga musi być większa od 0', 400)
    
        try:
            user_login = session.get('login', 'System')
            paleta_id = None
            nr_palety = None
    
            # If there are reserved labels for this plan, consume the oldest one first.
            cursor.execute(
                f"SELECT id, nr_palety FROM {table_pal} WHERE plan_id = %s AND COALESCE(status, '') = 'rezerwacja' ORDER BY id ASC LIMIT 1",
                (plan_id,),
            )
            reserved_row = cursor.fetchone()
    
            nr_palety_czyszczenie = None
            if plan_produkt == 'Czyszczenie':
                cursor.execute(f"SELECT skan_sscc FROM {table_plan} WHERE id IN (%s, %s) AND skan_sscc IS NOT NULL LIMIT 1", (plan_id, plan_zasyp_id or -1))
                sscc_row = cursor.fetchone()
                if sscc_row and sscc_row[0]:
                    nr_palety_czyszczenie = sscc_row[0]
    
            if reserved_row:
                paleta_id = reserved_row[0]
                if plan_produkt == 'Czyszczenie' and nr_palety_czyszczenie:
                    nr_palety = nr_palety_czyszczenie
                else:
                    nr_palety = reserved_row[1] or generate_pallet_id(linia)
                cursor.execute(
                    f"UPDATE {table_pal} SET waga = %s, tara = 25, waga_brutto = 0, data_dodania = %s, status = 'do_przyjecia', dodal_login = %s, nr_palety = %s, nr_plomby = COALESCE(%s, nr_plomby) WHERE id = %s",
                    (waga_input, now_ts, user_login, nr_palety, nr_plomby, paleta_id),
                )
            else:
                if plan_produkt == 'Czyszczenie' and nr_palety_czyszczenie:
                    nr_palety = nr_palety_czyszczenie
                else:
                    nr_palety = generate_pallet_id(linia)
                cursor.execute(
                    f"INSERT INTO {table_pal} (plan_id, waga, tara, waga_brutto, data_dodania, status, dodal_login, nr_palety, nr_plomby) VALUES (%s, %s, 25, 0, %s, 'do_przyjecia', %s, %s, %s)",
                    (plan_id, waga_input, now_ts, user_login, nr_palety, nr_plomby),
                )
                paleta_id = cursor.lastrowid if hasattr(cursor, 'lastrowid') else None
    
            # Compute sequential pallet number (nr_palety_lp) for this plan and store it if column exists
            try:
                if paleta_id:
                    cursor.execute(f"SELECT COUNT(*) FROM {table_pal} WHERE plan_id = %s AND id <= %s", (plan_id, paleta_id))
                    res_lp = cursor.fetchone()
                    nr_palety_lp = int(res_lp[0]) if res_lp else 1
                    # check if column exists
                    try:
                        cursor.execute(f"SHOW COLUMNS FROM {table_pal} LIKE 'nr_palety_lp'")
                        col = cursor.fetchone()
                        if col:
                            cursor.execute(f"UPDATE {table_pal} SET nr_palety_lp = %s WHERE id = %s", (nr_palety_lp, paleta_id))
                    except Exception:
                        # ignore if SHOW COLUMNS or UPDATE fails on older schemas
                        pass
            except Exception:
                pass
    
            cursor.execute(
                f"UPDATE {table_plan} SET tonaz_rzeczywisty = COALESCE(tonaz_rzeczywisty, 0) + %s WHERE id = %s",
                (waga_input, plan_id),
            )
    
            # Manual add should explicitly set production date on the order.
            cursor.execute(
                f"UPDATE {table_plan} SET data_produkcji = %s WHERE id = %s",
                (selected_data_produkcji, plan_id),
            )
    
            is_original_czyszczenie = False
            try:
                nazwa_do_historii = plan_produkt
                if plan_produkt == 'Czyszczenie':
                    is_original_czyszczenie = True
                    nazwa_do_historii = "Maka Mix do Lnu"
                    # Zaktualizuj nazwe produktu w zleceniu
                    cursor.execute(f"UPDATE {table_plan} SET produkt = %s WHERE id = %s", (nazwa_do_historii, plan_id))
                    plan_produkt = nazwa_do_historii
    
                cursor.execute(
                    "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, komentarz, user_login) VALUES (%s, %s, 'wyrob_gotowy', 'UTWORZENIE', %s, %s)",
                    (paleta_id, linia, f"Utworzono paletę: {nazwa_do_historii}, waga: {waga_input} kg", user_login)
                )
            except Exception as hist_err:
                current_app.logger.warning('Failed to log history for paleta %s: %s', paleta_id, hist_err)
    
            # --- AUTOMATYCZNY WYDRUK 2 ETYKIET ASYNCHRONICZNIE ---
            app_obj = current_app._get_current_object()
            
            user_printer_ip = str(request.form.get('printer_ip') or '').strip()
            user_printer_name = str(request.form.get('printer_name') or '').strip()
    
            def _async_print_label(paleta_id_local, nr_palety_local, app, usr_ip=None, usr_name=None):
                with app.app_context():
                        try:
                            from app.utils.pallet_label import prepare_pallet_label_data
                            conn2 = get_db_connection()
                            cur2 = conn2.cursor()
                            label_data_local = prepare_pallet_label_data(cur2, paleta_id_local, linia, source_table='workowanie')
                        except Exception as prep_err:
                            app.logger.error('Failed to prepare label data for paleta %s: %s', paleta_id_local, prep_err)
                            if 'conn2' in locals() and conn2:
                                try:
                                    conn2.close()
                                except Exception:
                                    pass
                            return
    
                        try:
                            if not label_data_local:
                                app.logger.error('No label data prepared for paleta %s', paleta_id_local)
                                if 'conn2' in locals() and conn2:
                                    try:
                                        conn2.close()
                                    except Exception:
                                        pass
                                return
        
                            from app.services.print_server import get_printer
                            printer_local = get_printer()
                            
                            if usr_ip or usr_name:
                                override_ip = usr_ip or None
                                override_name = usr_name or None
                            else:
                                override_name, override_ip = _select_preferred_printer(cur2)
                                
                            for copy_num in range(1, 3):
                                try:
                                    ok, print_msg = printer_local.print_finished_product_label(
                                        label_data_local,
                                        override_ip=override_ip,
                                        override_name=override_name,
                                    )
                                    app.logger.info(
                                        'Async print copy %s/2 for paleta %s: ok=%s printer=%s ip=%s msg=%s',
                                        copy_num, nr_palety_local, ok, override_name or getattr(printer_local, 'printer_name', None), override_ip or getattr(printer_local, 'printer_ip', None), print_msg
                                    )
                                except Exception as single_err:
                                    app.logger.error('Print attempt failed for paleta %s copy %s: %s', paleta_id_local, copy_num, single_err)
                                
                            if 'conn2' in locals() and conn2:
                                try:
                                    conn2.close()
                                except Exception:
                                    pass
        
                        except Exception as err:
                            app.logger.error('Unexpected error in async print thread for paleta %s: %s', paleta_id_local, err)
            # ---------------------------------------------
            if is_original_czyszczenie:
                # Rozliczenie straty worków dla czyszczenia
                try:
                    cursor.execute(f"SELECT opakowanie_id FROM {table_plan} WHERE id=%s", (plan_id,))
                    op_row = cursor.fetchone()
                    opak_id = op_row[0] if op_row else None
                    if opak_id:
                        bags_to_deduct = max(1, int(waga_input / 25))
                        cursor.execute(
                            "UPDATE magazyn_opakowania SET stan_magazynowy = GREATEST(0, stan_magazynowy - %s) WHERE id=%s",
                            (bags_to_deduct, opak_id)
                        )
                        current_app.logger.info("Deducted %s bags for Czyszczenie from folia %s", bags_to_deduct, opak_id)
                except Exception as op_err:
                    current_app.logger.error("Failed to deduct bags for Czyszczenie: %s", op_err)
    
            conn.commit()
    
            try:
                t = threading.Thread(target=_async_print_label, args=(paleta_id, nr_palety, app_obj, user_printer_ip, user_printer_name), daemon=True)
                t.start()
            except Exception as thr_err:
                current_app.logger.error('Failed to start async print thread for paleta %s: %s', nr_palety, thr_err)
    
            try:
                PlanningStatusService.ensure_status_after_tonaz_update(plan_id, linia=linia)
            except Exception as error:
                try:
                    current_app.logger.warning('Warning during status validation: %s', error)
                except Exception:
                    pass
    
            try:
                current_app.logger.info(
                    'Dodano paletę: plan_id=%s, waga=%s kg, data_produkcji=%s, użytkownik=%s',
                    plan_id,
                    waga_input,
                    selected_data_produkcji,
                    session.get('login'),
                )
                audit_log(
                    'Dodał paletę',
                    f'plan_id={plan_id}, produkt={plan_produkt}, waga={waga_input} kg, data_produkcji={selected_data_produkcji}'
                )
            except Exception:
                pass
    
            try:
                # _mark_dosypki_updated function removed - no longer needed
                # _mark_dosypki_updated(linia)
                pass
            except Exception:
                pass
    
        except Exception as error:
            try:
                current_app.logger.exception('Failed to add paleta: %s', error)
            except Exception:
                pass
            conn.rollback()
            conn.close()
            return ('Błąd: Nie udało się dodać paletki', 500)
    
        conn.close()
    
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'message': 'Paletka dodana', 'paleta_id': paleta_id}), 200
    
        return redirect(safe_return())