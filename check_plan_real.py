from app.core.factory import create_app
from app.db import get_db_connection
import json

app = create_app()
with app.app_context():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, zlecenie_numer, uszkodzone_worki FROM plan_produkcji_agro ORDER BY id DESC LIMIT 5")
    rows = cursor.fetchall()
    print(json.dumps(rows, indent=2))
