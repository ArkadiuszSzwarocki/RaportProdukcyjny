import os
import sys
sys.path.insert(0, r'c:\Users\arkad\Documents\GitHub\RaportProdukcyjny')

from flask import Flask, session
from app.core.factory import create_app
from app.core.contexts import inject_role_permissions

sys.stdout.reconfigure(encoding='utf-8')

app = create_app(init_db=False)
with app.test_request_context():
    # Set session values
    session['rola'] = 'pracownik'
    session['grupa'] = 'PSD'
    
    ctx = inject_role_permissions()
    role_has_access = ctx['role_has_access']
    
    print("--- Permissions for pracownik ---")
    print(f"psd.dashboard: {role_has_access('psd.dashboard')}")
    print(f"psd.zasyp: {role_has_access('psd.zasyp')}")
    print(f"psd.workowanie: {role_has_access('psd.workowanie')}")
    print(f"psd.bufor: {role_has_access('psd.bufor')}")
    print(f"psd.magazyn: {role_has_access('psd.magazyn')}")
    
    session['rola'] = 'lider'
    print("\n--- Permissions for lider ---")
    print(f"psd.dashboard: {role_has_access('psd.dashboard')}")
    print(f"psd.zasyp: {role_has_access('psd.zasyp')}")
