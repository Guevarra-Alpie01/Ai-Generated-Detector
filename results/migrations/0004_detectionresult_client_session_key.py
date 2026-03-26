from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("results", "0003_detectionresult_content_sha256"),
    ]

    operations = [
        migrations.AddField(
            model_name="detectionresult",
            name="client_session_key",
            field=models.CharField(blank=True, db_index=True, max_length=64),
        ),
    ]
