"""SQL-aware warehouse metadata for mocked receipt transactions."""
def configure_receipt_cursor(cursor, locations=('MGW01','MGW02','MP01','MS01','R01','R02')):
    original_one, original_all = cursor.fetchone.side_effect, cursor.fetchall.side_effect
    default_one, default_all = cursor.fetchone.return_value, cursor.fetchall.return_value
    def original(effect, default):
        if effect is None:
            return default
        return effect() if callable(effect) else next(effect)
    def one():
        sql=cursor.execute.call_args.args[0]
        if 'SELECT ENGINE AS engine' in sql:
            return {'engine':'InnoDB'}
        return original(original_one,default_one)
    def all_rows():
        sql=cursor.execute.call_args.args[0]
        if 'SELECT TABLE_NAME AS name' in sql:
            return [{'name':name} for name in ('magazyn_surowce','magazyn_agro_surowce',
                    'magazyn_opakowania','magazyn_agro_opakowania','magazyn_dodatki','magazyn_palety')]
        if 'SELECT nazwa FROM magazyn_dozwolone_lokalizacje' in sql:
            return [{'nazwa':location} for location in locations]
        rows=original(original_all,default_all)
        return [dict(row,nazwa=row['product_name']) if isinstance(row,dict) and 'product_name' in row and 'nazwa' not in row else row
                for row in rows]
    cursor.fetchone.side_effect=one
    cursor.fetchall.side_effect=all_rows
    return cursor
