class AngelBrokerageCalculator:
    def __init__(self, smart_api):
        self.smart_api = smart_api

    def estimate_charges(self, orders_list):
        """
        Estimates total brokerage and tax breakdown for a list of planned orders.
        Endpoint: /rest/secure/angelbroking/brokerage/v1/estimateCharges
        """
        try:
            formatted_orders = []
            for order in orders_list:
                formatted_orders.append({
                    "product_type": str(order.get("product_type", "DELIVERY")),
                    "transaction_type": str(order.get("transaction_type", "BUY")),
                    "quantity": str(order.get("quantity")),
                    "price": str(order.get("price")),
                    "exchange": str(order.get("exchange", "NSE")),
                    "symbol_name": str(order.get("symbol_name")),
                    "token": str(order.get("token"))
                })

            params = {
                "orders": formatted_orders
            }

            response = self.smart_api.estimateCharges(params)

            if response and response.get('status'):
                data = response.get('data', {})
                summary = data.get('summary', {})

                print("[BROKERAGE] ✅ Estimate Charges Retrieved Successfully!")
                print(f"            Trade Value   : ₹{summary.get('trade_value')}")
                print(f"            Total Charges : ₹{summary.get('total_charges')}")

                # Safely parse category items handling potential None breakups
                breakup_items = summary.get('breakup') or []
                for category in breakup_items:
                    print(f"\n            📌 {category.get('name')}: ₹{category.get('amount')}")
                    
                    # Ensure sub_breakup defaults to empty list if None
                    sub_breakup = category.get('breakup') or []
                    for sub in sub_breakup:
                        print(f"               • {sub.get('name')}: ₹{sub.get('amount')}")

                return data
            else:
                msg = response.get('message') if response else "No response"
                err = response.get('errorcode') if response else ""
                print(f"[BROKERAGE] ❌ Estimate Charges Failed [{err}]: {msg}")
                return None
        except Exception as e:
            print(f"[BROKERAGE] ❌ Exception in estimate_charges: {e}")
            return None

