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
