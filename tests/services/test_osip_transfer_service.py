"""
Testy jednostkowe serwisu transferów wewnętrznych OSIP (OsipTransferService).
"""
import pytest
from unittest.mock import MagicMock
from app.services.osip_transfer_service import OsipTransferService
from app.models.osip_transfer_model import OsipTransferModel
from app.models.osip_transfer_item_model import OsipTransferItemModel


def test_create_transfer_order_validation():
    mock_repo = MagicMock()
    service = OsipTransferService(repository=mock_repo)

    with pytest.raises(ValueError, match="musi zawierać co najmniej jedną pozycję"):
        service.create_transfer_order(
            source_warehouse="MS01",
            destination_warehouse="OSIP",
            items=[],
            created_by="test_user"
        )


def test_create_transfer_order_success():
    mock_repo = MagicMock()
    created_model = OsipTransferModel(id=1, transfer_code="TR-123", source_warehouse="MS01", destination_warehouse="OSIP")
    mock_repo.create_transfer.return_value = created_model
    mock_repo.get_transfer_by_id.return_value = created_model

    service = OsipTransferService(repository=mock_repo)
    items = [{"product_name": "Test Produkt", "requested_qty": 100.0, "unit": "kg"}]
    
    result = service.create_transfer_order("MS01", "OSIP", items, "test_user")

    assert result.id == 1
    assert result.transfer_code == "TR-123"
    mock_repo.create_transfer.assert_called_once_with("MS01", "OSIP", "test_user", None)
    mock_repo.add_transfer_items.assert_called_once_with(1, items)


def test_get_transfers_list_filtering():
    mock_repo = MagicMock()
    t1 = OsipTransferModel(id=1, source_warehouse="MS01", destination_warehouse="OSIP", status="PLANNED")
    t2 = OsipTransferModel(id=2, source_warehouse="OSIP", destination_warehouse="MS01", status="PLANNED")
    mock_repo.get_all_transfers.return_value = [t1, t2]

    service = OsipTransferService(repository=mock_repo)

    # Admin widzi wszystko
    admin_list = service.get_transfers_list("admin", "AGRO")
    assert len(admin_list) == 2

    # Magazynier AGRO widzi tylko zlecenia zaplanowane wychodzące z AGRO/MS01
    agro_list = service.get_transfers_list("magazynier", "AGRO")
    assert len(agro_list) == 1
    assert agro_list[0].id == 1
