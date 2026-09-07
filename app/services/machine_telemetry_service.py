from typing import Dict, Any, List, Optional
import time
from app.services.mqtt_service import get_latest_data, publish_command, simulate_machine_data
from app.dto.service_result import ServiceResult
from app.services.pallet_pattern_service import PalletPatternService

class MachineTelemetryService:
    """
    Domain service for IoT machine broker communication and live telemetry aggregation.
    Provides structured data for Wagopakowaczka, Paletyzator, Owijarka, and MQTT stream logs.
    """

    HEARTBEAT_TIMEOUT_SECONDS = 30  # Machine considered offline if no message received for > 30s

    @staticmethod
    def get_live_dashboard_data() -> Dict[str, Any]:
        """
        Aggregates and enriches real-time telemetry from the MQTT broker.
        """
        raw_data = get_latest_data()
        now = time.time()
        last_update = raw_data.get("last_update", 0)
        time_since_update = round(now - last_update, 1) if last_update > 0 else 9999

        is_connected = time_since_update <= MachineTelemetryService.HEARTBEAT_TIMEOUT_SECONDS and last_update > 0

        # 1. WAGOPAKOWACZKA (Bagger)
        bpm = float(raw_data.get("bpm") or 0.0)
        bag_weight_kg = 25.0  # standard bag size
        tons_per_hour = round((bpm * 60 * bag_weight_kg) / 1000.0, 2)

        bagger_status = raw_data.get("status", "OFFLINE")
        if not is_connected:
            bagger_status = "OFFLINE"

        jaws_closed = bool(raw_data.get("bagger_jaws_closed", False))

        bagger = {
            "name": "Wagopakowaczka Automatyczna",
            "type": "BAGGER",
            "status": bagger_status,
            "is_running": bagger_status == "PRACA",
            "bpm": bpm,
            "tons_per_hour": tons_per_hour,
            "counter_global": int(raw_data.get("counter") or 0),
            "counter_local": int(raw_data.get("local_counter") or 0),
            "recipe_name": raw_data.get("receptura", "Brak danych"),
            "bag_nominal_weight_kg": bag_weight_kg,
            "jaws_closed": jaws_closed,
            "last_seen_sec": time_since_update
        }

        # 2. PALETYZATOR (Palletizer)
        current_layer = int(raw_data.get("nrWarstwy") or 0)
        current_bag = int(raw_data.get("nrWorka") or 0)
        
        pallet_calc = PalletPatternService.calculate_progress(current_layer, current_bag)
        pattern_cfg = pallet_calc["config"]

        is_palletizer_moving = bool(raw_data.get("turner_active") or raw_data.get("pusher_active") or raw_data.get("dispenser_active") or raw_data.get("sygnal_do_owijarki_start") or raw_data.get("oproznianie"))
        if not is_connected:
            pal_status = "OFFLINE"
        elif is_palletizer_moving or (bagger_status == "PRACA" and bpm > 0):
            pal_status = "PRACA"
        elif bagger_status in ("STOP", "PAUZA", "AWARIA"):
            pal_status = bagger_status
        else:
            pal_status = "GOTOWY"

        palletizer = {
            "name": "Robot Paletyzujący",
            "type": "PALLETIZER",
            "status": pal_status,
            "current_layer": current_layer,
            "full_layers": pallet_calc["full_layers"],
            "total_layers": pallet_calc["total_layers"],
            "current_bag": current_bag,
            "bags_per_layer": pattern_cfg.get("bags_per_layer", 4),
            "top_layer_bags": pattern_cfg.get("top_layer_bags", 2),
            "total_target_bags": pallet_calc["total_target_bags"],
            "accumulated_bags": pallet_calc["accumulated_bags"],
            "expected_bags_in_current_layer": pallet_calc["expected_bags_in_current_layer"],
            "preset_name": pattern_cfg.get("preset_name", ""),
            "pallet_progress_percent": pallet_calc["progress_percent"],
            "pallets_completed_global": int(raw_data.get("pallet_counter") or 0),
            "is_emptying": bool(raw_data.get("oproznianie", False)),
            "wrapper_start_signal": bool(raw_data.get("sygnal_do_owijarki_start", False)),
            "bag_rotation_deg": raw_data.get("bag_rotation_deg"),
            "turner_active": raw_data.get("turner_active", False),
            "pusher_active": raw_data.get("pusher_active", False),
            "dispenser_pallet_count": int(raw_data.get("dispenser_pallet_count") or 8),
            "dispenser_active": bool(raw_data.get("dispenser_active", False)),
            "roller_1_occupied": bool(raw_data.get("rolki1zajete", False)),
            "roller_2_occupied": bool(raw_data.get("rolki2zajete", False)),
            "buffer_full": bool(raw_data.get("buforPelny", False))
        }

        # 3. OWIJARKA (Stretch Wrapper)
        is_wrapped = bool(raw_data.get("is_wrapped", False))
        raw_progress = raw_data.get("wrapping_progress")
        raw_top_sheet = raw_data.get("top_sheet_applied")
        raw_rotations = int(raw_data.get("wrapper_rotations") or 0)
        raw_phase = str(raw_data.get("wrapper_phase") or "").upper()
        wrapper_signal = palletizer["wrapper_start_signal"]

        # Determine wrapping progress & phase
        if is_wrapped:
            progress_pct = 100
            phase_code = "DONE"
            phase_label = "Paleta owinięta (Gotowa do odbioru)"
            top_sheet_applied = True
            top_sheet_active = False
            carriage_height_pct = 0
            wrapper_status = "GOTOWY" if not is_connected else "GOTOWA"
        elif raw_progress is not None:
            progress_pct = int(min(100, max(0, raw_progress)))
            if progress_pct >= 100:
                phase_code = "DONE"
                phase_label = "Paleta owinięta (Gotowa do odbioru)"
                top_sheet_applied = True
                top_sheet_active = False
                carriage_height_pct = 0
            elif progress_pct >= 85:
                phase_code = "DESCENDING"
                phase_label = "Zjazd wózka, odcięcie i zgrzew folii"
                top_sheet_applied = True
                top_sheet_active = False
                carriage_height_pct = int((100 - progress_pct) * 6.6)
            elif progress_pct >= 65:
                phase_code = "TOP_WRAP"
                phase_label = "Owinięcie szczytu i zabezpieczenie kapturka"
                top_sheet_applied = True
                top_sheet_active = False
                carriage_height_pct = 100
            elif progress_pct >= 45:
                phase_code = "TOP_SHEET"
                phase_label = "Nakładanie kapturka foliowego (Top Sheet)"
                top_sheet_applied = True
                top_sheet_active = True
                carriage_height_pct = 100
            elif progress_pct >= 20:
                phase_code = "ASCENDING"
                phase_label = "Wznoszenie wózka z folią stretch"
                top_sheet_applied = False
                top_sheet_active = False
                carriage_height_pct = int((progress_pct - 20) * 4.0)
            elif progress_pct > 0:
                phase_code = "BOTTOM_WRAP"
                phase_label = "Owinięcie dolnej podstawy palety"
                top_sheet_applied = False
                top_sheet_active = False
                carriage_height_pct = 0
            else:
                phase_code = "IDLE"
                phase_label = "Oczekiwanie na paletę"
                top_sheet_applied = False
                top_sheet_active = False
                carriage_height_pct = 0

            wrapper_status = "OWIJANIE" if 0 < progress_pct < 100 else ("GOTOWA" if progress_pct >= 100 else ("GOTOWY" if is_connected else "OFFLINE"))
        elif wrapper_signal:
            progress_pct = 35
            phase_code = "ASCENDING"
            phase_label = "Cykl owijania w toku"
            top_sheet_applied = False
            top_sheet_active = False
            carriage_height_pct = 35
            wrapper_status = "OWIJANIE"
        else:
            progress_pct = 0
            phase_code = "IDLE"
            phase_label = "Oczekiwanie na nową paletę"
            top_sheet_applied = False
            top_sheet_active = False
            carriage_height_pct = 0
            wrapper_status = "GOTOWY" if is_connected else "OFFLINE"

        if raw_top_sheet is not None:
            top_sheet_applied = raw_top_sheet
        if raw_phase:
            phase_code = raw_phase

        wrapper = {
            "name": "Owijarka Palet Stretch",
            "type": "WRAPPER",
            "status": wrapper_status,
            "is_wrapped": is_wrapped or progress_pct >= 100,
            "ready_for_pickup": (is_wrapped or progress_pct >= 100) and not palletizer["is_emptying"],
            "signal_active": wrapper_signal,
            "progress_percent": progress_pct,
            "phase_code": phase_code,
            "phase_label": phase_label,
            "top_sheet_applied": top_sheet_applied,
            "top_sheet_active": top_sheet_active,
            "rotations_count": raw_rotations if raw_rotations > 0 else int(progress_pct * 0.16),
            "carriage_height_percent": carriage_height_pct
        }

        # 4. CHECKWEIGHER & REJECT DROP FLAP (WAGA DYNAMICZNA I ZRZUT)
        from app.services.machine_reject_log_service import MachineRejectLogService
        reject_stats = MachineRejectLogService.get_reject_statistics()
        
        raw_cur_weight = raw_data.get("checkweigher_weight")
        cur_weight = float(raw_cur_weight) if raw_cur_weight is not None else (25.04 if bpm > 0 else 0.0)
        target_w = float(raw_data.get("checkweigher_target_weight") or 25.0)
        reject_flap_open = bool(raw_data.get("checkweigher_reject_active", False))

        checkweigher = {
            "name": "Waga Dynamiczna & Klapa Zrzutu",
            "type": "CHECKWEIGHER",
            "current_weight_kg": cur_weight,
            "target_weight_kg": target_w,
            "min_tolerance_kg": round(target_w - 0.25, 2),
            "max_tolerance_kg": round(target_w + 0.25, 2),
            "is_in_tolerance": (target_w - 0.25) <= cur_weight <= (target_w + 0.25) if cur_weight > 0 else True,
            "reject_flap_open": reject_flap_open,
            "bag_on_scale": bool(is_connected and bagger_status == "PRACA" and bpm > 0 and raw_cur_weight is not None and cur_weight > 0.5),
            "reject_count_total": reject_stats["total_rejects"],
            "reject_count_today": reject_stats["today_rejects"],
            "reject_by_reason": reject_stats["by_reason"],
            "recent_rejects": reject_stats["recent_rejects"]
        }

        # 5. PALLET LOGISTICS & STATION TRACKING (Magazynek, Paletyzator, Rolotoki, Owijarka, Odbiór)
        is_emptying = palletizer["is_emptying"]
        is_transferring = palletizer["wrapper_start_signal"]
        is_wrapping = (wrapper["progress_percent"] > 0 and wrapper["progress_percent"] < 100) or wrapper["status"] == "OWIJANIE"
        is_ready_pickup = wrapper["ready_for_pickup"]
        roller_1_occupied = palletizer["roller_1_occupied"]
        roller_2_occupied = palletizer["roller_2_occupied"]
        buffer_full = palletizer["buffer_full"]

        disp_count = palletizer["dispenser_pallet_count"]
        disp_active = palletizer["dispenser_active"]

        pallet_stations = [
            {
                "id": "ST1_DISPENSER",
                "name": "Magazynek Palet",
                "station_no": 1,
                "pallet_present": disp_count > 0,
                "status": "PODAWANIE" if disp_active else ("GOTOWY" if disp_count > 0 else "PUSTY"),
                "badge_class": "status-pill praca" if disp_active else ("status-pill" if disp_count > 0 else "status-pill off"),
                "count": disp_count,
                "description": f"Stos {disp_count} szt pustych palet"
            },
            {
                "id": "ST2_PALLETIZER",
                "name": "Stacja Paletyzatora",
                "station_no": 2,
                "pallet_present": is_connected and not is_emptying,
                "status": "OPRÓŻNIANIE" if is_emptying else ("UKŁADANIE" if (current_layer > 0 or current_bag > 0) else "OCZEKIWANIE"),
                "badge_class": "status-pill praca" if (is_emptying or current_layer > 0) else "status-pill",
                "count": palletizer["accumulated_bags"],
                "description": f"Warstwa {current_layer}/{palletizer['total_layers']} • {palletizer['accumulated_bags']}/{palletizer['total_target_bags']} worków"
            },
            {
                "id": "ST3_TRANSFER_CONVEYOR",
                "name": "Rolotok Pośredni",
                "station_no": 3,
                "pallet_present": is_emptying or is_transferring,
                "status": "TRANSFER" if (is_emptying or is_transferring) else "WOLNY",
                "badge_class": "status-pill praca" if (is_emptying or is_transferring) else "status-pill",
                "count": 1 if (is_emptying or is_transferring) else 0,
                "description": "Przejazd pełnej palety do owijarki" if (is_emptying or is_transferring) else "Tor rolkowy czysty"
            },
            {
                "id": "ST4_WRAPPER",
                "name": "Stół Owijarki",
                "station_no": 4,
                "pallet_present": is_wrapping or is_transferring or is_ready_pickup,
                "status": "OWIJANIE" if is_wrapping else ("GOTOWA" if is_ready_pickup else "CZUWANIE"),
                "badge_class": "status-pill praca" if is_wrapping else ("status-pill ready" if is_ready_pickup else "status-pill"),
                "count": wrapper["rotations_count"],
                "description": f"Postęp: {wrapper['progress_percent']}% • Kapturek: {'TAK' if wrapper['top_sheet_applied'] else 'BRAK'}"
            },
            {
                "id": "ST5_PICKUP",
                "name": "Bufor Odbiorczy",
                "station_no": 5,
                "pallet_present": is_ready_pickup or roller_1_occupied or roller_2_occupied,
                "status": "PELNY" if buffer_full else ("DO ODBIORU" if (is_ready_pickup or roller_1_occupied or roller_2_occupied) else "WOLNY"),
                "badge_class": "status-pill off" if buffer_full else ("status-pill ready" if (is_ready_pickup or roller_1_occupied or roller_2_occupied) else "status-pill"),
                "count": (1 if roller_1_occupied else 0) + (1 if roller_2_occupied else 0),
                "description": (
                    f"Rolka1: {'ZAJETA' if roller_1_occupied else 'WOLNA'} • Rolka2: {'ZAJETA' if roller_2_occupied else 'WOLNA'}"
                    if (roller_1_occupied or roller_2_occupied or buffer_full)
                    else "Strefa odbioru wolna"
                )
            }
        ]

        # 6. BROKER & LOGS
        broker = {
            "is_connected": is_connected,
            "host": "HiveMQ Cloud TLS (s1.eu.hivemq.cloud)",
            "port": 8883,
            "last_update_ts": last_update,
            "time_since_update_sec": time_since_update,
            "messages_total": int(raw_data.get("messages_total") or 0),
            "subscribed_topics": raw_data.get("subscribed_topics") or ["#"],
            "topics_seen": raw_data.get("topics_seen") or []
        }

        # 7. ACTIVE AGRO BAGGING ORDER DETAILS (DANE ZLECENIA WORKOWANIA DLA WORKÓW 3D)
        active_order = MachineTelemetryService.get_active_bagging_order()

        from app.services.machine_error_log_service import MachineErrorLogService
        persistent_errors = MachineErrorLogService.get_errors(limit=50)

        return {
            "timestamp": now,
            "timestamp_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
            "broker": broker,
            "machines": {
                "bagger": bagger,
                "checkweigher": checkweigher,
                "palletizer": palletizer,
                "wrapper": wrapper
            },
            "active_order": active_order,
            "pallet_stations": pallet_stations,
            "reject_statistics": reject_stats,
            "recent_rejects": reject_stats["recent_rejects"],
            "recent_messages": raw_data.get("recent_messages") or [],
            "recent_errors": raw_data.get("recent_errors") or [],
            "error_logs": persistent_errors,
            "error_logs_count": len(persistent_errors)
        }

    @staticmethod
    def get_active_bagging_order() -> Dict[str, Any]:
        """
        Retrieves active or latest bagging order details for the AGRO packaging line.
        Includes product name, batch/lot number, production date, expiry date, brand.
        """
        import datetime
        from app.core.database import get_db_connection

        default_order = {
            "plan_id": 0,
            "product_name": "KREDA NAWOZOWA AGRO GRANULOWANA",
            "batch_number": f"LOT-{datetime.date.today().strftime('%Y%m%d')}-01",
            "production_date": datetime.date.today().strftime("%Y-%m-%d"),
            "expiry_date": (datetime.date.today() + datetime.timedelta(days=730)).strftime("%Y-%m-%d"),
            "weight_kg": 25.0,
            "brand": "AGRONETZWERK",
            "sub_brand": "AGRO PREMIUM FERTILIZERS"
        }

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            # 1. First priority: active order in plan_produkcji_agro
            cursor.execute("""
                SELECT id, produkt, nazwa_zlecenia, nr_receptury, data_planu, data_produkcji, status
                FROM plan_produkcji_agro
                WHERE sekcja IN ('Workowanie', 'Czyszczenie') AND is_deleted = 0
                ORDER BY 
                    CASE WHEN status = 'w toku' THEN 1 WHEN status = 'zaplanowane' THEN 2 ELSE 3 END,
                    data_planu DESC,
                    kolejnosc ASC,
                    id DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            if not row:
                # 2. Fallback: plan_produkcji
                cursor.execute("""
                    SELECT id, produkt, nazwa_zlecenia, nr_receptury, data_planu, data_produkcji, status
                    FROM plan_produkcji
                    WHERE sekcja IN ('Workowanie', 'Czyszczenie') AND is_deleted = 0
                    ORDER BY 
                        CASE WHEN status = 'w toku' THEN 1 WHEN status = 'zaplanowane' THEN 2 ELSE 3 END,
                        data_planu DESC,
                        kolejnosc ASC,
                        id DESC
                    LIMIT 1
                """)
                row = cursor.fetchone()

            cursor.close()
            conn.close()

            if row:
                plan_id = row.get("id") or 0
                raw_prod = str(row.get("produkt") or row.get("nazwa_zlecenia") or "KREDA NAWOZOWA AGRO").strip()
                prod_name = raw_prod.upper()

                db_prod_date = row.get("data_produkcji") or row.get("data_planu")
                if isinstance(db_prod_date, (datetime.date, datetime.datetime)):
                    prod_date_obj = db_prod_date if isinstance(db_prod_date, datetime.date) else db_prod_date.date()
                else:
                    prod_date_obj = datetime.date.today()

                prod_date_str = prod_date_obj.strftime("%Y-%m-%d")
                exp_date_str = (prod_date_obj + datetime.timedelta(days=730)).strftime("%Y-%m-%d")

                recipe_no = str(row.get("nr_receptury") or "").strip()
                if recipe_no and recipe_no != "Brak" and recipe_no != "None":
                    batch_str = f"LOT-{recipe_no}"
                else:
                    batch_str = f"LOT-{prod_date_obj.strftime('%Y%m%d')}-{plan_id:03d}"

                return {
                    "plan_id": plan_id,
                    "product_name": prod_name,
                    "batch_number": batch_str,
                    "production_date": prod_date_str,
                    "expiry_date": exp_date_str,
                    "weight_kg": 25.0,
                    "brand": "AGRONETZWERK",
                    "sub_brand": "AGRO PREMIUM QUALITY",
                    "status": row.get("status") or "w toku"
                }
        except Exception:
            pass

        return default_order

    @staticmethod
    def send_machine_command(topic: str, command_payload: dict) -> ServiceResult:
        """Publishes a direct command to a machine topic via MQTT broker."""
        if not topic:
            return ServiceResult.fail("Brak tematu (topic) do wysłania komendy.")

        success = publish_command(topic, command_payload)
        if success:
            return ServiceResult.ok(
                data={"topic": topic, "payload": command_payload},
                message=f"Komenda została pomyślnie wysłana do brokera (Topic: {topic})."
            )
        return ServiceResult.fail(f"Nie udało się wysłać komendy do tematu {topic}. Sprawdź połączenie brokera.")
