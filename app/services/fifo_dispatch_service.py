from typing import Dict, Any, List, Optional
from datetime import datetime
from app.db import get_db_connection, get_table_name

class FifoDispatchService:
    """
    Domain service for FIFO (First In, First Out) compliance verification and smart picking advice.
    Ensures oldest available raw materials and packaging units are consumed before newer batches.
    """

    @staticmethod
    def check_fifo_compliance(
        product_name: str,
        scanned_pallet_id: int,
        linia: str = 'PSD',
        pallet_type: str = 'Surowiec'
    ) -> Dict[str, Any]:
        """
        Validates whether the scanned pallet is the oldest available in accordance with FIFO rules.
        If an older batch exists on stock, returns is_fifo_compliant=False along with recommended pallet details.
        """
        if not product_name:
            return {"is_fifo_compliant": True, "message": "Brak nazwy produktu do weryfikacji FIFO."}

        norm_line = str(linia or 'PSD').upper()
        p_type = str(pallet_type or 'Surowiec').lower()

        if 'opak' in p_type:
            table = get_table_name('magazyn_opakowania', norm_line)
            col_qty = 'stan_magazynowy'
        elif 'dodat' in p_type:
            table = 'magazyn_dodatki'
            col_qty = 'stan_magazynowy'
        else:
            table = get_table_name('magazyn_surowce', norm_line)
            col_qty = 'stan_magazynowy'

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            
            # Fetch the scanned pallet info
            cursor.execute(f"SELECT * FROM {table} WHERE id = %s", (scanned_pallet_id,))
            scanned_pallet = cursor.fetchone()
            if not scanned_pallet:
                return {"is_fifo_compliant": True, "message": "Paleta nie została znaleziona w bazie."}

            scanned_date = scanned_pallet.get('data_przyjecia') or scanned_pallet.get('data_produkcji') or scanned_pallet.get('created_at')
            scanned_id = scanned_pallet.get('id')

            # Query all active available pallets for the same product, ordered by age (FIFO)
            query = f"""
                SELECT id, nr_palety, nazwa, {col_qty} as amount, lokalizacja,
                       data_przyjecia, data_produkcji, data_przydatnosci, nr_partii
                FROM {table}
                WHERE UPPER(nazwa) = UPPER(%s)
                  AND {col_qty} > 0
                  AND UPPER(COALESCE(lokalizacja, '')) NOT LIKE 'OCZEK%%'
                  AND id <> %s
                ORDER BY 
                    COALESCE(data_przydatnosci, '9999-12-31') ASC,
                    COALESCE(data_przyjecia, data_produkcji, '9999-12-31') ASC,
                    id ASC
            """
            cursor.execute(query, (product_name, scanned_id))
            older_candidates = cursor.fetchall() or []

            if not older_candidates:
                return {
                    "is_fifo_compliant": True,
                    "scanned_pallet_id": scanned_id,
                    "message": "Paleta jest zgodna z zasadą FIFO (brak starszych partii)."
                }

            # Check if top candidate is significantly older (e.g. earlier date or lower ID)
            top_oldest = older_candidates[0]
            top_date = top_oldest.get('data_przyjecia') or top_oldest.get('data_produkcji')
            
            # If the oldest candidate has a strictly earlier date or earlier ID
            is_older = False
            if top_date and scanned_date and str(top_date) < str(scanned_date):
                is_older = True
            elif not top_date and top_oldest.get('id', 0) < scanned_id:
                is_older = True

            if is_older:
                return {
                    "is_fifo_compliant": False,
                    "scanned_pallet_id": scanned_id,
                    "scanned_pallet_code": scanned_pallet.get('nr_palety') or f"ID-{scanned_id}",
                    "recommended_pallet": {
                        "id": top_oldest.get('id'),
                        "nr_palety": top_oldest.get('nr_palety') or f"ID-{top_oldest.get('id')}",
                        "lokalizacja": top_oldest.get('lokalizacja'),
                        "amount": top_oldest.get('amount'),
                        "nr_partii": top_oldest.get('nr_partii'),
                        "data_przyjecia": str(top_oldest.get('data_przyjecia') or '')
                    },
                    "message": f"Uwaga: W magazynie znajduje się starsza partia surowca ({top_oldest.get('nr_palety') or top_oldest.get('id')}) w lokalizacji {top_oldest.get('lokalizacja')} (Zasada FIFO)."
                }

            return {
                "is_fifo_compliant": True,
                "scanned_pallet_id": scanned_id,
                "message": "Paleta jest zgodna z zasadą FIFO."
            }
        finally:
            conn.close()

    @staticmethod
    def get_fifo_recommended_pallet(
        product_name: str,
        linia: str = 'PSD',
        pallet_type: str = 'Surowiec'
    ) -> Optional[Dict[str, Any]]:
        """
        Returns the top FIFO-recommended pallet to pick for a given product.
        """
        norm_line = str(linia or 'PSD').upper()
        p_type = str(pallet_type or 'Surowiec').lower()

        if 'opak' in p_type:
            table = get_table_name('magazyn_opakowania', norm_line)
            col_qty = 'stan_magazynowy'
        elif 'dodat' in p_type:
            table = 'magazyn_dodatki'
            col_qty = 'stan_magazynowy'
        else:
            table = get_table_name('magazyn_surowce', norm_line)
            col_qty = 'stan_magazynowy'

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            query = f"""
                SELECT id, nr_palety, nazwa, {col_qty} as amount, lokalizacja,
                       data_przyjecia, data_produkcji, data_przydatnosci, nr_partii
                FROM {table}
                WHERE UPPER(nazwa) = UPPER(%s)
                  AND {col_qty} > 0
                  AND UPPER(COALESCE(lokalizacja, '')) NOT LIKE 'OCZEK%%'
                ORDER BY 
                    COALESCE(data_przydatnosci, '9999-12-31') ASC,
                    COALESCE(data_przyjecia, data_produkcji, '9999-12-31') ASC,
                    id ASC
                LIMIT 1
            """
            cursor.execute(query, (product_name,))
            return cursor.fetchone()
        finally:
            conn.close()
