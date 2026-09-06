import json
import os
import threading
from typing import Dict, Any, List
from app.dto.service_result import ServiceResult

class PalletPatternService:
    """
    Service responsible for managing palletizer stacking recipes, pallet dimensions, and layer configurations.
    Supports Industrial Pallets (1000 x 1200 mm) and EURO/EPAL Pallets (800 x 1200 mm).
    """

    _CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.pallet_pattern_config.json')
    _LOCK = threading.Lock()

    PALLET_TYPES = {
        "INDUSTRIAL_100X120": {
            "id": "INDUSTRIAL_100X120",
            "name": "Paleta Przemysłowa (1000 × 1200 mm)",
            "short_name": "Przemysłowa 100×120",
            "width_m": 1.0,
            "length_m": 1.2,
            "top_boards_count": 7
        },
        "EURO_80X120": {
            "id": "EURO_80X120",
            "name": "Paleta EURO / EPAL 1 (800 × 1200 mm)",
            "short_name": "EURO 80×120",
            "width_m": 0.8,
            "length_m": 1.2,
            "top_boards_count": 5
        }
    }

    _DEFAULT_CONFIG = {
        "recipe_id": "ind_100x120_12x4_plus2",
        "preset_name": "Paleta Przemysłowa 100x120 - 12W x 4szt + 2szt szczyt (50 worków)",
        "pallet_type": "INDUSTRIAL_100X120",
        "pallet_name": "Paleta Przemysłowa (1000 × 1200 mm)",
        "pallet_width_m": 1.0,
        "pallet_length_m": 1.2,
        "full_layers": 12,
        "total_layers": 13,
        "bags_per_layer": 4,
        "top_layer_bags": 2,
        "bag_weight_kg": 25.0
    }

    _PRESETS = [
        # --- RECEPTURY PALETY PRZEMYSŁOWEJ (1000 x 1200 mm) ---
        {
            "id": "ind_12x4_plus2",
            "pallet_type": "INDUSTRIAL_100X120",
            "name": "Przemysłowa 100x120 • 12W × 4szt + 2 szczyt = 50 worków",
            "full_layers": 12,
            "bags_per_layer": 4,
            "top_layer_bags": 2,
            "bag_weight_kg": 25.0
        },
        {
            "id": "ind_10x5_50",
            "pallet_type": "INDUSTRIAL_100X120",
            "name": "Przemysłowa 100x120 • 10W × 5szt = 50 worków",
            "full_layers": 10,
            "bags_per_layer": 5,
            "top_layer_bags": 0,
            "bag_weight_kg": 25.0
        },
        {
            "id": "ind_12x5_60",
            "pallet_type": "INDUSTRIAL_100X120",
            "name": "Przemysłowa 100x120 • 12W × 5szt = 60 worków",
            "full_layers": 12,
            "bags_per_layer": 5,
            "top_layer_bags": 0,
            "bag_weight_kg": 25.0
        },
        {
            "id": "ind_11x5_55",
            "pallet_type": "INDUSTRIAL_100X120",
            "name": "Przemysłowa 100x120 • 11W × 5szt = 55 worków",
            "full_layers": 11,
            "bags_per_layer": 5,
            "top_layer_bags": 0,
            "bag_weight_kg": 25.0
        },

        # --- RECEPTURY PALETY EURO (800 x 1200 mm) ---
        {
            "id": "euro_12x4_plus2",
            "pallet_type": "EURO_80X120",
            "name": "EURO 80x120 • 12W × 4szt + 2 szczyt = 50 worków",
            "full_layers": 12,
            "bags_per_layer": 4,
            "top_layer_bags": 2,
            "bag_weight_kg": 25.0
        },
        {
            "id": "euro_12x4_48",
            "pallet_type": "EURO_80X120",
            "name": "EURO 80x120 • 12W × 4szt = 48 worków",
            "full_layers": 12,
            "bags_per_layer": 4,
            "top_layer_bags": 0,
            "bag_weight_kg": 25.0
        },
        {
            "id": "euro_10x4_40",
            "pallet_type": "EURO_80X120",
            "name": "EURO 80x120 • 10W × 4szt = 40 worków",
            "full_layers": 10,
            "bags_per_layer": 4,
            "top_layer_bags": 0,
            "bag_weight_kg": 25.0
        },
        {
            "id": "euro_8x4_32",
            "pallet_type": "EURO_80X120",
            "name": "EURO 80x120 • 8W × 4szt = 32 worki",
            "full_layers": 8,
            "bags_per_layer": 4,
            "top_layer_bags": 0,
            "bag_weight_kg": 25.0
        }
    ]

    @classmethod
    def get_config(cls) -> Dict[str, Any]:
        """Loads the current pallet stacking recipe and pattern configuration."""
        with cls._LOCK:
            if os.path.exists(cls._CONFIG_FILE):
                try:
                    with open(cls._CONFIG_FILE, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        merged = dict(cls._DEFAULT_CONFIG)
                        merged.update(data)
                        
                        full_layers = merged.get("full_layers") or merged.get("total_layers", 12)
                        bags_per_layer = merged.get("bags_per_layer", 4)
                        top_layer_bags = merged.get("top_layer_bags", 2)
                        pallet_type = str(merged.get("pallet_type", "INDUSTRIAL_100X120")).upper()
                        if pallet_type not in cls.PALLET_TYPES:
                            pallet_type = "INDUSTRIAL_100X120"
                        pallet_info = cls.PALLET_TYPES[pallet_type]

                        merged["pallet_type"] = pallet_type
                        merged["pallet_name"] = pallet_info["name"]
                        merged["pallet_short_name"] = pallet_info["short_name"]
                        merged["pallet_width_m"] = pallet_info["width_m"]
                        merged["pallet_length_m"] = pallet_info["length_m"]
                        merged["full_layers"] = full_layers
                        merged["total_layers"] = full_layers + (1 if top_layer_bags > 0 else 0)
                        merged["total_bags"] = cls.calculate_total_bags(full_layers, bags_per_layer, top_layer_bags)
                        return merged
                except Exception:
                    pass

            config = dict(cls._DEFAULT_CONFIG)
            pallet_info = cls.PALLET_TYPES[config["pallet_type"]]
            config["pallet_name"] = pallet_info["name"]
            config["pallet_short_name"] = pallet_info["short_name"]
            config["pallet_width_m"] = pallet_info["width_m"]
            config["pallet_length_m"] = pallet_info["length_m"]
            config["total_bags"] = cls.calculate_total_bags(
                config["full_layers"],
                config["bags_per_layer"],
                config["top_layer_bags"]
            )
            return config

    @classmethod
    def get_presets(cls) -> List[Dict[str, Any]]:
        """Returns available predefined stacking recipes."""
        presets = []
        for p in cls._PRESETS:
            item = dict(p)
            p_type = str(item.get("pallet_type", "INDUSTRIAL_100X120")).upper()
            pallet_info = cls.PALLET_TYPES.get(p_type, cls.PALLET_TYPES["INDUSTRIAL_100X120"])
            item["pallet_type"] = p_type
            item["pallet_name"] = pallet_info["name"]
            item["pallet_short_name"] = pallet_info["short_name"]
            item["pallet_width_m"] = pallet_info["width_m"]
            item["pallet_length_m"] = pallet_info["length_m"]
            item["total_bags"] = cls.calculate_total_bags(
                item["full_layers"],
                item["bags_per_layer"],
                item["top_layer_bags"]
            )
            item["total_layers"] = item["full_layers"] + (1 if item["top_layer_bags"] > 0 else 0)
            presets.append(item)
        return presets

    @classmethod
    def update_config(cls, data: Dict[str, Any]) -> ServiceResult:
        """Updates and persists the selected pallet stacking recipe."""
        try:
            pallet_type = str(data.get("pallet_type") or "INDUSTRIAL_100x120").strip().upper()
            if pallet_type not in cls.PALLET_TYPES:
                pallet_type = "INDUSTRIAL_100x120"
            pallet_info = cls.PALLET_TYPES[pallet_type]

            full_layers = max(1, min(25, int(data.get("full_layers") or data.get("total_layers", 12))))
            bags_per_layer = max(1, min(10, int(data.get("bags_per_layer", 4))))
            top_layer_bags = max(0, min(bags_per_layer, int(data.get("top_layer_bags", 0))))
            bag_weight_kg = max(1.0, float(data.get("bag_weight_kg", 25.0)))
            
            total_layers = full_layers + (1 if top_layer_bags > 0 else 0)
            total_bags = cls.calculate_total_bags(full_layers, bags_per_layer, top_layer_bags)

            preset_name = str(data.get("preset_name") or f"{pallet_info['short_name']} • {full_layers}W x {bags_per_layer}szt" + (f" + {top_layer_bags}szt" if top_layer_bags > 0 else "") + f" = {total_bags} worków").strip()

            config_to_save = {
                "preset_name": preset_name,
                "pallet_type": pallet_type,
                "pallet_name": pallet_info["name"],
                "pallet_short_name": pallet_info["short_name"],
                "pallet_width_m": pallet_info["width_m"],
                "pallet_length_m": pallet_info["length_m"],
                "full_layers": full_layers,
                "total_layers": total_layers,
                "bags_per_layer": bags_per_layer,
                "top_layer_bags": top_layer_bags,
                "bag_weight_kg": bag_weight_kg,
                "total_bags": total_bags
            }

            with cls._LOCK:
                with open(cls._CONFIG_FILE, 'w', encoding='utf-8') as f:
                    json.dump(config_to_save, f, indent=2, ensure_ascii=False)

            return ServiceResult.ok(
                data=config_to_save,
                message=f"Zastosowano recepturę: {pallet_info['short_name']} ({full_layers}W × {bags_per_layer} szt" + (f" + szczyt {top_layer_bags} szt" if top_layer_bags > 0 else "") + f" = {total_bags} worków)."
            )
        except Exception as e:
            return ServiceResult.fail(f"Błąd zapisu receptury palety: {str(e)}")

    @staticmethod
    def calculate_total_bags(full_layers: int, bags_per_layer: int, top_layer_bags: int) -> int:
        """Calculates total bags: full_layers * bags_per_layer + top_layer_bags."""
        if full_layers <= 0:
            return top_layer_bags
        return (full_layers * bags_per_layer) + top_layer_bags

    @classmethod
    def calculate_progress(cls, current_layer: int, current_bag: int, config: Dict[str, Any] = None) -> Dict[str, Any]:
        """Calculates current accumulated bags and progress percentage against configured schema."""
        cfg = config or cls.get_config()
        full_layers = cfg.get("full_layers", 12)
        bags_per_layer = cfg.get("bags_per_layer", 4)
        top_layer_bags = cfg.get("top_layer_bags", 2)
        total_layers = cfg.get("total_layers", full_layers + (1 if top_layer_bags > 0 else 0))
        total_bags = cfg.get("total_bags") or cls.calculate_total_bags(full_layers, bags_per_layer, top_layer_bags)

        if current_layer <= 0:
            accumulated = 0
        elif current_layer <= full_layers:
            accumulated = ((current_layer - 1) * bags_per_layer) + min(bags_per_layer, current_bag)
        else:
            accumulated = (full_layers * bags_per_layer) + min(top_layer_bags, current_bag)

        accumulated = max(0, min(total_bags, accumulated))
        pct = round((accumulated / total_bags) * 100.0, 1) if total_bags > 0 else 0.0
        pct = min(100.0, max(0.0, pct))

        expected_bags_in_current_layer = top_layer_bags if current_layer > full_layers else bags_per_layer

        return {
            "accumulated_bags": accumulated,
            "total_target_bags": total_bags,
            "progress_percent": pct,
            "expected_bags_in_current_layer": expected_bags_in_current_layer,
            "full_layers": full_layers,
            "total_layers": total_layers,
            "pallet_type": cfg.get("pallet_type", "INDUSTRIAL_100x120"),
            "config": cfg
        }
