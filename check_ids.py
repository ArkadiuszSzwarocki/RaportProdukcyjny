import os

content = open('templates/magazyn_dostawy/podzial_palety.html', encoding='utf-8').read()
ids = ['splitScannerInput', 'splitDetailsSection', 'scanLoading', 'scanError', 'scanErrorMsg', 'splitCancelBtn', 'splitWeightInput', 'splitConfirmBtn', 'printModal', 'forcePrintBtn', 'splitSearchBtn']
print({i: (f'id="{i}"' in content or f"id='{i}'" in content) for i in ids})
