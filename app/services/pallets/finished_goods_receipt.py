# cspell:words sscc lastrowid
"""Shared stock/history writer while legacy line tables await verified migration."""
import math

from app.db import get_table_name


class FinishedGoodsReceipt:
    @staticmethod
    def write(connection, *, line, production_id, code, product, quantity, location,
              login, plan_id=None, plan_date=None, gross=0, tare=0, batch=None,
              production_date=None, expiry=None, seal=None, sequence=None):
        code = str(code or '').strip().upper()
        quantity = float(quantity or 0)
        if not code or not math.isfinite(quantity) or quantity <= 0:
            raise ValueError('Przyjęcie wymaga SSCC i dodatniej, poprawnej wagi.')
        from app.utils.location_validator import validate_warehouse_location, normalize_warehouse_location
        location = normalize_warehouse_location(location)
        valid, error = validate_warehouse_location(location,allow_empty=False)
        if not valid:
            raise ValueError(error)
        cursor = connection.cursor(dictionary=True)
        # The production row must already be locked by the caller. No commit here.
        for table in ('magazyn_palety', 'magazyn_palety_agro'):
            cursor.execute(f'SELECT id FROM {table} WHERE UPPER(nr_palety)=%s AND waga_netto>0 FOR UPDATE', (code,))
            if cursor.fetchall():
                raise ValueError(f'Paleta {code} ma już dodatni stan magazynowy; sprawdź wcześniejsze przyjęcie.')
        from app.utils.location_validator import check_rack_location_availability
        available, error = check_rack_location_availability(location,current_nr_palety=code,product_name=product,cursor=cursor)
        if not available:
            raise ValueError(error)
        table = get_table_name('magazyn_palety',line)
        values = dict(paleta_workowanie_id=production_id,plan_id=plan_id,data_planu=plan_date,
                      produkt=product,waga_netto=quantity,waga_brutto=gross,tara=tare,
                      lokalizacja=location,user_login=login,nr_palety=code,linia=line,
                      nr_partii=batch or None,data_produkcji=production_date or None,
                      data_przydatnosci=expiry or None,nr_plomby=seal)
        cursor.execute(f"SHOW COLUMNS FROM {table} LIKE 'nr_palety_lp'")
        if cursor.fetchone():
            if sequence is None:
                production_table = get_table_name('palety_workowanie',line)
                cursor.execute(f"SHOW COLUMNS FROM {production_table} LIKE 'nr_palety_lp'")
                if cursor.fetchone():
                    cursor.execute(f'SELECT nr_palety_lp FROM {production_table} WHERE id=%s',(production_id,))
                    row = cursor.fetchone()
                    sequence = row.get('nr_palety_lp') if row else None
            values['nr_palety_lp'] = sequence
        cursor.execute(f"INSERT INTO {table} ({','.join(values)}) VALUES({','.join(['%s'] * len(values))})",tuple(values.values()))
        warehouse_id = cursor.lastrowid
        cursor.execute('''INSERT INTO palety_historia
            (paleta_id,nr_palety,linia,typ_palety,akcja,lokalizacja_zrodlowa,lokalizacja_docelowa,komentarz,user_login)
            VALUES(%s,%s,%s,'wyrob_gotowy','PRZYJECIE_WG','OCZEKUJĄCE',%s,%s,%s)''',
            (warehouse_id,code,line,location,f'Przyjęcie wyrobu gotowego z produkcji: {product}',login))
        return warehouse_id
