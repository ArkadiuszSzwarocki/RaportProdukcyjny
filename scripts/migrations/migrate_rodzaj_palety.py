import mysql.connector

def run_migration():
    print("Running migration to add 'rodzaj_palety' column...")
    from app.db import get_db_connection
    conn = get_db_connection()
    cursor = conn.cursor()
    
    tables = ['plan_produkcji', 'plan_produkcji_agro']
    
    for table in tables:
        try:
            cursor.execute(f"SHOW COLUMNS FROM {table} LIKE 'rodzaj_palety'")
            result = cursor.fetchone()
            if not result:
                print(f"Adding 'rodzaj_palety' to {table}...")
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN rodzaj_palety VARCHAR(50) DEFAULT 'krajowa'")
                conn.commit()
                print(f"Column added successfully to {table}.")
            else:
                print(f"Column 'rodzaj_palety' already exists in {table}.")
        except Exception as e:
            print(f"Error checking/adding column in {table}: {e}")
            
    cursor.close()
    conn.close()
    print("Migration completed.")

if __name__ == '__main__':
    run_migration()
