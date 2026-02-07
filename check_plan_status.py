from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# Check status of plan 467
cursor.execute("SELECT id, produkt, status, sekcja FROM plan_produkcji WHERE id IN (460, 467)")
plans = cursor.fetchall()

print("Plan status check:")
for plan_id, produkt, status, sekcja in plans:
    print(f"  ID {plan_id}: {produkt:15s} sekcja={sekcja:12s} status={status}")

conn.close()
