import json
import os
import threading
import time
from typing import Dict, Any, List, Optional
from app.dto.service_result import ServiceResult

class MachineErrorLogService:
    """
    Domain service for persisting and retrieving machine alarms, PLC errors,
    and MQTT communication faults for Wagopakowaczka, Paletyzator, Owijarka, and Broker.
    """

    _LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.machine_error_logs.json')
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
    def _save_logs(cls, logs: List[Dict[str, Any]]):
        try:
            with open(cls._LOG_FILE, 'w', encoding='utf-8') as f:
                json.dump(logs[:cls._MAX_LOGS], f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    @classmethod
    def log_error(
        cls,
        machine: str,
        description: str,
        severity: str = "WARNING",
        code: Optional[str] = None,
        raw_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Records a new machine error or alarm event.
        Severity: 'CRITICAL', 'WARNING', 'COMMUNICATION', 'INFO'
        """
        now = time.time()
        entry = {
            "id": f"err_{int(now * 1000)}",
            "timestamp": now,
            "timestamp_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
            "machine": machine.upper(),
            "severity": severity.upper(),
            "code": code or "ERR-SYS",
            "description": description,
            "raw_data": raw_data or {}
        }

        with cls._LOCK:
            logs = cls._load_logs()
            # Avoid recording duplicate consecutive identical errors within 15 seconds
            if logs:
                last = logs[0]
                if (
                    last.get("machine") == entry["machine"] and
                    last.get("description") == entry["description"] and
                    (now - last.get("timestamp", 0)) < 15
                ):
                    return last

            logs.insert(0, entry)
            cls._save_logs(logs)

        return entry

    @classmethod
    def get_errors(
        cls,
        machine: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Retrieves filtered list of error logs."""
        with cls._LOCK:
            logs = cls._load_logs()

        filtered = []
        for e in logs:
            if machine and machine.upper() != "ALL" and e.get("machine") != machine.upper():
                continue
            if severity and severity.upper() != "ALL" and e.get("severity") != severity.upper():
                continue
            filtered.append(e)
            if len(filtered) >= limit:
                break

        return filtered

    @classmethod
    def clear_logs(cls) -> ServiceResult:
        """Clears all historical error logs."""
        with cls._LOCK:
            cls._save_logs([])
        return ServiceResult.ok(message="Historia błędów maszyn została pomyślnie wyczyszczona.")

    @classmethod
    def parse_and_record_payload(cls, topic: str, payload_data: Dict[str, Any]):
        """Inspects incoming MQTT payload for any alarms, error codes, or status faults."""
        if not isinstance(payload_data, dict):
            return

        # 1. Wagopakowaczka
        if "agroPakowaczka" in topic:
            alarm_val = payload_data.get("alarm") or payload_data.get("blad")
            kod = payload_data.get("kodBledu") or payload_data.get("error_code")
            if alarm_val:
                cls.log_error(
                    machine="WAGOPAKOWACZKA",
                    severity="CRITICAL",
                    code=str(kod or "ALM-BAG"),
                    description=f"Alarm wagi/pakowaczki: {alarm_val}",
                    raw_data=payload_data
                )
            status_val = payload_data.get("status")
            if status_val in ("AWARIA", "BLAD", "ERROR", 99):
                cls.log_error(
                    machine="WAGOPAKOWACZKA",
                    severity="CRITICAL",
                    code="STAT-ERR",
                    description=f"Stan awarii wagopakowaczki (Status: {status_val})",
                    raw_data=payload_data
                )

        # 2. Paletyzator
        elif "agroPaletyzator" in topic:
            alarm_val = payload_data.get("alarm") or payload_data.get("blad")
            kod = payload_data.get("kodBledu") or payload_data.get("error_code")
            if alarm_val:
                cls.log_error(
                    machine="PALETYZATOR",
                    severity="CRITICAL",
                    code=str(kod or "ALM-PAL"),
                    description=f"Alarm robota paletyzatora: {alarm_val}",
                    raw_data=payload_data
                )

        # 3. Owijarka
        elif "agroOwijarka" in topic:
            alarm_val = payload_data.get("alarm") or payload_data.get("blad") or payload_data.get("brakFoli")
            if alarm_val:
                cls.log_error(
                    machine="OWIJARKA",
                    severity="WARNING",
                    code="ALM-WRAPP",
                    description=f"Alarm owijarki: {alarm_val}",
                    raw_data=payload_data
                )
