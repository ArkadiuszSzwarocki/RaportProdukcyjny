import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import vm from 'node:vm';

const layout = readFileSync('templates/includes/_layout_scripts.html', 'utf8');
const flow = layout.slice(layout.indexOf('    function setHiddenFormValue('),
    layout.indexOf('    /** Initialize a custom,'));
const confirmation = layout.slice(layout.indexOf("    document.addEventListener('submit', function(event) {"),
    layout.indexOf('    /** Function for operators'));

function setup({checklist = true, accepted = true} = {}) {
    const elements = [], body = [], hidden = new Map([
        ['linia', {value: 'AGRO'}], ['sekcja', {value: 'Workowanie'}],
        ['override_start_rule', {value: '1'}]
    ]);
    let submissions = 0, confirmations = 0, genericPopups = 0, submitListener;
    const attributes = {'data-start-confirm': 'Override?', 'data-start-checklist': checklist ? '1' : '0',
        'data-required-opakowanie': 'Film', 'data-required-etykieta': 'Label'};
    const form = {
        isConnected: true,
        getAttribute: name => attributes[name] || null,
        querySelector: selector => hidden.get(/name="([^"]+)"/.exec(selector)?.[1]) || null,
        appendChild: element => hidden.set(element.name, element),
        submit() { submissions++; }
    };
    const document = {
        body: {appendChild: element => body.push(element)},
        getElementById: id => elements.find(element => element.id === id && !element.removed) || null,
        addEventListener(name, handler) { if (name === 'submit') submitListener = handler; },
        createElement(tag) {
            const element = {tag, style: {}, value: '', handlers: {}, children: [],
                appendChild(child) { this.children.push(child); },
                addEventListener(name, handler) { this.handlers[name] = handler; },
                remove() { this.removed = true; }, focus() {}};
            elements.push(element);
            return element;
        }
    };
    const window = {showConfirmModal(_message, onAccept) { confirmations++; if (accepted) onAccept(); },
        confirm() { throw new Error('Expected the application dialog'); },
        openQuickPopup() { genericPopups++; }, safeAlert() { throw new Error('Unexpected alert'); }};
    vm.runInNewContext(flow + confirmation, {window, document, Date, setTimeout() {}});
    return {elements, body, hidden, counts: () => ({submissions, confirmations, genericPopups}),
        start() {
            const allowed = window.confirmStartOrder(form, 'Product', '2');
            submitListener({target: form, defaultPrevented: allowed === false,
                preventDefault() { this.defaultPrevented = true; }});
            return allowed;
        }};
}

test('master override keeps checklist open until the operator completes it', () => {
    const ui = setup();
    assert.equal(ui.start(), false);
    const overlay = ui.body[0];
    assert.equal(overlay.id, 'start-order-checklist-overlay');
    const confirm = ui.elements.filter(element => element.tag === 'button')[1];
    confirm.handlers.click();
    assert.equal(overlay.removed, undefined);
    assert.deepEqual(ui.counts(), {submissions: 0, confirmations: 1, genericPopups: 0});
    ui.elements.filter(element => element.type === 'checkbox').forEach(element => { element.checked = true; });
    ui.elements.find(element => element.type === 'text').value = 'LOT-123';
    confirm.handlers.click();
    assert.equal(overlay.removed, true);
    assert.equal(ui.hidden.get('start_checklist_confirmed').value, '1');
    assert.equal(ui.hidden.get('override_start_rule').value, '1');
    assert.equal(ui.counts().submissions, 1);
});

test('cancelled override does not open a checklist or send a request', () => {
    const ui = setup({accepted: false});
    assert.equal(ui.start(), false);
    assert.equal(ui.body.length, 0);
    assert.deepEqual(ui.counts(), {submissions: 0, confirmations: 1, genericPopups: 0});
});

test('resume waits for the production date dialog instead of submitting in the background', () => {
    const ui = setup({checklist: false});
    assert.equal(ui.start(), false);
    assert.equal(ui.body[0].id, 'start-order-date-overlay');
    assert.deepEqual(ui.counts(), {submissions: 0, confirmations: 1, genericPopups: 0});
    ui.elements.find(element => element.tag === 'button').handlers.click();
    assert.equal(ui.body[0].removed, true);
    assert.equal(ui.counts().submissions, 0);
});

const scripts = readFileSync('static/scripts.js', 'utf8');
const overlayGuard = scripts.slice(scripts.indexOf('    function hasBlockingOverlayOpen()'),
    scripts.indexOf('    function captureExpandedDetails()'));
for (const id of ['start-order-checklist-overlay', 'start-order-date-overlay', 'czyszczenie-packaging-overlay', 'appDialogOverlay']) {
    test(`${id} blocks background refresh`, () => {
        const document = {body: {classList: {contains: () => false}},
            querySelector: selector => selector.split(',').map(s => s.trim()).includes('#' + id) ? {} : null};
        const context = vm.createContext({document});
        vm.runInContext(overlayGuard, context);
        assert.equal(context.hasBlockingOverlayOpen(), true);
    });
}

test('a refresh already in flight cannot replace content after the checklist opens', async () => {
    let open = false, release, created = 0;
    const document = {getElementById: () => null, querySelector: () => null,
        createElement() { created++; throw new Error('Content must not be replaced'); }};
    const context = vm.createContext({document, window: {location: {pathname: '/', href: 'https://example.test/'}},
        console: {info() {}, error(error) { throw error; }}, shouldSkipAutoRefresh: () => open,
        localStorage: {setItem() {}}, captureExpandedDetails: () => [], partialReloadInFlight: false,
        fetch: () => new Promise(resolve => { release = resolve; })});
    vm.runInContext(scripts.slice(scripts.indexOf('    async function performPartialReload(options)'),
        scripts.indexOf('    // Expose to window for external scripts')), context);
    const read = context.performPartialReload({source: 'smart-polling'});
    open = true;
    release({ok: true, text: async () => '<main id="mainContent">New data</main>'});
    await read;
    assert.equal(created, 0);
    assert.equal(context.partialReloadInFlight, false);
});

test('generic confirmation respects a submit already cancelled by a checklist', () => {
    let listener;
    const document = {addEventListener(name, handler) { listener = handler; }};
    const window = {openQuickPopup() { throw new Error('Must not open a second confirmation'); }};
    vm.runInNewContext(confirmation, {document, window});
    listener({defaultPrevented: true, target: {getAttribute: () => 'Confirm?'},
        preventDefault() { throw new Error('Submit was already cancelled'); }});
});
