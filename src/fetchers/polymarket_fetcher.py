"""
Polymarket fetcher.
Uses Gamma API (public) for market data; py_clob_client for orders.
"""
import json
import logging
from dataclasses import dataclass
from typing import Optional

import aiohttp

from ..config import Config

logger = logging.getLogger(__name__)


def _parse_outcome_prices(m: dict) -> tuple[float, float]:
    """Parse outcomePrices JSON string; return (yes_price, no_price)."""
    raw = m.get("outcomePrices", '["0.5", "0.5"]')
    try:
        if isinstance(raw, str):
            prices = json.loads(raw)
        else:
            prices = raw
        yes_price = float(prices[0]) if len(prices) > 0 else 0.5
        no_price = float(prices[1]) if len(prices) > 1 else (1.0 - yes_price)
        return (yes_price, no_price)
    except (json.JSONDecodeError, ValueError, TypeError):
        return (0.5, 0.5)


@dataclass
class PolymarketMarket:
    """Polymarket market with YES/NO prices."""
    market_id: str
    question: str
    condition_id: str
    yes_bid: float
    yes_ask: float
    no_bid: float
    no_ask: float
    volume: float = 0.0
    yes_token_id: str = ""
    no_token_id: str = ""


class PolymarketFetcher:
    """Fetches Polymarket market data via Gamma API."""

    GAMMA_API = "https://gamma-api.polymarket.com"

    def __init__(self, config: Config, simulation_mode: bool = False):
        self.config = config
        self.simulation_mode = simulation_mode

    async def fetch_markets(self, limit: int = 50) -> list[PolymarketMarket]:
        """Fetch active, open markets from Gamma API."""
        markets = []
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.GAMMA_API}/markets?limit={limit}&active=true&closed=false"
                async with session.get(url) as resp:
                    if resp.status != 200:
                        logger.warning("Polymarket Gamma API returned %s", resp.status)
                        return []
                    data = await resp.json()
            for m in data:
                try:
                    if m.get("closed") is True:
                        continue
                    outcomes_raw = m.get("outcomes", '["Yes", "No"]')
                    outcomes = json.loads(outcomes_raw) if isinstance(outcomes_raw, str) else outcomes_raw
                    if not outcomes or "Yes" not in str(outcomes) or "No" not in str(outcomes):
                        continue
                    clob_raw = m.get("clobTokenIds", "[]")
                    clob_token_ids = json.loads(clob_raw) if isinstance(clob_raw, str) else clob_raw
                    if len(clob_token_ids) < 2:
                        continue
                    yes_price, no_price = _parse_outcome_prices(m)
                    best_bid = m.get("bestBid")
                    best_ask = m.get("bestAsk")
                    if best_bid is not None and best_ask is not None:
                        yes_bid = float(best_bid)
                        yes_ask = float(best_ask)
                        no_bid = 1.0 - yes_ask
                        no_ask = 1.0 - yes_bid
                    else:
                        yes_bid = yes_price - 0.01
                        yes_ask = yes_price + 0.01
                        no_bid = no_price - 0.01
                        no_ask = no_price + 0.01
                    markets.append(PolymarketMarket(
                        market_id=m.get("id", ""),
                        question=m.get("question", ""),
                        condition_id=m.get("conditionId", m.get("condition_id", "")),
                        yes_bid=yes_bid,
                        yes_ask=yes_ask,
                        no_bid=no_bid,
                        no_ask=no_ask,
                        volume=float(m.get("volume", m.get("volumeNum", 0)) or 0),
                        yes_token_id=str(clob_token_ids[0]) if len(clob_token_ids) > 0 else "",
                        no_token_id=str(clob_token_ids[1]) if len(clob_token_ids) > 1 else "",
                    ))
                except (KeyError, ValueError, TypeError) as e:
                    logger.debug("Skip market: %s", e)
        except Exception as e:
            logger.warning("Polymarket fetch_markets failed: %s", e)
        return markets

    async def fetch_market_by_condition(self, condition_id: str) -> Optional[PolymarketMarket]:
        """Fetch single market by condition ID."""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.GAMMA_API}/markets?condition_id={condition_id}"
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    if not data:
                        return None
                    m = data[0]
                    clob_raw = m.get("clobTokenIds", "[]")
                    clob_token_ids = json.loads(clob_raw) if isinstance(clob_raw, str) else clob_raw
                    yes_price, no_price = _parse_outcome_prices(m)
                    best_bid = m.get("bestBid")
                    best_ask = m.get("bestAsk")
                    if best_bid is not None and best_ask is not None:
                        yes_bid = float(best_bid)
                        yes_ask = float(best_ask)
                        no_bid = 1.0 - yes_ask
                        no_ask = 1.0 - yes_bid
                    else:
                        yes_bid = yes_price - 0.01
                        yes_ask = yes_price + 0.01
                        no_bid = no_price - 0.01
                        no_ask = no_price + 0.01
                    return PolymarketMarket(
                        market_id=m.get("id", ""),
                        question=m.get("question", ""),
                        condition_id=condition_id,
                        yes_bid=yes_bid,
                        yes_ask=yes_ask,
                        no_bid=no_bid,
                        no_ask=no_ask,
                        volume=float(m.get("volume", m.get("volumeNum", 0)) or 0),
                        yes_token_id=str(clob_token_ids[0]) if len(clob_token_ids) > 0 else "",
                        no_token_id=str(clob_token_ids[1]) if len(clob_token_ids) > 1 else "",
                    )
        except Exception as e:
            logger.warning("fetch_market_by_condition failed: %s", e)
        return None
