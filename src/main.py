"""
AI Arbitrage Agent - Main entry point.
Run 24/7 with asyncio + periodic scheduler.
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Ensure project root (parent of src/) is on path when run as script
if __name__ == "__main__" and "__file__" in dir():
    _root = Path(__file__).resolve().parent.parent
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from datetime import datetime

from .alerts import send_alert
from .capital_guard import CapitalGuard
from .config import Config
from .executor import Executor
from .fetchers import PolymarketFetcher, KalshiFetcher
from .portfolio_manager import PortfolioManager, Position
from .scanner import OpportunityScanner
from .ai_crew import AICrew

_components: dict = {}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


async def run_scan_cycle() -> None:
    """Single scan-execute cycle."""
    c = _components
    config, scanner, ai_crew, executor, portfolio = c.get("config"), c.get("scanner"), c.get("ai_crew"), c.get("executor"), c.get("portfolio")
    if not all([config, scanner, ai_crew, executor, portfolio]):
        return
    try:
        opps = await scanner.scan_all()
        for opp in opps:
            if not ai_crew.validate_opportunity(opp):
                logger.info("LLM rejected opportunity: %s", opp.type.value)
                continue
            safe_size = ai_crew.get_safe_size(opp)
            if safe_size <= 0:
                continue
            opp.size_usd = safe_size
            result = await executor.execute(opp)
            if result.success:
                portfolio.add_position(
                    Position(
                        id=result.order_ids[0] if result.order_ids else "unknown",
                        type=opp.type.value,
                        size_usd=opp.size_usd,
                        entry_time=datetime.utcnow(),
                        expected_profit_pct=opp.net_profit_pct,
                    )
                )
                await send_alert(
                    f"✅ Arb executed: {opp.type.value} | size=${opp.size_usd:.0f} | net={opp.net_profit_pct:.2f}%",
                    config.telegram_token,
                    config.telegram_chat_id,
                    config.discord_webhook,
                )
    except Exception as e:
        logger.exception("Scan cycle failed: %s", e)
        await send_alert(
            f"⚠️ Scan cycle error: {str(e)[:200]}",
            config.telegram_token,
            config.telegram_chat_id,
            config.discord_webhook,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Prediction Market Arbitrage Agent")
    parser.add_argument("--mode", choices=["sim", "live"], default="sim")
    parser.add_argument("--capital", type=float, default=None, help="Max capital USD")
    parser.add_argument("--no-dashboard", action="store_true", help="Disable dashboard")
    args = parser.parse_args()

    config = Config.from_env()
    if args.mode:
        config.mode = args.mode
    if args.capital is not None:
        config.capital_usd = args.capital

    guard = CapitalGuard(config.capital_usd, config)
    sim_mode = config.mode == "sim"

    poly_fetcher = PolymarketFetcher(config, simulation_mode=sim_mode)
    kalshi_fetcher = KalshiFetcher(config, simulation_mode=sim_mode)

    scanner = OpportunityScanner(config, poly_fetcher, kalshi_fetcher, guard)
    ai_crew = AICrew(config, scanner, guard)
    executor = Executor(config, guard, poly_fetcher, kalshi_fetcher)
    portfolio = PortfolioManager(guard)

    _components.update({"config": config, "scanner": scanner, "ai_crew": ai_crew, "executor": executor, "portfolio": portfolio})

    logger.info(
        "Prediction Market Arb Agent started | mode=%s | capital=$%.0f",
        config.mode, config.capital_usd,
    )

    if not args.no_dashboard:
        import uvicorn
        from contextlib import asynccontextmanager
        from fastapi import FastAPI
        from fastapi.responses import HTMLResponse

        @asynccontextmanager
        async def lifespan(app):
            sched = AsyncIOScheduler()
            sched.add_job(run_scan_cycle, "interval", seconds=config.scan_interval_seconds, id="scan")
            sched.start()
            yield
            sched.shutdown()

        app = FastAPI(title="Prediction Market Arb Agent", lifespan=lifespan)
        @app.get("/", response_class=HTMLResponse)
        async def dash():
            snap = portfolio.get_snapshot()
            return HTMLResponse(f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>PM Arb Agent</title><style>body{{font-family:system-ui;margin:2rem;background:#0f0f12;color:#e0e0e0}}h1{{color:#00d4aa}}.card{{background:#1a1a1f;padding:1.5rem;border-radius:8px;margin:1rem 0}}</style></head><body><h1>Prediction Market Arb Agent</h1><div class="card"><p>Mode: {config.mode.upper()}</p><p>Capital: ${config.capital_usd:,.0f}</p><p>Allocated: ${guard.used:,.0f}</p><p>Free: ${guard.free_capital:,.0f}</p><p>P&L: ${snap.total_pnl:,.2f}</p></div></body></html>""")
        @app.get("/health")
        async def health(): return {"status": "ok"}
        uvicorn.run(app, host=config.dashboard_host, port=config.dashboard_port)
    else:
        scheduler = AsyncIOScheduler()
        scheduler.add_job(run_scan_cycle, "interval", seconds=config.scan_interval_seconds, id="scan")
        scheduler.start()
        try:
            asyncio.get_event_loop().run_forever()
        except KeyboardInterrupt:
            pass
        finally:
            scheduler.shutdown()


if __name__ == "__main__":
    main()
