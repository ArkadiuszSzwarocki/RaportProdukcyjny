import os
import json

def test():
    project_root = os.path.dirname(os.path.abspath(__file__))
    cfg_path = os.path.join(project_root, 'config', 'role_permissions.json')
    try:
        with open(cfg_path, 'r', encoding='utf-8') as f:
            perms = json.load(f)
            print("Successfully loaded config.")
    except Exception as e:
        print("Failed to load config:", e)
        return

    rola = 'laborant'
    page = 'workowanie'
    page_perms = perms.get(page)
    if page_perms is None:
        print(f"Page '{page}' not in config")
        return
    res = bool(page_perms.get(rola, {}).get('access', False))
    print(f"role_has_access('{page}') for '{rola}' = {res}")
    print(f"Permissions for laborant: {json.dumps(page_perms.get('laborant'))}")

if __name__ == '__main__':
    test()
