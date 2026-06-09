from flask import Blueprint
from .backups import register_admin_backup_routes
from .bugs import register_admin_bug_routes
from .diagnostics import register_admin_diagnostics_routes
from .production import register_admin_production_routes
from .roles import register_admin_roles_routes
from .system import register_admin_system_routes
from .team import register_admin_team_routes
from .workowanie_times import register_admin_workowanie_times_routes
from .warehouse_capacities import register_admin_warehouse_capacities_routes
from .raw_materials import register_admin_raw_materials_routes
from app.db import create_notification_for_login, list_online_users

def _load_roles(cursor):
    try:
        cursor.execute("SELECT name, label FROM roles ORDER BY id ASC")
        return cursor.fetchall()
    except Exception:
        return [('admin', 'admin'), ('planista', 'planista'), ('pracownik', 'pracownik'), ('magazynier', 'magazynier'), ('dur', 'dur'), ('zarzad', 'zarzad'), ('laborant', 'laborant')]

admin_bp = Blueprint('admin', __name__)
register_admin_backup_routes(admin_bp)
register_admin_bug_routes(admin_bp, create_notification=create_notification_for_login)
register_admin_diagnostics_routes(admin_bp)
register_admin_production_routes(admin_bp, load_roles=_load_roles)
register_admin_roles_routes(admin_bp)
register_admin_system_routes(admin_bp, list_online_users=list_online_users)
register_admin_team_routes(admin_bp, load_roles=_load_roles)
register_admin_workowanie_times_routes(admin_bp)
register_admin_warehouse_capacities_routes(admin_bp)
register_admin_raw_materials_routes(admin_bp)
