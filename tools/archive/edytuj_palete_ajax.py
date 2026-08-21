    def edytuj_palete_ajax():
        """AJAX: Edytuj wagę palety w magazyn_palety (tylko potwierdzone w magazynie)."""
        data = request.get_json(force=True) or {}
        linia = str(resolve_payload_linia(data)).upper()
        paleta_id = data.get('id')
        nowa_waga = data.get('waga')
        try:
            paleta_id = int(paleta_id)
            nowa_waga = int(float(str(nowa_waga).replace(',', '.')))
        except Exception:
            return jsonify({'success': False, 'message': 'Nieprawidłowe dane'}), 400
    
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
    
            result = update_paleta_magazyn(cursor, paleta_id, nowa_waga, linia=linia)
            if not result.get('found'):
                msg = f'Paleta ID={paleta_id} nie istnieje w magazynie lub nie została potwierdzona'
                current_app.logger.warning('[WAREHOUSE-AJAX-EDIT] %s', msg)
                return jsonify({'success': False, 'message': msg}), 404
    
            conn.commit()
            plan_id = result.get('plan_id')
            current_app.logger.info('Edytowano paletę (AJAX) ID=%s, waga=%s kg, użytkownik=%s', paleta_id, nowa_waga, session.get('login'))
            audit_log('Edytował paletę (magazyn)', f'ID={paleta_id}, waga={nowa_waga} kg, plan_id={plan_id}')
            return jsonify({'success': True, 'message': f'Waga zaktualizowana ({nowa_waga}kg)'})
        except Exception as error:
            current_app.logger.exception('[WAREHOUSE-AJAX-EDIT] Failed to edit paleta %s: %s', paleta_id, error)
            return jsonify({'success': False, 'message': f'Błąd: {str(error)}'}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass