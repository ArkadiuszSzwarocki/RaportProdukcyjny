"""
Admin CLI commands for user management.
Usage:
    flask admin create-user --login planista --role planista
    flask admin reset-password --login planista
"""
import click
from werkzeug.security import generate_password_hash
from app.db import get_db_connection


def register_cli_commands(app):
    """Register administrative CLI commands for managing users."""
    admin_group = click.Group('admin', help="Administrative user and system commands.")

    @admin_group.command('create-user')
    @click.option('--login', required=True, prompt=True, help="User login")
    @click.option('--password', required=False, prompt=True, hide_input=True, confirmation_prompt=True, help="User password")
    @click.option('--role', '--rola', 'role', default='planista', type=click.Choice(['admin', 'planista', 'magazynier', 'lider', 'zarzad', 'pakowacz'], case_sensitive=False), help="User role")
    @click.option('--group', '--grupa', 'group', default=None, help="Optional user group (e.g. OSIP, PSD, AGRO)")
    def create_user_cmd(login, password, role, group):
        """Create a new system user safely."""
        login = login.strip()
        if not login:
            click.echo("Error: Login cannot be empty.")
            return

        from app.services.password_policy_service import password_policy_service
        is_valid_pwd, pwd_error = password_policy_service.validate_password(password)
        if not is_valid_pwd:
            click.echo(f"Error: {pwd_error}")
            return

        hashed = generate_password_hash(password, method='pbkdf2:sha256')
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id FROM uzytkownicy WHERE login=%s", (login,))
                if cursor.fetchone():
                    click.echo(f"Error: User '{login}' already exists.")
                    return

                if group:
                    cursor.execute(
                        "INSERT INTO uzytkownicy (login, haslo, rola, grupa) VALUES (%s, %s, %s, %s)",
                        (login, hashed, role.lower(), group)
                    )
                else:
                    cursor.execute(
                        "INSERT INTO uzytkownicy (login, haslo, rola) VALUES (%s, %s, %s)",
                        (login, hashed, role.lower())
                    )
                conn.commit()
                click.echo(f"Success: User '{login}' with role '{role.lower()}' created successfully.")
        except Exception as e:
            click.echo(f"Database error: {e}")
        finally:
            conn.close()

    @admin_group.command('reset-password')
    @click.option('--login', required=True, prompt=True, help="User login")
    @click.option('--password', required=False, prompt=True, hide_input=True, confirmation_prompt=True, help="New password")
    def reset_password_cmd(login, password):
        """Reset a user password safely."""
        login = login.strip()
        if not login:
            click.echo("Error: Login cannot be empty.")
            return

        if not password or len(password) < 6:
            click.echo("Error: Password must be at least 6 characters.")
            return

        hashed = generate_password_hash(password, method='pbkdf2:sha256')
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id FROM uzytkownicy WHERE login=%s", (login,))
                if not cursor.fetchone():
                    click.echo(f"Error: User '{login}' not found.")
                    return

                cursor.execute("UPDATE uzytkownicy SET haslo=%s WHERE login=%s", (hashed, login))
                conn.commit()
                click.echo(f"Success: Password for user '{login}' has been reset successfully.")
        except Exception as e:
            click.echo(f"Database error: {e}")
        finally:
            conn.close()

    app.cli.add_command(admin_group)
