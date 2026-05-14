import sys
import os
sys.path.append('.')

print("1. Importing mqtt_service...")
from app.services.mqtt_service import get_latest_data
print("2. Importing agro_warehouse_service...")
from app.services.agro_warehouse_service import AgroWarehouseService
print("3. Importing routes_production_orders...")
from app.blueprints.routes_production_orders import production_orders_bp
print("Done!")
