import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';
import { IDBFactory } from 'fake-indexeddb';

const storeCode = readFileSync(new URL('../../static/js/offline_store.js', import.meta.url), 'utf8');
const scannerCode = readFileSync(new URL('../../static/js/offline_scan_buffer.js', import.meta.url), 'utf8');
const plain = (value) => JSON.parse(JSON.stringify(value));
const tick = () => new Promise((resolve) => setImmediate(resolve));

function page(owner, database = new IDBFactory()) {
    const elements = new Map();
    const listeners = new Map();
    let serial = 0;
    const context = vm.createContext({
        __RP_OFFLINE_USER_ID: owner,
        indexedDB: database,
        Headers,
        console: { log() {}, warn() {} },
        navigator: { onLine: false },
        crypto: { randomUUID: () => `test-${++serial}` },
        localStorage: { removeItem() {} },
        sessionStorage: { removeItem() {} },
        CustomEvent: class { constructor(type) { this.type = type; } },
        dispatchEvent() {},
        addEventListener(type, callback) { listeners.set(type, callback); },
        document: {
            getElementById(id) { return elements.get(id); },
            createElement() { return { style: {} }; },
            body: { appendChild(element) { elements.set(element.id, element); } },
        },
    });
    context.window = context;
    context.listeners = listeners;
    return context;
}

async function loadStore(context) {
    vm.runInContext(storeCode, context);
    await context.RPOfflineStore.ready;
    return context.RPOfflineStore;
}

test('IndexedDB survives a new page and separates users', async () => {
    const database = new IDBFactory();
    const first = await loadStore(page(17, database));
    await first.setQueue('rp_offline_scan_buffer', [{ client_uuid: 'saved-scan' }]);
    await first.setQueue('agromes_offline_queue', [{ id: 'saved-operation' }]);
    const other = await loadStore(page(29, database));
    assert.deepEqual(plain(await other.getQueue('rp_offline_scan_buffer')), []);
    assert.deepEqual(plain(await other.getQueue('agromes_offline_queue')), []);
    const reloaded = await loadStore(page(17, database));
    assert.equal((await reloaded.getQueue('rp_offline_scan_buffer'))[0].client_uuid, 'saved-scan');
    assert.equal((await reloaded.getQueue('agromes_offline_queue'))[0].id, 'saved-operation');
    assert.equal(reloaded.withOwner({ headers: { Accept: 'application/json' } }).headers.get('X-RP-Offline-Owner'), '17');
    assert.equal(reloaded.withOwner({}).redirect, 'error');
    assert.equal(reloaded.withOwner({}).headers.get('X-Requested-With'), 'XMLHttpRequest');
});

test('scan created during restoration is merged with persisted scans', async () => {
    const context = page(17);
    let release;
    let persisted;
    context.RPOfflineStore = {
        ownerUserId: '17',
        getQueue: () => new Promise((resolve) => { release = resolve; }),
        async setQueue(_key, queue) { persisted = plain(queue); },
    };
    vm.runInContext(scannerCode, context);
    const scanner = context.offlineScanBuffer;
    const created = scanner.enqueueScan('new-code');
    release([{ client_uuid: 'saved-scan', scanned_code: 'saved-code' }]);
    await scanner.ready;
    await scanner.persistQueue();
    assert.deepEqual(persisted.map((item) => item.client_uuid), ['saved-scan', created.client_uuid]);
});

test('successful batch removes only acknowledged scans, retaining new and invalid ones', async () => {
    const context = page(17);
    await loadStore(context);
    vm.runInContext(scannerCode, context);
    const scanner = context.offlineScanBuffer;
    await scanner.ready;
    const first = scanner.enqueueScan('first-code');
    const invalid = scanner.enqueueScan('invalid-code');
    let response;
    let sent;
    context.fetch = async (_url, options) => {
        sent = JSON.parse(options.body);
        assert.equal(options.headers['X-RP-Offline-Owner'], '17');
        return new Promise((resolve) => { response = resolve; });
    };
    context.navigator.onLine = true;
    const syncing = scanner.sync();
    await tick();
    const newer = scanner.enqueueScan('created-during-sync');
    assert.equal(sent.owner_user_id, '17');
    response({ ok: true, json: async () => ({ success: true, data: { items: [
        { client_uuid: first.client_uuid, status: 'SUCCESS' },
        { client_uuid: invalid.client_uuid, status: 'INVALID' },
        { client_uuid: newer.client_uuid, status: 'SUCCESS' },
    ] } }) });
    await syncing;
    const remaining = await context.RPOfflineStore.getQueue('rp_offline_scan_buffer');
    assert.deepEqual(plain(remaining).map((item) => item.client_uuid), [invalid.client_uuid, newer.client_uuid]);
});

test('expired session and owner mismatch keep durable scans and stop replay', async () => {
    for (const status of [401, 403]) {
        const context = page(17);
        await loadStore(context);
        vm.runInContext(scannerCode, context);
        const scanner = context.offlineScanBuffer;
        await scanner.ready;
        scanner.enqueueScan('kept-code');
        let requests = 0;
        context.fetch = async () => { requests += 1; return { ok: false, status }; };
        context.navigator.onLine = true;
        await scanner.sync();
        await scanner.sync();
        assert.equal(requests, 1);
        assert.equal(scanner.authBlocked, true);
        assert.equal((await context.RPOfflineStore.getQueue('rp_offline_scan_buffer')).length, 1);
    }
});
