# cspell:words sscc
"""Allocate canonical scanned pallets to individual order lines atomically."""
import json
import math

from app.services.magazyn_dostawy.commands.internal_transfer_processor import InternalTransferProcessor


class WarehouseOrderFulfillment:
    @staticmethod
    def requested(item):
        value = float(item.get('brakujace_kg') if item.get('brakujace_kg') is not None else item.get('ilosc_kg') or 0)
        if not math.isfinite(value) or value < 0:
            raise ValueError('Nieprawidłowa ilość zamówienia')
        return value

    @classmethod
    def sync_transfer(cls, cursor, transfer_id, items, linia, login):
        """Synchronize this transfer's allocation without committing the caller's transaction.

        Each physical SSCC is counted once. Removing a pending transfer item
        revokes its contribution; completed historical orders are left intact.
        """
        transfer_id = str(transfer_id)
        active = {str(item.get('id')): item for item in items if not item.get('rejected')}
        cursor.execute('SELECT id,items,status FROM magazyn_zamowienia ORDER BY created_at,id FOR UPDATE')
        orders = cursor.fetchall()
        if not orders:
            return
        states = []
        counted = set()
        for order in orders:
            raw = order.get('items') or []
            order_items = json.loads(raw) if isinstance(raw,str) else raw
            if not isinstance(order_items,list):
                raise ValueError('Nieprawidłowe pozycje zamówienia')
            before = json.dumps(order_items,sort_keys=True)
            for entry in order_items:
                allocations = entry.get('transfer_allocations', [])
                entry['transfer_allocations'] = [allocation for allocation in allocations if
                    allocation['transfer_id'] != transfer_id or (
                        str(allocation['item_id']) in active and allocation['sscc'] == str(
                            active[str(allocation['item_id'])].get('sourcePalletNo') or
                            active[str(allocation['item_id'])].get('nr_palety') or '').strip().upper())]
                counted.update(allocation['sscc'] for allocation in entry['transfer_allocations'])
            states.append((order,order_items,before))

        for item_id,item in active.items():
            number = str(item.get('sourcePalletNo') or item.get('nr_palety') or '').strip().upper()
            if not number or number in counted:
                continue
            # Client-provided names/quantities cannot close orders.
            stock, kind, table = InternalTransferProcessor._find_active_pallet_by_sscc(cursor,number,linia)
            if not stock or kind != 'surowiec':
                continue
            cursor.execute(f'SELECT * FROM {table} WHERE id=%s AND UPPER(nr_palety)=%s FOR UPDATE',
                           (stock['id'],number))
            physical = cursor.fetchone()
            if not physical:
                raise ValueError('Zeskanowana paleta nie jest dostępna')
            from app.services.magazyn_dostawy.commands.pallet_lock_manager import PalletLockManager
            if PalletLockManager.has_quality_or_manual_block(cursor,number):
                raise ValueError('Paleta posiada blokadę LAB lub ręczną')
            available = float(physical.get('stan_magazynowy') or 0)
            if not math.isfinite(available) or available <= 0:
                raise ValueError('Zeskanowana paleta ma nieprawidłowy stan')
            submitted = float(item.get('netWeight') or item.get('quantity') or available)
            if not math.isfinite(submitted) or abs(submitted-available) > 0.001:
                raise ValueError('Ilość transferu musi odpowiadać palecie; dla części ilości najpierw podziel paletę')
            target_line = str(linia or 'AGRO').upper()
            if target_line == 'ALL':
                target_line = str(physical.get('linia') or 'AGRO').upper()
            material = str(physical.get('nazwa') or '').strip().casefold()
            for order,entries,_ in states:
                # Old manually closed orders are history, not pending requests.
                if order['status'] == 'ZAMKNIETE' and not any(entry.get('transfer_allocations') for entry in entries):
                    continue
                for entry in entries:
                    if str(entry.get('linia') or 'AGRO').upper() != target_line or str(
                            entry.get('surowiec_nazwa') or '').strip().casefold() != material:
                        continue
                    requested = cls.requested(entry)
                    assigned = sum(float(allocation['kg']) for allocation in entry['transfer_allocations'])
                    quantity = min(available,max(0,requested-assigned))
                    if quantity <= 0:
                        continue
                    entry['transfer_allocations'].append(dict(transfer_id=transfer_id,item_id=item_id,
                                                             sscc=number,kg=quantity))
                    available -= quantity
                    counted.add(number)
                    if available <= 0:
                        break
                if available <= 0:
                    break

        for order,entries,before in states:
            # Adding empty allocation metadata alone is not a state transition.
            for entry in entries:
                if not entry.get('transfer_allocations'):
                    entry.pop('transfer_allocations',None)
            if json.dumps(entries,sort_keys=True) == before:
                continue
            requested_entries = [entry for entry in entries if cls.requested(entry) > 0]
            complete = bool(requested_entries) and all(sum(float(allocation['kg']) for allocation in
                entry.get('transfer_allocations',[])) >= cls.requested(entry)-0.0001 for entry in requested_entries)
            cursor.execute('UPDATE magazyn_zamowienia SET items=%s,status=%s,magazynier_login=%s, '
                           'confirmed_at=IF(%s,NOW(),NULL) WHERE id=%s',
                           (json.dumps(entries,ensure_ascii=False),'ZAMKNIETE' if complete else 'NOWE',
                            login if complete else None,complete,order['id']))
