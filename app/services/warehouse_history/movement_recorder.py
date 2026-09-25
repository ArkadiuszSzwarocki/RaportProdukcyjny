from datetime import datetime
import uuid

from app.db import get_db_connection
from app.services.warehouse_history.history_indexer import HistoryIndexer


class MovementRecorder:
    _ACTION_ALIASES = {
        'PRZEMIESZCZENIE': 'PRZESUNIECIE',
        'PRZENIESIENIE': 'PRZESUNIECIE',
        'TRANSFER': 'PRZESUNIECIE',
    }
    _MOVEMENT_ACTIONS = {
        'PRZESUNIECIE', 'PRZYJECIE', 'DOSTAWA_PRZYJECIE',
        'WYDANIE_PRODUKCJA', 'ZUZYCIE_PRODUKCJA', 'PRZYJECIE_ZWROT',
    }

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
        nr_palety: str | None = None,
        *,
        cursor=None,
        connection=None,
        event_id: str | None = None,
        entity_type: str | None = None,
        operation_id: str | None = None,
        quantity_before: float | None = None,
        quantity_after: float | None = None,
        occurred_at: datetime | None = None,
    ) -> bool:
        """Record one normalized, idempotent event, optionally in the caller's transaction."""
        owns_connection = connection is None
        conn = connection or get_db_connection()
        try:
            cur = cursor or conn.cursor()
            cols = HistoryIndexer.get_table_columns(cur, 'palety_historia')
            normalized_action = (akcja or 'PRZESUNIECIE').strip().upper()
            normalized_action = MovementRecorder._ACTION_ALIASES.get(normalized_action, normalized_action)
            source = str(lokalizacja_zrodlowa or '').strip().upper() or None
            destination = str(lokalizacja_docelowa or '').strip().upper() or None
            sscc = str(nr_palety or '').strip().upper() or None
            entity = str(entity_type or typ_palety or 'surowiec').strip().lower()
            event_time = occurred_at or datetime.now()

            if normalized_action in MovementRecorder._MOVEMENT_ACTIONS:
                source = source or 'NIEZNANE'
                destination = destination or 'NIEZNANE'
            if source and destination and source == destination and normalized_action == 'PRZESUNIECIE':
                return False

            # A stable operation/event ID makes retries idempotent without suppressing
            # two legitimate, identical movements performed close to each other.
            idempotency_filters = []
            idempotency_params = []
            if event_id and 'event_id' in cols:
                idempotency_filters.append("event_id = %s")
                idempotency_params.append(event_id)
            if operation_id and 'operation_id' in cols:
                idempotency_filters.append("(operation_id = %s AND akcja = %s)")
                idempotency_params.extend([operation_id, normalized_action])
            if idempotency_filters:
                cur.execute(
                    f"SELECT id FROM palety_historia WHERE {' OR '.join(idempotency_filters)} LIMIT 1",
                    tuple(idempotency_params),
                )
                if cur.fetchone():
                    return True
            elif 'nr_palety' in cols:
                # Legacy callers have no operation key. Protect only immediate retries.
                cur.execute("""
                    SELECT id FROM palety_historia
                    WHERE COALESCE(paleta_id, -1) = COALESCE(%s, -1)
                      AND COALESCE(nr_palety, '') = COALESCE(%s, '')
                      AND akcja = %s
                      AND COALESCE(lokalizacja_zrodlowa, '') = COALESCE(%s, '')
                      AND COALESCE(lokalizacja_docelowa, '') = COALESCE(%s, '')
                      AND COALESCE(komentarz, '') = COALESCE(%s, '')
                      AND data_ruchu >= DATE_SUB(%s, INTERVAL 10 SECOND)
                    LIMIT 1
                """, (paleta_id, sscc, normalized_action, source, destination, komentarz, event_time))
                if cur.fetchone():
                    return True

            values = {
                'event_id': event_id or str(uuid.uuid4()),
                'paleta_id': paleta_id,
                'nr_palety': sscc,
                'linia': (linia or 'PSD').upper(),
                'typ_palety': (typ_palety or 'surowiec').lower(),
                'entity_type': entity,
                'operation_id': operation_id,
                'akcja': normalized_action,
                'lokalizacja_zrodlowa': source,
                'lokalizacja_docelowa': destination,
                'quantity_before': quantity_before,
                'quantity_after': quantity_after,
                'komentarz': komentarz,
                'user_login': user_login or 'System',
                'data_ruchu': event_time,
            }
            insert_cols = [name for name in values if name in cols]
            placeholders = ', '.join(['%s'] * len(insert_cols))
            cur.execute(
                f"INSERT INTO palety_historia ({', '.join(insert_cols)}) VALUES ({placeholders})",
                tuple(values[name] for name in insert_cols),
            )
            if owns_connection:
                conn.commit()
            return True
        except Exception as e:
            if owns_connection:
                conn.rollback()
            print(f"[MovementRecorder] Błąd zapisu ruchu: {e}")
            return False
        finally:
            if owns_connection:
                conn.close()
