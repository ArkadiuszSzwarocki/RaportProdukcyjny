from app.db import get_db_connection, get_table_name
import json
from datetime import datetime
import uuid
import re
from app.utils.pallet_id import generate_pallet_id
from app.utils.location_validator import validate_warehouse_location, is_production_tank_code

class DeliveryQueries:

    def get_dostawy(linia='PSD'):
            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                if str(linia).upper() == 'ALL':
                    cursor.execute("SELECT * FROM magazyn_dostawy ORDER BY created_at DESC")
                else:
                    cursor.execute(
                        "SELECT * FROM magazyn_dostawy WHERE UPPER(linia) = %s ORDER BY created_at DESC",
                        (str(linia).upper(),)
                    )
                dostawy = cursor.fetchall()
                for d in dostawy:
                    if d.get('items'):
                        try:
                            d['items_parsed'] = json.loads(d['items'])
                        except Exception:
                            d['items_parsed'] = []
                return dostawy
            finally:
                conn.close()

    def get_oczekujace(linia='PSD'):
            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                # 1. Pending Raw Materials / Transfers
                if str(linia).upper() == 'ALL':
                    cursor.execute(
                        "SELECT * FROM magazyn_dostawy WHERE status = 'OCZEKUJE' ORDER BY created_at DESC"
                    )
                else:
                    cursor.execute(
                        "SELECT * FROM magazyn_dostawy WHERE status = 'OCZEKUJE' AND UPPER(linia) = %s ORDER BY created_at DESC",
                        (str(linia).upper(),)
                    )
                dostawy = cursor.fetchall()
                for d in dostawy:
                    if d.get('items'):
                        try: d['items_parsed'] = json.loads(d['items'])
                        except Exception: d['items_parsed'] = []
                
                # 2. Pending Production Pallets (WG)
                wg = DeliveryQueries.get_pending_production_pallets(linia)
                
                return {
                    "dostawy": dostawy,
                    "wg": wg
                }
            finally:
                conn.close()

    def get_pending_production_pallets(linia='PSD'):
            """Fetches pallets with status 'do_przyjecia' from production tables."""
            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                normalized_line = str(linia or 'PSD').upper()
                is_psd = normalized_line == 'PSD'
                table_prod = 'palety_workowanie' if is_psd else 'palety_agro'
                table_plan = 'plan_produkcji' if is_psd else 'plan_produkcji_agro'
                table_wh = 'magazyn_palety' if is_psd else 'magazyn_palety_agro'
                plan_product_col = 'plan.produkt'
                
                # Check if table exists (safety)
                cursor.execute("SHOW TABLES LIKE %s", (table_prod,))
                if not cursor.fetchone():
                    return []

                cursor.execute("SHOW TABLES LIKE %s", (table_wh,))
                has_wh_table = bool(cursor.fetchone())

                suggested_location_sql = "''"
                if has_wh_table:
                    suggested_location_sql = (
                        f"COALESCE((SELECT w.lokalizacja FROM {table_wh} w "
                        f"WHERE w.produkt = {plan_product_col} "
                        "AND w.lokalizacja IS NOT NULL AND w.lokalizacja <> '' "
                        "ORDER BY COALESCE(w.data_potwierdzenia, w.created_at, w.id) DESC LIMIT 1), '')"
                    )

                query = f"""
                    SELECT p.*, plan.produkt as nazwa_produktu, 
                           plan.nazwa_zlecenia as numer_zlecenia,
                           {suggested_location_sql} AS suggested_location
                    FROM {table_prod} p
                    LEFT JOIN {table_plan} plan ON p.plan_id = plan.id
                    WHERE p.status = 'do_przyjecia'
                    ORDER BY p.data_dodania DESC
                """
                if is_psd:
                    query = f"""
                        SELECT p.*, plan.produkt as nazwa_produktu,
                               plan.nazwa_zlecenia as numer_zlecenia,
                               {suggested_location_sql} AS suggested_location
                        FROM {table_prod} p
                        LEFT JOIN {table_plan} plan ON p.plan_id = plan.id
                        WHERE p.status = 'do_przyjecia'
                        ORDER BY p.data_dodania DESC
                    """

                cursor.execute(query)
                rows = cursor.fetchall()
                for row in rows:
                    suggested_location = LocationService._normalize_location_code(row.get('suggested_location'))
                    row['suggested_location'] = suggested_location
                    row['target_zone'] = LocationService._derive_target_zone(suggested_location)
                return rows
            except Exception as e:
                print(f"Error fetching pending production pallets: {e}")
                return []
            finally:
                conn.close()

    def get_raport(date_from=None, date_to=None):
            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                query = "SELECT * FROM magazyn_dostawy WHERE status = 'COMPLETED'"
                params = []
                if date_from:
                    query += " AND DATE(created_at) >= %s"
                    params.append(date_from)
                if date_to:
                    query += " AND DATE(created_at) <= %s"
                    params.append(date_to)
                query += " ORDER BY created_at DESC"
                cursor.execute(query, params)
                dostawy = cursor.fetchall()
                
                # For backfilling missing nr_palety in old reports
                table_sur_psd = get_table_name('magazyn_surowce', 'PSD')
                table_opk_psd = get_table_name('magazyn_opakowania', 'PSD')
                table_sur_agro = get_table_name('magazyn_surowce', 'AGRO')
                table_opk_agro = get_table_name('magazyn_opakowania', 'AGRO')

                for d in dostawy:
                    if d.get('created_at'):
                        d['created_at'] = d['created_at'].strftime('%Y-%m-%d %H:%M:%S')
                    if d.get('potwierdzone_at'):
                        d['potwierdzone_at'] = d['potwierdzone_at'].strftime('%Y-%m-%d %H:%M:%S')
                    if d.get('items'):
                        try:
                            its = json.loads(d['items'])
                            linia = d.get('linia', 'PSD').upper()
                            t_sur = table_sur_agro if linia == 'AGRO' else table_sur_psd
                            t_opk = table_opk_agro if linia == 'AGRO' else table_opk_psd

                            for item in its:
                                if not item.get('nr_palety'):
                                    # Try to find it in DB by last known location/product
                                    loc = item.get('lokalizacja_przyjecia')
                                    name = item.get('productName')
                                    if loc and name:
                                        cursor.execute(f"SELECT nr_palety FROM {t_sur} WHERE lokalizacja = %s AND nazwa = %s AND stan_magazynowy > 0 LIMIT 1", (loc, name))
                                        res = cursor.fetchone()
                                        if not res:
                                            cursor.execute(f"SELECT nr_palety FROM {t_opk} WHERE lokalizacja = %s AND nazwa = %s AND stan_magazynowy > 0 LIMIT 1", (loc, name))
                                            res = cursor.fetchone()
                                        if res:
                                            item['nr_palety'] = res['nr_palety']
                            d['items_parsed'] = its
                        except Exception as e:
                            print(f"Error parsing items in raport: {e}")
                            d['items_parsed'] = []
                return dostawy
            finally:
                conn.close()
