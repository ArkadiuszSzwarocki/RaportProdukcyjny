import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
const html=fs.readFileSync(new URL('../../templates/panels/obecnosci_panel.html',import.meta.url),'utf8');
const source=html.slice(html.indexOf('(function () {'),html.indexOf('function toggleAbsTimePanel'));
function setup() {
 const events={}, fields={}, window={alert: message=>alerts.push(message)}, alerts=[], calls=[];
 const button={disabled:false};
 const form={id:'absQuickAddForm',action:'/dodaj_obecnosc_zakres',dataset:{refreshUrl:'/panel?fragment=true'},querySelector:()=>button};
 const dialog={showModal(){this.opens=(this.opens||0)+1;},close(){this.closed=true;}};
 const document={addEventListener:(type,fn)=>{(events[type]||=[]).push(fn);},
 getElementById:id=>id==='absQuickAddDialog'?dialog:(fields[id]||={}),
 createElement:()=>({querySelector:()=>({})}),querySelector:()=>({replaceWith(){}})};
 let resolve;
 const fetch=(url)=>{calls.push(url);return new Promise(r=>{resolve=r;});};
 const context={window,document,fetch,FormData:class {},URLSearchParams:class {}};
 vm.runInNewContext(source,context);vm.runInNewContext(source,context);
 return {events,form,dialog,button,calls,alerts,resolve: r=>resolve(r)};
}
test('reopening calendar never accumulates submit handlers; concurrent submit sends once',async()=>{
 const s=setup();
 const cell={dataset:{date:'2040-01-02'},closest:()=>({dataset:{empId:'1',empName:'Test'}})};
 for(let i=0;i<3;i++)s.events.click[0]({target:{closest:()=>cell}});
 assert.equal(s.dialog.opens,3);assert.equal(s.events.submit.length,1);
 const event={target:s.form,preventDefault(){},stopImmediatePropagation(){}};
 const first=s.events.submit[0](event);await s.events.submit[0](event);
 assert.equal(s.calls.length,1);assert.equal(s.button.disabled,true);
 s.resolve({ok:false,json:async()=>({success:false,message:'Brak zapisu'})});await first;
 assert.equal(s.dialog.closed,undefined);assert.equal(s.button.disabled,false);
 assert.deepEqual(s.alerts,['Brak zapisu']);
});
