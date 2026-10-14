import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

function setup(response) {
    const notices = [];
    const input = { value: '', dataset: {}, style: {}, addEventListener() {}, focus() {} };
    const context = vm.createContext({
        window: { addEventListener() {} },
        document: {
            body: { classList: { contains: () => false } }, activeElement: null,
            getElementById: id => id === 'scanInput' ? input : (id === 'toast-container' ? { appendChild: el => notices.push(el) } : null),
            createElement: () => ({ style: {} }),
        },
        navigator: { onLine: true }, performance: { now: () => 0 }, console, AbortController,
        setTimeout: () => 1, clearTimeout() {},
        checkPrinter() {}, hidePallet() {}, hideStation() {},
        fetch: async () => ({ status: 403, json: async () => response }),
    });
    for (const file of ['scanner_audio_toast.js', 'scanner_flow.js']) {
        vm.runInContext(readFileSync(`static/js/scanner/modules/${file}`, 'utf8'), context);
    }
    vm.runInContext("currentPallet = { id: 3387, nr_palety: 'TEST', inventory_type: 'Surowiec', stan_magazynowy: 1000 }", context);
    return { context, notices };
}

for (const [response, expected] of [
    [{ success: false, error: 'Lokalizacja jest zajęta.' }, 'Lokalizacja jest zajęta.'],
    [{ success: false, error: 'forbidden' }, 'Brak uprawnień do wykonania tej operacji na wskazanej palecie.'],
    [{ success: false, message: ' ', error: 'unauthenticated' }, 'Sesja wygasła. Zaloguj się ponownie.'],
    [{ success: false }, 'Nie udało się wykonać operacji. Spróbuj ponownie.'],
]) {
    test(`failed scanner move displays a readable notification: ${expected}`, async () => {
        const { context, notices } = setup(response);
        await context.doMoveFromMainInput('MS01');
        assert.equal(notices.length, 1);
        assert.equal(notices[0].textContent, expected);
        assert.equal(notices[0].style.background, '#991b1b');
    });
}

test('empty toast text always receives a visible fallback', () => {
    const { context, notices } = setup({});
    context.showToast(undefined, 'danger');
    assert.equal(notices[0].textContent, 'Nie udało się wykonać operacji. Spróbuj ponownie.');
    assert.equal(context.scannerResponseMessage({ message: 'constructor' }), 'constructor');
});

test('move uses the stored pallet hall and displays the warehouse boundary block', async () => {
    const { context, notices } = setup({});
    context.LINIA = 'AGRO';
    vm.runInContext("currentPallet.linia = 'PSD'", context);
    let payload;
    const message = 'Przeniesienie z MS01 do MP01 / regałów wymaga zlecenia przesunięcia magazynowego.';
    context.fetch = async (_url, options) => {
        payload = JSON.parse(options.body);
        return {json: async () => ({success: false, message})};
    };
    await context.doMoveFromMainInput('MP01');
    assert.equal(payload.linia, 'PSD');
    assert.equal(notices[0].textContent, message);
});
