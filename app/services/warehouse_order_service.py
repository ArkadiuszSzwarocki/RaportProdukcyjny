"""
Serwis zamówień magazynowych.

Odpowiedzialność: Logika biznesowa zamówień surowców z magazynu.
Walidacja danych, orkiestracja operacji.
"""
import json
from app.repositories.warehouse_order_repository import WarehouseOrderRepository
from app.utils.surowiec_validator import validate_surowiec_name


class WarehouseOrderService:
    """Logika biznesowa zamówień magazynowych."""

    def __init__(self):
        self._repository = WarehouseOrderRepository()

    def create_order(self, items, operator_login, komentarz=None):
        """Tworzy nowe zamówienie na surowce.

        Args:
            items: Lista słowników (surowiec_nazwa, ilosc_kg).
            operator_login: Login operatora.
            komentarz: Opcjonalny komentarz.

        Returns:
            tuple[bool, str, int | None]: (sukces, komunikat, id_zamówienia).
        """
        validation_error = self._validate_order_data(items)
        if validation_error:
            return False, validation_error, None

        cleaned_items = []
        for item in items:
            nazwa = item['surowiec_nazwa'].strip()
            is_valid, error = validate_surowiec_name(nazwa)
            if not is_valid:
                return False, error, None
            cleaned_items.append({
                'surowiec_nazwa': nazwa,
                'ilosc_kg': float(item['ilosc_kg'])
            })

        order_id = self._repository.create(
            items=cleaned_items,
            operator_login=operator_login,
            komentarz=komentarz.strip() if komentarz else None
        )
        return True, f"Zamówienie #{order_id} utworzone pomyślnie.", order_id

    def get_all_orders(self, status_filter=None):
        """Pobiera listę zamówień.

        Args:
            status_filter: Opcjonalny filtr statusu ('NOWE', 'ZAMKNIETE').

        Returns:
            list[dict]: Lista zamówień.
        """
        valid_statuses = ('NOWE', 'ZAMKNIETE')
        if status_filter and status_filter.upper() not in valid_statuses:
            status_filter = None

        orders = self._repository.get_all(
            status_filter=status_filter.upper() if status_filter else None
        )

        for order in orders:
            self._format_order_dates(order)
            if 'items' in order and isinstance(order['items'], (str, bytes, bytearray)):
                try:
                    order['items'] = json.loads(order['items'])
                except Exception:
                    order['items'] = []

        return orders

    def confirm_order(self, order_id, magazynier_login):
        """Potwierdza odczytanie zamówienia przez magazyniera.

        Args:
            order_id: ID zamówienia.
            magazynier_login: Login magazyniera.

        Returns:
            tuple[bool, str]: (sukces, komunikat).
        """
        order = self._repository.get_by_id(order_id)
        if not order:
            return False, "Zamówienie nie zostało znalezione."

        if order['status'] == 'ZAMKNIETE':
            return False, "Zamówienie jest już zamknięte."

        rows_updated = self._repository.confirm(order_id, magazynier_login)
        if rows_updated == 0:
            return False, "Nie udało się potwierdzić zamówienia."

        return True, f"Zamówienie #{order_id} potwierdzone i zamknięte."

    def delete_order(self, order_id, user_role):
        """Usuwa zamówienie z magazynu (uprawnienia dla masteradmin, admin, zarzad).

        Args:
            order_id: ID zamówienia.
            user_role: Rola użytkownika.

        Returns:
            tuple[bool, str]: (sukces, komunikat).
        """
        role_norm = str(user_role or '').lower().replace(' ', '').replace('_', '').strip()
        if role_norm not in ['masteradmin', 'admin', 'administrator', 'zarzad', 'zarząd']:
            return False, "Brak uprawnień. Usuwanie dostępne tylko dla ról: MasterAdmin, Admin oraz Zarząd."

        order = self._repository.get_by_id(order_id)
        if not order:
            return False, "Zamówienie nie istnieje lub zostało już usunięte."

        rows = self._repository.delete(order_id)
        if rows == 0:
            return False, "Nie udało się usunąć zamówienia."

        return True, f"Zamówienie #{order_id} zostało trwale usunięte."

    def get_available_surowce(self):
        """Pobiera listę surowców ze słownika.

        Returns:
            list[dict]: Lista surowców (id, nazwa).
        """
        return self._repository.get_available_surowce()

    @staticmethod
    def _validate_order_data(items):
        """Waliduje listę elementów zamówienia.

        Returns:
            str | None: Komunikat błędu lub None jeśli dane poprawne.
        """
        if not items or not isinstance(items, list):
            return "Zamówienie musi zawierać co najmniej jeden surowiec."

        for item in items:
            nazwa = item.get('surowiec_nazwa')
            if not nazwa or not str(nazwa).strip():
                return "Każda pozycja musi mieć wybraną nazwę surowca."
            
            try:
                ilosc = float(item.get('ilosc_kg', 0))
                if ilosc <= 0:
                    return f"Ilość dla surowca {nazwa} musi być większa od zera."
            except (TypeError, ValueError):
                return f"Ilość dla surowca {nazwa} musi być prawidłową liczbą."

        return None

    @staticmethod
    def _format_order_dates(order):
        """Formatuje daty zamówienia do stringów dla JSON.

        Args:
            order: Słownik zamówienia (modyfikowany in-place).
        """
        if order.get('created_at'):
            order['created_at'] = order['created_at'].strftime('%Y-%m-%d %H:%M:%S')
        if order.get('confirmed_at'):
            order['confirmed_at'] = order['confirmed_at'].strftime('%Y-%m-%d %H:%M:%S')

    def calculate_and_check_stock(self, items, order_tons, linia='AGRO'):
        """Oblicza zapotrzebowanie surowców i weryfikuje ich stany w magazynie.

        Waliduje unikalność surowców (brak duplikatów w recepturze), przypisuje kolejność FIFO
        oraz wyodrębnia palety aktywne i zablokowane.

        Args:
            items: Lista słowników (surowiec_nazwa, przelicznik_na_1t).
            order_tons: Całkowita wielkość zlecenia w tonach.
            linia: Linia ('AGRO' lub 'PSD') dla sprawdzenia magazynu.

        Returns:
            tuple[bool, str, dict]: (sukces, błąd/komunikat, payload z wynikami i strefami).
        """
        try:
            tons = float(order_tons)
            if tons <= 0:
                return False, "Wielkość zlecenia musi być większa od zera.", {}
        except (ValueError, TypeError):
            return False, "Wielkość zlecenia musi być poprawną liczbą.", {}

        if not items or not isinstance(items, list):
            return False, "Brak surowców do sprawdzenia.", {}

        surowce_names = []
        seen_names = set()

        for item in items:
            nazwa = str(item.get('surowiec_nazwa') or '').strip()
            if not nazwa:
                return False, "Każda pozycja musi mieć wybraną nazwę surowca.", {}
            
            nazwa_lower = nazwa.lower()
            if nazwa_lower in seen_names:
                return False, f"Błąd: Surowiec '{nazwa}' został podany więcej niż raz w kalkulatorze. Usuń duplikat lub połącz przelicznik.", {}
            seen_names.add(nazwa_lower)

            try:
                rate = float(item.get('przelicznik_na_1t', 0))
                if rate <= 0:
                    return False, f"Przelicznik dla {nazwa} musi być większy od 0.", {}
            except (ValueError, TypeError):
                return False, f"Przelicznik dla {nazwa} musi być poprawną liczbą.", {}

            is_valid, error = validate_surowiec_name(nazwa)
            if not is_valid:
                return False, error, {}

            surowce_names.append(nazwa)

        check_res = self._repository.check_stock(surowce_names, linia)
        stock_dict = check_res.get('stock_data', {})
        scanned_zones = check_res.get('scanned_zones', [])
        
        results = []
        for item in items:
            nazwa = str(item['surowiec_nazwa']).strip()
            rate = float(item['przelicznik_na_1t'])
            needed_kg = tons * rate
            
            stock_info = stock_dict.get(nazwa, {
                'stan_magazynowy_kg': 0.0,
                'zablokowane_kg': 0.0,
                'lokalizacje': [],
                'palety_fifo': []
            })

            in_stock_kg = stock_info.get('stan_magazynowy_kg', 0.0)
            blocked_kg = stock_info.get('zablokowane_kg', 0.0)
            missing_kg = needed_kg - in_stock_kg
            if missing_kg < 0:
                missing_kg = 0.0

            raw_fifo = stock_info.get('palety_fifo', [])
            active_fifo = [p for p in raw_fifo if not p.get('is_blocked')]
            blocked_fifo = [p for p in raw_fifo if p.get('is_blocked')]

            # Dobieraj palety FIFO tylko do pokrycia zapotrzebowania (needed_kg)
            allocated_pallets = []
            accumulated_kg = 0.0
            for p in active_fifo:
                allocated_pallets.append(p)
                accumulated_kg += float(p.get('stan_magazynowy', 0))
                if accumulated_kg >= needed_kg:
                    break

            # Informacyjnie dodaj powiązane zablokowane palety jeśli brakuje surowca
            if accumulated_kg < needed_kg and blocked_fifo:
                allocated_pallets.extend(blocked_fifo)

            results.append({
                'surowiec_nazwa': nazwa,
                'przelicznik_na_1t': rate,
                'potrzebne_kg': round(needed_kg, 2),
                'stan_magazynowy_kg': round(in_stock_kg, 2),
                'zablokowane_kg': round(blocked_kg, 2),
                'brakujace_kg': round(missing_kg, 2),
                'pokryte_kg': round(accumulated_kg, 2),
                'lokalizacje': stock_info.get('lokalizacje', []),
                'palety_fifo': allocated_pallets,
                'wszystkie_palety_count': len(raw_fifo)
            })

        payload = {
            'order_tons': tons,
            'items': results,
            'scanned_zones': scanned_zones
        }

        return True, "Zapotrzebowanie przeliczone.", payload
