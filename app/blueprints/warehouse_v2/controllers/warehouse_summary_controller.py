# File: app/blueprints/warehouse_v2/controllers/warehouse_summary_controller.py
"""Warehouse Summary Controller.

Handles aggregated product and inventory summary view for warehouse v2.
"""

from datetime import datetime
from typing import Any, Dict, List, Tuple
from flask import render_template, request

from app.db import get_db_connection, get_table_name
from app.blueprints.warehouse_v2.utils.date_formatters import (
    compute_expiry_date,
    format_date_val,
)


class WarehouseSummaryController:
    """Controller for warehouse summary and aggregated inventory."""

    @staticmethod
    def _summary_batch_key(pallet: Dict[str, Any]) -> Tuple[str, str]:
        exp = str(pallet.get('data_przydatnosci') or '')
        if not exp or exp == '-':
            exp = '9999-99-99'
        prod = str(pallet.get('data_produkcji') or '')
        if not prod or prod == '-':
            prod = '9999-99-99'
        return (exp, prod)

    @classmethod
    def _summary_fifo_key(cls, pallet: Dict[str, Any]) -> Tuple[str, str, int]:
        bk = cls._summary_batch_key(pallet)
        pid = int(pallet.get('id') or 0)
        return (bk[0], bk[1], pid)

    @classmethod
    def render_summary(cls):
        """Renders summary of all warehouse items aggregated by product name."""
        linia = request.args.get('linia', 'PSD').upper()
        palety_linie = ['PSD', 'AGRO'] if linia == 'ALL' else [linia]
        conn = get_db_connection()
        items: List[Dict[str, Any]] = []

        try:
            cursor = conn.cursor(dictionary=True)

            # 1. Surowce
            table_surowce = get_table_name('magazyn_surowce', linia)
            cursor.execute(
                f"SELECT id, nr_palety, nazwa as productName, lokalizacja as location, "
                f"stan_magazynowy as amount, 'Surowiec' as type, nr_partii, data_produkcji, data_przydatnosci "
                f"FROM {table_surowce} WHERE stan_magazynowy > 0"
            )
            for row in cursor.fetchall():
                row['unit'] = 'kg'
                row['displayId'] = row['nr_palety'] if row['nr_palety'] else f"SUR-{row['id']}"
                row['data_produkcji'] = format_date_val(row.get('data_produkcji'))
                row['data_przydatnosci'] = compute_expiry_date(row.get('data_przydatnosci'), row.get('data_produkcji'))
                items.append(row)

            # 2. Opakowania
            table_opakowania = get_table_name('magazyn_opakowania', linia)
            cursor.execute(
                f"SELECT id, nr_palety, nazwa as productName, lokalizacja as location, "
                f"stan_magazynowy as amount, 'Opakowanie' as type, nr_partii, data_produkcji, data_przydatnosci "
                f"FROM {table_opakowania} WHERE stan_magazynowy > 0"
            )
            for row in cursor.fetchall():
                row['unit'] = 'szt'
                row['displayId'] = row['nr_palety'] if row['nr_palety'] else f"OPK-{row['id']}"
                row['data_produkcji'] = format_date_val(row.get('data_produkcji'))
                row['data_przydatnosci'] = compute_expiry_date(row.get('data_przydatnosci'), row.get('data_produkcji'))
                items.append(row)

            # 3. Wyroby Gotowe
            for linia_palety in palety_linie:
                table_palety = get_table_name('magazyn_palety', linia_palety)
                table_plan = get_table_name('plan_produkcji', linia_palety)
                line_condition = "AND (m.linia = 'PSD' OR m.linia IS NULL OR m.linia = '')" if table_palety == 'magazyn_palety' else ""
                cursor.execute(f"""
                    SELECT m.id, m.nr_palety, 
                           COALESCE(NULLIF(TRIM(m.produkt), ''), plan.produkt, 'Nieznany produkt') as productName, 
                           COALESCE(NULLIF(TRIM(m.lokalizacja), ''), 'OCZEKUJĄCE') as location, 
                           m.waga_netto as amount, 
                           'Wyrób Gotowy' as type, 
                           COALESCE(NULLIF(TRIM(m.nr_partii), ''), plan.nr_partii) as nr_partii, 
                           COALESCE(NULLIF(TRIM(m.data_produkcji), ''), plan.data_produkcji, m.data_planu, plan.data_planu) as data_produkcji, 
                           COALESCE(NULLIF(TRIM(m.data_przydatnosci), ''), plan.termin_przydatnosci) as data_przydatnosci 
                    FROM {table_palety} m
                    LEFT JOIN {table_plan} plan ON m.plan_id = plan.id
                    WHERE m.waga_netto > 0 AND (m.is_loaded = 0 OR m.is_loaded IS NULL) {line_condition}
                """)
                for row in cursor.fetchall():
                    row['unit'] = 'kg'
                    row['displayId'] = row['nr_palety'] if row['nr_palety'] else f"PAL-{row['id']}"
                    row['data_produkcji'] = format_date_val(row.get('data_produkcji'))
                    row['data_przydatnosci'] = compute_expiry_date(row.get('data_przydatnosci'), row.get('data_produkcji'))
                    items.append(row)

            # 4. Dodatki
            cursor.execute(
                "SELECT id, nr_palety, nazwa as productName, lokalizacja as location, "
                "stan_magazynowy as amount, 'Dodatek' as type, nr_partii, data_produkcji, data_przydatnosci "
                "FROM magazyn_dodatki WHERE stan_magazynowy > 0"
            )
            for row in cursor.fetchall():
                row['unit'] = 'kg'
                row['displayId'] = row['nr_palety'] if row['nr_palety'] else f"DOD-{row['id']}"
                row['data_produkcji'] = format_date_val(row.get('data_produkcji'))
                row['data_przydatnosci'] = compute_expiry_date(row.get('data_przydatnosci'), row.get('data_produkcji'))
                items.append(row)

        except Exception as e:
            print(f"Error in WarehouseSummaryController.render_summary: {e}")
        finally:
            if conn:
                conn.close()

        # Group data by product name
        summary_data: Dict[str, Dict[str, Any]] = {}
        for it in items:
            name = it['productName']
            if name not in summary_data:
                summary_data[name] = {
                    'total': 0,
                    'count': 0,
                    'type': it['type'],
                    'unit': it['unit'],
                    'pallets': []
                }
            summary_data[name]['total'] += it['amount']
            summary_data[name]['count'] += 1
            summary_data[name]['pallets'].append(it)

        today_str = datetime.now().strftime('%Y-%m-%d')
        for _, data in summary_data.items():
            data['pallets'].sort(key=cls._summary_fifo_key)

            for p in data['pallets']:
                p_exp = str(p.get('data_przydatnosci') or '').strip()
                if p_exp and p_exp not in ('-', 'brak', '', 'None') and p_exp < today_str:
                    p['is_blocked'] = 1
                    p['is_system_blocked'] = 1

            valid_pallets = [p for p in data['pallets'] if not p.get('is_blocked')]
            earliest_bk = cls._summary_batch_key(valid_pallets[0]) if valid_pallets else ('9999-99-99', '9999-99-99')
            has_multiple_batches = any(cls._summary_batch_key(p) != earliest_bk for p in valid_pallets)

            unique_batches: List[Tuple[str, str]] = []
            for p in data['pallets']:
                bk = cls._summary_batch_key(p)
                if bk not in unique_batches:
                    unique_batches.append(bk)

            for idx, p in enumerate(data['pallets'], 1):
                bk = cls._summary_batch_key(p)
                batch_num = unique_batches.index(bk) + 1 if bk in unique_batches else 1
                is_eligible = not p.get('is_blocked')
                is_earliest = is_eligible and (bk == earliest_bk)
                p['fifo_index'] = idx
                p['fifo_batch_num'] = batch_num
                p['is_first_fifo'] = is_earliest and (has_multiple_batches or len(valid_pallets) > 1)

        return render_template('warehouse_v2/summary.html', summary=summary_data, linia=linia)
