import enum
import time
from collections.abc import Awaitable, Callable


class ErrClass(enum.Enum):
    RETRY = "RETRY"
    FATAL = "FATAL"
    RATE_LIMIT = "RATE_LIMIT"
    AUTH = "AUTH"

def classify(status: int, message: str) -> ErrClass:
    msg = message.lower()
    if status == 429 or "quota" in msg or "rate limit" in msg:
        return ErrClass.RATE_LIMIT
    if status in (401, 403) or "auth" in msg or "api key" in msg:
        return ErrClass.AUTH
    if status >= 500 or "timeout" in msg:
        return ErrClass.RETRY
    if status >= 400:
        return ErrClass.FATAL
    return ErrClass.RETRY

class KeyState:
    def __init__(self) -> None:
        self.cooldown_until: float = 0.0
        self.error_count: int = 0
        self.last_error: str | None = None

    def available(self) -> bool:
        return time.time() > self.cooldown_until

    def record(self, err_class: ErrClass, msg: str) -> None:
        self.last_error = msg
        if err_class == ErrClass.RATE_LIMIT:
            self.cool(60)
        elif err_class == ErrClass.AUTH:
            self.cool(86400)
        elif err_class == ErrClass.RETRY:
            self.error_count += 1
            self.cool(5 * self.error_count)
        else:
            self.cool(300)

    def cool(self, seconds: float) -> None:
        self.cooldown_until = time.time() + seconds

class Breaker:
    def __init__(self, name: str, threshold: int = 5, cooldown_secs: int = 300, alert_fn: Callable[[str, str], Awaitable[None]] | None = None) -> None:
        self.name = name
        self.threshold = threshold
        self.cooldown_secs = cooldown_secs
        self.failures = 0
        self.trip_time = 0.0
        self.alert_fn = alert_fn

    def allow(self) -> bool:
        if self.failures >= self.threshold:
            if time.time() - self.trip_time > self.cooldown_secs:
                # Half-open
                self.failures = 0
                return True
            return False
        return True

    async def record_failure(self, msg: str = "") -> None:
        self.failures += 1
        if self.failures == self.threshold:
            self.trip_time = time.time()
            if self.alert_fn:
                await self.alert_fn(f"LLM Breaker Tripped: {self.name}", msg)

    def record_success(self) -> None:
        self.failures = 0
        self.trip_time = 0.0
