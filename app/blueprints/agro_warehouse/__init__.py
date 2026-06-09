"""Agro warehouse management module."""
from flask import Blueprint
from .base import agro_warehouse_bp
from . import tank_assignment  # Import endpoints

__all__ = ['agro_warehouse_bp']
