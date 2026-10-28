# cspell:words timespec calkowita
"""Read-only periodic production analytics with separate process stages."""
import calendar
import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from app.db import get_db_connection, get_table_name

MONTHS = ['Styczeń','Luty','Marzec','Kwiecień','Maj','Czerwiec','Lipiec','Sierpień','Wrzesień','Październik','Listopad','Grudzień']
SECTIONS = ('Zasyp', 'Workowanie')


def number(value):
    if value is None:
        return None
    result = float(value)
    return result if math.isfinite(result) and result >= 0 else None


def percentage(actual, planned):
    return round(actual / planned * 100, 1) if planned else None


def day(value):
    return value.date() if isinstance(value, datetime) else date.fromisoformat(str(value)[:10])


def timestamp(value):
    if not value:
        return None
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


def output_events(row):
    events = row.get('production_events')
    if events:
        return [(day(event['date']),number(event['kg'])) for event in events]
    return [(day(row['data_planu']),number(row.get('tonaz_rzeczywisty')))]


def in_period(row,year,month):
    dates=[day(row['data_planu'])]+[event_day for event_day,_ in output_events(row)]
    return any(value.year==year and value.month==month for value in dates)


def period_mass(row,year,month):
    events=output_events(row)
    values=[mass for event_day,mass in events if event_day.year==year and event_day.month==month]
    known=[mass for mass in values if mass is not None]
    return round(sum(known),3) if known else (0 if not values else None)



def scheduled_work_seconds(begin,end):
    """07:00-15:00 weekdays; explicit START/STOP retain recorded overtime."""
    if not begin or not end or end<=begin:return None
    current=begin.date();total=0
    while current<=end.date():
        if current.weekday()<5 or (begin.date()==end.date()==current):
            shift_start=datetime.combine(current,datetime.min.time()).replace(hour=7)
            shift_end=shift_start.replace(hour=15)
            if current==begin.date() and begin<shift_start:shift_start=begin
            if current==end.date() and end>shift_end:shift_end=end
            total+=max(0,(min(end,shift_end)-max(begin,shift_start)).total_seconds())
        current+=timedelta(days=1)
    return total or None

