# File: app/blueprints/warehouse_v2/controllers/pallet_report_controller.py
"""Pallet Report Controller.

Generates printable production and pallet balance reports for lines (e.g. PSD).
"""

from datetime import date, datetime
from typing import Any, Dict, List
from flask import current_app, jsonify, render_template, request

from app.db import get_db_connection


class PalletReportController:
    """Controller for printable and AJAX pallet production reports."""

    @staticmethod
    def render_pallet_report():
        """Generates a printable pallet report for PSD line with batch trace."""
        today = date.today()
        data_od = request.args.get('data_od') or request.args.get('data') or str(today)
        data_do = request.args.get('data_do') or request.args.get('data') or data_od
        plan_id = request.args.get('plan_id')
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            query = """
                SELECT w.id as work_id, w.produkt, w.tonaz_rzeczywisty as w_kg, 
                       z.id as zasyp_id, z.tonaz_rzeczywisty as z_kg,
                       w.nazwa_zlecenia, w.typ_produkcji, w.typ_opakowania, w.nr_partii,
                       z.typ_produkcji as zasyp_typ_produkcji, w.data_planu,
                       w.status,
                       0 as odrzuty_przesiewacz
                FROM plan_produkcji w
                LEFT JOIN plan_produkcji z ON w.zasyp_id = z.id
                WHERE (w.sekcja IN ('Workowanie', 'Czyszczenie') OR LOWER(w.produkt) LIKE '%czyszczenie%') 
                  AND (w.is_deleted = 0 OR w.is_deleted IS NULL)
            """
            params: List[Any] = []
            if plan_id:
                query += ' AND w.id = %s'
                params.append(plan_id)
            else:
                query += (
                    ' AND ((w.data_planu BETWEEN %s AND %s) '
                    'OR w.id IN (SELECT plan_id FROM palety_workowanie WHERE DATE(data_dodania) BETWEEN %s AND %s))'
                )
                params.extend([data_od, data_do, data_od, data_do])
                query += ' ORDER BY w.data_planu DESC, w.id DESC'

            cursor.execute(query, tuple(params))
            plans = cursor.fetchall() or []

            if plan_id and plans:
                data_planu = str(plans[0]['data_planu'])
            else:
                data_planu = data_od

            report_data: List[Dict[str, Any]] = []
            for p in plans:
                target_zasyp_id = p['zasyp_id'] if p.get('zasyp_id') else p['work_id']

                # Batches (szarze)
                cursor.execute("""
                    SELECT s.id, s.waga as waga, s.data_dodania 
                    FROM szarze s
                    WHERE s.plan_id = %s 
                    ORDER BY s.data_dodania ASC
                """, (target_zasyp_id,))
                batches_raw = cursor.fetchall() or []

                # Mixes
                mixes_raw = []
                try:
                    cursor.execute("""
                        SELECT id, waga, COALESCE(data_dodania, created_at) as data_dodania, kategoria 
                        FROM psd_mix_rozliczenie 
                        WHERE plan_id = %s 
                        ORDER BY data_dodania ASC
                    """, (target_zasyp_id,))
                    mixes_raw = cursor.fetchall() or []
                except Exception:
                    mixes_raw = []

                # Solo additions (dosypki)
                solo_dosypki = []
                try:
                    cursor.execute("""
                        SELECT id, nazwa, kg, data_zlecenia 
                        FROM dosypki 
                        WHERE plan_id = %s AND szarza_id IS NULL AND potwierdzone = 1 AND anulowana = 0
                        ORDER BY data_zlecenia ASC
                    """, (target_zasyp_id,))
                    solo_dosypki = cursor.fetchall() or []
                except Exception:
                    solo_dosypki = []

                # Big Bags
                bigbags_raw = []
                try:
                    cursor.execute("""
                        SELECT id, paleta_id, nr_palety, nazwa_produktu, waga_kg,
                               nr_partii, data_produkcji, data_przydatnosci, typ_palety,
                               lokalizacja_zrodlowa, autor_login, created_at, status
                        FROM agro_workowanie_bigbagi
                        WHERE plan_id = %s AND status = 'ZUZYTY'
                        ORDER BY created_at ASC, id ASC
                    """, (p['work_id'],))
                    bigbags_raw = cursor.fetchall() or []
                except Exception:
                    bigbags_raw = []

                total_bigbag_kg = sum(float(b['waga_kg'] or 0) for b in bigbags_raw)

                all_inputs: List[Dict[str, Any]] = []
                for b_raw in batches_raw:
                    all_inputs.append({
                        'label': f"Zasyp #{b_raw['id']}",
                        'waga': b_raw['waga'] or 0,
                        'time': b_raw['data_dodania']
                    })
                for d_raw in solo_dosypki:
                    all_inputs.append({
                        'label': f"Dosypka {d_raw['nazwa']} #{d_raw['id']}",
                        'waga': d_raw['kg'] or 0,
                        'time': d_raw['data_zlecenia']
                    })
                for m_raw in mixes_raw:
                    cat = m_raw.get('kategoria', 'MIX').replace('_', ' ') if m_raw.get('kategoria') else 'MIX'
                    all_inputs.append({
                        'label': f"MIX {cat} #{m_raw['id']}",
                        'waga': m_raw.get('waga') or m_raw.get('waga_kg') or 0,
                        'time': m_raw.get('data_dodania')
                    })
                for bb in bigbags_raw:
                    all_inputs.append({
                        'label': f"Big Bag {bb['nazwa_produktu']} #{bb['nr_palety'] or bb['id']}",
                        'waga': float(bb['waga_kg'] or 0),
                        'time': bb['created_at']
                    })

                all_inputs.sort(key=lambda x: x['time'] if x['time'] else datetime.min)

                current_in_kg = 0
                input_ranges = []
                for inp in all_inputs:
                    start = current_in_kg
                    end = current_in_kg + inp['waga']
                    input_ranges.append({'label': inp['label'], 'start': start, 'end': end})
                    current_in_kg = end

                # Pallets
                cursor.execute("""
                    SELECT 
                        p.id, p.waga, p.status, p.data_dodania, 
                        p.dodal_login,
                        NULLIF(TRIM(COALESCE(p.potwierdzil_login, m.user_login, '')), '') as potwierdzil_login,
                        COALESCE(p.data_potwierdzenia, m.data_potwierdzenia) as data_potwierdzenia,
                        COALESCE(m.nr_plomby, p.nr_plomby) as nr_plomby,
                        COALESCE(p.nr_palety, m.nr_palety) as nr_palety,
                        COALESCE(p.nr_palety_lp, m.nr_palety_lp) as nr_palety_lp
                    FROM palety_workowanie p
                    LEFT JOIN magazyn_palety m ON p.id = m.paleta_workowanie_id
                    WHERE p.plan_id = %s OR (%s IS NOT NULL AND p.plan_id = %s)
                    ORDER BY p.data_dodania ASC
                """, (p['work_id'], target_zasyp_id, target_zasyp_id))
                pallets_raw = cursor.fetchall() or []

                current_out_kg = 0
                processed_pallets = []
                for pal_raw in pallets_raw:
                    p_start = current_out_kg
                    p_end = current_out_kg + (pal_raw['waga'] or 0)
                    shares = []
                    for ir in input_ranges:
                        overlap_start = max(p_start, ir['start'])
                        overlap_end = min(p_end, ir['end'])
                        if overlap_end > overlap_start:
                            overlap_kg = overlap_end - overlap_start
                            waga_palety = float(pal_raw['waga'] or 0)
                            percent = overlap_kg / waga_palety * 100 if waga_palety > 0 else 0
                            if percent >= 0.5:
                                shares.append(f"{ir['label']} ({round(percent)}%)")
                    pal_raw['sklad'] = ', '.join(shares) if shares else 'Nieznany skład'
                    processed_pallets.append(pal_raw)
                    current_out_kg = p_end

                total_pallet_kg = sum(float(pal['waga'] or 0) for pal in pallets_raw)
                total_mix_kg = sum(float(m.get('waga') or m.get('waga_kg') or 0) for m in mixes_raw)

                report_data.append({
                    'plan': p,
                    'palety': processed_pallets,
                    'pallets': processed_pallets,
                    'mixes': mixes_raw,
                    'bigbags': bigbags_raw,
                    'opakowania': [],
                    'aktywne_opakowania': [],
                    'packaging_stocks': {},
                    'total_pallet_kg': total_pallet_kg,
                    'total_mix_kg': total_mix_kg,
                    'total_bigbag_kg': total_bigbag_kg,
                    'input_summary': ', '.join([f"{inp['label']} ({inp['waga']:.1f}kg)" for inp in all_inputs])
                })

            return render_template(
                'warehouse_v2/raport_palet.html',
                report_data=report_data,
                data_planu=data_planu,
                single_view=bool(plan_id),
                is_ajax=is_ajax,
                print_date=datetime.now().strftime('%d.%m.%Y %H:%M')
            )
        except Exception as e:
            current_app.logger.error(f'Error generating raport_palet in PalletReportController: {e}')
            if is_ajax:
                return jsonify({'success': False, 'error': str(e)})
            return render_template('warehouse_v2/raport_palet.html', report_data=[], data_planu='', error=str(e))
        finally:
            cursor.close()
            conn.close()
