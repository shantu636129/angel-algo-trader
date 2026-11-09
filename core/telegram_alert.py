import requests
from config import settings


class TelegramAlert:
    """
    Lightweight Telegram Bot API wrapper for trading alerts.
    Uses the raw Bot API over HTTPS - no external telegram library dependency.

    Setup:
      1. Bot token comes from @BotFather (already configured in config/settings.py).
      2. Message your bot at least once on Telegram (any text works, e.g. "/start")
         so Telegram creates a chat with you.
      3. Run `python3 core/telegram_alert.py` directly to auto-fetch and print your
         chat_id from getUpdates, then paste it into settings.TELEGRAM_CHAT_ID.

    Design notes:
      - send() never raises - a Telegram outage or bad chat_id should never crash
        a live strategy or order-postback handler. Failures are logged and swallowed.
      - Uses Markdown parse_mode by default; if your message text contains raw
        underscores/asterisks/brackets that aren't meant as formatting (e.g. symbol
        names like NIFTY_25AUG), pass parse_mode=None to send as plain text instead.
    """

    BASE_URL = "https://api.telegram.org/bot{token}/{method}"

    def __init__(self, bot_token=None, chat_id=None):
        self.bot_token = bot_token or getattr(settings, "TELEGRAM_BOT_TOKEN", None)
        self.chat_id = chat_id or getattr(settings, "TELEGRAM_CHAT_ID", None)

        if not self.bot_token:
            print("[TELEGRAM] ⚠️ No bot token configured — alerts disabled.")
        if not self.chat_id:
            print("[TELEGRAM] ⚠️ No chat_id configured — alerts disabled. "
                  "Run `python3 core/telegram_alert.py` after messaging your bot.")

    @property
    def enabled(self):
        return bool(self.bot_token and self.chat_id)

    def send(self, message, parse_mode="Markdown", disable_notification=False):
        """
        Send a text message to the configured chat.
        Returns True on success, False on any failure (never raises).
        Pass parse_mode=None (or "") to send as plain text, e.g. if the message
        contains characters that break Markdown entity parsing.
        """
        if not self.enabled:
            return False

        url = self.BASE_URL.format(token=self.bot_token, method="sendMessage")
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "disable_notification": disable_notification,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        try:
            resp = requests.post(url, json=payload, timeout=10)
            result = resp.json()
            if result.get("ok"):
                print("[TELEGRAM] ✅ Alert sent.")
                return True
            print(f"[TELEGRAM] ❌ Send failed: {result.get('description')}")
            return False
        except Exception as e:
            print(f"[TELEGRAM] ❌ Exception sending alert: {e}")
            return False

    def send_signal_alert(self, strategy, symbol, action, price, reason=None, extra=None):
        """Convenience formatter for strategy entry/exit signals (BUY/SELL/EXIT)."""
        emoji = {"BUY": "🟢", "SELL": "🔴", "EXIT": "🟡"}.get(action.upper(), "⚪")
        lines = [
            f"{emoji} *{action.upper()} SIGNAL* — `{symbol}`",
            f"Strategy: {strategy}",
            f"Price: ₹{price}",
        ]
        if reason:
            lines.append(f"Reason: {reason}")
        if extra:
            for k, v in extra.items():
                lines.append(f"{k}: {v}")
        return self.send("\n".join(lines))

    def send_order_alert(self, symbol, status, qty=None, avg_price=None, order_id=None, note=None):
        """Convenience formatter for order execution/rejection alerts (used by core/webhook.py)."""
        emoji = {"complete": "🎉", "executed": "🎉", "rejected": "⚠️", "cancelled": "❌"}.get(status, "ℹ️")
        lines = [f"{emoji} *Order {str(status).upper()}* — `{symbol}`"]
        if qty:
            lines.append(f"Qty: {qty}")
        if avg_price:
            lines.append(f"Avg Price: ₹{avg_price}")
        if order_id:
            lines.append(f"Order ID: {order_id}")
        if note:
            lines.append(f"Note: {note}")
        return self.send("\n".join(lines))

    def send_error_alert(self, source, error):
        """Convenience formatter for cron/strategy failure alerts."""
        return self.send(f"🚨 ERROR in {source}\n{error}", parse_mode=None)

    def send_scan_candidate_alert(self, symbol, score, rating, thesis=None, stop_loss=None, entry_range=None):
        """Convenience formatter for a single smallcap-pipeline scan candidate."""
        lines = [
            f"📈 SCAN HIT — {symbol}",
            f"Score: {score}/100  ({rating})",
        ]
        if entry_range:
            lines.append(f"Entry: {entry_range}")
        if stop_loss:
            lines.append(f"Stop-loss: {stop_loss}")
        if thesis:
            lines.append(f"Thesis: {thesis}")
        return self.send("\n".join(lines), parse_mode=None)

    def send_scan_summary(self, new_candidates, total_candidates, min_score, source="Smallcap Scan"):
        """
        Convenience formatter for the end-of-run summary of a scheduled scan.
        new_candidates: list of scorecard dicts newly qualifying this run (not
                        already alerted earlier the same day).
        total_candidates: total count currently >= min_score (incl. previously alerted).
        """
        if not new_candidates:
            lines = [
                f"🔎 {source} — no new candidates ≥ {min_score}",
                f"({total_candidates} total still qualifying)",
            ]
            return self.send("\n".join(lines), disable_notification=True, parse_mode=None)

        lines = [f"🔎 {source} — {len(new_candidates)} new candidate(s) ≥ {min_score}:"]
        for c in new_candidates:
            lines.append(f"  • {c['symbol']}  {c['composite_score']}/100  {c.get('rating', '')}")
        return self.send("\n".join(lines), parse_mode=None)

    _BOOK_LABELS = {
        "strong_candidate": "Strong Candidate (₹10L book)",
        "pattern_breakout": "Pattern Agent (₹10L book)",
    }

    def send_paper_trade_open_alert(self, symbol, entry_price, qty, stop_loss=None, target=None,
                                     notional=None, rating=None, book=None):
        """Convenience formatter for a smallcap-pipeline paper trade being opened.
        `book` ("strong_candidate" | "pattern_breakout") is shown when given so
        it's clear which of the two independent Rs 10L pools funded this trade."""
        lines = [f"🟢 PAPER TRADE OPENED — {symbol}"]
        if book:
            lines.append(f"Book: {self._BOOK_LABELS.get(book, book)}")
        if rating:
            lines.append(f"Rating: {rating}")
        lines.append(f"Entry: ₹{entry_price} x{qty}")
        if notional:
            lines.append(f"Notional: ₹{notional}")
        if stop_loss:
            lines.append(f"Stop-loss: ₹{stop_loss}")
        if target:
            lines.append(f"Target: ₹{target}")
        return self.send("\n".join(lines), parse_mode=None)

    def send_paper_trade_close_alert(self, symbol, exit_price, exit_reason, pnl, pnl_pct,
                                      entry_price=None, qty=None, book=None):
        """
        Convenience formatter for a smallcap-pipeline paper trade being closed
        (stop-loss hit, target hit, or flattened at end-of-day). `book` is
        shown when given so it's clear which Rs 10L pool the closed trade
        belonged to.
        """
        reason_emoji = {"target": "🎯", "stop": "🛑", "eod_flat": "⏹️"}.get(exit_reason, "ℹ️")
        reason_label = {"target": "TARGET HIT", "stop": "STOPPED OUT", "eod_flat": "EOD FLAT"}.get(
            exit_reason, str(exit_reason).upper()
        )
        pnl_emoji = "✅" if pnl is not None and pnl >= 0 else "❌"
        lines = [f"{reason_emoji} PAPER TRADE CLOSED — {symbol} ({reason_label})"]
        if book:
            lines.append(f"Book: {self._BOOK_LABELS.get(book, book)}")
        if entry_price is not None:
            lines.append(f"Entry: ₹{entry_price}" + (f" x{qty}" if qty else ""))
        lines.append(f"Exit: ₹{exit_price}")
        if pnl is not None:
            lines.append(f"{pnl_emoji} P&L: ₹{pnl} ({pnl_pct:+.2f}%)")
        return self.send("\n".join(lines), parse_mode=None)


def _fetch_chat_id(bot_token):
    """One-off helper: pulls the most recent chat_id(s) from getUpdates."""
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
    except Exception as e:
        print(f"[TELEGRAM] ❌ Could not reach Telegram API: {e}")
        return

    if not data.get("ok"):
        print(f"[TELEGRAM] ❌ getUpdates failed: {data}")
        return

    results = data.get("result", [])
    if not results:
        print("[TELEGRAM] ⚠️ No messages found yet. Open Telegram, search for your bot, "
              "and send it any message (e.g. /start), then re-run this script.")
        return

    seen = {}
    for update in results:
        msg = update.get("message") or update.get("channel_post")
        if not msg:
            continue
        chat = msg.get("chat", {})
        seen[chat.get("id")] = chat

    print("[TELEGRAM] ✅ Found chat(s):")
    for chat_id, chat in seen.items():
        label = chat.get("username") or chat.get("first_name") or chat.get("title") or "unknown"
        print(f"    chat_id = {chat_id}   ({chat.get('type')}: {label})")
    print("\nCopy the chat_id above into config/settings.py -> TELEGRAM_CHAT_ID")


if __name__ == "__main__":
    _fetch_chat_id(getattr(settings, "TELEGRAM_BOT_TOKEN", None))
