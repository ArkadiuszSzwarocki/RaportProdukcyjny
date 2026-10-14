"""
Serwis zarządzenia cyklem życia transferów wewnętrznych OSIP <-> Centrala.
"""
import math
from typing import List, Dict, Any, Optional
from app.repositories.osip_transfer_repository import OsipTransferRepository
from app.models.osip_transfer_model import OsipTransferModel
from app.core.database import get_db_connection
from app.utils.location_validator import is_osip_location
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

    @classmethod
    def pallet_metadata(cls, transfers):
        """Read pallet dates by physical code, never by a warehouse-local id."""
        grouped = {}
        for transfer in transfers:
            for item in cls._extract_items(transfer):
                code = cls._value(item, 'nr_palety')
                if code:
                    table = cls._stock_spec(item)[0]
                    grouped.setdefault(table, set()).add(code)
        metadata = {}
        if not grouped:
            return metadata
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            for table, codes in grouped.items():
                marks = ','.join(['%s'] * len(codes))
                cursor.execute(f'SELECT nr_palety,nr_partii,data_produkcji,data_przydatnosci '
                               f'FROM {table} WHERE nr_palety IN ({marks})', tuple(codes))
                rows = {}
                for row in cursor.fetchall():
                    rows.setdefault(row['nr_palety'], []).append(row)
                for code, matches in rows.items():
                    if len(matches) == 1:
                        metadata[(table, code)] = matches[0]
            return metadata
        finally:
            conn.close()

    @staticmethod
    def _value(item, key, default=None):
        return item.get(key, default) if isinstance(item, dict) else getattr(item, key, default)

    @classmethod
    def _match_item(cls, transfer, code):
        code = str(code or '').strip().upper()
        if not code:
            raise ValueError("Podaj pełny numer palety.")
        matches = [item for item in cls._extract_items(transfer) if
                   code == str(cls._value(item, 'nr_palety') or '').strip().upper() or
                   (code.isdigit() and code == str(cls._value(item, 'pallet_id') or ''))]
        if len(matches) != 1:
            raise ValueError(f"Paleta '{code}' nie identyfikuje jednej pozycji w tym zleceniu transferu.")
        if cls._value(matches[0], 'status') == 'RECEIVED':
            raise ValueError("Paleta została już przyjęta; ponowny skan nie może zmienić jej lokalizacji.")
        return matches[0]

    @classmethod
    def _stock_spec(cls, item):
        kind = str(cls._value(item, 'item_type', 'raw') or 'raw').strip().lower()
        if kind in ('raw', 'surowiec'):
            return 'magazyn_surowce', 'stan_magazynowy', 'surowiec'
        if kind in ('fg', 'wyrób gotowy', 'wyrob gotowy', 'wyrob_gotowy', 'magazyn'):
            return 'magazyn_palety', 'waga_netto', 'wyrob_gotowy'
        if kind in ('packaging', 'opakowanie'):
            return 'magazyn_opakowania', 'stan_magazynowy', 'opakowanie'
        if kind in ('dodatek', 'additive'):
            return 'magazyn_dodatki', 'stan_magazynowy', 'dodatek'
        raise ValueError(f"Nieobsługiwany typ palety: {kind}")

    @classmethod
    def _move_stock(cls, cursor, conn, transfer, item, new_location, login, action, loaded_qty=None):
        from app.utils.location_validator import validate_warehouse_location
        valid, error = validate_warehouse_location(new_location, allow_empty=False)
        if not valid:
            raise ValueError(error)
        if action == 'PRZYJECIE' and new_location == cls.IN_TRANSIT_LOCATION:
            raise ValueError('Tranzyt nie jest lokalizacją przyjęcia')
        table, quantity_column, pallet_type = cls._stock_spec(item)
        pallet_id, number = cls._value(item, 'pallet_id'), cls._value(item, 'nr_palety')
        if not pallet_id and not number:
            raise ValueError("Pozycja transferu nie wskazuje fizycznej palety")
        predicate, params = [], []
        if pallet_id:
            predicate.append('id = %s')
            params.append(pallet_id)
        if number:
            predicate.append('UPPER(TRIM(nr_palety)) = %s')
            params.append(str(number).strip().upper())
        cursor.execute(f"SELECT id,nr_palety,lokalizacja,is_blocked,{quantity_column} AS quantity "
                       f"FROM {table} WHERE {' AND '.join(predicate)} FOR UPDATE", tuple(params))
        rows = cursor.fetchall()
        if len(rows) != 1:
            raise ValueError("Nie znaleziono jednoznacznej palety w magazynie")
        row = rows[0]
        quantity = float(row['quantity'] or 0)
        if not math.isfinite(quantity) or quantity <= 0:
            raise ValueError("Paleta jest zużyta lub ma nieprawidłowy stan")
        if action != 'TRANSFER_CANCEL':
            from app.services.magazyn_dostawy.commands.pallet_lock_manager import PalletLockManager
            if PalletLockManager.has_quality_or_manual_block(cursor, row['nr_palety']):
                raise ValueError('Paleta posiada blokadę LAB lub ręczną')
        if action in ('PRZYJECIE', 'TRANSFER_CANCEL'):
            from app.utils.location_validator import check_rack_location_availability
            available, error = check_rack_location_availability(new_location, row['nr_palety'], cursor=cursor)
            if not available:
                raise ValueError(error)
        if action == 'PRZYJECIE':
            destination_osip = str(transfer.destination_warehouse or '').upper().startswith('OS')
            if destination_osip != is_osip_location(new_location):
                raise ValueError('Lokalizacja nie należy do magazynu docelowego transferu')
        if action == 'TRANSFER':
            source_osip = str(transfer.source_warehouse or '').upper().startswith('OS')
            if source_osip != is_osip_location(row.get('lokalizacja')):
                raise ValueError('Paleta nie znajduje się w magazynie źródłowym transferu')
            if row.get('is_blocked'):
                raise ValueError("Paleta jest zablokowana; nie można jej załadować")
            if str(row.get('lokalizacja') or '').upper() == cls.IN_TRANSIT_LOCATION:
                raise ValueError("Paleta jest już w tranzycie")
            qty = float(loaded_qty)
            if not math.isfinite(qty) or qty <= 0 or abs(qty - quantity) > 0.001:
                raise ValueError("Załadunek musi obejmować pełny stan palety. Najpierw podziel paletę dla częściowego transferu.")
        if action == 'TRANSFER_CANCEL' and row.get('lokalizacja') != cls.IN_TRANSIT_LOCATION:
            raise ValueError("Paleta nie jest w tranzycie; nie można cofnąć jej lokalizacji")
        cursor.execute(f"UPDATE {table} SET lokalizacja=%s WHERE id=%s", (new_location, row['id']))
        if not MovementRecorder.record_movement(
                paleta_id=row['id'], linia='OSIP', typ_palety=pallet_type, akcja=action,
                lokalizacja_zrodlowa=row.get('lokalizacja'), lokalizacja_docelowa=new_location,
                komentarz=f"Transfer {transfer.transfer_code or transfer.id}", user_login=login,
                nr_palety=row['nr_palety'], cursor=cursor, connection=conn,
                operation_id=f"osip-transfer:{transfer.id}:item:{cls._value(item, 'id')}:{action.lower()}"):
            raise RuntimeError("Nie udało się zapisać historii transferu OSIP")
        return row

    def _locked_transfer(self, conn, transfer_id, allowed_statuses):
        transfer = self.repository.get_transfer_by_id(transfer_id, external_conn=conn, for_update=True)
        if not transfer:
            raise ValueError("Nie znaleziono zlecenia transferu.")
        if transfer.status not in allowed_statuses:
            raise ValueError(f"Nie można zmienić zlecenia w statusie {transfer.status}.")
        if not self._extract_items(transfer):
            raise ValueError("Zlecenie nie zawiera pozycji")
        return transfer

    def create_transfer_order(self, source_warehouse: str, destination_warehouse: str, items: List[Dict[str, Any]], created_by: str, notes: Optional[str] = None) -> OsipTransferModel:
        if not items:
            raise ValueError("Zlecenie transferu musi zawierać co najmniej jedną pozycję.")
        for item in items:
            quantity = float(item.get('requested_qty', 0))
            if not math.isfinite(quantity) or quantity <= 0:
                raise ValueError("Podaj dodatnią ilość transferu")
            self._stock_spec(item)
        if not source_warehouse or not destination_warehouse or source_warehouse.upper() == destination_warehouse.upper():
            raise ValueError("Podaj różne magazyny źródłowy i docelowy")
        conn = get_db_connection()
        try:
            transfer = self.repository.create_transfer(source_warehouse, destination_warehouse, created_by, notes, external_conn=conn)
            self.repository.add_transfer_items(transfer.id, items, external_conn=conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return self.repository.get_transfer_by_id(transfer.id)

    def dispatch_transfer(self, transfer_id: Any, loaded_pallets: List[Dict[str, Any]], user_login: str) -> OsipTransferModel:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            transfer = self._locked_transfer(conn, transfer_id, ('PLANNED',))
            planned = {str(self._value(item, 'id')): item for item in self._extract_items(transfer)}
            selected = loaded_pallets or [dict(
                id=self._value(item, 'id'), pallet_id=self._value(item, 'pallet_id'),
                nr_palety=self._value(item, 'nr_palety'), loaded_qty=self._value(item, 'requested_qty'))
                for item in planned.values()]
            if len(selected) != len(planned) or {str(item.get('id')) for item in selected} != set(planned):
                raise ValueError("Załaduj wszystkie pozycje tego transferu; nie dodawaj obcych pozycji")
            resolved, used_pallets = [], set()
            for item in selected:
                plan_item = planned[str(item['id'])]
                data = dict(item, item_type=self._value(plan_item, 'item_type', 'raw'))
                # A planned physical identity cannot be replaced by a client payload.
                for key in ('pallet_id', 'nr_palety'):
                    expected = self._value(plan_item, key)
                    if expected and data.get(key) and str(expected).upper() != str(data[key]).upper():
                        raise ValueError("Załadowana paleta nie odpowiada pozycji zlecenia")
                    if expected:
                        data[key] = expected
                identity = (self._stock_spec(data)[0], str(data.get('nr_palety') or data.get('pallet_id')))
                if identity in used_pallets:
                    raise ValueError("Nie można załadować tej samej palety dwa razy")
                used_pallets.add(identity)
                row = self._move_stock(cursor, conn, transfer, data, self.IN_TRANSIT_LOCATION,
                                       user_login, 'TRANSFER', loaded_qty=data.get('loaded_qty'))
                resolved.append(dict(data, pallet_id=row['id'], nr_palety=row['nr_palety']))
            self.repository.update_items_loaded(transfer.id, resolved, external_conn=conn)
            self.repository.update_transfer_status(transfer.id, 'IN_TRANSIT', user_login, external_conn=conn)
            from app.services.warehouse_order_fulfillment import WarehouseOrderFulfillment
            target_line = 'OSIP' if str(transfer.destination_warehouse).upper() == 'OSIP' else 'AGRO'
            WarehouseOrderFulfillment.sync_transfer(cursor,'OSIP:'+str(transfer.id),resolved,target_line,user_login)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()
        return self.repository.get_transfer_by_id(transfer.id)

    def _receive_item(self, cursor, conn, transfer, item, target_location, login):
        if self._value(item, 'status') == 'RECEIVED':
            return
        self._move_stock(cursor, conn, transfer, item, target_location, login, 'PRZYJECIE')
        cursor.execute("UPDATE osip_transfer_items SET status='RECEIVED' WHERE id=%s AND transfer_id=%s",
                       (self._value(item, 'id'), transfer.id))

    def begin_receiving(self, transfer_id, user_login):
        """Record the receiver's explicit start before any pallet can be accepted."""
        conn = get_db_connection()
        try:
            transfer = self._locked_transfer(conn, transfer_id, ('IN_TRANSIT', 'RECEIVING'))
            if transfer.status == 'IN_TRANSIT':
                self.repository.update_transfer_status(transfer.id, 'RECEIVING', user_login, external_conn=conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return self.repository.get_transfer_by_id(transfer.id)

    @staticmethod
    def require_receiving(cursor, pallet_code, target_location=None):
        """Protect generic moves as well as the dedicated receiving API."""
        cursor.execute("SELECT t.id,t.transfer_code,t.status,t.destination_warehouse FROM osip_transfers t "
                       "JOIN osip_transfer_items ti ON ti.transfer_id=t.id "
                       "WHERE UPPER(TRIM(ti.nr_palety))=%s AND ti.status!='RECEIVED' "
                       "AND t.status IN ('PLANNED','IN_TRANSIT','RECEIVING') FOR UPDATE",
                       (str(pallet_code or '').strip().upper(),))
        transfers = cursor.fetchall()
        if len(transfers) > 1:
            raise ValueError('Paleta należy do kilku aktywnych transferów; wyjaśnij dokumenty przed odbiorem.')
        if transfers and transfers[0]['status'] != 'RECEIVING':
            raise ValueError(f"Transfer {transfers[0]['transfer_code']}: najpierw kliknij Odbierz / Przyjmij na stronie transferów.")
        if transfers and target_location:
            from app.utils.location_validator import is_osip_location
            if (str(transfers[0]['destination_warehouse']).upper() == 'OSIP') != is_osip_location(target_location):
                raise ValueError('Odstaw paletę do magazynu docelowego tego transferu.')
        return bool(transfers)

    def receive_transfer(self, transfer_id: Any, target_locations: Dict[Any, str], user_login: str) -> OsipTransferModel:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            transfer = self._locked_transfer(conn, transfer_id, ('RECEIVING',))
            for item in self._extract_items(transfer):
                location = None
                for key in ('id', 'pallet_id', 'nr_palety'):
                    value = self._value(item, key)
                    location = target_locations.get(value) or target_locations.get(str(value))
                    if location:
                        break
                location = str(location or target_locations.get('default') or transfer.destination_warehouse).strip().upper()
                self._receive_item(cursor, conn, transfer, item, location, user_login)
            self.repository.update_transfer_status(transfer.id, 'COMPLETED', user_login, external_conn=conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()
        return self.repository.get_transfer_by_id(transfer.id)

    def receive_single_item(self, transfer_id: Any, pallet_code: str, target_location: str, user_login: str) -> Dict[str, Any]:
        # Early validation gives a clear response without opening a write transaction.
        transfer = self.repository.get_transfer_by_id(transfer_id)
        if not transfer or transfer.status != 'RECEIVING':
            raise ValueError("Najpierw kliknij Odbierz / Przyjmij na stronie transferów.")
        self._match_item(transfer, pallet_code)
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            transfer = self._locked_transfer(conn, transfer_id, ('RECEIVING',))
            item = self._match_item(transfer, pallet_code)
            location = str(target_location or transfer.destination_warehouse).strip().upper()
            self._receive_item(cursor, conn, transfer, item, location, user_login)
            cursor.execute("SELECT COUNT(*) AS remaining FROM osip_transfer_items WHERE transfer_id=%s AND status!='RECEIVED'", (transfer.id,))
            completed = cursor.fetchone()['remaining'] == 0
            if completed:
                self.repository.update_transfer_status(transfer.id, 'COMPLETED', user_login, external_conn=conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()
        updated = self.repository.get_transfer_by_id(transfer.id)
        items = self._extract_items(updated)
        return dict(success=True, message=f"Przyjęto paletę {self._value(item, 'nr_palety')} do lokalizacji {location}",
                    item_id=self._value(item, 'id'), nr_palety=self._value(item, 'nr_palety'), location=location,
                    transfer_status=updated.status, completed=completed, total_count=len(items),
                    received_count=sum(self._value(value, 'status') == 'RECEIVED' for value in items))

    def cancel_transfer(self, transfer_id: Any, user_login: str) -> OsipTransferModel:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            transfer = self._locked_transfer(conn, transfer_id, ('PLANNED', 'IN_TRANSIT', 'RECEIVING', 'CANCELLED'))
            if transfer.status == 'CANCELLED':
                return transfer
            for item in self._extract_items(transfer):
                if self._value(item, 'status') == 'RECEIVED':
                    continue
                if transfer.status in ('IN_TRANSIT', 'RECEIVING') and self._value(item, 'status') == 'LOADED':
                    self._move_stock(cursor, conn, transfer, item, transfer.source_warehouse, user_login, 'TRANSFER_CANCEL')
                cursor.execute("UPDATE osip_transfer_items SET status='CANCELLED' WHERE id=%s AND transfer_id=%s",
                               (self._value(item, 'id'), transfer.id))
            self.repository.update_transfer_status(transfer.id, 'CANCELLED', user_login, external_conn=conn)
            from app.services.warehouse_order_fulfillment import WarehouseOrderFulfillment
            received = [dict(id=self._value(item,'id'),nr_palety=self._value(item,'nr_palety')) for item in
                        self._extract_items(transfer) if self._value(item,'status') == 'RECEIVED']
            target_line = 'OSIP' if str(transfer.destination_warehouse).upper() == 'OSIP' else 'AGRO'
            WarehouseOrderFulfillment.sync_transfer(cursor,'OSIP:'+str(transfer.id),received,target_line,user_login)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()
        return self.repository.get_transfer_by_id(transfer.id)

    @staticmethod
    def auto_receive_pallet_by_code(pallet_code: str, target_location: str, user_login: str, external_conn=None):
        """Resolve receipt in the caller's transaction when stock has been moved."""
        code = str(pallet_code or '').strip().upper()
        location = str(target_location or '').strip().upper()
        if not code or not location or location == OsipTransferService.IN_TRANSIT_LOCATION:
            return False, 'Brak przyjęcia do potwierdzenia'
        conn = external_conn or get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            numeric_id = int(code) if code.isdigit() else 0
            cursor.execute("""
                SELECT ti.id, ti.transfer_id FROM osip_transfer_items ti
                JOIN osip_transfers t ON t.id=ti.transfer_id
                WHERE (UPPER(TRIM(ti.nr_palety))=%s OR (ti.pallet_id=%s AND %s!=0))
                AND t.status IN ('PLANNED','IN_TRANSIT','RECEIVING') AND ti.status!='RECEIVED'
            """, (code, numeric_id, numeric_id))
            candidates = cursor.fetchall()
            if len(candidates) != 1:
                return False, 'Brak jednoznacznej pozycji transferu'
            service = OsipTransferService()
            transfer = service._locked_transfer(conn, candidates[0]['transfer_id'], ('RECEIVING',))
            item = service._match_item(transfer, code)
            table, qty_column, _ = service._stock_spec(item)
            cursor.execute(f"SELECT id,lokalizacja,{qty_column} AS quantity FROM {table} "
                           "WHERE id=%s AND UPPER(TRIM(nr_palety))=%s FOR UPDATE",
                           (service._value(item,'pallet_id'), str(service._value(item,'nr_palety') or '').upper()))
            row = cursor.fetchone()
            if not row or str(row.get('lokalizacja') or '').upper() != location or float(row.get('quantity') or 0) <= 0:
                return False, 'Paleta nie została odstawiona na wskazaną lokalizację'
            if str(transfer.destination_warehouse or '').upper().startswith('OS') != is_osip_location(location):
                return False, 'Paleta nie trafiła do magazynu docelowego transferu'
            cursor.execute("UPDATE osip_transfer_items SET status='RECEIVED' WHERE id=%s AND transfer_id=%s",
                           (service._value(item,'id'), transfer.id))
            cursor.execute("SELECT COUNT(*) AS remaining FROM osip_transfer_items WHERE transfer_id=%s AND status!='RECEIVED'", (transfer.id,))
            if cursor.fetchone()['remaining'] == 0:
                service.repository.update_transfer_status(transfer.id, 'COMPLETED', user_login, external_conn=conn)
            if external_conn is None:
                conn.commit()
            return True, 'Potwierdzono przyjęcie transferu'
        except Exception:
            if external_conn is not None:
                raise
            conn.rollback()
            raise
        finally:
            cursor.close()
            if external_conn is None:
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
            elif t.status in ("IN_TRANSIT", "RECEIVING") and user_branch == dest_branch:
                filtered.append(t)
            elif t.status in ("COMPLETED", "CANCELLED") and (user_branch in (source_branch, dest_branch)):
                filtered.append(t)

        return filtered
