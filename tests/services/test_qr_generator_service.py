import unittest
from app.services.qr_generator_service import QrGeneratorService


class TestQrGeneratorService(unittest.TestCase):
    def test_get_all_warehouse_locations(self):
        result = QrGeneratorService.get_all_warehouse_locations()
        self.assertIn('categories', result)
        self.assertIn('total_count', result)
        self.assertGreater(result['total_count'], 100)

        cats = result['categories']
        self.assertIn('magazyny', cats)
        self.assertIn('regaly', cats)
        self.assertIn('osip', cats)
        self.assertIn('stacje', cats)

        codes = [item['code'] for sub in cats.values() for item in sub]
        self.assertIn('MS01', codes)
        self.assertIn('MP01', codes)
        self.assertIn('OSIP', codes)
        self.assertIn('R010101', codes)
        self.assertIn('OS01', codes)
        self.assertIn('KO01', codes)

    def test_build_location_zpl_80x80(self):
        zpl = QrGeneratorService.build_location_zpl_80x80('R010203', 'Regał R01', 'REGAŁ R01', 80, 80)
        self.assertIn('^XA', zpl)
        self.assertIn('^XZ', zpl)
        self.assertIn('^PW640', zpl)
        self.assertIn('^LL640', zpl)
        self.assertIn('R010203', zpl)
        self.assertIn('^FDMA,R010203^FS', zpl)

    def test_build_custom_qr_zpl_80x80(self):
        zpl = QrGeneratorService.build_custom_qr_zpl_80x80('TEST_DATA_123', 'TEST TITLE', 'SUBTITLE', 80, 80)
        self.assertIn('^XA', zpl)
        self.assertIn('^XZ', zpl)
        self.assertIn('^FDMA,TEST_DATA_123^FS', zpl)


if __name__ == '__main__':
    unittest.main()
