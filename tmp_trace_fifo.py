from app.db import get_db_connection, get_table_name
from datetime import date
dzisiaj = date(2026, 3, 31)
aktywna_linia = 'PSD'

conn = get_db_connection()
cursor = conn.cursor()
table_bufor = get_table_name('bufor', aktywna_linia)
table_plan = get_table_name('plan_produkcji', aktywna_linia)

q1 = f"""
    SELECT MIN(b.kolejka) as global_min_queue
    FROM {table_bufor} b
    WHERE DATE(b.data_planu) = %s AND b.status = 'aktywny'
      AND EXISTS (
          SELECT 1 FROM {table_plan} w
          WHERE w.sekcja = 'Workowanie' AND w.status IN ('zaplanowane', 'w toku')
            AND w.produkt = b.produkt AND DATE(w.data_planu) = DATE(b.data_planu)
      )
"""
cursor.execute(q1, (dzisiaj,))
res1 = cursor.fetchone()
print(f"Global Min Queue: {res1[0]}")

if res1[0] is not None:
    q2 = f"""
        SELECT DISTINCT produkt
        FROM {table_bufor} 
        WHERE DATE(data_planu) = %s AND status = 'aktywny' AND kolejka = %s
    """
    cursor.execute(q2, (dzisiaj, res1[0]))
    prods = [r[0] for r in cursor.fetchall()]
    print(f"Products with min queue: {prods}")

cursor.close()
conn.close()
