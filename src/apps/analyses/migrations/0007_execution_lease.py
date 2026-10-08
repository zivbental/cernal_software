from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("analyses", "0006_owner_idempotency")]
    operations = [
        migrations.AddField(
            model_name="analysisrun", name="enqueued_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="analysisrun", name="execution_token",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
    ]
