"""
AI Crew: CrewAI agents for reasoning and validation.
- MonitorAgent: fetches data continuously
- DetectorAgent: applies rules + asks LLM "is this true arb? same resolution?"
- RiskAgent: sizes position = min(remaining_capital * 0.2, max_safe_size)
- ExecutorAgent: only this one calls trade functions
"""
import logging
from typing import Optional

from .capital_guard import CapitalGuard
from .config import Config
from .scanner import Opportunity, OpportunityScanner

logger = logging.getLogger(__name__)

# Optional CrewAI - graceful fallback if not installed
try:
    from crewai import Agent, Task, Crew
    from langchain_openai import ChatOpenAI
    CREWAI_AVAILABLE = True
except ImportError:
    CREWAI_AVAILABLE = False


class AICrew:
    """
    CrewAI-based agent crew for arbitrage validation and execution decisions.
    Falls back to rule-based if CrewAI not available.
    """

    def __init__(
        self,
        config: Config,
        scanner: OpportunityScanner,
        capital_guard: CapitalGuard,
    ):
        self.config = config
        self.scanner = scanner
        self.guard = capital_guard
        self._llm = None
        self._crew = None
        if CREWAI_AVAILABLE and config.ai.api_key:
            self._init_crew()

    def _init_crew(self) -> None:
        """Initialize CrewAI agents and crew."""
        try:
            self._llm = ChatOpenAI(
                model=self.config.ai.model,
                api_key=self.config.ai.api_key,
                temperature=self.config.ai.temperature,
            )
            monitor = Agent(
                role="Market Monitor",
                goal="Continuously track market data and surface anomalies",
                backstory="Expert at monitoring crypto and prediction markets.",
                llm=self._llm,
                allow_delegation=False,
            )
            detector = Agent(
                role="Arbitrage Detector",
                goal="Validate if an opportunity is true arbitrage with identical resolution",
                backstory="Expert at identifying cross-market arbitrage and basis risk.",
                llm=self._llm,
                allow_delegation=False,
            )
            risk = Agent(
                role="Risk Assessor",
                goal="Size positions safely: min(remaining_capital*0.2, max_safe_size)",
                backstory="Conservative risk manager for trading systems.",
                llm=self._llm,
                allow_delegation=False,
            )
            executor_agent = Agent(
                role="Executor",
                goal="Only this agent may call trade execution functions",
                backstory="Trusted executor that follows risk-approved sizes.",
                llm=self._llm,
                allow_delegation=False,
            )
            self._crew = Crew(
                agents=[monitor, detector, risk, executor_agent],
                verbose=True,
            )
        except Exception as e:
            logger.warning("CrewAI init failed: %s. Using rule-based fallback.", e)
            self._crew = None

    def validate_opportunity(self, opp: Opportunity) -> bool:
        """
        Ask LLM: "Is this exact same event with identical resolution source?"
        Returns True if validated.
        """
        if not self._llm or not self.config.ai.api_key:
            # Rule-based fallback: accept if net profit above threshold
            return opp.net_profit_pct >= self.config.pm_min_profit_pct
        try:
            prompt = f"""
            Validate this arbitrage opportunity:
            Type: {opp.type.value}
            Net profit %: {opp.net_profit_pct:.2f}
            Details: {opp.details}
            For prediction markets: Is this the EXACT same event with identical resolution source?
            Reply with ONLY 'YES' or 'NO'.
            """
            response = self._llm.invoke(prompt)
            output = str(response.content).strip().upper()
            return "YES" in output
        except Exception as e:
            logger.warning("LLM validation failed: %s. Defaulting to accept.", e)
            return opp.net_profit_pct >= self.config.pm_min_profit_pct

    def get_safe_size(self, opp: Opportunity) -> float:
        """RiskAgent logic: min(remaining * 0.2, suggested size)."""
        return self.guard.get_safe_position_size(
            opp.size_usd,
            max_pct=self.config.max_position_pct_of_capital,
        )
