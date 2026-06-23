from app.core.factory import create_app
from app.db import get_db_connection

app = create_app()
with app.app_context():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    tables_to_check = ['magazyn_agro_slownik_surowce', 'magazyn_psd_slownik_surowce', 'magazyn_slownik_surowce']
    
    for table in tables_to_check:
        try:
            cursor.execute(f"SHOW TABLES LIKE '{table}'")
            if cursor.fetchone():
                cursor.execute(f"INSERT INTO {table} (nazwa) VALUES (%s)", ("MPC Koncentrat białka",))
                conn.commit()
                print(f"Added to {table}")
        except Exception as e:
            print(f"Error for {table}: {e}")
