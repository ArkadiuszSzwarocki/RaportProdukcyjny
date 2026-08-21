#!/usr/bin/env python3
from app.db import get_db_connection
from datetime import date, datetime
import sys

# Optional date arg: YYYY-MM-DD
if len(sys.argv) > 1:
    try:
        target_date = datetime.strptime(sys.argv[1], '%Y-%m-%d').date()
    except Exception:
        print('Nieprawidłowy format daty. Użyj YYYY-MM-DD')
        sys.exit(1)
else:
    target_date = date.today()

print(f"Synchronizuję Workowanie.tonaz z Zasyp.tonaz_rzeczywisty dla daty: {target_date}")
conn = get_db_connection()
cursor = conn.cursor()

# Pobierz unikalne produkty we Workowanie dla daty
cursor.execute("SELECT DISTINCT produkt FROM plan_produkcji WHERE sekcja='Workowanie' AND DATE(data_planu) = %s", (target_date,))
produkty = [r[0] for r in cursor.fetchall()]

updated = 0
for prod in produkty:
    try:
        cursor.execute(
            "SELECT COALESCE(tonaz_rzeczywisty, 0) FROM plan_produkcji "
            "WHERE sekcja='Zasyp' AND produkt=%s AND DATE(data_planu) = %s "
            "ORDER BY COALESCE(real_stop, real_start, id) ASC LIMIT 1",
            (prod, target_date)
        )
        row = cursor.fetchone()
        zasyp_ton = row[0] if row and row[0] is not None else 0

        cursor.execute(
            "UPDATE plan_produkcji SET tonaz = %s WHERE sekcja='Workowanie' AND produkt=%s AND DATE(data_planu) = %s",
            (zasyp_ton, prod, target_date)
        )
        if cursor.rowcount > 0:
            print(f"  Zaktualizowano Workowanie dla '{prod}': tonaz <- {zasyp_ton}")
            updated += cursor.rowcount
    except Exception as e:
        print(f"  Błąd dla produktu {prod}: {e}")
        conn.rollback()

conn.commit()
print(f"Gotowe. Zaktualizowano {updated} wierszy.")
cursor.close()
conn.close()
