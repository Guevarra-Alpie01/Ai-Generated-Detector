from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="DetectionResult",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "source_type",
                    models.CharField(
                        choices=[
                            ("image", "Image"),
                            ("video", "Video"),
                            ("youtube", "YouTube"),
                            ("facebook", "Facebook"),
                        ],
                        db_index=True,
                        max_length=20,
                    ),
                ),
                ("uploaded_file", models.FileField(blank=True, null=True, upload_to="uploads/")),
                ("source_url", models.URLField(blank=True)),
                ("original_filename", models.CharField(blank=True, max_length=255)),
                ("result_label", models.CharField(blank=True, max_length=32)),
                ("confidence_score", models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ("details", models.TextField(blank=True)),
                ("score_breakdown", models.JSONField(blank=True, default=dict)),
                ("source_metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
