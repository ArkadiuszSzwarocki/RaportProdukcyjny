    def usun_palete_ajax():
        """AJAX: Usuń paletę tylko z magazyn_palety (potwierdzone w magazynie)."""
        data = request.get_json(force=True) or {}
        linia = str(resolve_payload_linia(data)).upper()
        paleta_id = data.get('id')
        try:
            paleta_id = int(paleta_id)
        except Exception:
            return jsonify({'success': False, 'message': 'Nieprawidłowe id'}), 400
    
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
    
            table_mag = get_table_name('magazyn_palety', linia)
            table_plan = get_table_name('plan_produkcji', linia)
            table_pal = get_table_name('palety_workowanie', linia)
    
            cursor.execute(f"SELECT plan_id, paleta_workowanie_id FROM {table_mag} WHERE id=%s", (paleta_id,))
            row = cursor.fetchone()
    
            if not row:
                msg = f'Paleta ID={paleta_id} nie istnieje w magazynie lub nie została potwierdzona'
                current_app.logger.warning('[WAREHOUSE-AJAX-DELETE] %s', msg)
                return jsonify({'success': False, 'message': msg}), 404
    
            plan_id = row[0]
            paleta_workowanie_id = row[1] if len(row) > 1 else None
            
            # Get paleta details for history before deletion
            cursor.execute(f"SELECT nr_palety, produkt, waga_netto, lokalizacja FROM {table_mag} WHERE id=%s", (paleta_id,))
            mag_data = cursor.fetchone()
            nr_pal = mag_data[0] if mag_data else None
            produkt = mag_data[1] if mag_data and len(mag_data) > 1 else ''
            waga = mag_data[2] if mag_data and len(mag_data) > 2 else 0
            lokalizacja = mag_data[3] if mag_data and len(mag_data) > 3 else ''
            
            cursor.execute(f"DELETE FROM {table_mag} WHERE id=%s", (paleta_id,))
            
            # Log to palety_historia - usunięcie z magazynu
            try:
                cursor.execute(
                    "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, lokalizacja_zrodlowa, komentarz, user_login) VALUES (%s, %s, 'wyrob_gotowy', 'USUNIECIE_Z_MAGAZYNU', %s, %s, %s)",
                    (paleta_id, linia, lokalizacja, f"Usunięto z magazynu: {nr_pal or 'ID='+str(paleta_id)}, {produkt}, {waga} kg", session.get('login'))
                )
            except Exception as hist_err:
                current_app.logger.warning('Failed to log history for deleted paleta from magazyn %s: %s', paleta_id, hist_err)
            try:
                if paleta_workowanie_id:
                    cursor.execute(
                        f"UPDATE {table_pal} SET status=%s, data_potwierdzenia=NULL, czas_potwierdzenia_s=NULL, czas_rzeczywistego_potwierdzenia=NULL, waga_potwierdzona=NULL WHERE id=%s",
                        ('zamknieta', paleta_workowanie_id),
                    )
            except Exception:
                try:
                    current_app.logger.exception('Failed to update palety_workowanie after magazyn delete for paleta_workowanie_id=%s', paleta_workowanie_id)
                except Exception:
                    pass
            cursor.execute(
                f"UPDATE {table_plan} SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga_netto), 0) FROM {table_mag} WHERE plan_id = %s) WHERE id = %s",
                (plan_id, plan_id),
            )
    
            conn.commit()
            current_app.logger.info('Usunięto paletę z magazynu (AJAX) ID=%s, plan_id=%s, użytkownik=%s', paleta_id, plan_id, session.get('login'))
            audit_log('Usunął paletę z magazynu', f'ID={paleta_id}, plan_id={plan_id}')
            return jsonify({'success': True, 'message': 'Paleta usunięta z magazynu'})
        except Exception as error:
            current_app.logger.exception('[WAREHOUSE-AJAX-DELETE] Failed to delete paleta %s: %s', paleta_id, error)
            return jsonify({'success': False, 'message': f'Błąd: {str(error)}'}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass