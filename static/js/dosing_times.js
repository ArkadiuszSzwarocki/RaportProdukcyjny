(function(){
    'use strict';
    const element=document.getElementById('dosingReportData');
    if(!element || typeof Chart==='undefined')return;
    const report=JSON.parse(element.textContent);
    function timeLabel(minutes) {
        const seconds=Math.max(0,Math.round(Number(minutes)*60));
        const hours=Math.floor(seconds/3600),mins=Math.floor(seconds%3600/60),secs=seconds%60;
        return (hours?hours+' godz. ':'')+mins+' min '+String(secs).padStart(2,'0')+' s';
    }
    function tooltipTime(context) {
        const label=context.dataset.label.replace(' · min','');
        return label+': '+timeLabel(context.parsed.y);
    }
    const charts=[];
    const options={responsive:true,maintainAspectRatio:false,animation:false,interaction:{mode:'index',intersect:false},plugins:{legend:{position:'bottom'}},scales:{x:{grid:{display:false},ticks:{autoSkip:true,maxTicksLimit:8,maxRotation:0,font:{size:10}}},y:{beginAtZero:true,grid:{color:'#edf1f6'}}}};
    charts.push(new Chart(document.getElementById('dosingStageChart'),{type:'bar',data:{labels:report.stage_chart.map(row=>[row.name.split(' · ')[0],row.name.split(' · ').slice(1).join(' · ').slice(0,30)]),datasets:[{label:'Praca · min',data:report.stage_chart.map(row=>row.work/60),backgroundColor:'#3778ea',borderRadius:3},{label:'Pauzy · min',data:report.stage_chart.map(row=>row.pause/60),backgroundColor:'#e9b34d',borderRadius:3}]},options:{...options,plugins:{...options.plugins,tooltip:{callbacks:{label:tooltipTime,title:items=>report.stage_chart[items[0].dataIndex].name}}}}}));
    charts.push(new Chart(document.getElementById('dosingBatchChart'),{type:'line',data:{labels:report.batch_chart.map(row=>[row.name.length>24?row.name.slice(0,22)+'…':row.name,row.date+' · '+row.line+' · sz. '+row.number]),datasets:[{label:'Suma pracy etapów · min',data:report.batch_chart.map(row=>row.minutes),borderColor:'#089a8e',backgroundColor:'#089a8e',pointRadius:3,tension:.15},{label:'Cel: 12 min / szarża 1 t = 5 t/h',data:report.batch_chart.map(()=>12),borderColor:'#dc2626',backgroundColor:'#dc2626',borderDash:[7,5],borderWidth:2,pointRadius:0,pointHitRadius:0,tension:0}]},options:{...options,plugins:{...options.plugins,tooltip:{callbacks:{label:tooltipTime,title:items=>report.batch_chart[items[0].dataIndex].label}}}}}));
    const views=new Map();
    const dialog=document.getElementById('dosingChartDialog');
    let expanded=null,ownsFullscreen=false;
    function applyZoom(id) {
        const view=views.get(id),chart=Chart.getChart(document.getElementById(id));
        if(!view || !chart || !view.viewport.clientWidth)return;
        const factor=view.zoom/100;
        view.canvasBox.style.width=Math.round(view.viewport.clientWidth*factor)+'px';
        view.canvasBox.style.height=Math.round(view.viewport.clientHeight*factor)+'px';
        chart.options.scales.x.ticks.font={size:10*Math.min(factor,2)};
        chart.options.scales.y.ticks.font={size:11*Math.min(factor,2)};
        chart.options.scales.x.ticks.maxTicksLimit=Math.max(8,Math.round(8*factor));
        chart.options.plugins.legend.labels.font={size:11*Math.min(factor,2)};
        chart.resize();chart.update('none');
        view.tools.querySelector('output').textContent=view.zoom+'%';
        view.tools.querySelector('[data-zoom-action="out"]').disabled=view.zoom<=50;
        view.tools.querySelector('[data-zoom-action="in"]').disabled=view.zoom>=250;
    }
    function restoreChart() {
        if(!expanded)return;
        const previous=expanded;expanded=null;
        previous.anchor.before(previous.view.figure);previous.anchor.remove();
        if(ownsFullscreen && document.fullscreenElement)document.exitFullscreen().catch(()=>{});
        ownsFullscreen=false;
        requestAnimationFrame(()=>{applyZoom(previous.id);previous.button.focus({preventScroll:true});});
    }
    function closeChart(){if(dialog.open)dialog.close();restoreChart();}
    document.getElementById('closeDosingChart').addEventListener('click',closeChart);
    dialog.addEventListener('close',restoreChart);
    document.addEventListener('fullscreenchange',()=>{if(ownsFullscreen&&!document.fullscreenElement)closeChart();});
    document.querySelectorAll('[data-figure]').forEach(figure=>{
        const id=figure.dataset.figure,tools=figure.querySelector('[data-chart-tools]');
        const view={figure,tools,viewport:figure.querySelector('.dosing-chart-viewport'),canvasBox:figure.querySelector('.pr-chart'),zoom:100};
        views.set(id,view);
        let drag=null;
        view.viewport.addEventListener('pointerdown',event=>{
            if(event.button!==0 || event.pointerType==='touch' || (view.viewport.scrollWidth<=view.viewport.clientWidth && view.viewport.scrollHeight<=view.viewport.clientHeight))return;
            drag={id:event.pointerId,x:event.clientX,y:event.clientY,left:view.viewport.scrollLeft,top:view.viewport.scrollTop};
            view.viewport.setPointerCapture(event.pointerId);
            view.viewport.classList.add('is-dragging');
            event.preventDefault();
        });
        view.viewport.addEventListener('pointermove',event=>{
            if(!drag || drag.id!==event.pointerId)return;
            view.viewport.scrollLeft=drag.left+drag.x-event.clientX;
            view.viewport.scrollTop=drag.top+drag.y-event.clientY;
            event.preventDefault();
        });
        function endDrag(event){
            if(!drag || drag.id!==event.pointerId)return;
            drag=null;view.viewport.classList.remove('is-dragging');
            if(view.viewport.hasPointerCapture(event.pointerId))view.viewport.releasePointerCapture(event.pointerId);
        }
        ['pointerup','pointercancel','lostpointercapture'].forEach(name=>view.viewport.addEventListener(name,endDrag));

        tools.addEventListener('click',event=>{
            const button=event.target.closest('[data-zoom-action]');if(!button)return;
            const action=button.dataset.zoomAction;
            if(action==='fullscreen'){
                if(expanded)return;
                const anchor=document.createComment('dosing-chart-position');figure.before(anchor);
                expanded={id,view,anchor,button};
                document.getElementById('dosingChartTitle').textContent=document.getElementById(id).getAttribute('aria-label');
                document.getElementById('dosingChartContent').appendChild(figure);dialog.showModal();
                if(!document.fullscreenElement&&document.documentElement.requestFullscreen)document.documentElement.requestFullscreen().then(()=>{ownsFullscreen=true;if(!dialog.open){document.exitFullscreen().catch(()=>{});ownsFullscreen=false;}}).catch(()=>{});
            }else view.zoom=action==='reset'?100:Math.max(50,Math.min(250,view.zoom+(action==='in'?25:-25)));
            requestAnimationFrame(()=>applyZoom(id));
        });
        if(window.ResizeObserver)new ResizeObserver(()=>requestAnimationFrame(()=>applyZoom(id))).observe(view.viewport);
        applyZoom(id);
    });
    window.addEventListener('rp:navigation-start',closeChart);
    let printState=[],zoomState=[];
    window.addEventListener('beforeprint',()=>{
        closeChart();zoomState=[...views].map(([id,view])=>[id,view.zoom]);
        views.forEach((view,id)=>{view.zoom=100;applyZoom(id);});
        printState=[...document.querySelectorAll('.dosing-batch')].map(node=>[node,node.open]);printState.forEach(([node])=>node.open=true);
    });
    window.addEventListener('afterprint',()=>{printState.forEach(([node,open])=>node.open=open);printState=[];zoomState.forEach(([id,zoom])=>{views.get(id).zoom=zoom;applyZoom(id);});zoomState=[];});
    document.getElementById('printDosingReport').addEventListener('click',()=>window.print());
})();
