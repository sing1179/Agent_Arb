"""
Kalshi authenticated client for order placement.
Uses RSA-PSS signature per Kalshi API docs.
"""
import base64
import logging
import time
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.backends import default_backend
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False


def _sign_request(private_key_pem: str, timestamp: str, method: str, path: str) -> Optional[str]:
    """Create RSA-PSS signature for Kalshi API."""
    if not CRYPTO_AVAILABLE:
        return None
    try:
        key = serialization.load_pem_private_key(
            private_key_pem.encode() if isinstance(private_key_pem, str) else private_key_pem,
            password=None,
            backend=default_backend(),
        )
        msg = f"{timestamp}{method}{path}"
        sig = key.sign(msg.encode(), padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256())
        return base64.b64encode(sig).decode()
    except Exception as e:
        logger.warning("Kalshi sign failed: %s", e)
        return None


async def place_kalshi_order(
    base_url: str,
    api_key: str,
    private_key_pem: str,
    ticker: str,
    side: str,
    action: str,
    count: int,
    yes_price: Optional[int] = None,
    no_price: Optional[int] = None,
) -> Optional[dict]:
    """Place order on Kalshi. Prices in cents (1-99)."""
    if not CRYPTO_AVAILABLE:
        logger.warning("cryptography not installed; Kalshi orders disabled")
        return None
    sign_path = "/trade-api/v2/portfolio/orders"
    url = base_url.rstrip("/") + "/portfolio/orders"
    timestamp = str(int(time.time() * 1000))
    sig = _sign_request(private_key_pem, timestamp, "POST", sign_path)
    if not sig:
        return None
    payload = {"ticker": ticker, "side": side, "action": action, "count": count, "type": "limit"}
    if yes_price is not None:
        payload["yes_price"] = yes_price
    if no_price is not None:
        payload["no_price"] = no_price
    headers = {
        "KALSHI-ACCESS-KEY": api_key,
        "KALSHI-ACCESS-TIMESTAMP": timestamp,
        "KALSHI-ACCESS-SIGNATURE": sig,
        "Content-Type": "application/json",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status in (200, 201):
                    return await resp.json()
                logger.warning("Kalshi order failed: %s %s", resp.status, await resp.text())
    except Exception as e:
        logger.warning("Kalshi order error: %s", e)
    return None
