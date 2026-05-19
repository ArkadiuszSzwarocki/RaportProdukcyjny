from app.core.daemon import _is_rising_edge, _resolve_pallet_counter_action


def test_counter_action_no_change():
    assert _resolve_pallet_counter_action(100, 100) == 'none'


def test_counter_action_single_increment_registers_once():
    assert _resolve_pallet_counter_action(100, 101) == 'register_single'


def test_counter_action_multi_increment_is_jump():
    assert _resolve_pallet_counter_action(100, 103) == 'jump'


def test_counter_action_backward_resets_baseline():
    assert _resolve_pallet_counter_action(120, 10) == 'reset'


def test_wrap_rising_edge_triggers_once():
    assert _is_rising_edge(False, True) is True


def test_wrap_non_rising_edges_do_not_trigger():
    assert _is_rising_edge(False, False) is False
    assert _is_rising_edge(True, True) is False
    assert _is_rising_edge(True, False) is False
