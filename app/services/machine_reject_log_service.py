import json
import os
import threading
import time
from typing import Dict, Any, List, Optional
from app.dto.service_result import ServiceResult

class MachineRejectLogService:
    """
    Domain service for logging checkweigher dynamic scale measurements,
    reject drop flap activations, and root-cause fault reasons (underweight, overweight, metal detected, etc.).
    """

    _LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.machine_reject_logs.json')
    _LOCK = threading.Lock()
    _MAX_LOGS = 500

    @classmethod
    def _load_logs(cls) -> List[Dict[str, Any]]:
        if os.path.exists(cls._LOG_FILE):
            try:
                with open(cls._LOG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    @classmethod
    def _save_logs(cls, logs: List[Dict[str, Any]]) -> None:
        try:
            with open(cls._LOG_FILE, 'w', encoding='utf-8') as f:
                json.dump(logs[:cls._MAX_LOGS], f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    @classmethod
    def log_reject(
        cls,
        weight_kg: float,
        target_weight_kg: float = 25.0,
        reason_code: str = "UNDERWEIGHT",
        reason_label: Optional[str] = None,
        recipe_name: str = "Brak danych",
        operator: Optional[str] = None,
        raw_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Records a checkweigher rejection event when the drop flap opens.
        Reasons: UNDERWEIGHT, OVERWEIGHT, METAL_DETECTED, BAG_BURST, MANUAL_REJECT
        """
        now = time.time()
        
        # Determine standard label if not provided
        if not reason_label:
            labels_map = {
                "UNDERWEIGHT": "Niedowaga worka (< min tolerancji)",
                "OVERWEIGHT": "Nadwaga worka (> max tolerancji)",
                "METAL_DETECTED": "Wykrycie metalu (Detektor metali)",
                "BAG_BURST": "Błąd geometrii / Rozszczelnienie worka",
                "MANUAL_REJECT": "Ręczne otwarcie klapy zrzutu przez operatora"
            }
            reason_label = labels_map.get(reason_code.upper(), f"Błąd wagi: {reason_code}")

        deviation_kg = round(weight_kg - target_weight_kg, 3)

        entry = {
            "id": f"rej_{int(now * 1000)}",
            "timestamp": now,
            "timestamp_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
            "weight_kg": round(float(weight_kg), 2),
            "target_weight_kg": round(float(target_weight_kg), 2),
            "deviation_kg": deviation_kg,
            "reason_code": reason_code.upper(),
            "reason_label": reason_label,
            "recipe_name": recipe_name or "Standard 25kg",
            "operator": operator or "Automatyczny zrzut PLC",
            "raw_data": raw_data or {}
        }

        with cls._LOCK:
            logs = cls._load_logs()
            # Prevent duplicate rapid logging within 3 seconds
            if logs:
                last = logs[0]
                if (
                    abs(last.get("weight_kg", 0) - entry["weight_kg"]) < 0.05 and
                    last.get("reason_code") == entry["reason_code"] and
                    (now - last.get("timestamp", 0)) < 3.0
                ):
                    return last

            logs.insert(0, entry)
            cls._save_logs(logs)

        # Also log to central machine error journal for unified alarming
        try:
            from app.services.machine_error_log_service import MachineErrorLogService
            MachineErrorLogService.log_error(
                machine="WAGA_ZRZUT",
                description=f"Odrzut worka: {reason_label} | Waga: {entry['weight_kg']} kg (zadana: {entry['target_weight_kg']} kg)",
                severity="WARNING",
                code=f"REJ-{reason_code.upper()[:4]}",
                raw_data=entry
            )
        except Exception:
            pass

        return entry

    @classmethod
    def get_rejects(
        cls,
        limit: int = 50,
        reason_code: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieves history of reject drop flap activations."""
        with cls._LOCK:
            logs = cls._load_logs()

        filtered = []
        for r in logs:
            if reason_code and reason_code.upper() != "ALL" and r.get("reason_code") != reason_code.upper():
                continue
            filtered.append(r)
            if len(filtered) >= limit:
                break

        return filtered

    @classmethod
    def get_reject_statistics(cls) -> Dict[str, Any]:
        """Calculates aggregated counts and reason breakdown."""
        with cls._LOCK:
            logs = cls._load_logs()

        total = len(logs)
        by_reason = {
            "UNDERWEIGHT": 0,
            "OVERWEIGHT": 0,
            "METAL_DETECTED": 0,
            "BAG_BURST": 0,
            "MANUAL_REJECT": 0,
            "OTHER": 0
        }

        today_start = time.mktime(time.strptime(time.strftime("%Y-%m-%d 00:00:00"), "%Y-%m-%d %H:%M:%S"))
        today_count = 0

        for r in logs:
            code = r.get("reason_code", "OTHER").upper()
            if code in by_reason:
                by_reason[code] += 1
            else:
                by_reason["OTHER"] += 1

            if r.get("timestamp", 0) >= today_start:
                today_count += 1

        return {
            "total_rejects": total,
            "today_rejects": today_count,
            "by_reason": by_reason,
            "recent_rejects": logs[:10]
        }

    @classmethod
    def clear_logs(cls) -> ServiceResult:
        """Clears all reject history."""
        with cls._LOCK:
            cls._save_logs([])
        return ServiceResult.ok(message="Historia zrzutów wagi została wyczyszczona.")
