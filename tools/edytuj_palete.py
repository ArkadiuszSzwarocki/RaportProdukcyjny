    def edytuj_palete(paleta_id):
        """Edit paleta weight (netto)."""
        linia = str(resolve_request_linia()).upper()
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
    
            try:
                waga = int(float(request.form.get('waga_palety', '0').replace(',', '.')))
            except Exception:
                waga = 0
    
            result = update_paleta_workowanie(cursor, paleta_id, waga, linia=linia)
            if not result.get('found'):
                msg = f'Paleta ID={paleta_id} nie istnieje'
                current_app.logger.warning('[WAREHOUSE-EDIT] %s', msg)
                flash(msg, 'warning')
                return redirect(safe_return())
            
            # Log to palety_historia - edycja wagi
            try:
                old_waga = result.get('old_waga', 0)
                cursor.execute(
                    "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, komentarz, user_login) VALUES (%s, %s, 'wyrob_gotowy', 'EDYCJA_WAGI', %s, %s)",
                    (paleta_id, linia, f"Zmieniono wagę: {old_waga} kg → {waga} kg", session.get('login'))
                )
            except Exception as hist_err:
                current_app.logger.warning('Failed to log history for edited paleta %s: %s', paleta_id, hist_err)
    
            conn.commit()
            current_app.logger.info('Edytowano paletę ID=%s, waga=%s kg, użytkownik=%s', paleta_id, waga, session.get('login'))
            audit_log('Edytował paletę', f'ID={paleta_id}, waga={waga} kg')
            flash(f'Paleta zaktualizowana (waga={waga}kg)', 'success')
        except Exception as error:
            current_app.logger.error('[WAREHOUSE-EDIT] Failed to edit paleta %s: %s', paleta_id, error, exc_info=True)
            flash(f'Błąd przy edytowaniu palety: {str(error)}', 'danger')
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
    
        return redirect(safe_return())