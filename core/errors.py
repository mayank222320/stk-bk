"""
Typed exception hierarchy for StockAI.
Never swallow errors silently — raise these and catch appropriately.
"""


class StockAIError(Exception):
    """Base exception for all StockAI domain and infrastructure errors."""


class DataUnavailable(StockAIError):
    """Expected error when an external data source is unreachable or blocked."""

    def __init__(self, source: str, reason: str = ""):
        self.source = source
        self.reason = reason
        super().__init__(f"Data unavailable from {source}: {reason}".strip(": "))


class DataStale(StockAIError):
    """Raised when an input fails its freshness budget."""

    def __init__(self, metric: str, age_seconds: float, max_age_seconds: float):
        self.metric = metric
        self.age_seconds = age_seconds
        self.max_age_seconds = max_age_seconds
        super().__init__(
            f"Data for {metric} is stale (age={age_seconds:.1f}s, max={max_age_seconds:.1f}s)"
        )


class LLMUnavailable(StockAIError):
    """Raised when LLM providers are rate limited or unavailable."""

    def __init__(self, provider: str, details: str = ""):
        self.provider = provider
        self.details = details
        super().__init__(f"LLM provider '{provider}' unavailable: {details}".strip(": "))


class ValidationFailed(StockAIError):
    """Raised when a business entity, trade, or recommendation fails validation."""

    def __init__(self, rule: str, details: str = ""):
        self.rule = rule
        self.details = details
        super().__init__(f"Validation failed on {rule}: {details}".strip(": "))


class ConfigError(StockAIError):
    """Raised when configuration or environment parameters are invalid."""
