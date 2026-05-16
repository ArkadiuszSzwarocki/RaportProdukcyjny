import json
import os

def migrate():
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    cfg_path = os.path.join(project_root, 'config', 'role_permissions.json')
    
    if not os.path.exists(cfg_path):
        print("Config file not found")
        return

    with open(cfg_path, 'r', encoding='utf-8') as f:
        perms = json.load(f)

    # Definitive mappings based on sidebar structure
    new_structure = {
        # PRODUKCJA PSD
        'psd.dashboard': perms.get('dashboard', {}),
        'psd.zasyp': perms.get('zasyp', {}),
        'psd.bufor': perms.get('bufor', {}),
        'psd.workowanie': perms.get('workowanie', {}),
        'psd.magazyn': perms.get('magazyn', {}),
        'psd.zasyp_summary': perms.get('podsumowanie_zasypow', {}),
        
        # PRODUKCJA AGRO
        'agro.dashboard': perms.get('agro.dashboard', perms.get('dashboard', {})),
        'agro.zasyp': perms.get('agro.zasyp', perms.get('zasyp', {})),
        'agro.bufor': perms.get('bufor', {}),
        'agro.workowanie': perms.get('agro.workowanie', perms.get('workowanie', {})),
        'agro.magazyn': perms.get('magazyn', {}),
        'agro.zasyp_summary': perms.get('agro.zasyp_summary', perms.get('podsumowanie_zasypow', {})),
        'agro.pallet_report': perms.get('agro.pallet_report', perms.get('raporty', {})),
        
        # MAGAZYNY
        'magazyn.view': perms.get('magazyn.view', perms.get('magazyn', {})),
        'magazyn.reception': perms.get('magazyn.reception', perms.get('magazyn', {})),
        'magazyn.return': perms.get('magazyn.return', perms.get('magazyn', {})),
        'magazyn.reports': perms.get('magazyn.reports', perms.get('wyniki', {})),
        'magazyn.card': perms.get('magazyn.card', perms.get('magazyn', {})),
        'inwentaryzacja': perms.get('inwentaryzacja', perms.get('magazyn', {})),
        
        # RAPORTY
        'raporty.dostawy': perms.get('raporty.dostawy', perms.get('wyniki', {})),
        'raporty.okresowe': perms.get('raporty.okresowe', perms.get('wyniki', {})),
        'raporty.agro_warehouse': perms.get('raporty.agro_warehouse', perms.get('wyniki', {})),
        'raporty.agro_production': perms.get('raporty.agro_production', perms.get('wyniki', {})),
        'raporty.performance': perms.get('raporty.performance', perms.get('wyniki', {})),
        
        # ADMIN & ANALIZA
        'planista': perms.get('planista', {}),
        'moje_godziny': perms.get('moje_godziny', {}),
        'wyniki': perms.get('wyniki', {}),
        'struktura': perms.get('struktura', {}),
        
        # JAKOSC
        'jakosc.index': perms.get('jakosc', {}),
        'jakosc.analysis': perms.get('jakosc', {}),
        'awarie': perms.get('awarie', {}),
        
        # SYMULATORY
        'sim.zebra': perms.get('sim.zebra', perms.get('dashboard', {})),
        'sim.scanner': perms.get('sim.scanner', perms.get('dashboard', {})),
        
        # USTAWIENIA
        'ustawienia.system': perms.get('ustawienia.system', perms.get('ustawienia', {})),
        'ustawienia.zespol': perms.get('ustawienia.zespol', perms.get('ustawienia', {})),
        
        # MASTER / DIAG
        'ustawienia.logs': perms.get('ustawienia.logs', perms.get('ustawienia', {})),
        'ustawienia.errors': perms.get('ustawienia.errors', perms.get('ustawienia', {})),
        'centrum': perms.get('centrum', {}),
        'baza_danych': perms.get('baza_danych', perms.get('ustawienia', {})),
        
        # INNE
        'leaves': perms.get('leaves', {}),
        'leaves.dodaj_do_obsady': perms.get('leaves.dodaj_do_obsady', {}),
        'leaves.obsada_for_date': perms.get('leaves.obsada_for_date', {}),
        'leaves.usun_z_obsady': perms.get('leaves.usun_z_obsady', {}),
        'leaves.zapisz_liderow_obsady': perms.get('leaves.zapisz_liderow_obsady', {}),
        'production.obsada_page': perms.get('production.obsada_page', {})
    }

    # Re-sort keys to maintain grouping
    sorted_perms = dict(sorted(new_structure.items()))

    with open(cfg_path, 'w', encoding='utf-8') as f:
        json.dump(sorted_perms, f, indent=2, ensure_ascii=False)
    
    print("Full structure migration complete")

if __name__ == "__main__":
    migrate()
