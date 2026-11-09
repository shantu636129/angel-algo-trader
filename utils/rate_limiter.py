"""
Centralized, thread-safe rate limiter for Angel One SmartAPI endpoints.

Enforces the official per-second / per-minute / per-hour throttling limits
using sliding-window counters. A single process-wide bucket per endpoint
group means limits are respected correctly even when called from multiple
threads (e.g. a strategy loop + an order-update stream thread).

Order APIs (placeOrder / modifyOrder / cancelOrder) share ONE bucket
("order") because Angel One enforces their 9 req/sec cap CUMULATIVELY
across all three. Likewise GTT create/modify/cancel share "gtt_write".

Usage:
    from utils.rate_limiter import rate_limited

    class AngelOrderManager:
        @rate_limited("order")
        def place_order(self, ...):
            ...
"""

import time
import threading
from collections import deque
from functools import wraps

# bucket_name -> (requests_per_second, requests_per_minute, requests_per_hour)
# None means "not specified by Angel One" -> that window is not enforced.
LIMITS = {
    # Auth
    "login":            (1,    None, None),   # loginByPassword / generateSession
    "generate_tokens":  (1,    None, 1000),
    "get_profile":      (3,    None, 1000),
    "logout":           (1,    None, None),
    "get_rms":          (2,    None, None),

    # Orders — placeOrder + modifyOrder + cancelOrder share this bucket
    "order":            (9,    500,  1000),
    "order_book":       (1,    None, None),
    "ltp_data":         (10,   500,  5000),
    "get_position":     (1,    None, None),
    "trade_book":       (1,    None, None),
    "convert_position": (10,   500,  5000),
    "search_scrip":     (1,    None, None),
    "order_details":    (10,   500,  5000),   # GET .../order/v1/details/{GuiOrderID}

    # Portfolio
    "get_holding":      (1,    None, None),
    "get_all_holding":  (1,    None, None),

    # Market data / margin
    "quote":            (10,   500,  5000),
    "margin":           (10,   500,  5000),

    # GTT — createRule + modifyRule + cancelRule share this bucket
    "gtt_write":        (9,    500,  5000),
    "gtt_read":         (10,   500,  5000),   # ruleDetails + ruleList share this bucket

    # Historical + option greeks
    "historical":       (3,    150,  5000),
    "option_greek":     (1,    None, None),
}


class _Bucket:
    """Sliding-window limiter covering up to 3 concurrent windows."""

    def __init__(self, per_second, per_minute, per_hour):
        self._windows = []  # list of (window_seconds, limit, deque[timestamps])
        if per_second:
            self._windows.append((1, per_second, deque()))
        if per_minute:
            self._windows.append((60, per_minute, deque()))
        if per_hour:
            self._windows.append((3600, per_hour, deque()))
        self._lock = threading.Lock()

    def acquire(self):
        """Blocks (sleeping) until a slot is free in every window, then reserves it."""
        while True:
            with self._lock:
                now = time.monotonic()
                wait_for = 0.0
                for window_secs, limit, dq in self._windows:
                    while dq and now - dq[0] >= window_secs:
                        dq.popleft()
                    if len(dq) >= limit:
                        wait_for = max(wait_for, window_secs - (now - dq[0]))
                if wait_for <= 0:
                    for _, _, dq in self._windows:
                        dq.append(now)
                    return
            # Sleep outside the lock so other threads can make progress too.
            time.sleep(min(wait_for, 5.0) + 0.01)


class RateLimiter:
    """Process-wide registry of named buckets."""

    _buckets = {}
    _registry_lock = threading.Lock()

    @classmethod
    def _get_bucket(cls, name):
        with cls._registry_lock:
            bucket = cls._buckets.get(name)
            if bucket is None:
                if name not in LIMITS:
                    raise KeyError(
                        f"Unknown rate-limit bucket '{name}'. "
                        f"Add it to utils.rate_limiter.LIMITS."
                    )
                bucket = _Bucket(*LIMITS[name])
                cls._buckets[name] = bucket
            return bucket

    @classmethod
    def acquire(cls, name):
        """Blocks until it is safe to make a call in the given bucket."""
        cls._get_bucket(name).acquire()


def rate_limited(bucket_name):
    """Decorator that throttles a method/function to the named bucket's limits."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            RateLimiter.acquire(bucket_name)
            return func(*args, **kwargs)
        return wrapper
    return decorator
