from datetime import datetime
from app.db import get_table_name

def _get_val(row, key, index):
    if row is None:
        return None
    if isinstance(row, dict):
        if key in row:
            return row[key]
        # fallback to getting by index for unaliased aggregations like COUNT(*)
        try:
            return list(row.values())[index]
        except (IndexError, AttributeError):
            return None
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

def prepare_pallet_label_data(cursor, paleta_id, linia='PSD', requested_plan_id=None, source_table=None):
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

    has_nr_palety_lp = False
    try:
        cursor.execute(f"SHOW COLUMNS FROM {table_pal} LIKE 'nr_palety_lp'")
        has_nr_palety_lp = bool(cursor.fetchone())
    except Exception:
        has_nr_palety_lp = False
    
    # 1. First attempt: Find in confirmed warehouse table
    params = []
    where_parts = []

    if source_table == 'magazyn':
        where_parts.append("mp.id = %s")
        params.append(paleta_id)
        order_clause = ""
        order_params = []
    elif source_table == 'workowanie':
        where_parts.append("mp.paleta_workowanie_id = %s")
        params.append(paleta_id)
        order_clause = ""
        order_params = []
    else:
        where_parts.append("(mp.id = %s OR mp.paleta_workowanie_id = %s)")
        params.extend([paleta_id, paleta_id])
        order_clause = "ORDER BY CASE WHEN mp.id = %s THEN 0 ELSE 1 END, mp.id DESC"
        order_params = [paleta_id]
        
    if requested_plan_id:
        where_parts.append("mp.plan_id = %s")
        params.append(requested_plan_id)

    where_clause = "WHERE " + " AND ".join(where_parts)
    final_params = tuple(params + order_params)

    cursor.execute(f"""
        SELECT
            mp.produkt,
            mp.waga_netto,
            COALESCE(pp.data_planu, mp.data_planu) AS data_planu,
            COALESCE(pp.id, mp.plan_id) AS plan_id,
            mp.nr_palety,
            mp.paleta_workowanie_id,
            pp.data_produkcji,
            mp.nr_plomby
        FROM {table_mag} mp
        LEFT JOIN {table_plan} pp ON mp.plan_id = pp.id
        {where_clause}
        {order_clause}
        LIMIT 1
    """, final_params)
    row = cursor.fetchone()
    
    if row:
        produkt = _get_val(row, 'produkt', 0)
        waga = _get_val(row, 'waga_netto', 1)
        data_planu = _get_val(row, 'data_planu', 2)
        plan_id = _get_val(row, 'plan_id', 3)
        nr_palety = _get_val(row, 'nr_palety', 4)
        pw_id_from_mag = _get_val(row, 'paleta_workowanie_id', 5)
        custom_data_prod = _get_val(row, 'data_produkcji', 6)
        nr_plomby = _get_val(row, 'nr_plomby', 7)
        
        # Decide production date
        if custom_data_prod:
            data_str = _format_date(custom_data_prod)
        else:
            data_str = _format_date(data_planu) or datetime.now().strftime('%Y-%m-%d')
            
        # Calculate zasyp_nr and nr_palety_lp from buffer
        zasyp_nr = '?'
        nr_palety_lp = 1
        try:
            pw_row = None
            if pw_id_from_mag:
                if has_nr_palety_lp:
                    cursor.execute(f"SELECT id, nr_palety_lp FROM {table_pal} WHERE id = %s LIMIT 1", (pw_id_from_mag,))
                else:
                    cursor.execute(f"SELECT id, NULL FROM {table_pal} WHERE id = %s LIMIT 1", (pw_id_from_mag,))
                pw_row = cursor.fetchone()

            if not pw_row and nr_palety:
                if has_nr_palety_lp:
                    cursor.execute(f"SELECT id, nr_palety_lp FROM {table_pal} WHERE nr_palety = %s ORDER BY id DESC LIMIT 1", (nr_palety,))
                else:
                    cursor.execute(f"SELECT id, NULL FROM {table_pal} WHERE nr_palety = %s ORDER BY id DESC LIMIT 1", (nr_palety,))
                pw_row = cursor.fetchone()

            if pw_row:
                pw_id = _get_val(pw_row, 'id', 0)
                stored_nr_palety_lp = _get_val(pw_row, 'nr_palety_lp', 1)
                
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

                if stored_nr_palety_lp not in (None, ''):
                    try:
                        nr_palety_lp = int(stored_nr_palety_lp)
                    except Exception:
                        nr_palety_lp = 1
                else:
                    cursor.execute(f"SELECT COUNT(*) FROM {table_pal} WHERE plan_id = %s AND id <= %s", (plan_id, pw_id))
                    res_lp = cursor.fetchone()
                    nr_palety_lp = _get_val(res_lp, 0, 0) if res_lp else 1
        except Exception:
            pass
            
        return {
            'nrPalety': nr_palety or str(paleta_id),
            'nazwa': produkt,
            'ilosc': float(waga),
            'data': data_str,
            'partia': f"ZASYP NR {zasyp_nr} (PALETA {nr_palety_lp})" if zasyp_nr != '?' else f"ZLE-{plan_id}",
            'nr_palety_lp': nr_palety_lp,
            'nr_plomby': nr_plomby
        }
        
    # 2. Second attempt: Find in buffer table (palety_workowanie)
    lp_select = "pw.nr_palety_lp" if has_nr_palety_lp else f"(SELECT COUNT(*) FROM {table_pal} sub WHERE sub.plan_id = pw.plan_id AND sub.id <= pw.id) AS nr_palety_lp"

    cursor.execute(f"""
        SELECT pw.plan_id, pw.waga, pp.produkt, pw.data_dodania, pw.nr_palety, pp.data_produkcji, {lp_select}, pw.nr_plomby
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
    stored_nr_palety_lp = _get_val(pw_row, 'nr_palety_lp', 6)
    nr_plomby = _get_val(pw_row, 'nr_plomby', 7)
    
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

        if stored_nr_palety_lp not in (None, ''):
            try:
                nr_palety_lp = int(stored_nr_palety_lp)
            except Exception:
                nr_palety_lp = 1
        else:
            cursor.execute(f"SELECT COUNT(*) FROM {table_pal} WHERE plan_id = %s AND id <= %s", (plan_id, paleta_id))
            res_lp = cursor.fetchone()
            nr_palety_lp = _get_val(res_lp, 0, 0) if res_lp else 1
    except Exception:
        pass
        
    return {
        'nrPalety': nr_palety or str(paleta_id),
        'nazwa': produkt,
        'ilosc': float(waga),
        'data': data_str,
        'partia': f"ZASYP NR {zasyp_nr} (PALETA {nr_palety_lp})",
        'nr_palety_lp': nr_palety_lp,
        'nr_plomby': nr_plomby
    }
