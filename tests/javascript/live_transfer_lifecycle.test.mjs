// cspell:ignore dostawa initialization
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

test('concurrent scans wait for the same slow order initialization', async () => {
    let release;
    const wait = new Promise(resolve => { release = resolve; });
    let requests = 0;
    const context = vm.createContext({
        window: {EdycjaConfig: {linia: 'AGRO'}, location: {href:'http://localhost/nowa'}, history: {replaceState() {}}},
        document: {getElementById: () => ({value:'TEST-ORDER'}), title:'Test'},
        console, URL, setInterval: () => 1, clearInterval() {}, saveDraftState() {},
        fetch: async () => { requests++; await wait; return {json: async () => ({success:true, result:{dostawa_id:'one-order', order_ref:'TEST-ORDER'}})}; },
    });
    vm.runInContext(readFileSync('static/js/magazyn_dostawy/edycja/api.js', 'utf8'), context);
    const first = context.ensureLiveTransferInitialized();
    const second = context.ensureLiveTransferInitialized();
    assert.equal(requests, 1);
    release();
    assert.deepEqual(await Promise.all([first, second]), ['one-order', 'one-order']);
});

test('canceling an open form cancels its server order before clearing the draft', async () => {
    const calls = [];
    const context = vm.createContext({window:{EdycjaConfig:{dostawaId:'one-order', urlListaDostaw:'/list'}, location:{}},
        document:{addEventListener(){}}, getStoredDraftState: () => ({items:[]}), confirm: () => true,
        clearDraftState: () => calls.push('clear'), showToast() {},
        fetch: async url => { calls.push(url); return {json:async () => ({success:true})}; },
    });
    vm.runInContext(readFileSync('static/js/magazyn_dostawy/edycja/events.js', 'utf8'), context);
    await context.cancelTransferForm({preventDefault(){}});
    assert.deepEqual(calls, ['/magazyn-dostawy/api/anuluj/one-order', 'clear']);
    assert.equal(context.window.location.href, '/list');
});
