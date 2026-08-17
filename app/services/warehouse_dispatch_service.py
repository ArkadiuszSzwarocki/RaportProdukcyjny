"""
Serwis obsługi wydań zewnętrznych na samochód (Załadunki ZZA/ZZL).

Odpowiedzialność: Logika biznesowa walidacji i wykonywania wyjazdów ciężarówek/pojazdów dostawczych.
"""

from app.repositories.warehouse_dispatch_repository import WarehouseDispatchRepository


class WarehouseDispatchService:
    """Serwis obsługi załadunków samochodowych."""

    def __init__(self):
        self._repository = WarehouseDispatchRepository()

    def get_available_pallets(self):
        """Pobiera listę dostępnych palet w magazynie do załadunku.

        Returns:
            list[dict]: Lista dostępnych palet.
        """
        return self._repository.get_available_pallets()

    def get_dispatches_history(self, limit=50):
        """Pobiera historię wydań zewnętrznych na samochód.

        Args:
            limit (int): Maksymalna liczba rekordów.

        Returns:
            list[dict]: Lista zrealizowanych załadunków.
        """
        dispatches = self._repository.get_recent_dispatches(limit=limit)
        for item in dispatches:
            if item.get('created_at'):
                item['created_at'] = item['created_at'].strftime('%Y-%m-%d %H:%M:%S')
        return dispatches

    def dispatch_pallet_to_vehicle(self, payload, magazynier_login):
        """Wykonuje wydanie zewnętrzne palety na samochód.

        Args:
            payload (dict): Dane załadunku (nr_palety, nazwa_produktu, typ_palety, ilosc_kg,
                            nr_rejestracyjny, kierowca, odbiorca, nr_dokumentu_wz, uwagi).
            magazynier_login (str): Login magazyniera.

        Returns:
            tuple[bool, str]: (sukces, komunikat).
        """
        nr_palety = payload.get('nr_palety')
        nazwa_produktu = payload.get('nazwa_produktu')

        if not nr_palety or not str(nr_palety).strip():
            return False, "Wymagany jest numer palety do załadunku."

        if not nazwa_produktu or not str(nazwa_produktu).strip():
            return False, "Wymagana jest nazwa produktu."

        data = {
            'nr_palety': str(nr_palety).strip(),
            'nazwa_produktu': str(nazwa_produktu).strip(),
            'typ_palety': payload.get('typ_palety', 'Surowiec'),
            'ilosc_kg': float(payload.get('ilosc_kg', 0.0) or 0.0),
            'nr_rejestracyjny': payload.get('nr_rejestracyjny', '').strip() or None,
            'kierowca': payload.get('kierowca', '').strip() or None,
            'odbiorca': payload.get('odbiorca', '').strip() or None,
            'nr_dokumentu_wz': payload.get('nr_dokumentu_wz', '').strip() or None,
            'uwagi': payload.get('uwagi', '').strip() or None,
            'magazynier': magazynier_login
        }

        dispatch_id = self._repository.create_dispatch(data)
        if dispatch_id:
            return True, f"Załadunek na samochód palety {nr_palety} został zarejestrowany (ID #{dispatch_id})."
        return False, "Błąd podczas rejestracji załadunku na samochód."
