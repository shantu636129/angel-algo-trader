import html


class AngelEDISManager:

    def __init__(self, smart_api):
        self.smart_api = smart_api

    def verify_dis(self, isin, quantity):
        """Initiates CDSL authorization to sell holdings for non-POA accounts.

        Endpoint: /rest/secure/angelbroking/edis/v1/verifyDis
        """
        try:
            params = {"isin": str(isin), "quantity": str(quantity)}
            response = self.smart_api.verifyDis(params)

            if response and response.get("status"):
                data = response.get("data") or {}
                print(
                    f"[EDIS] ✅ DIS Verification Initiated Successfully for ISIN: {isin}"
                )
                print(f"       ReqId    : {data.get('ReqId')}")
                print(f"       DPId     : {data.get('DPId')}")
                print(f"       BOID     : {data.get('BOID')}")
                return data
            else:
                err = response.get("errorcode") if response else ""
                msg = response.get("message") if response else "No response"

                # AG1000 indicates CDSL authorization is already active for the day
                if err == "AG1000":
                    print(
                        f"[EDIS] ℹ️ CDSL Authorization Active: User is already registered with CDSL for today."
                    )
                else:
                    print(f"[EDIS] ⚠️ Verify DIS Failed [{err}]: {msg}")

                return response.get("data") if response else None

        except Exception as e:
            print(f"[EDIS] ❌ Exception in verify_dis: {e}")
            return None

    def generate_tpin(self):
        """Triggers TPIN generation on the user's registered mobile
        number/email.

        Endpoint: /rest/secure/angelbroking/edis/v1/generateTPIN
        """
        try:
            response = self.smart_api.generateTPIN()
            if response and response.get("status"):
                print(
                    f"[EDIS] ✅ TPIN Generated and sent to registered mobile/email!"
                )
                return response
            else:
                msg = response.get("message") if response else "No response"
                err = response.get("errorcode") if response else ""
                print(f"[EDIS] ❌ Generate TPIN Failed [{err}]: {msg}")
                return None
        except Exception as e:
            print(f"[EDIS] ❌ Exception in generate_tpin: {e}")
            return None

    def get_transaction_status(self, req_id):
        """Checks whether CDSL authorization has been completed for a given
        ReqId.

        Endpoint: /rest/secure/angelbroking/edis/v1/getTranStatus
        """
        try:
            params = {"ReqId": str(req_id)}
            response = self.smart_api.getEdisTransactionStatus(params)
            if response and response.get("status"):
                data = response.get("data") or {}
                trans_res = data.get("TransResDtls") or {}
                print(
                    f"[EDIS] ✅ Transaction Status Retrieved for ReqId: {req_id}"
                )
                print(f"       ResStatus: {trans_res.get('ResStatus')}")
                return data
            else:
                msg = response.get("message") if response else "No response"
                err = response.get("errorcode") if response else ""
                print(f"[EDIS] ❌ Get Transaction Status Failed [{err}]: {msg}")
                return None
        except Exception as e:
            print(f"[EDIS] ❌ Exception in get_transaction_status: {e}")
            return None

    def generate_cdsl_html_form(
        self, dp_id, req_id, trans_dtls, version="1.1"
    ):
        """Generates an auto-submitting HTML string to open CDSL verification
        page."""
        try:
            html_content = f"""<!DOCTYPE html>
<html>
<head><title>CDSL eDIS Verification</title></head>
<script>
    window.onload = function() {{ submitForm(); }};
    function submitForm() {{ document.getElementById("frmDIS").submit(); }}
</script>
<body style="text-align: center; margin-top: 50px;">
    <h3>Redirecting to CDSL eDIS Portal...</h3>
    <form id="frmDIS" name="frmDIS" method="post" action="https://edis.cdslindia.com/eDIS/VerifyDIS/">
        <input type="hidden" name="DPId" value="{html.escape(str(dp_id))}">
        <input type="hidden" name="ReqId" value="{html.escape(str(req_id))}">
        <input type="hidden" name="Version" value="{html.escape(str(version))}">
        <input type="hidden" name="TransDtls" value="{html.escape(str(trans_dtls))}">
        <input type="submit" value="Click here if not redirected automatically">
    </form>
</body>
</html>"""
            return html_content
        except Exception as e:
            print(f"[EDIS] ❌ Exception in generate_cdsl_html_form: {e}")
            return ""

