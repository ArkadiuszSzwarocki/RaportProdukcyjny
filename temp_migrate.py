from app.db import get_db_connection

def migrate():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    tables = ['plan_produkcji', 'plan_agro']
    columns = [
        ('uszkodzone_worki', 'INT DEFAULT 0'),
        ('wyjasnienie_rozbieznosci', 'TEXT'),
        ('typ_zlecenia', "VARCHAR(50) DEFAULT 'standard'"),
        ('nazwa_zlecenia', 'VARCHAR(255)'),
        ('zasyp_id', 'INT')
    ]
    
    for table in tables:
        print(f"Migrating table: {table}")
        for col_name, col_def in columns:
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
                print(f"  [+] Added {col_name} to {table}")
            except Exception as e:
                # Column might already exist
                if 'Duplicate column name' in str(e):
                    print(f"  [.] {col_name} already exists in {table}")
                else:
                    print(f"  [!] Error adding {col_name} to {table}: {e}")
    
    conn.commit()
    conn.close()
    print("Migration finished!")

if __name__ == "__main__":
    migrate()
