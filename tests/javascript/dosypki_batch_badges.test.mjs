import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

test('polling keeps batch badges separate from the order total', () => {
    const buttons = [null, '101', '102', '103'].map(batch => ({batch, badge: null,
        querySelector() {return this.badge;}, appendChild(node) {this.badge = node;}}));
    const document = {
        createElement: () => ({textContent: ''}),
        querySelectorAll(selector) {
            const selected = selector.match(/data-szarza-id="(\d+)"/);
            return buttons.filter(button => selected ? button.batch === selected[1] : button.batch === null);
        }
    };
    const source = fs.readFileSync('static/js/dashboard/agro-banners.js', 'utf8');
    const fn = source.slice(source.indexOf('    function _setDosypkiActionBadgeAbsolute'),
        source.indexOf('    function _syncDosypkiBadgesAndFallbackBanner'));
    const context = vm.createContext({document});
    vm.runInContext(fn, context);
    vm.runInContext('_setDosypkiActionBadgeAbsolute(323, 1, "103"); _setDosypkiActionBadgeAbsolute(323, 1);', context);
    assert.equal(buttons[0].badge.textContent, '1');
    assert.equal(buttons[1].badge, null);
    assert.equal(buttons[2].badge, null);
    assert.equal(buttons[3].badge.textContent, '1');
});

test('polling clears stale badges on other batches when only batch four has an addition', async () => {
    const buttons = [null, '555', '556', '557', '558'].map(batch => ({batch,
        getAttribute(name) {return name === 'data-plan-id' ? '323' : this.batch;},
        querySelector() {return this.badge;}, appendChild(node) {this.badge = node;}}));
    for (const button of buttons) button.badge = {textContent: '1', remove() {button.badge = null;}};
    const document = {
        createElement: () => ({textContent: ''}),
        querySelectorAll(selector) {
            if (selector === '.btn-with-badge[data-plan-id]') return buttons;
            const selected = selector.match(/data-szarza-id="(\d+)"/);
            return buttons.filter(button => selected ? button.batch === selected[1] : button.batch === null);
        }
    };
    const source = fs.readFileSync('static/js/dashboard/agro-banners.js', 'utf8');
    const code = source.slice(source.indexOf('    function _setDosypkiActionBadgeAbsolute'),
        source.indexOf('    function _ensureAgroBannerPulseStyle'));
    const context = vm.createContext({global: {}, document, console, Date, encodeURIComponent,
        isAgroZasypPage: () => true, getConfigState: () => ({linia: 'AGRO'}),
        getCurrentDateIso: () => '2026-10-11',
        fetch: async () => ({json: async () => ({success: true, counts: {'323': 1},
            batch_counts: {'323': {'558': 1}}})})});
    vm.runInContext(code + '\n_syncDosypkiBadgesAndFallbackBanner();', context);
    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(buttons.map(button => button.badge?.textContent ?? null), ['1', null, null, null, '1']);
});