class PeriodicReportService:
    @staticmethod
    def load(year, month, line='AGRO', product='', include_live=True):
        lines = ('AGRO','PSD') if line == 'ALL' else (line,)
        if any(value not in ('AGRO','PSD') for value in lines):
            raise ValueError('Nieprawidłowa hala.')
        start = date(year-1,12,1)
        end = date(year+1,1,1)
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        orders, downtimes, warnings = [], [], []
        staffing = []
        try:
            for current_line in lines:
                table = get_table_name('plan_produkcji', current_line)
                cursor.execute(f'SHOW COLUMNS FROM {table}')
                columns = {row['Field'] for row in cursor.fetchall()}
                work_time = 'p.czas_pracy_sekundy' if 'czas_pracy_sekundy' in columns else 'NULL AS czas_pracy_sekundy'
                resumed_time = 'p.ostatnie_wznowienie' if 'ostatnie_wznowienie' in columns else 'NULL AS ostatnie_wznowienie'
                excel = 'p.zasyp_excel_kg' if 'zasyp_excel_kg' in columns else 'NULL AS zasyp_excel_kg'
                deleted = ' AND COALESCE(p.is_deleted,0)=0' if 'is_deleted' in columns else ''
                quality = " AND COALESCE(p.typ_zlecenia,'') != 'jakosc'" if 'typ_zlecenia' in columns else ''
                pallets = get_table_name('palety_workowanie',current_line)
                batch_table=get_table_name('szarze',current_line)
                dose_table=get_table_name('dosypki',current_line)
                related = f"LEFT JOIN {table} z ON p.zasyp_id=z.id AND z.sekcja='Zasyp'" if 'zasyp_id' in columns else ''
                linked = 'z.tonaz_rzeczywisty AS linked_zasyp_kg' if related else 'NULL AS linked_zasyp_kg'
                cursor.execute(f"SELECT p.id,p.data_planu,p.sekcja,p.produkt,p.tonaz,p.tonaz_rzeczywisty,p.status,p.real_start,p.real_stop,{work_time},{resumed_time},{excel},{linked},EXISTS(SELECT 1 FROM {batch_table} recorded_batch WHERE recorded_batch.plan_id=p.id) AS has_recorded_batches FROM {table} p {related} WHERE ((p.data_planu >= %s AND p.data_planu < %s) OR p.id IN (SELECT plan_id FROM {pallets} WHERE data_dodania >= %s AND data_dodania < %s UNION SELECT plan_id FROM {batch_table} WHERE data_dodania >= %s AND data_dodania < %s UNION SELECT plan_id FROM {dose_table} WHERE data_potwierdzenia >= %s AND data_potwierdzenia < %s UNION SELECT plan_id FROM wiaderka_maluchy WHERE data_zasypania >= %s AND data_zasypania < %s AND UPPER(linia)=%s)) AND p.sekcja IN ('Zasyp','Workowanie'){deleted}{quality} ORDER BY p.data_planu,p.id",(start,end,start,end,start,end,start,end,start,end,current_line))
                line_orders=[dict(row,linia=current_line) for row in cursor.fetchall()]
                cursor.execute(f'SELECT plan_id,DATE(data_dodania) AS production_date,SUM(waga) AS kg FROM {pallets} WHERE data_dodania >= %s AND data_dodania < %s GROUP BY plan_id,DATE(data_dodania)',(start,end))
                pallet_events=defaultdict(list)
                for event in cursor.fetchall():
                    pallet_events[event['plan_id']].append(dict(date=day(event['production_date']).isoformat(),kg=number(event['kg'])))
                for row in line_orders:
                    if row['sekcja']=='Workowanie':
                        linked_mass=number(row.get('linked_zasyp_kg'))
                        if linked_mass:
                            row['tonaz']=linked_mass
                        row['production_events']=pallet_events.get(row['id'],[])
                batches=get_table_name('szarze',current_line)
                doses=get_table_name('dosypki',current_line)
                sources=[]
                event_args=[]
                for source,alias,weight,event_time,condition in [
                    (batches,'b','waga','data_dodania','1=1'),
                    (doses,'d','kg','data_potwierdzenia','d.potwierdzone=1 AND COALESCE(d.anulowana,0)=0'),
                    ('wiaderka_maluchy','w','waga_calkowita','data_zasypania',"w.status='wrzucone_do_mieszalnika' AND UPPER(w.linia)=%s")]:
                    sources.append(f'SELECT {alias}.plan_id,DATE(COALESCE({alias}.{event_time},p.data_planu)) AS production_date,{alias}.{weight} AS kg,({alias}.{event_time} IS NULL) AS fallback_date FROM {source} {alias} JOIN {table} p ON p.id={alias}.plan_id WHERE COALESCE({alias}.{event_time},p.data_planu) >= %s AND COALESCE({alias}.{event_time},p.data_planu) < %s AND {condition}')
                    event_args.extend([start,end])
                    if alias=='w':event_args.append(current_line)
                cursor.execute('SELECT plan_id,production_date,ROUND(SUM(kg),3) AS kg,SUM(fallback_date) AS fallback_dates FROM ('+' UNION ALL '.join(sources)+') production_events GROUP BY plan_id,production_date',tuple(event_args))
                batch_events=defaultdict(list)
                for event in cursor.fetchall():
                    batch_events[event['plan_id']].append(dict(date=day(event['production_date']).isoformat(),kg=round(number(event['kg']) or 0,3),fallback_date=bool(event.get('fallback_dates'))))
                for row in line_orders:
                    if row['sekcja']=='Zasyp':row['production_events']=batch_events.get(row['id'],[])
                orders.extend(line_orders)
                for section, table_name in [('Zasyp','przestoje_zasyp'),('Workowanie','przestoje_produkcyjne')]:
                    try:
                        cursor.execute(f'SELECT data_przestoju,kategoria,produkt,czas_trwania_min FROM {table_name} WHERE linia=%s AND data_przestoju >= %s AND data_przestoju < %s',(current_line,start,end))
                        downtimes.extend(dict(row,sekcja=section,linia=current_line) for row in cursor.fetchall())
                    except Exception as error:
                        if getattr(error,'errno',None) != 1146:
                            raise
                        warnings.append('Brak rejestru przestojów: ' + current_line + ' / ' + section)
            try:
                cursor.execute("SELECT DISTINCT DATE(oz.data_wpisu) AS date,oz.sekcja,oz.pracownik_id,UPPER(COALESCE(NULLIF(oz.linia,''),'PSD')) AS linia FROM obsada_zmiany oz JOIN pracownicy p ON p.id=oz.pracownik_id WHERE oz.data_wpisu >= %s AND oz.data_wpisu < %s",(date(year,month,1),date(year+1,1,1) if month==12 else date(year,month+1,1)))
                staffing=[row for row in cursor.fetchall() if row['linia'] in lines]
            except Exception as error:
                if getattr(error,'errno',None)!=1146:raise
                warnings.append('Brak danych obsady zmian.')
        finally:
            cursor.close()
            connection.close()
        return PeriodicReportService.build(orders,downtimes,year,month,line,product,warnings,include_live,staffing)

    @staticmethod
    def build(orders,downtimes,year,month,line='AGRO',product='',warnings=None,include_live=True,staffing=None):
        orders=[row for row in orders if row.get('sekcja')!='Zasyp' or row.get('has_recorded_batches',True)]
        products = sorted({str(row.get('produkt') or '') for row in orders if day(row['data_planu']).year == year or any(event_day.year==year for event_day,_ in output_events(row))})
        if product:
            orders = [row for row in orders if str(row.get('produkt') or '') == product]
            downtimes = [row for row in downtimes if str(row.get('produkt') or '') == product]
        start = date(year,month,1)
        previous = start-timedelta(days=1)
        days = calendar.monthrange(year,month)[1]
        statuses = {'zakonczone','w toku','zawieszone'} if include_live else {'zakonczone'}
        completed = [row for row in orders if str(row.get('status') or '').strip().lower() in statuses]
        result = dict(year=year,month=month,month_name=MONTHS[month-1],line=line,product=product,products=products,
            months=MONTHS,include_live=include_live,warnings=warnings or [],sections={},annual={},generated_at=datetime.now().isoformat(timespec='minutes'))
        for section in SECTIONS:
            all_rows = [row for row in completed if row['sekcja'] == section]
            selected = [row for row in all_rows if in_period(row,year,month)]
            previous_rows = [row for row in all_rows if in_period(row,previous.year,previous.month)]
            monthly = []
            for selected_month in range(1,13):
                rows = [row for row in all_rows if in_period(row,year,selected_month)]
                known = [period_mass(row,year,selected_month) for row in rows if period_mass(row,year,selected_month) is not None]
                monthly.append(round(sum(known),3) if known else None)
            result['annual'][section] = monthly
            daily = [dict(date=date(year,month,n).isoformat(),plan=0,actual=None,excel=None,continuation=0) for n in range(1,days+1)]
            people=defaultdict(set)
            people_by_hall=defaultdict(set)
            for assignment in staffing or []:
                role=str(assignment.get('sekcja') or '').strip().lower()
                assigned_section='Workowanie' if role in ('workowanie','operator workowania') else 'Zasyp' if role in ('zasyp','sterownia','operator sterowni') or role.startswith(('operator zasyp','zasyp ')) else None
                if assigned_section != section or assignment.get('linia') not in (('AGRO','PSD') if line=='ALL' else (line,)):continue
                assignment_day=day(assignment['date'])
                if assignment_day.year==year and assignment_day.month==month and assignment.get('pracownik_id') is not None:
                    people[assignment_day.isoformat()].add(assignment['pracownik_id'])
                    people_by_hall[(assignment_day.isoformat(),assignment['linia'])].add(assignment['pracownik_id'])
            for item in daily:
                item['staff_count']=len(people[item['date']]) if item['date'] in people else None
                item['staff_by_hall']={hall:len(people_by_hall[(item['date'],hall)]) if (item['date'],hall) in people_by_hall else None for hall in ('AGRO','PSD')}
            products_sum = defaultdict(float)
            details, learning, valid_times, hours_total, kg_total = [], [], [], 0, 0
            selected.sort(key=lambda row:(str(row.get('real_stop') or row['data_planu']),row['id']))
            for index,row in enumerate(selected,1):
                total_actual = number(row.get('tonaz_rzeczywisty'))
                actual = period_mass(row,year,month)
                plan = number(row.get('tonaz')) or 0
                excel = number(row.get('zasyp_excel_kg')) if section == 'Zasyp' else None
                plan_day=day(row['data_planu'])
                period_plan=plan if plan_day.year==year and plan_day.month==month else 0
                if period_plan:
                    daily[plan_day.day-1]['plan']+=period_plan
                for event_day,mass in output_events(row):
                    if event_day.year==year and event_day.month==month and mass is not None:
                        item=daily[event_day.day-1]
                        item['actual']=round((item['actual'] or 0)+mass,3)
                        if event_day!=plan_day:
                            item['continuation']+=mass
                if actual is not None:
                    products_sum[row.get('produkt') or 'Bez nazwy']+=actual
                if excel is not None and plan_day.year==year and plan_day.month==month:
                    item=daily[plan_day.day-1]
                    item['excel']=(item['excel'] or 0)+excel
                begin,end = timestamp(row.get('real_start')),timestamp(row.get('real_stop'))
                closed = str(row.get('status') or '').strip().lower() == 'zakonczone'
                elapsed_seconds=(end-begin).total_seconds() if closed and begin and end and end>begin else None
                recorded_seconds=number(row.get('czas_pracy_sekundy'))
                hours=None
                time_basis='Brak potwierdzonego czasu pracy'
                resumed=timestamp(row.get('ostatnie_wznowienie'))
                last_segment=(end-resumed).total_seconds() if end and resumed and end>=resumed else None
                complete=last_segment is None or (recorded_seconds is not None and recorded_seconds>=last_segment)
                if not complete:time_basis='Niepełny licznik czasu pracy — krótszy niż ostatni odcinek START–STOP'
                if closed and recorded_seconds and elapsed_seconds and recorded_seconds<=elapsed_seconds and complete:
                    hours=recorded_seconds/3600
                    time_basis='Zapisany czas pracy (bez pauz)'
                schedule_seconds=scheduled_work_seconds(begin,end) if closed else None
                if schedule_seconds and (hours is None or hours*3600>schedule_seconds):
                    hours=schedule_seconds/3600
                    time_basis='Wyliczony czas zmiany 07:00–15:00; zapisany STOP po 15:00 uwzględniony'
                rate = total_actual/hours if total_actual is not None and hours else None
                if rate is not None:
                    hours_total += hours
                    kg_total += total_actual
                    valid_times.append((total_actual,hours))
                recent = valid_times[-5:]
                if closed:
                    learning.append(dict(time_basis=time_basis,hours=round(hours,4) if hours else None,order=index,id=row['id'],product=row.get('produkt') or 'Bez nazwy',line=row['linia'],date=(end.date() if end else plan_day).isoformat(),plan_date=plan_day.isoformat(),finished_at=end.isoformat(timespec='minutes') if end else None,started_at=begin.isoformat(timespec='minutes') if begin else None,label=(row.get('produkt') or 'Bez nazwy')+' · '+(end.date() if end else plan_day).strftime('%d.%m.%Y')+' · '+row['linia'],rate=round(rate,2) if rate is not None else None,
                    cumulative=round(kg_total/hours_total,2) if rate is not None else None,
                    rolling=round(sum(pair[0] for pair in recent)/sum(pair[1] for pair in recent),2) if rate is not None else None))
                details.append(dict(id=row['id'],line=row['linia'],date=day(row['data_planu']).isoformat(),product=row.get('produkt') or '',
                    status=str(row.get('status') or ''),plan=plan,period_plan=period_plan,actual=actual,total_actual=total_actual,excel=excel,hours=round(hours,2) if hours else None,rate=round(rate,2) if rate is not None else None,percent=percentage(total_actual,plan) if total_actual is not None else None))
            details.sort(key=lambda row:(row['date'],row['line'],row['id']))
            known = [row['actual'] for row in details if row['actual'] is not None]
            actual_total = sum(known) if known else None
            plan_total = sum(row['period_plan'] for row in details)
            previous_known = [period_mass(row,previous.year,previous.month) for row in previous_rows if period_mass(row,previous.year,previous.month) is not None]
            previous_total = sum(previous_known) if previous_known else None
            month_change = round((actual_total/previous_total-1)*100,1) if actual_total is not None and previous_total and len(known)==len(selected) and len(previous_known)==len(previous_rows) else None
            outages = defaultdict(float)
            missing_durations = 0
            for row in downtimes:
                if row['sekcja'] == section and day(row['data_przestoju']).year == year and day(row['data_przestoju']).month == month:
                    duration = number(row.get('czas_trwania_min'))
                    if duration is None: missing_durations += 1
                    else: outages[row.get('kategoria') or 'Inne'] += duration
            ordered_outages = sorted(outages.items(),key=lambda pair:pair[1],reverse=True)
            total_downtime = sum(outages.values())
            downtime_available = not any(warning.endswith(' / '+section) for warning in (warnings or []))
            result['sections'][section] = dict(count=len(selected),closed_count=sum(row['status']=='zakonczone' for row in selected),live_count=sum(row['status'] in ('w toku','zawieszone') for row in selected),plan=round(plan_total,3),actual=round(actual_total,3) if actual_total is not None else None,
                percent=percentage(actual_total,plan_total) if actual_total is not None and len(known)==len(selected) else None,change=month_change,
                missing_actual=len(selected)-len(known),legacy_dates=sum((not row.get('production_events') and (number(row.get('tonaz_rzeczywisty')) or 0)>0) or any(event.get('fallback_date') for event in row.get('production_events',[])) for row in selected),timed_count=len(valid_times),rate=round(kg_total/hours_total,1) if hours_total else None,
                excel=sum(row['excel'] for row in details if row['excel'] is not None) if any(row['excel'] is not None for row in details) else None,
                daily=daily,learning=learning,products=[dict(name=name,kg=round(kg,3)) for name,kg in sorted(products_sum.items(),key=lambda pair:pair[1],reverse=True)[:8]],
                downtime=[dict(category=name,minutes=minutes) for name,minutes in ordered_outages],downtime_minutes=total_downtime if downtime_available else None,
                missing_durations=missing_durations,details=details)
        return result
