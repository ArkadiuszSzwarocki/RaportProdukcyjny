# cspell:words calkowita
"""Daily recorded output per order, shared by shift HTML and PDF."""
from collections import defaultdict
from app.db import get_table_name

def load_daily_progress(connection,day,line,order_ids=None):
    table=get_table_name('plan_produkcji',line)
    batches=get_table_name('szarze',line)
    doses=get_table_name('dosypki',line)
    pallets=get_table_name('palety_workowanie',line)
    cursor=connection.cursor(dictionary=True)
    try:
        if order_ids is None:
            cursor.execute(f"SELECT id FROM {table} WHERE data_planu=%s OR id IN (SELECT plan_id FROM {batches} WHERE DATE(data_dodania)=%s UNION SELECT plan_id FROM {pallets} WHERE DATE(data_dodania)=%s)",(day,day,day))
            order_ids=[row['id'] for row in cursor.fetchall()]
        ids=list(dict.fromkeys(int(value) for value in order_ids))
        if not ids:return []
        placeholders=','.join(['%s']*len(ids))
        cursor.execute(f"SELECT p.id,p.produkt,p.sekcja,p.tonaz,z.tonaz_rzeczywisty AS source_kg FROM {table} p LEFT JOIN {table} z ON z.id=p.zasyp_id AND z.sekcja='Zasyp' WHERE p.id IN ({placeholders}) AND p.sekcja IN ('Zasyp','Workowanie') ORDER BY p.real_start IS NULL,p.real_start,p.real_stop,p.id",tuple(ids))
        orders=cursor.fetchall();result=[]
        for row in orders:
            daily=defaultdict(float)
            sources=[(batches,'waga','data_dodania','1=1'),(doses,'kg','data_potwierdzenia','potwierdzone=1 AND COALESCE(anulowana,0)=0')] if row['sekcja']=='Zasyp' else [(pallets,'waga','data_dodania','1=1')]
            if row['sekcja']=='Zasyp' and line=='AGRO':sources.append(('wiaderka_maluchy','waga_calkowita','data_zasypania',"UPPER(linia)='AGRO' AND status='wrzucone_do_mieszalnika'"))
            for source,weight,event_time,condition in sources:
                cursor.execute(f"SELECT DATE({event_time}) AS day,SUM({weight}) AS kg FROM {source} WHERE plan_id=%s AND {event_time}<DATE_ADD(%s,INTERVAL 1 DAY) AND {condition} GROUP BY DATE({event_time})",(row['id'],day))
                for event in cursor.fetchall():daily[str(event['day'])]+=float(event['kg'] or 0)
            plan=row['source_kg'] if row['sekcja']=='Workowanie' else row['tonaz']
            result.append(dict(id=row['id'],product=row['produkt'],section=row['sekcja'],plan=float(plan) if plan is not None else None,daily={date:round(kg,3) for date,kg in sorted(daily.items())},total=round(sum(daily.values()),3)))
        return result
    finally:cursor.close()
