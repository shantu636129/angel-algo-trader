"""
core/fundamentals.py — wraps Yahoo Finance (yfinance) to fetch current
fundamental ratios for NSE-listed stocks.

IMPORTANT LIMITATION (read before using in a backtest):
This only returns CURRENT/latest fundamentals, not point-in-time historical
snapshots. Using today's fundamentals to filter which stocks to include in a
PAST backtest is lookahead bias — a stock's fundamentals 2 years ago may look
very different from today (that's often WHY it became a big gainer: its
fundamentals improved over the period). This module is intended for:
  - LIVE / forward screening (build today's "quality universe", then trade
    it going forward) — no lookahead bias, fully legitimate.
  - Descriptive analysis (e.g. "what do this quarter's winners look like
    fundamentally right now") — fine for insight, not for backtesting claims.
Do NOT use this to filter historical backtest universes and claim the
resulting performance is realistic; that number would be inflated by
hindsight.
"""

import time
import yfinance as yf


class NSEFundamentals:
    NSE_SUFFIX = ".NS"

    def __init__(self, rate_limit_sleep=0.3):
        self.rate_limit_sleep = rate_limit_sleep

    def get_fundamentals(self, symbol: str):
        """
        symbol: NSE trading symbol WITHOUT exchange suffix (e.g. "BAJFINANCE")

        Returns a dict of current fundamental ratios, or None if unavailable.
        """
        try:
            ticker = yf.Ticker(f"{symbol}{self.NSE_SUFFIX}")
            info = ticker.info

            if not info or info.get("regularMarketPrice") is None:
                return None

            data = {
                "symbol": symbol,
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "market_cap": info.get("marketCap"),
                "trailing_pe": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "price_to_book": info.get("priceToBook"),
                "return_on_equity": info.get("returnOnEquity"),
                "debt_to_equity": info.get("debtToEquity"),
                "earnings_growth": info.get("earningsGrowth"),
                "revenue_growth": info.get("revenueGrowth"),
                "profit_margins": info.get("profitMargins"),
                "current_ratio": info.get("currentRatio"),
                "dividend_yield": info.get("dividendYield"),
                "beta": info.get("beta"),
                "52w_high": info.get("fiftyTwoWeekHigh"),
                "52w_low": info.get("fiftyTwoWeekLow"),
                "current_price": info.get("regularMarketPrice") or info.get("currentPrice"),
            }
            return data

        except Exception as e:
            print(f"[FUNDAMENTALS] ⚠️ {symbol}: {e}")
            return None
        finally:
            time.sleep(self.rate_limit_sleep)

    def passes_quality_filter(
        self,
        fundamentals: dict,
        min_earnings_growth=0.15,
        min_revenue_growth=0.10,
        max_debt_to_equity=150,
        min_profit_margin=0.05,
        max_pe=None,
    ):
        """
        Simple quality/growth screen. Returns (passed: bool, reasons: list[str]).
        Any missing field is treated as "unknown" and does NOT auto-fail
        (Yahoo data has gaps, especially for smaller NSE names) — but is
        noted in reasons so it's visible, not silently ignored.
        """
        if not fundamentals:
            return False, ["no data available"]

        reasons = []
        passed = True

        eg = fundamentals.get("earnings_growth")
        if eg is None:
            reasons.append("earnings_growth: unknown")
        elif eg < min_earnings_growth:
            passed = False
            reasons.append(f"earnings_growth {eg:.1%} < {min_earnings_growth:.0%}")

        rg = fundamentals.get("revenue_growth")
        if rg is None:
            reasons.append("revenue_growth: unknown")
        elif rg < min_revenue_growth:
            passed = False
            reasons.append(f"revenue_growth {rg:.1%} < {min_revenue_growth:.0%}")

        de = fundamentals.get("debt_to_equity")
        if de is None:
            reasons.append("debt_to_equity: unknown")
        elif de > max_debt_to_equity:
            passed = False
            reasons.append(f"debt_to_equity {de:.1f} > {max_debt_to_equity}")

        pm = fundamentals.get("profit_margins")
        if pm is None:
            reasons.append("profit_margins: unknown")
        elif pm < min_profit_margin:
            passed = False
            reasons.append(f"profit_margins {pm:.1%} < {min_profit_margin:.0%}")

        if max_pe is not None:
            pe = fundamentals.get("trailing_pe")
            if pe is not None and pe > max_pe:
                passed = False
                reasons.append(f"trailing_pe {pe:.1f} > {max_pe}")

        return passed, reasons
