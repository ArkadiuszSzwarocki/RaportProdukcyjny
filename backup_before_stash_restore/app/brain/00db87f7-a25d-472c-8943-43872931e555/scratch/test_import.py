from app.core.factory import create_app
import sys
import traceback

try:
    print("Starting app creation...")
    app = create_app()
    print("App created successfully!")
except Exception as e:
    print(f"Error: {e}")
    traceback.print_exc()
    sys.exit(1)
