from app.db import get_db_connection
conn = get_db_connection()
cur = conn.cursor()
cur.execute("SELECT id, paleta_workowanie_id, plan_id, produkt, waga_netto, data_potwierdzenia FROM magazyn_palety ORDER BY data_potwierdzenia DESC LIMIT 20")
mag = cur.fetchall()
print('magazyn_palety (last 20):')
for r in mag:
    print(r)
    pwid = r[1]
    if pwid:
        cur.execute("SELECT id, waga, data_dodania, data_potwierdzenia, czas_rzeczywistego_potwierdzenia, TIME_TO_SEC(czas_rzeczywistego_potwierdzenia) FROM palety_workowanie WHERE id=%s", (pwid,))
        pw = cur.fetchone()
        print('  -> palety_workowanie raw:', pw)

cur.close()
conn.close()
