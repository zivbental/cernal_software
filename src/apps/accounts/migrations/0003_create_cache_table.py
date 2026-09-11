# Creates the DatabaseCache table (config/settings/base.py CACHES, docs/public-api.md
# §6) via createcachetable, so `./do migrate` is the only setup step needed — not a
# manual `manage.py createcachetable` a deploy can forget to run.

from django.core.management import call_command
from django.db import migrations


def create_cache_table(apps, schema_editor):
    call_command("createcachetable")


def drop_cache_table(apps, schema_editor):
    schema_editor.execute("DROP TABLE IF EXISTS cernal_cache_table")


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_apikey"),
    ]

    operations = [
        migrations.RunPython(create_cache_table, drop_cache_table),
    ]
