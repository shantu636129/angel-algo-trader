"""
core/news_alert.py

Free, no-API-key news watcher for the Angel Algo watchlist.
Uses yfinance (already in requirements.txt) to pull the latest headlines
per NSE symbol, de-dupes against a small state file, and pushes new
headlines out via the existing TelegramAlert bot.
"""
import json
import os

import yfinance as yf

from core.telegram_alert import TelegramAlert

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEEN_FILE = os.path.join(BASE_DIR, "data", "news_seen_state.json")


def to_yf_ticker(symbol):
    """Angel-style trading symbol ('SBIN-EQ') -> Yahoo Finance NSE ticker ('SBIN.NS')."""
    base = symbol.replace("-EQ", "").replace("-BE", "").strip().upper()
    return f"{base}.NS"


class NewsWatcher:
    """
    Polls Yahoo Finance for the latest news on a watchlist of NSE symbols
    and pushes unseen headlines to Telegram. State (already-alerted IDs)
    persists to data/news_seen_state.json so restarts don't re-alert.
    """

    def __init__(self, symbols, seen_file=SEEN_FILE, telegram=None):
        self.symbols = symbols
        self.seen_file = seen_file
        self.telegram = telegram or TelegramAlert()
        self.seen_ids = self._load_seen()

    def _load_seen(self):
        try:
            with open(self.seen_file, "r") as f:
                return set(json.load(f))
        except (FileNotFoundError, json.JSONDecodeError):
            return set()

    def _save_seen(self):
        trimmed = list(self.seen_ids)[-2000:]  # cap growth
        os.makedirs(os.path.dirname(self.seen_file), exist_ok=True)
        with open(self.seen_file, "w") as f:
            json.dump(trimmed, f)

    def fetch_symbol_news(self, symbol):
        """Returns a list of news dicts for one symbol. Never raises."""
        try:
            items = yf.Ticker(to_yf_ticker(symbol)).news or []
        except Exception as e:
            print(f"[NEWS] \u26a0\ufe0f Fetch failed for {symbol}: {e}")
            return []

        out = []
        for item in items:
            # yfinance has shipped a couple of different news schemas over time;
            # handle both the flat one and the newer content-nested one.
            content = item.get("content", item) if isinstance(item, dict) else {}
            title = content.get("title") or item.get("title")
            if not title:
                continue

            provider = content.get("provider")
            publisher = provider.get("displayName") if isinstance(provider, dict) else item.get("publisher")

            canonical = content.get("canonicalUrl")
            link = canonical.get("url") if isinstance(canonical, dict) else item.get("link")

            news_id = str(item.get("id") or f"{symbol}:{title}")

            out.append({
                "id": news_id,
                "symbol": symbol,
                "title": title,
                "publisher": publisher or "Unknown",
                "link": link or "",
            })
        return out

    def prime(self):
        """Mark all currently-available headlines as seen WITHOUT alerting.
        Call this once on a fresh start so the loop doesn't dump every
        cached article Yahoo happens to have at boot time."""
        count = 0
        for symbol in self.symbols:
            for article in self.fetch_symbol_news(symbol):
                if article["id"] not in self.seen_ids:
                    self.seen_ids.add(article["id"])
                    count += 1
        if count:
            self._save_seen()
        return count

    def run_once(self):
        """Check all watchlist symbols once; alert on any unseen headline. Returns count sent."""
        new_count = 0
        for symbol in self.symbols:
            for article in self.fetch_symbol_news(symbol):
                if article["id"] in self.seen_ids:
                    continue
                self.seen_ids.add(article["id"])
                new_count += 1
                self._alert(article)
        if new_count:
            self._save_seen()
        return new_count

    def _alert(self, article):
        lines = [f"\U0001F4F0 *{article['symbol']}*", article["title"], f"_{article['publisher']}_"]
        if article["link"]:
            lines.append(article["link"])
        self.telegram.send("\n".join(lines), parse_mode="Markdown")


if __name__ == "__main__":
    watcher = NewsWatcher(["SBIN-EQ", "INFY-EQ", "RELIANCE-EQ"])
    found = watcher.run_once()
    print(f"[NEWS] Done \u2014 {found} new alert(s) sent.")
