"""Warehouse deliveries module - main blueprint configuration."""
from flask import Blueprint
from .config import (
    LOKALIZACJE_SZCZEGOLOWE, BUFORY, LOKALIZACJE, LOKALIZACJE_CEL,
    _safe_float, _safe_datetime_str, _format_label_weight
)
from .base import magazyn_dostawy_bp

# Re-export configuration constants
__all__ = [
    'magazyn_dostawy_bp',
    'LOKALIZACJE_SZCZEGOLOWE',
    'BUFORY',
    'LOKALIZACJE',
    'LOKALIZACJE_CEL',
    '_safe_float',
    '_safe_datetime_str',
    '_format_label_weight',
]
