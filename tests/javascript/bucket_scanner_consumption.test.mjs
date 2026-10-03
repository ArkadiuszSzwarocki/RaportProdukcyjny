import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

test('scanning a consumed filling again clears the scanner card and reports consumption', () => {
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
  context.showPallet({ id: 1, is_bucket: true, status: 'wrzucone_do_mieszalnika', kod_wiadra: '04', is_used_up: true });
  assert.equal(context.currentPallet, null);
  assert.equal(element('palletTypePill').style.display, 'none');
  assert.match(notifications[0][0], /już zużyte/);
});
