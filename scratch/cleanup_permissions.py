import json
import os

def cleanup():
    project_root = os.getcwd()
    cfg_path = os.path.join(project_root, 'config', 'role_permissions.json')
    
    if not os.path.exists(cfg_path):
        return

    with open(cfg_path, 'r', encoding='utf-8') as f:
        perms = json.load(f)

    # List of allowed keys (everything else will be removed)
    allowed_keys = [
        'magazyn.view', 'magazyn.reception', 'magazyn.return', 'magazyn.pending',
        'magazyn.agro_total', 'magazyn.agro_packaging', 'magazyn.mom', 'magazyn.card', 'magazyn.inventory',
        'psd.dashboard', 'psd.zasyp', 'psd.bufor', 'psd.workowanie', 'psd.magazyn', 'psd.zasyp_summary',
        'agro.dashboard', 'agro.zasyp', 'agro.bufor', 'agro.workowanie', 'agro.magazyn', 'agro.zasyp_summary', 'agro.pallet_report',
        'raporty.dostawy', 'raporty.okresowe', 'raporty.agro_warehouse', 'raporty.agro_production', 'raporty.performance',
        'ustawienia.system', 'ustawienia.zespol', 'ustawienia.logs', 'ustawienia.errors', 'ustawienia.backups',
        'planista', 'moje_godziny', 'wyniki', 'struktura',
        'jakosc.index', 'jakosc.analysis', 'awarie',
        'sim.zebra', 'sim.scanner',
        'centrum', 'baza_danych', 'production.obsada',
        'leaves.view', 'leaves.dodaj', 'leaves.usun'
    ]

    new_perms = {k: perms[k] for k in allowed_keys if k in perms}

    with open(cfg_path, 'w', encoding='utf-8') as f:
        json.dump(new_perms, f, indent=2, ensure_ascii=False)
    
    print("Cleanup complete")

if __name__ == "__main__":
    cleanup()
