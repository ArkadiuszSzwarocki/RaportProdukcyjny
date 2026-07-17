import sys
sys.path.append('a:\\GitHub\\RaportProdukcyjny')
from app.core.database import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute("USE biblioteka")

tables = ['szarze_agro', 'zasyp_etapy', 'zasyp_etap_start_events', 'zasyp_dosypka_added_events', 'agro_mix_rozliczenie']
for t in tables:
    print(f"--- columns of {t} ---")
    cursor.execute(f"DESCRIBE {t}")
    for col in cursor.fetchall():
        print(f"  {col['Field']}: {col['Type']}")
        
cursor.close()
conn.close()
