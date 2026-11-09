import os

# --- Angel One SmartAPI Credentials ---
API_KEY = "YOUR_VALUE_HERE"
CLIENT_CODE = "YOUR_VALUE_HERE"
PIN = "YOUR_VALUE_HERE"
TOTP_SECRET = "YOUR_VALUE_HERE"

# --- Directory Paths ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "logs")


# --- Margin Calculator: required identity headers ---
CLIENT_LOCAL_IP = "YOUR_VALUE_HERE"
CLIENT_PUBLIC_IP = "YOUR_VALUE_HERE"
MAC_ADDRESS = "YOUR_VALUE_HERE"

# --- Telegram Alert Bot (@algo_algo_alerts_bot) ---
TELEGRAM_BOT_TOKEN = "YOUR_VALUE_HERE"
TELEGRAM_CHAT_ID = "YOUR_VALUE_HERE"
