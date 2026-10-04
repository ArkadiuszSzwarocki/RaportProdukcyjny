# cspell:words putaway sscc
from app.db import get_db_connection, get_table_name
import json
import math
from datetime import datetime
import uuid
import re
from app.utils.pallet_id import generate_pallet_id
from app.utils.location_validator import validate_warehouse_location, is_production_tank_code, normalize_warehouse_location

from app.services.magazyn_dostawy.location_service import LocationService
from app.services.warehouse_history.movement_recorder import MovementRecorder

class AcceptanceResult(tuple):
    def __new__(cls, success, message, open_report_url=None, plan_id=None, is_last_pallet=False):
        return super().__new__(cls, (success, message))
    
    def __init__(self, success, message, open_report_url=None, plan_id=None, is_last_pallet=False):
        self.success = success
        self.message = message
        self.open_report_url = open_report_url
        self.plan_id = plan_id
        self.is_last_pallet = is_last_pallet

class AcceptanceService:

    @staticmethod
    def accept_item(dostawa_id, item_id, lokalizacja, login='system', nr_partii=None, data_produkcji=None, data_przydatnosci=None, printer_ip=None, printer_name=None, expected_status=None, strict_putaway=False):
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
                cursor.execute("SELECT * FROM magazyn_dostawy WHERE id = %s FOR UPDATE", (dostawa_id,))
                dostawa = cursor.fetchone()
                if not dostawa: return False, "Nie znaleziono przesunięcia", None
                actual_status = str(dostawa.get('status') or '').upper()
                if expected_status and actual_status != expected_status:
                    return False, 'Status dostawy zmienił się. Odśwież odbiór.', None
                if actual_status in ('SZKIC','AWIZOWANE','W_STREFIE_PRZYJEC'):
                    return False, 'Najpierw zakończ przygotowanie dostawy i rozpocznij rozlokowanie.', None
                if str(dostawa.get('status') or '').upper() in ('CANCELLED', 'COMPLETED'):
                    return False, "Nie można przyjmować pozycji zamkniętego przesunięcia", None

                lokalizacja = normalize_warehouse_location(lokalizacja) or str(lokalizacja or '').strip().upper()
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
                if actual_status == 'PUTAWAY_IN_PROGRESS' and strict_putaway:
                    suggested = target.get('putaway_suggested_location')
                    from app.services.magazyn_dostawy.commands.putaway_suggestion_service import PutawaySuggestionService
                    valid, error = PutawaySuggestionService.validate_putaway_location(lokalizacja, suggested, strict_mode=True)
                    if not valid:
                        return False, error, None


                source_spot = str(target.get('sourceSpot') or '').strip().upper()
                if not source_spot:
                    fallback_source = str(dostawa.get('lokalizacja_z') or '').strip().upper()
                    if fallback_source and fallback_source != 'WIELE':
                        source_spot = fallback_source
                supplier = str(dostawa.get('supplier') or '').strip()
                is_external = bool(supplier) or source_spot == 'DOSTAWA' or str(dostawa.get('lokalizacja_z') or '').strip().upper() == 'DOSTAWA'
                is_manual = target.get('is_manual', False) or target.get('warehouseLookupSkipped', False)
                if not is_external:
                    destination = normalize_warehouse_location(target.get('targetSpot') or dostawa.get('lokalizacja_do'))
                    # An open live movement receives its actual rack at scan time.
                    if destination and destination != lokalizacja:
                        return False, f'Paleta jest przeznaczona do {destination}. Nie można przyjąć jej na {lokalizacja}.', None
                if not is_manual and source_spot and source_spot == lokalizacja:
                    return False, f"Nie można przyjąć na tę samą lokalizację ({lokalizacja}), z której przyjmujesz.", None

                table_sur = get_table_name('magazyn_surowce', linia)
                table_opk = get_table_name('magazyn_opakowania', linia)
                table_got = get_table_name('magazyn_palety', linia)

                # Internal transfers resolve a pallet across both production
                # lines. Keep the exact table found by that lookup; rebuilding
                # it from dostawa.linia can update a different row with the
                # same numeric id and leave the real pallet in OCZEKUJĄCE.
                source_table_hint = str(target.get('sourceTable') or '').strip()
                # Surowce są wspólne dla PSD i AGRO. Nie ma osobnej tabeli
                # magazyn_agro_surowce — linia dokumentu nie może zmieniać
                # tabeli surowców.
                allowed_sur = {'magazyn_surowce'}
                allowed_opk = {'magazyn_opakowania', 'magazyn_agro_opakowania'}
                allowed_got = {'magazyn_palety', 'magazyn_palety_agro'}
                if source_table_hint in allowed_sur:
                    table_sur = source_table_hint
                elif source_table_hint in allowed_opk:
                    table_opk = source_table_hint
                elif source_table_hint in allowed_got:
                    table_got = source_table_hint

                product_name = target.get('productName') or 'Brak nazwy'
                p_type_scanned = str(target.get('scannedType') or target.get('type') or '').strip().lower()
                pkg_form_raw = str(target.get('packageForm') or '').strip().lower()
                unit_raw = str(target.get('unit') or '').strip().lower()
                is_opk_pkg = pkg_form_raw in ('packaging', 'tasma', 'taśma', 'karton') or unit_raw == 'szt' or p_type_scanned == 'opakowanie'

                # Resolve legacy/inconsistent documents by the physical SSCC
                # (or source id), not by the document line. This prevents an
                # AGRO/ALL document from updating a PSD row with the same id.
                source_identity = target.get('sourcePalletNo') or target.get('nr_palety') or target.get('sourcePalletId')
                if source_identity and not source_table_hint:
                    if p_type_scanned in ('wyrob_gotowy', 'wyrób gotowy', 'wyrob gotowy', 'magazyn', 'produkcja'):
                        table_candidates, qty_column = sorted(allowed_got), 'waga_netto'
                    elif is_opk_pkg:
                        table_candidates, qty_column = sorted(allowed_opk), 'stan_magazynowy'
                    else:
                        table_candidates, qty_column = sorted(allowed_sur), 'stan_magazynowy'

                    found_tables = []
                    for candidate in table_candidates:
                        try:
                            if str(source_identity).isdigit():
                                cursor.execute(
                                    f"SELECT id FROM {candidate} WHERE (id = %s OR nr_palety = %s) AND {qty_column} > 0 LIMIT 1",
                                    (int(source_identity), str(source_identity)),
                                )
                            else:
                                cursor.execute(
                                    f"SELECT id FROM {candidate} WHERE nr_palety = %s AND {qty_column} > 0 LIMIT 1",
                                    (str(source_identity),),
                                )
                            if cursor.fetchone():
                                found_tables.append(candidate)
                        except Exception:
                            continue

                    if len(found_tables) > 1:
                        return False, f"SSCC {target.get('sourcePalletNo') or target.get('nr_palety') or source_identity} występuje w wielu aktywnych tabelach magazynowych.", None
                    if len(found_tables) == 1:
                        source_table_hint = found_tables[0]
                        if source_table_hint in allowed_sur:
                            table_sur = source_table_hint
                        elif source_table_hint in allowed_opk:
                            table_opk = source_table_hint
                        elif source_table_hint in allowed_got:
                            table_got = source_table_hint

                # Reuse existing nr_palety if this was a transfer, otherwise generate new
                nr_palety = target.get('nr_palety') or generate_pallet_id(linia, type=('opakowanie' if is_opk_pkg else 'surowiec'))
                if pkg_form_raw in ('tasma', 'taśma') or 'taśm' in product_name.lower() or 'tasm' in product_name.lower():
                    pkg_form = 'Taśma'
                elif pkg_form_raw == 'karton':
                    pkg_form = 'Karton'
                elif pkg_form_raw == 'packaging':
                    pkg_form = 'Opakowanie'
                else:
                    pkg_form = target.get('packageForm', 'bags') # bags or big_bag
                nr_partii = nr_partii or target.get('nr_partii') or None
                data_produkcji = data_produkcji or _clean_date(target.get('data_produkcji'))
                data_przydatnosci = data_przydatnosci or _clean_date(target.get('data_przydatnosci'))

                open_locations = ['MS01', 'MP01', 'MD01', 'MOP01', 'BF_MS01', 'BF_MP01', 'BFMS01', 'BFMP01', 'BFOS', 'MDM01', 'PSD01', 'MGW01', 'MGW02', 'OSIP', 'KO01', 'RAMPA', 'MIX01', 'W_TRANZYCIE_OSIP', 'PSD', 'R09']
                is_open = any(lokalizacja.upper().startswith(ol) for ol in open_locations)

                if not is_open:
                    from app.utils.location_validator import is_rack_location, check_rack_location_availability
                    if is_rack_location(lokalizacja):
                        is_avail, err_msg = check_rack_location_availability(
                            lokalizacja,
                            current_nr_palety=nr_palety,
                            product_name=product_name, cursor=cursor
                        )
                        if not is_avail:
                            return False, err_msg, None
                    else:
                        cursor.execute(f"SELECT 1 FROM {table_sur} WHERE lokalizacja = %s AND stan_magazynowy > 0 AND (nr_palety IS NULL OR nr_palety != %s)", (lokalizacja, nr_palety))
                        if cursor.fetchone(): return False, f"Lokalizacja {lokalizacja} zajęta w surowcach!", None
                        cursor.execute(f"SELECT 1 FROM {table_opk} WHERE lokalizacja = %s AND stan_magazynowy > 0 AND (nr_palety IS NULL OR nr_palety != %s)", (lokalizacja, nr_palety))
                        if cursor.fetchone(): return False, f"Lokalizacja {lokalizacja} zajęta w opakowaniach!", None
                        cursor.execute(f"SELECT 1 FROM magazyn_dodatki WHERE lokalizacja = %s AND stan_magazynowy > 0 AND (nr_palety IS NULL OR nr_palety != %s)", (lokalizacja, nr_palety))
                        if cursor.fetchone(): return False, f"Lokalizacja {lokalizacja} zajęta w dodatkach!", None
                        cursor.execute(f"SELECT 1 FROM {table_got} WHERE lokalizacja = %s AND waga_netto > 0 AND (nr_palety IS NULL OR nr_palety != %s)", (lokalizacja, nr_palety))
                        if cursor.fetchone(): return False, f"Lokalizacja {lokalizacja} zajęta w wyrobach gotowych!", None

                pallet_id = None
                source_pallet_id = target.get('sourcePalletId')

                raw_qty = target.get('unitsPerPallet') or target.get('quantity') or target.get('netWeight') or target.get('ilosc') or 0
                qty = float(raw_qty) if raw_qty else 0.0
                if not math.isfinite(qty) or (is_external and qty <= 0):
                    return False, 'Ilość przyjęcia musi być dodatnia i skończona.', None

                if is_opk_pkg:
                    cursor.execute(f"SELECT id FROM {table_opk} WHERE nr_palety = %s LIMIT 1", (nr_palety,))
                    exist_opk = cursor.fetchone()
                    if not exist_opk and is_external and source_pallet_id:
                        cursor.execute(f"SELECT id FROM {table_opk} WHERE id = %s LIMIT 1", (source_pallet_id,))
                        exist_opk = cursor.fetchone()
                    if exist_opk:
                        pallet_id = exist_opk['id']
                        cursor.execute(f"""
                            UPDATE {table_opk}
                            SET stan_magazynowy = %s, lokalizacja = %s, nazwa = %s, nr_partii = %s,
                                data_produkcji = %s, data_przydatnosci = %s, nr_palety = %s,
                                typ_opakowania = %s, updated_at = NOW()
                            WHERE id = %s
                        """, (qty, lokalizacja, product_name, nr_partii, data_produkcji, data_przydatnosci, nr_palety, pkg_form, pallet_id))
                    else:
                        cursor.execute(f"INSERT INTO {table_opk} (nazwa, stan_magazynowy, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, nr_palety, typ_opakowania) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", (product_name, qty, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, nr_palety, pkg_form))
                        pallet_id = cursor.lastrowid
                    p_type = 'opakowanie'
                elif p_type_scanned == 'dodatek':
                    cursor.execute(f"INSERT INTO magazyn_dodatki (nazwa, stan_magazynowy, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, nr_palety, typ_opakowania, linia) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE stan_magazynowy = VALUES(stan_magazynowy), nazwa = VALUES(nazwa), nr_partii = VALUES(nr_partii), data_produkcji = VALUES(data_produkcji), data_przydatnosci = VALUES(data_przydatnosci), nr_palety = VALUES(nr_palety), typ_opakowania = VALUES(typ_opakowania), lokalizacja = VALUES(lokalizacja)", (product_name, qty, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, nr_palety, pkg_form, linia))
                    pallet_id = cursor.lastrowid
                    if not pallet_id or pallet_id == 0:
                        cursor.execute(f"SELECT id FROM magazyn_dodatki WHERE nr_palety = %s LIMIT 1", (nr_palety,))
                        _row = cursor.fetchone()
                        if _row: pallet_id = _row['id']
                    p_type = 'dodatek'
                elif p_type_scanned in ['wyrob_gotowy', 'magazyn', 'produkcja']:
                    p_type = 'wyrob_gotowy'
                    source_pid = target.get('sourcePalletId')
                    exist_got = None
                    if source_pid:
                        cursor.execute(f"SELECT id FROM {table_got} WHERE id = %s LIMIT 1", (source_pid,))
                        exist_got = cursor.fetchone()
                    if not exist_got and nr_palety:
                        cursor.execute(f"SELECT id FROM {table_got} WHERE nr_palety = %s LIMIT 1", (nr_palety,))
                        exist_got = cursor.fetchone()

                    if exist_got:
                        pallet_id = exist_got['id']
                        cursor.execute(f"""
                            UPDATE {table_got}
                            SET lokalizacja = %s, waga_netto = %s
                            WHERE id = %s
                        """, (lokalizacja, qty, pallet_id))
                    else:
                        target_linia = linia if linia in ['PSD', 'AGRO'] else 'PSD'
                        cursor.execute(f"""
                            INSERT INTO {table_got} (nr_palety, produkt, waga_netto, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, is_blocked, is_loaded, linia)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, 0, 0, %s)
                        """, (nr_palety, product_name, qty, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, target_linia))
                        pallet_id = cursor.lastrowid
                else:
                    p_type = 'surowiec'
                    from app.utils.surowiec_validator import is_valid_surowiec
                    if not is_valid_surowiec(product_name):
                        return False, f"Surowiec '{product_name}' nie występuje w słowniku surowców. Nie można go przyjąć.", None
                    # Sprawdź, czy rekord palety już istnieje (np. utworzony w OCZEKUJĄCYCH lub podczas zwrotu)
                    cursor.execute(f"SELECT id, stan_magazynowy FROM {table_sur} WHERE nr_palety = %s LIMIT 1", (nr_palety,))
                    exist_sur = cursor.fetchone()
                    if not exist_sur and is_external and source_pallet_id:
                        cursor.execute(f"SELECT id, stan_magazynowy FROM {table_sur} WHERE id = %s LIMIT 1", (source_pallet_id,))
                        exist_sur = cursor.fetchone()
                    if exist_sur:
                        pallet_id = exist_sur['id']
                        if qty <= 0 and float(exist_sur.get('stan_magazynowy') or 0) > 0:
                            qty = float(exist_sur['stan_magazynowy'])
                        cursor.execute(f"""
                            UPDATE {table_sur}
                            SET stan_magazynowy = %s, lokalizacja = %s, nazwa = %s, nr_partii = %s,
                                data_produkcji = %s, data_przydatnosci = %s, nr_palety = %s, typ_opakowania = %s,
                                updated_at = NOW()
                            WHERE id = %s
                        """, (qty, lokalizacja, product_name, nr_partii, data_produkcji, data_przydatnosci, nr_palety, pkg_form, pallet_id))
                    else:
                        cursor.execute(f"INSERT INTO {table_sur} (nazwa, stan_magazynowy, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, nr_palety, typ_opakowania) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE stan_magazynowy = VALUES(stan_magazynowy), nazwa = VALUES(nazwa), nr_partii = VALUES(nr_partii), data_produkcji = VALUES(data_produkcji), data_przydatnosci = VALUES(data_przydatnosci), nr_palety = VALUES(nr_palety), typ_opakowania = VALUES(typ_opakowania), lokalizacja = VALUES(lokalizacja)", (product_name, qty, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, nr_palety, pkg_form))
                        pallet_id = cursor.lastrowid

                # Get the ID of the pallet (new or existing) if not resolved yet
                if not pallet_id or pallet_id == 0:
                    table_name = table_opk if p_type == 'opakowanie' else ('magazyn_dodatki' if p_type == 'dodatek' else (table_got if p_type == 'wyrob_gotowy' else table_sur))
                    col_st = 'waga_netto' if p_type == 'wyrob_gotowy' else 'stan_magazynowy'
                    cursor.execute(f"SELECT id FROM {table_name} WHERE lokalizacja = %s AND {col_st} > 0 LIMIT 1", (lokalizacja,))
                    p_row = cursor.fetchone()
                    pallet_id = p_row['id'] if p_row else None

                # Persist the resolved physical table with the item. Future
                # retries/putaway confirmations must use the same source and
                # must not infer it from the document line.
                target['sourceTable'] = (
                    table_opk if p_type == 'opakowanie' else
                    ('magazyn_dodatki' if p_type == 'dodatek' else
                     (table_got if p_type == 'wyrob_gotowy' else table_sur))
                )
                target['sourcePalletId'] = pallet_id
                if actual_status == 'PUTAWAY_IN_PROGRESS':
                    target['putaway_confirmed_location'] = lokalizacja
                    target['putaway_confirmed_by'] = login
                    target['putaway_confirmed_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    target['pallet_status'] = 'STORED'
                target['accepted'] = True
                target['accepted_by'] = login
                target['accepted_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                target['lokalizacja_przyjecia'] = lokalizacja
                target['nr_partii'] = nr_partii
                target['nr_palety'] = nr_palety
                target['data_produkcji'] = data_produkcji
                target['data_przydatnosci'] = data_przydatnosci

                # Zwalniamy blokadę dla przyjętej palety źródłowej i nowej palety (dla obu linii PSD i AGRO)
                from app.services.magazyn_dostawy.commands.pallet_lock_manager import PalletLockManager
                PalletLockManager.set_pallets_blocked(cursor, [target], 0, exclude_delivery_id=dostawa_id)

                # 3. Empty the source spot ONLY for internal transfers where source pallet is a SEPARATE row
                source_spot = str(target.get('sourceSpot') or '').strip().upper()
                is_partial = target.get('is_partial', False)
                is_return = target.get('is_return', False)
                if not is_external and source_spot and not is_partial and not is_return:
                    source_table = source_table_hint or (table_opk if is_opk_pkg else
                        (table_got if p_type == 'wyrob_gotowy' else
                         ('magazyn_dodatki' if p_type == 'dodatek' else table_sur)))
                    source_quantity = 'waga_netto' if source_table in allowed_got else 'stan_magazynowy'
                    # Numeric ids belong to one physical table, never to every stock table.
                    if source_pallet_id and str(source_pallet_id) != str(pallet_id):
                        cursor.execute(f"UPDATE {source_table} SET {source_quantity}=0 WHERE id=%s AND lokalizacja=%s",
                                       (source_pallet_id, source_spot))
                    elif not source_pallet_id and source_spot != lokalizacja:
                        source_name = 'produkt' if source_table in allowed_got else 'nazwa'
                        cursor.execute(f"SELECT id FROM {source_table} WHERE lokalizacja=%s AND {source_name}=%s AND {source_quantity}>0 FOR UPDATE",
                                       (source_spot, product_name))
                        sources = cursor.fetchall()
                        if len(sources) > 1:
                            raise ValueError('Wiele palet w lokalizacji źródłowej. Wskaż dokładny kod palety.')
                        if sources:
                            cursor.execute(f"UPDATE {source_table} SET {source_quantity}=0 WHERE id=%s", (sources[0]['id'],))
                
                # Log to palety_historia
                action_name = 'PRZYJECIE_ZWROT' if is_return else 'PRZYJECIE'
                comment_text = f"Przyjęcie zwrotu z produkcji: {product_name} na {lokalizacja}" if is_return else f"Przyjęcie z dostawy: {product_name}, partia: {nr_partii}"
                operation_id = f"delivery:{dostawa_id}:item:{item_id}:accept"
                history_saved = MovementRecorder.record_movement(
                    pallet_id, linia, p_type, action_name,
                    source_spot or 'OCZEKUJACE', lokalizacja, comment_text, login,
                    nr_palety,
                    cursor=cursor,
                    connection=conn,
                    event_id=str(uuid.uuid5(uuid.NAMESPACE_URL, operation_id)),
                    operation_id=operation_id,
                    quantity_after=qty,
                )
                if not history_saved:
                    raise RuntimeError("Nie udało się zapisać historii przyjęcia palety")

                all_processed = all(i.get('accepted') or i.get('rejected') for i in items)
                new_status = 'COMPLETED' if all_processed and dostawa.get('supplier') else ('PUTAWAY_IN_PROGRESS' if actual_status == 'PUTAWAY_IN_PROGRESS' else 'OCZEKUJE')

                cursor.execute(
                    """
                    UPDATE magazyn_dostawy 
                    SET items=%s, status=%s, potwierdzone_przez=%s, potwierdzone_at=%s 
                    WHERE id=%s
                    """,
                    (
                        json.dumps(items),
                        new_status,
                        login if all_processed else dostawa.get('potwierdzone_przez'),
                        datetime.now() if all_processed else dostawa.get('potwierdzone_at'),
                        dostawa_id
                    )
                )
                conn.commit()
                
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
                            "copies": 2,
                            "dane": {
                                "palletData": {
                                    "nrPalety": nr_palety,
                                    "productName": product_name,
                                    "batchNumber": nr_partii or '---',
                                    "productionDate": str(data_produkcji) if data_produkcji else '---',
                                    "expiryDate": str(data_przydatnosci) if data_przydatnosci else '---',
                                    "currentWeight": qty,
                                    "labNotes": "Dostawa Przyjęta",
                                    "copies": 2
                                }
                            }
                        }
                        def run_print():
                            url = "http://127.0.0.1:3001/drukuj-zpl"
                            try:
                                requests.post(url, json=payload, verify=False, timeout=5)
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

    @staticmethod
    def confirm_moved_pallet(cursor, connection, number, location, login):
        """Confirm a full physical move in the same transaction as its stock."""
        from app.services.magazyn_dostawy.commands.pallet_lock_manager import PalletLockManager
        number = str(number or '').strip().upper()
        if not number:
            return
        cursor.execute("SELECT id,items FROM magazyn_dostawy WHERE status IN ('OCZEKUJE','IN_PROGRESS') FOR UPDATE")
        matched = []
        for delivery in cursor.fetchall():
            items = json.loads(delivery.get('items') or '[]')
            pending = [item for item in items if
                       str(item.get('nr_palety') or item.get('sourcePalletNo') or '').strip().upper() == number
                       and not (item.get('accepted') or item.get('rejected'))]
            if pending:
                matched.append((delivery, items, pending))
        if sum(len(pending) for _, _, pending in matched) > 1:
            raise ValueError('Paleta pasuje do wielu pozycji przyjęcia; wybierz konkretny dokument')
        for delivery, items, _ in matched:
            changed, received = False, []
            for item in items:
                nr = str(item.get('nr_palety') or item.get('sourcePalletNo') or '').strip().upper()
                if nr == number and not (item.get('accepted') or item.get('rejected')):
                    item.update(accepted=True,accepted_by=login,
                                accepted_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                lokalizacja_przyjecia=location)
                    received.append(item)
                    changed = True
            if not changed:
                continue
            complete = bool(items) and all(item.get('accepted') or item.get('rejected') for item in items)
            cursor.execute("UPDATE magazyn_dostawy SET items=%s,status=%s, "
                           "potwierdzone_przez=IF(%s,%s,potwierdzone_przez), "
                           "potwierdzone_at=IF(%s,NOW(),potwierdzone_at) WHERE id=%s",
                           (json.dumps(items),'OCZEKUJE',
                            complete,login,complete,delivery['id']))
            PalletLockManager.set_pallets_blocked(cursor,received,0,exclude_delivery_id=delivery['id'])

    @staticmethod
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

    @staticmethod
    def reject_item(dostawa_id, item_id, reason='', login='system'):
            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("SELECT * FROM magazyn_dostawy WHERE id = %s FOR UPDATE", (dostawa_id,))
                dostawa = cursor.fetchone()
                if not dostawa:
                    return False, "Nie znaleziono przesunięcia", None
                if str(dostawa.get('status') or '').upper() in ('CANCELLED', 'COMPLETED'):
                    return False, "Nie można odrzucać pozycji zamkniętego przesunięcia", None

                items = json.loads(dostawa.get('items') or '[]')
                target = next((i for i in items if str(i.get('id')) == str(item_id)), None)
                if not target:
                    return False, "Nie znaleziono pozycji", None
                if target.get('accepted'):
                    return False, "Pozycja już przyjęta", None
                if target.get('rejected'):
                    return False, "Pozycja już odrzucona", None

                linia = dostawa['linia']
                source_spot = normalize_warehouse_location(target.get('sourceSpot') or '')
                if not source_spot:
                    fallback_source = normalize_warehouse_location(dostawa.get('lokalizacja_z') or '')
                    if fallback_source != 'WIELE':
                        source_spot = fallback_source
                original_spot = normalize_warehouse_location(target.get('originalSpot') or '')
                pallet_no = str(target.get('sourcePalletNo') or target.get('nr_palety') or '').strip()
                restored = False
                restored_type = None
                pallet_id = None
                if source_spot and original_spot and source_spot != original_spot:
                    from app.services.magazyn_dostawy.commands.internal_transfer_processor import InternalTransferProcessor
                    from app.utils.location_validator import check_rack_location_availability
                    if not pallet_no:
                        raise ValueError('Brak SSCC do bezpiecznego cofnięcia odrzuconej palety')
                    row, restored_type, table = InternalTransferProcessor._find_active_pallet_by_sscc(cursor, pallet_no, linia)
                    if not row:
                        raise ValueError(f'Nie znaleziono aktywnej palety {pallet_no}')
                    pallet_id = row['id']
                    if normalize_warehouse_location(row.get('lokalizacja') or '') == source_spot:
                        available, error = check_rack_location_availability(
                            original_spot, current_nr_palety=pallet_no,
                            product_name=row.get('nazwa') or row.get('produkt'), cursor=cursor)
                        if not available:
                            raise ValueError(error)
                        quantity_column = 'waga_netto' if restored_type == 'wyrob_gotowy' else 'stan_magazynowy'
                        cursor.execute(f'UPDATE {table} SET lokalizacja=%s WHERE id=%s AND nr_palety=%s '
                                       f'AND lokalizacja=%s AND {quantity_column}>0',
                                       (original_spot, pallet_id, row['nr_palety'], source_spot))
                        restored = cursor.rowcount == 1

                normalized_reason = str(reason or '').strip() or 'Brak palety do przyjęcia'
                target['rejected'] = True
                target['rejected_by'] = login
                target['rejected_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                target['rejected_reason'] = normalized_reason
                # Zwalniamy blokadę dla odrzuconej palety
                from app.services.magazyn_dostawy.commands.pallet_lock_manager import PalletLockManager
                PalletLockManager.set_pallets_blocked(cursor, [target], 0, exclude_delivery_id=dostawa_id)

                if restored:
                    cursor.execute(
                        "INSERT INTO palety_historia (paleta_id, nr_palety, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login) VALUES (%s, %s, %s, %s, 'TRANSFER_REJECT_ITEM', %s, %s, %s, %s)",
                        (pallet_id, pallet_no, linia, restored_type, source_spot, original_spot, f"Odrzucenie pozycji: {normalized_reason}", login)
                    )

                all_processed = all(i.get('accepted') or i.get('rejected') for i in items)
                new_status = 'COMPLETED' if all_processed and dostawa.get('supplier') else 'OCZEKUJE'

                cursor.execute(
                    """
                    UPDATE magazyn_dostawy 
                    SET items=%s, status=%s, potwierdzone_przez=%s, potwierdzone_at=%s 
                    WHERE id=%s
                    """,
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
                conn.rollback()
                return False, str(e), None
            finally:
                conn.close()

    @staticmethod
    def accept_production_pallet(pallet_id, lokalizacja, linia='PSD', login='system', confirmed_weight=None):
            """Moves a production pallet (WG) from 'do_przyjecia' to warehouse inventory with robust cross-line detection."""
            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                
                lokalizacja = str(lokalizacja or '').strip().upper()
                if not lokalizacja:
                    return False, "Podaj docelową lokalizację palety."

                pallet_id_str = str(pallet_id or '').strip()
                pallet_id_int = int(pallet_id_str) if pallet_id_str.isdigit() else None
                pallet_nr_str = pallet_id_str.upper()

                # Kolejność sprawdzania linii
                req_line = str(linia or 'PSD').strip().upper()
                if pallet_nr_str.startswith('AGR'):
                    lines_to_try = ['AGRO', 'PSD']
                elif pallet_nr_str.startswith('PSD'):
                    lines_to_try = ['PSD', 'AGRO']
                elif req_line == 'AGRO':
                    lines_to_try = ['AGRO', 'PSD']
                else:
                    lines_to_try = ['PSD', 'AGRO']

                pallet = None
                matched_line = None
                table_prod = None
                table_wh = None

                # 1. Szukaj w statusie 'do_przyjecia' (lub oczekującym)
                for try_line in lines_to_try:
                    t_prod = 'palety_workowanie' if try_line == 'PSD' else 'palety_agro'
                    t_wh = 'magazyn_palety'
                    t_plan = 'plan_produkcji' if try_line == 'PSD' else 'plan_produkcji_agro'

                    where_clauses = ["p.nr_palety = %s"]
                    params = [pallet_nr_str]
                    if pallet_id_int is not None:
                        where_clauses.append("p.id = %s")
                        params.append(pallet_id_int)

                    query = f"""
                        SELECT p.*, plan.produkt as produkt_nazwa, plan.data_planu
                        FROM {t_prod} p
                        LEFT JOIN {t_plan} plan ON p.plan_id = plan.id
                        WHERE ({' OR '.join(where_clauses)})
                          AND (p.status = 'do_przyjecia' OR p.status IS NULL OR p.status = '')
                        ORDER BY p.id DESC LIMIT 1
                    """
                    cursor.execute(query, tuple(params))
                    p_row = cursor.fetchone()
                    if p_row:
                        pallet = p_row
                        matched_line = try_line
                        table_prod = t_prod
                        table_wh = t_wh
                        break

                # 1b. Fallback: jeśli nie znaleziono ze statusem 'do_przyjecia', sprawdź czy paleta istnieje
                if not pallet:
                    for try_line in lines_to_try:
                        t_prod = 'palety_workowanie' if try_line == 'PSD' else 'palety_agro'
                        t_wh = 'magazyn_palety'
                        t_plan = 'plan_produkcji' if try_line == 'PSD' else 'plan_produkcji_agro'

                        where_clauses = ["p.nr_palety = %s"]
                        params = [pallet_nr_str]
                        if pallet_id_int is not None:
                            where_clauses.append("p.id = %s")
                            params.append(pallet_id_int)

                        query = f"""
                            SELECT p.*, plan.produkt as produkt_nazwa, plan.data_planu
                            FROM {t_prod} p
                            LEFT JOIN {t_plan} plan ON p.plan_id = plan.id
                            WHERE ({' OR '.join(where_clauses)})
                            ORDER BY p.id DESC LIMIT 1
                        """
                        cursor.execute(query, tuple(params))
                        p_row = cursor.fetchone()
                        if p_row:
                            if p_row.get('status') in ('w_magazynie', 'przyjeta'):
                                return False, f"Paleta {p_row.get('nr_palety') or pallet_id} została już wcześniej przyjęta do magazynu."
                            pallet = p_row
                            matched_line = try_line
                            table_prod = t_prod
                            table_wh = t_wh
                            break

                if not pallet:
                    return False, f"Nie znaleziono palety wyrobu gotowego: {pallet_id}."

                actual_pallet_id = pallet['id']
                linia = matched_line

                try:
                    confirmed_netto = float(confirmed_weight) if confirmed_weight is not None else float(pallet.get('waga') or 0)
                except (TypeError, ValueError):
                    confirmed_netto = float(pallet.get('waga') or 0)

                if confirmed_netto <= 0:
                    return False, "Brak poprawnej wagi netto palety do przyjęcia."

                # 2. Update production table status
                cursor.execute(
                    f"UPDATE {table_prod} SET status = 'w_magazynie', data_potwierdzenia = %s, waga_potwierdzona = %s, potwierdzil_login = %s WHERE id = %s",
                    (datetime.now(), confirmed_netto, login, actual_pallet_id),
                )
                
                # 3. Insert into unified warehouse table
                fk_col = 'paleta_workowanie_id'
                cursor.execute(f"SELECT id FROM magazyn_palety WHERE {fk_col} = %s AND linia = %s", (actual_pallet_id, linia))
                existing = cursor.fetchone()
                
                if existing:
                    cursor.execute(
                        "UPDATE magazyn_palety SET lokalizacja = %s, data_potwierdzenia = %s, user_login = %s, waga_netto = %s, linia = %s WHERE id = %s",
                        (lokalizacja, datetime.now(), login, confirmed_netto, linia, existing['id']),
                    )
                else:
                    cursor.execute(f"""
                        INSERT INTO magazyn_palety 
                        ({fk_col}, plan_id, data_planu, produkt, waga_netto, waga_brutto, tara, lokalizacja, user_login, nr_palety, linia)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (actual_pallet_id, 
                          pallet.get('plan_id'), 
                          pallet.get('data_planu'), 
                          pallet.get('produkt_nazwa') or pallet.get('produkt') or '', 
                          confirmed_netto, 
                          float(pallet.get('waga_brutto') or 0), 
                          float(pallet.get('tara') or 0), 
                          lokalizacja, login, 
                          pallet.get('nr_palety'),
                          linia))

                # 4. Log history
                cursor.execute("""
                    INSERT INTO palety_historia (paleta_id, linia, typ_palety, akcja, lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login)
                    VALUES (%s, %s, 'wyrob_gotowy', 'PRZYJECIE_WG', 'OCZEKUJĄCE', %s, %s, %s)
                """, (actual_pallet_id, linia, lokalizacja, f"Przyjęcie WG z OCZEKUJĄCE: {pallet.get('produkt_nazwa') or pallet.get('produkt') or ''}", login))

                conn.commit()
                
                # --- AUTO DRUKOWANIE RAPORTU BIUROWEGO I OTWARCIE RAPORTU DLA MAGAZYNIERA ---
                open_report_url = None
                is_last_pallet = False
                try:
                    plan_id = pallet.get('plan_id')
                    if plan_id:
                        if linia == 'AGRO':
                            # Check if plan is 'zakonczone'
                            cursor.execute("SELECT status, sekcja FROM plan_produkcji_agro WHERE id = %s", (plan_id,))
                            plan_status_row = cursor.fetchone()
                            if plan_status_row:
                                plan_st = str(plan_status_row.get('status') or '').strip().lower()
                                if plan_st in ('zakonczone', 'zakończone', 'zakonczony', 'zakończony'):
                                    # Count total pallets and received pallets
                                    cursor.execute("SELECT COUNT(*) as total FROM palety_agro WHERE plan_id = %s", (plan_id,))
                                    total_pallets = cursor.fetchone()['total']
                                    
                                    cursor.execute("SELECT COUNT(*) as received FROM palety_agro WHERE plan_id = %s AND status IN ('przyjeta', 'w_magazynie')", (plan_id,))
                                    received_pallets = cursor.fetchone()['received']
                                    
                                    if total_pallets > 0 and total_pallets == received_pallets:
                                        is_last_pallet = True
                                        from app.services.office_print_service import trigger_office_print
                                        print(f"Wszystkie {total_pallets} palet dla zlecenia AGRO {plan_id} zostały przyjęte. Uruchamiam druk raportu.")
                                        trigger_office_print(plan_id, typ_raportu='raport_palet_agro')
                                        open_report_url = f"/agro/raport_palet?plan_id={plan_id}&autoprint=1"
                                        
                        elif linia == 'PSD':
                            cursor.execute("SELECT status, sekcja FROM plan_produkcji WHERE id = %s", (plan_id,))
                            plan_status_row = cursor.fetchone()
                            if plan_status_row:
                                plan_st = str(plan_status_row.get('status') or '').strip().lower()
                                if plan_st in ('zakonczone', 'zakończone', 'zakonczony', 'zakończony'):
                                    cursor.execute("SELECT COUNT(*) as total FROM palety_workowanie WHERE plan_id = %s", (plan_id,))
                                    total_pallets = cursor.fetchone()['total']
                                    
                                    cursor.execute("SELECT COUNT(*) as received FROM palety_workowanie WHERE plan_id = %s AND status IN ('przyjeta', 'w_magazynie')", (plan_id,))
                                    received_pallets = cursor.fetchone()['received']
                                    
                                    if total_pallets > 0 and total_pallets == received_pallets:
                                        is_last_pallet = True
                                        from app.services.office_print_service import trigger_office_print
                                        print(f"Wszystkie {total_pallets} palet dla zlecenia PSD {plan_id} zostały przyjęte. Uruchamiam druk raportu.")
                                        # Assuming there might be a PSD report type later, for now we can just log it or trigger 'raport_palet_psd'
                                        trigger_office_print(plan_id, typ_raportu='raport_palet_psd')
                                        open_report_url = f"/warehouse-v2/psd/raport_palet?plan_id={plan_id}&autoprint=1"
                except Exception as pe:
                    print(f"Błąd przy próbie automatycznego wydruku raportu biurowego: {pe}")
                # --- KONIEC AUTO DRUKOWANIA RAPORTU ---

                msg = "Zlecenie zamknięte - przyjęto ostatnią paletę. Raport z produkcji został otwarty do wydruku." if is_last_pallet else "Paleta została przyjęta do magazynu."
                return AcceptanceResult(True, msg, open_report_url=open_report_url, plan_id=plan_id, is_last_pallet=is_last_pallet)
            except Exception as e:
                return False, str(e)
            finally:
                conn.close()
