# Agent Arb - Prediction Market Arbitrage Agent

**Agent Arb** (responds to "arb") is a modular, secure, autonomous arbitrage agent for **prediction markets** (Polymarket vs Kalshi). Supports simulation and live modes with strict capital guards.

## Features

- **Capital Guard**: Never risks more than user-specified amount
- **Prediction Markets**: Polymarket + Kalshi cross-platform arb
- **AI Layer**: LLM validation for opportunity confirmation (LLM never executes trades)
- **24/7 Operation**: Async + APScheduler
- **Modes**: Simulation (fake balances) + Live
- **Alerts**: Telegram, Discord
- **Dashboard**: FastAPI + HTML

## Quick Start

```bash
cd agent_arb_repo  # or wherever you cloned this repo

# Create venv and install dependencies
python3 -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Copy env template
cp .env.example .env
# Edit .env with your API keys (optional for sim mode)

# Run in simulation mode
python run.py --mode sim --capital 5000

# Run without dashboard (scheduler only)
python run.py --mode sim --capital 5000 --no-dashboard

# Live mode (requires Polymarket + Kalshi credentials)
python run.py --mode live
```

## Project Structure

```
src/
  config.py          # Loads from .env, never hardcodes keys
  capital_guard.py   # Enforces max capital, can_allocate() before every trade
  fetchers/
    polymarket_fetcher.py  # Gamma API markets
    kalshi_fetcher.py      # Kalshi REST API
  scanner.py         # Rule-based + LLM validator (PM only)
  executor.py        # Async trade placement (sim/live)
  ai_crew.py         # LLM validation
  portfolio_manager.py  # P&L, fee-aware sizing
  alerts.py          # Telegram/Discord
  kalshi_client.py   # Kalshi authenticated orders
  main.py            # Entry point, scheduler, dashboard
```

## Arbitrage Logic

### Prediction Markets (Polymarket vs Kalshi)
- Buy YES on cheaper platform + NO on other → cost < $1 → guaranteed $1 payout
- Example: Poly YES=$0.45, Kalshi NO=$0.52 → cost $0.97 → $0.03 profit/contract
- Question similarity matching to pair equivalent events
- LLM validates: "Exact same event, identical resolution?"
- Threshold: 0.5% net after fees

## Warnings

- **Educational use only**. Markets move fast; opportunities disappear quickly.
- Fees + slippage can turn profit negative.
- Prediction markets have resolution risk if events are ambiguous.
- Regulatory: KYC on Kalshi; some jurisdictions restrict.
- **Never share API keys.** Test with tiny capital first.

## Extensibility

- Add PM platforms: new fetcher + scanner logic
- Swap LLM: change `AIConfig.provider` / `langchain-openai` to Grok, etc.

## License

MIT
