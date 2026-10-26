const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const body={innerHTML:'unchanged'};
const badge={innerText:''};
const calls=[];
const context={URL,console,window:{location:{origin:'http://127.0.0.1:8082'},CAN_SEARCH_CONSUMPTION_HISTORY:true,CONSUMPTION_HISTORY_DATE:'2026-08-12',CAN_RESTORE_PALLET:false},
 document:{addEventListener(){},getElementById(id){return id==='consumptionHistoryBody'?body:id==='historyCountBadge'?badge:null;}},
 fetch:async url=>{calls.push(url);return {json:async()=>({success:true,history:[]})};}};
vm.createContext(context);
vm.runInContext(fs.readFileSync('static/js/warehouse_v2/production_consumption.js','utf8'),context);
(async()=>{
 await context.refreshConsumptionHistory();
 assert.equal(new URL(calls[0]).searchParams.get('data'),'2026-08-12');
 assert.equal(badge.innerText,'Pozycji: 0');
 assert.ok(body.innerHTML.includes('wybranej daty'));
 body.innerHTML='historical rows';
 context.prependHistoryRow({data_archiwizacji:'2026-10-26 10:00:00'});
 assert.equal(body.innerHTML,'historical rows','new consumption must not pollute a selected historical day');
 context.window.CAN_SEARCH_CONSUMPTION_HISTORY=false;
 await context.refreshConsumptionHistory();
 assert.equal(new URL(calls[1]).search,'');
 console.log('Consumption history: selected date preserved, historical rows protected, ordinary users keep default history.');
})().catch(error=>{console.error(error);process.exitCode=1;});
