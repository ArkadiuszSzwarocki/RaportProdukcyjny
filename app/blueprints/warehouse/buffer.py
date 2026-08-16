from flask import current_app, jsonify, request

from app.db import get_db_connection
from app.decorators import login_required, roles_required


def register_warehouse_buffer_routes(warehouse_bp):
    @warehouse_bp.route('/api/bufor', methods=['GET'])
    @login_required
    def api_bufor():
        """Public API returning bufor entries as JSON."""
        from datetime import date as _date
        from datetime import datetime as _datetime

        from app.db import refresh_bufor_queue

        out = []
        qdate = request.args.get('data') or str(_date.today())
        try:
            try:
                dt = _datetime.strptime(qdate, '%Y-%m-%d')
                qdate = dt.date().isoformat()
            except Exception:
                try:
                    dt = _datetime.strptime(qdate, '%d.%m.%Y')
                    qdate = dt.date().isoformat()
                except Exception:
                    qdate = str(_date.today())
        except Exception:
            qdate = str(_date.today())

        conn = None
        try:
            refresh_bufor_queue()

            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, zasyp_id, data_planu, produkt, nazwa_zlecenia, typ_produkcji,
                       tonaz_rzeczywisty, spakowano, kolejka
                FROM bufor
                WHERE data_planu = %s AND status = 'aktywny'
                ORDER BY kolejka ASC
                """,
                (qdate,),
            )
            rows = cur.fetchall()

            for row in rows:
                _buf_id, z_id, z_data, z_produkt, z_nazwa, z_typ, z_tonaz, z_spakowano, z_kolejka = row
                pozostalo_w_silosie = max(z_tonaz - z_spakowano, 0)
                needs_reconciliation = round((z_spakowano or 0) - (z_tonaz or 0), 1) != 0
                show_in_bufor = (pozostalo_w_silosie > 0) or (z_spakowano and z_spakowano > 0)

                if show_in_bufor:
                    out.append(
                        {
                            'id': z_id,
                            'data': str(z_data),
                            'produkt': z_produkt,
                            'nazwa': z_nazwa,
                            'w_silosie': round(max(pozostalo_w_silosie, 0), 1),
                            'typ_produkcji': z_typ,
                            'zasyp_total': z_tonaz,
                            'spakowano_total': z_spakowano,
                            'kolejka': z_kolejka,
                            'needs_reconciliation': needs_reconciliation,
                            'raw_pozostalo': round(pozostalo_w_silosie, 1),
                        }
                    )

        except Exception as error:
            try:
                import traceback

                print(f'[ERROR] api_bufor: {error}')
                traceback.print_exc()
            except Exception:
                pass
            return jsonify({'bufor': [], 'error': True, 'message': str(error)}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

        return jsonify({'bufor': out})

    @warehouse_bp.route('/bufor/create_zlecenie', methods=['POST'])
    @login_required
    @roles_required('planista', 'admin', 'zarzad', 'lider')
    def warehouse_bufor_create_zlecenie():
        """Create new Workowanie zlecenie based on buffer remainder."""
        try:
            data = request.get_json(force=True) if request.is_json else request.form.to_dict()
        except Exception:
            data = request.form.to_dict()

        zasyp_id = data.get('zasyp_id')
        use_buffer = data.get('use_buffer_data') == 'true' or data.get('use_buffer_data') is True
        override_work_date = data.get('workowanie_date')

        if not zasyp_id:
            return jsonify({'success': False, 'message': 'Brak zasyp_id'}), 400

        try:
            zasyp_id = int(zasyp_id)
        except Exception:
            return jsonify({'success': False, 'message': 'Nieprawidłowy zasyp_id'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            if use_buffer:
                cursor.execute(
                    """
                    SELECT
                        zasyp_id,
                        data_planu,
                        produkt,
                        COALESCE(tonaz_rzeczywisty, 0) as tonaz_rzeczywisty,
                        typ_produkcji,
                        COALESCE(nazwa_zlecenia, '') as nazwa_zlecenia,
                        COALESCE(SUM(spakowano), 0) as spakowano
                    FROM bufor
                    WHERE zasyp_id = %s
                    GROUP BY zasyp_id, data_planu, produkt, typ_produkcji, nazwa_zlecenia
                    LIMIT 1
                    """,
                    (zasyp_id,),
                )
                zasyp_data = cursor.fetchone()
                if not zasyp_data:
                    conn.close()
                    return jsonify({'success': False, 'message': 'Nie znaleziono wpisu w buforze dla tego Zasypu'}), 404

                z_id, z_data, z_produkt, z_tonaz_rz, z_typ, z_nazwa, spakowano = zasyp_data
                roznicza = (z_tonaz_rz or 0) - spakowano
            else:
                cursor.execute(
                    """
                    SELECT id, data_planu, produkt, tonaz_rzeczywisty, typ_produkcji, nazwa_zlecenia
                    FROM plan_produkcji
                    WHERE id = %s AND sekcja = 'Zasyp'
                    """,
                    (zasyp_id,),
                )
                zasyp = cursor.fetchone()
                if not zasyp:
                    conn.close()
                    return jsonify({'success': False, 'message': 'Nie znaleziono Zasypu'}), 404

                z_id, z_data, z_produkt, z_tonaz_rz, z_typ, z_nazwa = zasyp
                cursor.execute(
                    """
                    SELECT SUM(spakowano) FROM bufor
                    WHERE zasyp_id = %s AND data_planu = %s
                    """,
                    (zasyp_id, z_data),
                )
                result = cursor.fetchone()
                spakowano = result[0] or 0 if result else 0
                roznicza = (z_tonaz_rz or 0) - spakowano

            work_date = override_work_date if override_work_date else z_data

            if roznicza <= 0:
                conn.close()
                return jsonify({'success': False, 'message': 'Nie ma pozostałego towaru do spakowania (różnica <= 0)'}), 400

            cursor.execute(
                """
                SELECT MAX(kolejnosc) FROM plan_produkcji
                WHERE data_planu = %s AND sekcja IN ('Workowanie', 'Czyszczenie')
                """,
                (work_date,),
            )
            result = cursor.fetchone()
            next_kolejnosc = (result[0] or 0) + 1 if result else 1

            insert_sql = """
                INSERT INTO plan_produkcji
                (data_planu, sekcja, produkt, tonaz, status, kolejnosc, typ_produkcji, nazwa_zlecenia, zasyp_id)
                SELECT %s, 'Workowanie', %s, %s, 'zaplanowane', %s, %s, %s, %s
                FROM DUAL
                WHERE NOT EXISTS (SELECT 1 FROM plan_produkcji WHERE zasyp_id = %s AND sekcja IN ('Workowanie', 'Czyszczenie'))
            """
            params = (
                work_date,
                z_produkt,
                round(roznicza, 1),
                next_kolejnosc,
                z_typ or 'worki_zgrzewane_25',
                (z_nazwa or '') + '_BUF',
                z_id,
                z_id,
            )

            import mysql.connector

            try:
                cursor.execute(insert_sql, params)
            except mysql.connector.IntegrityError:
                try:
                    conn.rollback()
                except Exception:
                    pass
                cursor.execute("SELECT id FROM plan_produkcji WHERE zasyp_id=%s AND sekcja='Workowanie' LIMIT 1", (z_id,))
                existing = cursor.fetchone()
                existing_id = existing[0] if existing else None
                conn.close()
                return jsonify({'success': True, 'message': 'Zlecenie Workowanie już istnieje', 'existing_id': existing_id}), 200

            if cursor.rowcount:
                conn.commit()
                new_id = cursor.lastrowid
                conn.close()
                return jsonify(
                    {
                        'success': True,
                        'message': f'Utworzono zlecenie Workowanie z planem {round(roznicza, 1)} kg',
                        'new_id': new_id,
                        'plan_kg': round(roznicza, 1),
                    }
                ), 201

            cursor.execute("SELECT id FROM plan_produkcji WHERE zasyp_id=%s AND sekcja='Workowanie' LIMIT 1", (z_id,))
            existing = cursor.fetchone()
            existing_id = existing[0] if existing else None
            conn.close()
            return jsonify({'success': True, 'message': 'Zlecenie Workowanie już istnieje', 'existing_id': existing_id}), 200
        except Exception as error:
            try:
                conn.rollback()
            except Exception:
                pass
            current_app.logger.exception('Error in warehouse_bufor_create_zlecenie')
            return jsonify({'success': False, 'message': f'Błąd: {str(error)}'}), 500
        finally:
            try:
                conn.close()
            except Exception:
                pass

    @warehouse_bp.route('/api/start_from_queue/<int:kolejka>', methods=['POST'])
    @login_required
    def start_from_queue(kolejka):
        """Startuje zlecenie z bufora po numerze kolejki."""
        from datetime import datetime as _datetime

        conn = get_db_connection()
        cur = conn.cursor()

        try:
            cur.execute(
                """
                SELECT b.zasyp_id, b.data_planu, b.produkt, b.kolejka,
                       w.id as workowanie_id
                FROM bufor b
                LEFT JOIN plan_produkcji w ON w.zasyp_id = b.zasyp_id
                    AND w.sekcja IN ('Workowanie', 'Czyszczenie')
                WHERE b.kolejka = %s AND b.status = 'aktywny'
                LIMIT 1
                """,
                (kolejka,),
            )
            row = cur.fetchone()
            if not row:
                return jsonify({'success': False, 'message': f'Nie znaleziono wpisu w buforze z kolejką {kolejka}'}), 404

            _zasyp_id, data_planu, produkt, buf_kolejka, workowanie_id = row
            if not workowanie_id:
                return jsonify({'success': False, 'message': f'Brak odpowiadającego Workowania dla {produkt} na dzień {data_planu}'}), 400

            cur.execute(
                """
                UPDATE plan_produkcji
                SET status = 'w toku', real_start = %s
                WHERE id = %s AND sekcja IN ('Workowanie', 'Czyszczenie')
                """,
                (_datetime.now(), workowanie_id),
            )
            cur.execute(
                """
                UPDATE bufor
                SET status = 'startowany'
                WHERE kolejka = %s AND status = 'aktywny'
                """,
                (kolejka,),
            )
            conn.commit()

            return jsonify(
                {
                    'success': True,
                    'message': f'Uruchomiono zlecenie {produkt} (kolejka {buf_kolejka})',
                    'workowanie_id': workowanie_id,
                    'produkt': produkt,
                    'kolejka': buf_kolejka,
                }
            ), 200
        except Exception as error:
            conn.rollback()
            import traceback

            traceback.print_exc()
            return jsonify({'success': False, 'message': str(error)}), 500
        finally:
            if cur:
                try:
                    cur.close()
                except Exception:
                    pass
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass