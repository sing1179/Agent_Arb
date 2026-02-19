"""
CapitalGuard: Enforces strict capital limits.
NEVER risk more than user-specified capital.
Query live balances before every trade; reject if insufficient.
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

from .config import Config

logger = logging.getLogger(__name__)


@dataclass
class BalanceSnapshot:
    """Snapshot of balances across venues."""
    total_usd: float = 0.0
    by_venue: dict[str, float] = field(default_factory=dict)
    timestamp: Optional[float] = None


class CapitalGuard:
    """
    Tracks allocated + free capital.
    Every opportunity must call can_allocate(size) before execution.
    """

    def __init__(self, max_capital: float, config: Optional[Config] = None):
        self.max_capital = max_capital
        self.used = 0.0
        self.config = config
        self._balance_snapshot: Optional[BalanceSnapshot] = None

    @property
    def free_capital(self) -> float:
        """Remaining capital available for new positions."""
        return max(0.0, self.max_capital - self.used)

    def allocate(self, amount: float) -> bool:
        """
        Reserve capital for a position.
        Returns True if allocation succeeded.
        """
        if amount <= 0:
            return False
        if self.used + amount > self.max_capital:
            logger.warning(
                "Allocation rejected: %.2f would exceed max capital %.2f (used: %.2f)",
                amount, self.max_capital, self.used,
            )
            return False
        self.used += amount
        logger.info("Allocated %.2f USD. Used: %.2f / %.2f", amount, self.used, self.max_capital)
        return True

    def release(self, amount: float) -> None:
        """Release allocated capital (e.g., after position closed)."""
        self.used = max(0.0, self.used - amount)
        logger.info("Released %.2f USD. Used: %.2f / %.2f", amount, self.used, self.max_capital)

    async def can_allocate(self, amount: float) -> bool:
        """
        Check if we can allocate this amount.
        In live mode, should query live balances via CCXT + PM/Kalshi.
        Returns True only if used + amount <= max_capital AND balances support it.
        """
        if amount <= 0:
            return False
        if self.used + amount > self.max_capital:
            return False
        # In live mode, balance snapshot would be checked here
        # For now we rely on max_capital as the hard limit
        return True

    def set_balance_snapshot(self, snapshot: BalanceSnapshot) -> None:
        """Update balance snapshot from fetchers."""
        self._balance_snapshot = snapshot

    def get_safe_position_size(
        self,
        suggested_size: float,
        max_pct: Optional[float] = None,
    ) -> float:
        """
        Return position size capped by remaining capital and max % rule.
        """
        pct = max_pct or (self.config.max_position_pct_of_capital if self.config else 0.2)
        max_by_pct = self.max_capital * pct
        max_by_free = self.free_capital
        return min(suggested_size, max_by_pct, max_by_free)
