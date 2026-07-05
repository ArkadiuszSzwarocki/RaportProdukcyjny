from flask import current_app
from app.db import get_table_name
from app.services.notification_service import notify_workers_about_plan_change

class DodajPlanCommand:
    """Command to handle adding a standard plan."""
    
    @staticmethod
    def execute(conn, cursor, linia, data_planu, produkt, tonaz, sekcja, typ, typ_opakowania, session):
        table_plan = get_table_name('plan_produkcji', linia)
        
        try:
            cursor.execute(
                f'SELECT id, sekcja FROM {table_plan} WHERE data_planu=%s AND produkt=%s AND (is_deleted=0 OR is_deleted IS NULL) LIMIT 1',
                (data_planu, produkt),
            )
            existing = cursor.fetchone()
            if existing:
                return False, f'Zlecenie dla {produkt} już istnieje na dzień {data_planu}. Zmień ilość istniejącego zlecenia zamiast tworzyć nowe.', existing[0]
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass

        status = 'zaplanowane'
        cursor.execute(f'SELECT MAX(kolejnosc) FROM {table_plan} WHERE data_planu=%s AND sekcja=%s', (data_planu, sekcja))
        res = cursor.fetchone()
        nk = (res[0] if res and res[0] else 0) + 1
        
        typ_opak_db = None if sekcja == 'Czyszczenie' else typ_opakowania
        zasyp_plan_id = None
        
        if sekcja == 'Czyszczenie':
            cursor.execute(
                f'INSERT INTO {table_plan} (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, typ_opakowania, tonaz_rzeczywisty) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)',
                (data_planu, produkt, tonaz, status, 'Zasyp', nk, typ, None, 0),
            )
            zasyp_plan_id = cursor.lastrowid
            
            cursor.execute(f"SELECT MAX(kolejnosc) FROM {table_plan} WHERE data_planu=%s AND sekcja IN ('Workowanie', 'Czyszczenie')", (data_planu,))
            res_w = cursor.fetchone()
            nk_w = (res_w[0] if res_w and res_w[0] else 0) + 1
            cursor.execute(
                f'INSERT INTO {table_plan} (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, typ_opakowania, tonaz_rzeczywisty, zasyp_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                (data_planu, produkt, 0, status, 'Workowanie', nk_w, typ, None, 0, zasyp_plan_id),
            )
        else:
            cursor.execute(
                f'INSERT INTO {table_plan} (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji, typ_opakowania, tonaz_rzeczywisty) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)',
                (data_planu, produkt, tonaz, status, sekcja, nk, typ, typ_opak_db, 0),
            )
            zasyp_plan_id = cursor.lastrowid if hasattr(cursor, 'lastrowid') else None
            
        notify_workers_about_plan_change(
            plan_context={
                'id': zasyp_plan_id,
                'produkt': produkt,
                'sekcja': sekcja,
                'data_planu': data_planu,
            },
            action_label='dodał',
            author_name=session.get('imie_nazwisko') or session.get('login'),
            conn=conn,
            cursor=cursor,
            created_by_user_id=session.get('user_id'),
            linia=linia,
        )

        return True, '', zasyp_plan_id
