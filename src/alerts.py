"""
Alerts: Telegram and Discord notifications.
Never log private keys or full balances.
"""
import logging
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)


async def send_telegram(message: str, token: Optional[str], chat_id: Optional[str]) -> bool:
    """Send Telegram alert. Never include sensitive data in message."""
    if not token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message[:4000], "parse_mode": "HTML"}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                return resp.status == 200
    except Exception as e:
        logger.warning("Telegram send failed: %s", e)
        return False


async def send_discord(message: str, webhook: Optional[str]) -> bool:
    """Send Discord webhook alert."""
    if not webhook:
        return False
    try:
        payload = {"content": message[:2000]}
        async with aiohttp.ClientSession() as session:
            async with session.post(webhook, json=payload) as resp:
                return resp.status in (200, 204)
    except Exception as e:
        logger.warning("Discord send failed: %s", e)
        return False


async def send_alert(
    message: str,
    telegram_token: Optional[str] = None,
    telegram_chat_id: Optional[str] = None,
    discord_webhook: Optional[str] = None,
) -> None:
    """Send to all configured alert channels."""
    if telegram_token and telegram_chat_id:
        await send_telegram(message, telegram_token, telegram_chat_id)
    if discord_webhook:
        await send_discord(message, discord_webhook)
