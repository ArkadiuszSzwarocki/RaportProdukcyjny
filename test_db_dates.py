from app.db import get_db_connection
conn = get_db_connection()
cur = conn.cursor(dictionary=True)
for table in ['magazyn_surowce', 'magazyn_surowce_agro', 'magazyn_opakowania', 'magazyn_opakowania_agro', 'magazyn_dodatki']:
    try:
        cur.execute(f"SELECT id, nazwa, lokalizacja, nr_palety, nr_partii, data_produkcji, data_przydatnosci FROM {table} ORDER BY id DESC LIMIT 5")
        rows = cur.fetchall()
        if rows:
            print(f"=== {table} ===")
            for r in rows:
                print(r)
    except Exception as e:
        print(f"Error reading {table}: {e}")
