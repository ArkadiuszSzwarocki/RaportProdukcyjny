from app.core.factory import create_app
from app.db import get_db_connection
import json

app = create_app()
with app.app_context():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, uszkodzone_worki FROM plan_produkcji_agro WHERE id=88")
    rows = cursor.fetchall()
    print(json.dumps(rows, indent=2))
