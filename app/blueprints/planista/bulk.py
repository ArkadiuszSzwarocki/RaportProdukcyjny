from datetime import date

from flask import current_app, redirect, render_template, request, session, url_for, jsonify

from app.db import get_db_connection, get_table_name
from app.decorators import roles_required
from app.services.notification_service import notify_workers_about_plan_change


def register_planista_bulk_routes(planista_bp):
    @planista_bp.route('/planista/add_czyszczenie', methods=['POST'])
    @roles_required('planista', 'zarzad', 'admin')
    def add_czyszczenie():
        """Dodaj wpis Czyszczenie do planu produkcji."""
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            json_body = request.get_json(silent=True) or {}
            data_planu = request.form.get('data_planu') or (json_body.get('data_planu') if json_body else None)
            tonaz = request.form.get('tonaz') or (json_body.get('tonaz') if json_body else None)
            kolejnosc = request.form.get('kolejnosc') or (json_body.get('kolejnosc') if json_body else None)
            try:
                tonaz_val = float(str(tonaz).replace(',', '.')) if tonaz is not None and tonaz != '' else 0
            except Exception:
                tonaz_val = 0
            try:
                kolejnosc_val = int(kolejnosc) if kolejnosc is not None and kolejnosc != '' else None
            except Exception:
                kolejnosc_val = None

            if not data_planu:
                return ('data_planu required', 400)

            linia = request.form.get('linia') or json_body.get('linia') or 'PSD'
            table_plan = get_table_name('plan_produkcji', linia)

            if kolejnosc_val is not None:
                cursor.execute(
                    f'UPDATE {table_plan} SET kolejnosc = kolejnosc + 1 WHERE data_planu = %s AND kolejnosc >= %s',
                    (data_planu, kolejnosc_val),
                )
            else:
                # Find the last order for the relevant section(s)
                if linia.upper() == 'PSD':
                    cursor.execute(
                        f"SELECT MAX(kolejnosc) FROM {table_plan} "
                        f"WHERE data_planu=%s AND (is_deleted=0 OR is_deleted IS NULL) "
                        f"AND LOWER(sekcja) IN ('zasyp', 'czyszczenie')",
                        (data_planu,)
                    )
                else:
                    cursor.execute(
                        f"SELECT MAX(kolejnosc) FROM {table_plan} "
                        f"WHERE data_planu=%s AND (is_deleted=0 OR is_deleted IS NULL)",
                        (data_planu,)
                    )
                
                max_res = cursor.fetchone()
                kolejnosc_val = (max_res[0] if max_res and max_res[0] is not None else 0) + 1

            insert_sql = (
                f'INSERT INTO {table_plan} (data_planu, sekcja, produkt, tonaz, status, kolejnosc, typ_zlecenia, zasyp_id) '
                'VALUES (%s, %s, %s, %s, %s, %s, %s, %s)'
            )
            
            # Create Zasyp row
            cursor.execute(
                insert_sql,
                (data_planu, 'Zasyp', 'Czyszczenie', tonaz_val, 'zaplanowane', kolejnosc_val, 'czyszczenie', None),
            )
            zasyp_id = cursor.lastrowid
            
            # Create Workowanie row
            cursor.execute(
                f"SELECT MAX(kolejnosc) FROM {table_plan} WHERE data_planu=%s AND (is_deleted=0 OR is_deleted IS NULL) AND LOWER(sekcja) IN ('workowanie', 'czyszczenie')",
                (data_planu,)
            )
            w_max = cursor.fetchone()
            w_kol = (w_max[0] if w_max and w_max[0] is not None else 0) + 1
            
            cursor.execute(
                insert_sql,
                (data_planu, 'Workowanie', 'Czyszczenie', tonaz_val, 'zaplanowane', w_kol, 'czyszczenie', zasyp_id),
            )
            
            # Renormalize to fix any numbering issues
            from app.services.plan_movement_service import PlanMovementService
            PlanMovementService.renormalize_sequences(cursor, table_plan, data_planu, None if linia.upper() == 'AGRO' else 'Zasyp')

            notify_workers_about_plan_change(
                plan_context={
                    'id': cursor.lastrowid if hasattr(cursor, 'lastrowid') else None,
                    'produkt': 'Czyszczenie',
                    'sekcja': 'Czyszczenie',
                    'data_planu': data_planu,
                },
                action_label='dodał',
                author_name=session.get('imie_nazwisko') or session.get('login'),
                conn=conn,
                cursor=cursor,
                created_by_user_id=session.get('user_id'),
            )
            conn.commit()
            return redirect(url_for('planista.panel_planisty', data=data_planu))
        except Exception as error:
            try:
                conn.rollback()
            except Exception:
                pass
            current_app.logger.exception('Error adding czyszczenie: %s', error)
            return (str(error), 500)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    @planista_bp.route('/planista/bulk', methods=['GET'])
    @roles_required('planista', 'admin', 'zarzad')
    def planista_bulk_page():
        """Render page for bulk adding plans."""
        wybrana_data = request.args.get('data', str(date.today()))
        domyslna_sekcja = request.args.get('sekcja', 'Zasyp')
        
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, nazwa FROM magazyn_opakowania ORDER BY nazwa")
            raw_opakowania = cursor.fetchall()
            seen_names = set()
            opakowania = []
            for o in raw_opakowania:
                name_clean = str(o.get('nazwa') or o.get('NAZWA') or '').strip()
                name_key = name_clean.lower()
                if name_key and name_key not in seen_names:
                    seen_names.add(name_key)
                    opakowania.append({'id': o['id'], 'nazwa': name_clean})
            cursor.execute("SELECT id, nazwa FROM slownik_etykiety_agro ORDER BY id")
            etykiety = cursor.fetchall()
        except Exception as e:
            current_app.logger.error(f"Error fetching bulk resources: {e}")
            opakowania = []
            etykiety = []
        finally:
            try: conn.close()
            except: pass
            
        return render_template('planista_bulk.html', wybrana_data=wybrana_data, domyslna_sekcja=domyslna_sekcja, opakowania=opakowania, etykiety=etykiety)

    @planista_bp.route('/planista/api/raport_dnia', methods=['GET'])
    @roles_required('planista', 'admin', 'lider', 'zarzad', 'masteradmin')
    def api_raport_dnia():
        data_planu = request.args.get('data')
        linia = request.args.get('linia', 'PSD')
        if not data_planu:
            return jsonify({'error': 'Brak daty'}), 400
            
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            table_plan = get_table_name('plan_produkcji', linia)
            table_palety = get_table_name('palety_workowanie', linia)
            
            sql = f"""
                SELECT 
                    p.id as plan_id,
                    p.produkt,
                    COUNT(pw.id) as ilosc_palet,
                    SUM(pw.waga) as laczna_waga
                FROM {table_palety} pw
                JOIN {table_plan} p ON pw.plan_id = p.id
                WHERE DATE(pw.data_dodania) = %s
                GROUP BY p.id, p.produkt
                ORDER BY p.id
            """
            cursor.execute(sql, (data_planu,))
            rows = cursor.fetchall()
            
            total_palet = sum(r['ilosc_palet'] for r in rows)
            total_waga = sum(float(r['laczna_waga'] or 0) for r in rows)
            
            return jsonify({
                'data': data_planu,
                'linia': linia,
                'total_palet': total_palet,
                'total_waga': total_waga,
                'items': rows
            })
        except Exception as e:
            current_app.logger.error(f"Raport dnia error: {e}")
            return jsonify({'error': str(e)}), 500
        finally:
            try: conn.close()
            except: pass