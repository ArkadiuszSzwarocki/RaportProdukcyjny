"""Database query and lookup methods for ScannerService."""
from __future__ import annotations

import re
import json
from datetime import datetime
from app.core.database import get_db_connection, get_table_name
from app.services.scanner.scanner_code_normalizer import ScannerCodeNormalizer
from app.services.scanner.scanner_item_normalizer import ScannerItemNormalizer


class ScannerLookupService:
    """Handles lookups for pallets, raw materials, finished goods, shelves and stations."""

    @staticmethod
    def get_active_production_qty(cur, surowiec_id: int, linia: str) -> tuple[float, str]:
        """Returns (remaining_qty_in_production, tank) for given raw material."""
        if not surowiec_id:
            return 0.0, ''
        try:
            table_ruch = get_table_name('magazyn_ruch', linia)
            cur.execute(
                f"SELECT r.id, ABS(r.ilosc) as pobrana, COALESCE(r.zbiornik, '') as zbiornik, "
                f"COALESCE((SELECT SUM(z.ilosc) FROM {table_ruch} z WHERE z.ruch_zrodlowy_id = r.id AND z.typ_ruchu = 'ZWROT'), 0) as zwrocona, "
                f"COALESCE((SELECT SUM(k.ilosc) FROM {table_ruch} k WHERE k.ruch_zrodlowy_id = r.id AND k.typ_ruchu = 'INWENTARYZACJA_PROD'), 0) as korekta "
                f"FROM {table_ruch} r "
                f"WHERE r.surowiec_id = %s AND r.typ_ruchu = 'PRODUKCJA' AND r.status = 'POTWIERDZONE' "
                f"ORDER BY r.autor_data DESC, r.id DESC LIMIT 1",
                (surowiec_id,)
            )
            row = cur.fetchone()
            if row:
                pobrana = float(row.get('pobrana') or 0)
                zwrocona = float(row.get('zwrocona') or 0)
                korekta = float(row.get('korekta') or 0)
                rem = round(pobrana - zwrocona + korekta, 2)
                if rem > 0:
                    return rem, (row.get('zbiornik') or '').strip().upper()
        except Exception:
            pass
        return 0.0, ''

    @staticmethod
    def lookup_inventory_row(
        cur,
        base_table: str,
        linia: str,
        *,
        qty_col: str,
        name_col: str = 'nazwa',
        location_code: str | None = None,
        item_id: int | None = None,
        pallet_no: str | None = None,
        partial_pallet_no: str | None = None,
    ) -> dict | None:
        table_name = get_table_name(base_table, linia)
        where = [f"COALESCE({qty_col}, 0) > 0"]
        params: list[object] = []

        if location_code is not None:
            where.append("UPPER(COALESCE(lokalizacja, '')) = %s")
            params.append(location_code)
        if item_id is not None:
            where.append("id = %s")
            params.append(item_id)
        if pallet_no is not None:
            where.append("UPPER(COALESCE(nr_palety, '')) = %s")
            params.append(str(pallet_no).upper())
        if partial_pallet_no is not None:
            where.append("UPPER(COALESCE(nr_palety, '')) LIKE %s")
            params.append('%' + str(partial_pallet_no).upper())

        sql = (
            f"SELECT id, {name_col} AS nazwa, {qty_col} AS ilosc, COALESCE(lokalizacja, '') AS lokalizacja, "
            f"COALESCE(nr_palety, '') AS nr_palety, COALESCE(nr_partii, '') AS nr_partii, "
            f"data_produkcji, data_przydatnosci, '{linia}' AS linia "
            f"FROM {table_name} WHERE {' AND '.join(where)} ORDER BY id DESC LIMIT 1"
        )
        try:
            cur.execute(sql, tuple(params))
            row = cur.fetchone()
            if row:
                return row
        except Exception:
            pass

        if location_code is None and (item_id is not None or pallet_no is not None or partial_pallet_no is not None):
            where_unbound = []
            params_unbound: list[object] = []
            if item_id is not None:
                where_unbound.append("id = %s")
                params_unbound.append(item_id)
            if pallet_no is not None:
                where_unbound.append("UPPER(COALESCE(nr_palety, '')) = %s")
                params_unbound.append(str(pallet_no).upper())
            if partial_pallet_no is not None:
                where_unbound.append("UPPER(COALESCE(nr_palety, '')) LIKE %s")
                params_unbound.append('%' + str(partial_pallet_no).upper())

            if where_unbound:
                sql_unbound = (
                    f"SELECT id, {name_col} AS nazwa, {qty_col} AS ilosc, COALESCE(lokalizacja, '') AS lokalizacja, "
                    f"COALESCE(nr_palety, '') AS nr_palety, COALESCE(nr_partii, '') AS nr_partii, "
                    f"data_produkcji, data_przydatnosci, '{linia}' AS linia "
                    f"FROM {table_name} WHERE {' AND '.join(where_unbound)} ORDER BY id DESC LIMIT 1"
                )
                try:
                    cur.execute(sql_unbound, tuple(params_unbound))
                    p_row = cur.fetchone()
                    if p_row:
                        prod_qty, prod_tank = ScannerLookupService.get_active_production_qty(cur, p_row['id'], linia)
                        if prod_qty > 0:
                            p_row['ilosc'] = prod_qty
                            if prod_tank:
                                p_row['lokalizacja'] = prod_tank
                            return p_row
                except Exception:
                    pass

        return None

    @staticmethod
    def lookup_finished_goods(
        cur,
        linia: str,
        *,
        item_id: int | None = None,
        location_code: str | None = None,
        pallet_no: str | None = None,
        partial_pallet_no: str | None = None,
    ) -> dict | None:
        table_name = get_table_name('magazyn_palety', linia)
        table_plan = get_table_name('plan_produkcji', linia)
        
        select_clause = (
            f"SELECT m.id, COALESCE(plan.produkt, m.produkt) AS nazwa, m.waga_netto AS ilosc, COALESCE(m.lokalizacja, 'MGW01') AS lokalizacja, "
            f"COALESCE(m.nr_palety, '') AS nr_palety, COALESCE(m.nr_partii, plan.nr_partii, '') AS nr_partii, "
            f"COALESCE(m.data_produkcji, plan.data_produkcji) AS data_produkcji, COALESCE(m.data_przydatnosci, plan.termin_przydatnosci) AS data_przydatnosci, "
            f"COALESCE(m.is_blocked, 0) AS is_blocked, '{linia}' AS linia "
            f"FROM {table_name} m "
            f"LEFT JOIN {table_plan} plan ON m.plan_id = plan.id "
        )

        if item_id is not None:
            try:
                cur.execute(select_clause + f"WHERE m.id = %s AND COALESCE(m.waga_netto, 0) > 0 LIMIT 1", (item_id,))
                return cur.fetchone()
            except Exception:
                return None

        if pallet_no is not None:
            try:
                cur.execute(select_clause + f"WHERE UPPER(COALESCE(m.nr_palety, '')) = %s AND COALESCE(m.waga_netto, 0) > 0 LIMIT 1", (str(pallet_no).upper(),))
                return cur.fetchone()
            except Exception:
                pass

        if partial_pallet_no is not None:
            try:
                cur.execute(select_clause + f"WHERE UPPER(COALESCE(m.nr_palety, '')) LIKE %s AND COALESCE(m.waga_netto, 0) > 0 LIMIT 1", ('%' + str(partial_pallet_no).upper(),))
                return cur.fetchone()
            except Exception:
                pass

        normalized_location = str(location_code or '').strip().upper()
        if not normalized_location:
            return None

        try:
            cur.execute(
                select_clause + f"WHERE UPPER(COALESCE(m.lokalizacja, 'MGW01')) = %s AND COALESCE(m.waga_netto, 0) > 0 "
                "ORDER BY COALESCE(m.data_potwierdzenia, m.created_at) DESC, m.id DESC LIMIT 1",
                (normalized_location,),
            )
            return cur.fetchone()
        except Exception:
            return None

    @staticmethod
    def check_active_transfer_for_code(code: str):
        if not code:
            return None
        code_clean = ScannerCodeNormalizer.normalize_scanned_code(code) or str(code).strip()
        conn = None
        cursor = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute("""
                SELECT t.id, t.transfer_code, t.source_warehouse, t.destination_warehouse, t.status, t.created_by, t.created_at
                FROM osip_transfers t
                WHERE t.transfer_code = %s AND t.status IN ('PLANNED', 'IN_TRANSIT')
            """, (code_clean,))
            transfer = cursor.fetchone()

            if not transfer:
                cursor.execute("""
                    SELECT t.id, t.transfer_code, t.source_warehouse, t.destination_warehouse, t.status, t.created_by, t.created_at
                    FROM osip_transfer_items ti
                    JOIN osip_transfers t ON ti.transfer_id = t.id
                    WHERE (ti.nr_palety = %s OR (ti.pallet_id = %s AND %s != '0')) AND t.status IN ('PLANNED', 'IN_TRANSIT')
                    LIMIT 1
                """, (code_clean, code_clean if code_clean.isdigit() else 0, code_clean if code_clean.isdigit() else '0'))
                transfer = cursor.fetchone()

            if transfer:
                cursor.execute("""
                    SELECT id, pallet_id, nr_palety, product_name, requested_qty, loaded_qty, unit, status
                    FROM osip_transfer_items
                    WHERE transfer_id = %s
                """, (transfer['id'],))
                items = cursor.fetchall()
                transfer['items'] = items
                if transfer.get('created_at') and hasattr(transfer['created_at'], 'strftime'):
                    transfer['created_at'] = transfer['created_at'].strftime('%Y-%m-%d %H:%M')
                elif transfer.get('created_at'):
                    transfer['created_at'] = str(transfer['created_at'])
                return transfer

            cursor.execute("""
                SELECT id, supplier, lokalizacja_z, lokalizacja_do, status, created_at, items, linia
                FROM magazyn_dostawy
                WHERE status IN ('OCZEKUJE', 'OPEN', 'PUTAWAY_IN_PROGRESS')
                ORDER BY id DESC
            """)
            dostawy = cursor.fetchall()
            code_clean_upper = code_clean.upper()
            for d in dostawy:
                raw_items = d.get('items')
                if not raw_items:
                    continue
                try:
                    d_items = json.loads(raw_items) if isinstance(raw_items, str) else raw_items
                except Exception:
                    continue
                if not isinstance(d_items, list):
                    continue

                delivery_status = str(d.get('status') or '').strip().upper()

                for it in d_items:
                    if not isinstance(it, dict):
                        continue
                    if it.get('rejected'):
                        continue

                    if delivery_status == 'PUTAWAY_IN_PROGRESS':
                        if it.get('putaway_confirmed_at'):
                            continue
                    else:
                        if it.get('accepted'):
                            continue
                    
                    it_nr_raw = str(it.get('nr_palety') or it.get('sourcePalletNo') or '').strip()
                    it_nr = (ScannerCodeNormalizer.normalize_scanned_code(it_nr_raw) or it_nr_raw).upper()
                    it_id = str(it.get('sourcePalletId') or it.get('id') or '')
                    
                    if (it_nr and it_nr == code_clean_upper) or (it_id and it_id == code_clean):
                        created_str = d['created_at'].strftime('%Y-%m-%d %H:%M') if hasattr(d.get('created_at'), 'strftime') else str(d.get('created_at') or '')
                        src_spot = it.get('sourceSpot') or d.get('lokalizacja_z') or 'MAGAZYN'
                        dst_spot = it.get('lokalizacja_przyjecia') or d.get('lokalizacja_do') or 'OCZEKUJĄCE'
                        return {
                            'id': d['id'],
                            'transfer_code': d.get('supplier') or f"Zlecenie #{d['id'][:8] if isinstance(d['id'], str) else d['id']}",
                            'source_warehouse': src_spot,
                            'destination_warehouse': dst_spot,
                            'status': delivery_status or 'OCZEKUJE',
                            'created_at': created_str,
                            'linia': d.get('linia', 'PSD'),
                            'is_magazyn_dostawy': True,
                            'item_details': it
                        }
            return None
        except Exception as e:
            print(f"Error checking active transfer for code {code}: {e}")
            return None
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
