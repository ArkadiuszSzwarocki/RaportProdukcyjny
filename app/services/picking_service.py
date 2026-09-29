"""
Service for warehouse picking (completion) orders.

Responsibility: Business logic for FIFO-based pallet allocation, pick confirmation,
and automatic relocation to MP01. Orchestrates PickingRepository and
WarehouseOrderRepository for stock data.
"""
from datetime import datetime
import uuid

from app.repositories.picking_repository import PickingRepository
from app.repositories.warehouse_order_repository import WarehouseOrderRepository
from app.services.warehouse_order_service import WarehouseOrderService
from app.core.database import get_db_connection
from app.utils.surowiec_validator import validate_surowiec_name


class PickingService:
    """Business logic for the picking / completion workflow."""

    _CREATE_LOCK_NAME = 'warehouse_picking_create'
    _CREATE_LOCK_TIMEOUT_SECONDS = 10

    def __init__(self):
        self._picking_repo = PickingRepository()
        self._order_repo = WarehouseOrderRepository()

    @staticmethod
    def _recipe_from_request(calculation_request):
        """Build a trusted recipe input from calculator data.

        The browser may send previously rendered stock rows, but only material name and
        recipe rate are reused. Pallet IDs, locations and quantities are always reloaded
        from the database immediately before the picking order is created.
        """
        source_items = calculation_request.get('recipe_items') or calculation_request.get('items') or []
        recipe = []
        for item in source_items:
            if not isinstance(item, dict):
                continue
            name = str(item.get('surowiec_nazwa') or '').strip()
            rate = item.get('przelicznik_na_1t')
            if name and rate is not None:
                recipe.append({
                    'surowiec_nazwa': name,
                    'przelicznik_na_1t': rate,
                })
        return recipe

    @staticmethod
    def _build_order_ref(sequence):
        """Build a readable but collision-resistant picking reference."""
        today_str = datetime.now().strftime('%Y%m%d')
        suffix = uuid.uuid4().hex[:4].upper()
        return f"PICK-{today_str}-{sequence:03d}-{suffix}"

    def start_picking(self, calculation_request, operator_login):
        """Create a picking order after a fresh stock calculation.

        Important invariants:
        - stock is recalculated on the server at creation time;
        - OSIP/MS01/BFMS01 exclusions and active reservations come from check_stock();
        - blocked pallets are informational and are never inserted as real picking rows;
        - every partial/complete shortage gets a placeholder so it can be filled later;
        - an advisory DB lock serializes picking creation to avoid double allocation.
        """
        recipe_items = self._recipe_from_request(calculation_request)
        if not recipe_items:
            return False, "Brak poprawnej receptury do ponownego sprawdzenia magazynu.", {}

        order_tons = calculation_request.get('order_tons', 0)
        linia = str(calculation_request.get('linia') or 'AGRO').upper()
        if linia not in ('AGRO', 'PSD'):
            linia = 'AGRO'

        lock_conn = None
        lock_cursor = None
        lock_acquired = False
        order_ref = None
        try:
            lock_conn = get_db_connection()
            lock_cursor = lock_conn.cursor()
            lock_cursor.execute(
                "SELECT GET_LOCK(%s, %s)",
                (self._CREATE_LOCK_NAME, self._CREATE_LOCK_TIMEOUT_SECONDS),
            )
            lock_row = lock_cursor.fetchone()
            lock_acquired = bool(lock_row and int(lock_row[0] or 0) == 1)
            if not lock_acquired:
                return False, (
                    "Magazyn jest właśnie rezerwowany przez inną kompletację. "
                    "Spróbuj ponownie za chwilę."
                ), {}

            # Nie ufamy paletom przesłanym przez przeglądarkę. Ponownie liczymy stan
            # dopiero po uzyskaniu blokady, aby druga kompletacja nie mogła przejąć
            # tych samych palet pomiędzy sprawdzeniem i zapisem.
            calculator = WarehouseOrderService()
            ok, message, fresh_calculation = calculator.calculate_and_check_stock(
                recipe_items,
                order_tons,
                linia,
            )
            if not ok:
                return False, message, {}

            items = fresh_calculation.get('items', [])
            if not items:
                return False, "Brak surowców do kompletacji po ponownym przeliczeniu.", {}

            sequence = self._picking_repo.get_next_order_sequence()
            order_ref = self._build_order_ref(sequence)

            picking_rows = []
            summary_surowce = []
            total_allocated = 0
            total_blocked = 0
            total_missing = 0

            for item in items:
                nazwa = str(item.get('surowiec_nazwa') or '').strip()
                is_valid, err_msg = validate_surowiec_name(nazwa)
                if not is_valid:
                    return False, err_msg, {}

                needed_kg = float(item.get('potrzebne_kg') or 0)
                palety_fifo = item.get('palety_fifo') or []
                allocated_kg = 0.0
                item_rows = []

                blocked_pallets = [p for p in palety_fifo if p.get('is_blocked')]
                total_blocked += len(blocked_pallets)
                blocked_kg = sum(float(p.get('stan_magazynowy') or 0) for p in blocked_pallets)

                for pallet in palety_fifo:
                    if pallet.get('is_blocked'):
                        continue

                    pallet_kg = float(pallet.get('stan_magazynowy') or 0)
                    if pallet_kg <= 0:
                        continue

                    source_location = str(pallet.get('lokalizacja') or '').strip().upper()
                    is_mp01 = source_location == 'MP01'
                    row = {
                        'order_ref': order_ref,
                        'surowiec_nazwa': nazwa,
                        'paleta_id': pallet.get('id', 0),
                        'nr_palety': pallet.get('nr_palety', ''),
                        'lokalizacja_zrodlowa': source_location,
                        'ilosc_kg': pallet_kg,
                        'nr_partii': pallet.get('nr_partii', ''),
                        'fifo_rank': pallet.get('fifo_rank'),
                        'is_blocked': False,
                        'powod_blokady': '',
                        'status': 'SKOMPLETOWANA' if is_mp01 else 'OCZEKUJE',
                        'operator_login': operator_login,
                    }
                    item_rows.append(row)
                    allocated_kg += pallet_kg
                    total_allocated += 1
                    if allocated_kg >= needed_kg:
                        break

                missing_kg = max(0.0, needed_kg - allocated_kg)
                if missing_kg > 0:
                    total_missing += 1
                    # Placeholder powstaje również przy braku częściowym. Dzięki temu
                    # sync_pending_pallets może później dobrać nowe palety z PZ/MM.
                    item_rows.append({
                        'order_ref': order_ref,
                        'surowiec_nazwa': nazwa,
                        'paleta_id': 0,
                        'nr_palety': 'BRAK DO UZUPEŁNIENIA',
                        'lokalizacja_zrodlowa': 'BRAK',
                        'ilosc_kg': round(missing_kg, 2),
                        'nr_partii': '',
                        'fifo_rank': None,
                        'is_blocked': True,
                        'powod_blokady': (
                            f'Brak do uzupełnienia: {missing_kg:.2f} kg '
                            f'(zapotrzebowanie: {needed_kg:.2f} kg)'
                        ),
                        'status': 'POMINIETA',
                        'operator_login': operator_login,
                    })

                picking_rows.extend(item_rows)
                pending_deliveries = self._check_pending_deliveries(nazwa)
                summary_surowce.append({
                    'surowiec_nazwa': nazwa,
                    'potrzebne_kg': round(needed_kg, 2),
                    'alokowane_kg': round(allocated_kg, 2),
                    'zablokowane_kg': round(blocked_kg, 2),
                    'brakujace_kg': round(missing_kg, 2),
                    'palet_alokowanych': len([r for r in item_rows if r.get('paleta_id', 0) > 0]),
                    'palet_zablokowanych': len(blocked_pallets),
                    'dostawy_oczekujace': pending_deliveries,
                })

            order_items = []
            for summary in summary_surowce:
                missing_kg = round(float(summary.get('brakujace_kg') or 0), 2)
                if missing_kg > 0:
                    order_items.append({
                        'surowiec_nazwa': summary['surowiec_nazwa'],
                        'ilosc_kg': missing_kg,
                        'pokryte_kg': round(float(summary.get('alokowane_kg') or 0), 2),
                        'brakujace_kg': missing_kg,
                        'potrzebne_kg': round(float(summary.get('potrzebne_kg') or 0), 2),
                        'order_ref': order_ref,
                    })

            # Najpierw zapisujemy dyspozycję. Gdy później nie uda się utworzyć
            # zamówienia braków, usuwamy dyspozycję kompensacyjnie.
            inserted = self._picking_repo.create_picking_items(picking_rows) if picking_rows else 0
            if picking_rows and inserted <= 0:
                return False, "Nie udało się zapisać listy kompletacyjnej.", {}

            order_id = None
            try:
                if order_items:
                    order_id = self._order_repo.create(
                        items=order_items,
                        operator_login=operator_login,
                        komentarz=(
                            f"Dyspozycja {order_ref} "
                            f"(brakujące na zlecenie {fresh_calculation.get('order_tons', order_tons)} t)"
                        ),
                    )
            except Exception:
                if order_ref:
                    try:
                        self._picking_repo.delete_order(order_ref)
                    except Exception:
                        pass
                raise

            payload = {
                'order_ref': order_ref,
                'order_id': order_id,
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'operator_login': operator_login,
                'total_allocated': total_allocated,
                'total_blocked': total_blocked,
                'total_missing_surowce': total_missing,
                'inserted_rows': inserted,
                'summary': summary_surowce,
                'calculation': fresh_calculation,
            }

            if order_id:
                msg = (
                    f"Dyspozycja {order_ref} utworzona ({inserted} pozycji). "
                    f"Zgłoszono zamówienie #{order_id} wyłącznie na brakujące ilości."
                )
            else:
                msg = (
                    f"Dyspozycja {order_ref} utworzona ({inserted} pozycji). "
                    "Wszystkie surowce są pokryte aktualnym stanem magazynu."
                )
            return True, msg, payload
        except Exception as exc:
            return False, f"Nie udało się utworzyć dyspozycji kompletacji: {exc}", {}
        finally:
            if lock_acquired and lock_cursor:
                try:
                    lock_cursor.execute("SELECT RELEASE_LOCK(%s)", (self._CREATE_LOCK_NAME,))
                except Exception:
                    pass
            if lock_cursor:
                try:
                    lock_cursor.close()
                except Exception:
                    pass
            if lock_conn:
                try:
                    lock_conn.close()
                except Exception:
                    pass

    def get_picking_order_details(self, order_ref):
        """Fetches full picking order data grouped by surowiec."""
        self.sync_pending_pallets(order_ref)
        items = self._picking_repo.get_by_order_ref(order_ref)
        if not items:
            return None

        grouped = {}
        total = 0
        completed = 0
        pending = 0
        skipped = 0
        cancelled = 0

        for item in items:
            total += 1
            status = item.get('status', 'OCZEKUJE')
            if status == 'SKOMPLETOWANA':
                completed += 1
            elif status == 'OCZEKUJE':
                pending += 1
            elif status == 'POMINIETA':
                skipped += 1
            elif status == 'ANULOWANA':
                cancelled += 1

            nazwa = item.get('surowiec_nazwa', '')
            if nazwa not in grouped:
                grouped[nazwa] = []

            self._format_dates(item)
            grouped[nazwa].append(item)

        return {
            'order_ref': order_ref,
            'operator_login': items[0].get('operator_login', '') if items else '',
            'created_at': items[0].get('created_at', '') if items else '',
            'items_grouped': grouped,
            'progress': {
                'total': total,
                'completed': completed,
                'pending': pending,
                'skipped': skipped,
                'cancelled': cancelled,
                'percent': round((completed / total * 100) if total > 0 else 0, 1),
            }
        }

    def sync_pending_pallets(self, order_ref):
        """Automatycznie sprawdza czy pojawiły się nowe palety z PZ / MM dla brakujących pozycji."""
        if not order_ref:
            return
        items = self._picking_repo.get_by_order_ref(order_ref)
        if not items:
            return

        placeholders = [
            item for item in items
            if item.get('paleta_id') == 0 and item.get('status') == 'POMINIETA'
        ]
        if not placeholders:
            return

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            for placeholder in placeholders:
                placeholder_id = placeholder['id']
                nazwa = placeholder['surowiec_nazwa']
                needed_kg = float(placeholder.get('ilosc_kg') or 0)
                operator_login = placeholder.get('operator_login', '')

                stock_check = self._order_repo.check_stock([nazwa])
                stock_data = stock_check.get('stock_data', {}).get(nazwa, {})
                palety_fifo = stock_data.get('palety_fifo', [])
                active_pallets = [p for p in palety_fifo if not p.get('is_blocked')]
                if not active_pallets:
                    continue

                cursor.execute(
                    "SELECT paleta_id FROM magazyn_kompletacja "
                    "WHERE status IN ('OCZEKUJE', 'SKOMPLETOWANA') AND paleta_id > 0"
                )
                allocated_ids = {row['paleta_id'] for row in cursor.fetchall()}
                newly_available = [p for p in active_pallets if p['id'] not in allocated_ids]
                if not newly_available:
                    continue

                accumulated = 0.0
                new_rows = []
                for pallet in newly_available:
                    pallet_kg = float(pallet.get('stan_magazynowy') or 0)
                    accumulated += pallet_kg
                    new_rows.append({
                        'order_ref': order_ref,
                        'surowiec_nazwa': nazwa,
                        'paleta_id': pallet['id'],
                        'nr_palety': pallet.get('nr_palety', ''),
                        'lokalizacja_zrodlowa': pallet.get('lokalizacja', ''),
                        'ilosc_kg': pallet_kg,
                        'nr_partii': pallet.get('nr_partii', ''),
                        'fifo_rank': pallet.get('fifo_rank'),
                        'is_blocked': False,
                        'powod_blokady': '',
                        'operator_login': operator_login,
                    })
                    if accumulated >= needed_kg:
                        break

                if new_rows:
                    self._picking_repo.create_picking_items(new_rows)
                    if accumulated >= needed_kg:
                        cursor.execute(
                            "DELETE FROM magazyn_kompletacja WHERE id = %s",
                            (placeholder_id,),
                        )
                    else:
                        remaining_kg = max(0.0, needed_kg - accumulated)
                        cursor.execute(
                            "UPDATE magazyn_kompletacja SET ilosc_kg = %s WHERE id = %s",
                            (remaining_kg, placeholder_id),
                        )
                    conn.commit()
        except Exception:
            pass
        finally:
            conn.close()

    def confirm_pick_by_sscc(self, order_ref, sscc_code, magazynier_login):
        """Confirms a pick by scanning SSCC barcode. Moves pallet to MP01."""
        sscc_clean = str(sscc_code).strip()
        if not sscc_clean:
            return False, "Pusty kod SSCC.", {}

        item = self._picking_repo.find_item_by_sscc(order_ref, sscc_clean)
        if not item:
            return False, (
                f"Paleta SSCC '{sscc_clean}' nie została znaleziona w dyspozycji "
                f"{order_ref} lub jest już skompletowana."
            ), {}

        return self._execute_pick_confirmation(item, magazynier_login)

    def confirm_pick_by_id(self, item_id, magazynier_login):
        """Confirms a pick by item ID (manual confirmation). Moves pallet to MP01."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM magazyn_kompletacja WHERE id = %s AND status = 'OCZEKUJE'",
                (item_id,)
            )
            item = cursor.fetchone()
        finally:
            conn.close()

        if not item:
            return False, "Pozycja nie istnieje lub jest już skompletowana.", {}

        return self._execute_pick_confirmation(item, magazynier_login)

    def cancel_picking_order(self, order_ref):
        """Cancels all pending items in a picking order."""
        items = self._picking_repo.get_by_order_ref(order_ref)
        if not items:
            return False, f"Dyspozycja {order_ref} nie istnieje lub została już usunięta."

        cancelled = self._picking_repo.cancel_order(order_ref)
        if cancelled == 0:
            has_pending = any(item.get('status') == 'OCZEKUJE' for item in items)
            if not has_pending:
                return True, f"Dyspozycja {order_ref} została anulowana."
            return False, f"Brak oczekujących pozycji do anulowania w {order_ref}."
        return True, f"Anulowano {cancelled} pozycji w dyspozycji {order_ref}."

    def delete_picking_order(self, order_ref, user_role):
        """Trwale usuwa dyspozycję kompletacji."""
        items = self._picking_repo.get_by_order_ref(order_ref)
        if not items:
            return False, f"Dyspozycja {order_ref} nie istnieje lub została już usunięta."

        role_norm = str(user_role or '').lower().replace(' ', '').replace('_', '').strip()
        is_admin = role_norm in ['masteradmin', 'admin', 'administrator', 'zarzad', 'zarząd']
        has_completed = any(item.get('status') == 'SKOMPLETOWANA' for item in items)

        if has_completed and not is_admin:
            return False, (
                "Brak uprawnień. W dyspozycji rozpoczęto już realizację palet — "
                "usuwanie dostępne tylko dla administratora."
            )

        deleted_rows = self._picking_repo.delete_order(order_ref)
        if deleted_rows == 0:
            return False, f"Nie udało się usunąć dyspozycji {order_ref}."

        return True, f"Dyspozycja {order_ref} ({deleted_rows} pozycji) została usunięta."

    def get_active_orders(self, operator_login=None):
        """Returns list of active picking orders."""
        return self._picking_repo.get_active_orders(operator_login)

    def _execute_pick_confirmation(self, item, magazynier_login):
        """Confirm a pick only if the pallet is still in the expected source location."""
        paleta_id = item.get('paleta_id')
        item_id = item.get('id')
        order_ref = item.get('order_ref', '')
        source_loc = item.get('lokalizacja_zrodlowa', '')

        move_ok = self._move_pallet_to_mp01(paleta_id, source_loc, magazynier_login)
        if not move_ok:
            return False, (
                f"Paleta #{paleta_id} nie jest już dostępna w lokalizacji {source_loc} "
                "lub została zablokowana. Odśwież kompletację."
            ), {}

        updated = self._picking_repo.mark_item_completed(item_id, magazynier_login)
        if updated == 0:
            return False, "Pozycja została już skompletowana przez innego operatora.", {}

        return True, (
            f"✅ Paleta {item.get('nr_palety', '')} przeniesiona na MP01 "
            "i oznaczona jako skompletowana."
        ), {
            'item_id': item_id,
            'paleta_id': paleta_id,
            'nr_palety': item.get('nr_palety', ''),
            'surowiec_nazwa': item.get('surowiec_nazwa', ''),
            'lokalizacja_zrodlowa': source_loc,
            'lokalizacja_docelowa': 'MP01',
            'order_ref': order_ref,
        }

    def _move_pallet_to_mp01(self, paleta_id, source_location, magazynier_login):
        """Move a pallet only when its current DB state still matches the picking row."""
        if not paleta_id or not source_location:
            return False

        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE magazyn_surowce
                SET lokalizacja = 'MP01'
                WHERE id = %s
                  AND stan_magazynowy > 0
                  AND COALESCE(is_blocked, 0) = 0
                  AND UPPER(TRIM(COALESCE(lokalizacja, ''))) = UPPER(TRIM(%s))
                """,
                (paleta_id, source_location)
            )
            moved_rows = cursor.rowcount
            if moved_rows != 1:
                conn.rollback()
                return False

            try:
                cursor.execute(
                    """
                    INSERT INTO magazyn_ruch
                        (paleta_id, typ, lokalizacja_z, lokalizacja_do,
                         operator_login, komentarz, created_at)
                    VALUES (%s, 'KOMPLETACJA', %s, 'MP01', %s, %s, %s)
                    """,
                    (
                        paleta_id,
                        source_location,
                        magazynier_login,
                        'Kompletacja FIFO → MP01',
                        datetime.now(),
                    )
                )
            except Exception:
                # Log ruchu jest pomocniczy; właściwy ruch palety nie powinien być
                # cofany tylko dlatego, że starszy schemat nie ma wymaganych kolumn.
                pass

            conn.commit()
            return True
        except Exception:
            conn.rollback()
            return False
        finally:
            conn.close()

    @staticmethod
    def _check_pending_deliveries(surowiec_nazwa):
        """Checks pending deliveries containing a given raw material (passive info)."""
        if not surowiec_nazwa:
            return []

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT id, items, created_at, status
                FROM magazyn_dostawy
                WHERE status IN ('OCZEKUJE', 'PUTAWAY_IN_PROGRESS')
                ORDER BY created_at ASC
                """
            )
            deliveries = cursor.fetchall()

            import json
            norm_name = surowiec_nazwa.strip().lower()
            matches = []

            for delivery in deliveries:
                raw_items = delivery.get('items', '')
                if not raw_items:
                    continue
                try:
                    parsed = json.loads(raw_items) if isinstance(raw_items, str) else raw_items
                except Exception:
                    continue

                if not isinstance(parsed, list):
                    continue

                for pending_item in parsed:
                    item_name = str(
                        pending_item.get('nazwa', '') or pending_item.get('surowiec', '') or ''
                    ).strip().lower()
                    if item_name and item_name == norm_name:
                        date_str = ''
                        if delivery.get('created_at'):
                            try:
                                date_str = delivery['created_at'].strftime('%Y-%m-%d %H:%M')
                            except Exception:
                                date_str = str(delivery['created_at'])

                        matches.append({
                            'delivery_id': delivery.get('id'),
                            'status': delivery.get('status', ''),
                            'date': date_str,
                            'item_name': item_name,
                            'qty': pending_item.get('ilosc_kg', pending_item.get('ilosc', 0)),
                        })
                        break

            return matches
        except Exception:
            return []
        finally:
            conn.close()

    @staticmethod
    def _format_dates(item):
        """Formats datetime fields to strings for JSON serialization."""
        for key in ('created_at', 'completed_at'):
            val = item.get(key)
            if val and hasattr(val, 'strftime'):
                item[key] = val.strftime('%Y-%m-%d %H:%M:%S')
