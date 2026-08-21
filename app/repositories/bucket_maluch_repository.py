from datetime import datetime
from typing import Any, Dict, List, Optional
from app.db import get_db_connection


class BucketMaluchRepository:
    """Repository for database operations on wiaderka_maluchy and wiaderka_maluchy_pozycje."""

    @staticmethod
    def create_bucket(
        kod_wiadra: str, 
        plan_id: int, 
        linia: str = 'PSD', 
        operator_login: Optional[str] = None,
        nr_sscc: Optional[str] = None,
        data_produkcji: Optional[datetime] = None,
        data_przydatnosci: Optional[datetime] = None
    ) -> int:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO wiaderka_maluchy 
                (kod_wiadra, nr_sscc, plan_id, linia, status, waga_calkowita, operator_nawazyl_login, data_produkcji, data_przydatnosci, data_rozpoczecia)
                VALUES (%s, %s, %s, %s, 'w_trakcie_nawazania', 0, %s, %s, %s, NOW())
                """,
                (kod_wiadra.strip().upper(), nr_sscc, plan_id, linia.upper(), operator_login, data_produkcji, data_przydatnosci),
            )
            bucket_id = cur.lastrowid
            conn.commit()
            return bucket_id
        finally:
            conn.close()

    @staticmethod
    def update_bucket_sscc(bucket_id: int, nr_sscc: str, data_produkcji: datetime, data_przydatnosci: datetime) -> bool:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE wiaderka_maluchy 
                SET nr_sscc = %s, data_produkcji = %s, data_przydatnosci = %s
                WHERE id = %s
                """,
                (nr_sscc, data_produkcji, data_przydatnosci, bucket_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    @staticmethod
    def find_by_sscc(nr_sscc: str) -> Optional[Dict[str, Any]]:
        conn = get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM wiaderka_maluchy WHERE nr_sscc = %s ORDER BY id DESC LIMIT 1", (nr_sscc.strip(),))
            row = cur.fetchone()
            if not row:
                return None
            row['pozycje'] = BucketMaluchRepository.get_items_for_bucket(row['id'])
            return row
        finally:
            conn.close()

    @staticmethod
    def find_by_id(bucket_id: int) -> Optional[Dict[str, Any]]:
        conn = get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM wiaderka_maluchy WHERE id = %s", (bucket_id,))
            row = cur.fetchone()
            if not row:
                return None
            row['pozycje'] = BucketMaluchRepository.get_items_for_bucket(bucket_id)
            return row
        finally:
            conn.close()

    @staticmethod
    def find_active_or_completed_by_code(kod_wiadra: str, linia: Optional[str] = None) -> Optional[Dict[str, Any]]:
        conn = get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            if linia:
                cur.execute(
                    """
                    SELECT * FROM wiaderka_maluchy 
                    WHERE kod_wiadra = %s AND linia = %s AND status IN ('w_trakcie_nawazania', 'skompletowane')
                    ORDER BY id DESC LIMIT 1
                    """,
                    (kod_wiadra.strip().upper(), linia.upper()),
                )
            else:
                cur.execute(
                    """
                    SELECT * FROM wiaderka_maluchy 
                    WHERE kod_wiadra = %s AND status IN ('w_trakcie_nawazania', 'skompletowane')
                    ORDER BY id DESC LIMIT 1
                    """,
                    (kod_wiadra.strip().upper(),),
                )
            row = cur.fetchone()
            if row:
                row['pozycje'] = BucketMaluchRepository.get_items_for_bucket(row['id'])
            return row
        finally:
            conn.close()

    @staticmethod
    def find_latest_by_code(kod_wiadra: str) -> Optional[Dict[str, Any]]:
        conn = get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT * FROM wiaderka_maluchy 
                WHERE kod_wiadra = %s
                ORDER BY id DESC LIMIT 1
                """,
                (kod_wiadra.strip().upper(),),
            )
            row = cur.fetchone()
            if row:
                row['pozycje'] = BucketMaluchRepository.get_items_for_bucket(row['id'])
            return row
        finally:
            conn.close()

    @staticmethod
    def add_item(bucket_id: int, stacja_kod: str, surowiec_nazwa: str, waga: float, operator_login: Optional[str] = None) -> int:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO wiaderka_maluchy_pozycje 
                (wiaderko_id, stacja_kod, surowiec_nazwa, waga_faktyczna, data_nawazenia, operator_login)
                VALUES (%s, %s, %s, %s, NOW(), %s)
                """,
                (bucket_id, stacja_kod.strip().upper(), surowiec_nazwa.strip(), waga, operator_login),
            )
            item_id = cur.lastrowid
            
            # Recalculate total weight on bucket
            cur.execute(
                """
                UPDATE wiaderka_maluchy 
                SET waga_calkowita = (SELECT COALESCE(SUM(waga_faktyczna), 0) FROM wiaderka_maluchy_pozycje WHERE wiaderko_id = %s)
                WHERE id = %s
                """,
                (bucket_id, bucket_id),
            )
            conn.commit()
            return item_id
        finally:
            conn.close()

    @staticmethod
    def remove_item(item_id: int, bucket_id: int) -> bool:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM wiaderka_maluchy_pozycje WHERE id = %s AND wiaderko_id = %s", (item_id, bucket_id))
            cur.execute(
                """
                UPDATE wiaderka_maluchy 
                SET waga_calkowita = (SELECT COALESCE(SUM(waga_faktyczna), 0) FROM wiaderka_maluchy_pozycje WHERE wiaderko_id = %s)
                WHERE id = %s
                """,
                (bucket_id, bucket_id),
            )
            conn.commit()
            return True
        finally:
            conn.close()

    @staticmethod
    def delete_bucket(bucket_id: int) -> bool:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM wiaderka_maluchy_pozycje WHERE wiaderko_id = %s", (bucket_id,))
            cur.execute("DELETE FROM wiaderka_maluchy WHERE id = %s", (bucket_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    @staticmethod
    def complete_bucket(bucket_id: int) -> bool:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE wiaderka_maluchy 
                SET status = 'skompletowane', data_skompletowania = NOW()
                WHERE id = %s AND status = 'w_trakcie_nawazania'
                """,
                (bucket_id,),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    @staticmethod
    def dump_bucket_to_mixer(bucket_id: int, szarza_id: Optional[int], operator_login: Optional[str] = None, mieszalnik_kod: str = 'MI01') -> bool:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE wiaderka_maluchy 
                SET status = 'wrzucone_do_mieszalnika', 
                    szarza_id = %s, 
                    mieszalnik_kod = %s,
                    operator_zasypal_login = %s, 
                    data_zasypania = NOW()
                WHERE id = %s AND status IN ('w_trakcie_nawazania', 'skompletowane')
                """,
                (szarza_id, mieszalnik_kod.strip().upper(), operator_login, bucket_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    @staticmethod
    def get_items_for_bucket(bucket_id: int) -> List[Dict[str, Any]]:
        conn = get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT id, wiaderko_id, stacja_kod, surowiec_nazwa, waga_faktyczna, data_nawazenia, operator_login
                FROM wiaderka_maluchy_pozycje 
                WHERE wiaderko_id = %s 
                ORDER BY id ASC
                """,
                (bucket_id,),
            )
            return cur.fetchall()
        finally:
            conn.close()

    @staticmethod
    def get_buckets_by_plan(plan_id: int, linia: str = 'PSD') -> List[Dict[str, Any]]:
        conn = get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT * FROM wiaderka_maluchy 
                WHERE plan_id = %s AND linia = %s
                ORDER BY id DESC
                """,
                (plan_id, linia.upper()),
            )
            buckets = cur.fetchall()
            for b in buckets:
                b['pozycje'] = BucketMaluchRepository.get_items_for_bucket(b['id'])
            return buckets
        finally:
            conn.close()

    @staticmethod
    def get_dumped_buckets_for_szarza(szarza_id: int, plan_id: int, linia: str = 'PSD') -> List[Dict[str, Any]]:
        conn = get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT * FROM wiaderka_maluchy 
                WHERE szarza_id = %s AND plan_id = %s AND linia = %s AND status = 'wrzucone_do_mieszalnika'
                ORDER BY data_zasypania ASC, id ASC
                """,
                (szarza_id, plan_id, linia.upper()),
            )
            buckets = cur.fetchall()
            for b in buckets:
                b['pozycje'] = BucketMaluchRepository.get_items_for_bucket(b['id'])
            return buckets
        finally:
            conn.close()
