const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const template=fs.readFileSync('templates/warehouse_v2/kompletacja.html','utf8');
const source=template.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
const events={};const calls=[];
const context={console,document:{addEventListener(name,callback){events[name]=callback;}},
 window:{addEventListener(){},location:{search:'?order_ref=TEST'}},
 PickingViewModule:{openPickingModal(){throw Error('A picking modal must never open on entry');}},
 setTimeout(){throw Error('Entry must not schedule a popup');},clearTimeout(){}};
vm.createContext(context);vm.runInContext(source,context);
context.switchPickingViewMode=mode=>calls.push('mode:'+mode);
context.loadCurrentPickingTab=()=>calls.push('list');
context.connectPickingUpdates=()=>calls.push('subscribe');
context.refreshPickingOrderSelect=()=>calls.push('selector');
events.DOMContentLoaded();
assert.deepEqual(calls,['mode:list','list','subscribe','selector']);
assert.ok(source.includes('PickingViewModule.openPickingModal('),'explicit order-detail buttons must remain');
console.log('Picking entry shows the list without selecting or opening an order popup.');
