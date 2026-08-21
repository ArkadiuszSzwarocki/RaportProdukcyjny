from app.db import get_db_connection
from datetime import datetime

conn = get_db_connection()
cur = conn.cursor()
cur.execute("SELECT id, paleta_workowanie_id, plan_id, produkt, waga_netto, waga_brutto, tara, user_login, data_potwierdzenia, created_at FROM magazyn_palety ORDER BY data_potwierdzenia DESC LIMIT 20")
mag = cur.fetchall()
print('magazyn_palety (last 20):')
for r in mag:
    print(r)
    pwid = r[1]
    if pwid:
        cur.execute("SELECT id, waga, tara, waga_brutto, data_dodania, data_potwierdzenia, czas_rzeczywistego_potwierdzenia, czas_potwierdzenia_s FROM palety_workowanie WHERE id=%s", (pwid,))
        pw = cur.fetchone()
        print('  -> palety_workowanie:', pw)

cur.close()
conn.close()
