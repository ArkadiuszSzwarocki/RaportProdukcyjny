import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { test } from 'node:test';

function setup({ validationFails = false } = {}) {
  const nodes = new Map();
  for (const id of ['scanInput', 'dispatchOverlay', 'dispatchModalLoc', 'dispatchModalQty', 'dispatchModalPlanId']) {
    nodes.set(id, { value: '', style: {}, dataset: { scannerAttached: 'true' }, focus() {}, textContent: '' });
  }
  const requests = [], notices = [];
  const context = vm.createContext({
    console: { error() {}, warn() {} }, window: { addEventListener() {} }, navigator: {}, LINIA: 'AGRO',
    document: { getElementById: id => nodes.get(id) || null },
    setTimeout: () => 1, clearTimeout() {}, hidePallet() {}, hideStation() {}, checkPrinter() {},
    scanInput: nodes.get('scanInput'),
    showToast: (...args) => notices.push(args), scannerResponseMessage: d => d.message || '',
    fetch: async (url, options) => {
      requests.push({ url, body: JSON.parse(options.body) });
      if (validationFails) throw new Error('network unavailable');
      return { json: async () => ({ success: true, normalized_station: 'BB20' }) };
    },
  });
  vm.runInContext(readFileSync('static/js/scanner/modules/scanner_flow.js', 'utf8'), context);
  vm.runInContext("currentPallet = {id: 123, nr_palety: 'TEST-123', linia: 'PSD', nazwa: 'FFP', inventory_type: 'Surowiec', stan_magazynowy: 1000}", context);
  return { context, nodes, requests, notices };
}

test('BB20 validation and final dispatch use the destination line and same physical pallet', async () => {
  const s = setup();
  await s.context.doMoveFromMainInput('BB20');
  assert.equal(s.requests[0].body.linia, 'AGRO');
  assert.equal(s.nodes.get('dispatchOverlay').style.display, 'flex');
  s.context.doFinalDispatch();
  await new Promise(resolve => setImmediate(resolve));
  const final = s.requests[1];
  assert.equal(final.url, '/agro/scanner/dispatch');
  assert.equal(final.body.linia, 'AGRO');
  assert.equal(final.body.nr_palety, 'TEST-123');
  assert.equal(final.body.surowiec_id, 123);
  assert.equal(final.body.type, final.body.pallet_type);
});

test('failed material validation cannot open the dispatch confirmation', async () => {
  const s = setup({ validationFails: true });
  await s.context.doMoveFromMainInput('BB19');
  assert.notEqual(s.nodes.get('dispatchOverlay').style.display, 'flex');
  assert.equal(s.requests.length, 1);
  assert.equal(s.notices.at(-1)[1], 'danger');
});
