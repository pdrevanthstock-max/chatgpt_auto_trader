from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from application.multi_index_coordinator import IndexScanResult
from application.capital_affordability import build_capital_affordability
from application.scan_diagnostics import ScanFunnel, build_scan_diagnostics
from config.settings import TradingConfig
from core.enums import MarketRegime
from core.index_registry import IndexSpec
from core.models import ScoredCandidate, Trade, TradePlan
from data.candle_store import CompletedCandleStore, completed_candles
from data.market_cache import MarketCache
from execution.execution_validator import ExecutionValidator
from strategy.divergence_scanner import DivergenceScanner
from strategy.entry_signal import EntrySignal
from strategy.liquidity_filter import LiquidityFilter
from strategy.pair_candidate_generator import PairCandidateGenerator
from strategy.pair_ranker import PairRanker
from strategy.position_sizer import PositionSizer
from strategy.trade_planner import TradePlanner


@dataclass(frozen=True)
class IndexOpportunity:
    index_symbol: str
    scored_candidate: ScoredCandidate
    plan: TradePlan

    @property
    def projected_net(self) -> float:
        return float(self.scored_candidate.projected_net_profit)

    @property
    def confidence(self) -> float:
        return float(self.scored_candidate.confidence)


class IndexScanner:
    """Runs one isolated strategy pipeline for one index market context."""

    def __init__(
        self,
        *,
        spec: IndexSpec,
        cache: MarketCache,
        config: TradingConfig,
        candle_store: CompletedCandleStore | None = None,
        require_completed: bool = True,
    ) -> None:
        self.spec = spec
        self.cache = cache
        self.config = config
        candles = candle_store or completed_candles
        self.generator = PairCandidateGenerator(
            cache,
            strike_step=spec.strike_step,
            depth=4,
        )
        self.liquidity = LiquidityFilter(cache)
        self.divergence = DivergenceScanner(
            candles,
            index_symbol=spec.symbol,
            require_completed=require_completed,
            cache=cache,
        )
        self.entry_signal = EntrySignal()
        self.ranker = PairRanker(cache)
        self.sizer = PositionSizer()
        self.planner = TradePlanner()
        self.validator = ExecutionValidator(cache)

    def scan(
        self,
        *,
        regime: MarketRegime,
        spot_trend: str,
        realized_pnl: float,
        active_trade: Trade | None,
        available_capital: float,
        trading_day: date,
        cycle_id: str | None = None,
    ) -> IndexScanResult:
        pairs = self.generator.generate_candidates(
            regime,
            trading_day,
            config=self.config,
        )
        if not pairs:
            return IndexScanResult(self.spec.symbol, None, ())

        spot, _ = self.cache.get_spot()
        atm_strike = self.cache.get_atm_strike() if spot else None

        def strike_universe(
            option_type: str,
            *,
            established: bool,
        ) -> list[dict[str, object]]:
            if not atm_strike:
                return []
            position = 0 if option_type == "CE" else 1
            strikes = sorted(
                {int(pair[position]) for pair in pairs},
                key=lambda strike: (abs(strike - atm_strike), strike),
            )
            result: list[dict[str, object]] = []
            for strike in strikes:
                signed_steps = (
                    (atm_strike - strike) // self.spec.strike_step
                    if option_type == "CE"
                    else (strike - atm_strike) // self.spec.strike_step
                )
                is_established = signed_steps >= 0
                if is_established != established:
                    continue
                distance = abs(int(signed_steps))
                label = "ATM" if distance == 0 else f"{'ITM' if established else 'OTM'}{distance}"
                result.append({"strike": strike, "moneyness": label})
            return result

        universe_fields = {
            "ce_universe": strike_universe("CE", established=True),
            "pe_universe": strike_universe("PE", established=True),
            "research_ce_universe": strike_universe("CE", established=False),
            "research_pe_universe": strike_universe("PE", established=False),
        }

        ce_allowed = set(self.liquidity.filter_strikes(
            list(dict.fromkeys(ce for ce, _ in pairs)), "CE", self.config
        ))
        pe_allowed = set(self.liquidity.filter_strikes(
            list(dict.fromkeys(pe for _, pe in pairs)), "PE", self.config
        ))
        executable_pairs = [
            pair for pair in pairs
            if pair[0] in ce_allowed and pair[1] in pe_allowed
        ]
        scanned = self.divergence.scan_candidates(executable_pairs)
        survivors = self.entry_signal.evaluate_signals(
            scanned,
            regime,
            spot_trend,
            self.config,
            spot_price=spot,
            strike_step=self.spec.strike_step,
        )
        top = self.ranker.rank_candidates(
            survivors,
            self.config,
            lot_size=self.spec.lot_size,
            available_capital=available_capital,
            regime=regime,
        )
        diagnostics = build_scan_diagnostics(
            scanned=scanned,
            survivors=survivors,
            ranker_decisions=self.ranker.last_decisions,
            regime=regime,
            spot_trend=spot_trend,
            config=self.config,
            index_symbol=self.spec.symbol,
            spot_price=spot,
            atm_strike=atm_strike,
            strike_step=self.spec.strike_step,
            cycle_id=cycle_id,
            funnel=ScanFunnel(
                generated_count=len(pairs),
                quotable_count=len(executable_pairs),
                signal_count=len(survivors),
                economic_count=sum(
                    1
                    for decision in self.ranker.last_decisions.values()
                    if str(decision.get("result", "")).upper() == "PASS"
                ),
                final_count=1 if top is not None else 0,
                prefilter_rejection_reasons={
                    "LIQUIDITY_OR_QUOTE_PREFILTER": len(pairs) - len(executable_pairs)
                } if len(executable_pairs) < len(pairs) else {},
            ),
        )
        for row in diagnostics:
            row.update(universe_fields)
            ce_quote = self.cache.get_option(row["ce_strike"], "CE")
            pe_quote = self.cache.get_option(row["pe_strike"], "PE")
            if not ce_quote or not pe_quote:
                continue
            try:
                quote_times = [
                    value for value in (
                        ce_quote.get("timestamp"), pe_quote.get("timestamp")
                    ) if isinstance(value, datetime)
                ]
                as_of = (
                    datetime.now(tz=quote_times[0].tzinfo)
                    if quote_times else None
                )
                affordability = build_capital_affordability(
                    ce_ask=float(ce_quote.get("ask", ce_quote.get("last", 0.0))),
                    pe_ask=float(pe_quote.get("ask", pe_quote.get("last", 0.0))),
                    lot_size=self.spec.lot_size,
                    available_capital=available_capital,
                    deployment_fraction=self.config.max_capital_deployment_pct,
                    ce_quote_time=ce_quote.get("timestamp"),
                    pe_quote_time=pe_quote.get("timestamp"),
                    as_of=as_of,
                )
            except (TypeError, ValueError):
                continue
            row.update(affordability.as_dict())
        if top is None:
            return IndexScanResult(self.spec.symbol, None, tuple(diagnostics))

        ce_quote = self.cache.get_option(top.ce_strike, "CE")
        pe_quote = self.cache.get_option(top.pe_strike, "PE")
        if not ce_quote or not pe_quote:
            return IndexScanResult(self.spec.symbol, None, tuple(diagnostics))
        ce_ask = float(ce_quote.get("ask", 0.0) or 0.0)
        pe_ask = float(pe_quote.get("ask", 0.0) or 0.0)
        lots = self.sizer.calculate_lots(
            ce_ask,
            pe_ask,
            self.config,
            available_capital=available_capital,
            lot_size=self.spec.lot_size,
        )
        if lots <= 0:
            return IndexScanResult(self.spec.symbol, None, tuple(diagnostics))
        plan = self.planner.plan_trade(
            candidate=top,
            regime=regime,
            quantity=lots,
            ce_price=ce_ask,
            pe_price=pe_ask,
            ce_bid=ce_quote.get("bid"),
            pe_bid=pe_quote.get("bid"),
            config=self.config,
            lot_size=self.spec.lot_size,
            index_symbol=self.spec.symbol,
        )
        plan.risk_capital_at_entry = available_capital
        plan.hard_stop_loss = self.config.per_trade_loss_limit(available_capital)
        valid, reason = self.validator.validate_entry(
            plan,
            realized_pnl,
            active_trade,
            self.config,
        )
        if not valid:
            context = diagnostics[0] if diagnostics else {}
            diagnostics.insert(0, {
                "index": self.spec.symbol,
                "timestamp": context.get("timestamp"),
                "cycle_id": context.get("cycle_id", cycle_id),
                "spot": spot,
                "atm": atm_strike,
                "result": "FAIL",
                "reason": "FINAL_VALIDATION_FAILED",
                "details": reason,
                "ce_strike": top.ce_strike,
                "pe_strike": top.pe_strike,
                **universe_fields,
            })
            return IndexScanResult(self.spec.symbol, None, tuple(diagnostics))
        return IndexScanResult(
            self.spec.symbol,
            IndexOpportunity(self.spec.symbol, top, plan),
            tuple(diagnostics),
        )
