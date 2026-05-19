from app.db import get_db_connection

def test():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    
    # 1. Sprawdzamy surowce z R030601 lub %030601%
    cur.execute("SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja FROM magazyn_surowce LIMIT 5")
    print("Surowce LIMIT 5:", cur.fetchall())
    
    cur.execute("SELECT id, nazwa, lokalizacja FROM magazyn_surowce WHERE lokalizacja LIKE '%030601%'")
    print("Surowce LIKE %030601%:", cur.fetchall())
    
    # 2. To samo dla palet_psd i palet_agro (jesli trzeba bedzie, ale zobaczmy surowce)
    conn.close()

if __name__ == '__main__':
    test()
