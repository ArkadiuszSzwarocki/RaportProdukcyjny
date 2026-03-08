from app.core.factory import create_app
from app.services.attendance_service import AttendanceService

app = create_app()

with app.app_context():
    success, inserted_id, name = AttendanceService.add_to_schedule('Zasyp', 13, '2026-03-08')
    print("Success:", success, "ID:", inserted_id, "Name:", name)
