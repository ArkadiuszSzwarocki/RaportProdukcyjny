"""
Repozytorium zamówień magazynowych.

Odpowiedzialność: Operacje CRUD na tabeli magazyn_zamowienia.
Brak logiki biznesowej — tylko dostęp do danych.
"""
from datetime import datetime
import json
from app.core.database import get_db_connection


class WarehouseOrderRepository:
    """Warstwa dostępu do danych zamówień magazynowych."""

    @staticmethod
    def create(items, operator_login, komentarz=None):
        """Tworzy nowe zamówienie w bazie.

        Args:
            items: Lista obiektów (dict) reprezentująca zamówione surowce.
            operator_login: Login operatora składającego zamówienie.
            komentarz: Opcjonalny komentarz do zamówienia.

        Returns:
            int: ID nowo utworzonego zamówienia.
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            items_json = json.dumps(items, ensure_ascii=False)
            cursor.execute(
                """
                INSERT INTO magazyn_zamowienia 
                    (items, operator_login, komentarz, status, created_at)
                VALUES (%s, %s, %s, 'NOWE', %s)
                """,
                (items_json, operator_login, komentarz, datetime.now())
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    @staticmethod
    def get_all(status_filter=None):
        """Pobiera listę zamówień z opcjonalnym filtrem statusu.

        Args:
            status_filter: Opcjonalny filtr ('NOWE', 'ZAMKNIETE').

        Returns:
            list[dict]: Lista zamówień posortowana od najnowszych.
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            if status_filter:
                cursor.execute(
                    "SELECT * FROM magazyn_zamowienia WHERE status = %s ORDER BY created_at DESC",
                    (status_filter,)
                )
            else:
                cursor.execute(
                    "SELECT * FROM magazyn_zamowienia ORDER BY created_at DESC"
                )
            return cursor.fetchall()
        finally:
            conn.close()

    @staticmethod
    def get_by_id(order_id):
        """Pobiera zamówienie po ID.

        Args:
            order_id: ID zamówienia.

        Returns:
            dict | None: Dane zamówienia lub None.
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM magazyn_zamowienia WHERE id = %s",
                (order_id,)
            )
            return cursor.fetchone()
        finally:
            conn.close()

    @staticmethod
    def confirm(order_id, magazynier_login):
        """Potwierdza odczytanie zamówienia — zmiana statusu na ZAMKNIETE.

        Args:
            order_id: ID zamówienia do potwierdzenia.
            magazynier_login: Login magazyniera potwierdzającego.

        Returns:
            int: Liczba zaktualizowanych wierszy (0 jeśli nie znaleziono lub już zamknięte).
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE magazyn_zamowienia 
                SET status = 'ZAMKNIETE', 
                    magazynier_login = %s, 
                    confirmed_at = %s
                WHERE id = %s AND status = 'NOWE'
                """,
                (magazynier_login, datetime.now(), order_id)
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    @staticmethod
    def get_available_surowce():
        """Pobiera listę dostępnych surowców ze słownika.

        Returns:
            list[dict]: Lista surowców (id, nazwa).
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT id, nazwa FROM magazyn_agro_slownik_surowce ORDER BY nazwa ASC"
            )
            return cursor.fetchall()
        finally:
            conn.close()

    @staticmethod
    def check_stock(surowce_names, linia='AGRO'):
        """Sprawdza łączny stan magazynowy dla podanych nazw surowców.

        Args:
            surowce_names: Lista nazw surowców do sprawdzenia.
            linia: Nazwa linii ('AGRO' lub 'PSD'). (Zunifikowane - wszystko w magazyn_surowce)

        Returns:
            dict: Słownik z aktualnymi stanami (np. {'Biała': 1200.5}).
        """
        if not surowce_names:
            return {}

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            placeholders = ', '.join(['%s'] * len(surowce_names))
            
            # Tabele surowców zostały zunifikowane (nie ma osobno dodatków, ani agro)
            query = f"""
                SELECT nazwa, SUM(stan_magazynowy) as total_stan
                FROM magazyn_surowce
                WHERE nazwa IN ({placeholders})
                GROUP BY nazwa
            """
            
            cursor.execute(query, tuple(surowce_names))
            
            results = cursor.fetchall()
            stock_dict = {row['nazwa']: float(row['total_stan'] or 0) for row in results}
            
            return stock_dict
        finally:
            conn.close()
