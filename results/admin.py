from django.contrib import admin

from results.models import DetectionResult


@admin.register(DetectionResult)
class DetectionResultAdmin(admin.ModelAdmin):
    list_display = ("id", "source_type", "result_label", "confidence_score", "created_at")
    list_filter = ("source_type", "result_label", "created_at")
    search_fields = ("original_filename", "source_url", "details")
    ordering = ("-created_at",)
