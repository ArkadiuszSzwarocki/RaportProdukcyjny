# cspell:words timespec
"""Read-only batch-stage timing report; no schema repair on report requests."""
from collections import defaultdict
from datetime import datetime, timedelta
from app.db import get_db_connection, get_table_name
from app.services.zasyp_etapy_support import _build_sequence_for_szarza, _etap_display_name


def as_datetime(value):
    return value if isinstance(value,datetime) else datetime.fromisoformat(str(value)) if value else None


def duration_text(seconds):
    if seconds is None:return '—'
    seconds=int(seconds)
    return f'{seconds//3600:02d}:{seconds%3600//60:02d}:{seconds%60:02d}'


class DosingTimeReportService:
    @staticmethod
    def load(start,end,line='AGRO',selected='',now=None):
        if line not in ('AGRO','PSD','ALL'):raise ValueError('Nieprawidłowa hala.')
        stop=end+timedelta(days=1)
        now=now or datetime.now()
        connection=get_db_connection();cursor=connection.cursor(dictionary=True)
        orders=[];stages=[]
        try:
            cursor.execute('SHOW COLUMNS FROM zasyp_etapy')
            columns={row['Field'] for row in cursor.fetchall()}
            optional=','.join('e.'+field if field in columns else default+' AS '+field for field,default in [('is_paused','0'),('pauza_start','NULL'),('pauza_sekundy','0'),('powod_opoznienia','NULL')])
            for current_line in (('AGRO','PSD') if line=='ALL' else (line,)):
                table=get_table_name('plan_produkcji',current_line)
                cursor.execute(f"SELECT p.id,p.produkt,p.data_planu,p.status FROM {table} p WHERE p.sekcja='Zasyp' AND COALESCE(p.is_deleted,0)=0 AND p.data_planu >= %s AND p.data_planu < %s ORDER BY p.data_planu,p.id",(start,stop))
                current_orders=[dict(row,linia=current_line) for row in cursor.fetchall()]
                orders.extend(current_orders)
                selected_orders=[row for row in current_orders if not selected or selected==current_line+':'+str(row['id'])]
                if not selected_orders:continue
                placeholders=','.join(['%s']*len(selected_orders))
                cursor.execute(f'SELECT e.id,e.plan_id,COALESCE(e.szarza_nr,1) AS szarza_nr,e.etap,e.czas_start,e.czas_stop,e.start_login,e.stop_login,{optional} FROM zasyp_etapy e WHERE e.linia=%s AND e.etap>0 AND e.plan_id IN ({placeholders}) ORDER BY e.plan_id,e.szarza_nr,e.czas_start,e.id',(current_line,*[row['id'] for row in selected_orders]))
                stages.extend(dict(row,linia=current_line) for row in cursor.fetchall())
        finally:
            cursor.close();connection.close()
        report=DosingTimeReportService.build(orders,stages,selected,now)
        report.update(start=start.isoformat(),end=end.isoformat(),line=line)
        return report

    @staticmethod
    def build(orders,stages,selected='',now=None):
        now=now or datetime.now()
        options=[dict(key=row['linia']+':'+str(row['id']),name=row['produkt'],date=str(row['data_planu'])[:10],line=row['linia']) for row in orders]
        grouped=defaultdict(list)
        for row in stages:
            if int(row.get('etap') or 0)>0:grouped[(row['linia'],row['plan_id'],int(row.get('szarza_nr') or 1))].append(row)
        output=[];stage_summary=defaultdict(lambda:dict(work=0,pause=0,count=0));batch_chart=[]
        for order in sorted(orders,key=lambda row:(str(row['data_planu']),row['linia'],row['id'])):
            key=order['linia']+':'+str(order['id'])
            if selected and selected!=key:continue
            batches=[]
            for (current_line,plan_id,batch),rows in sorted(grouped.items()):
                if (current_line,plan_id)!=(order['linia'],order['id']):continue
                sequence=_build_sequence_for_szarza(current_line,[int(row['etap']) for row in rows])
                sequence.extend(sorted({int(row['etap']) for row in rows}-set(sequence)))
                ranks={stage:index+1 for index,stage in enumerate(sequence)}
                chronological=sorted([row for row in rows if row.get('czas_start')],key=lambda row:(as_datetime(row['czas_start']),row['id']))
                actual_ranks={row['id']:index+1 for index,row in enumerate(chronological)}
                entries=[]
                for row in sorted(rows,key=lambda row:(ranks[int(row['etap'])],row['id'])):
                    begin=as_datetime(row.get('czas_start'));finish=as_datetime(row.get('czas_stop'))
                    endpoint=finish or now
                    gross=pause=work=None;issue=''
                    state='Zakończony' if begin and finish else 'W pauzie' if begin and row.get('is_paused') else 'W toku' if begin else 'Brak START'
                    if begin and endpoint>=begin:
                        gross=int((endpoint-begin).total_seconds())
                        pause=max(0,int(row.get('pauza_sekundy') or 0))
                        pause_start=as_datetime(row.get('pauza_start'))
                        if row.get('is_paused') and pause_start:pause+=max(0,int((endpoint-max(begin,pause_start)).total_seconds()))
                        if row.get('is_paused') and not pause_start:issue='Brak początku aktywnej pauzy'
                        elif pause>gross:issue='Zapisane pauzy przekraczają czas etapu'
                        else:work=gross-pause
                    elif begin:issue='STOP jest wcześniejszy niż START'
                    elif finish:issue='Zapisany STOP bez START'
                    stage=int(row['etap']);label=_etap_display_name(current_line,stage)
                    code=str(stage)
                    if current_line=='AGRO' and len(code)>1 and code[0] in ('3','4'):code=code[0]+'.'+str(int(code[1:])+1)
                    entry=dict(id=row['id'],sequence=ranks[stage],actual_sequence=actual_ranks.get(row['id']),code=code,name=label,
                        start=begin.isoformat(sep=' ') if begin else None,stop=finish.isoformat(sep=' ') if finish else None,
                        gross_s=gross,pause_s=pause,work_s=work,gross=duration_text(gross),pause=duration_text(pause),work=duration_text(work),
                        state=state,live=bool(begin and not finish),issue=issue,start_login=row.get('start_login') or '—',stop_login=row.get('stop_login') or '—',reason=row.get('powod_opoznienia') or '')
                    entries.append(entry)
                    if work is not None:
                        summary=stage_summary[current_line+' · '+code+' '+label]
                        summary['work']+=work;summary['pause']+=pause or 0;summary['count']+=1
                gross_sum=sum(row['gross_s'] or 0 for row in entries)
                pause_sum=sum(row['pause_s'] or 0 for row in entries)
                work_sum=sum(row['work_s'] or 0 for row in entries)
                timestamps=[as_datetime(row['start']) for row in entries if row['start']]
                last_times=[as_datetime(row['stop']) if row['stop'] else now for row in entries if row['start']]
                elapsed=int((max(last_times)-min(timestamps)).total_seconds()) if timestamps and last_times and max(last_times)>=min(timestamps) else None
                batch_data=dict(number=batch,stages=entries,gross_s=gross_sum,pause_s=pause_sum,work_s=work_sum,gross=duration_text(gross_sum),pause=duration_text(pause_sum),work=duration_text(work_sum),elapsed=duration_text(elapsed),live=any(row['live'] for row in entries),missing=sum(row['work_s'] is None for row in entries))
                batches.append(batch_data)
                batch_chart.append(dict(name=order['produkt'],date=str(order['data_planu'])[:10],line=order['linia'],number=batch,label=order['produkt']+' · '+str(order['data_planu'])[:10]+' · szarża '+str(batch),minutes=round(work_sum/60,2),start=min(timestamps).isoformat() if timestamps else str(order['data_planu'])))
            output.append(dict(key=key,id=order['id'],name=order['produkt'],date=str(order['data_planu'])[:10],line=order['linia'],status=order['status'],batches=batches,
                work=duration_text(sum(batch['work_s'] for batch in batches)),gross=duration_text(sum(batch['gross_s'] for batch in batches)),pause=duration_text(sum(batch['pause_s'] for batch in batches))))
        all_stages=[stage for order in output for batch in order['batches'] for stage in batch['stages']]
        return dict(options=options,orders=output,selected=selected,generated_at=now.isoformat(sep=' ',timespec='seconds'),
            kpis=dict(orders=len(output),batches=sum(len(order['batches']) for order in output),closed=sum(row['state']=='Zakończony' for row in all_stages),live=sum(row['live'] for row in all_stages),missing=sum(row['work_s'] is None for row in all_stages),work=duration_text(sum(row['work_s'] or 0 for row in all_stages))),
            stage_chart=[dict(name=name,**values) for name,values in stage_summary.items()],batch_chart=sorted(batch_chart,key=lambda row:row['start']))
