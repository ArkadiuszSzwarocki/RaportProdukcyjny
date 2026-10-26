"""Cancel outstanding order quantities and atomically create a linked replacement."""
import json
import math
from datetime import datetime

from app.db import get_db_connection
from app.core.shared_inventory_permissions import can_manage_orders


def requested_quantity(item):
    value = float(item.get('brakujace_kg') if item.get('brakujace_kg') is not None else item.get('ilosc_kg') or 0)
    if not math.isfinite(value) or value < 0:
        raise ValueError('Nieprawidłowa ilość zamówienia.')
    return value


def remaining_quantity(item):
    assigned = sum(float(allocation['kg']) for allocation in item.get('transfer_allocations', []))
    return max(0, requested_quantity(item) - assigned)


def order_status(items):
    relevant = [item for item in items if requested_quantity(item) > 0]
    if any(not item.get('cancellation') and remaining_quantity(item) > 0.0001 for item in relevant):
        return 'NOWE'
    return 'ANULOWANE' if any(item.get('cancellation') for item in relevant) else 'ZAMKNIETE'


class WarehouseOrderChanges:
    @staticmethod
    def resolve(order_id, item_index, payload, login, role):
        if not can_manage_orders(role):
            return False, 'Brak uprawnień do zmiany zamówienia.', None
        mode = payload.get('mode')
        reason = str(payload.get('reason') or '').strip()
        if mode not in ('cancel', 'replace'):
            return False, 'Wybierz anulowanie albo zamianę surowca.', None
        if not reason or len(reason) > 2000:
            return False, 'Podaj powód zmiany (maksymalnie 2000 znaków).', None
        if isinstance(item_index, bool) or not isinstance(item_index, int) or item_index < 0:
            return False, 'Nieprawidłowa pozycja zamówienia.', None
        replacement_name = str(payload.get('replacement_name') or '').strip()
        quantity = None
        if mode == 'replace':
            try:
                quantity = float(str(payload.get('replacement_kg', '')).replace(',', '.'))
            except (ValueError, TypeError):
                return False, 'Podaj ilość nowego surowca w kg.', None
            if not math.isfinite(quantity) or quantity <= 0 or quantity > 999999999:
                return False, 'Ilość nowego surowca musi być dodatnia i skończona.', None
            if not replacement_name:
                return False, 'Wybierz nowy surowiec ze słownika.', None
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute('SELECT id,items,status FROM magazyn_zamowienia WHERE id=%s FOR UPDATE', (order_id,))
            order = cursor.fetchone()
            if not order:
                raise ValueError('Nie znaleziono zamówienia.')
            items = json.loads(order['items']) if isinstance(order['items'], (str, bytes, bytearray)) else order['items']
            if not isinstance(items, list) or item_index >= len(items):
                raise ValueError('Nie znaleziono pozycji zamówienia.')
            item = items[item_index]
            if order['status'] != 'NOWE' or item.get('cancellation'):
                raise ValueError('Pozycja jest już zamknięta lub anulowana. Odśwież listę zamówień.')
            outstanding = remaining_quantity(item)
            if outstanding <= 0.0001:
                raise ValueError('Pozycja została już zrealizowana w całości.')
            new_order_id = None
            now = datetime.now()
            if mode == 'replace':
                if replacement_name.casefold() == str(item.get('surowiec_nazwa') or '').strip().casefold():
                    raise ValueError('Wybierz inny surowiec niż w pierwotnym zamówieniu.')
                cursor.execute('SELECT nazwa FROM slownik_surowcow WHERE LOWER(TRIM(nazwa))=LOWER(%s) LIMIT 1', (replacement_name,))
                material = cursor.fetchone()
                if not material:
                    raise ValueError('Wybrany surowiec nie istnieje w słowniku.')
                replacement = dict(surowiec_nazwa=material['nazwa'], ilosc_kg=quantity,
                    linia=item.get('linia') or 'AGRO', replaces=dict(order_id=order_id, item_index=item_index,
                    material=item.get('surowiec_nazwa'), reason=reason, login=login, at=now.isoformat(timespec='seconds')))
                cursor.execute("INSERT INTO magazyn_zamowienia(items,operator_login,komentarz,status,created_at) VALUES(%s,%s,%s,'NOWE',%s)",
                    (json.dumps([replacement], ensure_ascii=False), login, 'Zamiana pozycji zamówienia #' + str(order_id), now))
                new_order_id = cursor.lastrowid
            item['cancellation'] = dict(reason=reason, login=login, at=now.isoformat(timespec='seconds'),
                cancelled_kg=outstanding, replacement_order_id=new_order_id)
            status = order_status(items)
            cursor.execute('UPDATE magazyn_zamowienia SET items=%s,status=%s,confirmed_at=%s,magazynier_login=%s WHERE id=%s',
                (json.dumps(items, ensure_ascii=False), status, now if status != 'NOWE' else None,
                 login if status != 'NOWE' else None, order_id))
            conn.commit()
            message = ('Niezrealizowana ilość anulowana. Utworzono zamówienie #' + str(new_order_id) + '.'
                       if new_order_id else 'Niezrealizowana ilość anulowana. Historia została zachowana.')
            return True, message, new_order_id
        except ValueError as error:
            conn.rollback()
            return False, str(error), None
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
