import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import vm from 'node:vm';

const template = readFileSync(new URL('../../templates/includes/_layout_scripts.html', import.meta.url), 'utf8');
const modalCode = template.slice(template.indexOf('    function openCzyszczeniePackagingModal('),
  template.indexOf('    function openAgroProductionDateModal('));

function setup(section = 'Zasyp') {
  const elements = [];
  let submissions = 0;
  const form = {appendChild(element) { elements.push(element); }};
  const document = {
    getElementById: () => null,
    body: {appendChild() {}},
    createElement(tag) {
      const element = {tag, value: '', style: {}, options: [], handlers: {},
        appendChild(child) { this.options.push(child); },
        addEventListener(event, handler) { this.handlers[event] = handler; },
        focus() { this.focused = true; }, remove() {},
      };
      elements.push(element);
      return element;
    },
  };
  const context = {document, window: {confirm: () => true, ajaxSubmitForm() { submissions++; }},
    setTimeout() {}, clearTimeout() {},
    fetch() { throw new Error('No network in modal test'); },
  };
  vm.runInNewContext(modalCode, context);
  context.openCzyszczeniePackagingModal(form, 2, section);
  return {elements, submissions: () => submissions,
    confirm() { elements.find(element => element.textContent === 'Zatwierdź').handlers.click(); }};
}

test('cleaning cannot start with blank SSCC even when every confirmation is accepted', () => {
  const ui = setup();
  const input = ui.elements.find(element => element.name === 'skan_sscc');
  input.value = '   ';
  ui.confirm();
  assert.equal(ui.submissions(), 0);
  assert.equal(input.focused, true);
  assert.ok(ui.elements.some(element => element.textContent?.includes('Jest wymagany także przy pominięciu kolejki.')));
});

test('cleaning submits supplied SSCC and consumed weight', () => {
  const ui = setup();
  ui.elements.find(element => element.name === 'skan_sscc').value = 'SUR000001234567890123';
  ui.elements.find(element => element.name === 'skan_sscc_waga').value = '300';
  ui.confirm();
  assert.equal(ui.submissions(), 1);
  assert.ok(ui.elements.some(element => element.type === 'hidden' && element.name === 'skan_sscc' && element.value === 'SUR000001234567890123'));
});

test('cleaning does not submit a pallet without a positive consumption weight', () => {
  const ui = setup();
  ui.elements.find(element => element.name === 'skan_sscc').value = 'SUR000001234567890123';
  ui.confirm();
  assert.equal(ui.submissions(), 0);
  assert.equal(ui.elements.find(element => element.name === 'skan_sscc_waga').focused, true);
});
