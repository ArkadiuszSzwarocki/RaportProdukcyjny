from datetime import datetime
from app.db import get_table_name

def _get_val(row, key, index):
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[index]
    except (IndexError, TypeError):
        return None

def _format_date(date_val):
    if date_val is None:
        return None
    if hasattr(date_val, 'strftime'):
        return date_val.strftime('%Y-%m-%d')
    return str(date_val)

def prepare_pallet_label_data(cursor, paleta_id, linia='PSD'):
    """
    Unifies finish-product label generation data between Flask routes
    (manual printing and dodaj_palete) and the PLC daemon.
    
    Supports dictionary cursors (used in daemon) and tuple cursors (used in Flask).
    """
    linia = str(linia).upper()
    table_plan = get_table_name('plan_produkcji', linia)
    table_pal = get_table_name('palety_workowanie', linia)
    table_mag = get_table_name('magazyn_palety', linia)
    table_zasypy = get_table_name('szarze', linia)
    
    # 1. First attempt: Find in confirmed warehouse table
    cursor.execute(f"""
        SELECT mp.produkt, mp.waga_netto, pp.data_planu, pp.id as plan_id, mp.nr_palety, pp.data_produkcji
        FROM {table_mag} mp
        JOIN {table_plan} pp ON mp.plan_id = pp.id
        WHERE mp.paleta_workowanie_id = %s OR mp.id = %s
    """, (paleta_id, paleta_id))
    row = cursor.fetchone()
    
    if row:
        produkt = _get_val(row, 'produkt', 0)
        waga = _get_val(row, 'waga_netto', 1)
        data_planu = _get_val(row, 'data_planu', 2)
        plan_id = _get_val(row, 'plan_id', 3)
        nr_palety = _get_val(row, 'nr_palety', 4)
        custom_data_prod = _get_val(row, 'data_produkcji', 5)
        
        # Decide production date
        if custom_data_prod:
            data_str = _format_date(custom_data_prod)
        else:
            data_str = _format_date(data_planu) or datetime.now().strftime('%Y-%m-%d')
            
        # Calculate zasyp_nr and nr_palety_lp from buffer
        zasyp_nr = '?'
        nr_palety_lp = 1
        try:
            cursor.execute(f"SELECT id FROM {table_pal} WHERE nr_palety = %s LIMIT 1", (nr_palety,))
            pw_row = cursor.fetchone()
            if pw_row:
                pw_id = _get_val(pw_row, 'id', 0)
                
                cursor.execute(
                    f"SELECT COALESCE(SUM(waga), 0) FROM {table_pal} WHERE plan_id = %s AND id <= %s",
                    (plan_id, pw_id),
                )
                cumulative_paleta_waga = _get_val(cursor.fetchone(), 0, 0)

                cursor.execute(f"SELECT zasyp_id FROM {table_plan} WHERE id = %s", (plan_id,))
                zasyp_check = cursor.fetchone()
                zasyp_plan_id = _get_val(zasyp_check, 'zasyp_id', 0) if (zasyp_check and _get_val(zasyp_check, 'zasyp_id', 0)) else plan_id

                cursor.execute(
                    f"SELECT id, waga, nr_szarzy FROM {table_zasypy} WHERE plan_id = %s ORDER BY data_dodania ASC, id ASC",
                    (zasyp_plan_id,),
                )
                zasypy_rows = cursor.fetchall()

                cumulative_zasyp = 0
                for index, s_row in enumerate(zasypy_rows):
                    cumulative_zasyp += float(_get_val(s_row, 'waga', 1) or 0)
                    s_nr = _get_val(s_row, 'nr_szarzy', 2)
                    zasyp_nr = s_nr if s_nr is not None else (index + 1)
                    if cumulative_zasyp >= cumulative_paleta_waga:
                        break

                cursor.execute(f"SELECT COUNT(*) FROM {table_pal} WHERE plan_id = %s AND id <= %s", (plan_id, pw_id))
                res_lp = cursor.fetchone()
                nr_palety_lp = _get_val(res_lp, 0, 0) if res_lp else 1
        except Exception:
            pass
            
        return {
            'nrPalety': nr_palety,
            'nazwa': produkt,
            'ilosc': float(waga),
            'data': data_str,
            'partia': f"ZASYP NR {zasyp_nr} (PALETA {nr_palety_lp})" if zasyp_nr != '?' else f"ZLE-{plan_id}"
        }
        
    # 2. Second attempt: Find in buffer table (palety_workowanie)
    cursor.execute(f"""
        SELECT pw.plan_id, pw.waga, pp.produkt, pw.data_dodania, pw.nr_palety, pp.data_produkcji
        FROM {table_pal} pw
        JOIN {table_plan} pp ON pw.plan_id = pp.id
        WHERE pw.id = %s
    """, (paleta_id,))
    pw_row = cursor.fetchone()
    
    if not pw_row:
        return None
        
    plan_id = _get_val(pw_row, 'plan_id', 0)
    waga = _get_val(pw_row, 'waga', 1)
    produkt = _get_val(pw_row, 'produkt', 2)
    data_dodania = _get_val(pw_row, 'data_dodania', 3)
    nr_palety = _get_val(pw_row, 'nr_palety', 4)
    custom_data_prod = _get_val(pw_row, 'data_produkcji', 5)
    
    # Decide production date
    if custom_data_prod:
        data_str = _format_date(custom_data_prod)
    else:
        data_str = _format_date(data_dodania) or datetime.now().strftime('%Y-%m-%d')
        
    # Calculate zasyp_nr and nr_palety_lp
    zasyp_nr = '?'
    nr_palety_lp = 1
    try:
        cursor.execute(
            f"SELECT COALESCE(SUM(waga), 0) FROM {table_pal} WHERE plan_id = %s AND id <= %s",
            (plan_id, paleta_id),
        )
        cumulative_paleta_waga = _get_val(cursor.fetchone(), 0, 0)

        cursor.execute(f"SELECT zasyp_id FROM {table_plan} WHERE id = %s", (plan_id,))
        zasyp_check = cursor.fetchone()
        zasyp_plan_id = _get_val(zasyp_check, 'zasyp_id', 0) if (zasyp_check and _get_val(zasyp_check, 'zasyp_id', 0)) else plan_id

        cursor.execute(
            f"SELECT id, waga, nr_szarzy FROM {table_zasypy} WHERE plan_id = %s ORDER BY data_dodania ASC, id ASC",
            (zasyp_plan_id,),
        )
        zasypy_rows = cursor.fetchall()

        cumulative_zasyp = 0
        for index, s_row in enumerate(zasypy_rows):
            cumulative_zasyp += float(_get_val(s_row, 'waga', 1) or 0)
            s_nr = _get_val(s_row, 'nr_szarzy', 2)
            zasyp_nr = s_nr if s_nr is not None else (index + 1)
            if cumulative_zasyp >= cumulative_paleta_waga:
                break

        cursor.execute(f"SELECT COUNT(*) FROM {table_pal} WHERE plan_id = %s AND id <= %s", (plan_id, paleta_id))
        res_lp = cursor.fetchone()
        nr_palety_lp = _get_val(res_lp, 0, 0) if res_lp else 1
    except Exception:
        pass
        
    return {
        'nrPalety': nr_palety,
        'nazwa': produkt,
        'ilosc': float(waga),
        'data': data_str,
        'partia': f"ZASYP NR {zasyp_nr} (PALETA {nr_palety_lp})"
    }
