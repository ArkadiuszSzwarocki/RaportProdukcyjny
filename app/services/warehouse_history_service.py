"""
WarehouseHistoryService — central warehouse and production movement history service facade.
Consolidates movement logging and querying across palety_historia, magazyn_ruch (PSD),
and magazyn_agro_ruch (AGRO) for all production lines and stations.
"""

from app.db import get_db_connection
from app.services.warehouse_history.history_indexer import HistoryIndexer
from app.services.warehouse_history.movement_recorder import MovementRecorder
from app.services.warehouse_history.history_query_service import HistoryQueryService
from app.services.warehouse_history.history_enricher_service import HistoryEnricherService


class WarehouseHistoryService:
    """Facade for warehouse history recording, indexing, and unified retrieval."""

    @classmethod
    def _get_table_columns(cls, cursor, table_name: str) -> set[str]:
        """Safely fetch existing column names in lowercase for a given table with in-memory caching."""
        return HistoryIndexer.get_table_columns(cursor, table_name)

    @classmethod
    def _ensure_performance_indexes(cls, cursor, conn):
        """Ensure critical database indexes exist once during application lifetime."""
        HistoryIndexer.ensure_performance_indexes(cursor, conn)

    @staticmethod
    def record_movement(
        paleta_id: int | None,
        linia: str,
        typ_palety: str,
        akcja: str,
        lokalizacja_zrodlowa: str | None,
        lokalizacja_docelowa: str | None,
        komentarz: str | None,
        user_login: str | None = 'System',
        nr_palety: str | None = None
    ) -> bool:
        """Record pallet/material movement in the central palety_historia table."""
        return MovementRecorder.record_movement(
            paleta_id=paleta_id,
            linia=linia,
            typ_palety=typ_palety,
            akcja=akcja,
            lokalizacja_zrodlowa=lokalizacja_zrodlowa,
            lokalizacja_docelowa=lokalizacja_docelowa,
            komentarz=komentarz,
            user_login=user_login,
            nr_palety=nr_palety
        )

    @staticmethod
    def get_unified_station_and_movement_history(
        linia: str = 'ALL',
        data_od: str | None = None,
        data_do: str | None = None,
        surowiec: str | None = None,
        stacja: str | None = None,
        typ_operacji: str | None = None,
        limit: int = 500
    ) -> list[dict]:
        """
        Return unified warehouse and station movement history combining palety_historia
        and legacy movement tables (magazyn_ruch / magazyn_agro_ruch).
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            
            raw_rows = HistoryQueryService.query_all_history_sources(
                cursor=cursor,
                conn=conn,
                linia=linia,
                data_od=data_od,
                data_do=data_do,
                surowiec=surowiec,
                stacja=stacja,
                typ_operacji=typ_operacji,
                limit=limit
            )

            return HistoryEnricherService.enrich_and_filter_history(
                cursor=cursor,
                all_rows=raw_rows,
                linia=linia,
                surowiec=surowiec,
                stacja=stacja,
                typ_operacji=typ_operacji,
                limit=limit
            )
        except Exception as e:
            print(f"[WarehouseHistoryService] Błąd pobierania historii: {e}")
            return []
        finally:
            conn.close()
