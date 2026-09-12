import re
from datetime import datetime as dt_mod, timedelta
from flask import jsonify, request
from app.db import get_db_connection, get_table_name
from app.services.warehouse_v2_service import WarehouseV2Service
from app.blueprints.warehouse_v2.utils import compute_expiry_date, classify_packaging_type

class PalletQueryController:
    @staticmethod
    def get_history():
        """Retrieve full pallet movement and lifecycle history."""
        pallet_id = request.args.get('id')
        pallet_type = request.args.get('type')
        linia = request.args.get('linia', 'PSD')
        sscc = request.args.get('sscc')
        
        if not pallet_id and not sscc:
            return jsonify({'success': False, 'error': 'Brak parametrów'}), 400
            
        history = WarehouseV2Service.get_pallet_history(pallet_id, pallet_type, linia, sscc=sscc)
        return jsonify({'success': True, 'history': history})

    @staticmethod
    def get_pallet_details():
        """Fetch unified pallet details with location/batch fallback lookups."""
        pallet_id = request.args.get('id')
        pallet_type = request.args.get('type')
        linia = request.args.get('linia', 'PSD')
        
        if not pallet_id or not pallet_type:
            return jsonify({'success': False, 'error': 'Brak parametrów'}), 400
            
        conn = get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            t_type = (pallet_type or '').strip()
            if t_type == 'Surowiec':
                t_name = get_table_name('magazyn_surowce', linia)
                cur.execute(f"SELECT *, nazwa as productName, stan_magazynowy as amount, 'kg' as unit FROM {t_name} WHERE id = %s OR nr_palety = %s", (pallet_id, pallet_id))
            elif t_type == 'Opakowanie':
                t_name = get_table_name('magazyn_opakowania', linia)
                cur.execute(f"SELECT *, nazwa as productName, stan_magazynowy as amount, 'szt' as unit FROM {t_name} WHERE id = %s OR nr_palety = %s", (pallet_id, pallet_id))
            elif t_type == 'Dodatek':
                t_name = 'magazyn_dodatki'
                cur.execute(f"SELECT *, nazwa as productName, stan_magazynowy as amount, 'kg' as unit FROM {t_name} WHERE id = %s OR nr_palety = %s", (pallet_id, pallet_id))
            else:
                t_name = get_table_name('magazyn_palety', linia)
                table_plan = get_table_name('plan_produkcji', linia)
                cur.execute(f"""
                    SELECT m.*, 
                           COALESCE(NULLIF(TRIM(m.produkt), ''), plan.produkt, 'Nieznany produkt') as productName, 
                           m.waga_netto as amount, 
                           'kg' as unit,
                           COALESCE(NULLIF(TRIM(m.nr_partii), ''), plan.nr_partii) as nr_partii,
                           COALESCE(NULLIF(TRIM(m.data_produkcji), ''), plan.data_produkcji, m.data_planu, plan.data_planu) as data_produkcji,
                           COALESCE(NULLIF(TRIM(m.data_przydatnosci), ''), plan.termin_przydatnosci) as data_przydatnosci,
                           COALESCE(m.created_at, m.data_potwierdzenia) as created_at
                    FROM {t_name} m
                    LEFT JOIN {table_plan} plan ON m.plan_id = plan.id
                    WHERE m.id = %s OR m.nr_palety = %s
                """, (pallet_id, pallet_id))
                
            row = cur.fetchone()
            if not row and t_type != 'Dodatek':
                alt_linia = 'PSD' if str(linia).upper() == 'AGRO' else 'AGRO'
                if t_type == 'Surowiec':
                    alt_t = get_table_name('magazyn_surowce', alt_linia)
                    cur.execute(f"SELECT *, nazwa as productName, stan_magazynowy as amount, 'kg' as unit FROM {alt_t} WHERE id = %s OR nr_palety = %s", (pallet_id, pallet_id))
                elif t_type == 'Opakowanie':
                    alt_t = get_table_name('magazyn_opakowania', alt_linia)
                    cur.execute(f"SELECT *, nazwa as productName, stan_magazynowy as amount, 'szt' as unit FROM {alt_t} WHERE id = %s OR nr_palety = %s", (pallet_id, pallet_id))
                else:
                    alt_t = get_table_name('magazyn_palety', alt_linia)
                    alt_plan = get_table_name('plan_produkcji', alt_linia)
                    cur.execute(f"""
                        SELECT m.*, 
                               COALESCE(NULLIF(TRIM(m.produkt), ''), plan.produkt, 'Nieznany produkt') as productName, 
                               m.waga_netto as amount, 
                               'kg' as unit,
                               COALESCE(NULLIF(TRIM(m.nr_partii), ''), plan.nr_partii) as nr_partii,
                               COALESCE(NULLIF(TRIM(m.data_produkcji), ''), plan.data_produkcji, m.data_planu, plan.data_planu) as data_produkcji,
                               COALESCE(NULLIF(TRIM(m.data_przydatnosci), ''), plan.termin_przydatnosci) as data_przydatnosci,
                               COALESCE(m.created_at, m.data_potwierdzenia) as created_at
                        FROM {alt_t} m
                        LEFT JOIN {alt_plan} plan ON m.plan_id = plan.id
                        WHERE m.id = %s OR m.nr_palety = %s
                    """, (pallet_id, pallet_id))
                row = cur.fetchone()
                if row:
                    linia = alt_linia

            if not row:
                return jsonify({'success': False, 'error': 'Nie znaleziono palety'}), 404
                
            def fmt_d(val, fmt='%Y-%m-%d'):
                if not val: return '-'
                if hasattr(val, 'strftime'): return val.strftime(fmt)
                return str(val)[:10]

            p_sscc = row.get('nr_palety') or str(pallet_id)
            p_real_id = row.get('id')

            loc_val = row.get('lokalizacja') or row.get('location')
            if not loc_val or str(loc_val).strip() in ('-', '', 'None', 'null'):
                try:
                    exp_type = '%wyrob%' if t_type in ('Wyrob', 'Wyroby', 'Paleta') else f"%{t_type.lower()}%"
                    cur.execute("""
                        SELECT lokalizacja_docelowa 
                        FROM palety_historia 
                        WHERE (nr_palety = %s OR (paleta_id = %s AND (nr_palety IS NULL OR nr_palety = '' OR nr_palety = %s) AND (typ_palety LIKE %s OR typ_palety IS NULL)))
                          AND lokalizacja_docelowa IS NOT NULL 
                          AND lokalizacja_docelowa NOT IN ('', '-', 'None', 'null') 
                        ORDER BY data_ruchu DESC, id DESC LIMIT 1
                    """, (p_sscc, p_real_id, p_sscc, exp_type))
                    loc_row = cur.fetchone()
                    if loc_row and loc_row.get('lokalizacja_docelowa'):
                        loc_val = loc_row['lokalizacja_docelowa']
                except Exception:
                    pass
                if not loc_val or str(loc_val).strip() in ('-', '', 'None', 'null'):
                    try:
                        for t_ruch_name in ['magazyn_ruch', 'magazyn_agro_ruch']:
                            cur.execute(f"""
                                SELECT lokalizacja 
                                FROM {t_ruch_name} 
                                WHERE (surowiec_id = %s OR komentarz LIKE %s)
                                  AND lokalizacja IS NOT NULL 
                                  AND lokalizacja NOT IN ('', '-', 'None', 'null') 
                                ORDER BY id DESC LIMIT 1
                            """, (p_real_id, f"%{p_sscc}%"))
                            loc_row2 = cur.fetchone()
                            if loc_row2 and loc_row2.get('lokalizacja'):
                                loc_val = loc_row2['lokalizacja']
                                break
                    except Exception:
                        pass

            if not loc_val or str(loc_val).strip() in ('-', '', 'None', 'null'):
                if t_type in ('Wyrob', 'Wyroby', 'Paleta', 'Wyrób Gotowy'):
                    loc_val = 'OCZEKUJĄCE'

            batch_val = row.get('nr_partii')
            if not batch_val or str(batch_val).strip() in ('-', ''):
                pw_id = row.get('paleta_workowanie_id')
                if pw_id:
                    try:
                        pw_tbl = get_table_name('palety_workowanie', linia)
                        plan_tbl = get_table_name('plan_produkcji', linia)
                        cur.execute(f"""
                            SELECT COALESCE(NULLIF(TRIM(pw.nr_plomby), ''), NULLIF(TRIM(pp.nr_partii), '')) as b_val
                            FROM {pw_tbl} pw
                            LEFT JOIN {plan_tbl} pp ON pw.plan_id = pp.id
                            WHERE pw.id = %s LIMIT 1
                        """, (pw_id,))
                        b_row = cur.fetchone()
                        if b_row and b_row.get('b_val'):
                            batch_val = b_row['b_val']
                    except Exception:
                        pass
                if not batch_val or str(batch_val).strip() in ('-', ''):
                    try:
                        cur.execute("""
                            SELECT komentarz FROM palety_historia 
                            WHERE (nr_palety = %s OR paleta_id = %s) AND komentarz LIKE '%partia%' 
                            ORDER BY id DESC LIMIT 1
                        """, (p_sscc, p_real_id))
                        kom_row = cur.fetchone()
                        if kom_row and kom_row.get('komentarz'):
                            m_part = re.search(r'partia:\s*([A-Za-z0-9\-_\/]+)', kom_row['komentarz'], re.IGNORECASE)
                            if m_part:
                                batch_val = m_part.group(1).strip()
                    except Exception:
                        pass

            calc_exp = compute_expiry_date(row.get('data_przydatnosci'), row.get('data_produkcji'))
            if not calc_exp or calc_exp == '-':
                d_prod = row.get('data_produkcji')
                if d_prod:
                    try:
                        if isinstance(d_prod, str):
                            dt_p = dt_mod.strptime(d_prod[:10], '%Y-%m-%d')
                        else:
                            dt_p = d_prod
                        calc_exp = (dt_p + timedelta(days=180)).strftime('%Y-%m-%d')
                    except Exception:
                        pass

            pkg_formatted = classify_packaging_type(
                row.get('productName') or row.get('nazwa') or row.get('produkt'),
                t_type,
                float(row.get('amount') or 0),
                row.get('unit') or 'kg',
                row.get('typ_opakowania') or ''
            )

            details = {
                'id': row.get('id'),
                'displayId': row.get('nr_palety') or f"PAL-{row.get('id')}",
                'productName': row.get('productName') or row.get('nazwa') or row.get('produkt') or '-',
                'amount': float(row.get('amount') or 0),
                'unit': row.get('unit') or 'kg',
                'location': loc_val or '-',
                'batch': batch_val or '-',
                'date_prod': fmt_d(row.get('data_produkcji')),
                'date_exp': calc_exp or '-',
                'date_added': fmt_d(row.get('created_at'), '%Y-%m-%d %H:%M'),
                'type': t_type,
                'is_blocked': row.get('is_blocked', 0),
                'packaging_type': pkg_formatted,
                'raw_packaging_type': row.get('typ_opakowania') or 'Karton'
            }
            return jsonify({'success': True, 'pallet': details})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
        finally:
            conn.close()
