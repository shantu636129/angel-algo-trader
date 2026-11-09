from utils.rate_limiter import rate_limited


class AngelPortfolioManager:
    def __init__(self, smart_api):
        self.smart_api = smart_api

    @rate_limited("get_holding")  # 1 req/sec
    def get_holding(self):
        """
        Retrieves user's holdings list.
        Endpoint: /rest/secure/angelbroking/portfolio/v1/getHolding
        """
        try:
            response = self.smart_api.holding()
            if response and response.get('status'):
                holdings = response.get('data') or []
                print(f"[PORTFOLIO] ✅ Holdings retrieved! Total items: {len(holdings)}")
                return holdings
            else:
                print("[PORTFOLIO] ✅ Holdings is empty.")
                return []
        except Exception as e:
            print(f"[PORTFOLIO] ❌ Exception in get_holding: {e}")
            return []

    @rate_limited("get_all_holding")  # 1 req/sec
    def get_all_holding(self):
        """
        Retrieves comprehensive holdings along with portfolio total summary values.
        Endpoint: /rest/secure/angelbroking/portfolio/v1/getAllHolding
        """
        try:
            response = self.smart_api.allholding()
            if response and response.get('status'):
                data = response.get('data') or {}
                holdings = data.get('holdings') or []
                
                # Safely extract totalholding object handling None
                total = data.get('totalholding') or {}
                
                print(f"[PORTFOLIO] ✅ All Holdings retrieved! Total items: {len(holdings)}")
                print(f"            Total Value      : ₹{total.get('totalholdingvalue', 0)}")
                print(f"            Total Investment : ₹{total.get('totalinvvalue', 0)}")
                print(f"            Total P&L        : ₹{total.get('totalprofitandloss', 0)} ({total.get('totalpnlpercentage', 0)}%)")
                return data
            else:
                print("[PORTFOLIO] ✅ All Holdings is empty.")
                return {"holdings": [], "totalholding": {}}
        except Exception as e:
            print(f"[PORTFOLIO] ❌ Exception in get_all_holding: {e}")
            return {"holdings": [], "totalholding": {}}

    @rate_limited("get_position")  # 1 req/sec
    def get_position(self):
        """
        Retrieves net and day positions.
        Endpoint: /rest/secure/angelbroking/order/v1/getPosition
        """
        try:
            response = self.smart_api.position()
            if response and response.get('status'):
                positions = response.get('data') or []
                print(f"[PORTFOLIO] ✅ Positions retrieved! Total positions: {len(positions)}")
                return positions
            else:
                print("[PORTFOLIO] ✅ Positions list is empty.")
                return []
        except Exception as e:
            print(f"[PORTFOLIO] ❌ Exception in get_position: {e}")
            return []

    @rate_limited("convert_position")  # 10 req/sec, 500/min, 5000/hr
    def convert_position(
        self,
        exchange,
        symbol_token,
        old_product_type,
        new_product_type,
        trading_symbol,
        symbol_name,
        transaction_type,
        quantity,
        type="DAY",
        price_den="1",
        price_num="1",
        gen_den="1",
        gen_num="1",
        precision="2",
        multiplier="-1",
        board_lot_size="1",
        buy_qty="1",
        sell_qty="0",
        buy_amount="0",
        sell_amount="0",
        instrument_type=""
    ):
        """
        Converts position product type (e.g. DELIVERY to INTRADAY).
        Endpoint: /rest/secure/angelbroking/order/v1/convertPosition
        """
        try:
            params = {
                "exchange": exchange,
                "symboltoken": str(symbol_token),
                "oldproducttype": old_product_type,
                "newproducttype": new_product_type,
                "tradingsymbol": trading_symbol,
                "symbolname": symbol_name,
                "instrumenttype": instrument_type,
                "priceden": str(price_den),
                "pricenum": str(price_num),
                "genden": str(gen_den),
                "gennum": str(gen_num),
                "precision": str(precision),
                "multiplier": str(multiplier),
                "boardlotsize": str(board_lot_size),
                "buyqty": str(buy_qty),
                "sellqty": str(sell_qty),
                "buyamount": str(buy_amount),
                "sellamount": str(sell_amount),
                "transactiontype": transaction_type,
                "quantity": int(quantity),
                "type": type
            }
            response = self.smart_api.convertPosition(params)
            if response and response.get('status'):
                print(f"[PORTFOLIO] ✅ Position Converted Successfully for {trading_symbol}!")
                return response
            else:
                msg = response.get('message') if response else "No response"
                err = response.get('errorcode') if response else ""
                print(f"[PORTFOLIO] ❌ Convert Position Failed [{err}]: {msg}")
                return None
        except Exception as e:
            print(f"[PORTFOLIO] ❌ Exception in convert_position: {e}")
            return None
