import json
p='config/role_permissions.json'
with open(p,encoding='utf-8') as f:
    d=json.load(f)
keys=list(d.keys())
total=len(keys)
admin_ok=[k for k,v in d.items() if isinstance(v,dict) and v.get('admin',{}).get('access')==True]
admin_not=[k for k,v in d.items() if not (isinstance(v,dict) and v.get('admin',{}).get('access')==True)]
print(f"{len(admin_ok)}/{total}")
if admin_not:
    print('\nBraki:')
    for k in admin_not:
        print(k)
else:
    print('\nBrak braków — admin ma dostęp do wszystkich wpisów')
