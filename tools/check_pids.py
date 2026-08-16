import sys
sys.path.append('a:\\GitHub\\RaportProdukcyjny')
from app.core.database import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute("USE biblioteka")

for pid in [94, 84]:
    print(f"--- ID {pid} ---")
    for t in ['magazyn_surowce', 'magazyn_agro_surowce', 'magazyn_agro_opakowania', 'magazyn_agro_slownik_surowce']:
        try:
            cursor.execute(f"SELECT * FROM {t} WHERE id = %s", (pid,))
            res = cursor.fetchall()
            if res:
                print(f"Found in {t}:")
                for r in res:
                    print(r)
        except Exception as e:
            pass

cursor.close()
conn.close()
