"""
Database migration: Unify finished goods warehouse into single 'magazyn_palety' table across BOTH databases (biblioteka and biblioteka_testowa).

- Ensures 'linia' column exists on 'magazyn_palety' (default 'PSD').
- Converts unique index 'uq_magazyn_palety_paleta_workowanie' to composite '(paleta_workowanie_id, linia)'.
- Copies existing pallets from 'magazyn_palety_agro' into 'magazyn_palety' with linia = 'AGRO'.
- Replaces 'magazyn_palety_agro' table with a backwards-compatible VIEW.
"""
import mysql.connector
from app.config import DB_CONFIG


def run_migration_for_db(db_name: str):
    print(f"\n==================================================")
    print(f"Running migration on database: '{db_name}'")
    print(f"==================================================")
    cfg = dict(DB_CONFIG)
    cfg['database'] = db_name

    try:
        conn = mysql.connector.connect(**cfg, buffered=True)
    except Exception as conn_err:
        print(f"[SKIP] Cannot connect to database '{db_name}': {conn_err}")
        return

    cursor = conn.cursor(dictionary=True)
    try:
        # 1. Ensure 'linia' column exists in magazyn_palety
        cursor.execute("SHOW COLUMNS FROM magazyn_palety LIKE 'linia'")
        if not cursor.fetchone():
            print(f"[{db_name}] Adding 'linia' column to magazyn_palety...")
            cursor.execute("ALTER TABLE magazyn_palety ADD COLUMN linia VARCHAR(20) NOT NULL DEFAULT 'PSD'")
            conn.commit()

        # 2. Update default to 'PSD' for any existing null/empty lines
        cursor.execute("UPDATE magazyn_palety SET linia = 'PSD' WHERE linia IS NULL OR linia = ''")
        conn.commit()

        # 3. Drop single-column unique constraint on paleta_workowanie_id if present
        cursor.execute("SHOW INDEX FROM magazyn_palety WHERE Key_name = 'uq_magazyn_palety_paleta_workowanie'")
        if cursor.fetchone():
            print(f"[{db_name}] Dropping legacy unique index 'uq_magazyn_palety_paleta_workowanie'...")
            cursor.execute("ALTER TABLE magazyn_palety DROP INDEX uq_magazyn_palety_paleta_workowanie")
            conn.commit()

        # 4. Create composite unique index on (paleta_workowanie_id, linia)
        cursor.execute("SHOW INDEX FROM magazyn_palety WHERE Key_name = 'uq_magazyn_palety_paleta_linia'")
        if not cursor.fetchone():
            print(f"[{db_name}] Creating composite unique index 'uq_magazyn_palety_paleta_linia'...")
            cursor.execute("ALTER TABLE magazyn_palety ADD UNIQUE INDEX uq_magazyn_palety_paleta_linia (paleta_workowanie_id, linia)")
            conn.commit()

        # 5. Ensure index on linia column
        cursor.execute("SHOW INDEX FROM magazyn_palety WHERE Key_name = 'idx_magazyn_palety_linia'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE magazyn_palety ADD INDEX idx_magazyn_palety_linia (linia)")
            conn.commit()

        # 6. Check if magazyn_palety_agro is a base table (not a view)
        cursor.execute("""
            SELECT TABLE_TYPE FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'magazyn_palety_agro'
        """)
        tbl_info = cursor.fetchone()

        if tbl_info and tbl_info.get('TABLE_TYPE') == 'BASE TABLE':
            print(f"[{db_name}] Migrating records from base table 'magazyn_palety_agro' into 'magazyn_palety'...")
            cursor.execute("""
                INSERT IGNORE INTO magazyn_palety (
                    nr_palety, paleta_workowanie_id, plan_id, data_planu, produkt,
                    waga_netto, waga_brutto, tara, user_login, data_potwierdzenia,
                    created_at, lokalizacja, nr_partii, data_produkcji, data_przydatnosci,
                    typ_opakowania, is_blocked, linia, nr_plomby
                )
                SELECT 
                    nr_palety, paleta_workowanie_id, plan_id, data_planu, produkt,
                    waga_netto, waga_brutto, tara, user_login, data_potwierdzenia,
                    created_at, COALESCE(lokalizacja, 'MGW01'), nr_partii, data_produkcji, data_przydatnosci,
                    COALESCE(typ_opakowania, 'bags'), COALESCE(is_blocked, 0), 'AGRO', nr_plomby
                FROM magazyn_palety_agro
            """)
            conn.commit()

            print(f"[{db_name}] Backing up base table 'magazyn_palety_agro' and replacing with compatibility VIEW...")
            cursor.execute("DROP TABLE IF EXISTS backup_magazyn_palety_agro_unified")
            cursor.execute("RENAME TABLE magazyn_palety_agro TO backup_magazyn_palety_agro_unified")
            conn.commit()

            cursor.execute("""
                CREATE OR REPLACE VIEW magazyn_palety_agro AS
                SELECT * FROM magazyn_palety WHERE linia = 'AGRO'
            """)
            conn.commit()
            print(f"[{db_name}] Compatibility VIEW 'magazyn_palety_agro' created successfully.")
        else:
            print(f"[{db_name}] Creating/updating compatibility VIEW 'magazyn_palety_agro'...")
            cursor.execute("""
                CREATE OR REPLACE VIEW magazyn_palety_agro AS
                SELECT * FROM magazyn_palety WHERE linia = 'AGRO'
            """)
            conn.commit()

        print(f"[{db_name}] Finished goods warehouse unification finished successfully.")
    except Exception as e:
        conn.rollback()
        print(f"[{db_name}] Error executing migration: {e}")
    finally:
        cursor.close()
        conn.close()


def run_migration():
    databases = ['biblioteka', 'biblioteka_testowa']
    for db in databases:
        run_migration_for_db(db)


if __name__ == '__main__':
    run_migration()
