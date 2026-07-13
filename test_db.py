
from app.core.database import get_db_connection
conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
try:
    cursor.execute('SELECT id, lokalizacja FROM magazyn_palety WHERE nr_palety = \'PSD020320262455411041\'')
    print('magazyn_palety:', cursor.fetchone())
except Exception as e: print(e)
try:
    cursor.execute('SELECT id, lokalizacja FROM magazyn_palety_agro WHERE nr_palety = \'PSD020320262455411041\'')
    print('magazyn_palety_agro:', cursor.fetchone())
except Exception as e: print(e)
try:
    cursor.execute('SELECT id FROM palety_workowanie WHERE nr_palety = \'PSD020320262455411041\'')
    print('palety_workowanie:', cursor.fetchone())
except Exception as e: print(e)

