import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const settle = () => new Promise(resolve => setImmediate(resolve));
function setup(response) {
  let handler, calls = 0;
  const messages = [], button = {disabled:false};
  const form = {action:'/api/reanimate_zlecenie/123', dataset:{}, matches:()=>true, querySelectorAll:()=>[button]};
  const location = {origin:'http://localhost:18084', href:'http://localhost:18084/planista'};
  vm.runInNewContext(readFileSync(new URL('../../static/js/common/order-resume.js', import.meta.url), 'utf8'), {
    document:{addEventListener(name, callback, capture) { assert.equal(name,'submit'); assert.equal(capture,true); handler=callback; }},
    window:{location,showToast:message=>messages.push(message)}, URL, FormData:class {},
    fetch:async (url,options)=> {calls++;assert.equal(url,form.action);assert.equal(options.headers['X-Requested-With'],'XMLHttpRequest');return response;},
  });
  return {form, button, location, messages, calls:()=>calls, submit() {handler({target:form,preventDefault(){},stopImmediatePropagation(){}});} };
}
test('resume popup submits once and opens the returned local production view', async()=> {
  const ui=setup({status:200,ok:true,json:async()=>({success:true,redirect_url:'/?sekcja=Workowanie&linia=AGRO'})});
  ui.submit();ui.submit();await settle();
  assert.equal(ui.calls(),1);
  assert.equal(ui.location.href,'http://localhost:18084/?sekcja=Workowanie&linia=AGRO');
});
test('blocked resume keeps the popup usable and displays the actual refusal', async()=> {
  const ui=setup({status:409,ok:false,json:async()=>({success:false,message:'Another order is active'})});
  ui.submit();await settle();
  assert.deepEqual(ui.messages,['Another order is active']);
  assert.equal(ui.button.disabled,false);
  assert.equal(ui.form.dataset.submitting,'false');
  assert.equal(ui.location.href,'http://localhost:18084/planista');
});
test('expired login redirects without reporting a successful resume',async()=> {
  const ui=setup({status:401,ok:false});ui.submit();await settle();
  assert.equal(ui.location.href,'/login');assert.deepEqual(ui.messages,[]);
});
test('resume never navigates to an external server',async()=> {
  const ui=setup({status:200,ok:true,json:async()=>({success:true,redirect_url:'https://example.com/'})});
  ui.submit();await settle();assert.equal(ui.location.href,'http://localhost:18084/planista');
  assert.equal(ui.messages.length,1);assert.equal(ui.button.disabled,false);
});
