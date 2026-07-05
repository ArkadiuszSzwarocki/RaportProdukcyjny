import logging
from app.db import get_db_connection, get_table_name
import datetime
import os
import re

def _normalize_tank_code(value):
    normalized = str(value or '').strip().upper()
    return normalized or None

def _classify_tank_zone(tank_code):
    normalized = _normalize_tank_code(tank_code)
    if not normalized:
        return 'BRAK'
    if normalized.startswith('BB'):
        return 'BB'
    if normalized.startswith('MZ'):
        return 'MZ'
    if normalized.startswith('KO'):
        return 'KO'
    return 'INNE'

def _is_additive_material(material_name, material_location=None):
    name = str(material_name or '').upper()
    location = str(material_location or '').upper()
    if location.startswith('DOD'):
        return True
    return bool(_DODATEK_NAME_REGEX.search(name))

def _get_auto_pallet_cooldown_seconds():
    """Return cooldown for auto pallet registration (seconds)."""
    raw_value = os.getenv('AGRO_AUTO_PALLET_COOLDOWN_SECONDS', '0')
    try:
        parsed = float(raw_value)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid AGRO_AUTO_PALLET_COOLDOWN_SECONDS=%r. Falling back to 0s.",
            raw_value,
        )
        return 0.0
    return max(0.0, parsed)

def _select_preferred_printer(cursor):
    """Pick production printer first, then fallback to any active printer."""
    cursor.execute(
        """
        SELECT id, nazwa, ip, lokalizacja
        FROM drukarki
        WHERE aktywna = 1
        ORDER BY
            CASE
                WHEN LOWER(COALESCE(nazwa, '')) LIKE '%zebra produkcja%' THEN 0
                WHEN LOWER(COALESCE(lokalizacja, '')) LIKE '%produk%' THEN 1
                ELSE 2
            END,
            id ASC
        LIMIT 1
        """
    )
    return cursor.fetchone()

def _sanitize_zpl_text(value, max_length=64):
    text = str(value or '')
    text = text.replace('^', ' ').replace('~', ' ')
    text = text.replace('\r', ' ').replace('\n', ' ')
    text = re.sub(r'\s+', ' ', text).strip()
    if max_length and len(text) > max_length:
        return text[:max_length]
    return text

def _format_quantity_label(value):
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return '0'

    if abs(numeric - round(numeric)) < 1e-6:
        return str(int(round(numeric)))
    return f"{numeric:.2f}".rstrip('0').rstrip('.')

