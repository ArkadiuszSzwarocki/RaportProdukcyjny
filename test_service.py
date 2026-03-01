from app.services.overtime_service import OvertimeService

print("=== TEST OvertimeService.get_user_requests(16) ===")
result = OvertimeService.get_user_requests(16)
print(f"Rezultat: {result}")
print(f"Typ: {type(result)}")
print(f"Długość: {len(result) if result else 0}")

if result:
    for r in result:
        print(f"  {r}")
else:
    print("  ⚠️  PUSTE!")
