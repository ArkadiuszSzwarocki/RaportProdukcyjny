import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

function setup(drafts, pending = false, verifiedCount = 2) {
  const storage = new Map(Object.entries(drafts));
  const buttons = {
    continue_transfer_btn: {style: {}, href: 'http://localhost/magazyn-dostawy/nowa?linia=ALL&draft=continue', setAttribute() {}},
    discard_transfer_draft_btn: {style: {}},
    continue_transfer_label: {},
  };
  const window = {localStorage: {
    get length() { return storage.size; }, key(index) { return [...storage.keys()][index]; },
    getItem(key) { return storage.get(key) || null; }, removeItem(key) { storage.delete(key); },
  }, location: {search: '?linia=ALL'}, addEventListener() {}, dispatchEvent() {}};
  const context = vm.createContext({window, document: {getElementById(id) { return buttons[id]; }},
    URL, URLSearchParams, CustomEvent: class {}, confirm: () => true,
    fetch: async () => ({ok: true, json: async () => ({success:true, counts:{ALL:verifiedCount}})})});
  if (pending) {
    const script = readFileSync(new URL('../../static/js/magazyn_dostawy/oczekujace/transfers_logic.js',import.meta.url),'utf8');
    vm.runInContext(script.slice(0,script.indexOf('let palletPreviewTimer')),context);
    return {context,storage,buttons};
  }
  const template = readFileSync(new URL('../../templates/magazyn_dostawy/lista.html', import.meta.url), 'utf8');
  const code = template.slice(template.indexOf('function hasPendingTransferDraft()'), template.indexOf('// Row click listener'));
  vm.runInContext(code.replaceAll('{{ linia }}', 'ALL'), context);
  return {context, storage, buttons};
}

test('discard removes only the selected draft and retains other halls and drafts', () => {
  const app = setup({
    magazyn_dostawy_draft_ALL_new: JSON.stringify({items: [{nr_palety: 'ONE'}]}),
    magazyn_dostawy_draft_AGRO_new: JSON.stringify({items: [{nr_palety: 'TWO'}]}),
    magazyn_dostawy_draft_OSIP_new: JSON.stringify({items: [{nr_palety: 'THREE'}]}),
  });
  app.context.discardPendingTransferDraft();
  assert.equal(app.storage.size, 2);
  assert.equal(app.storage.has('magazyn_dostawy_draft_ALL_new'), false);
  assert.equal(new URL(app.buttons.continue_transfer_btn.href).searchParams.get('linia'), 'AGRO');
});

test('pending view selects newest open snapshot and protects its server order', async () => {
  const app=setup({
    magazyn_dostawy_draft_ALL_new: JSON.stringify({dostawa_id:'OPEN',saved_at:'2026-10-04T10:00:00Z',items:[{nr_palety:'ONE'}]}),
    magazyn_dostawy_draft_ALL_OPEN: JSON.stringify({dostawa_id:'OPEN',saved_at:'2026-10-04T11:00:00Z',items:[{nr_palety:'ONE'},{nr_palety:'TWO'}]}),
  },true);
  await app.context.refreshOczekujaceDraftButtons();
  assert.match(app.buttons.continue_transfer_label.textContent,/2 pal/);
  assert.equal(new URL(app.buttons.continue_transfer_btn.href).searchParams.get('id'),'OPEN');
  assert.equal(app.buttons.discard_transfer_draft_btn.style.display,'none');
  await app.context.discardPendingTransferDraftOczekujace();
  assert.equal(app.storage.size,2);
});

test('pending view hides a completed or fully settled draft after server validation', async () => {
  const app=setup({magazyn_dostawy_draft_ALL_OPEN:JSON.stringify({dostawa_id:'OPEN',items:[{nr_palety:'ONE'}]})},true,0);
  await app.context.refreshOczekujaceDraftButtons();
  assert.equal(app.buttons.continue_transfer_btn.style.display,'none');
});

test('pending discard retains drafts from other halls', async () => {
  const app=setup({
    magazyn_dostawy_draft_ALL_new:JSON.stringify({saved_at:'2026-10-04T11:00:00Z',items:[{nr_palety:'ONE'}]}),
    magazyn_dostawy_draft_OSIP_new:JSON.stringify({saved_at:'2026-10-04T12:00:00Z',items:[{nr_palety:'TWO'}]}),
  },true);
  await app.context.discardPendingTransferDraftOczekujace();
  assert.equal(app.storage.has('magazyn_dostawy_draft_ALL_new'),false);
  assert.equal(app.storage.has('magazyn_dostawy_draft_OSIP_new'),true);
});

test('pending discard uses the application dialog even without a window property', async () => {
  const app=setup({magazyn_dostawy_draft_ALL_new:JSON.stringify({items:[{nr_palety:'ONE'}]})},true);
  vm.runInContext('const AppDialog = {confirm: async () => false};',app.context);
  await app.context.discardPendingTransferDraftOczekujace();
  assert.equal(app.storage.size,1);
});

test('an open order continues by its ID and cannot be discarded as a local draft', () => {
  const app = setup({magazyn_dostawy_draft_ALL_new: JSON.stringify({dostawa_id: 'OPEN-ORDER', items: [{nr_palety: 'ONE'}]})});
  assert.equal(new URL(app.buttons.continue_transfer_btn.href).searchParams.get('id'), 'OPEN-ORDER');
  assert.equal(app.buttons.discard_transfer_draft_btn.style.display, 'none');
  app.context.discardPendingTransferDraft();
  assert.equal(app.storage.size, 1);
});
