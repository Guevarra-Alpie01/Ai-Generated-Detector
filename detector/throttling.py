from rest_framework.throttling import AnonRateThrottle


class DetectionBurstRateThrottle(AnonRateThrottle):
    scope = "detection_burst"


class DetectionSustainedRateThrottle(AnonRateThrottle):
    scope = "detection_sustained"


class ResultsHistoryRateThrottle(AnonRateThrottle):
    scope = "results"
