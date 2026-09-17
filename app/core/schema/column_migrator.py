"""Database schema migration helpers and column alteration functions."""
from __future__ import annotations


def table_has_column(cursor, table_name: str, column_name: str) -> bool:
    try:
        cursor.execute(
            "SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND COLUMN_NAME=%s",
            (table_name, column_name),
        )
        return bool(cursor.fetchone())
    except Exception:
        return False


def add_column_if_missing(cursor, table: str, column: str, definition: str, description: str = ""):
    """Helper to add column if it doesn't exist."""
    try:
        cursor.execute(
            "SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND COLUMN_NAME=%s",
            (table, column)
        )
        if not cursor.fetchone():
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                if description:
                    print(f"[MIGRATE] {description}")
            except Exception as e:
                print(f"[WARN] Failed to add column {table}.{column}: {e}")
    except Exception as e:
        print(f"[WARN] Error checking column {table}.{column}: {e}")


def ensure_unique_index(cursor, table: str, index_name: str, columns: tuple | list, description: str = ""):
    """Ensure that a UNIQUE index exists with the exact column order provided."""
    try:
        cursor.execute(
            """
            SELECT COLUMN_NAME
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND INDEX_NAME = %s
            ORDER BY SEQ_IN_INDEX
            """,
            (table, index_name),
        )
        existing_columns = [row[0] for row in cursor.fetchall() or []]
        desired_columns = list(columns)
        if existing_columns == desired_columns:
            return

        if existing_columns:
            try:
                cursor.execute(f"ALTER TABLE {table} DROP INDEX {index_name}")
            except Exception:
                pass

        cursor.execute(
            f"ALTER TABLE {table} ADD UNIQUE KEY {index_name} ({', '.join(desired_columns)})"
        )
        if description:
            print(f"[MIGRATE] {description}")
    except Exception as e:
        print(f"[WARN] Failed to ensure unique index {table}.{index_name}: {e}")
