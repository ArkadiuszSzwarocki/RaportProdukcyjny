"""
Serwis zarządzenia cyklem życia transferów wewnętrznych OSIP <-> Centrala.
"""
from typing import List, Dict, Any, Optional
from app.repositories.osip_transfer_repository import OsipTransferRepository
from app.models.osip_transfer_model import OsipTransferModel
from app.core.database import get_db_connection


class OsipTransferService:
    IN_TRANSIT_LOCATION = "W_TRANZYCIE_OSIP"

    def __init__(self, repository: Optional[OsipTransferRepository] = None):
        self.repository = repository or OsipTransferRepository()

    def get_transfer_by_id(self, transfer_id: int) -> Optional[OsipTransferModel]:
        """Pobiera zlecenie transferu po ID."""
        return self.repository.get_transfer_by_id(transfer_id)

    def create_transfer_order(self, source_warehouse: str, destination_warehouse: str, items: List[Dict[str, Any]], created_by: str, notes: Optional[str] = None) -> OsipTransferModel:
        """Tworzy zaplanowane zlecenie transferu z pozycjami."""
        if not items:
            raise ValueError("Zlecenie transferu musi zawierać co najmniej jedną pozycję.")

        transfer = self.repository.create_transfer(source_warehouse, destination_warehouse, created_by, notes)
        self.repository.add_transfer_items(transfer.id, items)
        return self.repository.get_transfer_by_id(transfer.id)

    def dispatch_transfer(self, transfer_id: int, loaded_pallets: List[Dict[str, Any]], user_login: str) -> OsipTransferModel:
        """Wykonuje załadunek zlecenia - przestawia status palet na W_TRANZYCIE_OSIP."""
        transfer = self.repository.get_transfer_by_id(transfer_id)
        if not transfer:
            raise ValueError("Nie znaleziono zlecenia transferu.")

        if transfer.status != "PLANNED":
            raise ValueError(f"Nie można załadować zlecenia w statusie {transfer.status}.")

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            # Przestawiamy lokalizację wybranych palet na W_TRANZYCIE_OSIP
            items_to_update = loaded_pallets if loaded_pallets else [
                {'pallet_id': item.pallet_id, 'nr_palety': item.nr_palety, 'loaded_qty': item.requested_qty, 'id': item.id} 
                for item in transfer.items
            ]
            
            for item in items_to_update:
                pallet_id = item.get("pallet_id")
                nr_palety = item.get("nr_palety")
                if pallet_id:
                    cursor.execute(
                        "UPDATE magazyn_surowce SET lokalizacja = %s WHERE id = %s",
                        (self.IN_TRANSIT_LOCATION, pallet_id)
                    )
                elif nr_palety:
                    cursor.execute(
                        "UPDATE magazyn_surowce SET lokalizacja = %s WHERE nr_palety = %s",
                        (self.IN_TRANSIT_LOCATION, nr_palety)
                    )

            conn.commit()
        finally:
            cursor.close()
            conn.close()

        self.repository.update_items_loaded(transfer_id, loaded_pallets)
        self.repository.update_transfer_status(transfer_id, "IN_TRANSIT", user_login)
        return self.repository.get_transfer_by_id(transfer_id)

    def receive_transfer(self, transfer_id: int, target_locations: Dict[Any, str], user_login: str) -> OsipTransferModel:
        """Przyjmuje transfer w magazynie docelowym i ustawia docelowe lokalizacje palet (np. OS01, OSIP lub MS01)."""
        transfer = self.repository.get_transfer_by_id(transfer_id)
        if not transfer:
            raise ValueError("Nie znaleziono zlecenia transferu.")

        if transfer.status not in ("PLANNED", "IN_TRANSIT"):
            raise ValueError(f"Nie można przyjąć zlecenia w statusie {transfer.status}.")

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            for item in transfer.items:
                # Find matching target location by item.id, item.pallet_id, or item.nr_palety
                new_loc = target_locations.get(item.id) or target_locations.get(item.pallet_id) or target_locations.get(item.nr_palety)
                if not new_loc:
                    new_loc = target_locations.get('default', transfer.destination_warehouse)
                
                new_loc = str(new_loc or transfer.destination_warehouse).strip().upper()

                if item.pallet_id:
                    cursor.execute(
                        "UPDATE magazyn_surowce SET lokalizacja = %s WHERE id = %s",
                        (new_loc, item.pallet_id)
                    )
                elif item.nr_palety:
                    cursor.execute(
                        "UPDATE magazyn_surowce SET lokalizacja = %s WHERE nr_palety = %s",
                        (new_loc, item.nr_palety)
                    )
                
                cursor.execute(
                    "UPDATE osip_transfer_items SET status = 'RECEIVED' WHERE id = %s",
                    (item.id,)
                )

            conn.commit()
        finally:
            cursor.close()
            conn.close()

        self.repository.update_transfer_status(transfer_id, "COMPLETED", user_login)
        return self.repository.get_transfer_by_id(transfer_id)

    def receive_single_item(self, transfer_id: int, pallet_code: str, target_location: str, user_login: str) -> Dict[str, Any]:
        """Przyjmuje pojedynczą paletę w transferze na podstawie zeskanowanego kodu palety i lokalizacji."""
        transfer = self.repository.get_transfer_by_id(transfer_id)
        if not transfer:
            raise ValueError("Nie znaleziono zlecenia transferu.")

        code_upper = str(pallet_code or '').strip().upper()
        target_loc = str(target_location or transfer.destination_warehouse).strip().upper()

        matched_item = None
        for item in transfer.items:
            item_code = str(item.nr_palety or '').strip().upper()
            item_id_str = str(item.pallet_id or '')
            if code_upper and (code_upper in item_code or item_code in code_upper or code_upper == item_id_str):
                matched_item = item
                break

        if not matched_item:
            raise ValueError(f"Paleta '{pallet_code}' nie występuje w tym zleceniu transferu.")

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            if matched_item.pallet_id:
                cursor.execute(
                    "UPDATE magazyn_surowce SET lokalizacja = %s WHERE id = %s",
                    (target_loc, matched_item.pallet_id)
                )
            elif matched_item.nr_palety:
                cursor.execute(
                    "UPDATE magazyn_surowce SET lokalizacja = %s WHERE nr_palety = %s",
                    (target_loc, matched_item.nr_palety)
                )

            cursor.execute(
                "UPDATE osip_transfer_items SET status = 'RECEIVED' WHERE id = %s",
                (matched_item.id,)
            )
            conn.commit()
        finally:
            cursor.close()
            conn.close()

        # Check if all items in transfer are now received
        updated_transfer = self.repository.get_transfer_by_id(transfer_id)
        all_received = all(it.status == 'RECEIVED' for it in updated_transfer.items)
        if all_received:
            self.repository.update_transfer_status(transfer_id, "COMPLETED", user_login)
            updated_transfer = self.repository.get_transfer_by_id(transfer_id)

        received_count = sum(1 for it in updated_transfer.items if it.status == 'RECEIVED')
        total_count = len(updated_transfer.items)

        return {
            "success": True,
            "message": f"Przyjęto paletę {matched_item.nr_palety} do lokalizacji {target_loc}",
            "item_id": matched_item.id,
            "nr_palety": matched_item.nr_palety,
            "location": target_loc,
            "transfer_status": updated_transfer.status,
            "received_count": received_count,
            "total_count": total_count,
            "completed": all_received
        }

    def cancel_transfer(self, transfer_id: int, user_login: str) -> OsipTransferModel:
        """Anuluje transfer i przywraca palety do magazynu źródłowego."""
        transfer = self.repository.get_transfer_by_id(transfer_id)
        if not transfer:
            raise ValueError("Nie znaleziono zlecenia transferu.")

        if transfer.status == "COMPLETED":
            raise ValueError("Zakończone zlecenie transferu nie może zostać anulowane.")

        if transfer.status == "IN_TRANSIT":
            # Zwrot palet z tranzytu do źródła
            conn = get_db_connection()
            cursor = conn.cursor()
            try:
                for item in transfer.items:
                    if item.pallet_id:
                        cursor.execute(
                            "UPDATE magazyn_surowce SET lokalizacja = %s WHERE id = %s",
                            (transfer.source_warehouse, item.pallet_id)
                        )
                conn.commit()
            finally:
                cursor.close()
                conn.close()

        self.repository.update_transfer_status(transfer_id, "CANCELLED", user_login)
        return self.repository.get_transfer_by_id(transfer_id)

    @staticmethod
    def auto_receive_pallet_by_code(pallet_code: str, target_location: str, user_login: str) -> None:
        """Automatycznie oznacza pozycję transferu jako RECEIVED, jeśli paleta jest przenoszona w Głównym Skanerze."""
        if not pallet_code:
            return
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT ti.id, ti.transfer_id, ti.pallet_id, ti.nr_palety, t.destination_warehouse, t.status as transfer_status
                FROM osip_transfer_items ti
                JOIN osip_transfers t ON ti.transfer_id = t.id
                WHERE (ti.nr_palety = %s OR (ti.pallet_id = %s AND %s != '0')) 
                  AND t.status = 'IN_TRANSIT' AND ti.status != 'RECEIVED'
                LIMIT 1
            """, (pallet_code, pallet_code if str(pallet_code).isdigit() else 0, pallet_code if str(pallet_code).isdigit() else '0'))
            item = cursor.fetchone()
            if not item:
                return

            transfer_id = item['transfer_id']

            cursor.execute("""
                UPDATE osip_transfer_items
                SET status = 'RECEIVED'
                WHERE id = %s
            """, (item['id'],))

            cursor.execute("""
                SELECT COUNT(*) as unreceived
                FROM osip_transfer_items
                WHERE transfer_id = %s AND status != 'RECEIVED'
            """, (transfer_id,))
            row = cursor.fetchone()
            
            if row and row['unreceived'] == 0:
                cursor.execute("""
                    UPDATE osip_transfers
                    SET status = 'COMPLETED', completed_by = %s, completed_at = NOW()
                    WHERE id = %s
                """, (user_login, transfer_id))

            conn.commit()
        finally:
            cursor.close()
            conn.close()

    def get_transfers_list(self, user_role: str, user_subrole: Optional[str] = None) -> List[OsipTransferModel]:
        """Pobiera listę transferów z filtrowaniem wg rola/oddział."""
        all_transfers = self.repository.get_all_transfers()
        role_lower = (user_role or '').lower()
        if role_lower in ("admin", "masteradmin", "zarzad", "boss", "planista", "lider", "master"):
            return all_transfers

        # Magazynier widzi zlecenia dedykowane jego oddziałowi
        user_branch = (user_subrole or "AGRO").upper()
        filtered = []
        for t in all_transfers:
            source_branch = "OSIP" if (t.source_warehouse or '').upper() == "OSIP" else "AGRO"
            dest_branch = "OSIP" if (t.destination_warehouse or '').upper() == "OSIP" else "AGRO"

            if t.status == "PLANNED" and user_branch == source_branch:
                filtered.append(t)
            elif t.status == "IN_TRANSIT" and user_branch == dest_branch:
                filtered.append(t)
            elif t.status in ("COMPLETED", "CANCELLED") and (user_branch in (source_branch, dest_branch)):
                filtered.append(t)

        return filtered
