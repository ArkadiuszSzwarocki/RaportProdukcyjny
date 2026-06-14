import mysql.connector

def add_columns_if_missing():
    try:
        conn = mysql.connector.connect(host='filipinka.myqnapcloud.com', port=3307, user='biblioteka', password='Filipinka2025', database='biblioteka_testowa')
    except Exception as e:
        print(f"Failed to connect: {e}")
        return

    cursor = conn.cursor()
    tables = ['plan_produkcji_agro', 'plan_produkcji_psd']
    
    for table in tables:
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN ostatnie_wznowienie DATETIME NULL;")
            print(f"Added ostatnie_wznowienie to {table}")
        except Exception as e:
            print(f"Error adding ostatnie_wznowienie to {table}: {e}")
            
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN czas_pracy_sekundy INT NOT NULL DEFAULT 0;")
            print(f"Added czas_pracy_sekundy to {table}")
        except Exception as e:
            print(f"Error adding czas_pracy_sekundy to {table}: {e}")
            
    conn.commit()
    conn.close()

if __name__ == '__main__':
    add_columns_if_missing()
