"""Production worker roles with a fixed hall and independently editable ACLs."""

HALL_ROLES = {'agro': 'AGRO', 'psd': 'PSD'}


def hall_for_role(role, fallback):
    return HALL_ROLES.get(str(role or '').strip().lower(), fallback)


def worker_role(role):
    return 'pracownik' if role in HALL_ROLES else role


def with_hall_roles(roles):
    names = {name for name, _ in roles}
    return [*roles, *((role, hall) for role, hall in HALL_ROLES.items() if role not in names)]


def with_hall_role_defaults(permissions):
    """Use worker defaults until an administrator saves a hall-role setting."""
    result = {key: dict(roles) for key, roles in permissions.items()}
    for key in ('group.agro', 'group.psd'):
        result.setdefault(key, {})
    for key, roles in result.items():
        for role in HALL_ROLES:
            other_hall = 'psd' if role == 'agro' else 'agro'
            if key == f'group.{other_hall}' or key.startswith(f'{other_hall}.'):
                roles[role] = {'access': False, 'readonly': False}
            elif 'pracownik' in roles:
                roles.setdefault(role, roles['pracownik'])
    return result
