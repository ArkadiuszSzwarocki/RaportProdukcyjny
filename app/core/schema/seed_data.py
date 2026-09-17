"""Database seed data initializer for users, products, labels and pallet normalization."""
from __future__ import annotations

import os
from werkzeug.security import generate_password_hash
from app.core.schema.column_migrator import table_has_column


class DatabaseSeeder:
    """Handles seeding initial accounts, products, recipes and normalizing pallet identifiers."""

    @staticmethod
    def seed_default_users(cursor):
        cursor.execute("SELECT id, haslo FROM uzytkownicy")
        existing = cursor.fetchall()
        migrated = 0
        for row in existing:
            uid, pwd = row[0], row[1]
            if pwd:
                s = str(pwd)
                if not (s.startswith('pbkdf2:') or s.startswith('scrypt:') or s.startswith('sha1:')):
                    new_h = generate_password_hash(s, method='pbkdf2:sha256')
                    cursor.execute("UPDATE uzytkownicy SET haslo=%s WHERE id=%s", (new_h, uid))
                    migrated += 1
        
        if migrated:
            print(f"[AUTH] Hashed {migrated} existing user passwords.")
        
        cursor.execute("SELECT id FROM uzytkownicy WHERE login='admin'")
        if not cursor.fetchone():
            init_pass = os.environ.get('INITIAL_ADMIN_PASSWORD')
            if init_pass:
                cursor.execute(
                    "INSERT INTO uzytkownicy (login, haslo, rola) VALUES (%s, %s, %s)",
                    ('admin', generate_password_hash(init_pass, method='pbkdf2:sha256'), 'admin')
                )
            else:
                print("[SECURITY] No INITIAL_ADMIN_PASSWORD provided; skipping creation of default 'admin' account.")

    @staticmethod
    def seed_produkty(cursor):
        default_products = [
            ('MOM INSTANT', '', 'worki_zgrzewane_25'),
            ('MILK BAND BIAŁE', '', 'worki_zgrzewane_25'),
            ('HOLENDER', '', 'worki_zgrzewane_25'),
            ('testowe 45', '', 'worki_zgrzewane_25'),
        ]
        for nazwa, nr_receptury, typ in default_products:
            cursor.execute("SELECT id FROM produkty_receptury WHERE nazwa_produktu=%s", (nazwa,))
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO produkty_receptury (nazwa_produktu, nr_receptury, typ_produkcji) VALUES (%s, %s, %s)",
                    (nazwa, nr_receptury, typ)
                )
        print("[OK] Produkty zainicjalizowane w bazie danych")

    @staticmethod
    def seed_etykiety(cursor):
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS slownik_etykiety_agro (
                id INT AUTO_INCREMENT PRIMARY KEY,
                nazwa VARCHAR(255) UNIQUE NOT NULL
            )
        """)
        default_labels = [
            "Biała",
            "Biała z paskiem brązowym",
            "Biała z paskiem czerwonym",
            "Biała z paskiem fioletowym",
            "Biała z paskiem żółtym"
        ]
        for label in default_labels:
            cursor.execute("SELECT id FROM slownik_etykiety_agro WHERE nazwa=%s", (label,))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO slownik_etykiety_agro (nazwa) VALUES (%s)", (label,))
        print("[OK] Etykiety AGRO zainicjalizowane w bazie danych")

    @staticmethod
    def standardize_warehouse_pallet_ids(cursor):
        from app.utils.pallet_id import generate_pallet_id, is_valid_pallet_id

        table_specs = [
            {'table': 'magazyn_surowce', 'type': 'surowiec', 'linia': 'PSD'},
            {'table': 'magazyn_opakowania', 'type': 'opakowanie', 'linia': 'PSD'},
            {'table': 'magazyn_dodatki', 'type': 'dodatek', 'linia': 'PSD'},
            {'table': 'magazyn_palety', 'type': 'wyrób gotowy', 'linia': 'PSD'},
            {'table': 'magazyn_palety_agro', 'type': 'wyrób gotowy', 'linia': 'AGRO'},
            {'table': 'palety_workowanie', 'type': 'wyrób gotowy', 'linia': 'PSD'},
            {'table': 'palety_agro', 'type': 'wyrób gotowy', 'linia': 'AGRO'},
        ]

        total_updated = 0
        for spec in table_specs:
            table_name = spec['table']
            if not table_has_column(cursor, table_name, 'id') or not table_has_column(cursor, table_name, 'nr_palety'):
                continue

            try:
                cursor.execute(
                    f"SELECT id, nr_palety FROM {table_name} "
                    "WHERE nr_palety IS NULL OR TRIM(nr_palety) = '' OR nr_palety NOT REGEXP '^[A-Za-z]{3}[0-9]{18}$'"
                )
            except Exception:
                continue

            rows = cursor.fetchall() or []
            updated = 0
            for row_id, old_nr_palety in rows:
                if is_valid_pallet_id(old_nr_palety):
                    continue

                new_nr_palety = generate_pallet_id(spec['linia'], type=spec['type'], record_id=row_id)
                cursor.execute(f"UPDATE {table_name} SET nr_palety = %s WHERE id = %s", (new_nr_palety, row_id))
                updated += 1

            if updated:
                total_updated += updated
                print(f"[MIGRATE] Standaryzacja SSCC w {table_name}: {updated} rekordow")

        if total_updated:
            print(f"[OK] Zaktualizowano {total_updated} rekordow nr_palety do formatu AAA+18 cyfr")
