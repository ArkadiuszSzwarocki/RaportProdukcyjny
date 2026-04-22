import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.db import get_db_connection

conn = get_db_connection()
c = conn.cursor()

c.execute("UPDATE plan_produkcji_agro SET status='zaplanowane' WHERE typ_zlecenia='carry_over_ghost' AND status='zakonczone' AND data_planu >= CURDATE()")
n = c.rowcount
conn.commit()
print(f'Naprawiono {n} ghost Zasypow w AGRO (zakonczone -> zaplanowane)')

c.execute("UPDATE plan_produkcji SET status='zaplanowane' WHERE typ_zlecenia='carry_over_ghost' AND status='zakonczone' AND data_planu >= CURDATE()")
n2 = c.rowcount
conn.commit()
print(f'Naprawiono {n2} ghost Zasypow w PSD (zakonczone -> zaplanowane)')

# Verify
c.execute("SELECT id, produkt, sekcja, status, typ_zlecenia FROM plan_produkcji_agro WHERE typ_zlecenia='carry_over_ghost' ORDER BY id DESC LIMIT 10")
rows = c.fetchall()
for row in rows:
    print(row)

conn.close()
