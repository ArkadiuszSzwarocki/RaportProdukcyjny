import sys, os, json
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.db import get_db_connection
import datetime

conn = get_db_connection()
c = conn.cursor(dictionary=True)

c.execute("SELECT id, produkt, sekcja, status, typ_zlecenia, tonaz, tonaz_rzeczywisty, data_planu FROM plan_produkcji_agro WHERE typ_zlecenia='carry_over_ghost' ORDER BY id DESC LIMIT 10")
rows = c.fetchall()

def default_ser(o):
    if isinstance(o, (datetime.date, datetime.datetime)):
        return o.isoformat()

with open('tmp/ghost_out.json', 'w', encoding='utf-8') as f:
    json.dump(rows, f, indent=2, default=default_ser, ensure_ascii=False)

# also check bufor_agro
c.execute("""
    SELECT b.id, b.produkt, b.status as bufor_status, b.tonaz_rzeczywisty, b.spakowano, b.kolejka,
           z.id as zasyp_id, z.status as zasyp_status, z.typ_zlecenia,
           w.id as work_id, w.status as work_status, w.tonaz as work_tonaz
    FROM bufor_agro b
    JOIN plan_produkcji_agro z ON z.id = b.zasyp_id
    LEFT JOIN plan_produkcji_agro w ON w.zasyp_id = z.id AND w.sekcja = 'Workowanie'
    WHERE z.typ_zlecenia = 'carry_over_ghost'
    ORDER BY b.id DESC LIMIT 10
""")
bufor_rows = c.fetchall()

with open('tmp/bufor_ghost_out.json', 'w', encoding='utf-8') as f:
    json.dump(bufor_rows, f, indent=2, default=default_ser, ensure_ascii=False)

print('Done')
conn.close()
