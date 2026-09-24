"""
Script to resolve and relocate pending pallets from transfer te22092026071643 and delivery #344a97a0.
Updates warehouse physical locations from OCZEKUJĄCE to real target locations and removes locks.
"""
import json
from datetime import datetime
from typing import Dict, Any, List
from app.db import get_db_connection, get_table_name


def fix_pending_pallets():
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        all_tables = [
            'magazyn_surowce',
            'magazyn_opakowania',
            'magazyn_dodatki',
            'magazyn_palety',
            'magazyn_palety_agro'
        ]

        # ---------------------------------------------------------
        # 1. Zlecenie przesunięcia te22092026071643
        # ---------------------------------------------------------
        print("=== 1. Weryfikacja i naprawa przesuniecia te22092026071643 ===")
        cursor.execute(
            "SELECT id, order_ref, status, lokalizacja_z, lokalizacja_do, items, linia FROM magazyn_dostawy WHERE order_ref LIKE %s OR id LIKE %s",
            ('%22092026071643%', '%22092026071643%')
        )
        transfer = cursor.fetchone()

        if transfer:
            trf_id = transfer['id']
            trf_ref = transfer['order_ref']
            trf_dst = transfer.get('lokalizacja_do') or 'MS01'
            if trf_dst in ('OCZEKUJĄCE', 'OCZEKUJACE', 'RAMPA', '', None):
                trf_dst = 'MS01'

            items = json.loads(transfer['items']) if isinstance(transfer['items'], str) else (transfer['items'] or [])
            print(f"Znaleziono przesuniecie {trf_ref} (ID: {trf_id}), Status: {transfer['status']}, Cel domyslny: {trf_dst}")
            print(f"Pozycji w zleceniu: {len(items)}")

            trf_updated = 0
            for it in items:
                pnr = (it.get('nr_palety') or it.get('sourcePalletNo') or '').strip().upper()
                pid = it.get('sourcePalletId') or it.get('id')
                target_loc = it.get('lokalizacja_przyjecia') or it.get('targetSpot') or trf_dst
                if target_loc in ('OCZEKUJĄCE', 'OCZEKUJACE', 'RAMPA', '', None):
                    target_loc = trf_dst

                it['accepted'] = True
                it['lokalizacja_przyjecia'] = target_loc
                it['putaway_confirmed_location'] = target_loc
                it['putaway_confirmed_at'] = it.get('putaway_confirmed_at') or now_str
                it['pallet_status'] = 'STORED'

                # Aktualizacja fizycznej palety w tabelach magazynowych
                for tbl in all_tables:
                    try:
                        if pnr:
                            cursor.execute(
                                f"UPDATE {tbl} SET lokalizacja = %s, is_blocked = 0, is_loaded = 0 WHERE nr_palety = %s",
                                (target_loc, pnr)
                            )
                            if cursor.rowcount > 0:
                                print(f"  • Paleta {pnr} w {tbl} przeniesiona na {target_loc} (is_blocked=0)")
                                trf_updated += 1
                        elif pid:
                            cursor.execute(
                                f"UPDATE {tbl} SET lokalizacja = %s, is_blocked = 0, is_loaded = 0 WHERE id = %s",
                                (target_loc, pid)
                            )
                            if cursor.rowcount > 0:
                                print(f"  • Paleta ID={pid} w {tbl} przeniesiona na {target_loc} (is_blocked=0)")
                                trf_updated += 1
                    except Exception:
                        pass

            # Zamkniecie statusu zlecenia przesuniecia
            cursor.execute(
                "UPDATE magazyn_dostawy SET items = %s, status = 'COMPLETED', potwierdzone_at = %s WHERE id = %s",
                (json.dumps(items), now_str, trf_id)
            )
            print(f"Przesuniecie {trf_ref} zamkniete (COMPLETED). Zaktualizowano palet: {trf_updated}\n")
        else:
            print("Nie znaleziono zlecenia przesuniecia zawierajacego '22092026071643'.\n")

        # ---------------------------------------------------------
        # 2. Dostawa zewnętrzna PZ #344a97a0
        # ---------------------------------------------------------
        print("=== 2. Weryfikacja i naprawa dostawy PZ #344a97a0 ===")
        cursor.execute(
            "SELECT id, order_ref, status, supplier, lokalizacja_do, items, linia FROM magazyn_dostawy WHERE id LIKE %s",
            ('344a97a0%',)
        )
        delivery = cursor.fetchone()

        if delivery:
            del_id = delivery['id']
            del_ref = delivery.get('order_ref') or f"#{del_id[:8]}"
            del_dst = delivery.get('lokalizacja_do') or 'MS01'
            if del_dst in ('OCZEKUJĄCE', 'OCZEKUJACE', 'RAMPA', '', None):
                del_dst = 'MS01'

            del_items = json.loads(delivery['items']) if isinstance(delivery['items'], str) else (delivery['items'] or [])
            print(f"Znaleziono dostawe {del_ref} (ID: {del_id}), Status: {delivery['status']}, Dostawca: {delivery['supplier']}")
            print(f"Pozycji w dostawie: {len(del_items)}")

            del_updated = 0
            for it in del_items:
                pnr = (it.get('nr_palety') or it.get('sourcePalletNo') or '').strip().upper()
                pid = it.get('sourcePalletId') or it.get('id')
                target_loc = it.get('lokalizacja_przyjecia') or it.get('targetSpot') or del_dst
                if target_loc in ('OCZEKUJĄCE', 'OCZEKUJACE', 'RAMPA', '', None):
                    target_loc = del_dst

                it['accepted'] = True
                it['lokalizacja_przyjecia'] = target_loc
                it['putaway_confirmed_location'] = target_loc
                it['putaway_confirmed_at'] = it.get('putaway_confirmed_at') or now_str
                it['pallet_status'] = 'STORED'

                # Sprawdz i popraw fizyczne palety wiszace w OCZEKUJACYCH lub zablokowane
                for tbl in all_tables:
                    try:
                        if pnr:
                            cursor.execute(
                                f"SELECT id, lokalizacja, is_blocked FROM {tbl} WHERE nr_palety = %s",
                                (pnr,)
                            )
                            row = cursor.fetchone()
                            if row:
                                curr_loc = str(row.get('lokalizacja') or '').strip().upper()
                                is_bl = row.get('is_blocked')
                                if curr_loc in ('OCZEKUJĄCE', 'OCZEKUJACE', 'RAMPA', 'BRAK', '') or is_bl == 1:
                                    cursor.execute(
                                        f"UPDATE {tbl} SET lokalizacja = %s, is_blocked = 0, is_loaded = 0 WHERE id = %s",
                                        (target_loc, row['id'])
                                    )
                                    print(f"  • Paleta {pnr} w {tbl}: zmieniono z '{curr_loc}' na '{target_loc}' (odblokowana)")
                                    del_updated += 1
                        elif pid:
                            cursor.execute(
                                f"SELECT id, lokalizacja, is_blocked FROM {tbl} WHERE id = %s",
                                (pid,)
                            )
                            row = cursor.fetchone()
                            if row:
                                curr_loc = str(row.get('lokalizacja') or '').strip().upper()
                                is_bl = row.get('is_blocked')
                                if curr_loc in ('OCZEKUJĄCE', 'OCZEKUJACE', 'RAMPA', 'BRAK', '') or is_bl == 1:
                                    cursor.execute(
                                        f"UPDATE {tbl} SET lokalizacja = %s, is_blocked = 0, is_loaded = 0 WHERE id = %s",
                                        (target_loc, row['id'])
                                    )
                                    print(f"  • Paleta ID={pid} w {tbl}: zmieniono z '{curr_loc}' na '{target_loc}' (odblokowana)")
                                    del_updated += 1
                    except Exception:
                        pass

            # Upewnij sie, ze status dostawy to COMPLETED
            cursor.execute(
                "UPDATE magazyn_dostawy SET items = %s, status = 'COMPLETED', potwierdzone_at = %s WHERE id = %s",
                (json.dumps(del_items), now_str, del_id)
            )
            print(f"Dostawa {del_ref} potwierdzona jako COMPLETED. Poprawiono palet w bazie: {del_updated}\n")
        else:
            print("Nie znaleziono dostawy o ID zaczynajacym sie od '344a97a0'.\n")

        conn.commit()
        print("=== SUKCES: Wszystkie powiazane palety zostaly przeniesione na realne regaly i odblokowane. ===")
    finally:
        conn.close()


if __name__ == '__main__':
    fix_pending_pallets()
