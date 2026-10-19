import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const script = readFileSync(new URL('../../static/js/osip/osip_transfer_nowy.js', import.meta.url), 'utf8');
function setup(response, edit = null) {
    const elements = {'trf-pallet-input': {value: 'SUR000001234567890123', focus() {}},
        'trf-scan-status-msg': {style: {}}, 'btn-submit-transfer': {}, 'trf-notes-input': {value: 'Updated notes'}};
    const calls = [], messages = [];
    const context = vm.createContext({window: {OSIP_TRANSFER_EDIT: edit, location: {}},
        document: {addEventListener() {}, getElementById: id => elements[id],
            querySelector: () => ({value: 'OSIP_MS01'})},
        console: {error() {}}, setTimeout() {},
        fetch: async (url, options) => { calls.push({url, options}); if (response instanceof Error) throw response;
            return {ok: response.success, json: async () => response}; }});
    vm.runInContext(script, context);
    context.renderScannedTable = () => {};
    context.saveDraftToStorage = () => {};
    context.clearDraftStorage = () => {};
    context.showTrfToast = (type, message) => messages.push({type, message});
    return {context, calls, elements, messages, items: () => vm.runInContext('scannedItems', context)};
}

test('OSIP scan uses the source-scoped lookup and actual physical identity and weight', async () => {
    const ui = setup({success: true, pallet: {pallet_id: 7, nr_palety: 'SUR000001234567890123',
        product_name: 'Test material', item_type: 'raw', requested_qty: 1000}});
    await ui.context.processPalletScan();
    assert.match(ui.calls[0].url, /source=OSIP/);
    assert.equal(ui.items().length, 1);
    assert.equal(ui.items()[0].ilosc_kg, 1000);
    assert.equal(ui.items()[0].pallet_id, 7);
});

for (const response of [{success: false, message: 'No access to source warehouse'}, new Error('Network unavailable')]) {
    test('failed scan never adds a zero-weight placeholder: ' + (response.message || ''), async () => {
        const ui = setup(response);
        await ui.context.processPalletScan();
        assert.equal(ui.items().length, 0);
        assert.equal(ui.messages.at(-1).type, 'error');
    });
}

test('editing a planned transfer updates the same document, preserving scanner item types', async () => {
    const ui = setup({success: true}, {id: 42, source: 'OSIP'});
    vm.runInContext("scannedItems = [{pallet_id:7, nr_palety:'SUR-TEST', ilosc_kg:100, typ_palety:'raw_agro'}]", ui.context);
    await ui.context.submitTransferOrder();
    assert.equal(ui.calls[0].url, '/osip/api/transfers/42');
    assert.equal(ui.calls[0].options.method, 'PUT');
    assert.equal(JSON.parse(ui.calls[0].options.body).items[0].item_type, 'raw_agro');
});

test('restored zero-weight drafts cannot be submitted', async () => {
    const ui = setup({success: true});
    vm.runInContext("scannedItems = [{nr_palety:'SUR-TEST', ilosc_kg:0}]", ui.context);
    await ui.context.submitTransferOrder();
    assert.equal(ui.calls.length, 0);
    assert.equal(ui.items().length, 1);
});

const details = readFileSync(new URL('../../templates/osip/osip_transfer_details.html', import.meta.url), 'utf8');
const locationFunction = details.slice(details.indexOf('function isTransferReceiptLocation('), details.indexOf('async function beginTransferReceipt('));
for (const destination of ['OSIP', 'MS01']) {
    test('receipt scanner recognizes only locations in destination ' + destination, () => {
        const context = vm.createContext({RECEIPT_DESTINATION: destination});
        vm.runInContext(locationFunction, context);
        for (const code of ['A01', 'OS01', 'BFOS']) assert.equal(context.isTransferReceiptLocation(code), destination === 'OSIP');
        for (const code of ['MS01', 'MP01', 'R030101']) assert.equal(context.isTransferReceiptLocation(code), destination === 'MS01');
        assert.equal(context.isTransferReceiptLocation('SUR000001234567890123'), false);
    });
}


const listScript = readFileSync(new URL('../../static/js/osip/osip_transfers.js', import.meta.url), 'utf8');
const legacyScan = listScript.slice(listScript.indexOf('    async function handlePalletScan()'), listScript.indexOf('    function addScannedItemRow('));
for (const success of [true, false]) {
    test('legacy transfer scanner preserves source and never invents stock: ' + success, async () => {
        const added = [], messages = [];
        const context = vm.createContext({scanInput: {value: 'SUR-123', focus() {}}, scanTimeout: null,
            inputSourceWh: {value: 'OSIP'}, _isProcessingScan: false,
            document: {querySelectorAll: () => []}, console, clearTimeout() {},
            alert: message => messages.push(message), addScannedItemRow: item => added.push(item),
            fetch: async url => { assert.match(url, /source=OSIP/); return {ok: success, json: async () => ({success,
                message: 'Invalid source pallet', pallet: success ? {nr_palety:'SUR-123',requested_qty:345,item_type:'raw_agro'} : null})}; }});
        vm.runInContext(legacyScan, context);
        await context.handlePalletScan();
        assert.equal(added.length, success ? 1 : 0);
        if (success) { assert.equal(added[0].requested_qty, 345); assert.equal(added[0].item_type, 'raw_agro'); }
        else assert.equal(messages.length, 1);
    });
}
