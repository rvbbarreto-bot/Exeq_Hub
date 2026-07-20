from django.conf import settings
from django.db import migrations


ROLE = "exeq_app"


def _create_role(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            f"""
            DO $$
            BEGIN
              IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') THEN
                CREATE ROLE {ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS;
              END IF;
            END $$;
            """
        )
        cursor.execute(f"GRANT USAGE ON SCHEMA public TO {ROLE}")
        cursor.execute(f"GRANT ALL ON ALL TABLES IN SCHEMA public TO {ROLE}")
        cursor.execute(f"GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO {ROLE}")
        cursor.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO {ROLE}"
        )
        cursor.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO {ROLE}"
        )
        # sessão Django (exeq) pode impersonar o role sujeito a RLS
        cursor.execute("SELECT current_user")
        current = cursor.fetchone()[0]
        cursor.execute(f'GRANT {ROLE} TO "{current}"')


def _drop_role(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f"DROP ROLE IF EXISTS {ROLE}")


class Migration(migrations.Migration):
    dependencies = [
        ("ops", "0003_enable_rls"),
    ]

    operations = [
        migrations.RunPython(_create_role, _drop_role),
    ]
