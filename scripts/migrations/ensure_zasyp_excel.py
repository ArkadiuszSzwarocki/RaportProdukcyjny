"""Add the Excel batch settlement field ONLY to biblioteka_testowa."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main():
    import mysql.connector
    from app.config import DB_CONFIG
    from app.services.zasyp_excel_service import ensure_zasyp_excel_schema
    settings = dict(DB_CONFIG, database='biblioteka_testowa', use_pure=True)
    connection = mysql.connector.connect(**settings)
    try:
        cursor = connection.cursor()
        cursor.execute('SELECT DATABASE()')
        if cursor.fetchone()[0] != 'biblioteka_testowa':
            raise RuntimeError('Refusing migration of a different database')
        cursor.execute('SET SESSION lock_wait_timeout = 10')
        ensure_zasyp_excel_schema(cursor)
        connection.commit()
        cursor.execute("SHOW COLUMNS FROM plan_produkcji_agro LIKE 'zasyp_excel_kg'")
        if not cursor.fetchone():
            raise RuntimeError('Migration verification failed')
        cursor.close()
        print('biblioteka_testowa: zasyp_excel_kg ready. No existing settlements or orders were changed.')
    finally:
        connection.close()


if __name__ == '__main__':
    main()
