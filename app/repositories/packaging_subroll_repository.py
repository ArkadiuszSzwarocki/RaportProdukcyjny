"""Data-access repository for magazyn_opakowania_rolki (Nested HU sub-rolls)."""
from __future__ import annotations

from app.dto.packaging_subroll_dto import SubrollInsertSpec


class PackagingSubrollRepository:
    """Pure SQL operations for packaging pallet sub-rolls."""

    @staticmethod
    def ensure_table(cursor) -> None:
        """Idempotently ensure magazyn_opakowania_rolki exists."""
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS magazyn_opakowania_rolki (
                id INT AUTO_INCREMENT PRIMARY KEY,
                parent_opakowanie_id INT NOT NULL,
                kod_rolki VARCHAR(64) NOT NULL UNIQUE,
                nr_rolki INT NOT NULL DEFAULT 1,
                ilosc_szt INT NOT NULL,
                waga_kg DECIMAL(10,3) NULL DEFAULT NULL,
                status VARCHAR(24) NOT NULL DEFAULT 'NA_PALECIE',
                lp01_opakowanie_id INT NULL DEFAULT NULL,
                zrodlo VARCHAR(32) NOT NULL DEFAULT 'PODZIAL',
                created_by VARCHAR(100) NULL DEFAULT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_mor_parent_status (parent_opakowanie_id, status),
                INDEX idx_mor_lp01_opak (lp01_opakowanie_id)
            )
            """
        )

    @staticmethod
    def list_active_by_parent(cursor, parent_id: int) -> list[dict]:
        """Return all active sub-rolls currently stored on a master pallet."""
        cursor.execute(
            """
            SELECT id, parent_opakowanie_id, kod_rolki, nr_rolki, ilosc_szt,
                   waga_kg, status, zrodlo, created_by, created_at
            FROM magazyn_opakowania_rolki
            WHERE parent_opakowanie_id = %s AND status = 'NA_PALECIE'
            ORDER BY nr_rolki ASC, id ASC
            """,
            (parent_id,),
        )
        return cursor.fetchall() or []

    @staticmethod
    def count_active_by_parents(cursor, parent_ids: list[int]) -> dict[int, dict]:
        """Aggregate active sub-roll counts and piece sums for multiple pallets."""
        if not parent_ids:
            return {}
        placeholders = ', '.join(['%s'] * len(parent_ids))
        cursor.execute(
            f"""
            SELECT parent_opakowanie_id,
                   COUNT(*) AS cnt,
                   COALESCE(SUM(ilosc_szt), 0) AS total_szt
            FROM magazyn_opakowania_rolki
            WHERE parent_opakowanie_id IN ({placeholders})
              AND status = 'NA_PALECIE'
            GROUP BY parent_opakowanie_id
            """,
            tuple(parent_ids),
        )
        summary: dict[int, dict] = {}
        for row in cursor.fetchall() or []:
            pid = int(row['parent_opakowanie_id'] if isinstance(row, dict) else row[0])
            cnt = int((row['cnt'] if isinstance(row, dict) else row[1]) or 0)
            szt = int((row['total_szt'] if isinstance(row, dict) else row[2]) or 0)
            summary[pid] = {'count': cnt, 'total_szt': szt}
        return summary

    @staticmethod
    def find_by_roll_code(cursor, kod_rolki: str, for_update: bool = False) -> dict | None:
        """Fetch sub-roll by its unique barcode (ROL...)."""
        lock_sql = ' FOR UPDATE' if for_update else ''
        cursor.execute(
            f"""
            SELECT id, parent_opakowanie_id, kod_rolki, nr_rolki, ilosc_szt,
                   waga_kg, status, lp01_opakowanie_id, zrodlo, created_by, created_at
            FROM magazyn_opakowania_rolki
            WHERE UPPER(kod_rolki) = UPPER(%s)
            LIMIT 1{lock_sql}
            """,
            (kod_rolki.strip(),),
        )
        return cursor.fetchone()

    @staticmethod
    def find_by_id(cursor, subroll_id: int, for_update: bool = False) -> dict | None:
        """Fetch sub-roll by primary key."""
        lock_sql = ' FOR UPDATE' if for_update else ''
        cursor.execute(
            f"""
            SELECT id, parent_opakowanie_id, kod_rolki, nr_rolki, ilosc_szt,
                   waga_kg, status, lp01_opakowanie_id, zrodlo, created_by, created_at
            FROM magazyn_opakowania_rolki
            WHERE id = %s
            LIMIT 1{lock_sql}
            """,
            (subroll_id,),
        )
        return cursor.fetchone()

    @staticmethod
    def next_roll_number(cursor, parent_id: int) -> int:
        """Compute next sequential roll number for a master pallet."""
        cursor.execute(
            """
            SELECT COALESCE(MAX(nr_rolki), 0) AS max_nr
            FROM magazyn_opakowania_rolki
            WHERE parent_opakowanie_id = %s
            """,
            (parent_id,),
        )
        row = cursor.fetchone()
        max_nr = int((row.get('max_nr') if isinstance(row, dict) else (row[0] if row else 0)) or 0)
        return max_nr + 1

    @staticmethod
    def insert_subroll(cursor, spec: SubrollInsertSpec) -> int:
        """Insert a new NA_PALECIE sub-roll row and return its ID."""
        cursor.execute(
            """
            INSERT INTO magazyn_opakowania_rolki
                (parent_opakowanie_id, kod_rolki, nr_rolki, ilosc_szt, waga_kg,
                 status, zrodlo, created_by)
            VALUES (%s, %s, %s, %s, %s, 'NA_PALECIE', %s, %s)
            """,
            (
                spec.parent_id,
                spec.kod_rolki,
                spec.nr_rolki,
                spec.ilosc_szt,
                spec.waga_kg,
                spec.zrodlo,
                spec.created_by,
            ),
        )
        return int(cursor.lastrowid)

    @staticmethod
    def mark_dispatched_to_lp01(cursor, subroll_id: int, lp01_opakowanie_id: int | None) -> None:
        """Transition sub-roll status to WYDANA_LP01 when detached from master pallet."""
        cursor.execute(
            """
            UPDATE magazyn_opakowania_rolki
            SET status = 'WYDANA_LP01', lp01_opakowanie_id = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (lp01_opakowanie_id, subroll_id),
        )
