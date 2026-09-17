import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime

from app.models.osip_email_settings_model import OsipEmailSettingsModel
from app.services.osip_report_email_service import OsipReportEmailService
from app.models.osip_transfer_model import OsipTransferModel
from app.models.osip_transfer_item_model import OsipTransferItemModel


class TestOsipEmailSettingsModel(unittest.TestCase):
    """Testy jednostkowe dla modelu OsipEmailSettingsModel."""

    def test_recipients_list_parsing(self):
        model = OsipEmailSettingsModel(
            odbiorcy="magazyn.osip@firma.pl, logistyka@firma.pl; kierownik@firma.pl\n inny@firma.pl, magazyn.osip@firma.pl "
        )
        recipients = model.recipients_list
        assert len(recipients) == 4
        assert recipients == [
            "magazyn.osip@firma.pl",
            "logistyka@firma.pl",
            "kierownik@firma.pl",
            "inny@firma.pl"
        ]

    def test_recipients_list_empty(self):
        model = OsipEmailSettingsModel(odbiorcy="")
        assert model.recipients_list == []

    def test_is_configured(self):
        unconfigured = OsipEmailSettingsModel(smtp_username="", smtp_password="")
        assert unconfigured.is_configured is False

        configured = OsipEmailSettingsModel(
            smtp_server="smtp.gmail.com",
            smtp_username="sender@osip.pl",
            smtp_password="secret_password",
            is_active=True
        )
        assert configured.is_configured is True

        inactive = OsipEmailSettingsModel(
            smtp_server="smtp.gmail.com",
            smtp_username="sender@osip.pl",
            smtp_password="secret_password",
            is_active=False
        )
        assert inactive.is_configured is False

    def test_to_dict(self):
        model = OsipEmailSettingsModel(
            id=1,
            smtp_server="smtp.wp.pl",
            smtp_port=465,
            smtp_security="SSL",
            smtp_username="magazyn@wp.pl",
            sender_name="Magazyn",
            odbiorcy="odbiorca@wp.pl",
            auto_send_on_dispatch=True,
            is_active=True,
            updated_by="Admin",
            updated_at=datetime(2026, 8, 30, 22, 0, 0)
        )
        d = model.to_dict()
        assert d["id"] == 1
        assert d["smtp_server"] == "smtp.wp.pl"
        assert d["smtp_port"] == 465
        assert d["smtp_username"] == "magazyn@wp.pl"
        assert d["odbiorcy"] == "odbiorca@wp.pl"
        assert d["updated_by"] == "Admin"
        assert d["updated_at"] == "2026-08-30 22:00:00"


class TestOsipEmailSettingsRepository(unittest.TestCase):
    """Testy repozytorium OsipEmailSettingsRepository."""

    @patch('app.repositories.osip_email_settings_repository.get_db_connection')
    def test_save_settings_with_model(self, mock_get_conn):
        from app.repositories.osip_email_settings_repository import OsipEmailSettingsRepository
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {
            'id': 1,
            'smtp_server': 'smtp.gmail.com',
            'smtp_port': 465,
            'smtp_security': 'SSL',
            'smtp_username': 'test@gmail.com',
            'smtp_password': 'pass',
            'sender_name': 'Nadawca',
            'odbiorcy': 'test@wp.pl',
            'auto_send_on_dispatch': 1,
            'is_active': 1,
            'updated_by': 'Admin',
            'updated_at': None
        }
        mock_get_conn.return_value = mock_conn

        repo = OsipEmailSettingsRepository()
        model = OsipEmailSettingsModel(
            smtp_server="smtp.gmail.com",
            smtp_port=465,
            smtp_security="SSL",
            smtp_username="test@gmail.com",
            smtp_password="pass",
            sender_name="Nadawca",
            odbiorcy="test@wp.pl",
            auto_send_on_dispatch=True,
            is_active=True,
            updated_by="Admin"
        )
        saved = repo.save_settings(model)
        assert saved.smtp_username == "test@gmail.com"
        assert saved.sender_name == "Nadawca"
        mock_cursor.execute.assert_called()

    @patch('app.repositories.osip_email_settings_repository.get_db_connection')
    def test_save_settings_with_kwargs(self, mock_get_conn):
        from app.repositories.osip_email_settings_repository import OsipEmailSettingsRepository
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {
            'id': 1,
            'smtp_server': 'smtp.wp.pl',
            'smtp_port': 465,
            'smtp_security': 'SSL',
            'smtp_username': 'test@wp.pl',
            'smtp_password': 'pass',
            'sender_name': 'Nadawca WP',
            'odbiorcy': 'odbiorca@wp.pl',
            'auto_send_on_dispatch': 1,
            'is_active': 1,
            'updated_by': 'User',
            'updated_at': None
        }
        mock_get_conn.return_value = mock_conn

        repo = OsipEmailSettingsRepository()
        saved = repo.save_settings(
            smtp_server="smtp.wp.pl",
            smtp_port=465,
            smtp_security="SSL",
            smtp_username="test@wp.pl",
            smtp_password="pass",
            sender_name="Nadawca WP",
            odbiorcy="odbiorca@wp.pl",
            auto_send_on_dispatch=True,
            is_active=True,
            updated_by="User"
        )
        assert saved.smtp_username == "test@wp.pl"
        assert saved.sender_name == "Nadawca WP"
        mock_cursor.execute.assert_called()


class TestOsipInvolvementValidation(unittest.TestCase):
    """Testy reguły sprawdzającej ruchy z i do OSIP ('gdy jedzie na osip i z osip')."""

    def test_is_osip_involved_true_for_movements_to_osip(self):
        assert OsipReportEmailService.is_osip_involved(source="MS01", destination="OSIP") is True
        assert OsipReportEmailService.is_osip_involved(source="PSD01", destination="OS01") is True
        assert OsipReportEmailService.is_osip_involved(source="CENTRALA", destination="W_TRANZYCIE_OSIP") is True

    def test_is_osip_involved_true_for_movements_from_osip(self):
        assert OsipReportEmailService.is_osip_involved(source="OSIP", destination="MS01") is True
        assert OsipReportEmailService.is_osip_involved(source="OS02", destination="PSD01") is True

    def test_is_osip_involved_false_for_non_osip_movements(self):
        assert OsipReportEmailService.is_osip_involved(source="MS01", destination="PSD01") is False
        assert OsipReportEmailService.is_osip_involved(source="MGW01", destination="RAMPA") is False
        assert OsipReportEmailService.is_osip_involved(source=None, destination=None) is False

    def test_is_osip_involved_with_items_target_or_source(self):
        items_non_osip = [{'productName': 'P1', 'sourceSpot': 'MS01', 'lokalizacja_przyjecia': 'PSD01'}]
        assert OsipReportEmailService.is_osip_involved("MS01", "PSD01", items_non_osip) is False

        items_with_target_osip = [{'productName': 'P1', 'lokalizacja_przyjecia': 'OS02'}]
        assert OsipReportEmailService.is_osip_involved("CENTRALA", "CENTRALA", items_with_target_osip) is True

        items_with_source_osip = [{'productName': 'P1', 'sourceSpot': 'OS05'}]
        assert OsipReportEmailService.is_osip_involved("CENTRALA", "CENTRALA", items_with_source_osip) is True

    def test_categorize_delivery_doc_dostawa_centrala(self):
        dostawa = {
            'id': 100,
            'supplier': 'Cukrownia SA',
            'lokalizacja_z': None,
            'lokalizacja_do': 'MS01',
            'created_by': 'Admin',
            'created_at': datetime(2026, 8, 30, 10, 0),
            'potwierdzone_przez': 'MagazynierJan',
            'potwierdzone_at': datetime(2026, 8, 30, 10, 30),
            'order_ref': 'WZ/2026/001'
        }
        items = [{'productName': 'Cukier', 'nr_palety': 'P1', 'quantity': 1000, 'accepted': True}]
        cat = OsipReportEmailService.categorize_delivery_doc(dostawa, items)
        assert cat['doc_type_code'] == 'DOSTAWA_CENTRALA'
        assert cat['subject_tag'] == 'Dostawa Centrala'
        assert cat['source_value'] == 'Cukrownia SA'
        assert cat['created_by'] == 'Admin'
        assert cat['accepted_by'] == 'MagazynierJan'

    def test_categorize_delivery_doc_dostawa_osip(self):
        dostawa = {
            'id': 101,
            'supplier': 'Hurtownia Opakowań',
            'lokalizacja_z': '',
            'lokalizacja_do': 'OSIP',
            'created_by': 'PaniKrysia',
            'created_at': datetime(2026, 8, 30, 11, 0),
            'potwierdzone_przez': 'MagazynierOSIP',
            'potwierdzone_at': datetime(2026, 8, 30, 11, 45),
            'order_ref': 'WZ/OPAK/88'
        }
        items = [{'productName': 'Worki', 'nr_palety': 'P2', 'quantity': 500, 'accepted': True, 'lokalizacja_przyjecia': 'OS01'}]
        cat = OsipReportEmailService.categorize_delivery_doc(dostawa, items)
        assert cat['doc_type_code'] == 'DOSTAWA_OSIP'
        assert cat['subject_tag'] == 'Dostawa OSIP'
        assert cat['created_by'] == 'PaniKrysia'
        assert cat['accepted_by'] == 'MagazynierOSIP'

    def test_categorize_delivery_doc_przesuniecie_mm(self):
        dostawa = {
            'id': 102,
            'supplier': None,
            'lokalizacja_z': 'MS01',
            'lokalizacja_do': 'PSD01',
            'created_by': 'WydajacyAdam',
            'created_at': datetime(2026, 8, 30, 12, 0),
            'potwierdzone_przez': 'PrzyjmujacyPawel',
            'potwierdzone_at': datetime(2026, 8, 30, 12, 15),
            'order_ref': 'MM-123'
        }
        items = [{'productName': 'Folia', 'nr_palety': 'P3', 'quantity': 100, 'accepted': True}]
        cat = OsipReportEmailService.categorize_delivery_doc(dostawa, items)
        assert cat['doc_type_code'] == 'PRZESUNIECIE_MM'
        assert cat['subject_tag'] == 'Przesunięcie MM'
        assert cat['source_value'] == 'MS01'
        assert cat['dest_value'] == 'PSD01'
        assert cat['created_by'] == 'WydajacyAdam'
        assert cat['accepted_by'] == 'PrzyjmujacyPawel'

    def test_is_allowed_central_warehouse_location(self):
        """Testuje białą listę dozwolonych regałów i buforów Magazynu Centralnego."""
        # Dozwolone regały
        assert OsipReportEmailService.is_allowed_central_warehouse_location("R010101") is True
        assert OsipReportEmailService.is_allowed_central_warehouse_location("R020603") is True
        assert OsipReportEmailService.is_allowed_central_warehouse_location("R-01-01-01") is True
        assert OsipReportEmailService.is_allowed_central_warehouse_location("RR030602") is True
        assert OsipReportEmailService.is_allowed_central_warehouse_location("010102") is True

        # Dozwolone bufory i strefy magazynu
        for loc in ['mp01', 'mpo1', 'bfmp01', 'bf_mp01', 'bfms01', 'bf_ms01', 'ms01', 'psd', 'psd01', 'mgw01', 'mgw02', 'mop01', 'mo01', 'mdo01', 'md01', 'mdm01']:
            assert OsipReportEmailService.is_allowed_central_warehouse_location(loc) is True, f"Failed for {loc}"
            assert OsipReportEmailService.is_allowed_central_warehouse_location(loc.upper()) is True, f"Failed for {loc.upper()}"

        # Niedozwolone lokalizacje (OSIP, produkcja, nieautoryzowane)
        for loc in ['OSIP', 'OS01', 'OS02', 'W_TRANZYCIE_OSIP', 'BB01', 'MZ23', 'KO19', 'LP01', 'MS02', 'MGW03', 'BF_MF01', 'Podłoga 3', 'Maszyna']:
            assert OsipReportEmailService.is_allowed_central_warehouse_location(loc) is False, f"Should be False for {loc}"

        # Puste / None
        assert OsipReportEmailService.is_allowed_central_warehouse_location("") is False
        assert OsipReportEmailService.is_allowed_central_warehouse_location(None) is False

    def test_is_allowed_central_transfer(self):
        """Testuje walidację przesunięć wewnętrznych tylko pomiędzy dozwolonymi strefami Centrali."""
        # Prawidłowe przesunięcia wewnątrz Magazynu Centralnego
        assert OsipReportEmailService.is_allowed_central_transfer("R010101", "MP01") is True
        assert OsipReportEmailService.is_allowed_central_transfer("MS01", "BF_MS01") is True
        assert OsipReportEmailService.is_allowed_central_transfer("PSD01", "MS01") is True
        assert OsipReportEmailService.is_allowed_central_transfer("MGW01", "MOP01") is True
        assert OsipReportEmailService.is_allowed_central_transfer("MD01", "R020101") is True
        assert OsipReportEmailService.is_allowed_central_transfer("WIELE", "MS01") is True
        assert OsipReportEmailService.is_allowed_central_transfer("MS01", "") is True

        # Nieprawidłowe przesunięcia (ruch do/z OSIP, produkcji lub innych stref)
        assert OsipReportEmailService.is_allowed_central_transfer("MS01", "OSIP") is False
        assert OsipReportEmailService.is_allowed_central_transfer("OS01", "MP01") is False
        assert OsipReportEmailService.is_allowed_central_transfer("R010101", "MZ23") is False
        assert OsipReportEmailService.is_allowed_central_transfer("Podłoga 3", "MS01") is False
        assert OsipReportEmailService.is_allowed_central_transfer("BB01", "MP01") is False
        assert OsipReportEmailService.is_allowed_central_transfer("MS01", "MGW03") is False
        assert OsipReportEmailService.is_allowed_central_transfer("", "") is False


class TestOsipReportEmailServiceSending(unittest.TestCase):
    """Testy logiki wysyłania e-maili po przyjęciu i izolacji od poczty systemowej."""

    def _get_mock_settings_repo(self):
        repo = MagicMock()
        repo.get_settings.return_value = OsipEmailSettingsModel(
            smtp_server="smtp.custom-osip.pl",
            smtp_port=465,
            smtp_security="SSL",
            smtp_username="osip_nadawca@custom-osip.pl",
            smtp_password="safe_password",
            sender_name="Dedykowany Nadawca OSIP",
            odbiorcy="odbiorca1@osip.pl, odbiorca2@osip.pl",
            is_active=True,
            auto_send_on_dispatch=True
        )
        return repo

    @patch('smtplib.SMTP_SSL')
    def test_transfer_report_sends_for_standard_transfer(self, mock_smtp_ssl):
        service = OsipReportEmailService(settings_repo=self._get_mock_settings_repo())

        mock_server_instance = MagicMock()
        mock_smtp_ssl.return_value = mock_server_instance

        mock_transfer = OsipTransferModel(
            id=10,
            transfer_code="TR-2026-001",
            source_warehouse="MS01",
            destination_warehouse="PSD01",  # Standardowy transfer między halami
            status="COMPLETED",
            created_by="Jan"
        )

        with patch('app.repositories.osip_transfer_repository.OsipTransferRepository.get_transfer_by_id', return_value=mock_transfer):
            success, msg = service.send_osip_transfer_report(10)
            assert success is True
            assert "Raport przyjęcia wysłany pomyślnie" in msg

    @patch('smtplib.SMTP_SSL')
    def test_transfer_report_sends_when_movement_to_osip(self, mock_smtp_ssl):
        service = OsipReportEmailService(settings_repo=self._get_mock_settings_repo())

        mock_server_instance = MagicMock()
        mock_smtp_ssl.return_value = mock_server_instance

        mock_transfer = OsipTransferModel(
            id=11,
            transfer_code="TR-2026-002",
            source_warehouse="MS01",
            destination_warehouse="OSIP",  # Ruch DO OSIP
            status="COMPLETED",
            created_by="Kierowca Jan",
            items=[
                OsipTransferItemModel(
                    id=1,
                    transfer_id=11,
                    pallet_id="101",
                    nr_palety="P-AGRO-001",
                    product_name="Cukier 25kg",
                    requested_qty=1000.0,
                    loaded_qty=1000.0,
                    unit="kg",
                    status="RECEIVED"
                )
            ]
        )

        with patch('app.repositories.osip_transfer_repository.OsipTransferRepository.get_transfer_by_id', return_value=mock_transfer):
            success, msg = service.send_osip_transfer_report(11)
            assert success is True
            assert "Raport przyjęcia wysłany pomyślnie" in msg
            mock_smtp_ssl.assert_called_once_with("smtp.custom-osip.pl", 465, timeout=15)
            mock_server_instance.login.assert_called_once_with("osip_nadawca@custom-osip.pl", "safe_password")
            mock_server_instance.sendmail.assert_called_once()

    @patch('smtplib.SMTP_SSL')
    def test_transfer_report_sends_when_movement_from_osip(self, mock_smtp_ssl):
        service = OsipReportEmailService(settings_repo=self._get_mock_settings_repo())

        mock_server_instance = MagicMock()
        mock_smtp_ssl.return_value = mock_server_instance

        mock_transfer = OsipTransferModel(
            id=12,
            transfer_code="TR-2026-003",
            source_warehouse="OSIP",  # Ruch Z OSIP
            destination_warehouse="MS01",
            status="COMPLETED",
            created_by="Kierowca Jan",
            items=[
                OsipTransferItemModel(
                    id=2,
                    transfer_id=12,
                    pallet_id="102",
                    nr_palety="P-AGRO-002",
                    product_name="Mąka 25kg",
                    requested_qty=500.0,
                    loaded_qty=500.0,
                    unit="kg",
                    status="RECEIVED"
                )
            ]
        )

        with patch('app.repositories.osip_transfer_repository.OsipTransferRepository.get_transfer_by_id', return_value=mock_transfer):
            success, msg = service.send_osip_transfer_report(12)
            assert success is True
            assert "Raport przyjęcia wysłany pomyślnie" in msg

    @patch('smtplib.SMTP_SSL')
    def test_delivery_report_sends_for_standard_transfer(self, mock_smtp_ssl):
        service = OsipReportEmailService(settings_repo=self._get_mock_settings_repo())

        mock_server_instance = MagicMock()
        mock_smtp_ssl.return_value = mock_server_instance

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {
            'id': 55,
            'order_ref': 'WZ-12345',
            'lokalizacja_z': 'MS01',
            'lokalizacja_do': 'PSD01',  # Przesunięcie między halami
            'items': '[{"productName": "Karton 100", "nr_palety": "PAL-100", "quantity": 500, "packageForm": "packaging", "accepted": true}]'
        }

        with patch('app.services.osip_report_email_service.get_db_connection', return_value=mock_conn):
            success, msg = service.send_central_delivery_osip_report(55)
            assert success is True
            assert "Raport przyjęcia wysłany pomyślnie" in msg

    @patch('smtplib.SMTP_SSL')
    def test_delivery_report_sends_for_osip_target(self, mock_smtp_ssl):
        service = OsipReportEmailService(settings_repo=self._get_mock_settings_repo())

        mock_server_instance = MagicMock()
        mock_smtp_ssl.return_value = mock_server_instance

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {
            'id': 77,
            'order_ref': 'WZ-OSIP-77',
            'lokalizacja_z': 'MS01',
            'lokalizacja_do': 'OSIP',  # Cel OSIP
            'created_by': 'Magazynier Centrali',
            'potwierdzone_przez': 'Magazynier OSIP',
            'potwierdzone_at': datetime(2026, 8, 30, 14, 0),
            'items': '[{"productName": "Sól 25kg", "nr_palety": "PAL-999", "quantity": 1000, "packageForm": "bags", "accepted": true}]'
        }

        with patch('app.services.osip_report_email_service.get_db_connection', return_value=mock_conn):
            success, msg = service.send_central_delivery_osip_report(77)
            assert success is True
            assert "Raport przyjęcia wysłany pomyślnie" in msg
            mock_server_instance.sendmail.assert_called_once()

    @patch('smtplib.SMTP_SSL')
    def test_delivery_report_skips_when_already_sent(self, mock_smtp_ssl):
        service = OsipReportEmailService(settings_repo=self._get_mock_settings_repo())

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {
            'id': 88,
            'order_ref': 'WZ-88',
            'supplier': 'Dostawca',
            'email_sent_at': datetime(2026, 8, 30, 15, 0),  # Already sent!
            'email_sent_to': 'odbiorca@wp.pl',
            'items': '[]'
        }

        with patch('app.services.osip_report_email_service.get_db_connection', return_value=mock_conn):
            success, msg = service.send_central_delivery_osip_report(88)
            assert success is False
            assert "został już wcześniej wysłany" in msg
            mock_smtp_ssl.assert_not_called()

    @patch('smtplib.SMTP_SSL')
    def test_transfer_report_skips_when_already_sent(self, mock_smtp_ssl):
        service = OsipReportEmailService(settings_repo=self._get_mock_settings_repo())

        mock_transfer = OsipTransferModel(
            id=99,
            transfer_code="TR-99",
            source_warehouse="MS01",
            destination_warehouse="OSIP",
            email_sent_at=datetime(2026, 8, 30, 15, 30)  # Already sent!
        )

        with patch('app.repositories.osip_transfer_repository.OsipTransferRepository.get_transfer_by_id', return_value=mock_transfer):
            success, msg = service.send_osip_transfer_report(99)
            assert success is False
            assert "został już wcześniej wysłany" in msg
            mock_smtp_ssl.assert_not_called()

    def test_daily_summary_excludes_osip_deliveries_and_transfers(self):
        """Testuje wykluczenie dostaw do OSIP oraz przesunięć/wywozów z OSIP w raporcie dziennym o 15:00."""
        service = OsipReportEmailService(settings_repo=self._get_mock_settings_repo())

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        # Symulacja 4 dokumentów w magazyn_dostawy:
        # 1. Dostawa Centrala (musi być uwzględniona)
        # 2. Dostawa OSIP (musi być wykluczona)
        # 3. Przesunięcie MM w Centrali (musi być uwzględnione)
        # 4. Przesunięcie MM do OSIP / wywóz (musi być wykluczone)
        mock_cursor.fetchall.return_value = [
            {
                'id': 1,
                'order_ref': 'WZ-CENT-01',
                'supplier': 'Cukrownia',
                'lokalizacja_z': '',
                'lokalizacja_do': 'MS01',
                'status': 'COMPLETED',
                'created_by': 'Admin',
                'potwierdzone_przez': 'Jan',
                'potwierdzone_at': datetime(2026, 9, 16, 10, 0),
                'items': '[{"productName": "Cukier 25kg", "nr_palety": "P1", "quantity": 1000, "accepted": true, "lokalizacja_przyjecia": "MS01"}]'
            },
            {
                'id': 2,
                'order_ref': 'WZ-OSIP-01',
                'supplier': 'Hurtownia',
                'lokalizacja_z': '',
                'lokalizacja_do': 'OSIP',
                'status': 'COMPLETED',
                'created_by': 'Admin',
                'potwierdzone_przez': 'Jan',
                'potwierdzone_at': datetime(2026, 9, 16, 11, 0),
                'items': '[{"productName": "Worki OSIP", "nr_palety": "P2", "quantity": 500, "accepted": true, "lokalizacja_przyjecia": "OS01"}]'
            },
            {
                'id': 3,
                'order_ref': 'MM-CENT-01',
                'supplier': '',
                'lokalizacja_z': 'MS01',
                'lokalizacja_do': 'MGW01',
                'status': 'COMPLETED',
                'created_by': 'Admin',
                'potwierdzone_przez': 'Jan',
                'potwierdzone_at': datetime(2026, 9, 16, 12, 0),
                'items': '[{"productName": "Paleta WG", "nr_palety": "P3", "quantity": 800, "accepted": true, "lokalizacja_przyjecia": "MGW01"}]'
            },
            {
                'id': 4,
                'order_ref': 'MM-WYWOZ-OSIP',
                'supplier': '',
                'lokalizacja_z': 'MS01',
                'lokalizacja_do': 'OSIP',
                'status': 'COMPLETED',
                'created_by': 'Admin',
                'potwierdzone_przez': 'Jan',
                'potwierdzone_at': datetime(2026, 9, 16, 13, 0),
                'items': '[{"productName": "Towar do OSIP", "nr_palety": "P4", "quantity": 300, "accepted": true, "lokalizacja_przyjecia": "OS02"}]'
            }
        ]

        with patch('app.services.osip_report_email_service.get_db_connection', return_value=mock_conn):
            activity = service.get_daily_warehouse_activity('2026-09-16', central_only=True)

            # Powinno być: 1 dostawa (WZ-CENT-01) i 1 przesunięcie (MM-CENT-01)
            assert activity['deliveries_count'] == 1
            assert activity['deliveries'][0]['order_ref'] == 'WZ-CENT-01'

            assert activity['transfers_count'] == 1
            assert activity['transfers'][0]['order_ref'] == 'MM-CENT-01'

            assert activity['total_pallets'] == 2
            assert activity['has_activity'] is True

    def test_daily_summary_strictly_whitelists_central_transfers(self):
        """Testuje że do raportu 15:00 trafiają przesunięcia wyłącznie z dozwolonych regałów i buforów (MP01, BFMP01, BFMS01, MS01, PSD, PSD01, MGW01, MGW02, MOP01, MDO01)."""
        service = OsipReportEmailService(settings_repo=self._get_mock_settings_repo())

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        mock_cursor.fetchall.return_value = [
            # 1. Poprawne przesunięcie między regałem a buforem
            {
                'id': 10,
                'order_ref': 'MM-R01-MP01',
                'supplier': '',
                'lokalizacja_z': 'R010101',
                'lokalizacja_do': 'MP01',
                'status': 'COMPLETED',
                'created_by': 'Admin',
                'potwierdzone_przez': 'Jan',
                'potwierdzone_at': datetime(2026, 9, 16, 10, 0),
                'items': '[{"productName": "Premiks A", "nr_palety": "P10", "quantity": 1000, "accepted": true, "sourceSpot": "R010101", "lokalizacja_przyjecia": "MP01"}]'
            },
            # 2. Poprawne przesunięcie między buforami (PSD01 -> BF_MS01)
            {
                'id': 11,
                'order_ref': 'MM-PSD-BFMS',
                'supplier': '',
                'lokalizacja_z': 'PSD01',
                'lokalizacja_do': 'BF_MS01',
                'status': 'COMPLETED',
                'created_by': 'Admin',
                'potwierdzone_przez': 'Jan',
                'potwierdzone_at': datetime(2026, 9, 16, 11, 0),
                'items': '[{"productName": "Premiks B", "nr_palety": "P11", "quantity": 500, "accepted": true, "sourceSpot": "PSD01", "lokalizacja_przyjecia": "BF_MS01"}]'
            },
            # 3. Nieprawidłowe przesunięcie: produkcja / mieszalnik (MZ23 -> MP01) - musi być wykluczone
            {
                'id': 12,
                'order_ref': 'MM-MZ23',
                'supplier': '',
                'lokalizacja_z': 'MZ23',
                'lokalizacja_do': 'MP01',
                'status': 'COMPLETED',
                'created_by': 'Admin',
                'potwierdzone_przez': 'Jan',
                'potwierdzone_at': datetime(2026, 9, 16, 12, 0),
                'items': '[{"productName": "Zasyp MZ", "nr_palety": "P12", "quantity": 300, "accepted": true, "sourceSpot": "MZ23", "lokalizacja_przyjecia": "MP01"}]'
            },
            # 4. Nieprawidłowe przesunięcie: linia produkcyjna / naważanie (R010101 -> KO19) - musi być wykluczone
            {
                'id': 13,
                'order_ref': 'MM-KO19',
                'supplier': '',
                'lokalizacja_z': 'R010101',
                'lokalizacja_do': 'KO19',
                'status': 'COMPLETED',
                'created_by': 'Admin',
                'potwierdzone_przez': 'Jan',
                'potwierdzone_at': datetime(2026, 9, 16, 13, 0),
                'items': '[{"productName": "Zasyp KO", "nr_palety": "P13", "quantity": 400, "accepted": true, "sourceSpot": "R010101", "lokalizacja_przyjecia": "KO19"}]'
            },
            # 5. Nieprawidłowe przesunięcie: nieautoryzowany bufor (MGW03 -> MS01) - musi być wykluczone
            {
                'id': 14,
                'order_ref': 'MM-MGW03',
                'supplier': '',
                'lokalizacja_z': 'MGW03',
                'lokalizacja_do': 'MS01',
                'status': 'COMPLETED',
                'created_by': 'Admin',
                'potwierdzone_przez': 'Jan',
                'potwierdzone_at': datetime(2026, 9, 16, 14, 0),
                'items': '[{"productName": "Towar MGW03", "nr_palety": "P14", "quantity": 200, "accepted": true, "sourceSpot": "MGW03", "lokalizacja_przyjecia": "MS01"}]'
            }
        ]

        with patch('app.services.osip_report_email_service.get_db_connection', return_value=mock_conn):
            activity = service.get_daily_warehouse_activity('2026-09-16', central_only=True)

            assert activity['transfers_count'] == 2
            assert [t['order_ref'] for t in activity['transfers']] == ['MM-R01-MP01', 'MM-PSD-BFMS']
            assert activity['total_pallets'] == 2

