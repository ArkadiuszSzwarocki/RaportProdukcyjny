import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

test('delivery names and comments cannot escape input attributes or inject HTML', () => {
    const rows = [];
    const context = vm.createContext({
        document: {
            getElementById: () => ({ appendChild: row => rows.push(row) }),
            createElement: () => ({ style: {} }),
        },
    });
    context.window = context;
    for (const file of ['utils.js', 'delivery.js']) {
        vm.runInContext(readFileSync(new URL(`../../static/js/agro_warehouse/${file}`, import.meta.url), 'utf8'), context);
    }
    const attack = '"><img src=x onerror=alert(1)> & \'test\'';
    context.addDeliveryRow(attack, 10, attack);
    assert.ok(!rows[0].innerHTML.includes('<img'));
    assert.ok(!rows[0].innerHTML.includes('value=""><'));
    assert.ok(rows[0].innerHTML.includes('&quot;&gt;&lt;img'));
    assert.ok(rows[0].innerHTML.includes('&amp; &#39;test&#39;'));
    context.addDeliveryRow('Soja', 1000, 'Przyjęta');
    assert.ok(rows[1].innerHTML.includes('value="Soja"'));
    assert.ok(rows[1].innerHTML.includes('value="1000"'));
});

test('picking renderer treats stock names, batches and block reasons as text', () => {
    let source = readFileSync(new URL('../../static/js/dashboard/picking_view.js', import.meta.url), 'utf8');
    source = source.replace('openPickingModal: openPickingModal,', '__render: renderPickingItems, openPickingModal: openPickingModal,');
    const rows = [];
    const context = vm.createContext({
        window: { addEventListener() {} },
        document: {
            getElementById: id => id === 'picking-items-tbody' ? { appendChild: row => rows.push(row) } : null,
            createElement: () => ({ style: {}, dataset: {} }),
        },
    });
    vm.runInContext(source, context);
    const attack = '<img src=x onerror="alert(1)">';
    context.window.PickingViewModule.__render({ items_grouped: {
        [attack]: [{ id: 1, status: 'POMINIETA', is_blocked: true, powod_blokady: attack,
                    nr_palety: attack, nr_partii: attack, lokalizacja_zrodlowa: attack, ilosc_kg: 10 }],
    }});
    assert.equal(rows.length, 2);
    for (const row of rows) {
        assert.ok(!row.innerHTML.includes('<img'));
        assert.ok(row.innerHTML.includes('&lt;img'));
    }
    assert.ok(rows[1].innerHTML.includes('10.0 kg'));
});
