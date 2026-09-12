from datetime import datetime
from app.db import get_db_connection
from app.services.warehouse_history.history_indexer import HistoryIndexer

class MovementRecorder:
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
        """Record pallet movement in central palety_historia table."""
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cols = HistoryIndexer.get_table_columns(cur, 'palety_historia')
            if 'nr_palety' in cols:
                cur.execute("""
                    INSERT INTO palety_historia (
                        paleta_id, nr_palety, linia, typ_palety, akcja, 
                        lokalizacja_zrodlowa, lokalizacja_docelowa, 
                        komentarz, user_login, data_ruchu
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    paleta_id,
                    nr_palety,
                    (linia or 'PSD').upper(),
                    (typ_palety or 'surowiec').lower(),
                    (akcja or 'PRZESUNIECIE').upper(),
                    lokalizacja_zrodlowa,
                    lokalizacja_docelowa,
                    komentarz,
                    user_login or 'System',
                    datetime.now()
                ))
            else:
                cur.execute("""
                    INSERT INTO palety_historia (
                        paleta_id, linia, typ_palety, akcja, 
                        lokalizacja_zrodlowa, lokalizacja_docelowa, 
                        komentarz, user_login, data_ruchu
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    paleta_id,
                    (linia or 'PSD').upper(),
                    (typ_palety or 'surowiec').lower(),
                    (akcja or 'PRZESUNIECIE').upper(),
                    lokalizacja_zrodlowa,
                    lokalizacja_docelowa,
                    komentarz,
                    user_login or 'System',
                    datetime.now()
                ))
            conn.commit()
            return True
        except Exception as e:
            print(f"[MovementRecorder] Błąd zapisu ruchu: {e}")
            return False
        finally:
            conn.close()