class AgroOpakowaniaPlanRepository:
    def get_linked_packaging(plan_id):
            """Get all packaging items linked to a production plan."""
            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("""
                    SELECT ap.id as link_id, ap.opakowanie_id, ap.stan_poczatkowy, ap.stan_koncowy, ap.is_active,
                           o.nazwa, o.stan_magazynowy as current_stan
                    FROM agro_plan_opakowania ap
                    JOIN magazyn_opakowania o ON ap.opakowanie_id = o.id
                    WHERE ap.plan_id = %s AND ap.is_active = TRUE
                    ORDER BY ap.created_at ASC
                """, (plan_id,))
                return cursor.fetchall()
            finally:
                conn.close()

    def get_all_linked_packaging(plan_id):
            """Get ALL packaging items linked to a production plan, active and inactive."""
            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("""
                    SELECT ap.id as link_id, ap.opakowanie_id, ap.stan_poczatkowy, ap.stan_koncowy, ap.is_active,
                           o.nazwa, o.stan_magazynowy as current_stan
                    FROM agro_plan_opakowania ap
                    JOIN magazyn_opakowania o ON ap.opakowanie_id = o.id
                    WHERE ap.plan_id = %s
                    ORDER BY ap.created_at ASC
                """, (plan_id,))
                return cursor.fetchall()
            finally:
                conn.close()

    def _link_to_active_plan(cursor, opakowanie_id, lokalizacja, linia='Agro'):
            """Internal helper to link packaging to active plan if moved to machine."""
            if str(lokalizacja).lower() != 'maszyna' or str(linia).upper() != 'AGRO':
                return
                
            # 1. Find active Workowanie plan
            table_plan = get_table_name('plan_produkcji', linia)
            cursor.execute(f"SELECT id FROM {table_plan} WHERE status='w toku' AND sekcja IN ('Workowanie', 'Czyszczenie') ORDER BY real_start DESC LIMIT 1")
            plan_row = cursor.fetchone()
            if not plan_row:
                return
                
            plan_id = plan_row[0]
            
            # 2. Get current state of packaging
            cursor.execute("SELECT stan_magazynowy FROM magazyn_opakowania WHERE id = %s", (opakowanie_id,))
            opak_row = cursor.fetchone()
            if not opak_row:
                return
            stan_poczatkowy = opak_row[0]
            
            # 3. Check if already linked and active for THIS plan
            cursor.execute("SELECT id FROM agro_plan_opakowania WHERE plan_id = %s AND opakowanie_id = %s AND is_active = TRUE", (plan_id, opakowanie_id))
            if cursor.fetchone():
                return # Already linked
                
            # 4. Link it
            cursor.execute(
                "INSERT INTO agro_plan_opakowania (plan_id, opakowanie_id, stan_poczatkowy, is_active) VALUES (%s, %s, %s, TRUE)",
                (plan_id, opakowanie_id, stan_poczatkowy)
            )

    def link_packaging_to_plan(opakowanie_id, plan_id, ilosc_pobrana=None, user_login=None):
            """Manually link a packaging item to a production plan (confirmed by operator).
            Jeśli podano ilosc_pobrana mniejszą niż aktualny stan_magazynowy, rekord zostanie podzielony.
            Sumuje pozostałe na maszynie opakowania tego samego typu.
            """
            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                
                # 1. Get current state of new packaging
                cursor.execute("SELECT nazwa, stan_magazynowy, lokalizacja FROM magazyn_opakowania WHERE id = %s", (opakowanie_id,))
                new_row = cursor.fetchone()
                if not new_row: return False, "Opakowanie nie istnieje"
                stan_poczatkowy_nowego = float(new_row['stan_magazynowy'])
                nazwa = new_row['nazwa']
                lokalizacja = new_row['lokalizacja']
                
                # Zdobądźmy aktualny licznik MQTT przed pętlą, bo będzie potrzebny do zamykania starych rolek
                mqtt_licznik_start = 0
                try:
                    from app.services.mqtt_service import get_latest_data
                    mqtt_licznik_start = int(get_latest_data().get('counter', 0) or 0)
                except Exception:
                    pass

                # 2. Find any active links for this plan (to close them or carry over)
                cursor.execute("""
                    SELECT ap.id as link_id, ap.opakowanie_id, ap.stan_poczatkowy, o.nazwa, ap.licznik_start
                    FROM agro_plan_opakowania ap
                    JOIN magazyn_opakowania o ON ap.opakowanie_id = o.id
                    WHERE ap.plan_id = %s AND ap.is_active = TRUE
                """, (plan_id,))
                active_links = cursor.fetchall()
                
                carryover_qty = 0.0
                
                for al in active_links:
                    if al['nazwa'] == nazwa:
                        # Zamiast zamykać starą rolkę, po prostu powiększamy pulę aktywnej folii
                        # Licznik start zostaje bez zmian (ten z pierwszej rolki)!
                        # Rejestrujemy tylko zdarzenie WSADZENIE w historii.
                        
                        cursor.execute("SELECT data_planu, produkt FROM plan_produkcji_agro WHERE id = %s", (plan_id,))
                        p_meta = cursor.fetchone() or {'data_planu': None, 'produkt': ''}
                        
                        ilosc_docelowa = float(ilosc_pobrana) if ilosc_pobrana is not None else stan_poczatkowy_nowego
                        
                        c_counter = 0
                        try:
                            from app.services.mqtt_service import get_latest_data
                            c_counter = int(get_latest_data().get('counter', 0) or 0)
                        except: pass
                        
                        # Update existing active link -> add the new amount
                        cursor.execute(
                            "UPDATE agro_plan_opakowania SET stan_poczatkowy = stan_poczatkowy + %s WHERE id = %s",
                            (ilosc_docelowa, al['link_id'])
                        )
                        
                        # Log WSADZENIE in history for this specific roll addition
                        cursor.execute("""
                            INSERT INTO agro_workowanie_rozliczenie (
                                plan_id, data_planu, produkt, opakowanie_id, opakowanie_nazwa,
                                stan_przed, zuzyte_worki, stan_po, autor_login,
                                licznik_start, licznik_stop, typ_zdarzenia, link_id
                            ) VALUES (%s, %s, %s, %s, %s, %s, 0, %s, %s, %s, %s, 'WSADZENIE', %s)
                        """, (
                            plan_id, p_meta['data_planu'], p_meta['produkt'], opakowanie_id, nazwa,
                            ilosc_docelowa, ilosc_docelowa, user_login or 'System',
                            c_counter, c_counter, al['link_id']
                        ))
                        
                        # Odejmujemy ze stanu w magazynie i zapisujemy ruch magazynowy POBRANIE_DO_PRODUKCJI
                        stan_pozostaly = stan_poczatkowy_nowego - ilosc_docelowa
                        if stan_pozostaly > 0:
                            cursor.execute("UPDATE magazyn_opakowania SET stan_magazynowy = %s WHERE id = %s", (stan_pozostaly, opakowanie_id))
                        else:
                            cursor.execute(
                                "UPDATE magazyn_opakowania SET stan_magazynowy = 0, lokalizacja = 'Maszyna' WHERE id = %s",
                                (opakowanie_id,)
                            )
                            
                        table_ruch = get_table_name('magazyn_ruch', 'AGRO')
                        cursor.execute(
                            f"INSERT INTO {table_ruch} (surowiec_id, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, komentarz) "
                            "VALUES (%s, 'POBRANIE_DO_PRODUKCJI', %s, %s, 'POTWIERDZONE', %s, NOW(), %s)",
                            (opakowanie_id, -ilosc_docelowa, stan_pozostaly, user_login or 'System',
                             f"Dobrana rolka na produkcję AGRO (lok: {lokalizacja}) plan #{plan_id}")
                        )
                        
                        conn.commit()
                        return True, None
                    else:
                        # Different material: close it with 0 left and ZUŻYTE
                        stan_poczatkowy_al = float(al['stan_poczatkowy'] or 0)
                        cursor.execute(
                            "UPDATE agro_plan_opakowania SET stan_koncowy = 0, is_active = FALSE WHERE id = %s",
                            (al['link_id'],)
                        )
                        
                        cursor.execute("SELECT data_planu, produkt FROM plan_produkcji_agro WHERE id = %s", (plan_id,))
                        p_meta = cursor.fetchone() or {'data_planu': None, 'produkt': ''}
                        
                        old_start = int(al.get('licznik_start') or 0)
                        old_stop = mqtt_licznik_start if mqtt_licznik_start > old_start else old_start
                        zuzyte_worki = old_stop - old_start
                        straty = max(stan_poczatkowy_al - zuzyte_worki, 0)
                        
                        cursor.execute("""
                            INSERT INTO agro_workowanie_rozliczenie (
                                plan_id, data_planu, produkt, opakowanie_id, opakowanie_nazwa,
                                stan_przed, zuzyte_worki, stan_po, autor_login,
                                licznik_start, licznik_stop, typ_zdarzenia, link_id, straty_worki
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'ZAMKNIECIE', %s, %s)
                        """, (
                            plan_id, p_meta['data_planu'], p_meta['produkt'], al['opakowanie_id'], al['nazwa'],
                            stan_poczatkowy_al, zuzyte_worki, 0.0, user_login or 'System',
                            old_start, old_stop, al['link_id'], straty
                        ))
                        
                        cursor.execute(
                            "INSERT INTO magazyn_opakowania_historia (oryginalny_id, nr_palety, nazwa, stan_magazynowy, lokalizacja, nr_partii, data_produkcji, data_przydatnosci, typ_opakowania, is_blocked, linia) "
                            "SELECT id, nr_palety, nazwa, 0, 'ZUŻYTE', nr_partii, data_produkcji, data_przydatnosci, typ_opakowania, is_blocked, linia "
                            "FROM magazyn_opakowania WHERE id = %s",
                            (al['opakowanie_id'],)
                        )
                        cursor.execute("DELETE FROM magazyn_opakowania WHERE id = %s", (al['opakowanie_id'],))
                
                # Oblicz pobraną ilość (jeśli podano ułamek, to traktujemy jako część)
                ilosc_docelowa = stan_poczatkowy_nowego
                if ilosc_pobrana is not None:
                    try:
                        ilosc_docelowa = float(ilosc_pobrana)
                    except:
                        pass
                        
                target_opakowanie_id = opakowanie_id
                
                # Licznik MQTT odczytany wcześniej

                if 0 < ilosc_docelowa < stan_poczatkowy_nowego:
                    # Rozdzielenie partii (utworzenie nowego rekordu dla maszyny, zostawienie reszty na starym)
                    stan_pozostaly = stan_poczatkowy_nowego - ilosc_docelowa
                    # Aktualizacja starego rekordu — odejmij pobraną ilość ze stanu magazynowego
                    cursor.execute("UPDATE magazyn_opakowania SET stan_magazynowy = %s WHERE id = %s", (stan_pozostaly, opakowanie_id))

                    # Utworzenie nowego rekordu (ilość pobrana + carryover) — nowy wpis reprezentuje rolkę na maszynie
                    ilosc_na_maszyne = ilosc_docelowa + carryover_qty
                    cursor.execute(
                        "INSERT INTO magazyn_opakowania (nazwa, stan_magazynowy, lokalizacja) VALUES (%s, %s, %s)",
                        (nazwa, ilosc_na_maszyne, 'Maszyna')
                    )
                    target_opakowanie_id = cursor.lastrowid

                    # FIX: Zapis ruchu POBRANIE_DO_PRODUKCJI (odejmuje ze stanu magazynowego)
                    table_ruch = get_table_name('magazyn_ruch', 'AGRO')
                    try:
                        cursor.execute(
                            f"INSERT INTO {table_ruch} (surowiec_id, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, komentarz) "
                            "VALUES (%s, 'POBRANIE_DO_PRODUKCJI', %s, %s, 'POTWIERDZONE', %s, NOW(), %s)",
                            (opakowanie_id, -ilosc_docelowa, stan_pozostaly, user_login or 'System',
                             f"Pobranie folii na produkcję AGRO (podział z lok: {lokalizacja}) plan #{plan_id}")
                        )
                        komentarz_pobrania = f"Wsadzenie rolki z lok: {lokalizacja}"
                        if carryover_qty > 0:
                            komentarz_pobrania += f" (w tym carryover {int(carryover_qty)} szt. z poprzedniej rolki)"
                        cursor.execute(
                            f"INSERT INTO {table_ruch} (surowiec_id, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, komentarz) "
                            "VALUES (%s, 'POBRANIE_NA_MASZYNE', %s, %s, 'POTWIERDZONE', %s, NOW(), %s)",
                            (target_opakowanie_id, ilosc_na_maszyne, ilosc_na_maszyne, user_login or 'System', komentarz_pobrania)
                        )
                    except Exception as ex:
                        print(f"Error logging partial move: {ex}")

                    stan_poczatkowy_plan = ilosc_na_maszyne
                else:
                    # Brak podziału — sprawdzamy czy już podpięte
                    cursor.execute("SELECT id FROM agro_plan_opakowania WHERE plan_id = %s AND opakowanie_id = %s AND is_active = TRUE", (plan_id, target_opakowanie_id))
                    if cursor.fetchone(): return True, "Już podpięte"

                    stan_w_magazynie_przed = stan_poczatkowy_nowego
                    ilosc_na_maszyne = stan_poczatkowy_nowego + carryover_qty

                    # FIX: Odejmij całą rolkę ze stanu magazynowego (stan = 0, lokal = Maszyna)
                    cursor.execute(
                        "UPDATE magazyn_opakowania SET stan_magazynowy = 0, lokalizacja = 'Maszyna' WHERE id = %s",
                        (target_opakowanie_id,)
                    )

                    table_ruch = get_table_name('magazyn_ruch', 'AGRO')
                    try:
                        # FIX: Ruch POBRANIE_DO_PRODUKCJI — poprawnie zmniejsza stan magazynowy
                        cursor.execute(
                            f"INSERT INTO {table_ruch} (surowiec_id, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, komentarz) "
                            "VALUES (%s, 'POBRANIE_DO_PRODUKCJI', %s, %s, 'POTWIERDZONE', %s, NOW(), %s)",
                            (target_opakowanie_id, -stan_w_magazynie_przed, 0, user_login or 'System',
                             f"Pobranie folii na produkcję AGRO (lok: {lokalizacja}) plan #{plan_id}")
                        )
                        komentarz_pobrania = f"Wsadzenie rolki z lok: {lokalizacja}"
                        if carryover_qty > 0:
                            komentarz_pobrania += f" (w tym carryover {int(carryover_qty)} szt. z poprzedniej rolki)"
                        cursor.execute(
                            f"INSERT INTO {table_ruch} (surowiec_id, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, komentarz) "
                            "VALUES (%s, 'POBRANIE_NA_MASZYNE', %s, %s, 'POTWIERDZONE', %s, NOW(), %s)",
                            (target_opakowanie_id, ilosc_na_maszyne, ilosc_na_maszyne, user_login or 'System', komentarz_pobrania)
                        )
                    except Exception as ex:
                        print(f"Error logging full pull move: {ex}")

                    stan_poczatkowy_plan = ilosc_na_maszyne
                    
                # 3. Link — zapisz licznik MQTT przy wsadzeniu
                cursor.execute(
                    "INSERT INTO agro_plan_opakowania (plan_id, opakowanie_id, stan_poczatkowy, is_active, licznik_start) VALUES (%s, %s, %s, TRUE, %s)",
                    (plan_id, target_opakowanie_id, stan_poczatkowy_plan, mqtt_licznik_start)
                )
                new_link_id = cursor.lastrowid

                # Log wsadzenia rolki w agro_workowanie_rozliczenie
                cursor.execute("SELECT data_planu, produkt FROM plan_produkcji_agro WHERE id = %s", (plan_id,))
                p_meta = cursor.fetchone() or {'data_planu': None, 'produkt': ''}
                cursor.execute("""
                    INSERT INTO agro_workowanie_rozliczenie (
                        plan_id, data_planu, produkt, opakowanie_id, opakowanie_nazwa,
                        stan_przed, zuzyte_worki, stan_po, autor_login,
                        typ_zdarzenia, licznik_start, link_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, 0, %s, %s, 'WSADZENIE', %s, %s)
                """, (
                    plan_id, p_meta['data_planu'], p_meta['produkt'], target_opakowanie_id, nazwa,
                    stan_poczatkowy_plan, stan_poczatkowy_plan, user_login or 'System',
                    mqtt_licznik_start, new_link_id
                ))
                
                conn.commit()
                return True, None
            except Exception as e:
                conn.rollback()
                return False, str(e)
            finally:
                conn.close()

    def undo_packaging_link(link_id):
            """Delete an active packaging link (Undo addition)."""
            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("SELECT id, plan_id, opakowanie_id, stan_poczatkowy, is_active FROM agro_plan_opakowania WHERE id = %s", (link_id,))
                row = cursor.fetchone()
                if not row:
                    return False, "Nie znaleziono takiego powiązania"
                
                cursor.execute("DELETE FROM agro_plan_opakowania WHERE id = %s", (link_id,))
                
                # Delete corresponding "wsadzenie" (where zuzyte_worki = 0)
                cursor.execute("""
                    DELETE FROM agro_workowanie_rozliczenie 
                    WHERE plan_id = %s AND opakowanie_id = %s AND zuzyte_worki = 0
                """, (row['plan_id'], row['opakowanie_id']))
                
                conn.commit()
                return True, None
            except Exception as e:
                return False, str(e)
            finally:
                conn.close()

    def finalize_packaging_usage(plan_id, szt_na_palecie, packaging_results, user_login):
            """Processes final states for all packaging items used in a plan."""
            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                
                # 1. Fetch Plan Info
                table_plan = get_table_name('plan_produkcji', 'AGRO')
                cursor.execute(f"SELECT produkt, data_planu FROM {table_plan} WHERE id = %s", (plan_id,))
                plan_row = cursor.fetchone()
                if not plan_row:
                    return False
                    
                produkt = plan_row['produkt']
                data_planu = plan_row['data_planu']
                
                # 2. Get total pallets produced
                cursor.execute("SELECT COUNT(*) as cnt, SUM(waga) as total_kg FROM palety_agro WHERE plan_id = %s", (plan_id,))
                prod_row = cursor.fetchone()
                palety_count = prod_row['cnt'] or 0
                total_kg = float(prod_row['total_kg'] or 0)
                
                expected_bags = palety_count * szt_na_palecie
                total_consumed = 0
                
                # 3. Process each packaging item
                for res in packaging_results:
                    link_id = res['link_id']
                    stan_po = float(res['stan_po'])
                    
                    # Fetch linking record
                    cursor.execute("SELECT opakowanie_id, stan_poczatkowy, licznik_start FROM agro_plan_opakowania WHERE id = %s", (link_id,))
                    link_row = cursor.fetchone()
                    if not link_row: continue
                    
                    opak_id = link_row['opakowanie_id']
                    stan_przed = float(link_row['stan_poczatkowy'])
                    old_start = int(link_row.get('licznik_start') or 0)
                    # Since plan is closed, we can try to find stop_machine_counter
                    cursor.execute("SELECT stop_machine_counter FROM plan_produkcji_agro WHERE id = %s", (plan_id,))
                    p_cnt_row = cursor.fetchone()
                    old_stop = int(p_cnt_row.get('stop_machine_counter') or 0) if p_cnt_row else 0
                    
                    if old_stop > old_start and old_start > 0:
                        zuzycie = old_stop - old_start
                    else:
                        zuzycie = max(stan_przed - stan_po, 0)
                        if old_stop == 0:
                            old_stop = old_start + int(zuzycie)
                    
                    total_consumed += zuzycie
                    
                    # Update link record
                    cursor.execute(
                        "UPDATE agro_plan_opakowania SET stan_koncowy = %s, is_active = FALSE WHERE id = %s",
                        (stan_po, link_id)
                    )
                    
                    # Update main warehouse stock (synchronize)
                    cursor.execute("UPDATE magazyn_opakowania SET stan_magazynowy = %s WHERE id = %s", (stan_po, opak_id))
                    
                    # Fetch packaging name
                    cursor.execute("SELECT nazwa FROM magazyn_opakowania WHERE id = %s", (opak_id,))
                    opak_nazwa = (cursor.fetchone() or {}).get('nazwa', 'Opakowanie')
                    
                    # Insert into agro_workowanie_rozliczenie
                    cursor.execute("""
                        INSERT INTO agro_workowanie_rozliczenie (
                            plan_id, data_planu, produkt, opakowanie_id, opakowanie_nazwa,
                            stan_przed, wyprodukowano_szt, szt_na_palecie, palety_kg_wykonane,
                            zuzyte_worki, stan_po, autor_login,
                            licznik_start, licznik_stop, typ_zdarzenia, link_id
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'ZAMKNIECIE', %s)
                    """, (
                        plan_id, data_planu, produkt, opak_id, opak_nazwa,
                        stan_przed, palety_count, szt_na_palecie, total_kg,
                        zuzycie, stan_po, user_login,
                        old_start, old_stop, link_id
                    ))
                    
                    # Log to movement history
                    table_ruch = get_table_name('magazyn_ruch', 'AGRO')
                    try:
                        cursor.execute(
                            f"INSERT INTO {table_ruch} (surowiec_id, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, komentarz) "
                            "VALUES (%s, 'ROZLICZENIE_WORKOWANIE', %s, %s, 'POTWIERDZONE', %s, NOW(), %s)",
                            (opak_id, -zuzycie, stan_po, user_login, f"Rozliczenie plan #{plan_id}")
                        )
                    except: pass
                
                # 4. Calculate total waste (damaged bags) based on GLOBAL machine usage
                cursor.execute("SELECT COALESCE(SUM(zuzyte_worki), 0) as sum_z FROM agro_workowanie_rozliczenie WHERE plan_id = %s AND typ_zdarzenia = 'ZAMKNIECIE'", (plan_id,))
                z_row = cursor.fetchone()
                total_pulled = float(z_row['sum_z'] if z_row else 0)
                uszkodzone = max(total_pulled - expected_bags, 0)
                
                # 5. Update plan record
                cursor.execute(f"UPDATE {table_plan} SET uszkodzone_worki = %s WHERE id = %s", (int(uszkodzone), plan_id))
                
                conn.commit()
                return True
            except Exception as e:
                print(f"Error in finalize_packaging_usage: {e}")
                conn.rollback()
                return False
            finally:
                conn.close()

    def return_packaging_from_machine(opakowanie_id, stan_po, lokalizacja, user_login, is_partial=False, print_label=False):
            """Return a roll from machine back to warehouse.

            If `is_partial` is True, `stan_po` means quantity returned to warehouse.
            Otherwise `stan_po` means quantity left on the returned roll.
            """
            print_result = {'requested': bool(print_label), 'success': False, 'message': None}
            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)

                try:
                    numeric_val = float(stan_po) if (stan_po is not None and str(stan_po).strip() != '') else 0.0
                except (ValueError, TypeError):
                    numeric_val = 0.0

                final_loc = lokalizacja if (lokalizacja and lokalizacja.strip()) else ('ZUŻYTE' if (not is_partial and numeric_val <= 0) else 'Maszyna')

                cursor.execute("SELECT nazwa, stan_magazynowy FROM magazyn_opakowania WHERE id = %s", (opakowanie_id,))
                opak_row = cursor.fetchone()
                if not opak_row:
                    return False, "Opakowanie nie istnieje", {'print_result': print_result}
                opak_nazwa = opak_row['nazwa']
                aktualny_stan_maszyna = float(opak_row['stan_magazynowy'])

                cursor.execute(
                    """
                    SELECT id, plan_id, stan_poczatkowy
                    FROM agro_plan_opakowania
                    WHERE opakowanie_id = %s AND is_active = TRUE
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (opakowanie_id,),
                )
                link = cursor.fetchone()

                if is_partial:
                    ilosc_zwracana = numeric_val
                    if ilosc_zwracana <= 0:
                        return False, "Ilość zwracana musi być większa od 0", {'print_result': print_result}

                    nowy_stan_maszyna = aktualny_stan_maszyna - ilosc_zwracana
                    if nowy_stan_maszyna < 0:
                        nowy_stan_maszyna = 0
                    cursor.execute(
                        "UPDATE magazyn_opakowania SET stan_magazynowy = %s, updated_at = NOW() WHERE id = %s",
                        (nowy_stan_maszyna, opakowanie_id),
                    )

                    if link:
                        nowy_stan_poczatkowy = float(link['stan_poczatkowy']) - ilosc_zwracana
                        cursor.execute(
                            "UPDATE agro_plan_opakowania SET stan_poczatkowy = %s WHERE id = %s",
                            (nowy_stan_poczatkowy, link['id']),
                        )

                    cursor.execute(
                        "SELECT id, stan_magazynowy FROM magazyn_opakowania WHERE nazwa = %s AND lokalizacja = %s LIMIT 1",
                        (opak_nazwa, final_loc),
                    )
                    existing = cursor.fetchone()
                    if existing:
                        cursor.execute(
                            "UPDATE magazyn_opakowania SET stan_magazynowy = stan_magazynowy + %s, updated_at = NOW() WHERE id = %s",
                            (ilosc_zwracana, existing['id']),
                        )
                    else:
                        cursor.execute(
                            "INSERT INTO magazyn_opakowania (nazwa, stan_magazynowy, lokalizacja, created_at, updated_at) VALUES (%s, %s, %s, NOW(), NOW())",
                            (opak_nazwa, ilosc_zwracana, final_loc),
                        )

                    table_ruch = get_table_name('magazyn_ruch', 'AGRO')
                    cursor.execute(
                        f"INSERT INTO {table_ruch} (surowiec_id, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, komentarz) "
                        "VALUES (%s, 'CZESCIOWY_ZWROT', %s, %s, 'POTWIERDZONE', %s, NOW(), %s)",
                        (opakowanie_id, ilosc_zwracana, nowy_stan_maszyna, user_login, f"Częściowy zwrot na lok: {final_loc}"),
                    )

                    ilosc_przy_zwrocie = ilosc_zwracana
                    pozostalo_na_rolce = nowy_stan_maszyna
                else:
                    final_stan = numeric_val
                    cursor.execute(
                        "UPDATE magazyn_opakowania SET stan_magazynowy = %s, lokalizacja = %s, updated_at = NOW() WHERE id = %s",
                        (final_stan, final_loc, opakowanie_id),
                    )

                    if link:
                        plan_id = link['plan_id']
                        stan_przed = float(link['stan_poczatkowy'])
                        zuzycie = max(stan_przed - final_stan, 0)

                        cursor.execute(
                            "UPDATE agro_plan_opakowania SET stan_koncowy = %s, is_active = FALSE WHERE id = %s",
                            (final_stan, link['id']),
                        )

                        cursor.execute(f"SELECT data_planu, produkt FROM {get_table_name('plan_produkcji', 'AGRO')} WHERE id = %s", (plan_id,))
                        p_meta = cursor.fetchone() or {'data_planu': None, 'produkt': ''}

                        cursor.execute(
                            """
                            INSERT INTO agro_workowanie_rozliczenie (
                                plan_id, data_planu, produkt, opakowanie_id, opakowanie_nazwa,
                                stan_przed, zuzyte_worki, stan_po, autor_login
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                plan_id,
                                p_meta['data_planu'],
                                p_meta['produkt'],
                                opakowanie_id,
                                opak_nazwa,
                                stan_przed,
                                zuzycie,
                                final_stan,
                                user_login,
                            ),
                        )

                    table_ruch = get_table_name('magazyn_ruch', 'AGRO')
                    cursor.execute(
                        f"INSERT INTO {table_ruch} (surowiec_id, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, komentarz) "
                        "VALUES (%s, 'ZWROT_Z_MASZYNY', %s, %s, 'POTWIERDZONE', %s, NOW(), %s)",
                        (opakowanie_id, 0, final_stan, user_login, f"Pełny zwrot na lok: {final_loc}"),
                    )

                    ilosc_przy_zwrocie = final_stan
                    pozostalo_na_rolce = final_stan

                conn.commit()
            except Exception as e:
                conn.rollback()
                return False, str(e), {'print_result': print_result}
            finally:
                conn.close()

            return_label = {
                'opakowanie_id': opakowanie_id,
                'opakowanie_nazwa': opak_nazwa,
                'ilosc_przy_zwrocie': ilosc_przy_zwrocie,
                'pozostalo_na_rolce': pozostalo_na_rolce,
                'lokalizacja': final_loc,
                'data_odlozenia': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'odlozyl': user_login or 'System',
                'tryb_zwrotu': 'CZESCIOWY' if is_partial else 'CALKOWITY',
            }

            if print_result['requested']:
                try:
                    ok, msg = AgroOpakowaniaPlanRepository.print_packaging_return_label(return_label)
                    print_result['success'] = bool(ok)
                    print_result['message'] = msg
                except Exception as print_err:
                    print_result['success'] = False
                    print_result['message'] = str(print_err)
                    logger.exception('Packaging return label print failed for opakowanie_id=%s: %s', opakowanie_id, print_err)

            return True, None, {'return_label': return_label, 'print_result': print_result}

    def undo_packaging_return(link_id, user_login):
            """Restore an inactive packaging link to active state and revert warehouse stock."""
            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("SELECT id, plan_id, opakowanie_id, stan_poczatkowy, stan_koncowy, is_active FROM agro_plan_opakowania WHERE id = %s", (link_id,))
                row = cursor.fetchone()
                if not row:
                    return False, "Nie znaleziono powiązania"
                
                plan_id = row['plan_id']
                opakowanie_id = row['opakowanie_id']
                stan_poczatkowy = float(row['stan_poczatkowy'])
                
                # Restore is_active state
                cursor.execute("UPDATE agro_plan_opakowania SET is_active = TRUE, stan_koncowy = NULL WHERE id = %s", (link_id,))
                
                # Restore main warehouse stock
                cursor.execute("UPDATE magazyn_opakowania SET stan_magazynowy = %s, lokalizacja = 'Maszyna' WHERE id = %s", (stan_poczatkowy, opakowanie_id))
                
                # Delete corresponding history records from agro_workowanie_rozliczenie (except the "wsadzenie" row where zuzyte_worki = 0)
                cursor.execute("DELETE FROM agro_workowanie_rozliczenie WHERE plan_id = %s AND opakowanie_id = %s AND zuzyte_worki > 0", (plan_id, opakowanie_id))
                
                # Delete corresponding history records from magazyn_ruch
                table_ruch = get_table_name('magazyn_ruch', 'AGRO')
                cursor.execute(f"DELETE FROM {table_ruch} WHERE surowiec_id = %s AND typ_ruchu = 'ZWROT_Z_MASZYNY' ORDER BY id DESC LIMIT 1", (opakowanie_id,))
                
                conn.commit()
                return True, None
            except Exception as e:
                conn.rollback()
                return False, str(e)
            finally:
                conn.close()

    def build_packaging_return_label_zpl(label_data):
            """Build informational ZPL label for packaging returns."""
            opakowanie_nazwa = _sanitize_zpl_text(label_data.get('opakowanie_nazwa'), 58) or 'BRAK NAZWY'
            ilosc_przy_zwrocie = _format_quantity_label(label_data.get('ilosc_przy_zwrocie'))
            pozostalo_na_rolce = _format_quantity_label(label_data.get('pozostalo_na_rolce'))
            lokalizacja = _sanitize_zpl_text(label_data.get('lokalizacja'), 48) or 'BRAK'
            data_odlozenia = _sanitize_zpl_text(label_data.get('data_odlozenia'), 32) or datetime.now().strftime('%Y-%m-%d %H:%M')
            operator = _sanitize_zpl_text(label_data.get('odlozyl'), 36) or 'SYSTEM'
            tryb_zwrotu = _sanitize_zpl_text(label_data.get('tryb_zwrotu'), 16) or 'ZWROT'

            qr_payload = _sanitize_zpl_text(
                f"{opakowanie_nazwa}|{ilosc_przy_zwrocie}|{pozostalo_na_rolce}|{lokalizacja}|{data_odlozenia}|{operator}",
                160,
            )

            return f"""^XA
    ^CI28
    ^PW812^LL1214
    ^FO20,20^GB772,1174,4^FS
    ^FO40,55^A0N,52,52^FDZWROT OPAKOWANIA^FS
    ^FO40,130^A0N,32,32^FDTRYB: {tryb_zwrotu}^FS
    ^FO40,185^A0N,44,44^FB720,2,0,L^FD{opakowanie_nazwa}^FS
    ^FO40,330^A0N,34,34^FDILOSC PRZY ZWROCIE: {ilosc_przy_zwrocie} szt^FS
    ^FO40,390^A0N,34,34^FDPOZOSTALO NA ROLCE: {pozostalo_na_rolce} szt^FS
    ^FO40,450^A0N,34,34^FDLOKALIZACJA: {lokalizacja}^FS
    ^FO40,510^A0N,34,34^FDDATA ODLOZENIA: {data_odlozenia}^FS
    ^FO40,570^A0N,34,34^FDODLOZYL: {operator}^FS
    ^FO470,690^BY3^BQN,2,7^FDLA,{qr_payload}^FS
    ^XZ"""

    def print_packaging_return_label(label_data):
            """Print informational packaging-return label via print bridge."""
            from app.services.print_server import get_printer

            candidate_printers = []
            seen_targets = set()

            def _append_candidate(name, ip):
                key = ((name or '').strip().lower(), (ip or '').strip().lower())
                if key in seen_targets:
                    return
                seen_targets.add(key)
                candidate_printers.append((name, ip))

            try:
                conn = get_db_connection()
                try:
                    cursor = conn.cursor(dictionary=True)
                    cursor.execute(
                        """
                        SELECT id, nazwa, ip
                        FROM drukarki
                        WHERE aktywna = 1
                        ORDER BY
                            CASE
                                WHEN LOWER(COALESCE(nazwa, '')) LIKE '%zebra produkcja%' THEN 0
                                WHEN LOWER(COALESCE(lokalizacja, '')) LIKE '%produk%' THEN 1
                                ELSE 2
                            END,
                            id ASC
                        """
                    )
                    for row in cursor.fetchall() or []:
                        _append_candidate(row.get('nazwa'), row.get('ip'))
                finally:
                    conn.close()
            except Exception as printer_cfg_err:
                logger.warning('Could not resolve preferred printer for packaging return label: %s', printer_cfg_err)

            printer = get_printer()
            zpl = AgroOpakowaniaPlanRepository.build_packaging_return_label_zpl(label_data)

            # Last resort: use configured default printer from PrintServer.
            _append_candidate(None, None)

            last_message = 'Brak dostępnej drukarki'
            for idx, (override_name, override_ip) in enumerate(candidate_printers, start=1):
                ok, msg = printer.print_zpl_label(zpl, override_ip=override_ip, override_name=override_name)
                if ok:
                    if idx > 1:
                        logger.info(
                            'Packaging return label printed via fallback printer (attempt=%s, printer=%s, ip=%s)',
                            idx,
                            override_name or printer.printer_name,
                            override_ip or printer.printer_ip,
                        )
                    return True, msg

                last_message = msg
                logger.warning(
                    'Packaging return label print attempt %s failed (printer=%s, ip=%s): %s',
                    idx,
                    override_name or printer.printer_name,
                    override_ip or printer.printer_ip,
                    msg,
                )

            return False, last_message

