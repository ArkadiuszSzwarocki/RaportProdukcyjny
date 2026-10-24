import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

test('production scheduler stops on menu navigation and resumes after cancellation', async () => {
    const events = {}, docEvents = {}, intervals = new Map();
    let id = 0, calls = 0, release;
    const document = {hidden: false, addEventListener: (name, fn) => {docEvents[name] = fn;}};
    const window = {addEventListener: (name, fn) => {events[name] = fn;},
        setInterval: fn => {intervals.set(++id, fn); return id;},
        clearInterval: id => intervals.delete(id)};
    vm.runInNewContext(fs.readFileSync('static/js/dashboard/scheduler.js', 'utf8'), {window, document, console, Date, Map});
    window.dashboardScheduler.addTask('pending-read', 1000, () => {calls++; return new Promise(resolve => {release = resolve;});});
    const tick = [...intervals.values()][0];
    tick(); tick();
    assert.equal(calls, 1);
    window.__rpNavigating = true;
    events['rp:navigation-start']();
    assert.equal(intervals.size, 0);
    tick(); assert.equal(calls, 1);
    window.__rpNavigating = false;
    events['rp:navigation-cancelled']();
    assert.equal(intervals.size, 1);
    document.hidden = true; docEvents.visibilitychange();
    assert.equal(intervals.size, 0);
    document.hidden = false; docEvents.visibilitychange();
    assert.equal(intervals.size, 1);
    release(); await Promise.resolve();
});

test('slow badge refreshes share one request and release it when finished', async () => {
    const source = fs.readFileSync('static/js/dashboard/agro-banners.js', 'utf8');
    const code = source.slice(source.indexOf('    var badgeRead = null;'), source.indexOf('    function _ensureAgroBannerPulseStyle'));
    let calls = 0, release;
    const global = {};
    const context = vm.createContext({global, document: {hidden: false}, console, Date, encodeURIComponent,
        isAgroZasypPage: () => true, getConfigState: () => ({linia: 'AGRO'}), getCurrentDateIso: () => '2026-10-24',
        fetch: (url, options) => {calls++; assert.equal(options.silent, true); return new Promise(resolve => {release = resolve;});}});
    vm.runInContext(code, context);
    const first = vm.runInContext('_syncDosypkiBadgesAndFallbackBanner()', context);
    const second = vm.runInContext('_syncDosypkiBadgesAndFallbackBanner()', context);
    assert.equal(first, second); assert.equal(calls, 1);
    release({json: async () => ({success: false})}); await first;
    global.__rpNavigating = true;
    vm.runInContext('_syncDosypkiBadgesAndFallbackBanner()', context);
    assert.equal(calls, 1);
    global.__rpNavigating = false;
    const third = vm.runInContext('_syncDosypkiBadgesAndFallbackBanner()', context);
    assert.equal(calls, 2);
    release({json: async () => ({success: false})}); await third;
});
