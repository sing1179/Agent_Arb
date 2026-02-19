"""
Executor: Async trade placement for prediction markets.
Only the ExecutorAgent (via AI crew) calls these functions.
Never execute directly from LLM.
"""
import asyncio
import logging
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from .capital_guard import CapitalGuard
from .config import Config
from .scanner import Opportunity, OpportunityType

if TYPE_CHECKING:
    from .fetchers import PolymarketFetcher, KalshiFetcher

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Result of a trade execution."""
    success: bool
    opportunity_type: OpportunityType
    size_usd: float
    message: str
    order_ids: list[str] = None

    def __post_init__(self):
        if self.order_ids is None:
            self.order_ids = []


class Executor:
    """
    Fast executor for prediction market trades.
    In sim mode: logs only, no real orders.
    """

    def __init__(
        self,
        config: Config,
        capital_guard: CapitalGuard,
        poly_fetcher: Optional["PolymarketFetcher"] = None,
        kalshi_fetcher: Optional["KalshiFetcher"] = None,
    ):
        self.config = config
        self.guard = capital_guard
        self.poly_fetcher = poly_fetcher
        self.kalshi_fetcher = kalshi_fetcher
        self.simulation = config.mode == "sim"

    async def execute(self, opp: Opportunity) -> ExecutionResult:
        """
        Execute an arbitrage opportunity.
        Must have been validated by RiskAgent and approved by ExecutorAgent.
        """
        if not await self.guard.can_allocate(opp.size_usd):
            return ExecutionResult(
                success=False,
                opportunity_type=opp.type,
                size_usd=opp.size_usd,
                message="Insufficient capital allocation",
            )
        if self.simulation:
            self.guard.allocate(opp.size_usd)
            logger.info(
                "[SIM] Executed %s: size=%.2f USD, net_profit_pct=%.2f",
                opp.type.value, opp.size_usd, opp.net_profit_pct,
            )
            return ExecutionResult(
                success=True,
                opportunity_type=opp.type,
                size_usd=opp.size_usd,
                message="Simulation execution logged",
                order_ids=["sim-" + opp.type.value],
            )
        if opp.type == OpportunityType.PM_POLY_KALSHI:
            return await self._execute_pm(opp)
        return ExecutionResult(
            success=False,
            opportunity_type=opp.type,
            size_usd=opp.size_usd,
            message=f"Unsupported type: {opp.type}",
        )

    async def _execute_pm(self, opp: Opportunity) -> ExecutionResult:
        """Place YES on Polymarket, NO on Kalshi. Both legs required for arb."""
        d = opp.details
        poly_token = d.get("poly_yes_token_id")
        poly_price = d.get("poly_yes_ask", 0.5)
        kalshi_ticker = d.get("kalshi_ticker")
        kalshi_no_price = d.get("kalshi_no_ask", 0.5)
        contracts = int(opp.size_usd)  # contracts
        if not poly_token or not kalshi_ticker:
            return ExecutionResult(False, opp.type, opp.size_usd, "Missing poly token or kalshi ticker", [])
        if not self.config.polymarket.private_key or not self.config.kalshi.api_key or not self.config.kalshi.api_secret:
            return ExecutionResult(False, opp.type, opp.size_usd, "PM arb requires Poly + Kalshi credentials", [])
        order_ids = []
        if poly_token and self.config.polymarket.private_key:
            try:
                from py_clob_client.clob_types import OrderArgs, OrderType
                from py_clob_client.order_builder.constants import BUY
                from py_clob_client.client import ClobClient

                def _place_poly_order():
                    c = ClobClient("https://clob.polymarket.com", key=self.config.polymarket.private_key, chain_id=137)
                    c.set_api_creds(c.create_or_derive_api_creds())
                    return c.create_and_post_order(
                        OrderArgs(token_id=poly_token, price=round(poly_price, 2), size=float(contracts), side=BUY),
                        options={"tick_size": "0.01", "neg_risk": False},
                        order_type=OrderType.GTC,
                    )
                resp = await asyncio.to_thread(_place_poly_order)
                order_ids.append(resp.get("orderID", "poly"))
            except ImportError:
                logger.warning("py_clob_client not installed; Polymarket order skipped")
            except Exception as e:
                logger.warning("Polymarket order failed: %s", e)
                return ExecutionResult(False, opp.type, opp.size_usd, f"Polymarket: {e}", order_ids)
        if kalshi_ticker:
            from .kalshi_client import place_kalshi_order
            no_price_cents = int(round(kalshi_no_price * 100))
            kalshi_res = await place_kalshi_order(
                self.config.kalshi.base_url,
                self.config.kalshi.api_key,
                self.config.kalshi.api_secret,
                ticker=kalshi_ticker,
                side="no",
                action="buy",
                count=contracts,
                no_price=no_price_cents,
            )
            if kalshi_res:
                ord_obj = kalshi_res.get("order", kalshi_res)
                order_ids.append(str(ord_obj.get("order_id", ord_obj.get("id", "kalshi"))))
            else:
                logger.warning("Kalshi order failed")
                return ExecutionResult(False, opp.type, opp.size_usd, "Kalshi order failed", order_ids)
        if len(order_ids) < 2:
            return ExecutionResult(False, opp.type, opp.size_usd, "Both Poly and Kalshi orders required", order_ids)
        self.guard.allocate(opp.size_usd)
        return ExecutionResult(True, opp.type, opp.size_usd, "PM arb executed", order_ids)
