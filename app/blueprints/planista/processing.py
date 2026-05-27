import json
import os

from flask import current_app


def get_processing_times_config():
    """Load workowanie processing times from config JSON file."""
    try:
        cfg_path = os.path.join(current_app.root_path, 'config', 'workowanie_processing_times.json')
        if not os.path.exists(cfg_path):
            return None
        with open(cfg_path, 'r') as config_file:
            data = json.load(config_file)
        return data.get('processing_times_minutes', {})
    except Exception as error:
        current_app.logger.error('Error loading processing times config: %s', error)
        return None


def calculate_kg_per_hour(product_type: str) -> int:
    """Convert configured batch processing time into kg/hour throughput."""
    config = get_processing_times_config()
    fallback_normy_kg_h = {
        'worki_zgrzewane_25': 3000,
        'worki_zgrzewane_20': 3000,
        'worki_zszywane_25': 2000,
        'worki_zszywane_20': 2000,
        'bigbag': 4000,
    }

    if config is None:
        return fallback_normy_kg_h.get(product_type, 3000)

    product_config = config.get(product_type, {})
    if not product_config:
        return fallback_normy_kg_h.get(product_type, 3000)

    minutes = product_config.get('processing_time_minutes', 20)
    kg_per_1000 = product_config.get('weight_kg', 1000)
    return int((kg_per_1000 / minutes) * 60) if minutes > 0 else 3000