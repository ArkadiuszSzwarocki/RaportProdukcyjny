// cspell:words szwarark
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
const source=fs.readFileSync(new URL('../../static/js/navigation-diagnostics.js',import.meta.url),'utf8');
function setup(path='/agro/scanner/ui?code=SECRET', previous=null, storageFails=false) {
 const events={}, values=new Map(), sent=[];
 if(previous) values.set('rp-navigation-diagnostic',JSON.stringify(previous));
 const storage={getItem:k=>{if(storageFails)throw Error('blocked');return values.get(k);},
  setItem:(k,v)=>{if(storageFails)throw Error('blocked');values.set(k,v);},removeItem:k=>values.delete(k)};
 const window={location:{href:'https://app.test'+path,origin:'https://app.test'},addEventListener:(n,f)=>events[n]=f};
 const document={referrer:'https://app.test/agro/scanner/ui?code=SECRET',
  getElementById:()=>({dataset:{owner:'szwarark',csrf:'csrf-test',eventId:'0123456789abcdef',url:'/auth/navigation-diagnostics'}}),
  addEventListener:(n,f)=>events[n]=f};
 vm.runInNewContext(source,{window,document,URL,Date,JSON,Blob,sessionStorage:storage,
  navigator:{sendBeacon:(url,body)=>{sent.push({url,body});return true;}},
  performance:{getEntriesByType:()=>[{type:'navigate'}]}});
 return {window,events,values,sent};
}
test('explicit role transition survives navigation without storing code or csrf',async()=>{
 const a=setup();a.window.recordDashboardNavigation('eligibility_lost',{previous_active:false,observed_eligible:false});a.events.pagehide();
 const raw=a.values.get('rp-navigation-diagnostic');assert.ok(!raw.includes('SECRET'));assert.ok(!raw.includes('csrf'));
 const b=setup('/',JSON.parse(raw));const report=JSON.parse(await b.sent[0].body.text());
 assert.equal(report.reason,'eligibility_lost');assert.equal(report.previous_view,'scanner');
 assert.equal(report.observed_eligible,false);assert.equal(report.event_id,'0123456789abcdef');
});
test('unattributed page departure is recorded without inventing a trigger',async()=>{
 const a=setup();a.events.pagehide();const b=setup('/',JSON.parse(a.values.get('rp-navigation-diagnostic')));
 const report=JSON.parse(await b.sent[0].body.text());assert.equal(report.reason,'unattributed');
 assert.equal(report.previous_view,'scanner');
});
test('other account and old page departures are ignored',async()=>{
 for(const previous of [{owner:'other',reason:'deadline',departed_at:Date.now()},
  {owner:'szwarark',reason:'deadline',departed_at:Date.now()-130000}]){
  const b=setup('/',previous);assert.equal(JSON.parse(await b.sent[0].body.text()).reason,'unattributed');
 }
});
test('blocked browser storage never prevents dashboard rendering',async()=>{
 const a=setup('/',null,true);assert.equal(a.sent.length,1);
 assert.equal(JSON.parse(await a.sent[0].body.text()).previous_view,'scanner');
});
