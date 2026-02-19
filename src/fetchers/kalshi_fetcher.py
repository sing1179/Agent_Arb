"""
Kalshi fetcher.
Uses public API for market data; authenticated for orders.
Orderbook: GET /markets/{ticker}/orderbook returns yes/no arrays of [price_cents, qty].
Price in cents (1-99); best bid is last element (sorted ascending).
YES bid at X = NO ask at (100-X).
"""
import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

import aiohttp

from ..config import Config

logger = logging.getLogger(__name__)


def _parse_orderbook_prices(orderbook: dict, last_price: float) -> tuple[float, float, float, float]:
    """
    Parse Kalshi orderbook. Returns (yes_bid, yes_ask, no_bid, no_ask).
    Orderbook has yes/no as [[price_cents, qty], ...] sorted ascending; best = last.
    """
    yes_bid = last_price - 0.02
    yes_ask = last_price + 0.02
    no_bid = 1.0 - yes_ask
    no_ask = 1.0 - yes_bid
    yes_arr = orderbook.get("yes") or []
    no_arr = orderbook.get("no") or []
    if yes_arr:
        best_yes = yes_arr[-1] if isinstance(yes_arr[-1], (list, tuple)) else yes_arr[-1]
        price_cents = best_yes[0] if isinstance(best_yes, (list, tuple)) else best_yes
        yes_bid = float(price_cents) / 100
    if no_arr:
        best_no = no_arr[-1] if isinstance(no_arr[-1], (list, tuple)) else no_arr[-1]
        price_cents = best_no[0] if isinstance(best_no, (list, tuple)) else best_no
        no_bid = float(price_cents) / 100
        yes_ask = 1.0 - no_bid
    no_ask = 1.0 - yes_bid
    return (yes_bid, yes_ask, no_bid, no_ask)


@dataclass
class KalshiMarket:
    """Kalshi market with YES/NO prices."""
    market_id: str
    ticker: str
    title: str
    yes_bid: float
    yes_ask: float
    no_bid: float
    no_ask: float
    volume: float = 0.0


class KalshiFetcher:
    """Fetches Kalshi market data via REST API."""

    def __init__(self, config: Config, simulation_mode: bool = False):
        self.config = config
        self.simulation_mode = simulation_mode
        self.base_url = config.kalshi.base_url

    async def _fetch_orderbook(self, session: aiohttp.ClientSession, ticker: str) -> dict:
        """Fetch orderbook for a single market."""
        try:
            url = f"{self.base_url}/markets/{ticker}/orderbook"
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("orderbook", {})
        except Exception as e:
            logger.debug("Orderbook fetch %s failed: %s", ticker, e)
        return {}

    async def fetch_markets(self, limit: int = 50) -> list[KalshiMarket]:
        """Fetch active markets from Kalshi public API."""
        markets = []
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/markets?limit={limit}&status=open"
                async with session.get(url) as resp:
                    if resp.status != 200:
                        logger.warning("Kalshi API returned %s", resp.status)
                        return []
                    data = await resp.json()
                items = data.get("markets", data) if isinstance(data, dict) else data
                if not isinstance(items, list):
                    items = []
                tickers = [m.get("ticker") or m.get("market_ticker", "") for m in items]
                tickers = [t for t in tickers if t]
                orderbooks = await asyncio.gather(*[self._fetch_orderbook(session, t) for t in tickers]) if tickers else []
                ob_by_ticker = dict(zip(tickers, orderbooks)) if tickers else {}
            for m in items:
                try:
                    ticker = m.get("ticker", m.get("market_ticker", ""))
                    if not ticker:
                        continue
                    last = float(m.get("last_price", m.get("close_price", 0.5)) or 0.5)
                    orderbook = ob_by_ticker.get(ticker, {})
                    yes_bid, yes_ask, no_bid, no_ask = _parse_orderbook_prices(orderbook, last)
                    markets.append(KalshiMarket(
                        market_id=m.get("id", ticker),
                        ticker=ticker,
                        title=m.get("title", m.get("subtitle", "")),
                        yes_bid=yes_bid,
                        yes_ask=yes_ask,
                        no_bid=no_bid,
                        no_ask=no_ask,
                        volume=float(m.get("volume", 0) or 0),
                    ))
                except (KeyError, ValueError, TypeError, IndexError) as e:
                    logger.debug("Skip Kalshi market: %s", e)
        except Exception as e:
            logger.warning("Kalshi fetch_markets failed: %s", e)
        return markets

    async def fetch_market(self, ticker: str) -> Optional[KalshiMarket]:
        """Fetch single market by ticker."""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/markets/{ticker}"
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return None
                    m = await resp.json()
                orderbook = await self._fetch_orderbook(session, ticker)
                last = float(m.get("last_price", 0.5) or 0.5)
                yes_bid, yes_ask, no_bid, no_ask = _parse_orderbook_prices(orderbook, last)
                return KalshiMarket(
                    market_id=m.get("id", ticker),
                    ticker=ticker,
                    title=m.get("title", ""),
                    yes_bid=yes_bid,
                    yes_ask=yes_ask,
                    no_bid=no_bid,
                    no_ask=no_ask,
                    volume=float(m.get("volume", 0) or 0),
                )
        except Exception as e:
            logger.warning("Kalshi fetch_market failed: %s", e)
        return None
