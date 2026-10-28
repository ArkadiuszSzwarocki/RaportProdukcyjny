"""Confirmed order timing, without reconstructing missing shifts or pauses."""
from datetime import datetime

def format_datetime(value):
    if value is None or str(value) in ('NaT','None','nan',''):return '—'
    try:
        parsed=value if isinstance(value,datetime) else datetime.fromisoformat(str(value))
        return parsed.strftime('%d.%m.%Y %H:%M')
    except (ValueError,TypeError):return '—'

def format_duration(value):
    try:
        seconds=int(value)
        if seconds<0:return 'brak danych'
        return f'{seconds//3600} godz. {seconds%3600//60:02d} min {seconds%60:02d} s'
    except (ValueError,TypeError,OverflowError):return 'brak danych'

def load_order_times(connection,table,day,order_ids=None):
    cursor=connection.cursor(dictionary=True)
    try:
        cursor.execute(f'SHOW COLUMNS FROM {table}')
        columns={row['Field'] for row in cursor.fetchall()}
        saved='czas_pracy_sekundy' if 'czas_pracy_sekundy' in columns else 'NULL AS czas_pracy_sekundy'
        resumed='ostatnie_wznowienie' if 'ostatnie_wznowienie' in columns else 'NULL AS ostatnie_wznowienie'
        if order_ids is not None:
            ids=list(dict.fromkeys(int(value) for value in order_ids))
            if not ids:return []
            condition='real_start >= %s AND real_start < DATE_ADD(%s,INTERVAL 1 DAY) AND id IN ('+','.join(['%s']*len(ids))+')'
            params=(day,day,*ids)
        else:
            condition='real_start >= %s AND real_start < DATE_ADD(%s,INTERVAL 1 DAY)'
            params=(day,day)
        cursor.execute(f'SELECT id,produkt,sekcja,real_start,real_stop,status,{saved},{resumed} FROM {table} WHERE {condition} ORDER BY real_start IS NULL,real_start,real_stop IS NULL,real_stop,id',params)
        return [dict(id=row['id'],product=row['produkt'],section=row['sekcja'],start=format_datetime(row['real_start']),stop=format_datetime(row['real_stop']),status=row['status'],saved=confirmed_work_label(row),elapsed=elapsed_label(row),resumed=format_datetime(row['ostatnie_wznowienie'])) for row in cursor.fetchall()]
    finally:cursor.close()


def chronological_key(start,stop,identifier=0):
    def parsed(value):
        try:return datetime.fromisoformat(str(value)) if value is not None else datetime.max
        except (ValueError,TypeError):return datetime.max
    return parsed(start),parsed(stop),int(identifier or 0)


def confirmed_work_label(row):
    value=row.get('czas_pracy_sekundy')
    if value is None or (not value and row.get('real_start')):return 'brak zapisanego czasu pracy'
    return format_duration(value)

def elapsed_label(row):
    try:
        start=datetime.fromisoformat(str(row['real_start']))
        stop=datetime.fromisoformat(str(row['real_stop']))
        return format_duration((stop-start).total_seconds())
    except (ValueError,TypeError,KeyError):return 'brak zamkniętego przedziału'
