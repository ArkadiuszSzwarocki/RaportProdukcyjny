// cspell:words SSCC
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

function setup({ durable = true, owner = 7 } = {}) {
  const queue = [], notices = [], requests = [];
  const input = {value: 'PAL-15', dataset: {}, addEventListener() {}, focus() {}};
  const context = vm.createContext({
    navigator: {onLine: false},
    document: {body: {classList: {contains: () => false}}, getElementById: id => id === 'scanInput' ? input : null},
    window: {addEventListener() {},
      RPOfflineStore: {ownerUserId: owner, async getQueue() {return durable ? queue : [];}},
      offlineScanBuffer: {enqueueScan(code, action) {const event = {client_uuid: 'one', scanned_code: code, scan_action: action}; queue.push(event); return event;}, async persistQueue() {}},
    },
    hidePallet() {vm.runInContext('currentPallet = null', context);}, hideStation() {}, checkPrinter() {},
    showToast(message, level) {notices.push({message, level});}, extractSSCCFromScan: value => value,
    setTimeout() {return 1;}, clearTimeout() {},
    fetch(url) {requests.push(url); throw new Error('Unexpected request');},
    performance: {now: () => 1000}, console,
  });
  vm.runInContext(readFileSync(new URL('../../static/js/scanner/modules/scanner_flow.js', import.meta.url), 'utf8'), context);
  return {context, input, queue, notices, requests};
}

test('offline lookup is durable, clears stale pallet and never confirms stock movement', async () => {
  const s = setup();
  vm.runInContext('currentPallet = {id: 15}', s.context);
  await s.context.lookupPallet('PAL-15');
  assert.equal(s.queue[0].scan_action, 'LOOKUP');
  assert.equal(s.queue[0].scanned_code, 'PAL-15');
  assert.equal(vm.runInContext('currentPallet', s.context), null);
  assert.equal(vm.runInContext('isProcessingScan', s.context), false);
  assert.deepEqual(s.requests, []);
  assert.equal(s.input.value, '');
  assert.equal(s.notices.at(-1).level, 'warn');
  assert.match(s.notices.at(-1).message, /online/);
});

test('failed durable storage retains input and does not claim success', async () => {
  const s = setup({durable: false});
  await s.context.lookupPallet('PAL-15');
  assert.equal(s.input.value, 'PAL-15');
  assert.equal(s.notices.at(-1).level, 'danger');
  assert.equal(vm.runInContext('isProcessingScan', s.context), false);
});

test('missing owner does not queue a scan under another account', async () => {
  const s = setup({owner: null});
  await s.context.lookupPallet('PAL-15');
  assert.equal(s.queue.length, 0);
  assert.equal(s.input.value, 'PAL-15');
  assert.equal(s.notices.at(-1).level, 'danger');
});

test('offline location scan with selected pallet cannot call movement endpoint', async () => {
  const s = setup();
  s.input.value = 'MGW01';
  vm.runInContext('currentPallet = {id: 15}', s.context);
  s.context.triggerScan();
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(s.requests, []);
  assert.equal(s.queue[0].scan_action, 'LOOKUP');
  assert.equal(vm.runInContext('currentPallet', s.context), null);
});
