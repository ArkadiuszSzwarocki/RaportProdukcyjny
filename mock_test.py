import sys
from flask import Flask
from app.services.attendance_service import AttendanceService

# Minimal mock app
app = Flask(__name__)
# Add a dummy logger that prints to stdout immediately
import logging
handler = logging.StreamHandler(sys.stdout)
app.logger.addHandler(handler)
app.logger.setLevel(logging.DEBUG)

with app.app_context():
    print("Executing custom remove_from_schedule", flush=True)
    try:
        success, pid, name = AttendanceService.remove_from_schedule(140)
        print("Success:", success, "PID:", pid, "Name:", name, flush=True)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print("Caught exception:", e, flush=True)

print("Done.", flush=True)
