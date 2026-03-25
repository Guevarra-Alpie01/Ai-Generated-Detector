from __future__ import annotations

from django.db.models import F
from django.utils import timezone

from results.models import ProviderUsageStat


class ProviderSoftQuotaGuard:
    def __init__(self, provider_name: str, soft_limit_per_day: int):
        self.provider_name = provider_name
        self.soft_limit_per_day = soft_limit_per_day

    def allow_request(self) -> tuple[bool, str]:
        if self.soft_limit_per_day <= 0:
            return True, ""

        stat = ProviderUsageStat.objects.filter(
            provider_name=self.provider_name,
            window_date=timezone.localdate(),
        ).first()
        if stat and stat.request_count >= self.soft_limit_per_day:
            return False, (
                f"{self.provider_name.replace('_', ' ').title()} was skipped because the configured local soft quota "
                "has already been reached for today."
            )
        return True, ""

    def record_attempt(self) -> None:
        if self.soft_limit_per_day <= 0:
            return

        stat, _ = ProviderUsageStat.objects.get_or_create(
            provider_name=self.provider_name,
            window_date=timezone.localdate(),
            defaults={"request_count": 0},
        )
        ProviderUsageStat.objects.filter(pk=stat.pk).update(
            request_count=F("request_count") + 1,
            last_attempt_at=timezone.now(),
        )
