"""
Serwis zarządzenia cyklem życia transferów wewnętrznych OSIP <-> Centrala.
"""
from typing import List, Dict, Any, Optional
from app.repositories.osip_transfer_repository import OsipTransferRepository
from app.models.osip_transfer_model import OsipTransferModel
from app.core.database import get_db_connection
from app.services.warehouse_history.movement_recorder import MovementRecorder


class OsipTransferService:
    IN_TRANSIT_LOCATION = "W_TRANZYCIE_OSIP"

    def __init__(self, repository: Optional[OsipTransferRepository] = None):
        self.repository = repository or OsipTransferRepository()

    @staticmethod
    def _extract_items(transfer: Any) -> List[Any]:
        """Bezpiecznie wyciąga listę pozycji ze zlecenia transferu (model lub słownik)."""
        if not transfer:
            return []
        if isinstance(transfer, dict):
            return transfer.get('items', [])
        items_attr = getattr(transfer, 'items', None)
        if callable(items_attr):
            return transfer.get('items', []) if hasattr(transfer, 'get') else []
        return items_attr or []

    def get_transfer_by_id(self, transfer_id: Any) -> Optional[OsipTransferModel]:
        """Pobiera zlecenie transferu po ID lub po kodzie (transfer_code)."""
        return self.repository.get_transfer_by_id(transfer_id)

    def create_transfer_order(self, source_warehouse: str, destination_warehouse: str, items: List[Dict[str, Any]], created_by: str, notes: Optional[str] = None) -> OsipTransferModel:
        """Tworzy zaplanowane zlecenie transferu z pozycjami."""
        if not items:
            raise ValueError("Zlecenie transferu musi zawierać co najmniej jedną pozycję.")

        transfer = self.repository.create_transfer(source_warehouse, destination_warehouse, created_by, notes)
        self.repository.add_transfer_items(transfer.id, items)
        return self.repository.get_transfer_by_id(transfer.id)

    def dispatch_transfer(self, transfer_id: Any, loaded_pallets: List[Dict[str, Any]], user_login: str) -> OsipTransferModel:
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
                {'pallet_id': getattr(item, 'pallet_id', None) or (item.get('pallet_id') if isinstance(item, dict) else None),
                 'nr_palety': getattr(item, 'nr_palety', '') or (item.get('nr_palety') if isinstance(item, dict) else ''),
                 'loaded_qty': getattr(item, 'requested_qty', 0.0) or (item.get('requested_qty', 0.0) if isinstance(item, dict) else 0.0),
                 'id': getattr(item, 'id', None) or (item.get('id') if isinstance(item, dict) else None)} 
                for item in self._extract_items(transfer)
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

                item_id = item.get("id")
                history_saved = MovementRecorder.record_movement(
                    paleta_id=pallet_id,
                    linia="OSIP",
                    typ_palety="surowiec",
                    akcja="TRANSFER",
                    lokalizacja_zrodlowa=transfer.source_warehouse,
                    lokalizacja_docelowa=self.IN_TRANSIT_LOCATION,
                    komentarz=f"Załadunek transferu {transfer.transfer_code or transfer.id}: {transfer.source_warehouse} -> {self.IN_TRANSIT_LOCATION}",
                    user_login=user_login,
                    nr_palety=nr_palety,
                    cursor=cursor,
                    connection=conn,
                    operation_id=f"osip-transfer:{transfer.id}:item:{item_id or nr_palety or pallet_id}:dispatch",
                )
                if not history_saved:
                    raise RuntimeError("Nie udało się zapisać historii wysyłki transferu OSIP")

            conn.commit()
        finally:
            cursor.close()
            conn.close()

        self.repository.update_items_loaded(transfer.id, loaded_pallets)
        self.repository.update_transfer_status(transfer.id, "IN_TRANSIT", user_login)
        return self.repository.get_transfer_by_id(transfer.id)

    def receive_transfer(self, transfer_id: Any, target_locations: Dict[Any, str], user_login: str) -> OsipTransferModel:
        """Przyjmuje transfer w magazynie docelowym i ustawia docelowe lokalizacje palet (np. OS01, OSIP lub MS01)."""
        transfer = self.repository.get_transfer_by_id(transfer_id)
        if not transfer:
            raise ValueError("Nie znaleziono zlecenia transferu.")

        if transfer.status not in ("PLANNED", "IN_TRANSIT"):
            raise ValueError(f"Nie można przyjąć zlecenia w statusie {transfer.status}.")

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            for item in self._extract_items(transfer):
                # Find matching target location by item.id, item.pallet_id, or item.nr_palety
                item_id = getattr(item, 'id', None) or (item.get('id') if isinstance(item, dict) else None)
                pallet_id = getattr(item, 'pallet_id', None) or (item.get('pallet_id') if isinstance(item, dict) else None)
                nr_palety = getattr(item, 'nr_palety', '') or (item.get('nr_palety') if isinstance(item, dict) else '')

                new_loc = target_locations.get(item_id) or target_locations.get(pallet_id) or target_locations.get(nr_palety)
                if not new_loc:
                    new_loc = target_locations.get('default', transfer.destination_warehouse)
                
                new_loc = str(new_loc or transfer.destination_warehouse).strip().upper()

                if pallet_id:
                    cursor.execute(
                        "UPDATE magazyn_surowce SET lokalizacja = %s WHERE id = %s",
                        (new_loc, pallet_id)
                    )
                elif nr_palety:
                    cursor.execute(
                        "UPDATE magazyn_surowce SET lokalizacja = %s WHERE nr_palety = %s",
                        (new_loc, nr_palety)
                    )
                
                if item_id:
                    cursor.execute(
                        "UPDATE osip_transfer_items SET status = 'RECEIVED' WHERE id = %s",
                        (item_id,)
                    )

                history_saved = MovementRecorder.record_movement(
                    paleta_id=pallet_id,
                    linia="OSIP",
                    typ_palety="surowiec",
                    akcja="PRZYJECIE",
                    lokalizacja_zrodlowa=self.IN_TRANSIT_LOCATION,
                    lokalizacja_docelowa=new_loc,
                    komentarz=f"Przyjęcie transferu {transfer.transfer_code or transfer.id}: {self.IN_TRANSIT_LOCATION} -> {new_loc}",
                    user_login=user_login,
                    nr_palety=nr_palety,
                    cursor=cursor,
                    connection=conn,
                    operation_id=f"osip-transfer:{transfer.id}:item:{item_id or nr_palety or pallet_id}:receive",
                )
                if not history_saved:
                    raise RuntimeError("Nie udało się zapisać historii przyjęcia transferu OSIP")

            conn.commit()
        finally:
            cursor.close()
            conn.close()

        self.repository.update_transfer_status(transfer_id, "COMPLETED", user_login)
        return self.repository.get_transfer_by_id(transfer_id)

    def receive_single_item(self, transfer_id: Any, pallet_code: str, target_location: str, user_login: str) -> Dict[str, Any]:
        """Przyjmuje pojedynczą paletę w transferze na podstawie zeskanowanego kodu palety i lokalizacji."""
        transfer = self.repository.get_transfer_by_id(transfer_id)
        if not transfer:
            raise ValueError("Nie znaleziono zlecenia transferu.")

        if transfer.status not in ("PLANNED", "IN_TRANSIT"):
            raise ValueError(f"Nie można przyjąć zlecenia w statusie {transfer.status}.")
        code_upper = str(pallet_code or '').strip().upper()
        if not code_upper:
            raise ValueError("Podaj pełny numer palety.")
        target_loc = str(target_location or transfer.destination_warehouse).strip().upper()
        matches = []
        for item in self._extract_items(transfer):
            item_code = str(getattr(item, 'nr_palety', None) or (item.get('nr_palety') if isinstance(item, dict) else '')).strip().upper()
            item_id_str = str(getattr(item, 'pallet_id', None) or (item.get('pallet_id') if isinstance(item, dict) else ''))
            if code_upper == item_code or (code_upper.isdigit() and code_upper == item_id_str):
                matches.append(item)
        if len(matches) != 1:
            raise ValueError(f"Paleta '{pallet_code}' nie identyfikuje jednej pozycji w tym zleceniu transferu.")
        matched_item = matches[0]
        matched_status = getattr(matched_item, 'status', None) or (matched_item.get('status') if isinstance(matched_item, dict) else '')
        if matched_status == 'RECEIVED':
            raise ValueError("Paleta została już przyjęta; ponowny skan nie może zmienić jej lokalizacji.")

        matched_pallet_id = getattr(matched_item, 'pallet_id', None) or (matched_item.get('pallet_id') if isinstance(matched_item, dict) else None)
        matched_nr_palety = getattr(matched_item, 'nr_palety', '') or (matched_item.get('nr_palety') if isinstance(matched_item, dict) else '')
        matched_item_id = getattr(matched_item, 'id', None) or (matched_item.get('id') if isinstance(matched_item, dict) else None)

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            if matched_pallet_id:
                cursor.execute(
                    "UPDATE magazyn_surowce SET lokalizacja = %s WHERE id = %s",
                    (target_loc, matched_pallet_id)
                )
            elif matched_nr_palety:
                cursor.execute(
                    "UPDATE magazyn_surowce SET lokalizacja = %s WHERE nr_palety = %s",
                    (target_loc, matched_nr_palety)
                )

            if matched_item_id:
                cursor.execute(
                    "UPDATE osip_transfer_items SET status = 'RECEIVED' WHERE id = %s",
                    (matched_item_id,)
                )

            src_history = transfer.source_warehouse if transfer.source_warehouse else 'CENTRALA'
            history_saved = MovementRecorder.record_movement(
                paleta_id=matched_pallet_id,
                linia="OSIP",
                typ_palety="surowiec",
                akcja="PRZYJECIE",
                lokalizacja_zrodlowa=src_history,
                lokalizacja_docelowa=target_loc,
                komentarz=f"Przyjęcie z transferu {transfer.transfer_code or transfer.id}: {src_history} -> {target_loc}",
                user_login=user_login,
                nr_palety=matched_nr_palety,
                cursor=cursor,
                connection=conn,
                operation_id=f"osip-transfer:{transfer.id}:item:{matched_item_id or matched_nr_palety or matched_pallet_id}:receive",
            )
            if not history_saved:
                raise RuntimeError("Nie udało się zapisać historii przyjęcia palety OSIP")

            conn.commit()
        finally:
            cursor.close()
            conn.close()

        # Check if all items in transfer are now received
        updated_transfer = self.repository.get_transfer_by_id(transfer.id)
        updated_items = self._extract_items(updated_transfer)
        all_received = bool(updated_items) and all(getattr(it, 'status', None) == 'RECEIVED' or (it.get('status') if isinstance(it, dict) else None) == 'RECEIVED' for it in updated_items)
        if all_received:
            self.repository.update_transfer_status(transfer.id, "COMPLETED", user_login)
            updated_transfer = self.repository.get_transfer_by_id(transfer.id)
            updated_items = self._extract_items(updated_transfer)

        received_count = sum(1 for it in updated_items if getattr(it, 'status', None) == 'RECEIVED' or (it.get('status') if isinstance(it, dict) else None) == 'RECEIVED')
        total_count = len(updated_items)

        return {
            "success": True,
            "message": f"Przyjęto paletę {matched_nr_palety} do lokalizacji {target_loc}",
            "item_id": matched_item_id,
            "nr_palety": matched_nr_palety,
            "location": target_loc,
            "transfer_status": updated_transfer.status,
            "received_count": received_count,
            "total_count": total_count,
            "completed": all_received
        }

    def cancel_transfer(self, transfer_id: Any, user_login: str) -> OsipTransferModel:
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
                for item in self._extract_items(transfer):
                    item_status = getattr(item, 'status', None) or (item.get('status') if isinstance(item, dict) else '')
                    if item_status == 'RECEIVED':
                        continue
                    pallet_id = getattr(item, 'pallet_id', None) or (item.get('pallet_id') if isinstance(item, dict) else None)
                    if pallet_id:
                        cursor.execute(
                            "UPDATE magazyn_surowce SET lokalizacja = %s WHERE id = %s",
                            (transfer.source_warehouse, pallet_id)
                        )
                conn.commit()
            finally:
                cursor.close()
                conn.close()

        self.repository.update_transfer_status(transfer.id, "CANCELLED", user_login)
        return self.repository.get_transfer_by_id(transfer.id)

    @staticmethod
    def auto_receive_pallet_by_code(pallet_code: str, target_location: str, user_login: str) -> None:
        """Automatycznie oznacza pozycję transferu jako RECEIVED, jeśli paleta jest przenoszona w Głównym Skanerze."""
        if not pallet_code:
            return
            
        loc_upper = str(target_location or '').strip().upper()
        if loc_upper == "W_TRANZYCIE_OSIP":
            return

        code_str = str(pallet_code).strip().upper()
        if not code_str:
            return
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            query = """
                SELECT ti.id, ti.transfer_id, ti.pallet_id, ti.nr_palety, t.destination_warehouse, t.status as transfer_status
                FROM osip_transfer_items ti
                JOIN osip_transfers t ON ti.transfer_id = t.id
                WHERE (
                    UPPER(TRIM(ti.nr_palety)) = %s
                    OR (ti.pallet_id = %s AND %s != 0)
                )
                AND t.status IN ('PLANNED', 'IN_TRANSIT')
                AND ti.status != 'RECEIVED'
            """
            pallet_id_param = int(code_str) if code_str.isdigit() else 0
            cursor.execute(query, (code_str, pallet_id_param, pallet_id_param))
            items = cursor.fetchall()
            if len(items) > 1:
                raise ValueError("Paleta występuje w wielu aktywnych transferach OSIP")

            if not items:
                return

            cur_up = conn.cursor()
            for item in items:
                transfer_id = item['transfer_id']

                cur_up.execute("""
                    UPDATE osip_transfer_items
                    SET status = 'RECEIVED'
                    WHERE id = %s
                """, (item['id'],))

                cur_up.execute("""
                    SELECT COUNT(*) as unreceived
                    FROM osip_transfer_items
                    WHERE transfer_id = %s AND status != 'RECEIVED'
                """, (transfer_id,))
                row = cur_up.fetchone()
                
                unreceived_count = row[0] if isinstance(row, tuple) else (row.get('unreceived') if isinstance(row, dict) else 0)
                if unreceived_count == 0:
                    cur_up.execute("""
                        UPDATE osip_transfers
                        SET status = 'COMPLETED', completed_by = %s, completed_at = NOW()
                        WHERE id = %s
                    """, (user_login, transfer_id))

            conn.commit()
            cur_up.close()
        except Exception as ex:
            import logging
            logging.error(f"[OSIP_AUTO_RECEIVE_ERROR] {ex}")
        finally:
            cursor.close()
            conn.close()

    def get_transfers_list(self, user_role: str, user_subrole: Optional[str] = None, scope: Optional[str] = None) -> List[OsipTransferModel]:
        """Pobiera listę transferów z filtrowaniem wg rola/oddział oraz zakresu (scope)."""
        all_transfers = self.repository.get_all_transfers()
        
        # Filtrowanie kierunku w zależności od zadanego widoku (OSIP vs Centrala / Wszystkie Magazyny)
        # 'centrala': widok Centrala/Wszystkie Magazyny -> tylko transfery Z OSIP (source_warehouse == 'OSIP')
        # 'osip': widok Magazyn OSIP -> tylko transfery Z CENTRALI (source_warehouse != 'OSIP')
        if scope:
            scope_lower = str(scope).lower().strip()
            if scope_lower in ('centrala', 'all_warehouses', 'from_osip', 'to_centrala'):
                all_transfers = [
                    t for t in all_transfers 
                    if (t.source_warehouse or '').upper() == 'OSIP'
                ]
            elif scope_lower in ('osip', 'from_centrala', 'to_osip'):
                all_transfers = [
                    t for t in all_transfers 
                    if (t.source_warehouse or '').upper() != 'OSIP'
                ]

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
