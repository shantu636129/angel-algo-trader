import sys
from core.auth import AngelAuth
from core.gtt import AngelGTT
from core.order_manager import AngelOrderManager
from core.brokerage import AngelBrokerageCalculator
from core.portfolio import AngelPortfolioManager
from core.edis import AngelEDISManager
from core.margin import AngelMarginCalculator
from core.market_data import AngelMarketData
from core.option_greeks import AngelOptionGreeks
from core.historical_data import AngelCandleData, AngelOIData


def main():
    print("=== Testing Complete Angel One Integration ===")

    # ----------------------------------------------------
    # 0. Authentication
    # ----------------------------------------------------
    auth = AngelAuth()
    if not auth.login():
        print("❌ Login failed.")
        sys.exit(1)

    # Initialize Modules
    gtt = AngelGTT(auth.smart_api)
    om = AngelOrderManager(auth.smart_api)
    calc = AngelBrokerageCalculator(auth.smart_api)
    pm = AngelPortfolioManager(auth.smart_api)
    edis = AngelEDISManager(auth.smart_api)
    margin = AngelMarginCalculator(auth.smart_api)
    quote = AngelMarketData(auth.smart_api)
    greeks = AngelOptionGreeks(auth.smart_api)
    candles = AngelCandleData(auth.smart_api)
    oi = AngelOIData(auth.smart_api)

    # ----------------------------------------------------
    # SECTION 1: GTT Module Tests
    # ----------------------------------------------------
    print("\n==============================================")
    print("           1. TESTING GTT MODULE              ")
    print("==============================================")

    print("\n--- 1.1 Fetching GTT Rule List ---")
    rules = gtt.get_rule_list(status=["FORALL"], page=1, count=10)

    if rules:
        print(f"Rules Found: {rules}")
        first_rule_id = rules[0].get("id")
        print(f"\n--- 1.2 Fetching GTT Rule Details for ID: {first_rule_id} ---")
        details = gtt.get_rule_details(first_rule_id)
        print(f"Details: {details}")
    else:
        print("No active/past GTT rules found in this account.")

    # ----------------------------------------------------
    # SECTION 2: Dynamic LTP & Orders Module Tests
    # ----------------------------------------------------
    print("\n==============================================")
    print("          2. TESTING ORDERS MODULE            ")
    print("==============================================")

    stocks_to_check = [
        {"symbol": "SBIN-EQ", "token": "3045", "exchange": "NSE"},
        {"symbol": "INFY-EQ", "token": "1594", "exchange": "NSE"},
        {"symbol": "RELIANCE-EQ", "token": "2885", "exchange": "NSE"},
    ]

    print("\n--- 2.1 Fetching Dynamic LTP Data ---")
    for stock in stocks_to_check:
        om.get_ltp(
            exchange=stock["exchange"],
            trading_symbol=stock["symbol"],
            symbol_token=stock["token"],
        )

    print("\n--- 2.2 Fetching Order Book ---")
    order_book = om.get_order_book()

    print("\n--- 2.3 Fetching Trade Book ---")
    trade_book = om.get_trade_book()

    if order_book:
        first_unique_id = order_book[0].get("uniqueorderid")
        if first_unique_id:
            print(
                f"\n--- 2.4 Fetching Individual Order Status [{first_unique_id}] ---"
            )
            om.get_individual_order_status(first_unique_id)

    # ----------------------------------------------------
    # SECTION 3: Brokerage Calculator Tests
    # ----------------------------------------------------
    print("\n==============================================")
    print("       3. TESTING BROKERAGE CALCULATOR        ")
    print("==============================================")

    sample_orders = [
        {
            "product_type": "DELIVERY",
            "transaction_type": "BUY",
            "quantity": "10",
            "price": "800",
            "exchange": "NSE",
            "symbol_name": "SBIN-EQ",
            "token": "3045",
        },
        {
            "product_type": "DELIVERY",
            "transaction_type": "BUY",
            "quantity": "10",
            "price": "800",
            "exchange": "BSE",
            "symbol_name": "500112",
            "token": "500112",
        },
    ]

    print("\n--- 3.1 Estimating Charges for Planned Orders ---")
    calc.estimate_charges(sample_orders)

    # ----------------------------------------------------
    # SECTION 4: Portfolio Module Tests
    # ----------------------------------------------------
    print("\n==============================================")
    print("          4. TESTING PORTFOLIO MODULE         ")
    print("==============================================")

    print("\n--- 4.1 Fetching Standard Holdings ---")
    pm.get_holding()

    print("\n--- 4.2 Fetching All Holdings & Summary ---")
    pm.get_all_holding()

    print("\n--- 4.3 Fetching Current Positions ---")
    pm.get_position()

    # ----------------------------------------------------
    # SECTION 5: EDIS Module Tests
    # ----------------------------------------------------
    print("\n==============================================")
    print("            5. TESTING EDIS MODULE            ")
    print("==============================================")

    print("\n--- 5.1 Testing Verify DIS (CDSL Authorization) ---")
    dis_res = edis.verify_dis(isin="INE528G01035", quantity="1")

    if dis_res and dis_res.get("ReqId"):
        req_id = dis_res.get("ReqId")
        print(f"\n--- 5.2 Fetching EDIS Transaction Status [{req_id}] ---")
        edis.get_transaction_status(req_id)

    # ----------------------------------------------------
    # SECTION 6: Margin Calculator Tests
    # ----------------------------------------------------
    print("\n==============================================")
    print("        6. TESTING MARGIN CALCULATOR          ")
    print("==============================================")

    sample_positions = [
        {
            "exchange": "NFO",
            "qty": 50,
            "price": 0,
            "product_type": "INTRADAY",
            "token": "67300",
            "trade_type": "BUY",
            "order_type": "MARKET",
        },
        {
            "exchange": "NFO",
            "qty": 50,
            "price": 0,
            "product_type": "INTRADAY",
            "token": "67308",
            "trade_type": "SELL",
            "order_type": "LIMIT",
        },
    ]

    print("\n--- 6.1 Estimating Margin for Basket of Positions ---")
    margin.estimate_margin(sample_positions)

    # ----------------------------------------------------
    # SECTION 7: Live Market Data Tests
    # ----------------------------------------------------
    print("\n==============================================")
    print("        7. TESTING LIVE MARKET DATA            ")
    print("==============================================")

    print("\n--- 7.1 Fetching FULL Quote ---")
    quote.get_quote("FULL", {"NSE": ["3045"]})

    print("\n--- 7.2 Fetching OHLC Quote ---")
    quote.get_quote("OHLC", {"NSE": ["3045"]})

    print("\n--- 7.3 Fetching LTP Quote ---")
    quote.get_quote("LTP", {"NSE": ["3045"]})

    # ----------------------------------------------------
    # SECTION 8: Option Greeks Tests
    # ----------------------------------------------------
    print("\n==============================================")
    print("        8. TESTING OPTION GREEKS               ")
    print("==============================================")

    print("\n--- 8.1 Fetching Option Greeks for TCS ---")
    greeks.get_option_greeks("TCS", "25AUG2026")

    # ----------------------------------------------------
    # SECTION 9: Historical Data Tests (Candle + OI)
    # ----------------------------------------------------
    print("\n==============================================")
    print("        9. TESTING HISTORICAL DATA MODULE      ")
    print("==============================================")

    print("\n--- 9.1 Fetching Historical Candle Data (SBIN-EQ, ONE_HOUR) ---")
    candles.get_candle_data(
        exchange="NSE",
        symboltoken="3045",
        interval="ONE_HOUR",
        fromdate="2025-07-28 09:15",
        todate="2025-07-29 15:30",
    )

    print("\n--- 9.2 Fetching Historical OI Data (NFO contract, THREE_MINUTE) ---")
    oi.get_oi_data(
        exchange="NFO",
        symboltoken="46823",
        interval="THREE_MINUTE",
        fromdate="2025-07-28 09:15",
        todate="2025-07-28 12:00",
    )

    # ----------------------------------------------------
    # SECTION 10: Clean Session Logout
    # ----------------------------------------------------
    print("\n==============================================")
    print("Terminating Session...")
    auth.logout_session()


if __name__ == "__main__":
    main()
