"""
Serwis zamówień magazynowych.

Odpowiedzialność: Logika biznesowa zamówień surowców z magazynu.
Walidacja danych, orkiestracja operacji.
"""
import json
from app.repositories.warehouse_order_repository import WarehouseOrderRepository


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
            cleaned_items.append({
                'surowiec_nazwa': item['surowiec_nazwa'].strip(),
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

        Args:
            items: Lista słowników (surowiec_nazwa, przelicznik_na_1t).
            order_tons: Całkowita wielkość zlecenia w tonach.
            linia: Linia ('AGRO' lub 'PSD') dla sprawdzenia magazynu.

        Returns:
            tuple[bool, str, list[dict]]: (sukces, błąd/komunikat, wyniki).
        """
        try:
            tons = float(order_tons)
            if tons <= 0:
                return False, "Wielkość zlecenia musi być większa od zera.", []
        except (ValueError, TypeError):
            return False, "Wielkość zlecenia musi być poprawną liczbą.", []

        if not items or not isinstance(items, list):
            return False, "Brak surowców do sprawdzenia.", []

        surowce_names = []
        for item in items:
            nazwa = item.get('surowiec_nazwa')
            if not nazwa or not str(nazwa).strip():
                return False, "Każda pozycja musi mieć wybraną nazwę surowca.", []
            try:
                rate = float(item.get('przelicznik_na_1t', 0))
                if rate <= 0:
                    return False, f"Przelicznik dla {nazwa} musi być większy od 0.", []
            except (ValueError, TypeError):
                return False, f"Przelicznik dla {nazwa} musi być poprawną liczbą.", []
                
            surowce_names.append(str(nazwa).strip())

        stock_dict = self._repository.check_stock(surowce_names, linia)
        
        results = []
        for item in items:
            nazwa = str(item['surowiec_nazwa']).strip()
            rate = float(item['przelicznik_na_1t'])
            needed_kg = tons * rate
            in_stock_kg = stock_dict.get(nazwa, 0.0)
            missing_kg = needed_kg - in_stock_kg
            if missing_kg < 0:
                missing_kg = 0.0
                
            results.append({
                'surowiec_nazwa': nazwa,
                'przelicznik_na_1t': rate,
                'potrzebne_kg': round(needed_kg, 2),
                'stan_magazynowy_kg': round(in_stock_kg, 2),
                'brakujace_kg': round(missing_kg, 2)
            })

        return True, "Zapotrzebowanie przeliczone.", results
