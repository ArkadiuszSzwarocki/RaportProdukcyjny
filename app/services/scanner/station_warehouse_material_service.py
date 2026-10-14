"""Service coordinating retrieval and aggregation of available warehouse pallets for production stations."""
from __future__ import annotations

from typing import List, Dict, Any, Optional
from app.repositories.station_warehouse_material_repository import StationWarehouseMaterialRepository
from app.utils.location_validator import normalize_production_tank_code, is_production_tank_code


class StationWarehouseMaterialService:
    """Business service resolving the assigned raw material of a station and its warehouse pallet stock."""

    @classmethod
    def get_available_warehouse_materials_for_station(
        cls,
        station_code: str,
        active_materials: Optional[List[str]] = None,
        linia: str = "AGRO"
    ) -> Dict[str, Any]:
        """Resolve the currently assigned material for the station and list ONLY pallets of this material in warehouse."""
        norm_code = normalize_production_tank_code(station_code) or str(station_code or "").strip().upper()

        if not norm_code or not is_production_tank_code(norm_code):
            return {
                "is_production_station": False,
                "station_code": norm_code,
                "assigned_material": None,
                "target_material": "",
                "total_pallets": 0,
                "total_weight": 0.0,
                "pallets": []
            }

        # 1. Fetch active production snapshot (identical to "Surowce w Produkcji" screen)
        assigned_name = ""
        stan_stacji = 0.0
        sscc = ""
        data_wstawienia = ""
        plan_name = ""
        surowiec_id = None
        ruch_id = None
        plan_id = None
        has_assignment = False

        try:
            from app.services.agro.agro_tanks_service import AgroTanksService
            snapshot = AgroTanksService.get_production_inventory_snapshot(linia=linia, show_empty=False)
            for item in snapshot:
                tank = normalize_production_tank_code(item.get("zbiornik"))
                if tank == norm_code and float(item.get("stan_systemowy") or 0) > 0:
                    assigned_name = str(item.get("surowiec_nazwa") or item.get("nazwa") or "").strip()
                    stan_stacji = float(item.get("stan_systemowy") or 0.0)
                    sscc = item.get("nr_palety") or ""
                    data_wstawienia = item.get("data") or ""
                    plan_name = item.get("plan_nazwa") or item.get("plan_name") or ""
                    surowiec_id = item.get("surowiec_id")
                    ruch_id = item.get("ruch_id")
                    plan_id = item.get("plan_id")
                    has_assignment = True
                    break
        except Exception:
            pass

        # 2. Fallback to configured rule if not active in production snapshot
        if not assigned_name:
            try:
                from app.repositories.tank_validation_repository import TankValidationRepository
                rule = TankValidationRepository.get_rule_by_tank(norm_code)
                if rule and rule.is_active and rule.nazwa_surowca:
                    assigned_name = rule.nazwa_surowca.strip()
                    surowiec_id = rule.surowiec_id
                    has_assignment = True
            except Exception:
                pass

        # 3. Fallback to active_materials passed from query if still missing
        if not assigned_name and active_materials:
            for m in active_materials:
                if m and str(m).strip():
                    assigned_name = str(m).strip()
                    has_assignment = True
                    break

        assigned_info = {
            "name": assigned_name or "Brak przypisanego surowca",
            "stan_stacji": stan_stacji,
            "sscc": sscc,
            "wstawiono": data_wstawienia,
            "plan": plan_name,
            "surowiec_id": surowiec_id,
            "ruch_id": ruch_id,
            "plan_id": plan_id,
            "has_active_assignment": bool(has_assignment and assigned_name)
        }

        # 4. If an assigned material is found, query available pallets matching ONLY this material
        pallets: List[Dict[str, Any]] = []
        total_weight = 0.0

        if assigned_name:
            pallets = StationWarehouseMaterialRepository.find_available_pallets_for_assigned_material(
                material_name=assigned_name,
                linia=linia,
                exclude_location=norm_code
            )
            total_weight = sum(float(p.get("stan_magazynowy") or 0.0) for p in pallets)

        return {
            "is_production_station": True,
            "station_code": norm_code,
            "assigned_material": assigned_info,
            "target_material": assigned_name,
            "total_pallets": len(pallets),
            "total_weight": round(total_weight, 2),
            "pallets": pallets
        }
