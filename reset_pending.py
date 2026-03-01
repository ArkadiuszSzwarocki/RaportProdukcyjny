#!/usr/bin/env python
"""Reset some wnioski to pending status for testing."""
from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# Reset a few requests to pending for testing
ids_to_reset = [7, 8, 9, 10]
for wid in ids_to_reset:
    cursor.execute(
        "UPDATE wnioski_wolne SET status='pending', lider_id=NULL, decyzja_dnia=NULL WHERE id=%s",
        (wid,)
    )

conn.commit()
print(f"Reset {len(ids_to_reset)} requests to pending status: {ids_to_reset}")

# Verify
cursor.execute("SELECT id, status FROM wnioski_wolne ORDER BY id")
results = cursor.fetchall()
print("\nAll requests now:")
for id_, status in results:
    print(f"  ID {id_}: {status}")

conn.close()
