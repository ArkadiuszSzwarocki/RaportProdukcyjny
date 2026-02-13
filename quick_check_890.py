from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

print("PLAN 890 - BIEŻĄCY STAN:\n")

# Szarze - szczegóły
cursor.execute('SELECT SUM(waga) FROM szarze WHERE plan_id = 890')
szarze_sum = cursor.fetchone()[0] or 0
print(f"Szarze suma: {szarze_sum} kg")

# Workowanie - szczegóły
cursor.execute('SELECT SUM(waga) FROM palety_workowanie WHERE plan_id = 890')
work_sum = cursor.fetchone()[0] or 0
print(f"Workowanie suma: {work_sum} kg")

# Czy plan status?
cursor.execute('SELECT status FROM plan_produkcji WHERE id = 890')
plan_status = cursor.fetchone()[0]
print(f"Plan status: {plan_status}")

# Bufor count
cursor.execute('SELECT COUNT(*) FROM bufor WHERE zasyp_id IN (SELECT id FROM szarze WHERE plan_id = 890)')
buf_count = cursor.fetchone()[0]
print(f"Buffor entries: {buf_count}")

print(f"\nRozbieżność: {szarze_sum - work_sum} kg")

cursor.close()
conn.close()
