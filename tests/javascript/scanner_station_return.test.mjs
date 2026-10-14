// cspell:words nostation
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { test } from 'node:test';

function setup() {
  const nodes = new Map();
  for (const id of ['palletInfoCard', 'palletCard', 'stationCard', 'stationCode', 'stationItemsList',
    'nostationMsg', 'stationAssignedMaterialCard', 'stationAssignedName', 'stationAssignedCodeBadge',
    'stationAssignedSSCC', 'stationAssignedDate', 'stationAssignedQty', 'stationReturnBtnContainer',
    'scannerReturnLoc', 'scannerReturnQty', 'scannerReturnMaxQty', 'scannerReturnOverlay', 'scanInput']) {
    nodes.set(id, { style: {}, textContent: '', innerHTML: '', value: '', focus() {}, dispatchEvent() {},
      classList: { add() {}, remove() {} } });
  }
  const requests = [];
  const context = vm.createContext({
    console, Event, window: {}, LINIA: 'AGRO', currentPallet: null,
    document: { getElementById: id => nodes.get(id) || null, querySelector: () => null },
    setTimeout: () => 1, clearTimeout() {}, closeScannerHistoryModal() {}, showToast() {},
    fetch: async (url, options) => { requests.push({ url, body: JSON.parse(options.body) });
      return { json: async () => ({ success: true }) }; },
  });
  for (const file of ['scanner_modals.js', 'scanner_ui.js']) {
    vm.runInContext(readFileSync(`static/js/scanner/modules/${file}`, 'utf8'), context);
  }
  return { nodes, context, requests };
}

const station = { station_code: 'BB03', is_production_station: true, warehouse_stock: {
  assigned_material: { has_active_assignment: true, name: 'Material', sscc: 'PALLET-42',
    surowiec_id: 42, ruch_id: 501, plan_id: 323, stan_stacji: 1000 },
} };

test('station displays one card and return uses the exact production movement', async () => {
  const { nodes, context, requests } = setup();
  context.station = station;
  vm.runInContext('showStation(station); openStationReturnModal();', context);
  assert.equal(nodes.get('palletInfoCard').style.display, 'none');
  assert.equal(nodes.get('stationCard').style.display, 'block');
  assert.equal(nodes.get('stationReturnBtnContainer').style.display, 'block');
  assert.equal(nodes.get('scannerReturnQty').value, 1000);
  nodes.get('scannerReturnQty').value = '150';
  vm.runInContext('currentPallet = {id:999, lokalizacja:"BB04", stan_magazynowy:999}; submitScannerReturn();', context);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, '/agro/api/return');
  assert.equal(requests[0].body.surowiec_id, 42);
  assert.equal(requests[0].body.ruch_produkcja_id, 501);
  assert.equal(requests[0].body.plan_id, 323);
  assert.equal(requests[0].body.ilosc, 150);
  assert.equal(nodes.get('stationCard').style.display, 'none');
});

test('station with only a configured material cannot return unassigned stock', () => {
  const { nodes, context, requests } = setup();
  context.station = { ...station, warehouse_stock: { assigned_material: {
    has_active_assignment: true, name: 'Material', surowiec_id: 42, stan_stacji: 0,
  } } };
  vm.runInContext('showStation(station); openStationReturnModal(); submitScannerReturn();', context);
  assert.equal(nodes.get('stationReturnBtnContainer').style.display, 'none');
  assert.equal(requests.length, 0);
});
