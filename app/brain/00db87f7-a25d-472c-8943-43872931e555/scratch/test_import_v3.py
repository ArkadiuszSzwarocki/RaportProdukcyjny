import sys
sys.path.append('.')

print("Importing app.db...")
import app.db
print("Importing auth_bp...")
from app.blueprints.routes_auth import auth_bp
print("Importing main_bp...")
from app.blueprints.routes_main import main_bp
print("Importing production_bp...")
from app.blueprints.routes_production import production_bp
print("All imports OK!")
