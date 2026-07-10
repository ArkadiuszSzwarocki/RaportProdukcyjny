"""
Test kompletnego flow skanera dla wyrobów gotowych
"""

def test_scanner_flow():
    from app.services.scanner_service import ScannerService
    from app.services.magazyny_nowe_service import MagazynyNoweService
    import json
    
    print("=" * 70)
    print("TEST FLOW SKANERA DLA WYROBÓW GOTOWYCH")
    print("=" * 70)
    
    # Test 1: Lookup
    print("\n1️⃣ LOOKUP PAL-3:")
    result = ScannerService.lookup_by_location('PAL-3', 'AGRO')
    if result:
        print(f"   ✅ Znaleziono: {result['nazwa']}")
        print(f"   📦 Typ: {result['inventory_type']}")
        print(f"   📍 Lokalizacja: {result['lokalizacja']}")
        print(f"   ⚖️  Waga: {result['stan_magazynowy']} kg")
        print(f"   🔑 ID: {result['id']}")
        print(f"   🚫 can_dispatch: {result['can_dispatch']}")
        print(f"   ✂️  can_split: {result['can_split']}")
    else:
        print("   ❌ Nie znaleziono")
        return
    
    # Test 2: Próba przeniesienia
    print("\n2️⃣ MOVE DO MGW02:")
    pallet_id = result['id']
    pallet_type = result['inventory_type']
    
    ok, msg = MagazynyNoweService.move_pallet(
        pallet_id=pallet_id,
        pallet_type=pallet_type,
        new_location='MGW02',
        worker_login='test_user',
        linia='AGRO'
    )
    
    if ok:
        print(f"   ✅ {msg}")
    else:
        print(f"   ❌ {msg}")
    
    # Test 3: Sprawdź czy się przeniósł
    print("\n3️⃣ LOOKUP PO PRZENIESIENIU:")
    result2 = ScannerService.lookup_by_location('PAL-3', 'AGRO')
    if result2:
        print(f"   📍 Nowa lokalizacja: {result2['lokalizacja']}")
        if result2['lokalizacja'] == 'MGW02':
            print("   ✅ Przeniesienie OK!")
            
            # Przywróć oryginalną lokalizację
            print("\n4️⃣ PRZYWRACAM ORYGINALNĄ LOKALIZACJĘ MGW01:")
            ok2, msg2 = MagazynyNoweService.move_pallet(
                pallet_id=pallet_id,
                pallet_type=pallet_type,
                new_location='MGW01',
                worker_login='test_user',
                linia='AGRO'
            )
            if ok2:
                print(f"   ✅ {msg2}")
            else:
                print(f"   ❌ {msg2}")
        else:
            print(f"   ⚠️  Lokalizacja: {result2['lokalizacja']} (oczekiwano MGW02)")
    
    print("\n" + "=" * 70)
    print("TEST ZAKOŃCZONY")
    print("=" * 70)

if __name__ == "__main__":
    test_scanner_flow()
