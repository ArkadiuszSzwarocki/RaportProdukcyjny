from datetime import date, datetime
import os
import threading

import mysql.connector
from flask import abort, current_app, flash, jsonify, redirect, render_template, request, session
from werkzeug.exceptions import HTTPException

from app.core.audit import audit_log
from app.db import get_db_connection, get_table_name
from app.decorators import login_required, roles_required, masteradmin_required
from app.services.planning.status import PlanningStatusService
from app.utils.validation import require_field
from app.utils.pallet_id import generate_pallet_id

from .routes.palety_routes import register_palety_routes
from .routes.szarze_routes import register_szarze_routes
from .routes.printing_routes import register_printing_routes
from .routes.misc_routes import register_misc_routes

def register_warehouse_management_routes(
    warehouse_bp,
    *,
    resolve_request_linia,
    resolve_payload_linia,
    update_paleta_workowanie,
    update_paleta_magazyn,
    safe_return,
):
    register_palety_routes(warehouse_bp, resolve_request_linia=resolve_request_linia, resolve_payload_linia=resolve_payload_linia, update_paleta_workowanie=update_paleta_workowanie, update_paleta_magazyn=update_paleta_magazyn, safe_return=safe_return)
    register_szarze_routes(warehouse_bp, resolve_request_linia=resolve_request_linia, resolve_payload_linia=resolve_payload_linia, update_paleta_workowanie=update_paleta_workowanie, update_paleta_magazyn=update_paleta_magazyn, safe_return=safe_return)
    register_printing_routes(warehouse_bp, resolve_request_linia=resolve_request_linia, resolve_payload_linia=resolve_payload_linia, update_paleta_workowanie=update_paleta_workowanie, update_paleta_magazyn=update_paleta_magazyn, safe_return=safe_return)
    register_misc_routes(warehouse_bp, resolve_request_linia=resolve_request_linia, resolve_payload_linia=resolve_payload_linia, update_paleta_workowanie=update_paleta_workowanie, update_paleta_magazyn=update_paleta_magazyn, safe_return=safe_return)
