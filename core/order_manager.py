from utils.rate_limiter import rate_limited


class AngelOrderManager:
    def __init__(self, smart_api):
        self.smart_api = smart_api

    @rate_limited("order")  # placeOrder shares the cumulative 9/sec cap with modify/cancel
    def place_order(
        self,
        trading_symbol,
        symbol_token,
        transaction_type,
        quantity,
        price=0,
        trigger_price=0,
        exchange="NSE",
        product_type="INTRADAY",
        order_type="MARKET",
        variety="NORMAL",
        duration="DAY",
        square_off=0,
        stop_loss=0,
        trailing_stop_loss=0,
        disclosed_quantity=0,
        order_tag="",
        scrip_consent="yes"
    ):
        """Places an order based on SmartAPI Order specs."""
        try:
            params = {
                "variety": variety,
                "tradingsymbol": trading_symbol,
                "symboltoken": str(symbol_token),
                "transactiontype": transaction_type,
                "exchange": exchange,
                "ordertype": order_type,
                "producttype": product_type,
                "duration": duration,
                "price": str(price),
                "squareoff": str(square_off),
                "stoploss": str(stop_loss),
                "quantity": str(quantity),
                "scripconsent": scrip_consent
            }

            if trigger_price > 0:
                params["triggerprice"] = str(trigger_price)
            if trailing_stop_loss > 0:
                params["trailingStopLoss"] = str(trailing_stop_loss)
            if disclosed_quantity > 0:
                params["disclosedquantity"] = str(disclosed_quantity)
            if order_tag:
                params["ordertag"] = str(order_tag)[:20]

            response = self.smart_api.placeOrder(params)
            if response and response.get('status'):
                data = response.get('data', {})
                print(f"[ORDER] ✅ Order Placed Successfully!")
                print(f"        Order ID       : {data.get('orderid')}")
                print(f"        Unique Order ID: {data.get('uniqueorderid')}")
                return data
            else:
                msg = response.get('message') if response else "No response"
                err = response.get('errorcode') if response else ""
                print(f"[ORDER] ❌ Place Order Failed [{err}]: {msg}")
                return None
        except Exception as e:
            print(f"[ORDER] ❌ Exception in place_order: {e}")
            return None

    @rate_limited("order")  # modifyOrder shares the cumulative 9/sec cap with place/cancel
    def modify_order(
        self,
        order_id,
        trading_symbol,
        symbol_token,
        quantity,
        price,
        order_type="LIMIT",
        exchange="NSE",
        product_type="INTRADAY",
        variety="NORMAL",
        duration="DAY"
    ):
        """Modifies a pending order."""
        try:
            params = {
                "variety": variety,
                "orderid": str(order_id),
                "ordertype": order_type,
                "producttype": product_type,
                "duration": duration,
                "price": str(price),
                "quantity": str(quantity),
                "tradingsymbol": trading_symbol,
                "symboltoken": str(symbol_token),
                "exchange": exchange
            }
            response = self.smart_api.modifyOrder(params)
            if response and response.get('status'):
                data = response.get('data', {})
                print(f"[ORDER] ✅ Order {order_id} Modified Successfully!")
                return data
            else:
                msg = response.get('message') if response else "No response"
                err = response.get('errorcode') if response else ""
                print(f"[ORDER] ❌ Modify Order Failed [{err}]: {msg}")
                return None
        except Exception as e:
            print(f"[ORDER] ❌ Exception in modify_order: {e}")
            return None

    @rate_limited("order")  # cancelOrder shares the cumulative 9/sec cap with place/modify
    def cancel_order(self, order_id, variety="NORMAL"):
        """Cancels an open order."""
        try:
            response = self.smart_api.cancelOrder(order_id, variety)
            if response and response.get('status'):
                data = response.get('data', {})
                print(f"[ORDER] ✅ Order {order_id} Cancelled Successfully!")
                return data
            else:
                msg = response.get('message') if response else "No response"
                err = response.get('errorcode') if response else ""
                print(f"[ORDER] ❌ Cancel Order Failed [{err}]: {msg}")
                return None
        except Exception as e:
            print(f"[ORDER] ❌ Exception in cancel_order: {e}")
            return None

    @rate_limited("order_book")  # 1 req/sec
    def get_order_book(self):
        """Retrieves order book safely (handles None/empty data)."""
        try:
            response = self.smart_api.orderBook()
            if response and response.get('status'):
                orders = response.get('data') or []
                print(f"[ORDER] ✅ Order Book retrieved! Total orders today: {len(orders)}")
                return orders
            else:
                print("[ORDER] ✅ Order Book is empty for today.")
                return []
        except Exception as e:
            print(f"[ORDER] ❌ Exception in get_order_book: {e}")
            return []

    @rate_limited("trade_book")  # 1 req/sec
    def get_trade_book(self):
        """Retrieves trade book safely (handles None/empty data)."""
        try:
            response = self.smart_api.tradeBook()
            if response and response.get('status'):
                trades = response.get('data') or []
                print(f"[ORDER] ✅ Trade Book retrieved! Total trades today: {len(trades)}")
                return trades
            else:
                print("[ORDER] ✅ Trade Book is empty for today.")
                return []
        except Exception as e:
            print(f"[ORDER] ❌ Exception in get_trade_book: {e}")
            return []

    @rate_limited("ltp_data")  # 10 req/sec, 500/min, 5000/hr
    def get_ltp(self, exchange, trading_symbol, symbol_token):
        """Retrieves Dynamic Last Traded Price (LTP) for any given stock."""
        try:
            response = self.smart_api.ltpData(exchange, trading_symbol, str(symbol_token))
            if response and response.get('status'):
                data = response.get('data', {})
                print(f"[ORDER] 📈 Dynamic LTP for {trading_symbol} ({exchange}): ₹{data.get('ltp')}")
                return data
            else:
                msg = response.get('message') if response else "No response"
                print(f"[ORDER] ❌ LTP Fetch Failed for {trading_symbol}: {msg}")
                return None
        except Exception as e:
            print(f"[ORDER] ❌ Exception in get_ltp: {e}")
            return None

    @rate_limited("order_details")  # 10 req/sec, 500/min, 5000/hr
    def get_individual_order_status(self, unique_order_id):
        """Retrieves details for a specific order using uniqueorderid."""
        try:
            response = self.smart_api.individualOrderStatus(unique_order_id)
            if response and response.get('status'):
                data = response.get('data', {})
                print(f"[ORDER] ✅ Order Details retrieved for Unique ID: {unique_order_id}")
                print(f"        Status: {data.get('orderstatus')}")
                print(f"        Reason: {data.get('text')}")
                return data
            else:
                msg = response.get('message') if response else "No response"
                print(f"[ORDER] ❌ Individual Order Status Fetch Failed: {msg}")
                return None
        except Exception as e:
            print(f"[ORDER] ❌ Exception in get_individual_order_status: {e}")
            return None
