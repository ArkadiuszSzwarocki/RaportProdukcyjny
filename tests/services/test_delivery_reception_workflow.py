from app.services.magazyn_dostawy.commands.delivery_reception_workflow import (
    DeliveryReceptionWorkflow,
    DeliveryStatus,
    PalletItemStatus,
)


def test_allows_nominal_wms_transitions():
    assert DeliveryReceptionWorkflow.can_transition(DeliveryStatus.SZKIC, DeliveryStatus.AWIZOWANE)
    assert DeliveryReceptionWorkflow.can_transition(DeliveryStatus.AWIZOWANE, DeliveryStatus.W_STREFIE_PRZYJEC)
    assert DeliveryReceptionWorkflow.can_transition(
        DeliveryStatus.W_STREFIE_PRZYJEC, DeliveryStatus.PUTAWAY_IN_PROGRESS
    )
    assert DeliveryReceptionWorkflow.can_transition(
        DeliveryStatus.PUTAWAY_IN_PROGRESS, DeliveryStatus.COMPLETED
    )


def test_blocks_invalid_transition_and_returns_message():
    ok, msg = DeliveryReceptionWorkflow.validate_transition(
        DeliveryStatus.SZKIC, DeliveryStatus.PUTAWAY_IN_PROGRESS
    )
    assert ok is False
    assert 'Niedozwolone przejście statusu' in msg


def test_computes_item_status_from_flags():
    assert DeliveryReceptionWorkflow.compute_item_status({}) == PalletItemStatus.AWAITING_LABEL
    assert DeliveryReceptionWorkflow.compute_item_status({'nr_palety': 'SUR123'}) == PalletItemStatus.IN_RECEPTION_ZONE
    assert DeliveryReceptionWorkflow.compute_item_status(
        {'putaway_suggested_location': 'R010101'}
    ) == PalletItemStatus.PUTAWAY_PENDING
    assert DeliveryReceptionWorkflow.compute_item_status(
        {'putaway_confirmed_at': '2026-09-17 12:00:00'}
    ) == PalletItemStatus.STORED
