from app.db import get_db_connection, get_table_name
import json
from datetime import datetime
import uuid
import re
from app.utils.pallet_id import generate_pallet_id
from app.utils.location_validator import validate_warehouse_location, is_production_tank_code

from app.services.magazyn_dostawy.location_service import LocationService

class AcceptanceService:

    def accept_item(dostawa_id, item_id, lokalizacja, login='system', nr_partii=None, data_produkcji=None, data_przydatnosci=None, printer_ip=None, printer_name=None):
            def _clean_date(d_str):
                if not d_str: return None
                s = str(d_str).strip()
                if not s: return None
                if re.match(r'^\d{4}-\d{2}-\d{2}$', s): return s
                try:
                    from dateutil import parser
                    return parser.parse(s).strftime('%Y-%m-%d')
                except Exception:
                    return None
            
            data_produkcji = _clean_date(data_produkcji)
            data_przydatnosci = _clean_date(data_przydatnosci)

            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("SELECT * FROM magazyn_dostawy WHERE id = %s", (dostawa_id,))
                dostawa = cursor.fetchone()
                if not dostawa: return False, "Nie znaleziono przesunięcia", None

                lokalizacja = str(lokalizacja or '').strip().upper()
                if not lokalizacja:
                    return False, "Podaj lokalizację odstawienia.", None

                # Walidacja: new_location NIE może być kodem zbiornika produkcyjnego
                is_valid, error_msg = validate_warehouse_location(lokalizacja, allow_empty=False)
                if not is_valid:
                    return False, error_msg

                # Sprawdzenie ze słownikiem dozwolonych lokalizacji
                try:
                    cursor.execute("SELECT nazwa FROM magazyn_dozwolone_lokalizacje")
                    dozwolone = [row['nazwa'].upper() for row in cursor.fetchall()]
                    if dozwolone:
                        is_dict_valid = False
                        for dozw_lok in dozwolone:
                            if lokalizacja.startswith(dozw_lok):
                                is_dict_valid = True
                                break
                        if not is_dict_valid:
                            return False, f"Lokalizacja '{lokalizacja}' nie występuje w dozwolonym słowniku (Baza: Ustawienia).", None
                except Exception as e:
                    print(f"Błąd ładowania słownika lokalizacji: {e}")

                items = json.loads(dostawa['items'] or '[]')
                linia = dostawa['linia']
                # Compare IDs as strings to avoid type mismatch (int/float from JSON vs string from request)
                target = next((i for i in items if str(i.get('id')) == str(item_id)), None)
                if not target: return False, "Nie znaleziono pozycji", None
                if target.get('accepted'): return False, "Pozycja już przyjęta", None
                if target.get('rejected'): return False, "Pozycja została odrzucona", None

                source_spot = str(target.get('sourceSpot') or '').strip().upper()
                if not source_spot:
                    fallback_source = str(dostawa.get('lokalizacja_z') or '').strip().upper()
                    if fallback_source and fallback_source != 'WIELE':
                        source_spot = fallback_source
                if source_spot and source_spot == lokalizacja:
                    return False, f"Nie można przyjąć na tę samą lokalizację ({lokalizacja}), z której przyjmujesz.", None

                table_sur = get_table_name('magazyn_surowce', linia)
                table_opk = get_table_name('magazyn_opakowania', linia)

                product_name = target.get('productName') or 'Brak nazwy'
                # Reuse existing nr_palety if this was a transfer, otherwise generate new
                nr_palety = target.get('nr_palety') or generate_pallet_id(linia, type=('opakowanie' if target.get('packageForm') == 'packaging' else 'surowiec'))
                pkg_form = target.get('packageForm', 'bags') # bags or big_bag

                open_locations = ['MS01', 'MP01', 'MD01', 'MOP01', 'BF_MS01', 'BF_MP01', 'MDM01', 'PSD01', 'MGW01', 'MGW02', 'OSIP', 'KO01', 'RAMPA', 'MIX01', 'W_TRANZYCIE_OSIP', 'PSD']
                is_open = any(lokalizacja.upper().startswith(ol) for ol in open_locations)

                if not is_open:
                    cursor.execute(f"SELECT 1 FROM {table_sur} WHERE lokalizacja = %s AND stan_magazynowy > 0 AND (nr_palety IS NULL OR nr_palety != %s)", (lokalizacja, nr_palety))
                    if cursor.fetchone(): return False, f"Lokalizacja {lokalizacja} zajęta w surowcach!", None
                    cursor.execute(f"SELECT 1 FROM {table_opk} WHERE lokalizacja = %s AND stan_magazynowy > 0 AND (nr_palety IS NULL OR nr_palety != %s)", (lokalizacja, nr_palety))
                    if cursor.fetchone(): return False, f"Lokalizacja {lokalizacja} zajęta w opakowaniach!", None
                    cursor.execute(f"SELECT 1 FROM magazyn_dodatki WHERE lokalizacja = %s AND stan_magazynowy > 0 AND (nr_palety IS NULL OR nr_palety != %s)", (lokalizacja, nr_palety))
                    if cursor.fetchone(): return False, f"Lokalizacja {lokalizacja} zajęta w dodatkach!", None

                p_type_scanned = str(target.get('scannedType') or target.get('type') or '').strip().lower()

                if target.get('packageForm') == 'packaging' or p_type_scanned == 'opakowanie':
                    qty = float(target.get('unitsPerPallet') or 0)
                    cursor.execute(f"INSERT INTO {table_opk} (nazwa, stan_magazynowy, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, nr_palety, typ_opakowania) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE stan_magazynowy = VALUES(stan_magazynowy), nazwa = VALUES(nazwa), nr_partii = VALUES(nr_partii), data_produkcji = VALUES(data_produkcji), data_przydatnosci = VALUES(data_przydatnosci), nr_palety = VALUES(nr_palety), typ_opakowania = VALUES(typ_opakowania), lokalizacja = VALUES(lokalizacja)", (product_name, qty, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, nr_palety, pkg_form))
                    p_type = 'opakowanie'
                elif p_type_scanned == 'dodatek':
                    qty = float(target.get('netWeight') or 0)
                    cursor.execute(f"INSERT INTO magazyn_dodatki (nazwa, stan_magazynowy, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, nr_palety, typ_opakowania, linia) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE stan_magazynowy = VALUES(stan_magazynowy), nazwa = VALUES(nazwa), nr_partii = VALUES(nr_partii), data_produkcji = VALUES(data_produkcji), data_przydatnosci = VALUES(data_przydatnosci), nr_palety = VALUES(nr_palety), typ_opakowania = VALUES(typ_opakowania), lokalizacja = VALUES(lokalizacja)", (product_name, qty, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, nr_palety, pkg_form, linia))
                    p_type = 'dodatek'
                else:
                    qty = float(target.get('netWeight') or 0)
                    cursor.execute(f"INSERT INTO {table_sur} (nazwa, stan_magazynowy, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, nr_palety, typ_opakowania) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE stan_magazynowy = VALUES(stan_magazynowy), nazwa = VALUES(nazwa), nr_partii = VALUES(nr_partii), data_produkcji = VALUES(data_produkcji), data_przydatnosci = VALUES(data_przydatnosci), nr_palety = VALUES(nr_palety), typ_opakowania = VALUES(typ_opakowania), lokalizacja = VALUES(lokalizacja)", (product_name, qty, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, nr_palety, pkg_form))
                    p_type = 'surowiec'

                # Get the ID of the pallet (new or existing)
                pallet_id = cursor.lastrowid
                if not pallet_id or pallet_id == 0:
                    table_name = table_opk if p_type == 'opakowanie' else ('magazyn_dodatki' if p_type == 'dodatek' else table_sur)
                    cursor.execute(f"SELECT id FROM {table_name} WHERE lokalizacja = %s AND stan_magazynowy > 0 LIMIT 1", (lokalizacja,))
                    p_row = cursor.fetchone()
                    pallet_id = p_row['id'] if p_row else None

                target['accepted'] = True
                target['accepted_by'] = login
                target['accepted_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                target['lokalizacja_przyjecia'] = lokalizacja
                target['nr_partii'] = nr_partii
                target['nr_palety'] = nr_palety
                target['data_produkcji'] = data_produkcji
                target['data_przydatnosci'] = data_przydatnosci

                # Zwalniamy blokadę dla przyjętej palety źródłowej
                source_pallet_id = target.get('sourcePalletId')
                if source_pallet_id:
                    tbl_unblk = table_opk if p_type == 'opakowanie' else (table_sur if p_type == 'surowiec' else None)
                    if not tbl_unblk and p_type == 'dodatek': tbl_unblk = 'magazyn_dodatki'
                    elif not tbl_unblk and p_type in ['magazyn', 'produkcja', 'wyrob_gotowy']: tbl_unblk = get_table_name('magazyn_palety', linia)
                    
                    if tbl_unblk:
                        try:
                            cursor.execute(f"UPDATE {tbl_unblk} SET is_blocked = 0 WHERE id = %s", (source_pallet_id,))
                        except Exception:
                            pass

                # 3. Empty the source spot (from Transfer or from External Delivery pending buffer)
                source_spot = target.get('sourceSpot')
                is_partial = target.get('is_partial', False)
                source_pallet_id = target.get('sourcePalletId')

                if source_spot and not is_partial:
                    actual_source_loc = 'OCZEKUJĄCE' if source_spot == 'DOSTAWA' else source_spot
                    
                    if source_pallet_id:
                        # Find the pallet at source and zero it EXACTLY by ID
                        cursor.execute(f"UPDATE {table_sur} SET stan_magazynowy = 0 WHERE id = %s", (source_pallet_id,))
                        cursor.execute(f"UPDATE {table_opk} SET stan_magazynowy = 0 WHERE id = %s", (source_pallet_id,))
                        cursor.execute(f"UPDATE magazyn_dodatki SET stan_magazynowy = 0 WHERE id = %s", (source_pallet_id,))
                    else:
                        # Fallback for old data without sourcePalletId
                        cursor.execute(f"UPDATE {table_sur} SET stan_magazynowy = 0 WHERE lokalizacja = %s AND nazwa = %s AND stan_magazynowy > 0 LIMIT 1", (actual_source_loc, product_name))
                        cursor.execute(f"UPDATE {table_opk} SET stan_magazynowy = 0 WHERE lokalizacja = %s AND nazwa = %s AND stan_magazynowy > 0 LIMIT 1", (actual_source_loc, product_name))
                        cursor.execute(f"UPDATE magazyn_dodatki SET stan_magazynowy = 0 WHERE lokalizacja = %s AND nazwa = %s AND stan_magazynowy > 0 LIMIT 1", (actual_source_loc, product_name))
                
                # If it's partial, we already subtracted at Stage 1, so we just create the new one at destination (handled by next lines)
                    
                    cursor.execute(
                        "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, lokalizacja_zrodlowa, komentarz, user_login) VALUES (%s, %s, %s, 'WYDANIE_PRZESUNIECIE', %s, %s, %s)",
                        (None, linia, p_type, source_spot, f"Wydanie do przesunięcia: {product_name} -> {lokalizacja}", login)
                    )

                # Log to palety_historia
                cursor.execute(
                    "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, %s, 'PRZYJECIE', %s, %s, %s)",
                    (pallet_id, linia, p_type, lokalizacja, f"Przyjęcie z dostawy: {product_name}, partia: {nr_partii}", login)
                )

                all_processed = all(i.get('accepted') or i.get('rejected') for i in items)
                new_status = 'COMPLETED' if all_processed else 'OCZEKUJE'

                cursor.execute("UPDATE magazyn_dostawy SET items=%s, status=%s, potwierdzone_przez=%s, potwierdzone_at=%s WHERE id=%s", (json.dumps(items), new_status, login if all_processed else dostawa.get('potwierdzone_przez'), datetime.now() if all_processed else dostawa.get('potwierdzone_at'), dostawa_id))
                conn.commit()
                
                if new_status == 'COMPLETED':
                    try:
                        from flask import url_for
                        from app.services.office_print_service import trigger_office_print_url
                        # Using request.host_url inside try block to be safe if no request context
                        from flask import current_app, request
                        if request:
                            report_url = url_for(
                                'magazyn_dostawy.raport_przesuniecia',
                                dostawa_id=dostawa_id,
                                linia=linia,
                                internal_print=1,
                                _external=True
                            )
                            trigger_office_print_url(report_url, 'raport_dostawy_zewnetrznej', prefix="dostawa_zewn_")
                    except Exception as print_e:
                        print("Błąd automatycznego druku raportu A4 po kompletacji dostawy zewnetrznej:", print_e)
                
                # --- AUTO DRUKOWANIE ETYKIET (2 SZT) W TLE ---
                if printer_ip and printer_name:
                    try:
                        import threading
                        import requests
                        import urllib3
                        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                        payload = {
                            "drukarka": printer_name,
                            "ip": printer_ip,
                            "typ": p_type,
                            "dane": {
                                "palletData": {
                                    "nrPalety": nr_palety,
                                    "productName": product_name,
                                    "batchNumber": nr_partii or '---',
                                    "productionDate": str(data_produkcji) if data_produkcji else '---',
                                    "expiryDate": str(data_przydatnosci) if data_przydatnosci else '---',
                                    "currentWeight": qty,
                                    "labNotes": "Dostawa Przyjęta"
                                }
                            }
                        }
                        def run_print():
                            url = "http://127.0.0.1:3001/drukuj-zpl"
                            for _ in range(2):
                                try:
                                    requests.post(url, json=payload, verify=False, timeout=3)
                                except Exception:
                                    pass
                        threading.Thread(target=run_print, daemon=True).start()
                    except Exception as e:
                        print(f"Błąd uruchomienia wątku drukowania: {e}")
                # --- KONIEC AUTO DRUKU ---

                return True, "", {
                    "all_accepted": all_processed,
                    "all_processed": all_processed,
                    "accepted_count": sum(1 for i in items if i.get('accepted')),
                    "rejected_count": sum(1 for i in items if i.get('rejected')),
                    "total": len(items),
                    "linia": linia,
                    "dostawa_id": dostawa_id,
                    "nr_palety": nr_palety,
                }
            except Exception as e:
                return False, str(e), None
            finally:
                conn.close()

    def auto_accept_by_pallet_no(nr_palety, nowa_lokalizacja, login):
            if not nr_palety: return
            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("SELECT id, items FROM magazyn_dostawy WHERE status IN ('OCZEKUJE', 'IN_PROGRESS')")
                orders = cursor.fetchall()
                for o in orders:
                    items = json.loads(o['items'] or '[]')
                    for item in items:
                        if str(item.get('nr_palety') or '') == str(nr_palety) and not item.get('accepted') and not item.get('rejected'):
                            import logging
                            logging.info(f"Auto-accepting item {item['id']} for dostawa {o['id']} (nr_palety={nr_palety})")
                            # Call accept_item for this specific item!
                            success, msg, _ = AcceptanceService.accept_item(
                                o['id'], 
                                item['id'], 
                                nowa_lokalizacja, 
                                login
                            )
                            if not success:
                                logging.error(f"Auto-accept item failed: {msg}")
            except Exception as e:
                import logging
                logging.error(f"Auto-accept failed for pallet {nr_palety}: {e}")
            finally:
                conn.close()

    def reject_item(dostawa_id, item_id, reason='', login='system'):
            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("SELECT * FROM magazyn_dostawy WHERE id = %s", (dostawa_id,))
                dostawa = cursor.fetchone()
                if not dostawa:
                    return False, "Nie znaleziono przesunięcia", None
                if str(dostawa.get('status') or '').upper() == 'CANCELLED':
                    return False, "Przesunięcie jest już anulowane", None

                items = json.loads(dostawa.get('items') or '[]')
                target = next((i for i in items if str(i.get('id')) == str(item_id)), None)
                if not target:
                    return False, "Nie znaleziono pozycji", None
                if target.get('accepted'):
                    return False, "Pozycja już przyjęta", None
                if target.get('rejected'):
                    return False, "Pozycja już odrzucona", None

                linia = dostawa['linia']
                table_sur = get_table_name('magazyn_surowce', linia)
                table_opk = get_table_name('magazyn_opakowania', linia)

                source_spot = str(target.get('sourceSpot') or '').strip().upper()
                if not source_spot:
                    fallback_source = str(dostawa.get('lokalizacja_z') or '').strip().upper()
                    if fallback_source and fallback_source != 'WIELE':
                        source_spot = fallback_source
                original_spot = str(target.get('originalSpot') or '').strip().upper()
                product_name = target.get('productName') or ''
                pallet_id = target.get('sourcePalletId')
                pallet_no = str(target.get('sourcePalletNo') or target.get('nr_palety') or '').strip()
                scanned_type = str(target.get('scannedType') or '').strip().lower()
                package_form = str(target.get('packageForm') or '').strip().lower()

                default_is_packaging = scanned_type == 'opakowanie' or package_form == 'packaging'
                default_table = table_opk if default_is_packaging else table_sur
                fallback_table = table_sur if default_is_packaging else table_opk
                restored = False
                restored_type = 'opakowanie' if default_is_packaging else 'surowiec'

                def _try_restore_on_table(table_name):
                    if pallet_id not in (None, ''):
                        cursor.execute(
                            f"UPDATE {table_name} SET lokalizacja = %s WHERE id = %s AND lokalizacja = %s",
                            (original_spot, pallet_id, source_spot)
                        )
                        if cursor.rowcount > 0:
                            return True

                    if pallet_no:
                        cursor.execute(
                            f"UPDATE {table_name} SET lokalizacja = %s WHERE lokalizacja = %s AND nr_palety = %s AND stan_magazynowy > 0",
                            (original_spot, source_spot, pallet_no)
                        )
                        if cursor.rowcount > 0:
                            return True

                    if product_name:
                        cursor.execute(
                            f"UPDATE {table_name} SET lokalizacja = %s WHERE lokalizacja = %s AND nazwa = %s AND stan_magazynowy > 0",
                            (original_spot, source_spot, product_name)
                        )
                        if cursor.rowcount > 0:
                            return True

                    return False

                if source_spot and original_spot and source_spot != original_spot:
                    restored = _try_restore_on_table(default_table)
                    if not restored:
                        restored = _try_restore_on_table(fallback_table)
                        if restored:
                            restored_type = 'surowiec' if default_is_packaging else 'opakowanie'

                normalized_reason = str(reason or '').strip() or 'Brak palety do przyjęcia'
                target['rejected'] = True
                target['rejected_by'] = login
                target['rejected_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                target['rejected_reason'] = normalized_reason
                target['reject_restored'] = restored

                if restored:
                    cursor.execute(
                        "INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, %s, 'TRANSFER_REJECT_ITEM', %s, %s, %s, %s)",
                        (pallet_id if pallet_id not in (None, '') else None, linia, restored_type, source_spot, original_spot, f"Odrzucenie pozycji: {normalized_reason}", login)
                    )

                all_processed = all(i.get('accepted') or i.get('rejected') for i in items)
                new_status = 'COMPLETED' if all_processed else 'OCZEKUJE'

                cursor.execute(
                    "UPDATE magazyn_dostawy SET items=%s, status=%s, potwierdzone_przez=%s, potwierdzone_at=%s WHERE id=%s",
                    (
                        json.dumps(items),
                        new_status,
                        login if all_processed else dostawa.get('potwierdzone_przez'),
                        datetime.now() if all_processed else dostawa.get('potwierdzone_at'),
                        dostawa_id,
                    )
                )
                conn.commit()

                return True, "", {
                    "all_accepted": all_processed,
                    "all_processed": all_processed,
                    "accepted_count": sum(1 for i in items if i.get('accepted')),
                    "rejected_count": sum(1 for i in items if i.get('rejected')),
                    "total": len(items),
                    "linia": linia,
                    "dostawa_id": dostawa_id,
                    "restored": restored,
                }
            except Exception as e:
                return False, str(e), None
            finally:
                conn.close()

    def accept_production_pallet(pallet_id, lokalizacja, linia='PSD', login='system', confirmed_weight=None):
            """Moves a production pallet (WG) from 'do_przyjecia' to warehouse inventory."""
            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                table_prod = 'palety_workowanie' if linia == 'PSD' else 'palety_agro'
                table_wh = 'magazyn_palety' if linia == 'PSD' else 'magazyn_palety_agro'
                
                # 1. Fetch pallet data
                query = f"""
                    SELECT p.*, plan.produkt as produkt_nazwa, plan.data_planu
                    FROM {table_prod} p
                    LEFT JOIN plan_produkcji plan ON p.plan_id = plan.id
                    WHERE p.id = %s AND p.status = 'do_przyjecia'
                """
                if linia == 'AGRO':
                    query = f"""
                        SELECT p.*, plan.produkt as produkt_nazwa, plan.data_planu
                        FROM {table_prod} p
                        LEFT JOIN plan_produkcji_agro plan ON p.plan_id = plan.id
                        WHERE p.id = %s AND p.status = 'do_przyjecia'
                    """
                
                cursor.execute(query, (pallet_id,))
                pallet = cursor.fetchone()
                if not pallet:
                    return False, "Nie znaleziono palety lub jest już przyjęta."

                try:
                    confirmed_netto = float(confirmed_weight) if confirmed_weight is not None else float(pallet.get('waga') or 0)
                except (TypeError, ValueError):
                    confirmed_netto = float(pallet.get('waga') or 0)

                if confirmed_netto <= 0:
                    return False, "Brak poprawnej wagi netto palety do przyjęcia."

                # 2. Update production table status
                cursor.execute(
                    f"UPDATE {table_prod} SET status = 'w_magazynie', data_potwierdzenia = %s, waga_potwierdzona = %s WHERE id = %s",
                    (datetime.now(), confirmed_netto, pallet_id),
                )
                
                # 3. Insert into warehouse table
                # Check if record already exists (some logic might have inserted it earlier)
                fk_col = 'paleta_workowanie_id'
                cursor.execute(f"SELECT id FROM {table_wh} WHERE {fk_col} = %s", (pallet_id,))
                existing = cursor.fetchone()
                
                if existing:
                    cursor.execute(
                        f"UPDATE {table_wh} SET lokalizacja = %s, data_potwierdzenia = %s, user_login = %s, waga_netto = %s WHERE id = %s",
                        (lokalizacja, datetime.now(), login, confirmed_netto, existing['id']),
                    )
                else:
                    cursor.execute(f"""
                        INSERT INTO {table_wh} 
                        ({fk_col}, plan_id, data_planu, produkt, waga_netto, waga_brutto, tara, lokalizacja, user_login, nr_palety)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (pallet_id, 
                          pallet.get('plan_id'), 
                          pallet.get('data_planu'), 
                          pallet.get('produkt_nazwa') or pallet.get('produkt') or '', 
                          confirmed_netto, 
                          float(pallet.get('waga_brutto') or 0), 
                          float(pallet.get('tara') or 0), 
                          lokalizacja, login, 
                          pallet.get('nr_palety')))

                # 4. Log history
                cursor.execute("""
                    INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login)
                    VALUES (%s, %s, 'wyrob_gotowy', 'PRZYJECIE_WG', 'LINIA', %s, %s, %s)
                """, (pallet_id, linia, lokalizacja, f"Przyjęcie WG: {pallet['produkt_nazwa']}", login))

                conn.commit()
                
                # --- AUTO DRUKOWANIE RAPORTU BIUROWEGO PO PRZYJĘCIU OSTATNIEJ PALETY ---
                try:
                    plan_id = pallet.get('plan_id')
                    if plan_id:
                        if linia == 'AGRO':
                            # Check if plan is 'zakonczone'
                            cursor.execute("SELECT status FROM plan_produkcji_agro WHERE id = %s", (plan_id,))
                            plan_status_row = cursor.fetchone()
                            if plan_status_row and plan_status_row.get('status') == 'zakonczone':
                                # Count total pallets and received pallets
                                cursor.execute("SELECT COUNT(*) as total FROM palety_agro WHERE plan_id = %s", (plan_id,))
                                total_pallets = cursor.fetchone()['total']
                                
                                cursor.execute("SELECT COUNT(*) as received FROM palety_agro WHERE plan_id = %s AND status = 'w_magazynie'", (plan_id,))
                                received_pallets = cursor.fetchone()['received']
                                
                                if total_pallets > 0 and total_pallets == received_pallets:
                                    from app.services.office_print_service import trigger_office_print
                                    print(f"Wszystkie {total_pallets} palet dla zlecenia AGRO {plan_id} zostały przyjęte. Uruchamiam druk raportu.")
                                    trigger_office_print(plan_id, typ_raportu='raport_palet_agro')
                                    
                        elif linia == 'PSD':
                            cursor.execute("SELECT status FROM plan_produkcji WHERE id = %s", (plan_id,))
                            plan_status_row = cursor.fetchone()
                            if plan_status_row and plan_status_row.get('status') == 'zakonczone':
                                cursor.execute("SELECT COUNT(*) as total FROM palety_workowanie WHERE plan_id = %s", (plan_id,))
                                total_pallets = cursor.fetchone()['total']
                                
                                cursor.execute("SELECT COUNT(*) as received FROM palety_workowanie WHERE plan_id = %s AND status = 'w_magazynie'", (plan_id,))
                                received_pallets = cursor.fetchone()['received']
                                
                                if total_pallets > 0 and total_pallets == received_pallets:
                                    from app.services.office_print_service import trigger_office_print
                                    print(f"Wszystkie {total_pallets} palet dla zlecenia PSD {plan_id} zostały przyjęte. Uruchamiam druk raportu.")
                                    # Assuming there might be a PSD report type later, for now we can just log it or trigger 'raport_palet_psd'
                                    trigger_office_print(plan_id, typ_raportu='raport_palet_psd')
                except Exception as pe:
                    print(f"Błąd przy próbie automatycznego wydruku raportu biurowego: {pe}")
                # --- KONIEC AUTO DRUKOWANIA RAPORTU ---

                return True, "Paleta została przyjęta do magazynu."
            except Exception as e:
                return False, str(e)
            finally:
                conn.close()
