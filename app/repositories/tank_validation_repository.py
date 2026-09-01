from typing import List, Optional, Dict, Any
from app.db import get_db_connection
from app.models.tank_validation_rule import TankValidationRule
import datetime


class TankValidationRepository:
    """Repository for managing production tank validation rules in MySQL."""

    @staticmethod
    def ensure_table() -> None:
        """Create the tank configuration table if it does not exist."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS konfiguracja_zbiornikow (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    kod_zbiornika VARCHAR(50) NOT NULL UNIQUE,
                    nazwa_surowca VARCHAR(255) NOT NULL,
                    surowiec_id INT NULL,
                    opis VARCHAR(255) NULL,
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    updated_by VARCHAR(100) NULL,
                    INDEX idx_zbiornik (kod_zbiornika)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            cursor.execute("""
                DELETE FROM konfiguracja_zbiornikow
                WHERE kod_zbiornika IN ('MZ11', 'MZ12', 'MZ13', 'MZ14', 'MZ15', 'MZ16', 'MZ17', 'MZ18', 'MZ19', 'MZ20', 'MZ21', 'MZ22')
            """)
            conn.commit()
        finally:
            conn.close()

    @classmethod
    def get_all_rules(cls) -> List[TankValidationRule]:
        """Fetch all configured tank validation rules."""
        cls.ensure_table()
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT id, kod_zbiornika, nazwa_surowca, surowiec_id, opis, is_active, updated_at, updated_by
                FROM konfiguracja_zbiornikow
                ORDER BY kod_zbiornika ASC
            """)
            rows = cursor.fetchall()
            return [
                TankValidationRule(
                    id=row['id'],
                    kod_zbiornika=row['kod_zbiornika'],
                    nazwa_surowca=row['nazwa_surowca'],
                    surowiec_id=row['surowiec_id'],
                    opis=row['opis'],
                    is_active=bool(row['is_active']),
                    updated_at=row['updated_at'],
                    updated_by=row['updated_by']
                )
                for row in rows
            ]
        finally:
            conn.close()

    @classmethod
    def get_rule_by_tank(cls, kod_zbiornika: str) -> Optional[TankValidationRule]:
        """Fetch a validation rule for a specific tank code."""
        if not kod_zbiornika:
            return None
        cls.ensure_table()
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT id, kod_zbiornika, nazwa_surowca, surowiec_id, opis, is_active, updated_at, updated_by
                FROM konfiguracja_zbiornikow
                WHERE UPPER(TRIM(kod_zbiornika)) = %s
                LIMIT 1
            """, (kod_zbiornika.strip().upper(),))
            row = cursor.fetchone()
            if not row:
                return None
            return TankValidationRule(
                id=row['id'],
                kod_zbiornika=row['kod_zbiornika'],
                nazwa_surowca=row['nazwa_surowca'],
                surowiec_id=row['surowiec_id'],
                opis=row['opis'],
                is_active=bool(row['is_active']),
                updated_at=row['updated_at'],
                updated_by=row['updated_by']
            )
        finally:
            conn.close()

    @classmethod
    def upsert_rule(
        cls,
        kod_zbiornika: str,
        nazwa_surowca: str,
        surowiec_id: Optional[int] = None,
        opis: Optional[str] = None,
        is_active: bool = True,
        updated_by: Optional[str] = None
    ) -> bool:
        """Insert or update a tank validation rule."""
        if not kod_zbiornika:
            return False
        cls.ensure_table()
        norm_code = kod_zbiornika.strip().upper()
        norm_name = (nazwa_surowca or "").strip()
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO konfiguracja_zbiornikow 
                    (kod_zbiornika, nazwa_surowca, surowiec_id, opis, is_active, updated_at, updated_by)
                VALUES (%s, %s, %s, %s, %s, NOW(), %s)
                ON DUPLICATE KEY UPDATE
                    nazwa_surowca = VALUES(nazwa_surowca),
                    surowiec_id = VALUES(surowiec_id),
                    opis = VALUES(opis),
                    is_active = VALUES(is_active),
                    updated_at = NOW(),
                    updated_by = VALUES(updated_by)
            """, (
                norm_code,
                norm_name,
                surowiec_id,
                opis,
                1 if is_active else 0,
                updated_by
            ))
            conn.commit()
            return True
        finally:
            conn.close()

    @classmethod
    def delete_rule(cls, kod_zbiornika: str) -> bool:
        """Delete / clear a validation rule for a specific tank code."""
        if not kod_zbiornika:
            return False
        cls.ensure_table()
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM konfiguracja_zbiornikow
                WHERE UPPER(TRIM(kod_zbiornika)) = %s
            """, (kod_zbiornika.strip().upper(),))
            conn.commit()
            return True
        finally:
            conn.close()

    @classmethod
    def get_raw_materials_dictionary(cls) -> List[Dict[str, Any]]:
        """Get unique raw material names from dictionary and active warehouse."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            materials = []
            try:
                cursor.execute("""
                    SELECT id, nazwa, symbol, typ 
                    FROM magazyn_agro_slownik_surowce 
                    WHERE nazwa IS NOT NULL AND TRIM(nazwa) != ''
                    ORDER BY nazwa ASC
                """)
                materials = cursor.fetchall()
            except Exception:
                pass

            if not materials:
                try:
                    cursor.execute("""
                        SELECT DISTINCT nazwa 
                        FROM magazyn_surowce 
                        WHERE nazwa IS NOT NULL AND TRIM(nazwa) != ''
                        ORDER BY nazwa ASC
                    """)
                    rows = cursor.fetchall()
                    materials = [{'id': None, 'nazwa': r['nazwa'], 'symbol': '', 'typ': ''} for r in rows]
                except Exception:
                    materials = []
            return materials
        finally:
            conn.close()
