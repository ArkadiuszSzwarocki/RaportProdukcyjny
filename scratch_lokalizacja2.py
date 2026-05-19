from app.db import get_db_connection

def test():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, nazwa, stan_magazynowy, lokalizacja FROM magazyn_surowce WHERE lokalizacja LIKE 'R01%' OR lokalizacja LIKE '01%' OR lokalizacja LIKE 'R-01%'")
    print("Surowce:", cur.fetchall())
    
    cur.execute("SELECT id, nazwa, stan_magazynowy, lokalizacja FROM magazyn_opakowania WHERE lokalizacja LIKE 'R01%' OR lokalizacja LIKE '01%' OR lokalizacja LIKE 'R-01%'")
    print("Opakowania:", cur.fetchall())
    
    cur.execute("SELECT id, nr_palety, lokalizacja FROM palety_psd_magazyn WHERE lokalizacja LIKE 'R01%' OR lokalizacja LIKE '01%' OR lokalizacja LIKE 'R-01%'")
    print("PSD:", cur.fetchall())

    conn.close()

if __name__ == '__main__':
    test()
