import re
from datetime import datetime, date, timedelta
from app.db import get_table_name

def calculate_expiry_date(exp_val, prod_date_val=None, fmt='%Y-%m-%d') -> str:
    """
    Wyznacza sformatowaną datę przydatności (YYYY-MM-DD).
    Obsługuje:
      - Obiekty datetime/date oraz stringi ISO (np. '2027-08-28')
      - Wartości tekstowe interwałów (np. '12 miesięcy', '6 miesięcy', '24 miesiące', '180 dni', '1 rok', '12')
      - Domyślny fallback: data_produkcji + 1 rok (lub dziś + 1 rok).
    """
    if exp_val is not None and hasattr(exp_val, 'strftime'):
        try:
            return exp_val.strftime(fmt)
        except Exception:
            return str(exp_val)

    base_dt = None
    if prod_date_val is not None:
        if hasattr(prod_date_val, 'strftime'):
            base_dt = prod_date_val
        elif isinstance(prod_date_val, str) and prod_date_val.strip():
            for p_fmt in ('%Y-%m-%d', '%d.%m.%Y', '%Y/%m/%d', '%Y-%m-%d %H:%M:%S'):
                try:
                    base_dt = datetime.strptime(prod_date_val.strip()[:10], p_fmt).date()
                    break
                except Exception:
                    pass

    if base_dt is None:
        base_dt = date.today()
    elif isinstance(base_dt, datetime):
        base_dt = base_dt.date()

    exp_str = str(exp_val or '').strip()
    if exp_str and exp_str.lower() not in ('-', 'none', 'null', 'brak', '---'):
        for p_fmt in ('%Y-%m-%d', '%d.%m.%Y', '%Y/%m/%d'):
            try:
                parsed = datetime.strptime(exp_str[:10], p_fmt).date()
                return parsed.strftime(fmt)
            except Exception:
                pass

        match_months = re.search(r'(\d+)\s*(?:miesi|m-c|m\b|mies)', exp_str, re.IGNORECASE)
        if match_months:
            months = int(match_months.group(1))
            total_m = base_dt.month - 1 + months
            y = base_dt.year + total_m // 12
            m = total_m % 12 + 1
            d = min(base_dt.day, 28 if m == 2 else 30 if m in (4, 6, 9, 11) else 31)
            return date(y, m, d).strftime(fmt)

        match_days = re.search(r'(\d+)\s*(?:dni|d\b|dzień)', exp_str, re.IGNORECASE)
        if match_days:
            days = int(match_days.group(1))
            return (base_dt + timedelta(days=days)).strftime(fmt)

        match_years = re.search(r'(\d+)\s*(?:rok|lat|lata)', exp_str, re.IGNORECASE)
        if match_years:
            years = int(match_years.group(1))
            try:
                return base_dt.replace(year=base_dt.year + years).strftime(fmt)
            except Exception:
                return base_dt.replace(year=base_dt.year + years, day=28).strftime(fmt)

        if exp_str.isdigit():
            months = int(exp_str)
            total_m = base_dt.month - 1 + months
            y = base_dt.year + total_m // 12
            m = total_m % 12 + 1
            d = min(base_dt.day, 28 if m == 2 else 30 if m in (4, 6, 9, 11) else 31)
            return date(y, m, d).strftime(fmt)

    try:
        return base_dt.replace(year=base_dt.year + 1).strftime(fmt)
    except Exception:
        return base_dt.replace(year=base_dt.year + 1, day=28).strftime(fmt)

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

def is_packaging_item(name: str | None, unit: str | None = None, typ: str | None = None, pallet_nr: str | None = None) -> bool:
    """
    Sprawdza, czy towar to materiał opakowaniowy / pomocniczy (kalka, włóknina, etykiety, worki, kartony itp.),
    który na etykietach i wydrukach powinien mieć jednostkę 'szt.' zamiast 'kg'.
    """
    typ_norm = str(typ or '').lower().strip()
    if typ_norm in {'surowiec', 'raw_material', 'surowce', 'dodatek', 'dodatki', 'wyrób gotowy', 'wyrob gotowy', 'fg'}:
        return False

    name_norm = str(name or '').lower()
    unit_norm = str(unit or '').lower().strip()
    nr_norm = str(pallet_nr or '').upper().strip()

    if unit_norm in {'szt', 'szt.', 'sztuk', 'sztuki', 'pcs', 'pc'}:
        return True
    if typ_norm in {'opakowanie', 'packaging', 'opak', 'material_opakowaniowy', 'opakowania'}:
        return True
    if nr_norm.startswith('OPK') or nr_norm.startswith('OPA'):
        return True

    pkg_keywords = [
        'kalk',      # kalka, kalki, kalkę, kalka termiczna
        'włók',      # włóknina, włókninę, włókniny
        'wlok',      # wloknina, wloknine
        'etyk',      # etykieta, etykiety, etykietę
        'worek',     # worek, worki, worków
        'worki',
        'karton',    # karton, kartony, kartonów
        'taśm',      # taśma, taśmy
        'tasm',      # tasma, tasmy
        'foli',      # folia, folie, folii, stretch
        'opakow',    # opakowanie, opakowania
        'rolk',      # rolka, rolki
    ]
    return any(kw in name_norm for kw in pkg_keywords)

