from app.core.factory import create_app
from app.db import get_db_connection
import json

app = create_app()
with app.app_context():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, nr_palety, waga_brutto FROM palety_agro WHERE plan_id=88")
    rows = cursor.fetchall()
    print(json.dumps(rows, indent=2))
