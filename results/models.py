from django.db import models

from media_handler.constants import SourceTypes


class DetectionResult(models.Model):
    source_type = models.CharField(max_length=20, choices=SourceTypes.CHOICES, db_index=True)
    uploaded_file = models.FileField(upload_to="uploads/", blank=True, null=True)
    source_url = models.URLField(blank=True)
    original_filename = models.CharField(max_length=255, blank=True)
    result_label = models.CharField(max_length=32, blank=True)
    confidence_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    details = models.TextField(blank=True)
    score_breakdown = models.JSONField(default=dict, blank=True)
    source_metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        source = self.original_filename or self.source_url or self.source_type
        return f"{source} -> {self.result_label or 'Pending'}"