def lookup_raw_material_details_by_sscc(cursor, sscc_code):
    """
    Given an SSCC code (e.g. from skan_sscc or nr_palety), searches warehouse/production tables
    to retrieve original nr_partii, data_produkcji, and data_przydatnosci.
    """
    if not sscc_code:
        return {}
    
    sscc_code = str(sscc_code).strip()
    
    tables_surowce = ['magazyn_surowce', 'magazyn_agro_surowce']
    for tbl in tables_surowce:
        try:
            cursor.execute(
                f"SELECT nr_partii, data_produkcji, data_przydatnosci, nazwa AS produkt, stan_magazynowy AS waga "
                f"FROM {tbl} WHERE (LOWER(nr_palety) = LOWER(%s) OR id = %s) AND (nr_partii IS NOT NULL AND nr_partii <> '') ORDER BY id ASC LIMIT 1",
                (sscc_code, sscc_code)
            )
            row = cursor.fetchone()
            if row:
                r_dict = row if isinstance(row, dict) else {
                    'nr_partii': row[0], 'data_produkcji': row[1], 'data_przydatnosci': row[2], 'produkt': row[3], 'waga': row[4]
                }
                if any(r_dict.values()):
                    return r_dict
        except Exception:
            pass

    tables_mag = ['magazyn_palety', 'magazyn_palety_agro']
    for tbl in tables_mag:
        try:
            cursor.execute(
                f"SELECT nr_partii, data_produkcji, data_przydatnosci, produkt, waga_netto AS waga "
                f"FROM {tbl} WHERE LOWER(nr_palety) = LOWER(%s) AND (nr_partii IS NOT NULL AND nr_partii <> '') ORDER BY id ASC LIMIT 1",
                (sscc_code,)
            )
            row = cursor.fetchone()
            if row:
                r_dict = row if isinstance(row, dict) else {
                    'nr_partii': row[0], 'data_produkcji': row[1], 'data_przydatnosci': row[2], 'produkt': row[3], 'waga': row[4]
                }
                if any(r_dict.values()):
                    return r_dict
        except Exception:
            pass

    return {}

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

    has_nr_partii = False
    try:
        cursor.execute(f"SHOW COLUMNS FROM {table_plan} LIKE 'nr_partii'")
        has_nr_partii = bool(cursor.fetchone())
    except Exception:
        has_nr_partii = False

    has_termin_przydatnosci = False
    try:
        cursor.execute(f"SHOW COLUMNS FROM {table_plan} LIKE 'termin_przydatnosci'")
        has_termin_przydatnosci = bool(cursor.fetchone())
    except Exception:
        has_termin_przydatnosci = False
    
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

    partia_select = "pp.nr_partii" if has_nr_partii else "NULL AS nr_partii"
    przyd_plan_select = "pp.termin_przydatnosci" if has_termin_przydatnosci else "NULL"
    cursor.execute(f"""
        SELECT
            COALESCE(mp.produkt, pp.produkt) AS produkt,
            CASE WHEN mp.waga_netto > 0 THEN mp.waga_netto ELSE COALESCE(pw.waga, mp.waga_netto) END AS waga_netto,
            COALESCE(pp.data_planu, mp.data_planu, pw.data_dodania) AS data_planu,
            COALESCE(pp.id, mp.plan_id, pw.plan_id) AS plan_id,
            COALESCE(mp.nr_palety, pw.nr_palety) AS nr_palety,
            mp.paleta_workowanie_id,
            COALESCE(pp.data_produkcji, mp.data_produkcji, pw.data_dodania) AS data_produkcji,
            COALESCE(mp.nr_plomby, pw.nr_plomby) AS nr_plomby,
            COALESCE(mp.data_przydatnosci, {przyd_plan_select}) AS data_przydatnosci,
            {partia_select}
        FROM {table_mag} mp
        LEFT JOIN {table_pal} pw ON mp.paleta_workowanie_id = pw.id
        LEFT JOIN {table_plan} pp ON (mp.plan_id = pp.id OR pw.plan_id = pp.id)
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
        data_przydatnosci = _get_val(row, 'data_przydatnosci', 8)
        nr_partii_db = _get_val(row, 'nr_partii', 9)
        
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
            
        is_surowiec = False
        prod_str = str(produkt or '').strip()
        if prod_str.lower() in ('czyszczenie', 'maka mix do lnu', 'mąka mix do lnu') or 'czyszczenie' in prod_str.lower() or 'maka mix do lnu' in prod_str.lower() or 'mąka mix do lnu' in prod_str.lower():
            produkt = 'Mąka mix do Lnu'
            is_surowiec = True
            if not nr_partii_db or str(nr_partii_db) in ('None', ''):
                orig_meta = lookup_raw_material_details_by_sscc(cursor, nr_palety)
                if orig_meta.get('nr_partii'):
                    nr_partii_db = orig_meta.get('nr_partii')
                if orig_meta.get('data_produkcji'):
                    data_str = _format_date(orig_meta.get('data_produkcji'))

        partia_resolved = nr_partii_db if (nr_partii_db and str(nr_partii_db) not in ('None', '')) else (f"ZASYP NR {zasyp_nr} (PALETA {nr_palety_lp})" if zasyp_nr != '?' else f"ZLE-{plan_id}")
        
        przydatnosc_str = calculate_expiry_date(data_przydatnosci, data_str)

        return {
            'nrPalety': nr_palety or str(paleta_id),
            'nazwa': produkt,
            'ilosc': float(waga),
            'data': data_str,
            'data_produkcji': data_str,
            'data_przydatnosci': przydatnosc_str,
            'termin_przydatnosci': przydatnosc_str,
            'partia': partia_resolved,
            'nr_partii': partia_resolved,
            'nr_szarzy': zasyp_nr,
            'plan_id': plan_id,
            'nr_palety_lp': nr_palety_lp,
            'nr_plomby': nr_plomby,
            'is_surowiec': is_surowiec,
            'linia': linia
        }
        
    # 2. Second attempt: Find in buffer table (palety_workowanie)
    lp_select = "pw.nr_palety_lp" if has_nr_palety_lp else f"(SELECT COUNT(*) FROM {table_pal} sub WHERE sub.plan_id = pw.plan_id AND sub.id <= pw.id) AS nr_palety_lp"

    partia_select_pw = "pp.nr_partii" if has_nr_partii else "NULL AS nr_partii"
    cursor.execute(f"""
        SELECT pw.plan_id, pw.waga, pp.produkt, pw.data_dodania, pw.nr_palety, pp.data_produkcji, {lp_select}, pw.nr_plomby, {partia_select_pw}, COALESCE(mp.data_przydatnosci, {przyd_plan_select}) AS data_przydatnosci
        FROM {table_pal} pw
        JOIN {table_plan} pp ON pw.plan_id = pp.id
        LEFT JOIN {table_mag} mp ON pw.plan_id = mp.plan_id
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
    nr_partii_db = _get_val(pw_row, 'nr_partii', 8)
    data_przydatnosci = _get_val(pw_row, 'data_przydatnosci', 9)
    
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
        
    is_surowiec = False
    prod_str = str(produkt or '').strip()
    if prod_str.lower() in ('czyszczenie', 'maka mix do lnu', 'mąka mix do lnu') or 'czyszczenie' in prod_str.lower() or 'maka mix do lnu' in prod_str.lower() or 'mąka mix do lnu' in prod_str.lower():
        produkt = 'Mąka mix do Lnu'
        is_surowiec = True
        if not nr_partii_db or str(nr_partii_db) in ('None', ''):
            orig_meta = lookup_raw_material_details_by_sscc(cursor, nr_palety)
            if orig_meta.get('nr_partii'):
                nr_partii_db = orig_meta.get('nr_partii')
            if orig_meta.get('data_produkcji'):
                data_str = _format_date(orig_meta.get('data_produkcji'))

    partia_resolved = nr_partii_db if (nr_partii_db and str(nr_partii_db) not in ('None', '')) else (f"ZASYP NR {zasyp_nr} (PALETA {nr_palety_lp})" if zasyp_nr != '?' else f"ZLE-{plan_id}")
    
    przydatnosc_str = calculate_expiry_date(data_przydatnosci, data_str)

    return {
        'nrPalety': nr_palety or str(paleta_id),
        'nazwa': produkt,
        'ilosc': float(waga),
        'data': data_str,
        'data_produkcji': data_str,
        'data_przydatnosci': przydatnosc_str,
        'termin_przydatnosci': przydatnosc_str,
        'partia': partia_resolved,
        'nr_partii': partia_resolved,
        'nr_szarzy': zasyp_nr,
        'plan_id': plan_id,
        'nr_palety_lp': nr_palety_lp,
        'nr_plomby': nr_plomby,
        'is_surowiec': is_surowiec,
        'linia': linia
    }
