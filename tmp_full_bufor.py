import json
from app.db import get_db_connection, get_table_name
conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
table_bufor = get_table_name('bufor', 'PSD')
cursor.execute(f"SELECT * FROM {table_bufor} WHERE DATE(data_planu)='2026-03-31' AND status='aktywny'")
rows = cursor.fetchall()
for r in rows:
    for k, v in r.items():
        if hasattr(v, 'isoformat'): r[k] = v.isoformat()
print(json.dumps(rows, indent=2, ensure_ascii=False))
conn.close()
