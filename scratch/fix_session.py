import sys
import os

# Add the project root to python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + '/..'))

from app import create_app
from app.services.inwentaryzacja_service import InwentaryzacjaService

app = create_app()

with app.app_context():
    # 52 is the session ID in the screenshot
    print("Fixing session 52...")
    InwentaryzacjaService.resume_session(52)
    success, msg = InwentaryzacjaService.close_session(52)
    print(f"Result: {success} - {msg}")
