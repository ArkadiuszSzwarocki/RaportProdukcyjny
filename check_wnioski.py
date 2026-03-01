from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# Check wnioski_wolne table structure and content
cursor.execute("SELECT id, pracownik_id, typ, data_od, data_do, status FROM wnioski_wolne ORDER BY id")
results = cursor.fetchall()

print("=== WNIOSKI_WOLNE TABLE ===")
print(f"{'ID':<5} {'Pracownik':<12} {'Typ':<20} {'Data Od':<12} {'Data Do':<12} {'Status':<12}")
print("-" * 73)

for row in results:
    id_, pw_id, typ, data_od, data_do, status = row
    print(f"{id_:<5} {pw_id:<12} {typ:<20} {str(data_od):<12} {str(data_do):<12} {status:<12}")

print(f"\nTotal records: {len(results)}")

# Show status distribution
cursor.execute("SELECT status, COUNT(*) FROM wnioski_wolne GROUP BY status")
status_dist = cursor.fetchall()
print("\nStatus distribution:")
for status, count in status_dist:
    print(f"  {status}: {count}")

conn.close()
