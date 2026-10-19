from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("analyses", "0007_execution_lease")]

    operations = [
        migrations.AddField(
            model_name="analysisrun",
            name="name",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
    ]
