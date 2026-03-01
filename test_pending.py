#!/usr/bin/env python
from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()
cursor.execute("SELECT id FROM wnioski_wolne WHERE status='pending' LIMIT 1")
result = cursor.fetchone()
pending_id = result[0] if result else None
print('Pending request ID:', pending_id)
conn.close()
