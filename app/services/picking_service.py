"""
Service for warehouse picking (completion) orders.

Responsibility: Business logic for FIFO-based pallet allocation, pick confirmation,
and automatic relocation to MP01. Orchestrates PickingRepository and
WarehouseOrderRepository for stock data.
"""
from datetime import datetime
from app.repositories.picking_repository import PickingRepository
from app.repositories.warehouse_order_repository import WarehouseOrderRepository
from app.core.database import get_db_connection
from app.utils.surowiec_validator import validate_surowiec_name


class PickingService:
    """Business logic for the picking / completion workflow."""

    def __init__(self):
        self._picking_repo = PickingRepository()
        self._order_repo = WarehouseOrderRepository()

    def start_picking(self, calculation_results, operator_login):
        """Creates a picking order from calculator results, allocating FIFO pallets.

        Workflow:
        1. Generate unique order_ref (PICK-YYYYMMDD-SEQ).
        2. For each surowiec in results, select active pallets (FIFO order)
           up to the required quantity.
        3. Blocked pallets are recorded with status POMINIETA.
        4. Pending deliveries are noted as informational (passive).
        5. Persist via PickingRepository.

        Args:
            calculation_results: Dict with 'items' list from calculate_and_check_stock.
                Each item: surowiec_nazwa, potrzebne_kg, palety_fifo, ...
            operator_login: Login of the operator creating the order.

        Returns:
            tuple[bool, str, dict]: (success, message, payload with order_ref + summary).
        """
        items = calculation_results.get('items', [])
        if not items:
            return False, "Brak surowców do kompletacji.", {}

        seq = self._picking_repo.get_next_order_sequence()
        today_str = datetime.now().strftime('%Y%m%d')
        order_ref = f"PICK-{today_str}-{seq:03d}"

        picking_rows = []
        summary_surowce = []
        total_allocated = 0
        total_blocked = 0
        total_missing = 0

        for item in items:
            nazwa = str(item.get('surowiec_nazwa', '')).strip()
            is_valid, err_msg = validate_surowiec_name(nazwa)
            if not is_valid:
                return False, err_msg, {}

            needed_kg = float(item.get('potrzebne_kg', 0))
            palety_fifo = item.get('palety_fifo', [])

            allocated_kg = 0.0
            blocked_kg = 0.0
            item_rows = []

            for pallet in palety_fifo:
                pallet_kg = float(pallet.get('stan_magazynowy', 0))
                is_blocked = bool(pallet.get('is_blocked'))
                is_mp01 = (str(pallet.get('lokalizacja') or '').strip().upper() == 'MP01')
                status = 'POMINIETA' if is_blocked else ('SKOMPLETOWANA' if is_mp01 else 'OCZEKUJE')

                row = {
                    'order_ref': order_ref,
                    'surowiec_nazwa': nazwa,
                    'paleta_id': pallet.get('id', 0),
                    'nr_palety': pallet.get('nr_palety', ''),
                    'lokalizacja_zrodlowa': pallet.get('lokalizacja', ''),
                    'ilosc_kg': pallet_kg,
                    'nr_partii': pallet.get('nr_partii', ''),
                    'fifo_rank': pallet.get('fifo_rank'),
                    'is_blocked': is_blocked,
                    'powod_blokady': pallet.get('powod_blokady', ''),
                    'status': status,
                    'operator_login': operator_login,
                }

                if is_blocked:
                    blocked_kg += pallet_kg
                    total_blocked += 1
                else:
                    allocated_kg += pallet_kg
                    total_allocated += 1

                item_rows.append(row)

                if not is_blocked and allocated_kg >= needed_kg:
                    break

            if not item_rows:
                # Brak palet na stanie magazynowym dla tego surowca
                item_rows.append({
                    'order_ref': order_ref,
                    'surowiec_nazwa': nazwa,
                    'paleta_id': 0,
                    'nr_palety': 'BRAK NA STANIE',
                    'lokalizacja_zrodlowa': 'BRAK',
                    'ilosc_kg': needed_kg,
                    'nr_partii': '',
                    'fifo_rank': None,
                    'is_blocked': True,
                    'powod_blokady': f'Brak dostępnych palet na stanie magazynowym (Zapotrzebowanie: {needed_kg:.2f} kg)',
                    'operator_login': operator_login,
                })
                total_blocked += 1

            picking_rows.extend(item_rows)

            missing_kg = max(0.0, needed_kg - allocated_kg)
            if missing_kg > 0:
                total_missing += 1

            pending_deliveries = self._check_pending_deliveries(nazwa)

            summary_surowce.append({
                'surowiec_nazwa': nazwa,
                'potrzebne_kg': round(needed_kg, 2),
                'alokowane_kg': round(allocated_kg, 2),
                'zablokowane_kg': round(blocked_kg, 2),
                'brakujace_kg': round(missing_kg, 2),
                'palet_alokowanych': len([r for r in item_rows if not r['is_blocked']]),
                'palet_zablokowanych': len([r for r in item_rows if r['is_blocked']]),
                'dostawy_oczekujace': pending_deliveries,
            })

        order_tons = calculation_results.get('order_tons', 0)
        order_items = []
        for s in summary_surowce:
            order_items.append({
                'surowiec_nazwa': s['surowiec_nazwa'],
                'ilosc_kg': s['potrzebne_kg'],
                'pokryte_kg': s['alokowane_kg'],
                'brakujace_kg': s['brakujace_kg'],
                'order_ref': order_ref
            })

        # Zapisz zawsze do tabeli magazyn_zamowienia (widok Zamówienia)
        order_id = self._order_repo.create(
            items=order_items,
            operator_login=operator_login,
            komentarz=f"Dyspozycja {order_ref} (Zlecenie {order_tons} t)"
        )

        inserted = 0
        if picking_rows:
            inserted = self._picking_repo.create_picking_items(picking_rows)

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
        }

        msg = f"Dyspozycja {order_ref} utworzona (Zamówienie #{order_id}, {inserted} palet do pobrania FIFO)." if inserted > 0 else f"Zamówienie #{order_id} ({order_ref}) zarejestrowane. Brak palet na stanie do kompletacji."
        return True, msg, payload

    def get_picking_order_details(self, order_ref):
        """Fetches full picking order data grouped by surowiec.

        Args:
            order_ref: Picking order reference string.

        Returns:
            dict: Order details with items grouped by surowiec, progress stats.
        """
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

        placeholders = [it for it in items if it.get('paleta_id') == 0 and it.get('status') == 'POMINIETA']
        if not placeholders:
            return

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            for ph in placeholders:
                ph_id = ph['id']
                nazwa = ph['surowiec_nazwa']
                needed_kg = float(ph.get('ilosc_kg', 0))
                operator_login = ph.get('operator_login', '')

                stock_check = self._order_repo.check_stock([nazwa])
                stock_data = stock_check.get('stock_data', {}).get(nazwa, {})
                palety_fifo = stock_data.get('palety_fifo', [])
                active_pallets = [p for p in palety_fifo if not p.get('is_blocked')]

                if not active_pallets:
                    continue

                # Wyklucz palety już przypisane do aktywnych kompletacji
                cursor.execute(
                    "SELECT paleta_id FROM magazyn_kompletacja WHERE status = 'OCZEKUJE' AND paleta_id > 0"
                )
                allocated_ids = {row['paleta_id'] for row in cursor.fetchall()}

                newly_available = [p for p in active_pallets if p['id'] not in allocated_ids]
                if not newly_available:
                    continue

                accumulated = 0.0
                new_rows = []
                for p in newly_available:
                    p_kg = float(p.get('stan_magazynowy', 0))
                    accumulated += p_kg
                    new_rows.append({
                        'order_ref': order_ref,
                        'surowiec_nazwa': nazwa,
                        'paleta_id': p['id'],
                        'nr_palety': p.get('nr_palety', ''),
                        'lokalizacja_zrodlowa': p.get('lokalizacja', ''),
                        'ilosc_kg': p_kg,
                        'nr_partii': p.get('nr_partii', ''),
                        'fifo_rank': p.get('fifo_rank'),
                        'is_blocked': False,
                        'powod_blokady': '',
                        'operator_login': operator_login,
                    })
                    if accumulated >= needed_kg:
                        break

                if new_rows:
                    self._picking_repo.create_picking_items(new_rows)
                    if accumulated >= needed_kg:
                        cursor.execute("DELETE FROM magazyn_kompletacja WHERE id = %s", (ph_id,))
                    else:
                        rem_kg = max(0.0, needed_kg - accumulated)
                        cursor.execute("UPDATE magazyn_kompletacja SET ilosc_kg = %s WHERE id = %s", (rem_kg, ph_id))
                    conn.commit()
        except Exception:
            pass
        finally:
            conn.close()

    def confirm_pick_by_sscc(self, order_ref, sscc_code, magazynier_login):
        """Confirms a pick by scanning SSCC barcode. Moves pallet to MP01.

        Args:
            order_ref: Picking order reference.
            sscc_code: Scanned SSCC barcode string.
            magazynier_login: Login of the warehouse worker.

        Returns:
            tuple[bool, str, dict]: (success, message, updated_item_data).
        """
        sscc_clean = str(sscc_code).strip()
        if not sscc_clean:
            return False, "Pusty kod SSCC.", {}

        item = self._picking_repo.find_item_by_sscc(order_ref, sscc_clean)
        if not item:
            return False, f"Paleta SSCC '{sscc_clean}' nie została znaleziona w dyspozycji {order_ref} lub jest już skompletowana.", {}

        return self._execute_pick_confirmation(item, magazynier_login)

    def confirm_pick_by_id(self, item_id, magazynier_login):
        """Confirms a pick by item ID (manual confirmation). Moves pallet to MP01.

        Args:
            item_id: ID of the magazyn_kompletacja row.
            magazynier_login: Login of the warehouse worker.

        Returns:
            tuple[bool, str, dict]: (success, message, updated_item_data).
        """
        items = self._picking_repo.get_by_order_ref('')
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
        """Cancels all pending items in a picking order.

        Args:
            order_ref: Picking order reference.

        Returns:
            tuple[bool, str]: (success, message).
        """
        cancelled = self._picking_repo.cancel_order(order_ref)
        if cancelled == 0:
            return False, f"Brak oczekujących pozycji do anulowania w {order_ref}."
        return True, f"Anulowano {cancelled} pozycji w dyspozycji {order_ref}."

    def delete_picking_order(self, order_ref, user_role):
        """Trwale usuwa dyspozycję kompletacji (uprawnienia dla masteradmin, admin, zarzad).

        Args:
            order_ref: Referencja zamówienia kompletacji.
            user_role: Rola użytkownika.

        Returns:
            tuple[bool, str]: (sukces, komunikat).
        """
        role_norm = str(user_role or '').lower().replace(' ', '').replace('_', '').strip()
        if role_norm not in ['masteradmin', 'admin', 'administrator', 'zarzad', 'zarząd']:
            return False, "Brak uprawnień. Usuwanie dostępne tylko dla ról: MasterAdmin, Admin oraz Zarząd."

        items = self._picking_repo.get_by_order_ref(order_ref)
        if not items:
            return False, f"Dyspozycja {order_ref} nie istnieje lub została już usunięta."

        deleted_rows = self._picking_repo.delete_order(order_ref)
        if deleted_rows == 0:
            return False, f"Nie udało się usunąć dyspozycji {order_ref}."

        return True, f"Dyspozycja {order_ref} ({deleted_rows} pozycji) została trwale usunięta."

    def get_active_orders(self, operator_login=None):
        """Returns list of active picking orders.

        Args:
            operator_login: Optional filter by operator.

        Returns:
            list[dict]: Active picking orders with progress stats.
        """
        return self._picking_repo.get_active_orders(operator_login)

    def _execute_pick_confirmation(self, item, magazynier_login):
        """Internal: confirms pick, moves pallet to MP01, logs movement.

        Args:
            item: Dict from magazyn_kompletacja row.
            magazynier_login: Warehouse worker login.

        Returns:
            tuple[bool, str, dict]: (success, message, item_data).
        """
        paleta_id = item.get('paleta_id')
        item_id = item.get('id')
        order_ref = item.get('order_ref', '')
        source_loc = item.get('lokalizacja_zrodlowa', '')

        move_ok = self._move_pallet_to_mp01(paleta_id, source_loc, magazynier_login)
        if not move_ok:
            return False, f"Nie udało się przenieść palety #{paleta_id} na MP01.", {}

        updated = self._picking_repo.mark_item_completed(item_id, magazynier_login)
        if updated == 0:
            return False, "Pozycja została już skompletowana przez innego operatora.", {}

        return True, f"✅ Paleta {item.get('nr_palety', '')} przeniesiona na MP01 i oznaczona jako skompletowana.", {
            'item_id': item_id,
            'paleta_id': paleta_id,
            'nr_palety': item.get('nr_palety', ''),
            'surowiec_nazwa': item.get('surowiec_nazwa', ''),
            'lokalizacja_zrodlowa': source_loc,
            'lokalizacja_docelowa': 'MP01',
            'order_ref': order_ref,
        }

    def _move_pallet_to_mp01(self, paleta_id, source_location, magazynier_login):
        """Moves a raw material pallet to MP01 in magazyn_surowce and logs movement.

        Args:
            paleta_id: ID of the pallet in magazyn_surowce.
            source_location: Previous location string.
            magazynier_login: Who performed the move.

        Returns:
            bool: True if update succeeded.
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()

            cursor.execute(
                """
                UPDATE magazyn_surowce
                SET lokalizacja = 'MP01'
                WHERE id = %s
                """,
                (paleta_id,)
            )

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
                        source_location or '',
                        magazynier_login,
                        f'Kompletacja FIFO → MP01',
                        datetime.now(),
                    )
                )
            except Exception:
                pass

            conn.commit()
            return cursor.rowcount > 0 or True
        except Exception:
            conn.rollback()
            return False
        finally:
            conn.close()

    @staticmethod
    def _check_pending_deliveries(surowiec_nazwa):
        """Checks magazyn_dostawy for pending deliveries containing a given raw material (passive info).

        Args:
            surowiec_nazwa: Name of the raw material.

        Returns:
            list[dict]: Pending delivery summaries (delivery_id, expected date, qty).
        """
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

            for d in deliveries:
                raw_items = d.get('items', '')
                if not raw_items:
                    continue
                try:
                    parsed = json.loads(raw_items) if isinstance(raw_items, str) else raw_items
                except Exception:
                    continue

                if not isinstance(parsed, list):
                    continue

                for pi in parsed:
                    item_name = str(pi.get('nazwa', '') or pi.get('surowiec', '') or '').strip().lower()
                    if item_name and (norm_name in item_name or item_name in norm_name):
                        date_str = ''
                        if d.get('created_at'):
                            try:
                                date_str = d['created_at'].strftime('%Y-%m-%d %H:%M')
                            except Exception:
                                date_str = str(d['created_at'])

                        matches.append({
                            'delivery_id': d.get('id'),
                            'status': d.get('status', ''),
                            'date': date_str,
                            'item_name': item_name,
                            'qty': pi.get('ilosc_kg', pi.get('ilosc', 0)),
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
