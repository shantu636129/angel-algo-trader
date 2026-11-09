from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, status
from pydantic import BaseModel
from typing import Optional, Any
import logging

from core.telegram_alert import TelegramAlert

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AngelWebhook")

app = FastAPI(title="Angel One Postback Handler")

# Single shared alert client for the whole webhook process
telegram = TelegramAlert()


# --- 1. Schema Definition for Postback Payload ---
class OrderPostbackPayload(BaseModel):
    variety: Optional[str] = None
    ordertype: Optional[str] = None
    producttype: Optional[str] = None
    duration: Optional[str] = None
    price: Optional[float] = 0.0
    triggerprice: Optional[float] = 0.0
    quantity: Optional[str] = "0"
    disclosedquantity: Optional[str] = "0"
    squareoff: Optional[float] = 0.0
    stoploss: Optional[float] = 0.0
    trailingstoploss: Optional[float] = 0.0
    tradingsymbol: Optional[str] = None
    transactiontype: Optional[str] = None
    exchange: Optional[str] = None
    symboltoken: Optional[str] = None
    ordertag: Optional[str] = None
    instrumenttype: Optional[str] = None
    strikeprice: Optional[float] = -1.0
    optiontype: Optional[str] = None
    expirydate: Optional[str] = None
    lotsize: Optional[str] = "1"
    cancelsize: Optional[str] = "0"
    averageprice: Optional[float] = 0.0
    filledshares: Optional[str] = "0"
    unfilledshares: Optional[str] = "0"
    orderid: Optional[str] = None
    text: Optional[str] = None
    status: Optional[str] = None
    orderstatus: Optional[str] = None
    updatetime: Optional[str] = None
    exchtime: Optional[str] = None
    exchorderupdatetime: Optional[str] = None
    fillid: Optional[str] = None
    filltime: Optional[str] = None
    parentorderid: Optional[str] = None
    clientcode: Optional[str] = None

    class Config:
        extra = "allow"  # Protects against unannounced payload fields


# --- 2. Background Processing Handler ---
def process_order_update(payload: OrderPostbackPayload):
    """
    Executes business logic for incoming order updates.
    Runs asynchronously in the background so the webhook endpoint returns HTTP 200 instantly.
    """
    try:
        logger.info(
            f"[POSTBACK] Received update for Order ID: {payload.orderid} | "
            f"Symbol: {payload.tradingsymbol} | Status: {payload.orderstatus} | "
            f"Filled: {payload.filledshares}/{payload.quantity}"
        )

        if payload.orderstatus in ["complete", "executed"]:
            logger.info(f"[POSTBACK] 🎉 Order Fully Executed at avg price: {payload.averageprice}")
            telegram.send_order_alert(
                symbol=payload.tradingsymbol,
                status=payload.orderstatus,
                qty=payload.filledshares,
                avg_price=payload.averageprice,
                order_id=payload.orderid,
            )

        elif payload.orderstatus == "rejected":
            logger.warning(f"[POSTBACK] ⚠️ Order Rejected! Reason: {payload.text}")
            telegram.send_order_alert(
                symbol=payload.tradingsymbol,
                status=payload.orderstatus,
                order_id=payload.orderid,
                note=payload.text,
            )

        elif payload.orderstatus == "cancelled":
            logger.info(f"[POSTBACK] ❌ Order Cancelled: {payload.orderid}")
            telegram.send_order_alert(
                symbol=payload.tradingsymbol,
                status=payload.orderstatus,
                order_id=payload.orderid,
            )

    except Exception as e:
        logger.error(f"[POSTBACK] Error processing payload: {e}")
        telegram.send_error_alert("webhook.process_order_update", e)


# --- 3. Webhook Endpoint ---
@app.post("/api/v1/angel/postback", status_code=status.HTTP_200_OK)
async def receive_postback(payload: OrderPostbackPayload, background_tasks: BackgroundTasks):
    """
    Postback URL endpoint to be registered in Angel One Developer Portal.
    URL Format: https://your-domain-or-ip/api/v1/angel/postback
    """
    # Delegate execution to background worker to respond immediately (< 50ms)
    background_tasks.add_task(process_order_update, payload)
    return {"status": "success", "message": "Postback received"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
