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


def _resolve_plan_id_for_paleta(cursor, paleta_id, linia, requested_plan_id=None):
    """Resolve Workowanie plan_id for a pallet id from magazyn/buffer tables safely."""
    table_pal = get_table_name('palety_workowanie', linia)
    table_mag = get_table_name('magazyn_palety', linia)

    requested_id = None
    try:
        if requested_plan_id not in (None, '', 'None'):
            requested_id = int(requested_plan_id)
    except Exception:
        requested_id = None

    if requested_id:
        # Validate that requested plan_id really belongs to this pallet.
        cursor.execute(
            f"SELECT 1 FROM {table_mag} WHERE (id=%s OR paleta_workowanie_id=%s) AND plan_id=%s LIMIT 1",
            (paleta_id, paleta_id, requested_id),
        )
        if cursor.fetchone():
            return requested_id

        cursor.execute(
            f"SELECT 1 FROM {table_pal} WHERE id=%s AND plan_id=%s LIMIT 1",
            (paleta_id, requested_id),
        )
        if cursor.fetchone():
            return requested_id

    # First check magazyn table by confirmed pallet id/pointer.
    # This avoids id-collision with palety_workowanie IDs.
    cursor.execute(
        f'''
        SELECT COALESCE(mp.plan_id, pw.plan_id)
        FROM {table_mag} mp
        LEFT JOIN {table_pal} pw ON pw.id = mp.paleta_workowanie_id
        WHERE mp.id = %s OR mp.paleta_workowanie_id = %s
        ORDER BY CASE WHEN mp.id = %s THEN 0 ELSE 1 END, mp.id DESC
        LIMIT 1
        ''',
        (paleta_id, paleta_id, paleta_id),
    )
    row = cursor.fetchone()
    if row and row[0]:
        return int(row[0])

    cursor.execute(f"SELECT plan_id FROM {table_pal} WHERE id=%s", (paleta_id,))
    row = cursor.fetchone()
    if row and row[0]:
        return int(row[0])

    return None

