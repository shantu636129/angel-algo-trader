# Angel One Algo Trader + ML Stock Prediction

Python algorithmic trading platform built on the Angel One SmartAPI, with an ML research module.

## Features
- Broker modules: auth, orders, GTT, portfolio, margin, brokerage, option Greeks, live quotes, WebSocket streaming
- Strategies: RSI scanner, support bounce, chart patterns (rounding bottom, trendline breakout), multi-strategy Telegram alerts
- Paper-trading engine with Flask dashboard and scheduler
- ML (`ml/zentec_v10.py`): walk-forward validation, Logistic Regression + Random Forest, robustness filters, trade simulator
- Node.js MCP server (`node_mcp/`)

## Setup
1. `pip install -r requirements.txt`
2. Copy `config/settings.example.py` to `config/settings.py` and add your own credentials
3. Never commit credentials

## Disclaimer
For education and research only. Not financial advice.
