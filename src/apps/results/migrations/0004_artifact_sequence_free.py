from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("results", "0003_alter_artifact_kind")]

    operations = [
        migrations.AddField(
            model_name="artifact",
            name="sequence_free",
            field=models.BooleanField(default=False, editable=False),
        ),
    ]
