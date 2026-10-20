from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("results", "0004_artifact_sequence_free")]

    operations = [
        migrations.AddField(
            model_name="artifact",
            name="release_required",
            field=models.BooleanField(default=True, editable=False),
        ),
    ]
