"""
Small helper: execute a .sql file using Python DB connector (bypasses mysql CLI).
Usage: python scripts\apply_sql_direct.py scripts\migrations\0002_add_pracownik_id_to_uzytkownicy.sql
"""
import sys
from pathlib import Path
# Ensure project root is on sys.path so top-level modules (db, config) import correctly
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from db import get_db_connection

def apply_sql_file(path: Path):
    sql = path.read_text(encoding='utf-8')
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Execute statements split by ';' to support multi-statement SQL files
        statements = [s.strip() for s in sql.split(';')]
        for stmt in statements:
            if not stmt:
                continue
            try:
                cursor.execute(stmt)
            except Exception as e:
                # print which statement failed and re-raise
                print('Failed statement:', stmt[:200])
                raise
        conn.commit()
        print(f"Applied SQL file: {path}")
        return 0
    except Exception as e:
        print(f"ERROR applying {path}: {e}")
        if conn:
            try: conn.rollback()
            except Exception: pass
        return 2
    finally:
        if conn:
            try: conn.close()
            except Exception: pass

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python scripts\\apply_sql_direct.py <sql-file>')
        sys.exit(2)
    p = Path(sys.argv[1])
    if not p.exists():
        print('File not found:', p)
        sys.exit(2)
    sys.exit(apply_sql_file(p))
