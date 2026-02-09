"""
Test: Nowy endpoint /api/reorder_plans_bulk
"""
import requests
import json
from datetime import date

base_url = "http://127.0.0.1:8082"

# Test data
test_data = {
    "plan_ids": [577, 573, 575, 571],  # Testowy4, Testowy2, Testowy3, Testowy1
    "data": str(date.today()),
    "sekcja": "zasyp"
}

print("\n" + "="*80)
print("TEST: Reorder plans via dragowe-drop")
print("="*80)
print(f"\nŻądane kolejęorder: {test_data['plan_ids']}")
print(f"Data: {test_data['data']}")

try:
    response = requests.post(
        f"{base_url}/api/reorder_plans_bulk",
        json=test_data,
        timeout=10
    )
    
    print(f"\nStatus code: {response.status_code}")
    print(f"Response: {response.text}")
    
    if response.status_code == 200:
        result = response.json()
        if result.get('success'):
            print("\n✅ SUCCESS! Plany przeordynacjowane!")
            print(f"   Mesage: {result.get('message')}")
        else:
            print(f"\n✗ FAILED: {result.get('message')}")
    else:
        print(f"\n✗ HTTP ERROR: {response.status_code}")
        
except Exception as e:
    print(f"\n✗ Connection error: {e}")

print("\n" + "="*80)
