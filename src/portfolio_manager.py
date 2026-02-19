"""
Portfolio & Risk Manager: Real-time P&L, fee-aware sizing.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .capital_guard import CapitalGuard

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Open position record."""
    id: str
    type: str
    size_usd: float
    entry_time: datetime
    expected_profit_pct: float
    status: str = "open"  # open | closed


@dataclass
class PnLSnapshot:
    """P&L snapshot."""
    total_pnl: float
    realized_pnl: float
    unrealized_pnl: float
    fees_paid: float
    timestamp: datetime


class PortfolioManager:
    """Tracks positions, P&L, and fee-aware sizing."""

    def __init__(self, capital_guard: CapitalGuard):
        self.guard = capital_guard
        self.positions: list[Position] = []
        self.realized_pnl = 0.0
        self.fees_paid = 0.0

    def add_position(self, pos: Position) -> None:
        """Record new position."""
        self.positions.append(pos)

    def close_position(self, pos_id: str, pnl: float, fees: float = 0.0) -> Optional[Position]:
        """Close position and record P&L."""
        for i, p in enumerate(self.positions):
            if p.id == pos_id and p.status == "open":
                p.status = "closed"
                self.realized_pnl += pnl
                self.fees_paid += fees
                self.guard.release(p.size_usd)
                return p
        return None

    def get_snapshot(self) -> PnLSnapshot:
        """Current P&L snapshot."""
        unrealized = sum(
            p.size_usd * (p.expected_profit_pct / 100)
            for p in self.positions if p.status == "open"
        )
        return PnLSnapshot(
            total_pnl=self.realized_pnl + unrealized - self.fees_paid,
            realized_pnl=self.realized_pnl,
            unrealized_pnl=unrealized,
            fees_paid=self.fees_paid,
            timestamp=datetime.utcnow(),
        )
