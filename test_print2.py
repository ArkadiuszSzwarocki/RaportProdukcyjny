from app.db import get_db_connection
from app.utils.pallet_label import prepare_pallet_label_data
conn = get_db_connection()
cur = conn.cursor(dictionary=True)
print(prepare_pallet_label_data(cur, 372, 'AGRO'))
