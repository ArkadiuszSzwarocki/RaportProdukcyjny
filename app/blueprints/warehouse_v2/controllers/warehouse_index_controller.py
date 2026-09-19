from datetime import datetime, date
from flask import render_template, request
from app.db import get_db_connection, get_table_name
from app.blueprints.warehouse_v2.utils.date_formatters import format_date_val, compute_expiry_date
from app.blueprints.warehouse_v2.utils.packaging_classifier import classify_packaging_type
from app.services.dashboard_service import DashboardService
from app.services.warehouse_v2.warehouse_pending_items_service import WarehousePendingItemsService

class WarehouseIndexController:
    @staticmethod
    def render_index():
        """Render the main warehouse dashboard with stocks, locations, capacities, and printers."""
        linia = request.args.get('linia', 'ALL').upper()
        palety_linie = ['PSD', 'AGRO']
        shared_linia = linia if linia in ('PSD', 'AGRO') else 'PSD'
        conn = get_db_connection()
        items = []
        printers = []
        try:
            cursor = conn.cursor(dictionary=True)
            
            # Load active printers
            try:
                cursor.execute("SELECT id, nazwa, ip, lokalizacja FROM drukarki WHERE aktywna = 1")
                printers = cursor.fetchall()
            except Exception as e:
                print(f"Error fetching printers: {e}")
            
            # 1. Surowce
            table_surowce = get_table_name('magazyn_surowce', linia)
            try:
                cursor.execute(f"SELECT id, nr_palety, nazwa as productName, lokalizacja as location, stan_magazynowy as amount, 'Surowiec' as type, data_produkcji, data_przydatnosci, nr_partii, is_blocked, created_at, typ_opakowania FROM {table_surowce} WHERE stan_magazynowy > 0")
                surowce = cursor.fetchall()
                for row in surowce:
                    row['displayId'] = row['nr_palety'] if row['nr_palety'] else f"SUR-{row['id']}"
                    row['linia'] = shared_linia
                    row['date_prod'] = format_date_val(row.get('data_produkcji'))
                    row['date_exp'] = compute_expiry_date(row.get('data_przydatnosci'), row.get('data_produkcji'))
                    row['date_added'] = format_date_val(row.get('created_at'), '%Y-%m-%d %H:%M')
                    row['batch'] = row.get('nr_partii') or '-'
                    row['unit'] = 'kg'
                    row['is_blocked'] = row.get('is_blocked', 0)
                    row['packaging_type'] = classify_packaging_type(row['productName'], row['type'], row['amount'], row['unit'], row.get('typ_opakowania'))
                    row['raw_packaging_type'] = row.get('typ_opakowania') or 'Karton'
                    items.append(row)
            except Exception as e:
                print(f"Error fetching surowce: {e}")

            # 2. Opakowania
            table_opakowania = get_table_name('magazyn_opakowania', linia)
            try:
                cursor.execute(f"SELECT id, nr_palety, nazwa as productName, lokalizacja as location, stan_magazynowy as amount, 'Opakowanie' as type, data_produkcji, data_przydatnosci, nr_partii, is_blocked, created_at, typ_opakowania FROM {table_opakowania} WHERE stan_magazynowy > 0")
                opakowania = cursor.fetchall()
                for row in opakowania:
                    row['displayId'] = row['nr_palety'] if row['nr_palety'] else f"OPK-{row['id']}"
                    row['linia'] = shared_linia
                    row['date_prod'] = format_date_val(row.get('data_produkcji'))
                    row['date_exp'] = compute_expiry_date(row.get('data_przydatnosci'), row.get('data_produkcji'))
                    row['date_added'] = format_date_val(row.get('created_at'), '%Y-%m-%d %H:%M')
                    row['batch'] = row.get('nr_partii') or '-'
                    row['unit'] = 'szt'
                    row['is_blocked'] = row.get('is_blocked', 0)
                    row['packaging_type'] = classify_packaging_type(row['productName'], row['type'], row['amount'], row['unit'], row.get('typ_opakowania'))
                    row['raw_packaging_type'] = row.get('typ_opakowania') or 'Karton'
                    items.append(row)
            except Exception as e:
                print(f"Error fetching opakowania: {e}")

            # 3. Wyroby Gotowe (dla obu linii z zunifikowanej tabeli magazyn_palety)
            for linia_palety in ['PSD', 'AGRO']:
                table_palety = get_table_name('magazyn_palety', linia_palety)
                table_plan = get_table_name('plan_produkcji', linia_palety)
                alt_linia = 'AGRO' if linia_palety == 'PSD' else 'PSD'
                table_plan_alt = get_table_name('plan_produkcji', alt_linia)
                if linia_palety == 'PSD':
                    line_condition = "AND (m.linia = 'PSD' OR m.linia IS NULL OR m.linia = '')"
                else:
                    line_condition = "AND m.linia = 'AGRO'"
                try:
                    cursor.execute(
                        f"""
                        SELECT m.id, m.nr_palety, 
                               COALESCE(NULLIF(TRIM(m.produkt), ''), plan.produkt, plan_pw.produkt, plan_alt.produkt, plan_pw_alt.produkt, 'Nieznany produkt') as productName, 
                               COALESCE(NULLIF(TRIM(m.lokalizacja), ''), 'MGW01') as location, 
                               m.waga_netto as amount, 
                               'Wyrób Gotowy' as type, 
                               COALESCE(NULLIF(TRIM(m.data_produkcji), ''), plan.data_produkcji, plan_pw.data_produkcji, m.data_planu, plan.data_planu, plan_pw.data_planu) as data_produkcji, 
                               COALESCE(NULLIF(TRIM(m.data_przydatnosci), ''), plan.termin_przydatnosci, plan_pw.termin_przydatnosci) as data_przydatnosci, 
                               COALESCE(NULLIF(TRIM(m.linia), ''), '{linia_palety}') as linia, 
                               COALESCE(NULLIF(TRIM(m.nr_partii), ''), plan.nr_partii, plan_pw.nr_partii) as nr_partii, 
                               m.is_blocked, 
                               COALESCE(m.created_at, m.data_potwierdzenia) as created_at,
                               COALESCE(m.typ_opakowania, plan.typ_opakowania, plan_pw.typ_opakowania, '') as typ_opakowania,
                               COALESCE(m.plan_id, pw.plan_id) as effective_plan_id,
                               COALESCE(plan.data_planu, plan_pw.data_planu, plan_alt.data_planu, plan_pw_alt.data_planu) as plan_order_date,
                               COALESCE(NULLIF(plan.nazwa_zlecenia, ''), NULLIF(plan_pw.nazwa_zlecenia, ''), NULLIF(plan_alt.nazwa_zlecenia, ''), NULLIF(plan_pw_alt.nazwa_zlecenia, ''), NULLIF(plan.typ_zlecenia, ''), NULLIF(plan_pw.typ_zlecenia, '')) as plan_order_name
                        FROM {table_palety} m
                        LEFT JOIN palety_workowanie pw ON m.paleta_workowanie_id = pw.id
                        LEFT JOIN {table_plan} plan ON m.plan_id = plan.id
                        LEFT JOIN {table_plan} plan_pw ON pw.plan_id = plan_pw.id
                        LEFT JOIN {table_plan_alt} plan_alt ON m.plan_id = plan_alt.id
                        LEFT JOIN {table_plan_alt} plan_pw_alt ON pw.plan_id = plan_pw_alt.id
                        WHERE m.waga_netto > 0 AND (m.is_loaded = 0 OR m.is_loaded IS NULL) {line_condition}
                        """
                    )
                    palety = cursor.fetchall()

                    for row in palety:
                        row['displayId'] = row['nr_palety'] if row['nr_palety'] else f"PAL-{row['id']}"
                        row['linia'] = (row.get('linia') or linia_palety)
                        row['date_prod'] = format_date_val(row.get('data_produkcji'))
                        row['date_exp'] = compute_expiry_date(row.get('data_przydatnosci'), row.get('data_produkcji'))
                        row['date_added'] = format_date_val(row.get('created_at'), '%Y-%m-%d %H:%M')
                        row['batch'] = row.get('nr_partii') or '-'
                        row['unit'] = 'kg'
                        row['is_blocked'] = row.get('is_blocked', 0)
                        row['packaging_type'] = classify_packaging_type(row['productName'], row['type'], row['amount'], row['unit'], row.get('typ_opakowania'))
                        row['raw_packaging_type'] = row.get('typ_opakowania') or 'Karton'

                        if not row.get('location') or str(row.get('location')).strip().upper() == 'OCZEKUJĄCE':
                            row['location'] = 'MGW01'

                        # Attach production plan order details
                        plan_id = row.get('effective_plan_id')
                        plan_date_raw = row.get('plan_order_date')
                        plan_date_str = format_date_val(plan_date_raw) if plan_date_raw else ''
                        if plan_id:
                            row['order_id'] = f"PLAN-{plan_id}"
                            row['order_ref'] = f"Plan #{plan_id}"
                            row['order_doc_type'] = 'PROD'
                            row['order_doc_label'] = f"PROD: #{plan_id}"
                            row['order_date'] = plan_date_str
                            row['order_source'] = f"Linia {row['linia']}"
                        elif plan_date_str:
                            row['order_date'] = plan_date_str

                        items.append(row)
                except Exception as e:
                    print(f"Error fetching wyroby gotowe ({linia_palety}): {e}")

            # 3b. Oczekujące Wyroby Gotowe z produkcji (palety w buforze ze statusem 'do_przyjecia')
            for linia_prod in ['PSD', 'AGRO']:
                tbl_prod = 'palety_workowanie' if linia_prod == 'PSD' else 'palety_agro'
                tbl_plan_p = 'plan_produkcji' if linia_prod == 'PSD' else 'plan_produkcji_agro'
                try:
                    cursor.execute(f"""
                        SELECT pw.id, pw.nr_palety,
                               COALESCE(NULLIF(TRIM(plan.produkt), ''), 'Wyrób gotowy') as productName,
                               'OCZEKUJĄCE' as location,
                               COALESCE(NULLIF(pw.waga_potwierdzona, 0), pw.waga, 0) as amount,
                               'Wyrób Gotowy' as type,
                               pw.data_dodania as data_produkcji,
                               plan.termin_przydatnosci as data_przydatnosci,
                               '{linia_prod}' as linia,
                               COALESCE(plan.nr_partii, '') as nr_partii,
                               0 as is_blocked,
                               pw.data_dodania as created_at,
                               COALESCE(plan.typ_opakowania, 'Karton') as typ_opakowania,
                               pw.plan_id as effective_plan_id,
                               plan.data_planu as plan_order_date,
                               COALESCE(NULLIF(plan.nazwa_zlecenia, ''), plan.typ_zlecenia, '') as plan_order_name
                        FROM {tbl_prod} pw
                        LEFT JOIN {tbl_plan_p} plan ON pw.plan_id = plan.id
                        WHERE (
                            LOWER(COALESCE(pw.status, '')) IN ('do_przyjecia', 'oczekujace', 'oczekuje', 'bufor', 'nowa', '')
                            OR pw.status IS NULL
                        )
                        AND LOWER(COALESCE(pw.status, '')) NOT IN ('w_magazynie', 'przyjeta', 'wydana', 'anulowana')
                        ORDER BY pw.id DESC
                    """)
                    pending_palety = cursor.fetchall()
                    for row in pending_palety:
                        row['displayId'] = row['nr_palety'] if row['nr_palety'] else f"PAL-{row['id']}"
                        row['linia'] = linia_prod
                        row['date_prod'] = format_date_val(row.get('data_produkcji'))
                        row['date_exp'] = compute_expiry_date(row.get('data_przydatnosci'), row.get('data_produkcji'))
                        row['date_added'] = format_date_val(row.get('created_at'), '%Y-%m-%d %H:%M')
                        row['batch'] = row.get('nr_partii') or '-'
                        row['unit'] = 'kg'
                        row['is_blocked'] = 0
                        row['packaging_type'] = classify_packaging_type(row['productName'], row['type'], row['amount'], row['unit'], row.get('typ_opakowania'))
                        row['raw_packaging_type'] = row.get('typ_opakowania') or 'Karton'
                        row['location'] = 'OCZEKUJĄCE'

                        plan_id = row.get('effective_plan_id')
                        plan_date_raw = row.get('plan_order_date')
                        plan_date_str = format_date_val(plan_date_raw) if plan_date_raw else ''
                        if plan_id:
                            row['order_id'] = f"PLAN-{plan_id}"
                            row['order_ref'] = f"Plan #{plan_id}"
                            row['order_doc_type'] = 'PROD'
                            row['order_doc_label'] = f"PROD: #{plan_id}"
                            row['order_date'] = plan_date_str
                            row['order_source'] = f"Linia {row['linia']}"
                        elif plan_date_str:
                            row['order_date'] = plan_date_str

                        items.append(row)
                except Exception as e_pw:
                    print(f"Error fetching pending production pallets ({linia_prod}): {e_pw}")

            # 4. Dodatki
            try:
                cursor.execute("SELECT id, nr_palety, nazwa as productName, lokalizacja as location, stan_magazynowy as amount, 'Dodatek' as type, data_produkcji, data_przydatnosci, nr_partii, is_blocked, created_at, typ_opakowania FROM magazyn_dodatki WHERE stan_magazynowy > 0")
                dodatki = cursor.fetchall()
                for row in dodatki:
                    row['displayId'] = row['nr_palety'] if row['nr_palety'] else f"DOD-{row['id']}"
                    row['linia'] = shared_linia
                    row['date_prod'] = format_date_val(row.get('data_produkcji'))
                    row['date_exp'] = compute_expiry_date(row.get('data_przydatnosci'), row.get('data_produkcji'))
                    row['date_added'] = format_date_val(row.get('created_at'), '%Y-%m-%d %H:%M')
                    row['batch'] = row.get('nr_partii') or '-'
                    row['unit'] = 'kg'
                    row['is_blocked'] = row.get('is_blocked', 0)
                    row['packaging_type'] = classify_packaging_type(row['productName'], row['type'], row['amount'], row['unit'], row.get('typ_opakowania'))
                    row['raw_packaging_type'] = row.get('typ_opakowania') or 'Karton'
                    items.append(row)
            except Exception as e:
                print(f"Error fetching dodatki: {e}")

            # 5. Oczekujące pozycje ze zleceń i dostaw (deduplikacja + wzbogacenie o dane PZ/MM/WZ)
            try:
                WarehousePendingItemsService.enrich_and_append_pending(items, linia)
            except Exception as e:
                print(f"Error enriching pending items: {e}")

        except Exception as e:
            print(f"Error in dashboard: {e}")

        # Mark expired pallets as system-blocked
        today_str = datetime.now().strftime('%Y-%m-%d')
        for it in items:
            exp = it.get('date_exp')
            if exp and exp not in ('-', 'brak', '', 'None') and exp < today_str:
                it['is_blocked'] = 1
                it['is_system_blocked'] = 1

        # Sortowanie: Regał -> Rząd -> Gniazdo
        def get_sort_key(item):
            loc = (item.get('location') or '').strip().upper()
            if loc.startswith('R') and len(loc) >= 7:
                try:
                    rack = loc[:3]
                    gniazdo = loc[3:5]
                    rzad = loc[5:7]
                    return (0, rack, rzad, gniazdo)
                except Exception:
                    return (1, loc, '', '')
            return (1, loc, '', '')

        items.sort(key=get_sort_key)

        magazyny_zakladki = [
            {'id': 'all', 'name': 'Wszystkie Magazyny'},
            {'id': 'MP01', 'name': 'Magazyn Produkcyjny (MP01)'},
            {'id': 'MS01', 'name': 'Magazyn Surowcowy (MS01)'},
            {'id': 'OSIP', 'name': 'Magazyn Zewnętrzny (OSIP)', 'code': 'ZEWNĘTRZNY'},
            {'id': 'PSD01', 'name': 'Magazyn Produkcyjny (PSD01)'},
            {'id': 'MDO01', 'name': 'Magazyn Dodatków (MDO01)'},
            {'id': 'MOP01', 'name': 'Magazyn Opakowań (MOP01)'},
            {'id': 'MGW01', 'name': 'Magazyn Wyrobów Gotowych 1 (MGW01)'},
            {'id': 'MGW02', 'name': 'Magazyn Wyrobów Gotowych 2 (MGW02)'},
            {'id': 'BF_MS01', 'name': 'BUFOR MS01'},
            {'id': 'BF_MP01', 'name': 'BUFOR MP01'}
        ]

        # Calculate occupancy stats
        stats = {}
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM magazyn_pojemnosci")
            caps = {r['sekcja']: r['pojemnosc_max'] for r in cursor.fetchall()}
            
            all_sections = list(caps.keys())
            for zid in all_sections:
                total = caps.get(zid, 100)
                occupied = 0
                
                if zid.startswith('R'):
                    occupied = len([it for it in items if (it.get('location') or '').startswith(zid)])
                elif zid == 'MP01':
                    occupied = len([it for it in items if ('MP01' in (it.get('location') or '').upper() or 'PODŁOGA' in (it.get('location') or '').upper()) and 'R0' not in (it.get('location') or '').upper()])
                    total = caps.get('MP01', 20)
                elif zid == 'MS01':
                    occupied = len([it for it in items if 'MS01' in (it.get('location') or '').upper() or 'PODŁOGA' in (it.get('location') or '').upper()])
                    total = caps.get('MS01', 0)
                elif zid in ['MGW01', 'MGW02']:
                    occupied = len([it for it in items if (it.get('location') or '').upper() == zid or (it.get('type') == 'Wyrób Gotowy' and not it.get('location') and zid == 'MGW01')])
                else:
                    occupied = len([it for it in items if zid in (it.get('location') or '').upper()])

                stats[zid] = {
                    'occupied': occupied,
                    'total': total,
                    'percent': round((occupied / total * 100), 1) if total > 0 else 0
                }

            non_osip_items = [it for it in items if not ('OSIP' in (it.get('location') or '').upper() or (it.get('location') or '').upper().startswith('OS'))]
            total_non_osip_cap = sum(v for k, v in caps.items() if k != 'OSIP')
            stats['all'] = {
                'occupied': len(non_osip_items),
                'total': total_non_osip_cap,
                'percent': min(100, round((len(non_osip_items) / total_non_osip_cap * 100), 1)) if total_non_osip_cap > 0 else 0
            }
        except Exception as e:
            print(f"Error calculating stats: {e}")
            stats = {}
        finally:
            conn.close()

        fefo_pallets = DashboardService.get_expiring_pallets(date.today(), linia, days_threshold=30)
        aktywna_zakladka = request.args.get('zakladka', 'all')
        return render_template('warehouse_v2/dashboard.html', items=items, linia=linia, zakladki=magazyny_zakladki, aktywna_zakladka=aktywna_zakladka, stats=stats, printers=printers, fefo_pallets=fefo_pallets)
