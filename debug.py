import sys
import os
from datetime import date
sys.path.insert(0, 'a:/GitHub/RaportProdukcyjny')
from app import create_app
from app.db import get_db_connection

app = create_app()
with app.app_context():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    dzisiaj = str(date.today())
    print('Dzisiaj:', dzisiaj)
    
    cursor.execute('SELECT id, data_planu, produkt, kolejka, zasyp_id, status FROM bufor_psd WHERE DATE(data_planu) = %s AND status = \'aktywny\'', (dzisiaj,))
    bufor = cursor.fetchall()
    print('BUFOR:', bufor)

    cursor.execute('SELECT id, data_planu, produkt, status, zasyp_id, is_deleted FROM plan_produkcji_psd WHERE DATE(data_planu) = %s AND sekcja = \'Workowanie\'', (dzisiaj,))
    workowanie = cursor.fetchall()
    print('WORKOWANIE:', workowanie)

    from app.services.workowanie_queue_service import WorkowanieQueueService
    from app.services.dashboard_service import DashboardService
    
    work_first_map = DashboardService.get_first_workowanie_map(date.today(), 'PSD')
    print('work_first_map:', work_first_map)
    
    allowed = WorkowanieQueueService.get_allowed_start_ids(date.today(), 'PSD', work_first_map)
    print('ALLOWED:', allowed)
