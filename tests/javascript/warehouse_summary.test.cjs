const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
class Element {
 constructor(){this.dataset={};this.events={};this.classList={add(){}};this.isConnected=true;this.value='';this.open=false;}
 replaceChildren(){this.textContent='';}
 addEventListener(name,handler){this.events[name]=handler;}
}
const qr=new Element();qr.dataset.qr='SUR000001234567890123';
const card=new Element();card.dataset.name='surowiec';card.dataset.type='Surowiec';card.querySelectorAll=()=>[qr];
const page=new Element();page.querySelectorAll=()=>[card];page.contains=()=>true;
const dialog=new Element();dialog.showModal=()=>{dialog.open=true;};dialog.close=()=>{dialog.open=false;dialog.events.close();};
const elements={warehouseSummaryPage:page,summarySearch:new Element(),summaryType:new Element(),summaryResultsCount:new Element(),summaryNoResults:new Element(),summaryQrDialog:dialog,summaryQrPreview:new Element(),summaryQrText:new Element(),closeSummaryQr:new Element()};
const calls=[];const frames=[];
function QRCode(target,options){calls.push(options);}
QRCode.CorrectLevel={M:0};
vm.runInNewContext(fs.readFileSync('static/js/warehouse_v2/summary.js','utf8'),{document:{readyState:'complete',getElementById:id=>elements[id]},window:{innerWidth:1200},requestAnimationFrame:fn=>frames.push(fn),QRCode});
assert.equal(calls.length,0,'collapsed products must not generate QR codes or network images');
card.open=true;card.events.toggle();frames.shift()();
assert.equal(calls.length,1);assert.equal(calls[0].text,qr.dataset.qr);assert.equal(calls[0].width,64);
card.events.toggle();frames.shift()();assert.equal(calls.length,1,'generated QR codes must be reused');
const button=new Element();button.dataset.qrValue=qr.dataset.qr;
page.events.click({target:{closest:()=>button}});
assert.equal(dialog.open,true);assert.equal(calls[1].width,256);assert.equal(calls[1].text,qr.dataset.qr);
assert.equal(elements.summaryQrText.textContent,qr.dataset.qr);
elements.closeSummaryQr.events.click();assert.equal(dialog.open,false);
elements.summarySearch.value='brak';elements.summarySearch.events.input();assert.equal(card.hidden,true);assert.equal(elements.summaryNoResults.hidden,false);
elements.summarySearch.value='surowiec';elements.summarySearch.events.input();assert.equal(card.hidden,false);
console.log('Warehouse summary: lazy local QR generation, correct payload, enlarged preview and product filtering passed.');
