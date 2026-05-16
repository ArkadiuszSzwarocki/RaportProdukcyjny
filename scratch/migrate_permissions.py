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

    # Define sub-sections and their parent mappings
    mappings = {
        'magazyn': [
            'magazyn.view', 
            'magazyn.reception', 
            'magazyn.return', 
            'magazyn.reports', 
            'magazyn.card'
        ],
        'agro': [
            'agro.dashboard',
            'agro.zasyp',
            'agro.workowanie',
            'agro.zasyp_summary',
            'agro.pallet_report'
        ],
        'ustawienia': [
            'ustawienia.zespol',
            'ustawienia.system'
        ],
        'raporty': [
            'raporty.dostawy',
            'raporty.okresowe',
            'raporty.agro_warehouse',
            'raporty.agro_production'
        ]
    }

    # If 'agro' parent doesn't exist, use 'dashboard' or 'zasyp' as template
    template_agro = perms.get('agro', perms.get('zasyp', {}))
    template_magazyn = perms.get('magazyn', {})
    template_ustawienia = perms.get('ustawienia', {})
    template_raporty = perms.get('wyniki', {})

    parents_templates = {
        'magazyn': template_magazyn,
        'agro': template_agro,
        'ustawienia': template_ustawienia,
        'raporty': template_raporty
    }

    for parent, subs in mappings.items():
        template = parents_templates.get(parent, {})
        for sub in subs:
            if sub not in perms:
                perms[sub] = template.copy()
                print(f"Added {sub} from template {parent}")

    # Re-sort keys to maintain grouping
    sorted_perms = dict(sorted(perms.items()))

    with open(cfg_path, 'w', encoding='utf-8') as f:
        json.dump(sorted_perms, f, indent=2, ensure_ascii=False)
    
    print("Migration complete")

if __name__ == "__main__":
    migrate()
