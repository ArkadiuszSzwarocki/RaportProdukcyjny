    def potwierdz_palete(paleta_id):
        """Confirm paleta acceptance with warehouse manager/lider."""
        linia = resolve_request_linia()
        table_plan = get_table_name('plan_produkcji', linia)
        table_pal = get_table_name('palety_workowanie', linia)
        table_mag = get_table_name('magazyn_palety', linia)
    
        role = str(session.get('rola', '')).strip()
        if role not in ['magazynier', 'lider', 'admin', 'masteradmin']:
            current_app.logger.warning(
                '[WAREHOUSE-AUTH] User %s with role=%s tried to confirm paleta %s - insufficient permissions',
                session.get('login'),
                role,
                paleta_id,
            )
            return jsonify({'success': False, 'message': 'Brak uprawnień do zatwierdzania palet'}), 403
    
        provided_netto = None
        provided_brutto = None
        deklarowana_waga = None
        weight_difference = None
        has_weight_difference = False
        check_only_request = False
        force_accept_request = False
        status_updated = False
        error_message = None
    
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
    
            tara = 25
            try:
                cursor.execute(f"SELECT COALESCE(tara,25) FROM {table_pal} WHERE id=%s", (paleta_id,))
                trow = cursor.fetchone()
                tara = int(trow[0]) if trow and trow[0] is not None else 25
            except Exception as error:
                current_app.logger.warning('Failed to fetch tara for paleta %s: %s', paleta_id, error)
    
            try:
                if request.form.get('waga_palety'):
                    try:
                        provided_netto = int(float(require_field(request.form, 'waga_palety').replace(',', '.')))
                    except (ValueError, Exception):
                        provided_netto = None
                elif request.form.get('waga_brutto'):
                    try:
                        provided_brutto = int(float(require_field(request.form, 'waga_brutto').replace(',', '.')))
                    except (ValueError, Exception):
                        provided_brutto = None
                    if provided_brutto is not None:
                        netto_val = provided_brutto - int(tara)
                        provided_netto = netto_val if netto_val >= 0 else 0
            except Exception as error:
                current_app.logger.error('Failed to parse provided weight for paleta %s: %s', paleta_id, error, exc_info=True)
    
            check_only_request = str(request.form.get('check_only', '')).strip().lower() in ('1', 'true', 'yes')
            force_accept_request = str(request.form.get('force_accept', '')).strip().lower() in ('1', 'true', 'yes')
    
            try:
                cursor.execute(f"SELECT waga FROM {table_pal} WHERE id=%s", (paleta_id,))
                drow = cursor.fetchone()
                if drow and drow[0] is not None:
                    deklarowana_waga = int(drow[0])
            except Exception as error:
                current_app.logger.debug('Failed to fetch declared weight for paleta %s: %s', paleta_id, error)
    
            if deklarowana_waga is not None and provided_netto is not None:
                try:
                    weight_difference = round(abs(provided_netto - deklarowana_waga), 1)
                    has_weight_difference = bool(weight_difference > 1)
                except Exception:
                    weight_difference = None
                    has_weight_difference = False
    
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' and check_only_request:
                return jsonify(
                    {
                        'success': True,
                        'check_only': True,
                        'has_difference': has_weight_difference,
                        'difference': weight_difference,
                        'requires_confirmation': has_weight_difference,
                    }
                ), 200
    
            try:
                if provided_netto is not None:
                    cursor.execute(f"UPDATE {table_pal} SET waga_potwierdzona=%s WHERE id=%s", (provided_netto, paleta_id))
                if provided_brutto is not None:
                    cursor.execute(f"UPDATE {table_pal} SET waga_brutto=%s WHERE id=%s", (provided_brutto, paleta_id))
                if provided_netto is not None or provided_brutto is not None:
                    conn.commit()
            except Exception as error:
                current_app.logger.error('Failed to persist weights for paleta %s: %s', paleta_id, error, exc_info=True)
                try:
                    conn.rollback()
                except Exception:
                    pass
    
            prev_status = ''
            plan_id = None
            stored_netto = None
            try:
                cursor.execute(
                    f"SELECT plan_id, COALESCE(status,''), COALESCE(waga_potwierdzona, 0), nr_palety, nr_plomby FROM {table_pal} WHERE id=%s",
                    (paleta_id,),
                )
                prev_row = cursor.fetchone()
                if prev_row:
                    plan_id = prev_row[0]
                    prev_status = prev_row[1]
                    stored_netto = int(prev_row[2] or 0)
                    nr_palety = prev_row[3]
                    nr_plomby = prev_row[4] if len(prev_row) > 4 else None
            except Exception as error:
                current_app.logger.warning('Failed to fetch plan_id/status/weights for paleta %s: %s', paleta_id, error)
    
            user_login = session.get('login', 'System')
            try:
                if linia == 'AGRO':
                    cursor.execute(
                        f"UPDATE {table_pal} SET status='przyjeta', "
                        "data_potwierdzenia = DATE_ADD(data_dodania, INTERVAL TIMESTAMPDIFF(SECOND, data_dodania, NOW()) SECOND), "
                        "czas_potwierdzenia_s = TIMESTAMPDIFF(SECOND, data_dodania, NOW()), "
                        "czas_rzeczywistego_potwierdzenia = SEC_TO_TIME(TIMESTAMPDIFF(SECOND, data_dodania, NOW())) "
                        f"WHERE id=%s",
                        (paleta_id,),
                    )
                else:
                    cursor.execute(f"UPDATE {table_pal} SET status='przyjeta' WHERE id=%s", (paleta_id,))
                conn.commit()
                status_updated = True
            except Exception as error:
                current_app.logger.warning('Complex update failed for paleta %s: %s, retrying simple update', paleta_id, error)
                try:
                    cursor.execute(f"UPDATE {table_pal} SET status='przyjeta' WHERE id=%s", (paleta_id,))
                    conn.commit()
                    status_updated = True
                except Exception as second_error:
                    current_app.logger.error('Simple status update also failed for paleta %s: %s', paleta_id, second_error, exc_info=True)
                    error_message = str(second_error)
                    try:
                        conn.rollback()
                    except Exception:
                        pass
    
            if not status_updated:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'success': False, 'message': f'Nie udało się zatwierdzić palety: {error_message or "błąd zapisu statusu"}'}), 500
                return redirect(safe_return())
    
            if plan_id:
                netto_val = provided_netto if provided_netto is not None else stored_netto
    
                try:
                    cursor.execute(f"SELECT data_planu, produkt, data_produkcji FROM {table_plan} WHERE id=%s", (plan_id,))
                    row = cursor.fetchone()
                    if row and prev_status not in ('przyjeta', 'w_magazynie'):
                        cursor.execute(f"SELECT id FROM {table_plan} WHERE data_planu=%s AND produkt=%s AND sekcja='Magazyn' LIMIT 1", (row[0], row[1]))
                        mp = cursor.fetchone()
                        mp_id = mp[0] if mp else None
    
                        nr_partii = request.form.get('nr_partii')
                        
                        # Check request.form, then fallback to plan's data_produkcji, then fallback to plan's date, then fallback to current date
                        data_produkcji = request.form.get('data_produkcji')
                        if not data_produkcji or not data_produkcji.strip():
                            plan_prod_date = row[2]
                            if plan_prod_date:
                                if hasattr(plan_prod_date, 'strftime'):
                                    data_produkcji = plan_prod_date.strftime('%Y-%m-%d')
                                else:
                                    data_produkcji = str(plan_prod_date)
                            else:
                                plan_date = row[0]
                                if plan_date:
                                    if hasattr(plan_date, 'strftime'):
                                        data_produkcji = plan_date.strftime('%Y-%m-%d')
                                    else:
                                        data_produkcji = str(plan_date)
                                else:
                                    from datetime import datetime
                                    data_produkcji = datetime.now().strftime('%Y-%m-%d')
    
                        data_przydatnosci = request.form.get('data_przydatnosci')
                        lokalizacja = request.form.get('lokalizacja')
    
                        if row[1] == 'Czyszczenie':
                            import uuid, json
                            from datetime import datetime
                            dostawa_id = str(uuid.uuid4())
                            items = [{
                                "id": str(uuid.uuid4()),
                                "type": "surowiec",
                                "name": row[1],
                                "amount": netto_val,
                                "unit": "kg",
                                "confirmed": False
                            }]
                            try:
                                cursor.execute("""
                                    INSERT INTO magazyn_dostawy
                                        (id, order_ref, supplier, delivery_date, status, items,
                                         created_by, created_at, requires_lab, linia)
                                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                                """, (dostawa_id, f"Czyszczenie Zlecenie #{plan_id}", "PRODUKCJA", data_produkcji, "OCZEKUJE",
                                      json.dumps(items), session.get('login'), datetime.now(), 0, linia))
                                mag_id = None
                                
                                # Update status to przeklasyfikowana
                                cursor.execute(f"UPDATE {table_pal} SET status='przeklasyfikowana' WHERE id=%s", (paleta_id,))
                                
                                cursor.execute(
                                    "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, 'surowiec', 'PRZEKLASYFIKOWANIE', %s, %s, %s)",
                                    (paleta_id, linia, lokalizacja, f"Przeklasyfikowano na surowiec: {row[1]}, Oczekuje w dostawach", session.get('login'))
                                )
                            except Exception as e:
                                current_app.logger.error('Database error for Czyszczenie dostawa: %s', e)
                        else:
                            try:
                                cursor.execute(
                                    f"INSERT IGNORE INTO {table_mag} (paleta_workowanie_id, plan_id, data_planu, produkt, waga_netto, waga_brutto, tara, user_login, nr_partii, data_produkcji, data_przydatnosci, lokalizacja, nr_palety, nr_plomby) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                                    (paleta_id, mp_id, row[0], row[1], netto_val, provided_brutto if provided_brutto is not None else 0, tara, session.get('login'), nr_partii, data_produkcji, data_przydatnosci, lokalizacja, nr_palety, nr_plomby),
                                )
                                mag_id = cursor.lastrowid
                                
                                # Log to palety_historia
                                cursor.execute(
                                    "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, 'wyrob_gotowy', 'PRZYJECIE', %s, %s, %s)",
                                    (paleta_id, linia, lokalizacja, f"Przyjęcie palety: {row[1]}, partia: {nr_partii}", session.get('login'))
                                )
                            except mysql.connector.Error as e:
                                current_app.logger.debug('Database error for paleta %s in %s: %s', paleta_id, table_mag, e)
    
                        if cursor.rowcount > 0:
                            current_app.logger.info(
                                'Potwierdzono paletę ID=%s: waga_netto=%s kg, produkt=%s, użytkownik=%s, lokalizacja=%s',
                                paleta_id,
                                netto_val,
                                row[1] if len(row) > 1 else '—',
                                session.get('login'),
                                lokalizacja
                            )
                            audit_log('Potwierdził paletę', f'ID={paleta_id}, produkt={row[1] if len(row) > 1 else "—"}, waga_netto={netto_val} kg, lokalizacja={lokalizacja}')
                        else:
                            current_app.logger.debug('Paleta ID=%s już jest w magazynie (INSERT IGNORE pominął duplikat), waga=%s kg', paleta_id, netto_val)
    
                        cursor.execute(
                            f"UPDATE {table_plan} SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga_netto),0) FROM {table_mag} WHERE plan_id = {table_plan}.id) WHERE data_planu=%s AND produkt=%s AND sekcja='Magazyn'",
                            (row[0], row[1]),
                        )
                        conn.commit()
                        
                        # --- Automatyczny wydruk raportu na drukarce biurowej, jeśli to ostatnia paleta w zakończonym zleceniu ---
                        printed_msg = None
                        try:
                            cursor.execute(f"SELECT status FROM {table_plan} WHERE id=%s", (plan_id,))
                            plan_status_row = cursor.fetchone()
                            if plan_status_row and str(plan_status_row[0]).strip().lower() in ('zakończone', 'zakończony', 'zakonczone'):
                                cursor.execute(f"SELECT COUNT(id) FROM {table_pal} WHERE plan_id=%s", (plan_id,))
                                total_pallets = cursor.fetchone()[0] or 0
                                
                                cursor.execute(f"SELECT COUNT(id) FROM {table_pal} WHERE plan_id=%s AND status IN ('przyjeta', 'w_magazynie')", (plan_id,))
                                accepted_pallets = cursor.fetchone()[0] or 0
                                
                                if total_pallets > 0 and total_pallets == accepted_pallets:
                                    current_app.logger.info("Magazynier przyjął ostatnią paletę zlecenia %s. Wyzwalanie wydruku biurowego.", plan_id)
                                    from app.services.office_print_service import trigger_office_print
                                    trigger_office_print(plan_id)
                                    printed_msg = "Zlecenie zamknięte - przyjęto ostatnią paletę. Raport został wysłany na drukarkę."
                                    flash(printed_msg, 'success')
                        except Exception as print_err:
                            current_app.logger.error('Failed to check/trigger auto-print for plan %s: %s', plan_id, print_err)
                        # ---------------------------------------------------------------------------------------------------------
                except Exception as error:
                    current_app.logger.error('Failed to update Magazyn aggregates for paleta %s: %s', paleta_id, error, exc_info=True)
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                        
            try:
                # _mark_dosypki_updated function removed - no longer needed
                # _mark_dosypki_updated(linia)
                pass
            except Exception:
                pass
    
        except Exception as error:
            current_app.logger.error('Failed to potwierdz palete %s: %s', paleta_id, error, exc_info=True)
        finally:
            try:
                conn.close()
            except Exception:
                pass
    
        try:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                response_data = {'success': True, 'paleta_id': paleta_id}
                if 'printed_msg' in locals() and printed_msg:
                    response_data['message'] = printed_msg
                if has_weight_difference and not force_accept_request:
                    response_data['has_difference'] = True
                    response_data['difference'] = weight_difference
                return jsonify(response_data), 200
        except Exception:
            pass
        return redirect(safe_return())