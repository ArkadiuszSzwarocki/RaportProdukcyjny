import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

function setup(response) {
  const notices = [], requests = [];
  const input = {value: 'LP01', dataset: {}, style: {}, addEventListener() {}, focus() {}};
  const button = {disabled: false, innerHTML: ''};
  const overlay = {style: {display: 'flex'}};
  const elements = {scanInput: input, btnConfirmLP01: button, lp01ModalQty: {value: '4'}, lp01ModalOverlay: overlay};
  const context = vm.createContext({
    LINIA: 'AGRO', console, navigator: {onLine: true},
    document: {body: {classList: {contains: () => false}}, getElementById: id => elements[id], querySelector() {}},
    window: {addEventListener() {}, Lp01Film: {ready: () => true, selection: () => ({plan_id: 322})}},
    setTimeout: () => 1, clearTimeout() {}, checkPrinter() {}, hideStation() {},
    hidePallet() {}, showToast: (...args) => notices.push(args), scannerResponseMessage: d => d.message,
    fetch: async (url, options) => {requests.push({url, options}); return {json: async () => response};},
  });
  for (const file of ['scanner_flow.js', 'scanner_operations.js'])
    vm.runInContext(readFileSync(`static/js/scanner/modules/${file}`, 'utf8'), context);
  context.hidePallet = () => vm.runInContext('currentPallet = null', context);
  vm.runInContext("currentPallet = {id:1, nr_palety:'OPK000001788773014226', inventory_type:'Opakowanie', stan_magazynowy:549}", context);
  return {context, input, button, overlay, requests, notices};
}

test('LP01 success clears the pallet and input with one notice and no repeat lookup', async () => {
  const s = setup({success:true, message:'Wydano na LP01', split_info:{is_split:true,new_sscc:'OPK-CHILD'}});
  await s.context.submitLP01Modal();
  assert.equal(s.requests.length,1);
  assert.equal(s.requests[0].url,'/api/lp01/film-roll');
  assert.equal(s.notices.length,1);
  assert.equal(s.input.value,'');
  assert.equal(vm.runInContext('currentPallet',s.context),null);
  assert.equal(s.overlay.style.display,'none');
  assert.equal(s.button.disabled,false);
});

test('LP01 failure preserves the pallet and entered amount for correction', async () => {
  const s = setup({success:false,message:'Nie można wydać'});
  await s.context.submitLP01Modal();
  assert.equal(s.notices.length,1);
  assert.equal(vm.runInContext('currentPallet.id',s.context),1);
  assert.equal(s.overlay.style.display,'flex');
});

test('repeated submit while waiting sends only one dispatch', async () => {
  const s = setup({success:true,message:'Wydano'});
  await Promise.all([s.context.submitLP01Modal(),s.context.submitLP01Modal()]);
  assert.equal(s.requests.length,1);
});
