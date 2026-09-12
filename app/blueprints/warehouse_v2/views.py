# File: app/blueprints/warehouse_v2/views.py
"""Warehouse V2 Views and Routes.

Delegates request handling to dedicated domain controllers following Clean Architecture:
- WarehouseIndexController: Main warehouse dashboard and inventory overview
- WarehouseSummaryController: Aggregated metrics, product stock and FIFO/FEFO analysis
- WarehousePageController: Generic pages (production status, orders, archive, 3D racks)
- PalletReportController: Printable production and shift reports
- PalletLabelController: Thermal/ZPL label preview and generator
"""

from app.blueprints.warehouse_v2.blueprint import warehouse_v2_bp
from app.blueprints.warehouse_v2.controllers import (
    PalletLabelController,
    PalletReportController,
    WarehouseIndexController,
    WarehousePageController,
    WarehouseSummaryController,
)
from app.blueprints.warehouse_v2.utils import (
    classify_packaging_type,
    compute_expiry_date,
    format_date_val,
    parse_date_obj,
)

# Re-exports for backward compatibility across modules
__all__ = [
    'classify_packaging_type',
    'compute_expiry_date',
    'format_date_val',
    'parse_date_obj',
    'index',
    'summary',
    'production_status',
    'zamowienia',
    'zamowienie_nowe',
    'archiwum',
    'raport_palet',
    'podglad_etykiety_psd',
    'racks_3d_view',
]


@warehouse_v2_bp.route('/')
def index():
    """Main warehouse dashboard view."""
    return WarehouseIndexController.render_index()


@warehouse_v2_bp.route('/summary')
def summary():
    """Aggregated warehouse inventory summary view."""
    return WarehouseSummaryController.render_summary()


@warehouse_v2_bp.route('/production-status')
def production_status():
    """Production stations status view."""
    return WarehousePageController.render_production_status()


@warehouse_v2_bp.route('/zamowienia')
def zamowienia():
    """Warehouse raw material orders list view."""
    return WarehousePageController.render_orders()


@warehouse_v2_bp.route('/zamowienia/nowe')
def zamowienie_nowe():
    """Warehouse new order creation view."""
    return WarehousePageController.render_new_order()


@warehouse_v2_bp.route('/archiwum')
def archiwum():
    """Pallet archive history view."""
    return WarehousePageController.render_archive()


@warehouse_v2_bp.route('/psd/raport_palet', methods=['GET'])
def raport_palet():
    """Printable and AJAX pallet report for PSD line."""
    return PalletReportController.render_pallet_report()


@warehouse_v2_bp.route('/podglad-etykiety/<paleta_id>', methods=['GET'])
@warehouse_v2_bp.route('/psd/podglad-etykiety/<paleta_id>', methods=['GET'])
def podglad_etykiety_psd(paleta_id):
    """Pallet label preview view."""
    return PalletLabelController.render_label_preview(paleta_id)


@warehouse_v2_bp.route('/racks-3d')
@warehouse_v2_bp.route('/widok-3d')
def racks_3d_view():
    """Interactive 3D warehouse rack visualizer."""
    return WarehousePageController.render_racks_3d()
