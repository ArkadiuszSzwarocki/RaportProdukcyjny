# File: app/blueprints/warehouse_v2/controllers/pallet_label_controller.py
"""Pallet Label Controller.

Handles preview rendering of thermal/ZPL labels for pallets across lines and types:
- Finished products
- Raw materials
- Packagings
- Additives
"""

from datetime import datetime
import json
from typing import Any, Dict, List, Optional, Tuple
from flask import render_template, request

from app.db import get_db_connection
from app.utils.pallet_label import (
    calculate_expiry_date,
    is_packaging_item,
    prepare_pallet_label_data,
)


class PalletLabelController:
    """Controller for pallet label previews and ZPL template generation."""

    @classmethod
    def render_label_preview(cls, paleta_id: str):
        """Generates HTML preview of a pallet label for any pallet type using Labelary API."""
        linia = request.args.get('linia', 'PSD').strip().upper()
        pallet_type = request.args.get('type', '').strip()
        sscc = request.args.get('sscc', '').strip()

        search_id = str(paleta_id).strip()
        search_sscc = sscc or search_id

        conn = get_db_connection()
        label_data: Optional[Dict[str, Any]] = None
        resolved_type = pallet_type

        try:
            cursor = conn.cursor(dictionary=True)

            # 1. Primary lookup using unified prepare_pallet_label_data
            try:
                label_data = prepare_pallet_label_data(cursor, search_sscc or search_id, linia=linia)
            except Exception:
                label_data = None

            # 2. Targeted lookup based on type if not yet resolved
            if not label_data:
                if pallet_type.lower() in ('surowiec', 'raw_material', 'surowce') or search_sscc.upper().startswith('SUR'):
                    tables = ['magazyn_surowce', 'magazyn_agro_surowce'] if linia != 'AGRO' else ['magazyn_agro_surowce', 'magazyn_surowce']
                    for tbl in tables:
                        cursor.execute(
                            f"SELECT id, nazwa, stan_magazynowy as waga_netto, nr_partii, "
                            f"data_produkcji, data_przydatnosci, nr_palety, lokalizacja FROM {tbl} "
                            f"WHERE id = %s OR nr_palety = %s OR nr_palety = %s ORDER BY stan_magazynowy > 0 DESC, id DESC LIMIT 1",
                            (search_id, search_id, search_sscc)
                        )
                        row = cursor.fetchone()
                        if row:
                            label_data = {
                                'id': row['id'],
                                'nr_palety': row.get('nr_palety') or search_sscc,
                                'nazwa': row.get('nazwa') or 'Surowiec',
                                'ilosc': float(row.get('waga_netto') or 0),
                                'data': str(row.get('data_produkcji') or datetime.now().strftime('%Y-%m-%d')),
                                'termin': str(row.get('data_przydatnosci') or ''),
                                'partia': row.get('nr_partii') or '---',
                                'jednostka': 'kg',
                                'typ': 'SUROWIEC',
                                'linia': linia
                            }
                            resolved_type = 'Surowiec'
                            break

                elif pallet_type.lower() in ('opakowanie', 'packaging', 'opakowania') or search_sscc.upper().startswith(('OPK', 'OPA')):
                    tables = ['magazyn_opakowania', 'magazyn_agro_opakowania'] if linia != 'AGRO' else ['magazyn_agro_opakowania', 'magazyn_opakowania']
                    for tbl in tables:
                        cursor.execute(
                            f"SELECT id, nazwa, stan_magazynowy as waga_netto, nr_partii, "
                            f"data_produkcji, data_przydatnosci, nr_palety, lokalizacja FROM {tbl} "
                            f"WHERE id = %s OR nr_palety = %s OR nr_palety = %s ORDER BY stan_magazynowy > 0 DESC, id DESC LIMIT 1",
                            (search_id, search_id, search_sscc)
                        )
                        row = cursor.fetchone()
                        if row:
                            label_data = {
                                'id': row['id'],
                                'nr_palety': row.get('nr_palety') or search_sscc,
                                'nazwa': row.get('nazwa') or 'Opakowanie',
                                'ilosc': float(row.get('waga_netto') or 0),
                                'data': str(row.get('data_produkcji') or datetime.now().strftime('%Y-%m-%d')),
                                'termin': str(row.get('data_przydatnosci') or ''),
                                'partia': row.get('nr_partii') or '---',
                                'jednostka': 'szt.',
                                'typ': 'OPAKOWANIE',
                                'linia': linia
                            }
                            resolved_type = 'Opakowanie'
                            break

                elif pallet_type.lower() in ('dodatek', 'dodatki') or search_sscc.upper().startswith('DOD'):
                    cursor.execute(
                        "SELECT id, nazwa, stan_magazynowy as waga_netto, nr_partii, "
                        "data_produkcji, data_przydatnosci, nr_palety, lokalizacja FROM magazyn_dodatki "
                        "WHERE id = %s OR nr_palety = %s OR nr_palety = %s ORDER BY stan_magazynowy > 0 DESC, id DESC LIMIT 1",
                        (search_id, search_id, search_sscc)
                    )
                    row = cursor.fetchone()
                    if row:
                        label_data = {
                            'id': row['id'],
                            'nr_palety': row.get('nr_palety') or search_sscc,
                            'nazwa': row.get('nazwa') or 'Dodatek',
                            'ilosc': float(row.get('waga_netto') or 0),
                            'data': str(row.get('data_produkcji') or datetime.now().strftime('%Y-%m-%d')),
                            'termin': str(row.get('data_przydatnosci') or ''),
                            'partia': row.get('nr_partii') or '---',
                            'jednostka': 'kg',
                            'typ': 'DODATEK',
                            'linia': linia
                        }
                        resolved_type = 'Dodatek'

            # 3. Fallback scan across all tables if still not found
            if not label_data:
                all_candidate_tables: List[Tuple[str, str, str]] = [
                    ('magazyn_surowce', 'SUROWIEC', 'kg'),
                    ('magazyn_agro_surowce', 'SUROWIEC', 'kg'),
                    ('magazyn_opakowania', 'OPAKOWANIE', 'szt.'),
                    ('magazyn_agro_opakowania', 'OPAKOWANIE', 'szt.'),
                    ('magazyn_dodatki', 'DODATEK', 'kg'),
                    ('magazyn_palety', 'WYRÓB GOTOWY', 'kg'),
                    ('magazyn_palety_agro', 'WYRÓB GOTOWY', 'kg')
                ]
                for tbl, def_typ, def_unit in all_candidate_tables:
                    col_name = 'produkt' if 'palety' in tbl else 'nazwa'
                    col_qty = 'waga_netto' if 'palety' in tbl else 'stan_magazynowy'
                    try:
                        cursor.execute(
                            f"SELECT id, {col_name} as nazwa, {col_qty} as waga_netto, nr_partii, "
                            f"data_produkcji, data_przydatnosci, nr_palety FROM {tbl} "
                            f"WHERE id = %s OR nr_palety = %s OR nr_palety = %s ORDER BY {col_qty} > 0 DESC, id DESC LIMIT 1",
                            (search_id, search_id, search_sscc)
                        )
                        row = cursor.fetchone()
                        if row:
                            label_data = {
                                'id': row['id'],
                                'nr_palety': row.get('nr_palety') or search_sscc,
                                'nazwa': row.get('nazwa') or 'Produkt',
                                'ilosc': float(row.get('waga_netto') or 0),
                                'data': str(row.get('data_produkcji') or datetime.now().strftime('%Y-%m-%d')),
                                'termin': str(row.get('data_przydatnosci') or ''),
                                'partia': row.get('nr_partii') or '---',
                                'jednostka': def_unit,
                                'typ': def_typ,
                                'linia': linia
                            }
                            resolved_type = def_typ
                            break
                    except Exception:
                        continue

        finally:
            conn.close()

        if not label_data:
            return 'Nie znaleziono danych etykiety dla tej palety.', 404

        nr_palety = str(label_data.get('nrPalety') or label_data.get('nr_palety') or search_sscc or paleta_id).strip()
        product_name = str(label_data.get('nazwa') or label_data.get('produkt') or 'Brak nazwy').strip()
        nr_partii = str(label_data.get('partia') or label_data.get('nr_partii') or '---').strip() or '---'
        data_produkcji = str(label_data.get('data') or label_data.get('data_produkcji') or datetime.now().strftime('%Y-%m-%d')).strip()[:10]
        data_przydatnosci_raw = str(label_data.get('termin') or label_data.get('data_przydatnosci') or '').strip()
        data_przydatnosci = calculate_expiry_date(data_przydatnosci_raw, data_produkcji) if data_przydatnosci_raw else ''
        qty_display = float(label_data.get('ilosc') or label_data.get('waga_netto') or 0)
        nr_palety_lp = label_data.get('nr_palety_lp')
        nr_plomby = label_data.get('nr_plomby') or None

        try:
            if nr_palety_lp not in (None, ''):
                nr_palety_lp = int(nr_palety_lp)
            else:
                nr_palety_lp = None
        except Exception:
            nr_palety_lp = None

        nr_upper = nr_palety.upper()
        prod_lower = product_name.lower()
        is_pkg = is_packaging_item(
            product_name,
            unit=label_data.get('jednostka') or label_data.get('unit'),
            typ=resolved_type or label_data.get('typ'),
            pallet_nr=nr_palety
        )
        is_surowiec = (
            nr_upper.startswith('SUR') or 
            nr_upper.startswith('DOD') or 
            'surowiec' in prod_lower or 
            (str(resolved_type or label_data.get('typ') or '')).lower() in ('surowiec', 'dodatek')
        )

        if is_pkg:
            typ_label = 'OPAKOWANIE'
            unit_str = 'szt.'
            qty_header = 'ILOSC:'
            header_zpl = f"OPAKOWANIE"
        elif is_surowiec:
            typ_label = 'SUROWIEC'
            unit_str = 'kg'
            qty_header = 'WAGA NETTO:'
            header_zpl = f"SUROWIEC"
        else:
            typ_label = 'WYRÓB GOTOWY'
            unit_str = 'kg'
            qty_header = 'WAGA NETTO:'
            header_zpl = f"WYRÓB GOTOWY - {linia}"

        conn = get_db_connection()
        qr_details = {}
        try:
            cursor = conn.cursor(dictionary=True)
            if is_surowiec or is_pkg:
                dostawa_id = None
                dostawa_ref = None
                dostawca = None
                data_dostawy = None

                cursor.execute("""
                    SELECT id, order_ref, supplier, delivery_date, created_at, items 
                    FROM magazyn_dostawy 
                    WHERE items LIKE %s OR order_ref = %s
                    ORDER BY id DESC LIMIT 1
                """, (f"%{nr_palety}%", nr_partii))
                d_row = cursor.fetchone()
                if d_row:
                    dostawa_id = str(d_row.get('id') or '')[:8]
                    dostawa_ref = d_row.get('order_ref') or f"PZ #{dostawa_id}"
                    dostawca = (d_row.get('supplier') or '').strip()
                    d_date = d_row.get('delivery_date') or d_row.get('created_at')
                    data_dostawy = d_date.strftime('%Y-%m-%d') if hasattr(d_date, 'strftime') else str(d_date)[:10] if d_date else ''

                qr_details = {
                    "typ": typ_label,
                    "sscc": nr_palety,
                    "dostawa": dostawa_ref or (f"PZ #{dostawa_id}" if dostawa_id else '---'),
                    "dostawca": dostawca or '---',
                    "partia": nr_partii,
                    "data_dostawy": data_dostawy or data_produkcji,
                    "prod": product_name,
                    "ilosc": f"{qty_display:.2f}",
                    "jm": unit_str
                }
            else:
                table_pal = 'palety_agro' if linia == 'AGRO' else 'palety_workowanie'
                plan_id_val = label_data.get('plan_id')
                data_wytworzenia_str = ''
                data_przyjecia_str = ''

                cursor.execute(f"""
                    SELECT pw.data_dodania, pw.data_potwierdzenia, mp.data_potwierdzenia as mp_potwierdzenie, 
                           mp.created_at as mp_created, pw.plan_id, pw.nr_palety_lp
                    FROM magazyn_palety mp
                    LEFT JOIN {table_pal} pw ON mp.paleta_workowanie_id = pw.id
                    WHERE mp.nr_palety = %s OR mp.id = %s OR pw.nr_palety = %s
                    ORDER BY mp.id DESC LIMIT 1
                """, (nr_palety, search_id, nr_palety))
                ts_row = cursor.fetchone()

                if ts_row:
                    dt_prod = ts_row.get('data_dodania') or ts_row.get('mp_created')
                    dt_recv = ts_row.get('data_potwierdzenia') or ts_row.get('mp_potwierdzenie') or ts_row.get('mp_created') or dt_prod
                    if dt_prod:
                        data_wytworzenia_str = dt_prod.strftime('%Y-%m-%d %H:%M:%S') if hasattr(dt_prod, 'strftime') else str(dt_prod)
                    if dt_recv:
                        data_przyjecia_str = dt_recv.strftime('%Y-%m-%d %H:%M:%S') if hasattr(dt_recv, 'strftime') else str(dt_recv)
                    if not plan_id_val and ts_row.get('plan_id'):
                        plan_id_val = ts_row.get('plan_id')
                    if not nr_palety_lp and ts_row.get('nr_palety_lp'):
                        nr_palety_lp = ts_row.get('nr_palety_lp')

                if not data_wytworzenia_str:
                    data_wytworzenia_str = f"{data_produkcji} 00:00:00"
                if not data_przyjecia_str:
                    data_przyjecia_str = data_wytworzenia_str

                qr_details = {
                    "typ": f"{typ_label} - {linia}",
                    "sscc": nr_palety,
                    "zlecenie": str(plan_id_val or '---'),
                    "lp": str(nr_palety_lp or '---'),
                    "prod": product_name,
                    "wytworzono": data_wytworzenia_str,
                    "przyjeto_magazyn": data_przyjecia_str,
                    "partia": nr_partii,
                    "ilosc": f"{qty_display:.2f}",
                    "jm": unit_str
                }
        finally:
            conn.close()

        qr_details_safe = json.dumps(qr_details, ensure_ascii=False).replace('^', '').replace('~', '')

        partia_line = f"^FO40,900^A0N,45,45^FDNR PARTII: {nr_partii}^FS" if nr_partii and nr_partii != '---' else ""
        przydatnosc_line = f"^FO40,950^A0N,45,45^FDTERMIN PRZYDATNOŚCI: {data_przydatnosci}^FS" if data_przydatnosci and data_przydatnosci != '---' else ""
        plomba_line = f"^FO40,1000^A0N,45,45^FDNR PLOMBY: {nr_plomby}^FS" if nr_plomby else ""

        zpl_string = f"""^XA
^CI28
^PW812^LL1214
^FO20,20^GB772,1174,4^FS
^FO40,60^A0N,50,50^FD{header_zpl}^FS
^FO40,150^A0N,65,65^FB720,3,0,C^FD{product_name}^FS
^FO250,320^BQN,2,12^FDQA,{nr_palety}^FS
^FO40,650^A0N,55,55^FB720,1,0,C^FD{nr_palety}^FS
^FO40,750^A0N,50,50^FDNR PALETY: {nr_palety_lp or '---'}^FS
^FO40,850^A0N,50,50^FDPRODUKCJA: {data_produkcji}^FS
{partia_line}
{przydatnosc_line}
{plomba_line}
^FO40,1050^A0N,70,70^FD{qty_header}^FS
^FO40,1150^A0N,100,100^FD{qty_display:.2f} {unit_str}^FS
^FO583,975^BQN,2,3^FDQA,{qr_details_safe}^FS
^PQ1
^XZ"""

        return render_template(
            'magazyn_dostawy/etykieta_podglad.html',
            nr_palety=nr_palety,
            product_name=product_name,
            nr_partii=nr_partii,
            data_produkcji=data_produkcji,
            data_przydatnosci=data_przydatnosci,
            qty=qty_display,
            typ_label=typ_label,
            is_surowiec=is_surowiec,
            is_pkg=is_pkg,
            linia=linia,
            qr_details_json=json.dumps(qr_details, ensure_ascii=False),
            zpl_string=zpl_string,
            generated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        )
