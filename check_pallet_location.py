import sys
from app.db import get_db_connection

def main():
    code = 'SUR000001781247737678'.upper()
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    # Check surowce
    cur.execute("SELECT nr_palety, nazwa, lokalizacja FROM magazyn_surowce WHERE nr_palety = %s", (code,))
    row = cur.fetchone()
    if row:
        print('surowce', row)
        return
    # opakowania
    cur.execute("SELECT nr_palety, nazwa, lokalizacja FROM magazyn_opakowania WHERE nr_palety = %s", (code,))
    row = cur.fetchone()
    if row:
        print('opakowania', row)
        return
    # dodatki
    cur.execute("SELECT nr_palety, nazwa, lokalizacja FROM magazyn_dodatki WHERE nr_palety = %s", (code,))
    row = cur.fetchone()
    if row:
        print('dodatki', row)
        return
    # wyroby PSD
    cur.execute("SELECT nr_palety, produkt as nazwa, lokalizacja FROM magazyn_palety WHERE nr_palety = %s", (code,))
    row = cur.fetchone()
    if row:
        print('palety_psd', row)
        return
    # wyroby AGRO
    cur.execute("SELECT nr_palety, produkt as nazwa, lokalizacja FROM magazyn_palety_agro WHERE nr_palety = %s", (code,))
    row = cur.fetchone()
    if row:
        print('palety_agro', row)
        return
    print('not found')
    
if __name__ == '__main__':
    main()
