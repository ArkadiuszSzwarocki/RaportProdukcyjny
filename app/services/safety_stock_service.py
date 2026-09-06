from typing import List, Dict, Any, Optional
from app.repositories.safety_stock_repository import SafetyStockRepository

class SafetyStockService:
    """
    Domain service for managing Safety Stocks (Stany Minimalne) and Reorder Points (Punkt Zamówienia).
    Identifies shortages, generates procurement recommendations, and flags critical materials.
    """

    @staticmethod
    def configure_threshold(
        kod_pozycji: str,
        nazwa: str,
        typ: str = 'surowiec',
        linia: str = 'PSD',
        stan_minimalny: float = 0.0,
        punkt_zamowienia: float = 0.0,
        jednostka: str = 'kg',
        czas_dostawy_dni: int = 7
    ) -> Dict[str, Any]:
        """Sets safety stock and reorder point parameters."""
        SafetyStockRepository.upsert_safety_threshold(
            kod_pozycji=kod_pozycji,
            nazwa=nazwa,
            typ=typ,
            linia=linia,
            stan_minimalny=stan_minimalny,
            punkt_zamowienia=punkt_zamowienia,
            jednostka=jednostka,
            czas_dostawy_dni=czas_dostawy_dni
        )
        return {
            "success": True,
            "message": f"Zapisano parametry bezpieczeństwa dla {nazwa} ({linia})."
        }

    @staticmethod
    def evaluate_safety_stock_levels(linia: Optional[str] = None) -> Dict[str, Any]:
        """
        Evaluates current warehouse inventory against safety stock and reorder points.
        Returns classified summary: CRITICAL, REORDER_NEEDED, SAFE.
        """
        thresholds = SafetyStockRepository.get_configured_thresholds(linia)
        items_evaluated = []
        critical_count = 0
        reorder_count = 0

        for t in thresholds:
            nazwa = t.get('nazwa', '')
            typ = t.get('typ', 'surowiec')
            item_line = t.get('linia', 'PSD')
            min_stock = float(t.get('stan_minimalny', 0.0))
            reorder_point = float(t.get('punkt_zamowienia', 0.0))

            actual_stock = SafetyStockRepository.get_actual_stock_for_material(nazwa, typ, item_line)

            status = 'BEZPIECZNY'
            deficit_kg = 0.0

            if actual_stock <= min_stock:
                status = 'KRYTYCZNY'
                critical_count += 1
                deficit_kg = round(reorder_point - actual_stock, 2)
            elif actual_stock <= reorder_point:
                status = 'WYMAGA_ZAMOWIENIA'
                reorder_count += 1
                deficit_kg = round(reorder_point - actual_stock, 2)

            items_evaluated.append({
                "id": t.get('id'),
                "kod_pozycji": t.get('kod_pozycji'),
                "nazwa": nazwa,
                "typ": typ,
                "linia": item_line,
                "stan_aktualny": round(actual_stock, 2),
                "stan_minimalny": min_stock,
                "punkt_zamowienia": reorder_point,
                "deficyt": max(0.0, deficit_kg),
                "jednostka": t.get('jednostka', 'kg'),
                "czas_dostawy_dni": t.get('czas_dostawy_dni', 7),
                "status": status
            })

        return {
            "total_items": len(items_evaluated),
            "critical_count": critical_count,
            "reorder_count": reorder_count,
            "has_alerts": (critical_count + reorder_count) > 0,
            "items": items_evaluated
        }
