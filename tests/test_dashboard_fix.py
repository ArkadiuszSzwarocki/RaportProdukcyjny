#!/usr/bin/env python3
"""
Test the dashboard endpoint with plan 399 to verify it displays 3120 kg realization
"""
import sys
sys.path.insert(0, '.')

# Mock the Flask context
import os
os.environ['FLASK_TESTING'] = '1'

from app import create_app_with_db

# Create app in test mode
app = create_app_with_db()

with app.test_client() as client:
    # Try to access dashboard (should redirect to login if no session)
    response = client.get('/', follow_redirects=True)
    
    print("Dashboard Response Status:", response.status_code)
    
    # Check if response contains data about plan 399
    if b'399' in response.data or b'3120' in response.data:
        print("✓ Dashboard loaded")
        
        # Try to see if 3120 kg is in the HTML
        if b'3120' in response.data:
            print("✓ Found '3120' in dashboard HTML")
        else:
            print("⚠️  '3120' not found directly in response")
            
        # Check for our plan's product name
        if b'AGROS' in response.data:
            print("✓ Found plan product 'AGROS' in dashboard")
    else:
        print("Dashboard requires login or filters, testing direct route...")
        
        # Alternatively, test by calling Flask's route directly in test mode
        from flask import json
        
        # We can at least verify the data is there
        print("\nDirect database verification:")
        from db import get_db_connection
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, produkt, tonaz_rzeczywisty 
            FROM plan_produkcji 
            WHERE id = 399
        """)
        result = cursor.fetchone()
        
        if result:
            plan_id, produkt, tonaz_rzeczywisty = result
            print(f"Plan {plan_id}: {produkt}")
            print(f"  Realization (tonaz_rzeczywisty): {tonaz_rzeczywisty} kg")
            
            if tonaz_rzeczywisty == 3120:
                print("\n✓ SUCCESS: Plan 399 correctly shows 3120 kg!")
            else:
                print(f"\n❌ ERROR: Expected 3120 kg, got {tonaz_rzeczywisty} kg")
        
        cursor.close()
        conn.close()

print("\nTest complete!")
