from app.db import get_db_connection
conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
q = """
    SELECT pz.id, pz.produkt 
    FROM plan_produkcji pz
    WHERE pz.sekcja='Zasyp' AND pz.status='zakonczone' AND DATE(pz.data_planu)='2026-03-31'
    AND EXISTS (
        SELECT 1 FROM plan_produkcji pw
        WHERE pw.sekcja='Workowanie' AND pw.produkt = pz.produkt 
        AND pw.status = 'zaplanowane' AND DATE(pw.data_planu) = DATE(pz.data_planu)
    )
    ORDER BY pz.real_stop ASC LIMIT 1
"""
cursor.execute(q)
res = cursor.fetchone()
print(f"Earliest Zaplanowane from Zasyp: {res}")
cursor.close()
conn.close()
