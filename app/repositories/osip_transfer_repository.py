"""
Repozytorium do obsługi operacji bazodanowych dla transferów wewnętrznych OSIP.
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid

from app.core.database import get_db_connection
from app.models.osip_transfer_model import OsipTransferModel
from app.models.osip_transfer_item_model import OsipTransferItemModel


class OsipTransferRepository:
    def create_transfer(self, source_warehouse: str, destination_warehouse: str, created_by: str, notes: Optional[str] = None) -> OsipTransferModel:
        transfer_code = f"TR-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            query = """
                INSERT INTO osip_transfers (transfer_code, source_warehouse, destination_warehouse, status, created_by, notes)
                VALUES (%s, %s, %s, 'PLANNED', %s, %s)
            """
            cursor.execute(query, (transfer_code, source_warehouse, destination_warehouse, created_by, notes))
            transfer_id = cursor.lastrowid
            conn.commit()
            return self.get_transfer_by_id(transfer_id)
        finally:
            cursor.close()
            conn.close()

    def add_transfer_items(self, transfer_id: int, items: List[Dict[str, Any]]) -> None:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            query = """
                INSERT INTO osip_transfer_items (transfer_id, pallet_id, nr_palety, product_name, item_type, requested_qty, loaded_qty, unit, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'PLANNED')
            """
            params = [
                (
                    transfer_id,
                    item.get('pallet_id'),
                    item.get('nr_palety'),
                    item.get('product_name', ''),
                    item.get('item_type', 'raw'),
                    float(item.get('requested_qty', 0.0)),
                    float(item.get('loaded_qty', 0.0)),
                    item.get('unit', 'kg')
                )
                for item in items
            ]
            cursor.executemany(query, params)
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    def get_transfer_by_id(self, transfer_id: int) -> Optional[OsipTransferModel]:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT * FROM osip_transfers WHERE id = %s", (transfer_id,))
            t_row = cursor.fetchone()
            if not t_row:
                return None

            cursor.execute("SELECT * FROM osip_transfer_items WHERE transfer_id = %s", (transfer_id,))
            i_rows = cursor.fetchall()

            items = [
                OsipTransferItemModel(
                    id=row['id'],
                    transfer_id=row['transfer_id'],
                    pallet_id=row['pallet_id'],
                    nr_palety=row['nr_palety'],
                    product_name=row['product_name'],
                    item_type=row['item_type'],
                    requested_qty=float(row['requested_qty']),
                    loaded_qty=float(row['loaded_qty']),
                    unit=row['unit'],
                    status=row['status'],
                    created_at=row['created_at']
                )
                for row in i_rows
            ]

            return OsipTransferModel(
                id=t_row['id'],
                transfer_code=t_row['transfer_code'],
                source_warehouse=t_row['source_warehouse'],
                destination_warehouse=t_row['destination_warehouse'],
                status=t_row['status'],
                created_by=t_row['created_by'],
                dispatched_by=t_row['dispatched_by'],
                completed_by=t_row['completed_by'],
                notes=t_row['notes'],
                created_at=t_row['created_at'],
                dispatched_at=t_row['dispatched_at'],
                completed_at=t_row['completed_at'],
                items=items
            )
        finally:
            cursor.close()
            conn.close()

    def get_all_transfers(self, warehouse_filter: Optional[str] = None) -> List[OsipTransferModel]:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            if warehouse_filter:
                query = """
                    SELECT * FROM osip_transfers
                    WHERE source_warehouse = %s OR destination_warehouse = %s
                    ORDER BY created_at DESC
                """
                cursor.execute(query, (warehouse_filter, warehouse_filter))
            else:
                query = "SELECT * FROM osip_transfers ORDER BY created_at DESC"
                cursor.execute(query)

            rows = cursor.fetchall()
            transfers = []
            for r in rows:
                t = self.get_transfer_by_id(r['id'])
                if t:
                    transfers.append(t)
            return transfers
        finally:
            cursor.close()
            conn.close()

    def update_transfer_status(self, transfer_id: int, status: str, user_login: str, timestamp_field: Optional[str] = None) -> None:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            user_field = "dispatched_by" if status == "IN_TRANSIT" else ("completed_by" if status == "COMPLETED" else None)
            time_field = "dispatched_at" if status == "IN_TRANSIT" else ("completed_at" if status == "COMPLETED" else None)

            updates = ["status = %s"]
            params = [status]

            if user_field:
                updates.append(f"{user_field} = %s")
                params.append(user_login)
            if time_field:
                updates.append(f"{time_field} = %s")
                params.append(datetime.now())

            params.append(transfer_id)
            query = f"UPDATE osip_transfers SET {', '.join(updates)} WHERE id = %s"
            cursor.execute(query, params)
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    def update_items_loaded(self, transfer_id: int, loaded_items: List[Dict[str, Any]]) -> None:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            for item in loaded_items:
                cursor.execute("""
                    UPDATE osip_transfer_items
                    SET pallet_id = %s, nr_palety = %s, loaded_qty = %s, status = 'LOADED'
                    WHERE id = %s AND transfer_id = %s
                """, (item.get('pallet_id'), item.get('nr_palety'), float(item.get('loaded_qty', 0.0)), item['id'], transfer_id))
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    def is_pallet_in_active_transfer(self, pallet_id: int) -> bool:
        """Sprawdza, czy paleta jest już w transferze, który nie jest zakończony ani anulowany."""
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT t.id 
                FROM osip_transfers t
                JOIN osip_transfer_items i ON t.id = i.transfer_id
                WHERE i.pallet_id = %s AND t.status IN ('PLANNED', 'IN_TRANSIT')
                LIMIT 1
            """, (pallet_id,))
            result = cursor.fetchone()
            return bool(result)
        finally:
            cursor.close()
            conn.close()
