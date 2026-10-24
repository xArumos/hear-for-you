import pytest

from app.errors import RateLimited
from app.ratelimit import RateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_second_call_too_soon_is_rejected() -> None:
    clock = FakeClock()
    limiter = RateLimiter(1, clock=clock)
    limiter.check()
    clock.now += 0.4
    with pytest.raises(RateLimited) as exc:
        limiter.check()
    assert exc.value.retry_after_ms == 600


def test_call_after_interval_is_allowed() -> None:
    clock = FakeClock()
    limiter = RateLimiter(1, clock=clock)
    limiter.check()
    clock.now += 0.4
    with pytest.raises(RateLimited):
        limiter.check()
    # The rejected call did not move the window, so 1.0 s after the first call is allowed.
    clock.now += 0.6
    limiter.check()


def test_zero_disables_limit() -> None:
    clock = FakeClock()
    limiter = RateLimiter(0, clock=clock)
    for _ in range(5):
        limiter.check()


def test_two_per_second_is_500ms_interval() -> None:
    clock = FakeClock()
    limiter = RateLimiter(2, clock=clock)
    limiter.check()
    clock.now += 0.3
    with pytest.raises(RateLimited) as exc:
        limiter.check()
    assert exc.value.retry_after_ms == 200
    clock.now += 0.2
    limiter.check()


def test_reset_clears_window() -> None:
    clock = FakeClock()
    limiter = RateLimiter(1, clock=clock)
    limiter.check()
    limiter.reset()
    limiter.check()
