from app.db import get_db_connection

def main():
    conn = get_db_connection()
    cursor = conn.cursor()
    query = "ALTER TABLE magazyn_inwentaryzacja_wpisy MODIFY COLUMN typ_palety ENUM('surowiec', 'opakowanie', 'wyrób gotowy', 'dodatek')"
    cursor.execute(query)
    conn.commit()
    conn.close()
    print("Enum updated successfully.")

if __name__ == '__main__':
    main()
