"""
Skrypt migracji: tworzenie tabeli magazyn_zamowienia (wersja z JSON items).
Uwaga: Usuwa starą tabelę i tworzy od nowa z nowym schematem.

Cel: Przechowywanie wielopozycyjnych zamówień surowców z magazynu.
Wejście: Brak (skrypt uruchamiany ręcznie lub w pipeline).
Wyjście: Tabela magazyn_zamowienia w bazie danych.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.core.database import get_db_connection


SQL_DROP_TABLE = "DROP TABLE IF EXISTS magazyn_zamowienia;"

SQL_CREATE_TABLE = """
CREATE TABLE magazyn_zamowienia (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    items           JSON NOT NULL,
    status          ENUM('NOWE','ZAMKNIETE') NOT NULL DEFAULT 'NOWE',
    operator_login  VARCHAR(100) NOT NULL,
    magazynier_login VARCHAR(100) DEFAULT NULL,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    confirmed_at    DATETIME DEFAULT NULL,
    komentarz       TEXT DEFAULT NULL,
    INDEX idx_status (status),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


def run_migration():
    """Usuwa stara tabele (jesli istnieje) i tworzy nowa."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        print("Usuwanie starej tabeli (jesli istnieje)...")
        cursor.execute(SQL_DROP_TABLE)
        print("Tworzenie nowej tabeli (schemat z JSON items)...")
        cursor.execute(SQL_CREATE_TABLE)
        conn.commit()
        print("[OK] Tabela magazyn_zamowienia utworzona pomyślnie.")
    except Exception as e:
        print(f"[BŁĄD] Migracja nieudana: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    run_migration()
