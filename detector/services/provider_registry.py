from __future__ import annotations

from django.conf import settings

from detector.services.providers.illuminarty_provider import IlluminartyProvider
from detector.services.providers.reality_defender_provider import RealityDefenderProvider


class ProviderRegistry:
    def __init__(
        self,
        illuminarty_provider: IlluminartyProvider | None = None,
        reality_defender_provider: RealityDefenderProvider | None = None,
    ):
        self.illuminarty_provider = illuminarty_provider or IlluminartyProvider()
        self.reality_defender_provider = reality_defender_provider or RealityDefenderProvider()

    def image_providers(self) -> list:
        return [self.illuminarty_provider, self.reality_defender_provider]

    def video_providers(self) -> list:
        if not settings.ENABLE_EXTERNAL_VIDEO_PROVIDERS:
            return []
        return [self.reality_defender_provider]
