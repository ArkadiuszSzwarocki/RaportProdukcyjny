"""
Repozytorium dla składników receptury AGRO.

Odpowiedzialność:
    - Pobieranie składników receptury (READ)
    - Zapis/aktualizacja składników dla danego nr_receptury (WRITE)
    - Usuwanie pojedynczego składnika (DELETE)
    - Pobieranie listy receptur z produkty_receptury (READ)
"""
from __future__ import annotations

from typing import Any


class RecepturyAgroRepository:
    """CRUD dla tabeli receptury_agro_skladniki."""

    def __init__(self, conn) -> None:
        self._conn = conn

    # ------------------------------------------------------------------
    # READ
    # ------------------------------------------------------------------

    def get_skladniki(self, nr_receptury: str) -> list[dict[str, Any]]:
        """Zwraca listę aktywnych składników dla podanego nr_receptury."""
        cursor = self._conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id, nr_receptury, nazwa_produktu, kolejnosc,
                   skladnik_nazwa, ilosc_kg_szarza, typ, aktywny,
                   created_at, updated_at
            FROM receptury_agro_skladniki
            WHERE nr_receptury = %s AND aktywny = 1
            ORDER BY kolejnosc ASC, id ASC
            """,
            (nr_receptury,),
        )
        rows = cursor.fetchall()
        cursor.close()
        return rows

    def get_receptury(self) -> list[dict[str, Any]]:
        """Zwraca listę produktów z przypisanym nr_receptury."""
        cursor = self._conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT pr.id, pr.nazwa_produktu, pr.nr_receptury,
                   COUNT(ras.id) AS liczba_skladnikow
            FROM produkty_receptury pr
            LEFT JOIN receptury_agro_skladniki ras
                ON ras.nr_receptury = pr.nr_receptury AND ras.aktywny = 1
            WHERE pr.nr_receptury IS NOT NULL AND pr.nr_receptury != ''
            GROUP BY pr.id, pr.nazwa_produktu, pr.nr_receptury
            ORDER BY pr.nazwa_produktu ASC
            """
        )
        rows = cursor.fetchall()
        cursor.close()
        return rows

    # ------------------------------------------------------------------
    # WRITE — bulk upsert (replace entire list for nr_receptury)
    # ------------------------------------------------------------------

    def save_skladniki(
        self,
        nr_receptury: str,
        nazwa_produktu: str,
        skladniki: list[dict[str, Any]],
    ) -> None:
        """
        Nadpisuje listę składników dla podanego nr_receptury.

        Args:
            nr_receptury: Numer receptury (np. '213').
            nazwa_produktu: Nazwa produktu (dla czytelności w tabeli).
            skladniki: Lista słowników z kluczami:
                - skladnik_nazwa (str) — wymagane
                - ilosc_kg_szarza (float | None) — opcjonalne
                - typ (str) — 'surowiec' / 'dodatek', default 'surowiec'
                - kolejnosc (int) — pozycja na liście
        """
        cursor = self._conn.cursor()
        # Soft-delete poprzednich składników
        cursor.execute(
            "UPDATE receptury_agro_skladniki SET aktywny = 0 WHERE nr_receptury = %s",
            (nr_receptury,),
        )
        # Insert nowych składników
        for idx, s in enumerate(skladniki):
            nazwa = str(s.get("skladnik_nazwa", "")).strip()
            if not nazwa:
                continue
            ilosc = s.get("ilosc_kg_szarza")
            if ilosc is not None:
                try:
                    ilosc = float(ilosc)
                except (TypeError, ValueError):
                    ilosc = None
            typ = str(s.get("typ") or "surowiec").strip()
            kolejnosc = s.get("kolejnosc", idx)
            try:
                kolejnosc = int(kolejnosc)
            except (TypeError, ValueError):
                kolejnosc = idx
            cursor.execute(
                """
                INSERT INTO receptury_agro_skladniki
                    (nr_receptury, nazwa_produktu, kolejnosc,
                     skladnik_nazwa, ilosc_kg_szarza, typ, aktywny)
                VALUES (%s, %s, %s, %s, %s, %s, 1)
                """,
                (nr_receptury, nazwa_produktu, kolejnosc, nazwa, ilosc, typ),
            )
        self._conn.commit()
        cursor.close()

    # ------------------------------------------------------------------
    # DELETE
    # ------------------------------------------------------------------

    def delete_skladnik(self, skladnik_id: int) -> bool:
        """Soft-delete pojedynczego składnika. Zwraca True jeśli znaleziono."""
        cursor = self._conn.cursor()
        cursor.execute(
            "UPDATE receptury_agro_skladniki SET aktywny = 0 WHERE id = %s",
            (skladnik_id,),
        )
        affected = cursor.rowcount
        self._conn.commit()
        cursor.close()
        return affected > 0
