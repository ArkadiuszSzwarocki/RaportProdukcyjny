import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

function setup(width = 1500) {
    const listeners = {};
    const panel = {style: {}, offsetWidth: 260, contains: target => target === panel};
    const button = {attrs: {}, getBoundingClientRect: () => ({left: 670, right: 718, bottom: 170}),
        setAttribute(key, value) {this.attrs[key] = value;}, contains: target => target === button, focus() {this.focused = true;}};
    const backdrop = {style: {}};
    const body = {appendChild(node) {node.parentNode = body;}};
    const document = {body, getElementById: id => id.endsWith('Btn') ? button : id.endsWith('Backdrop') ? backdrop : panel,
        addEventListener(name, fn) {listeners[name] = fn;}};
    const window = {innerWidth: width, innerHeight: 800, addEventListener(name, fn) {listeners[name] = fn;}};
    vm.runInNewContext(fs.readFileSync('static/js/dashboard/popovers.js', 'utf8'), {window, document});
    return {window, panel, button, backdrop, body, listeners};
}

test('quick actions open below dots with left edges aligned outside parent stacking context', () => {
    const {window, panel, button, body, backdrop} = setup();
    window.dashboardPopover.toggle('dashboardActionsDropdownMenu', 'dashboardActionsDropdownBtn', 'dashboardActionsBackdrop');
    assert.equal(panel.style.left, '670px');
    assert.equal(panel.style.top, '178px');
    assert.equal(panel.style.position, 'fixed');
    assert.equal(panel.parentNode, body);
    assert.equal(backdrop.parentNode, body);
    assert.equal(button.attrs['aria-expanded'], 'true');
    window.dashboardPopover.toggle('dashboardActionsDropdownMenu', 'dashboardActionsDropdownBtn', 'dashboardActionsBackdrop');
    assert.equal(panel.style.display, 'none');
    assert.equal(backdrop.style.display, 'none');
});

test('bell opens its task list, keeps task clicks available, and Escape closes it', () => {
    const {window, panel, button, listeners} = setup();
    window.dashboardPopover.toggle('cleaningNotificationsPanel', 'cleaningNotificationsBtn');
    assert.equal(panel.style.display, 'block');
    assert.equal(panel.style.left, '458px');
    listeners.click({target: panel});
    assert.equal(panel.style.display, 'block');
    listeners.keydown({key: 'Escape'});
    assert.equal(panel.style.display, 'none');
    assert.equal(button.attrs['aria-expanded'], 'false');
    assert.equal(button.focused, true);
});

test('popups fit viewport and close on outside click or resize', () => {
    const {window, panel, listeners} = setup(800);
    window.dashboardPopover.toggle('dashboardActionsDropdownMenu', 'dashboardActionsDropdownBtn');
    assert.equal(panel.style.left, '532px');
    listeners.click({target: {}});
    assert.equal(panel.style.display, 'none');
    window.dashboardPopover.toggle('cleaningNotificationsPanel', 'cleaningNotificationsBtn');
    listeners.resize();
    assert.equal(panel.style.display, 'none');
});
