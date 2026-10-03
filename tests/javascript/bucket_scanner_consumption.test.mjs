import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

test('bucket scans replace the selected item instead of becoming a destination', () => {
  const context = vm.createContext({});
  vm.runInContext(readFileSync(new URL('../../static/js/scanner/modules/scanner_hardware.js', import.meta.url), 'utf8'), context);
  assert.equal(context.isPalletCode('V1'), true);
  assert.equal(context.isPalletCode('W01'), true);
  assert.equal(context.isPalletCode('MAL04OLD'), true);
  assert.equal(context.isPalletCode('KO01'), false);
});

for (const entry of [
  { name: 'consumed filling', pallet: { status: 'wrzucone_do_mieszalnika', is_used_up: true }, message: /już zużyte/ },
  { name: 'free physical bucket', pallet: { status: 'wolne', is_free: true }, message: /jest wolne/ },
]) test(`scanning a ${entry.name} clears the previous card and explains its status`, () => {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, { style: {}, classList: { remove() {} }, focus() {}, dispatchEvent() {} });
    return elements.get(id);
  };
  const notifications = [];
  const context = vm.createContext({
    window: {}, currentPallet: { id: 2 }, pendingProductionLoc: null,
    document: { getElementById: element, querySelector: () => null },
    closeScannerHistoryModal() {}, resetLocationInputDetection() {},
    showToast: (...args) => notifications.push(args), clearTimeout() {}, Event,
  });
  vm.runInContext(readFileSync(new URL('../../static/js/scanner/modules/scanner_ui.js', import.meta.url), 'utf8'), context);
  context.showPallet({ id: 1, is_bucket: true, kod_wiadra: '04', ...entry.pallet });
  assert.equal(context.currentPallet, null);
  assert.equal(element('palletTypePill').style.display, 'none');
  assert.match(notifications[0][0], entry.message);
});
