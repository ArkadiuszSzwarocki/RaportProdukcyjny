from app.core.database import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

pallets = ['SUR000001786005633670', 'SUR000001789128387745']
for p in pallets:
    print(f"\n=== PALETA {p} ===")
    cursor.execute("SELECT * FROM palety_historia WHERE nr_palety = %s", (p,))
    hist = cursor.fetchall()
    for h in hist:
        print(f"  HISTORIA: {h}")

conn.close()
