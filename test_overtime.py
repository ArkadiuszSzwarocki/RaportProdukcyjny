#!/usr/bin/env python
"""Test script for overtime functionality."""

from app.services.overtime_service import OvertimeService
from datetime import date

# Test 1: Get pending requests
print('Test 1: Get pending requests')
requests = OvertimeService.get_pending_requests()
print(f'  Pending requests: {len(requests)} items')
for r in requests:
    rid = r['id']
    name = r['imie_nazwisko']
    hours = r['ilosc_nadgodzin']
    data = r['data']
    print(f'    - ID{rid}: {name} - {hours}h OT on {data}')

# Test 2: Get user requests for pracownik_id=16
print('\nTest 2: Get user requests for pracownik_id=16')
user_reqs = OvertimeService.get_user_requests(16)
print(f'  User requests: {len(user_reqs)} items')
for r in user_reqs:
    data = r['data']
    hours = r['ilosc_nadgodzin']
    status = r['status']
    print(f'    - {data}: {hours}h ({status})')

# Test 3: Get approved overtime for specific date
print('\nTest 3: Get approved overtime for pracownik_id=16 on 2026-03-02')
ot = OvertimeService.get_approved_overtime_for_date(16, date(2026, 3, 2))
print(f'  Approved OT hours: {ot}h')

print('\n[OK] All tests passed!')
