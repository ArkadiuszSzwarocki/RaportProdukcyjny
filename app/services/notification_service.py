from app.db import create_notifications


EMPLOYEE_NOTIFICATION_ROLES = ('pracownik', 'produkcja', 'lider')
LAB_NOTIFICATION_ROLES = ('laborant',)


def _display_name(raw_name):
    name = str(raw_name or '').strip()
    return name or 'Użytkownik'


def build_section_link(data_planu, sekcja='Zasyp'):
    section = str(sekcja or 'Zasyp').strip() or 'Zasyp'
    data_str = str(data_planu or '')
    return f'/?sekcja={section}&data={data_str}' if data_str else f'/?sekcja={section}'


def notify_workers_about_dosypka(plan_context, total_kg, entries_count, author_name, conn=None, cursor=None, created_by_user_id=None):
    if not plan_context:
        return []

    produkt = plan_context.get('produkt') or 'Zasyp'
    data_planu = plan_context.get('data_planu')
    tytul = f'Nowa dosypka: {produkt}'
    if entries_count == 1:
        tresc = f'{_display_name(author_name)} dodał dosypkę {float(total_kg):.1f} kg dla {produkt}.'
    else:
        tresc = f'{_display_name(author_name)} dodał {entries_count} pozycje dosypki, razem {float(total_kg):.1f} kg, dla {produkt}.'

    return create_notifications(
        typ='dosypka',
        tytul=tytul,
        tresc=tresc,
        recipient_roles=EMPLOYEE_NOTIFICATION_ROLES,
        link_url=build_section_link(data_planu, 'Zasyp'),
        plan_id=plan_context.get('id'),
        created_by_user_id=created_by_user_id,
        conn=conn,
        cursor=cursor,
    )


def notify_laboratory_about_szarza(plan_context, weight_kg, author_name, conn=None, cursor=None, created_by_user_id=None):
    if not plan_context:
        return []

    produkt = plan_context.get('produkt') or 'Zasyp'
    data_planu = plan_context.get('data_planu')
    tytul = f'Nowa szarża: {produkt}'
    tresc = f'{_display_name(author_name)} dodał szarżę {float(weight_kg):.1f} kg na zasypie dla {produkt}.'

    return create_notifications(
        typ='szarza',
        tytul=tytul,
        tresc=tresc,
        recipient_roles=LAB_NOTIFICATION_ROLES,
        link_url=build_section_link(data_planu, 'Zasyp'),
        plan_id=plan_context.get('id'),
        created_by_user_id=created_by_user_id,
        conn=conn,
        cursor=cursor,
    )


def notify_workers_about_plan_change(plan_context, action_label, author_name, conn=None, cursor=None, created_by_user_id=None):
    if not plan_context:
        return []

    produkt = plan_context.get('produkt') or 'Zlecenie'
    sekcja = plan_context.get('sekcja') or 'Zasyp'
    data_planu = plan_context.get('data_planu')
    tytul = f'Plan {action_label.lower()}: {produkt}'
    tresc = f'{_display_name(author_name)} {action_label.lower()} plan w sekcji {sekcja} dla {produkt}.'

    return create_notifications(
        typ='plan',
        tytul=tytul,
        tresc=tresc,
        recipient_roles=EMPLOYEE_NOTIFICATION_ROLES,
        link_url=build_section_link(data_planu, sekcja),
        plan_id=plan_context.get('id'),
        created_by_user_id=created_by_user_id,
        conn=conn,
        cursor=cursor,
    )


def notify_workers_about_plan_batch(data_planu, plans_count, author_name, sekcja='Zasyp', conn=None, cursor=None, created_by_user_id=None):
    if plans_count <= 0:
        return []

    tytul = 'Nowe pozycje w planie produkcyjnym'
    tresc = f'{_display_name(author_name)} dodał {plans_count} pozycji do planu produkcyjnego na {data_planu}.'

    return create_notifications(
        typ='plan_batch',
        tytul=tytul,
        tresc=tresc,
        recipient_roles=EMPLOYEE_NOTIFICATION_ROLES,
        link_url=build_section_link(data_planu, sekcja),
        created_by_user_id=created_by_user_id,
        conn=conn,
        cursor=cursor,
    )
