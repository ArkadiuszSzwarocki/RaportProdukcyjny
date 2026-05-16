import json
import os

def migrate():
    # Fix project root detection
    project_root = os.getcwd()
    cfg_path = os.path.join(project_root, 'config', 'role_permissions.json')
    
    print(f"Targeting: {cfg_path}")
    if not os.path.exists(cfg_path):
        print("Config file not found at", cfg_path)
        return

    with open(cfg_path, 'r', encoding='utf-8') as f:
        perms = json.load(f)

    # Template permissions from existing keys
    tpl_dash = perms.get('dashboard', {})
    tpl_mag = perms.get('magazyn', {})
    tpl_agro = perms.get('agro_magazyn', tpl_mag)
    tpl_stats = perms.get('wyniki', {})
    tpl_admin = perms.get('ustawienia', {})
    tpl_psd = perms.get('zasyp', {})

    new_structure = {
        # PRODUKCJA PSD
        'psd.dashboard': tpl_dash,
        'psd.zasyp': tpl_psd,
        'psd.bufor': perms.get('bufor', {}),
        'psd.workowanie': perms.get('workowanie', {}),
        'psd.magazyn': tpl_mag,
        'psd.zasyp_summary': perms.get('podsumowanie_zasypow', {}),
        
        # PRODUKCJA AGRO
        'agro.dashboard': tpl_dash,
        'agro.zasyp': perms.get('agro.zasyp', tpl_psd),
        'agro.bufor': perms.get('bufor', {}),
        'agro.workowanie': perms.get('agro.workowanie', perms.get('workowanie', {})),
        'agro.magazyn': tpl_agro,
        'agro.zasyp_summary': perms.get('agro.zasyp_summary', perms.get('podsumowanie_zasypow', {})),
        'agro.pallet_report': perms.get('agro.pallet_report', tpl_stats),
        
        # MAGAZYNY
        'magazyn.view': tpl_mag,
        'magazyn.reception': tpl_mag,
        'magazyn.return': tpl_mag,
        'magazyn.pending': tpl_mag,
        'magazyn.agro_total': tpl_agro,
        'magazyn.agro_packaging': tpl_agro,
        'magazyn.mom': tpl_stats,
        'magazyn.card': tpl_mag,
        'magazyn.inventory': perms.get('inwentaryzacja', tpl_mag),
        
        # RAPORTY
        'raporty.dostawy': perms.get('raporty.dostawy', tpl_stats),
        'raporty.okresowe': perms.get('raporty.okresowe', tpl_stats),
        'raporty.agro_warehouse': perms.get('raporty.agro_warehouse', tpl_stats),
        'raporty.agro_production': perms.get('raporty.agro_production', tpl_stats),
        'raporty.performance': perms.get('raporty.performance', tpl_stats),
        
        # ADMIN & ANALIZA
        'planista': perms.get('planista', {}),
        'moje_godziny': perms.get('moje_godziny', {}),
        'wyniki': tpl_stats,
        'struktura': perms.get('struktura', {}),
        
        # JAKOSC
        'jakosc.index': perms.get('jakosc', {}),
        'jakosc.analysis': perms.get('jakosc', {}),
        'awarie': perms.get('awarie', {}),
        
        # SYMULATORY
        'sim.zebra': perms.get('sim.zebra', tpl_dash),
        'sim.scanner': perms.get('sim.scanner', tpl_dash),
        
        # USTAWIENIA
        'ustawienia.system': perms.get('ustawienia.system', tpl_admin),
        'ustawienia.zespol': perms.get('ustawienia.zespol', tpl_admin),
        'ustawienia.logs': perms.get('ustawienia.logs', tpl_admin),
        'ustawienia.errors': perms.get('ustawienia.errors', tpl_admin),
        'ustawienia.backups': perms.get('ustawienia.backups', tpl_admin),
        
        # DIAGNOSTYKA
        'centrum': perms.get('centrum', {}),
        'baza_danych': perms.get('baza_danych', tpl_admin),
        'leaves.dodaj': perms.get('leaves.dodaj_do_obsady', {}),
        'leaves.usun': perms.get('leaves.usun_z_obsady', {}),
        'leaves.view': perms.get('leaves.obsada_for_date', {}),
        'production.obsada': perms.get('production.obsada_page', {})
    }

    # Re-sort keys to maintain grouping
    sorted_perms = dict(sorted(new_structure.items()))

    with open(cfg_path, 'w', encoding='utf-8') as f:
        json.dump(sorted_perms, f, indent=2, ensure_ascii=False)
    
    print("Migration V3 complete")

if __name__ == "__main__":
    migrate()
