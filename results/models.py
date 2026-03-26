from django.db import models
from django.utils import timezone

from media_handler.constants import SourceTypes


class DetectionResult(models.Model):
    client_session_key = models.CharField(max_length=64, blank=True, db_index=True)
    source_type = models.CharField(max_length=20, choices=SourceTypes.CHOICES, db_index=True)
    content_sha256 = models.CharField(max_length=64, blank=True, db_index=True)
    uploaded_file = models.FileField(upload_to="uploads/", blank=True, null=True)
    source_url = models.URLField(blank=True)
    original_filename = models.CharField(max_length=255, blank=True)
    result_label = models.CharField(max_length=32, blank=True)
    confidence_score = models.DecimalField(max_digits=6, decimal_places=4, default=0)
    details = models.TextField(blank=True)
    provider_summary = models.JSONField(default=dict, blank=True)
    provider_used = models.JSONField(default=list, blank=True)
    fallback_used = models.BooleanField(default=False)
    signals = models.JSONField(default=list, blank=True)
    audio_analysis_used = models.BooleanField(default=False)
    score_breakdown = models.JSONField(default=dict, blank=True)
    source_metadata = models.JSONField(default=dict, blank=True)
    raw_local_result = models.JSONField(default=dict, blank=True)
    raw_illuminarty_result = models.JSONField(default=dict, blank=True)
    raw_reality_defender_result = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        source = self.original_filename or self.source_url or self.source_type
        return f"{source} -> {self.result_label or 'Pending'}"


class ProviderUsageStat(models.Model):
    provider_name = models.CharField(max_length=64, db_index=True)
    window_date = models.DateField(default=timezone.localdate, db_index=True)
    request_count = models.PositiveIntegerField(default=0)
    last_attempt_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-window_date", "provider_name"]
        unique_together = ("provider_name", "window_date")

    def __str__(self):
        return f"{self.provider_name} ({self.window_date}): {self.request_count}"
