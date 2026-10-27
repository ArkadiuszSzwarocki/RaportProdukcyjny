/* Periodic analytics: local charts, stage selection and month drill-down. */
(function () {
    'use strict';
    const element = document.getElementById('periodicReportData');
    if (!element || typeof Chart === 'undefined') return;
    let report = JSON.parse(element.textContent);
    const charts = [];
    const rendered = new Set();
    const zoomDialog=document.getElementById('periodChartDialog');
    let zoom=null,ownsFullscreen=false;
    function closeZoom() {if(zoomDialog.open) zoomDialog.close();restoreZoom();}
    function restoreZoom() {
        if (!zoom) return;
        const previous=zoom;zoom=null;
        previous.anchor.parentNode.insertBefore(previous.wrapper,previous.anchor);
        previous.anchor.remove();
        zoomDialog.querySelector('[data-zoom-help]')?.remove();
        if (ownsFullscreen && document.fullscreenElement) document.exitFullscreen().catch(()=>{});
        ownsFullscreen=false;
        requestAnimationFrame(()=>{Chart.getChart(previous.canvas)?.resize();previous.button.focus({preventScroll:true});});
    }
    zoomDialog.addEventListener('close',restoreZoom);
    document.getElementById('closePeriodChart').addEventListener('click',closeZoom);
    document.addEventListener('fullscreenchange',()=>{if(ownsFullscreen && !document.fullscreenElement) closeZoom();});
    document.querySelectorAll('[data-chart-expand]').forEach(button=>{
        const canvas=document.getElementById(button.dataset.chartExpand);
        if (!canvas) return;
        const wrapper=canvas.parentElement;
        button.addEventListener('click',()=>{
            if (zoom) return;
            const anchor=document.createComment('chart-position');wrapper.before(anchor);
            zoom={wrapper,anchor,button,canvas};
            const help=wrapper.closest('.pr-card')?.querySelector('.pr-chart-help');
            if(help){const copy=help.cloneNode(true);copy.removeAttribute('open');copy.dataset.zoomHelp='true';document.getElementById('closePeriodChart').before(copy);}
            document.getElementById('periodChartTitle').textContent=canvas.getAttribute('aria-label');
            document.getElementById('periodChartContent').appendChild(wrapper);
            zoomDialog.showModal();
            if (!document.fullscreenElement && document.documentElement.requestFullscreen) {
                document.documentElement.requestFullscreen().then(()=>{ownsFullscreen=true;if(!zoomDialog.open) {document.exitFullscreen().catch(()=>{});ownsFullscreen=false;}}).catch(()=>{});
            }
            requestAnimationFrame(()=>Chart.getChart(canvas)?.resize());
        });
    });
    window.addEventListener('rp:navigation-start',closeZoom);
    window.addEventListener('beforeprint',closeZoom);

    const formatter = new Intl.NumberFormat('pl-PL', {maximumFractionDigits: 1});
    const teal = '#089a8e', blue = '#3778ea', gray = '#b6c7db';
    const empty = {id: 'periodEmpty', afterDraw(chart) {
        if (chart.data.datasets.some(series => series.data.some(value => value !== null && value !== undefined))) return;
        const {ctx,chartArea} = chart;
        if (!chartArea) return;
        ctx.save();ctx.textAlign = 'center';ctx.fillStyle = '#718399';ctx.font = '14px sans-serif';
        ctx.fillText('Brak danych dla wybranych filtrów', (chartArea.left+chartArea.right)/2, (chartArea.top+chartArea.bottom)/2);ctx.restore();
    }};
    const weekendBands={id:'periodWeekends',beforeDraw(chart){
        const dates=chart.config.options.weekendDates;
        const area=chart.chartArea,axis=chart.scales.x;
        if(!dates || !area || !axis) return;
        chart.ctx.save();chart.ctx.fillStyle='rgba(250,204,21,0.18)';
        dates.forEach((date,index)=>{
            const [year,month,day]=date.split('-').map(Number);
            const weekday=new Date(year,month-1,day).getDay();
            if(weekday!==0 && weekday!==6) return;
            const center=axis.getPixelForValue(index);
            const previous=index>0?axis.getPixelForValue(index-1):center-(axis.getPixelForValue(index+1)-center);
            const next=index<dates.length-1?axis.getPixelForValue(index+1):center+(center-previous);
            const left=Math.max(area.left,(previous+center)/2),right=Math.min(area.right,(center+next)/2);
            chart.ctx.fillRect(left,area.top,right-left,area.bottom-area.top);
        });
        chart.ctx.restore();
    }};
    function chart(id, type, labels, datasets, extra = {}) {
        const canvas = document.getElementById(id);
        if (!canvas) return;
        const options = {responsive: true, maintainAspectRatio: false, animation: false,
            interaction: {mode: 'index',intersect: false},
            plugins: {legend: {position: 'bottom',labels: {usePointStyle:true,padding:18,font:{size:11}}},
                tooltip:{callbacks:{title:contexts=>{
                    const context=contexts[0],order=context?.dataset.orderInfo?.[context.dataIndex];
                    if(!order) return context?.label || '';
                    return [order.product+' · '+order.line,'Data planu: '+order.plan_date,'Zakończono: '+(order.finished_at || 'brak czasu zakończenia')];
                },label: context => context.dataset.label + ': ' + (context.raw===null?'brak danych':formatter.format(context.raw)),afterLabel: context => {const value=context.dataset.continuation?.[context.dataIndex];return value?'W tym kontynuacje: '+formatter.format(value)+' t':'';}}}},
            scales:{x:{grid:{display:false},ticks:{color:'#64748b',maxRotation:0,autoSkip:true}},
                y:{beginAtZero:true,grid:{color:'#edf1f6'},ticks:{color:'#64748b'}}},...extra};
        if (extra.weekendDates) {
            options.plugins.legend.labels.generateLabels=instance=>[
                ...Chart.defaults.plugins.legend.labels.generateLabels(instance),
                {text:'Weekendy — soboty i niedziele',fillStyle:'#fff3b0',strokeStyle:'#e9ca49',lineWidth:1,pointStyle:'rect',hidden:false,weekend:true}
            ];
            options.plugins.legend.onClick=(event,item,legend)=>{
                if (!item.weekend) Chart.defaults.plugins.legend.onClick(event,item,legend);
            };
        }
        const existing = Chart.getChart(canvas);
        if (existing) {existing.data={labels,datasets};existing.options=options;existing.update('none');}
        else charts.push(new Chart(canvas,{type,data:{labels,datasets},options,plugins:[empty,weekendBands]}));
    }
    function series(label,data,color,extra={}) {
        return {label,data,borderColor:color,backgroundColor:color,borderWidth:2,pointRadius:2,pointHoverRadius:5,
            tension:.2,spanGaps:false,...extra};
    }
    function monthUrl(month) {
        const url = new URL(window.location.href);
        url.searchParams.delete('format');url.searchParams.set('miesiac',month);
        url.searchParams.set('sekcja',document.getElementById('periodSectionInput').value);
        url.hash = 'period-details';return url;
    }
    function renderAnnual() {
    chart('periodAnnualChart','bar',report.months.map(name=>name.slice(0,3)),[
        series('Zasyp · t',report.annual.Zasyp.map(value=>value===null?null:value/1000),teal,{borderRadius:4}),
        series('Workowanie · t',report.annual.Workowanie.map(value=>value===null?null:value/1000),blue,{borderRadius:4})
    ],{onClick(_event,items){if(items.length) window.location.assign(monthUrl(items[0].index+1));},
        onHover(event,items){event.native.target.style.cursor=items.length?'pointer':'default';}});
    }
    renderAnnual();
    function renderSection(name) {
        if (rendered.has(name)) return;
        rendered.add(name);
        const data = report.sections[name], color = name==='Zasyp'?teal:blue;
        const labels = data.daily.map(row=>row.date.slice(8));
        const actual = data.daily.map(row=>row.actual===null?null:row.actual/1000);
        const plan = data.daily.map(row=>row.plan/1000);
        const dailySeries=[series('Plan zleceń · t',plan,gray,{borderRadius:3}),series('Wykonanie · t',actual,color,{borderRadius:3,continuation:data.daily.map(row=>(row.continuation||0)/1000)})];
        if (name==='Zasyp' && data.daily.some(row=>row.excel!==null)) dailySeries.push(series('Excel · t',data.daily.map(row=>row.excel===null?null:row.excel/1000),'#9b6bce',{borderRadius:3}));
        const staffStyle={type:'line',yAxisID:'people',showLine:true,tension:0,pointRadius:2,pointHoverRadius:4,spanGaps:false,order:0};
        if(report.line==='ALL'){
            dailySeries.push(series('Obsada AGRO · osoby',data.daily.map(row=>row.staff_by_hall?.AGRO??null),'#b45309',staffStyle));
            dailySeries.push(series('Obsada PSD · osoby',data.daily.map(row=>row.staff_by_hall?.PSD??null),'#7c3aed',{...staffStyle,borderDash:[5,3]}));
        }else dailySeries.push(series('Obsada '+report.line+' · osoby',data.daily.map(row=>row.staff_count??null),'#b45309',staffStyle));
        chart('daily'+name,'bar',labels,dailySeries,{weekendDates:data.daily.map(row=>row.date),scales:{
            x:{grid:{display:false},ticks:{color:'#64748b',maxRotation:0,autoSkip:true}},
            y:{beginAtZero:true,title:{display:true,text:'Masa · t'},grid:{color:'#edf1f6'}},
            people:{position:'right',beginAtZero:true,title:{display:true,text:'Obsada · osoby'},ticks:{precision:0},grid:{drawOnChartArea:false}}
        }});
        let planTotal=0, actualTotal=0;
        const cumulativePlan=plan.map(value=>planTotal+=value);
        const cumulativeActual=data.daily.map(row=>{
            if (row.actual===null && row.plan>0) return null;
            actualTotal+=(row.actual || 0)/1000;
            return data.count-data.missing_actual>0?actualTotal:null;
        });
        chart('cumulative'+name,'line',labels,[series('Plan · t',cumulativePlan,gray,{borderDash:[5,4],pointRadius:0}),
            series('Wykonanie · t',cumulativeActual,color,{pointRadius:0,fill:true,backgroundColor:color+'12'})],{weekendDates:data.daily.map(row=>row.date)});
        chart('learning'+name,'line',data.learning.map(row=>[(row.product || row.label).length>28?(row.product || row.label).slice(0,26)+'…':(row.product || row.label),(row.date || '').split('-').reverse().join('.')+' · '+(row.line || '')]),[
            series('Zlecenie · kg/h',data.learning.map(row=>row.rate),color,{borderWidth:1,pointRadius:3,orderInfo:data.learning}),
            series('Ostatnie 5 pomiarów · kg/h',data.learning.map(row=>row.rolling),'#e59b25',{pointRadius:0,borderWidth:2,orderInfo:data.learning}),
            series('Średnia narastająca · kg/h',data.learning.map(row=>row.cumulative),'#635bcb',{pointRadius:0,borderWidth:3,orderInfo:data.learning})],{scales:{x:{grid:{display:false},ticks:{autoSkip:true,maxTicksLimit:8,maxRotation:0,font:{size:10}}},y:{beginAtZero:true,grid:{color:'#edf1f6'}}}});
        chart('products'+name,'bar',data.products.map(row=>row.name),[series('Wykonanie · t',data.products.map(row=>row.kg/1000),color,{borderRadius:4})],{indexAxis:'y',
            scales:{x:{beginAtZero:true,grid:{color:'#edf1f6'}},y:{grid:{display:false},ticks:{font:{size:11}}}}});
        let elapsed=0;
        chart('downtime'+name,'bar',data.downtime.map(row=>row.category),[
            series('Przestój · min',data.downtime.map(row=>row.minutes),'#e59b25',{borderRadius:4,yAxisID:'y'}),
            series('Udział narastający · %',data.downtime.map(row=>{elapsed+=row.minutes;return data.downtime_minutes?elapsed/data.downtime_minutes*100:0;}),'#635bcb',{type:'line',yAxisID:'share'})
        ],{scales:{x:{grid:{display:false},ticks:{maxRotation:30,font:{size:10}}},y:{beginAtZero:true,grid:{color:'#edf1f6'}},
            share:{position:'right',min:0,max:100,grid:{drawOnChartArea:false},ticks:{callback:value=>value+'%'}}}});
    }
    function selectSection(name) {
        const stageMarker=document.getElementById('periodStageMarker');
        stageMarker.textContent=name;stageMarker.dataset.stage=name;stageMarker.setAttribute('aria-label','Aktualnie przeglądasz: '+name);
        document.querySelectorAll('[data-section]').forEach(button=>button.setAttribute('aria-selected',String(button.dataset.section===name)));
        for (const section of ['Zasyp','Workowanie']) document.getElementById('panel'+section).hidden=section!==name;
        document.getElementById('periodSectionInput').value=name;
        const url=new URL(window.location.href);url.searchParams.set('sekcja',name);window.history.replaceState(null,'',url);
        document.querySelectorAll('[data-month]').forEach(link=>link.href=monthUrl(link.dataset.month));
        renderSection(name);charts.forEach(item=>item.resize());
    }
    document.querySelectorAll('[data-section]').forEach(button=>button.addEventListener('click',()=>selectSection(button.dataset.section)));
    document.querySelectorAll('[data-order-search]').forEach(input=>input.addEventListener('input',()=>{
        const query=input.value.trim().toLocaleLowerCase('pl-PL');
        document.querySelectorAll('#details'+input.dataset.orderSearch+' tbody tr').forEach(row=>row.hidden=!row.textContent.toLocaleLowerCase('pl-PL').includes(query));
    }));
    function format(value,unit='',precision=1) {
        return value===null || value===undefined?'—':new Intl.NumberFormat('pl-PL',{minimumFractionDigits:precision,maximumFractionDigits:precision}).format(value)+(unit?' '+unit:'');
    }
    function filterDetails(input) {
        const query=input.value.trim().toLocaleLowerCase('pl-PL');
        document.querySelectorAll('#details'+input.dataset.orderSearch+' tbody tr').forEach(row=>row.hidden=!row.textContent.toLocaleLowerCase('pl-PL').includes(query));
    }
    function applyReport(next) {
        report=next;
        for (const name of ['Zasyp','Workowanie']) {
            const data=report.sections[name],panel=document.getElementById('panel'+name);
            document.querySelector('[data-summary-actual="'+name+'"]').textContent=format(data.actual===null?null:data.actual/1000,'t');
            document.querySelector('[data-summary-note="'+name+'"]').textContent=data.closed_count+' zakończonych · '+data.live_count+' w toku / zawieszonych'+
                (data.change===null?'':' · '+(data.change>0?'+':'')+format(data.change,'%')+' miesiąc do miesiąca');
            const values={actual:format(data.actual===null?null:data.actual/1000,'t'),coverage:(data.count-data.missing_actual)+' / '+data.count+' zleceń z pomiarem',
                plan:format(data.plan/1000,'t'),percent:'Wykonanie / plan okresu: '+format(data.percent,'%'),rate:format(data.rate,'kg/h'),
                timed:data.timed_count+' zleceń z masą i czasem',downtime:format(data.downtime_minutes===null?null:data.downtime_minutes/60,'h'),
                excel:name==='Zasyp'?'Rozliczenie Excel: '+format(data.excel===null?null:data.excel/1000,'t'):'Kategorie według rejestru Workowania',count:data.count+' zleceń · '+name};
            for (const [key,value] of Object.entries(values)) panel.querySelector('[data-stat="'+key+'"]').textContent=value;
            panel.querySelector('[data-empty]').hidden=data.count>0;
            const quality=panel.querySelector('[data-quality]');quality.hidden=!data.missing_actual&&!data.missing_durations&&!data.legacy_dates;
            quality.textContent='Kompletność danych: '+data.missing_actual+' zleceń bez wykonania, '+data.missing_durations+' przestojów bez czasu. Brakujących pomiarów nie zastępujemy planem.'+(data.legacy_dates?' '+data.legacy_dates+' zleceń bez pełnej historii dat produkcji — brakujące daty zastąpiono datą planu.':'');
            for (let index=0;index<12;index++) document.querySelector('[data-month-value="'+(index+1)+':'+name+'"]').textContent=(name==='Zasyp'?'Z ':'W ')+format(report.annual[name][index]===null?null:report.annual[name][index]/1000)+' t';
            const tbody=document.querySelector('#details'+name+' tbody');
            const rows=data.details.map(order=>{
                const row=document.createElement('tr');
                const cells=['#'+order.id,order.date,order.line,({'zakonczone':'Zakończone','w toku':'W toku','zawieszone':'Zawieszone'})[order.status]||order.status,order.product,format(order.plan,'',2),format(order.actual,'',2)];
                if (name==='Zasyp') cells.push(format(order.excel,'',0));
                cells.push(format(order.percent,'%'),format(order.hours),format(order.rate,'',0));
                for (const [index,value] of cells.entries()) {const cell=document.createElement('td');cell.textContent=value;if(index===6 && order.total_actual!==order.actual){const note=document.createElement('small');note.className='pr-order-total';note.textContent='Całe zlecenie: '+format(order.total_actual,'kg',0);cell.appendChild(note);}row.appendChild(cell);}
                return row;
            });
            if (!rows.length) {const row=document.createElement('tr'),cell=document.createElement('td');cell.colSpan=11;cell.textContent='Brak zleceń.';row.appendChild(cell);rows.push(row);}
            tbody.replaceChildren(...rows);
            filterDetails(document.querySelector('[data-order-search="'+name+'"]'));
        }
        document.getElementById('periodGeneratedAt').textContent='Wygenerowano: '+report.generated_at.replace('T',' ');
        const sections=[...rendered];rendered.clear();renderAnnual();sections.forEach(renderSection);
    }
    function fingerprint(data) {return JSON.stringify({...data,generated_at:null,revision:null});}
    let signature=fingerprint(report),events=null,scheduled=null,controller=null,pending=null,applied=report.revision,stopped=false;
    const liveStatus=document.getElementById('periodLiveStatus');
    async function refresh() {
        if (controller || document.hidden || stopped || pending===applied) return;
        const version=pending;
        let succeeded=false;
        controller=new AbortController();
        const timeout=setTimeout(()=>controller && controller.abort(),20000);
        try {
            const url=new URL(window.location.href);url.hash='';url.searchParams.set('format','json');
            const response=await fetch(url,{credentials:'same-origin',cache:'no-store',silent:true,signal:controller.signal});
            if (!response.ok) throw new Error('report '+response.status);
            const payload=await response.json();
            if (!payload.success || !payload.report) throw new Error('Invalid report');
            const next=fingerprint(payload.report);
            if (next!==signature) {applyReport(payload.report);signature=next;}
            applied=payload.report.revision;
            if (pending===version) pending=applied;
            succeeded=true;
            liveStatus.textContent='Na żywo · aktualne dane';
        } catch(error) {
            if (!stopped && !document.hidden) liveStatus.textContent='Aktualizacje chwilowo niedostępne';
        } finally {clearTimeout(timeout);controller=null;}
        if (succeeded && pending!==applied) schedule();
    }
    function schedule() {
        if (!scheduled) scheduled=setTimeout(()=>{scheduled=null;refresh();},250);
    }
    function connect() {
        if (stopped || events || document.hidden || !window.EventSource) return;
        events=new EventSource('/raporty_okresowe/events');
        events.addEventListener('warehouse-change',event=>{pending=event.data;if (pending!==applied) schedule();else liveStatus.textContent='Na żywo · aktualne dane';});
        events.addEventListener('error',()=>{liveStatus.textContent='Łączenie aktualizacji…';});
    }
    function disconnect() {
        if (events) events.close();events=null;
        if (scheduled) clearTimeout(scheduled);scheduled=null;
        if (controller) controller.abort();
    }
    function refreshAfterReturn() {
        if (controller || stopped || document.hidden) return;
        pending='return:'+Date.now();refresh();
    }
    document.addEventListener('visibilitychange',()=>{if(document.hidden)disconnect();else {connect();refreshAfterReturn();}});
    window.addEventListener('focus',refreshAfterReturn);
    window.addEventListener('rp:navigation-start',()=>{stopped=true;disconnect();});
    window.addEventListener('rp:navigation-cancelled',()=>{stopped=false;connect();});
    window.addEventListener('pagehide',()=>{stopped=true;disconnect();});
    window.addEventListener('pageshow',()=>{stopped=false;connect();});
    window.addEventListener('offline',disconnect);
    window.addEventListener('online',connect);
    connect();

    function preparePrint() {
        for (const name of ['Zasyp','Workowanie']) {document.getElementById('panel'+name).hidden=false;renderSection(name);}
        charts.forEach(item=>item.resize());
    }
    window.addEventListener('beforeprint',preparePrint);
    document.getElementById('printPeriodicReport').addEventListener('click',()=>{preparePrint();setTimeout(()=>window.print(),150);});
    window.addEventListener('afterprint',()=>selectSection(document.getElementById('periodSectionInput').value));
    selectSection(document.getElementById('periodSectionInput').value);
})();
