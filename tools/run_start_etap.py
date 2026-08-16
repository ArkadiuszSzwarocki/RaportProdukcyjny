import os
import sys
from datetime import date
sys.path.insert(0, r'c:\Users\arkad\Documents\GitHub\RaportProdukcyjny')

from app.db import get_db_connection
from app.services.zasyp_etapy_service import ZasypEtapyService

sys.stdout.reconfigure(encoding='utf-8')

print("Executing start_etap...")
ok, msg = ZasypEtapyService.start_etap(
    plan_id=46,
    linia='AGRO',
    data_planu=date(2026, 5, 25),
    etap=1,
    user_login='MasterAdmin',
    szarza_nr=1,
    allow_restart=False
)

print(f"Result: ok={ok}, msg={msg}")
