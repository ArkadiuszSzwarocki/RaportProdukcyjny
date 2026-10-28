# cspell:words calkowita
"""Opening unpacked balance for source orders included in a daily report."""
from app.db import get_table_name

def load_opening_buffer(connection,day,line):
    table=get_table_name('plan_produkcji',line)
    batches=get_table_name('szarze',line)
    doses=get_table_name('dosypki',line)
    pallets=get_table_name('palety_workowanie',line)
    cursor=connection.cursor(dictionary=True)
    try:
        cursor.execute(f"SELECT DISTINCT p.id,p.zasyp_id FROM {table} p WHERE p.data_planu=%s OR p.id IN (SELECT plan_id FROM {batches} WHERE DATE(data_dodania)=%s UNION SELECT plan_id FROM {pallets} WHERE DATE(data_dodania)=%s)",(day,day,day))
        ids=sorted({int(row['zasyp_id'] or row['id']) for row in cursor.fetchall()})
        if not ids:return []
        placeholders=','.join(['%s']*len(ids))
        cursor.execute(f"SELECT id,produkt FROM {table} WHERE sekcja='Zasyp' AND id IN ({placeholders})",tuple(ids))
        sources=cursor.fetchall()
        result=[]
        for source in sources:
            pid=source['id']
            cursor.execute(f"SELECT COALESCE(SUM(waga),0) AS kg FROM {batches} WHERE plan_id=%s AND data_dodania < %s",(pid,day))
            made=float(cursor.fetchone()['kg'])
            cursor.execute(f"SELECT COALESCE(SUM(kg),0) AS kg FROM {doses} WHERE plan_id=%s AND potwierdzone=1 AND COALESCE(anulowana,0)=0 AND data_potwierdzenia < %s",(pid,day))
            made+=float(cursor.fetchone()['kg'])
            if line=='AGRO':
                cursor.execute("SELECT COALESCE(SUM(waga_calkowita),0) AS kg FROM wiaderka_maluchy WHERE plan_id=%s AND UPPER(linia)='AGRO' AND status='wrzucone_do_mieszalnika' AND data_zasypania < %s",(pid,day))
                made+=float(cursor.fetchone()['kg'])
            cursor.execute(f"SELECT COALESCE(SUM(p.waga),0) AS kg FROM {pallets} p JOIN {table} w ON w.id=p.plan_id WHERE w.zasyp_id=%s AND p.data_dodania < %s",(pid,day))
            packed=float(cursor.fetchone()['kg'])
            if made>packed+.001:result.append(dict(id=pid,product=source['produkt'],made=round(made,3),packed=round(packed,3),remaining=round(made-packed,3)))
        return result
    finally:cursor.close()
