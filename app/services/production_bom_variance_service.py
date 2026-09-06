from typing import Dict, Any, List, Optional
from app.repositories.production_bom_variance_repository import ProductionBomVarianceRepository

class ProductionBomVarianceService:
    """
    Service responsible for verifying recipe ingredient dosing, calculating BOM variances,
    enforcing tolerance thresholds, and generating variance balance summaries.
    """

    DEFAULT_TOLERANCE_PERCENT = 2.0  # Default +/- 2.0% tolerance for bulk materials
    MICRO_TOLERANCE_PERCENT = 1.0    # Tighter +/- 1.0% tolerance for micro-ingredients and premixes

    @staticmethod
    def calculate_and_record_variance(
        plan_id: int,
        linia: str,
        kod_produktu: str,
        skladnik: str,
        waga_recepturowa: float,
        waga_rzeczywista: float,
        tolerancja_procent: Optional[float] = None,
        is_micro_ingredient: bool = False,
        user_login: str = 'system',
        conn=None
    ) -> Dict[str, Any]:
        """
        Calculates the exact deviation and logs the result.
        Returns a dictionary with variance metrics and tolerance status.
        """
        waga_rec = float(waga_recepturowa or 0.0)
        waga_act = float(waga_rzeczywista or 0.0)

        if tolerancja_procent is None:
            tolerancja_procent = (
                ProductionBomVarianceService.MICRO_TOLERANCE_PERCENT 
                if is_micro_ingredient 
                else ProductionBomVarianceService.DEFAULT_TOLERANCE_PERCENT
            )

        odchylka_kg = round(waga_act - waga_rec, 3)
        if waga_rec > 0:
            odchylka_procent = round((odchylka_kg / waga_rec) * 100.0, 2)
        else:
            odchylka_procent = 0.0

        is_exceeded = abs(odchylka_procent) > float(tolerancja_procent)

        record_id = ProductionBomVarianceRepository.record_variance(
            plan_id=plan_id,
            linia=linia,
            kod_produktu=kod_produktu,
            skladnik=skladnik,
            waga_recepturowa=waga_rec,
            waga_rzeczywista=waga_act,
            odchylka_kg=odchylka_kg,
            odchylka_procent=odchylka_procent,
            tolerancja_procent=float(tolerancja_procent),
            is_exceeded=is_exceeded,
            user_login=user_login,
            conn=conn
        )

        return {
            "id": record_id,
            "plan_id": plan_id,
            "skladnik": skladnik,
            "waga_recepturowa": waga_rec,
            "waga_rzeczywista": waga_act,
            "odchylka_kg": odchylka_kg,
            "odchylka_procent": odchylka_procent,
            "tolerancja_procent": tolerancja_procent,
            "is_exceeded": is_exceeded
        }

    @staticmethod
    def get_plan_variance_summary(plan_id: int, linia: str = 'PSD') -> Dict[str, Any]:
        """
        Compiles a comprehensive BOM variance summary for a given production order.
        """
        variances = ProductionBomVarianceRepository.get_variances_by_plan(plan_id, linia)
        total_planned_weight = sum(v.get('waga_recepturowa', 0.0) for v in variances)
        total_actual_weight = sum(v.get('waga_rzeczywista', 0.0) for v in variances)
        total_delta_kg = round(total_actual_weight - total_planned_weight, 3)

        exceeded_count = sum(1 for v in variances if v.get('is_exceeded'))

        return {
            "plan_id": plan_id,
            "linia": linia.upper(),
            "total_items": len(variances),
            "total_planned_weight_kg": round(total_planned_weight, 3),
            "total_actual_weight_kg": round(total_actual_weight, 3),
            "total_delta_kg": total_delta_kg,
            "has_exceeded_tolerances": exceeded_count > 0,
            "exceeded_items_count": exceeded_count,
            "items": variances
        }
