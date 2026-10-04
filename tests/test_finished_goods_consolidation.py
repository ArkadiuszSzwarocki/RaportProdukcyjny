from app.services.finished_goods_consolidation import FinishedGoodsConsolidation


def copy(table, id, sscc, quantity, location='MGW01', **extra):
    return dict(table=table, row=dict(id=id, nr_palety=sscc, waga_netto=quantity,
                                      lokalizacja=location, **extra))


def test_same_sscc_uses_confirmed_receipt_even_when_old_ids_differ():
    code = 'AGR-UNIQUE'
    entries = [
        copy('magazyn_palety', 928, code, 1000, paleta_workowanie_id=19,
             linia='AGRO', data_potwierdzenia='2026-10-04 09:00:00'),
        copy('magazyn_palety_agro', 4, code, 1000, paleta_workowanie_id=19,
             linia='AGRO', data_potwierdzenia='2026-10-04 09:00:00'),
    ]
    production = [dict(id=19, nr_palety=code, status='przyjeta',
                       data_potwierdzenia='2026-10-04 09:00:00',
                       waga_potwierdzona=1000, _line='AGRO')]
    record = FinishedGoodsConsolidation._resolve(code, entries, [], production)
    assert record['reasons'] == []
    assert record['row']['id'] == 928


def test_different_weights_do_not_become_available_stock():
    record = FinishedGoodsConsolidation._resolve(
        'AGR-CONFLICT', [copy('magazyn_palety', 2, 'AGR-CONFLICT', 40),
                         copy('magazyn_palety_agro', 3, 'AGR-CONFLICT', 1000)], [], [])
    assert record['row']['waga_netto'] == 0
    assert record['row']['is_blocked'] == 1
    assert 'different_quantity' in record['reasons']
