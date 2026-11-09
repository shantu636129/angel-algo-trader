from utils.rate_limiter import rate_limited


class AngelGTT:
    def __init__(self, smart_api):
        self.smart_api = smart_api

    @rate_limited("gtt_write")  # shared cumulative 9/sec cap with modify/cancel
    def create_rule(self, trading_symbol, symbol_token, transaction_type, price, trigger_price, qty, exchange="NSE", product_type="DELIVERY", disclosed_qty=0):
        """
        Creates a GTT Rule.
        Endpoints: /rest/secure/angelbroking/gtt/v1/createRule
        """
        try:
            params = {
                "tradingsymbol": trading_symbol,
                "symboltoken": str(symbol_token),
                "exchange": exchange,
                "transactiontype": transaction_type,
                "producttype": product_type,
                "price": str(price),
                "qty": str(qty),
                "triggerprice": str(trigger_price),
                "disclosedqty": str(disclosed_qty if disclosed_qty > 0 else qty)
            }
            response = self.smart_api.gttCreateRule(params)
            if response and response.get('status'):
                rule_id = response.get('data', {}).get('id')
                print(f"[GTT] ✅ Rule Created Successfully! Rule ID: {rule_id}")
                return response.get('data')
            else:
                error_msg = response.get('message') if response else "No response"
                error_code = response.get('errorcode') if response else ""
                print(f"[GTT] ❌ Create Rule Failed [{error_code}]: {error_msg}")
                return None
        except Exception as e:
            print(f"[GTT] ❌ Exception in create_rule: {e}")
            return None

    @rate_limited("gtt_write")  # shared cumulative 9/sec cap with create/cancel
    def modify_rule(self, rule_id, symbol_token, price, trigger_price, qty, exchange="NSE", disclosed_qty=0):
        """
        Modifies an existing GTT Rule.
        Endpoints: /rest/secure/angelbroking/gtt/v1/modifyRule
        """
        try:
            params = {
                "id": str(rule_id),
                "symboltoken": str(symbol_token),
                "exchange": exchange,
                "price": str(price),
                "qty": str(qty),
                "triggerprice": str(trigger_price),
                "disclosedqty": str(disclosed_qty if disclosed_qty > 0 else qty)
            }
            response = self.smart_api.gttModifyRule(params)
            if response and response.get('status'):
                print(f"[GTT] ✅ Rule {rule_id} Modified Successfully!")
                return response.get('data')
            else:
                error_msg = response.get('message') if response else "No response"
                error_code = response.get('errorcode') if response else ""
                print(f"[GTT] ❌ Modify Rule Failed [{error_code}]: {error_msg}")
                return None
        except Exception as e:
            print(f"[GTT] ❌ Exception in modify_rule: {e}")
            return None

    @rate_limited("gtt_write")  # shared cumulative 9/sec cap with create/modify
    def cancel_rule(self, rule_id, symbol_token, exchange="NSE"):
        """
        Cancels an active GTT Rule.
        Endpoints: /rest/secure/angelbroking/gtt/v1/cancelRule
        """
        try:
            params = {
                "id": str(rule_id),
                "symboltoken": str(symbol_token),
                "exchange": exchange
            }
            response = self.smart_api.gttCancelRule(params)
            if response and response.get('status'):
                print(f"[GTT] ✅ Rule {rule_id} Cancelled Successfully!")
                return response.get('data')
            else:
                error_msg = response.get('message') if response else "No response"
                error_code = response.get('errorcode') if response else ""
                print(f"[GTT] ❌ Cancel Rule Failed [{error_code}]: {error_msg}")
                return None
        except Exception as e:
            print(f"[GTT] ❌ Exception in cancel_rule: {e}")
            return None

    @rate_limited("gtt_read")  # shared 10/sec cap with ruleList
    def get_rule_details(self, rule_id):
        """
        Fetches detailed information for a specific GTT Rule ID.
        Endpoints: /rest/secure/angelbroking/gtt/v1/ruleDetails
        """
        try:
            params = {
                "id": str(rule_id)
            }
            response = self.smart_api.gttDetails(params)
            if response and response.get('status'):
                print(f"[GTT] ✅ Rule Details retrieved for ID: {rule_id}")
                return response.get('data')
            else:
                error_msg = response.get('message') if response else "No response"
                error_code = response.get('errorcode') if response else ""
                print(f"[GTT] ❌ Rule Details Failed [{error_code}]: {error_msg}")
                return None
        except Exception as e:
            print(f"[GTT] ❌ Exception in get_rule_details: {e}")
            return None

    @rate_limited("gtt_read")  # shared 10/sec cap with ruleDetails
    def get_rule_list(self, status=["NEW", "CANCELLED", "ACTIVE", "SENTTOEXCHANGE", "FORALL"], page=1, count=10):
        """
        Fetches list of GTT rules filtered by status list, page, and count.
        Endpoints: /rest/secure/angelbroking/gtt/v1/ruleList
        """
        try:
            # Pass arguments directly as expected by SmartConnect SDK signature
            response = self.smart_api.gttLists(status, page, count)
            if response and isinstance(response, dict) and response.get('status'):
                rules = response.get('data', [])
                print(f"[GTT] ✅ Rule List Fetched! Total rules retrieved: {len(rules)}")
                return rules
            else:
                error_msg = response.get('message') if isinstance(response, dict) else response
                print(f"[GTT] ❌ Rule List Fetch Response: {error_msg}")
                return None
        except Exception as e:
            print(f"[GTT] ❌ Exception in get_rule_list: {e}")
            return None
