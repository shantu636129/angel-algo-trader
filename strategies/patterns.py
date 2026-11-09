"""
patterns.py - Objective, rule-based chart-pattern detectors.

Detects two shapes on WEEKLY resampled OHLCV data:

  1. rounding_bottom  - "cup" pattern: price carves a U-shape over the lookback
                        window and has recovered back near the old high (left rim),
                        poised to break out to new highs.
  2. trendline_breakout - price has been making lower swing-highs (a descending
                        resistance line / falling wedge / descending triangle) and
                        the latest close has broken above that line.

Both return a score 0-100 and the key levels (resistance/support/target) so the
caller can decide a threshold and build an alert message. Nothing here places
orders or claims predictive power - it's pure geometry on historical candles.
"""

import numpy as np
import pandas as pd


def to_weekly(df):
    """df: DataFrame indexed by datetime with open/high/low/close/volume columns.
    Returns a weekly-resampled (W-FRI) OHLCV DataFrame."""
    w = df.resample("W-FRI").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna()
    return w


def _r_squared(y, yhat):
    ss_res = np.sum((y - yhat) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    if ss_tot == 0:
        return 0.0
    return 1 - ss_res / ss_tot


def detect_rounding_bottom(weekly, lookback=30, min_r2=0.55):
    """
    Fits a quadratic to the last `lookback` weekly closes and checks for a
    genuine U-shape whose right rim has recovered near the left rim (old high).

    Returns None if no pattern, else a dict with pattern/score/levels.
    """
    if len(weekly) < lookback:
        return None

    win = weekly.iloc[-lookback:]
    closes = win["close"].values
    x = np.arange(len(closes))

    a, b, c = np.polyfit(x, closes, 2)
    if a <= 0:
        return None  # not U-shaped (downward or flat parabola)

    yhat = a * x ** 2 + b * x + c
    r2 = _r_squared(closes, yhat)
    if r2 < min_r2:
        return None

    vertex_x = -b / (2 * a)
    n = len(closes)
    # vertex (cup low) must sit roughly in the middle of the window, not at
    # either edge, or this is just a partial trend, not a bowl.
    if not (0.15 * n <= vertex_x <= 0.85 * n):
        return None

    left_rim = closes[: max(2, n // 4)].max()
    cup_low = closes.min()
    last_close = closes[-1]

    depth = (left_rim - cup_low) / left_rim
    if depth < 0.08:
        return None  # too shallow to be a meaningful base

    recovery = last_close / left_rim  # >=1 means already at/above old high

    # recent 3-bar slope must be up (right side of the cup climbing out)
    if len(closes) >= 4 and closes[-1] <= closes[-4]:
        return None

    if recovery < 0.90 or recovery > 1.18:
        return None  # too far below the rim (not yet) or too far past it (already ran)

    vol = win["volume"].values
    avg_vol = vol[:-1].mean() if len(vol) > 1 else vol.mean()
    vol_ratio = vol[-1] / avg_vol if avg_vol > 0 else 1.0

    score = 0
    score += min(35, r2 * 35)                                # fit quality
    score += min(25, depth * 100)                             # cup depth
    score += min(25, max(0, (recovery - 0.90) / 0.10 * 25))   # proximity to rim
    score += min(15, max(0, (vol_ratio - 1) * 15))            # volume pickup
    score = round(min(100, score), 1)

    target = round(left_rim + (left_rim - cup_low), 2)

    return {
        "pattern": "rounding_bottom",
        "score": score,
        "resistance": round(left_rim, 2),
        "cup_low": round(cup_low, 2),
        "support": round(cup_low, 2),
        "target": target,
        "last_close": round(last_close, 2),
        "vol_ratio": round(vol_ratio, 2),
        "window": lookback,
    }


def _swing_highs(highs, k=2):
    """Indices where highs[i] is the strict max within the +/-k window around it."""
    idx = []
    n = len(highs)
    for i in range(k, n - k):
        seg = highs[i - k: i + k + 1]
        if highs[i] == seg.max():
            idx.append(i)
    return idx


def detect_trendline_breakout(weekly, lookback=24, swing_k=2, min_r2=0.5, confirm_bars=0):
    """
    Fits a descending line through recent swing highs and checks whether
    price has broken above it.

    confirm_bars=0 (default): fires on the crossover bar itself - the
        previous close was at/below the line, the latest close is above it.
    confirm_bars=1: requires the crossover bar (n-2) to have broken out AND
        the following bar (n-1, "confirmation bar") to have HELD above the
        line too, before firing. Entry is then the confirmation bar's close,
        one week later than an unconfirmed signal on the same setup - the
        trade-off is fewer, later, hopefully-cleaner signals in exchange for
        filtering single-week whipsaws that break out and immediately fail.

    Returns None if no pattern, else a dict with pattern/score/levels.
    """
    if len(weekly) < lookback:
        return None

    win = weekly.iloc[-lookback:]
    highs = win["high"].values
    closes = win["close"].values
    lows = win["low"].values
    n = len(win)

    exclude = 2 + confirm_bars  # fit the trendline only on bars before the breakout+confirm bars
    fit_end = n - exclude
    if fit_end < 2 * swing_k + 2:
        return None
    swing_idx = _swing_highs(highs[:fit_end], k=swing_k)
    if len(swing_idx) < 2:
        return None

    xs = np.array(swing_idx)
    ys = highs[swing_idx]
    slope, intercept = np.polyfit(xs, ys, 1)
    if slope >= 0:
        return None  # not descending

    yhat = slope * xs + intercept
    r2 = _r_squared(ys, yhat)
    if r2 < min_r2:
        return None

    if confirm_bars == 0:
        last_x = n - 1
        trend_now = slope * last_x + intercept
        trend_prev = slope * (last_x - 1) + intercept
        last_close = closes[-1]
        prev_close = closes[-2]
        # Require: previous close was at/below the line, latest close has closed
        # above it -> a genuine crossover this bar, not just already-old news.
        if not (prev_close <= trend_prev * 1.01 and last_close > trend_now):
            return None
        entry_close = last_close
        vol_idx = -1
    else:
        # breakout bar is n-2, confirmation bar is n-1 (the last bar)
        brk_x = n - 2
        conf_x = n - 1
        pre_x = n - 3
        trend_pre = slope * pre_x + intercept
        trend_brk = slope * brk_x + intercept
        trend_conf = slope * conf_x + intercept
        pre_close = closes[pre_x]
        brk_close = closes[brk_x]
        conf_close = closes[conf_x]
        # pre-breakout bar at/below line, breakout bar closes above, and the
        # NEXT bar (confirmation) also holds above the (now slightly lower,
        # since the line keeps descending) trendline value.
        if not (pre_close <= trend_pre * 1.01 and brk_close > trend_brk and conf_close > trend_conf):
            return None
        trend_now = trend_conf
        entry_close = conf_close
        vol_idx = -1  # confirmation bar is the last bar in the window

    breakout_pct = (entry_close - trend_now) / trend_now

    support = lows[max(0, n - 8):].min()  # recent swing-low as stop reference
    swing_high_val = ys.max()
    swing_low_val = lows[min(xs):].min() if len(xs) else support

    vol = win["volume"].values
    avg_vol = vol[:-1].mean() if len(vol) > 1 else vol.mean()
    vol_ratio = vol[vol_idx] / avg_vol if avg_vol > 0 else 1.0

    score = 0
    score += min(35, r2 * 35)                                 # trendline fit quality
    score += min(10, len(swing_idx) * 3)                      # more touches = more valid line
    score += min(30, max(0, breakout_pct * 100) * 6)          # breakout strength
    score += min(25, max(0, (vol_ratio - 1) * 25))            # volume confirmation
    score = round(min(100, score), 1)

    target = round(entry_close + (swing_high_val - swing_low_val), 2)

    return {
        "pattern": "trendline_breakout",
        "score": score,
        "resistance": round(trend_now, 2),
        "support": round(support, 2),
        "target": target,
        "last_close": round(entry_close, 2),
        "vol_ratio": round(vol_ratio, 2),
        "window": lookback,
        "confirm_bars": confirm_bars,
    }


def scan_symbol(daily_df, confirm_bars=0, patterns=("trendline_breakout", "rounding_bottom")):
    """
    daily_df: DataFrame with a DatetimeIndex and open/high/low/close/volume,
    daily bars. Runs the requested detectors on the weekly resample and
    returns a list of pattern-hit dicts.

    confirm_bars: passed through to detect_trendline_breakout (see its
        docstring). Has no effect on the rounding_bottom detector.
    patterns: which detectors to run - e.g. ("trendline_breakout",) alone for
        an apples-to-apples confirm_bars=0 vs confirm_bars=1 comparison.
    """
    if daily_df is None or len(daily_df) < 60:
        return []

    weekly = to_weekly(daily_df)
    hits = []
    if "trendline_breakout" in patterns:
        for lookback in (18, 26):
            hit = detect_trendline_breakout(weekly, lookback=lookback, confirm_bars=confirm_bars)
            if hit:
                hits.append(hit)
                break  # keep the first (shortest) clean fit only
    if "rounding_bottom" in patterns:
        for lookback in (20, 30, 40):
            hit = detect_rounding_bottom(weekly, lookback=lookback)
            if hit:
                hits.append(hit)
                break
    return hits
