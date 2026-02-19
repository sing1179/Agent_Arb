"""
Opportunity Scanner: Rule-based detection for prediction market arbitrage.
Polymarket vs Kalshi cross-platform arb. LLM validates opportunities.
"""
import asyncio
import re
import logging
from dataclasses import dataclass, field
from enum import Enum

from .capital_guard import CapitalGuard
from .config import Config
from .fetchers import PolymarketFetcher, KalshiFetcher
from .fetchers.polymarket_fetcher import PolymarketMarket
from .fetchers.kalshi_fetcher import KalshiMarket

logger = logging.getLogger(__name__)

_STOPWORDS = frozenset({"the", "a", "an", "will", "be", "by", "before", "after", "on", "in", "to", "of", "for", "and", "or", "is", "at"})


def _normalize_tokens(text: str) -> frozenset[str]:
    """Normalize and tokenize for similarity; exclude stopwords and short tokens."""
    if not text:
        return frozenset()
    cleaned = re.sub(r"[^\w\s]", " ", str(text).lower())
    tokens = {t for t in cleaned.split() if len(t) > 2 and t not in _STOPWORDS}
    return frozenset(tokens)


def _question_similarity(q1: str, q2: str, min_jaccard: float = 0.2) -> bool:
    """
    Check if two market questions refer to the same/similar event.
    Uses Jaccard similarity on normalized tokens.
    """
    t1 = _normalize_tokens(q1)
    t2 = _normalize_tokens(q2)
    if not t1 or not t2:
        return False
    inter = len(t1 & t2)
    union = len(t1 | t2)
    if union == 0:
        return False
    jaccard = inter / union
    return jaccard >= min_jaccard


class OpportunityType(str, Enum):
    PM_POLY_KALSHI = "pm_poly_kalshi"


@dataclass
class Opportunity:
    """Detected arbitrage opportunity."""
    type: OpportunityType
    gross_profit_pct: float
    net_profit_pct: float
    size_usd: float
    details: dict = field(default_factory=dict)
    llm_validated: bool = False


class OpportunityScanner:
    """
    Detects prediction market arbitrage (Polymarket vs Kalshi).
    Rule-based first; LLM validator confirms.
    """

    def __init__(
        self,
        config: Config,
        poly_fetcher: PolymarketFetcher,
        kalshi_fetcher: KalshiFetcher,
        capital_guard: CapitalGuard,
    ):
        self.config = config
        self.poly = poly_fetcher
        self.kalshi = kalshi_fetcher
        self.guard = capital_guard

    def _scan_pm_poly_kalshi(
        self,
        poly_markets: list[PolymarketMarket],
        kalshi_markets: list[KalshiMarket],
    ) -> list[Opportunity]:
        """
        PM arb: Buy YES on cheaper + NO on other -> cost < $1 -> guaranteed $1.
        Example: Poly YES=0.45, Kalshi NO=0.52 -> cost 0.97 -> $0.03 profit.
        Only pairs with similar questions (same event) are considered.
        """
        opps = []
        min_profit = self.config.pm_min_profit_pct / 100
        poly_fee = 0.005  # ~0.5%
        kalshi_fee = 0.003
        for pm in poly_markets:
            for km in kalshi_markets:
                if not _question_similarity(pm.question, km.title):
                    continue
                cost_poly_yes = pm.yes_ask * (1 + poly_fee)
                cost_kalshi_no = km.no_ask * (1 + kalshi_fee)
                total_cost = cost_poly_yes + cost_kalshi_no
                if total_cost < 1.0:
                    profit_per_contract = 1.0 - total_cost
                    profit_pct = profit_per_contract / total_cost * 100
                    if profit_pct >= self.config.pm_min_profit_pct:
                        size = self.guard.get_safe_position_size(1000)  # contracts
                        if size > 0:
                            opps.append(Opportunity(
                                type=OpportunityType.PM_POLY_KALSHI,
                                gross_profit_pct=profit_pct,
                                net_profit_pct=profit_pct,
                                size_usd=size,
                                details={
                                    "poly_question": pm.question,
                                    "poly_yes_ask": pm.yes_ask,
                                    "poly_yes_token_id": pm.yes_token_id,
                                    "poly_condition_id": pm.condition_id,
                                    "kalshi_title": km.title,
                                    "kalshi_ticker": km.ticker,
                                    "kalshi_no_ask": km.no_ask,
                                    "total_cost": total_cost,
                                },
                            ))
        return opps

    async def scan_all(self) -> list[Opportunity]:
        """Run PM scan (Polymarket + Kalshi)."""
        poly_mkts, kalshi_mkts = await asyncio.gather(
            self.poly.fetch_markets(limit=30),
            self.kalshi.fetch_markets(limit=30),
        )
        opps = self._scan_pm_poly_kalshi(poly_mkts, kalshi_mkts)
        logger.info("Scanner found %d PM opportunities", len(opps))
        return opps
