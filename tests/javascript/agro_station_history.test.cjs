const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
class Element {
 constructor(tag='div'){this.tagName=tag;this.children=[];this.dataset={};this.events={};this.value='';this._text='';}
 set textContent(value){this._text=String(value);this.children=[];}
 get textContent(){return this._text+this.children.map(child=>child.textContent).join('');}
 appendChild(child){this.children.push(child);return child;}
 replaceChildren(...children){this._text='';this.children=children.flatMap(child=>child.tagName==='fragment'?child.children:[child]);}
 addEventListener(name,handler){this.events[name]=handler;}
}
const ids=['stationHistoryFilters','stationHistoryTableBody','stationHistoryCount','stationHistoryStatus','historyFilterLinia','historyFilterDataOd','historyFilterDataDo','historyFilterTyp','historyFilterSurowiec','historyFilterStacja','historyFilterLimit','clearHistoryDates'];
const elements=Object.fromEntries(ids.map(id=>[id,new Element()]));
elements.historyFilterLinia.value='AGRO';elements.historyFilterTyp.value='ALL';elements.historyFilterLimit.value='200';
const created=[];const timers=new Map();let timerId=0;const requests=[];
const window={location:{href:'http://127.0.0.1:8082/raporty/agro-historia-stacji',search:''},history:{replaceState(){}},addEventListener(){}};
const context={window,URL,URLSearchParams,AbortController,console,
 document:{readyState:'complete',getElementById:id=>elements[id],createElement:tag=>{created.push(tag);return new Element(tag);},createDocumentFragment:()=>new Element('fragment'),querySelectorAll:()=>[]},
 setTimeout(fn,delay){const id=++timerId;timers.set(id,{fn,delay});return id;},clearTimeout(id){timers.delete(id);},
 fetch(url,options){return new Promise(resolve=>requests.push({url,options,reply:data=>resolve({ok:true,json:async()=>({success:true,data})})}));}};
vm.createContext(context);vm.runInContext(fs.readFileSync('static/js/agro_station_history.js','utf8'),context);
const flush=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 assert.equal(requests.length,1);
 elements.historyFilterSurowiec.value='bb14';elements.historyFilterSurowiec.events.input();
 assert.equal(requests[0].options.signal.aborted,true);
 const debounce=[...timers.values()].find(t=>t.delay===350);debounce.fn();
 assert.equal(requests.length,2);
 const query=new URL('http://localhost'+requests[1].url).searchParams;
 assert.equal(query.get('stacja'),'BB14');assert.equal(query.has('surowiec'),false);
 requests[1].reply([{data:'2026-10-26 10:00',stacja:'MS01 -> BB14',nazwa:'<img onerror=alert(1)>',nr_palety:'SUR1',ilosc:100,typ:'WYDANIE',user:'operator'}]);await flush();
 const body=elements.stationHistoryTableBody;
 assert.ok(body.textContent.includes('BB14'));assert.equal(body.children.length,1);
 assert.ok(body.textContent.includes('<img onerror=alert(1)>'));assert.equal(created.includes('img'),false,'history data must remain text');
 const latest=body.textContent;
 requests[0].reply([{stacja:'BB15',nazwa:'Wrong old response'}]);await flush();
 assert.equal(body.textContent,latest,'stale unfiltered response cannot replace BB14 results');
 elements.historyFilterDataOd.value='2026-10-27';elements.historyFilterDataDo.value='2026-10-26';
 elements.stationHistoryFilters.events.submit({preventDefault(){}});await flush();
 assert.equal(requests.length,2);assert.ok(body.textContent.includes('Data od'));
 console.log('Station history: debounced exact-code search, stale response protection, safe rendering and date validation passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
