import logging
from app.db import get_db_connection, get_table_name
import datetime
import os
import re

_DODATEK_NAME_REGEX = re.compile(r'DODATEK')

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

class AgroOpakowaniaRepository:
    def get_packaging_inventory(linia='Agro'):
            """Return packaging inventory rows from magazyn_opakowania."""
            table_opak = get_table_name('magazyn_opakowania', linia)
            conn = get_db_connection()
            try:
                cursor = conn.cursor(dictionary=True)
                cursor.execute(
                    f"SELECT * FROM {table_opak} "
                    f"WHERE (lokalizacja != 'ZUŻYTE' OR lokalizacja IS NULL) AND stan_magazynowy > 0 "
                    f"ORDER BY nazwa, id"
                )
                return cursor.fetchall()
            finally:
                conn.close()

    def create_packaging(nazwa, ilosc, lokalizacja=None, linia='Agro'):
            table_opak = get_table_name('magazyn_opakowania', linia)
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(f"INSERT INTO {table_opak} (nazwa, stan_magazynowy, lokalizacja) VALUES (%s, %s, %s)", (nazwa, ilosc, lokalizacja))
                conn.commit()
                return cursor.lastrowid
            finally:
                conn.close()

    def edit_packaging(record_id, nazwa=None, ilosc=None, lokalizacja=None, linia='Agro'):
            table_opak = get_table_name('magazyn_opakowania', linia)
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                updates = []
                params = []
                if nazwa is not None:
                    updates.append('nazwa = %s')
                    params.append(nazwa)
                if ilosc is not None:
                    updates.append('stan_magazynowy = %s')
                    params.append(ilosc)
                if lokalizacja is not None:
                    updates.append('lokalizacja = %s')
                    params.append(lokalizacja)
                if not updates:
                    return True
                params.append(record_id)
                q = f"UPDATE {table_opak} SET " + ', '.join(updates) + " WHERE id = %s"
                cursor.execute(q, tuple(params))
                conn.commit()
                return True
            finally:
                conn.close()

    def delete_packaging(record_id, linia='Agro'):
            table_opak = get_table_name('magazyn_opakowania', linia)
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(f"DELETE FROM {table_opak} WHERE id = %s", (record_id,))
                conn.commit()
                return True
            finally:
                conn.close()

    def adjust_packaging_inventory(record_id, actual_qty, worker_login=None, linia='Agro'):
            table_opak = get_table_name('magazyn_opakowania', linia)
            # We will reuse magazyn_ruch for audit if available
            table_ruch = get_table_name('magazyn_ruch', linia)
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(f"SELECT stan_magazynowy FROM {table_opak} WHERE id = %s", (record_id,))
                row = cursor.fetchone()
                if not row:
                    return False
                old_qty = row[0]
                delta = actual_qty - old_qty
                cursor.execute(f"UPDATE {table_opak} SET stan_magazynowy = %s WHERE id = %s", (actual_qty, record_id))
                try:
                    cursor.execute(
                        f"INSERT INTO {table_ruch} (surowiec_id, typ_ruchu, ilosc, ilosc_po, status, autor_login, autor_data, komentarz) VALUES (%s, 'INWENTARYZACJA', %s, %s, 'POTWIERDZONE', %s, %s, %s)",
                        (record_id, delta, actual_qty, worker_login, datetime.datetime.now(), 'Inwentaryzacja opakowania')
                    )
                except Exception:
                    # If ruch table missing or insert fails, ignore audit
                    pass
                conn.commit()
                return True
            finally:
                conn.close()

