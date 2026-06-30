import sys, os
sys.path.append(os.getcwd())
from app.core.factory import create_app
from app.db import get_db_connection

app = create_app(init_db=False)
with app.app_context():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SHOW TABLES LIKE "%palety_agro%"')
    print("Tables like palety_agro:")
    for row in cursor.fetchall():
        print(row[0])
