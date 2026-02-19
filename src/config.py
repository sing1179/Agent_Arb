"""
Configuration loader for Prediction Market Arbitrage Agent.
Loads from .env - NEVER hardcode API keys.
"""
import os
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class PolymarketConfig:
    """Polymarket API configuration."""
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    private_key: Optional[str] = None
    enabled: bool = True


@dataclass
class KalshiConfig:
    """Kalshi API configuration."""
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    base_url: str = "https://api.elections.kalshi.com/trade-api/v2"
    enabled: bool = True


@dataclass
class AIConfig:
    """LLM/AI configuration."""
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    api_key: Optional[str] = None
    temperature: float = 0.1


@dataclass
class Config:
    """Main application configuration."""
    # Capital & mode
    capital_usd: float = 5000.0
    mode: str = "sim"  # sim | live
    simulation_balance_multiplier: float = 1.0  # For sim: fake balances = capital * this

    # Thresholds
    pm_min_profit_pct: float = 0.5
    max_position_pct_of_capital: float = 0.2

    # Prediction markets
    polymarket: PolymarketConfig = field(default_factory=PolymarketConfig)
    kalshi: KalshiConfig = field(default_factory=KalshiConfig)

    # AI
    ai: AIConfig = field(default_factory=AIConfig)

    # Alerts
    telegram_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    discord_webhook: Optional[str] = None

    # Dashboard
    dashboard_host: str = "0.0.0.0"
    dashboard_port: int = 8000

    # Scheduler
    scan_interval_seconds: int = 5
    balance_check_interval_seconds: int = 60

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        capital = float(os.getenv("CAPITAL_USD", "5000"))
        mode = os.getenv("MODE", "sim")

        polymarket = PolymarketConfig(
            api_key=os.getenv("POLY_API_KEY"),
            api_secret=os.getenv("POLY_API_SECRET"),
            private_key=os.getenv("POLY_PRIVATE_KEY"),
            enabled=bool(os.getenv("POLY_PRIVATE_KEY")),
        )

        kalshi = KalshiConfig(
            api_key=os.getenv("KALSHI_API_KEY"),
            api_secret=os.getenv("KALSHI_API_SECRET"),
            base_url=os.getenv("KALSHI_BASE_URL", "https://api.elections.kalshi.com/trade-api/v2"),
            enabled=bool(os.getenv("KALSHI_API_KEY") and os.getenv("KALSHI_API_SECRET")),
        )

        ai = AIConfig(
            provider=os.getenv("AI_PROVIDER", "openai"),
            model=os.getenv("AI_MODEL", "gpt-4o-mini"),
            api_key=os.getenv("OPENAI_API_KEY"),
        )

        return cls(
            capital_usd=capital,
            mode=mode,
            polymarket=polymarket,
            kalshi=kalshi,
            ai=ai,
            telegram_token=os.getenv("TELEGRAM_TOKEN"),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID"),
            discord_webhook=os.getenv("DISCORD_WEBHOOK"),
        )
