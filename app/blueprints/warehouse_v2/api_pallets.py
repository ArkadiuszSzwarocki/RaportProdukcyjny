"""
Warehouse V2 Pallets API Routes.
Delegates business handling to dedicated controllers while registering HTTP routes on the warehouse_v2 blueprint.
"""

from app.blueprints.warehouse_v2.blueprint import warehouse_v2_bp
from app.blueprints.warehouse_v2.controllers.pallet_query_controller import PalletQueryController
from app.blueprints.warehouse_v2.controllers.pallet_relocation_controller import PalletRelocationController
from app.blueprints.warehouse_v2.controllers.pallet_mutation_controller import PalletMutationController
from app.blueprints.warehouse_v2.controllers.pallet_print_controller import PalletPrintController
from app.blueprints.warehouse_v2.controllers.pallet_delete_controller import PalletDeleteController

# Query Endpoints
@warehouse_v2_bp.route('/api/pallet/history', methods=['GET'])
def get_history():
    return PalletQueryController.get_history()

@warehouse_v2_bp.route('/api/pallet/details', methods=['GET'])
def get_pallet_details():
    return PalletQueryController.get_pallet_details()

# Relocation Endpoints
@warehouse_v2_bp.route('/api/pallet/move', methods=['POST'])
def move_pallet():
    return PalletRelocationController.move_pallet()

# Mutation & Lifecycle Endpoints
@warehouse_v2_bp.route('/api/pallet/update-packaging', methods=['POST'])
def update_packaging():
    return PalletMutationController.update_packaging()

@warehouse_v2_bp.route('/api/pallet/update-material-type', methods=['POST'])
def update_material_type():
    return PalletMutationController.update_material_type()

@warehouse_v2_bp.route('/api/pallet/bulk-update-material-type', methods=['POST'])
def bulk_update_material_type():
    return PalletMutationController.bulk_update_material_type()

@warehouse_v2_bp.route('/api/pallet/archive', methods=['POST'])
def archive_pallet():
    return PalletMutationController.archive_pallet()

@warehouse_v2_bp.route('/api/pallet/dispatch', methods=['POST'])
def dispatch_pallet():
    return PalletMutationController.dispatch_pallet()

@warehouse_v2_bp.route('/api/pallet/rename', methods=['POST'])
def rename_pallet():
    return PalletMutationController.rename_pallet()

@warehouse_v2_bp.route('/api/pallet/update-weight', methods=['POST'])
def update_weight():
    return PalletMutationController.update_weight()

@warehouse_v2_bp.route('/api/pallet/toggle-block', methods=['POST'])
def toggle_block():
    return PalletMutationController.toggle_block()

@warehouse_v2_bp.route('/api/pallet/return-to-raw', methods=['POST'])
def pallet_return_to_raw():
    return PalletMutationController.pallet_return_to_raw()

@warehouse_v2_bp.route('/api/archiwum/restore/<int:archive_id>', methods=['POST'])
def restore_from_archive(archive_id):
    return PalletMutationController.restore_from_archive(archive_id)

# Print Endpoints
@warehouse_v2_bp.route('/api/pallet/print', methods=['POST'])
def print_pallet_label():
    return PalletPrintController.print_pallet_label()

# Deletion Endpoints
@warehouse_v2_bp.route('/api/pallet/delete', methods=['POST'])
def delete_pallet():
    return PalletDeleteController.delete_pallet()
