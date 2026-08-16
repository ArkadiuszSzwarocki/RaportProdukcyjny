    def usun_palete(id):
        """Delete paleta from buffer."""
        linia = str(resolve_request_linia()).upper()
        table_pal = get_table_name('palety_workowanie', linia)
        table_plan = get_table_name('plan_produkcji', linia)
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
    
            cursor.execute(f"SELECT plan_id FROM {table_pal} WHERE id=%s", (id,))
            res = cursor.fetchone()
    
            if not res:
                msg = f'Paleta ID={id} nie istnieje'
                current_app.logger.warning('[WAREHOUSE-DELETE] %s', msg)
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'success': False, 'message': msg}), 404
                flash(msg, 'warning')
                return redirect(safe_return())
    
            plan_id = res[0]
            
            # Get paleta details for history before deletion
            cursor.execute(f"SELECT waga, nr_palety, status FROM {table_pal} WHERE id=%s", (id,))
            paleta_data = cursor.fetchone()
            waga_val = paleta_data[0] if paleta_data else 0
            nr_palety_val = paleta_data[1] if paleta_data and len(paleta_data) > 1 else None
            status_val = paleta_data[2] if paleta_data and len(paleta_data) > 2 else 'unknown'
            
            cursor.execute(f"DELETE FROM {table_pal} WHERE id=%s", (id,))
            
            # Log to palety_historia - usunięcie palety
            try:
                cursor.execute(
                    "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, komentarz, user_login) VALUES (%s, %s, 'wyrob_gotowy', 'USUNIECIE', %s, %s)",
                    (id, linia, f"Usunięto paletę z workowania: {nr_palety_val or 'ID='+str(id)}, waga: {waga_val} kg, status: {status_val}", session.get('login'))
                )
            except Exception as hist_err:
                current_app.logger.warning('Failed to log history for deleted paleta %s: %s', id, hist_err)
            
            cursor.execute(
                f"UPDATE {table_plan} SET tonaz_rzeczywisty = (SELECT COALESCE(SUM(waga), 0) FROM {table_pal} WHERE plan_id = %s AND status NOT IN ('przyjeta', 'w_magazynie')) WHERE id = %s",
                (plan_id, plan_id),
            )
            conn.commit()
    
            current_app.logger.info('Usunięto paletę ID=%s, plan_id=%s, użytkownik=%s', id, plan_id, session.get('login'))
            audit_log('Usunął paletę', f'ID={id}, plan_id={plan_id}')
            msg = 'Paleta usunięta'
    
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': True, 'message': msg}), 200
    
            flash(msg, 'success')
        except Exception as error:
            current_app.logger.error('[WAREHOUSE-DELETE] Error deleting paleta %s: %s', id, error, exc_info=True)
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': f'Błąd: {str(error)}'}), 500
            flash(f'Błąd przy usuwaniu palety: {str(error)}', 'danger')
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
    
        return redirect(safe_return())