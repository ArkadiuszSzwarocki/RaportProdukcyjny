import sys
sys.path.append('a:\\GitHub\\RaportProdukcyjny')
from app.core.database import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute("USE biblioteka")

# Check if there's any ingredient/skaldnik table
cursor.execute("SHOW TABLES")
tables = [list(r.values())[0] if hasattr(r, 'values') else r[0] for r in cursor.fetchall()]
print("ALL TABLES:")
for t in sorted(tables):
    print(" ", t)

cursor.close()
conn.close()
