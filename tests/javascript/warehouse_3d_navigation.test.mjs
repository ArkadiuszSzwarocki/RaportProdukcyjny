import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

for (const orderRef of ['', 'TEST-ORDER']) {
    test(`rack navigation remains available after focusing R01 (order=${orderRef || 'none'})`, async () => {
        const chips = ['R01', 'R02', 'MP01', 'BFMP01', 'ALL'].map(id => ({
            style: { display: 'none' }, getAttribute: () => id,
        }));
        const elements = {
            selectRackFilter: { value: 'R01' },
            selectLineFilter: { value: 'ALL' },
            selectPickingOrderFilter: { value: orderRef },
        };
        const calls = [];
        const context = vm.createContext({
            document: { readyState: 'loading', addEventListener() {},
                getElementById: id => elements[id] || null,
                querySelectorAll: () => chips },
            window: { addEventListener() {} }, console,
            setTimeout: () => 1, clearTimeout() {},
            fetch: async url => { calls.push(url); return { json: async () => ({
                success: true, summary: {}, racks: [{ rack_id: 'R01' }],
            }) }; },
        });
        vm.runInContext(readFileSync('static/js/warehouse_3d/scene.js', 'utf8'), context);
        context.updateMetricsHUD = () => {};
        context.buildWarehouseScene = () => {};
        await context.loadWarehouseData();
        assert.equal(calls.length, 1);
        assert.equal(chips[0].style.display, 'inline-flex');
        for (const chip of chips.slice(1, 4)) {
            assert.equal(chip.style.display, orderRef ? 'none' : 'inline-flex');
        }
        assert.equal(chips[4].style.display, 'inline-flex');
    });
}

test('whole hall includes empty racks and empty floor zones', () => {
    const context = vm.createContext({
        document: { readyState: 'loading', addEventListener() {} },
        window: { addEventListener() {} },
    });
    vm.runInContext(readFileSync('static/js/warehouse_3d/scene.js', 'utf8'), context);
    const racks = [
        { rack_id: 'R01', occupied_slots: 1 },
        { rack_id: 'R02', occupied_slots: 0 },
        { rack_id: 'MP01', occupied_slots: 0, rack_type: 'FLOOR_ZONE' },
        { rack_id: 'BFMP01', occupied_slots: 0, rack_type: 'BUFFER_ZONE' },
    ];
    assert.deepEqual(context.getWarehouseRacksForView(racks, 'ALL', false), racks);
    assert.deepEqual(context.getWarehouseRacksForView(racks, 'R02', false), [racks[1]]);
    assert.deepEqual(context.getWarehouseRacksForView(racks, 'ALL', true), [racks[0], racks[2], racks[3]]);
});
