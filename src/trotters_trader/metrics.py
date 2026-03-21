from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

from trotters_trader.catalog import register_catalog_entry
from trotters_trader.config import EvaluationConfig
from trotters_trader.domain import ClosedTrade, Fill, PortfolioSnapshot
from trotters_trader.reports import write_report_artifacts


def summarize(
    performance: list[PortfolioSnapshot],
    fills: list[Fill],
    closed_trades: list[ClosedTrade],
) -> dict[str, float]:
    if not performance:
        return {
            "total_return": 0.0,
            "max_drawdown": 0.0,
            "ending_nav": 0.0,
            "turnover": 0.0,
            "trade_count": 0.0,
            "closed_trade_count": 0.0,
            "win_rate": 0.0,
        }

    start_nav = performance[0].net_asset_value
    end_nav = performance[-1].net_asset_value
    peak = performance[0].net_asset_value
    max_drawdown = 0.0
    daily_returns = []
    total_gross_exposure = 0.0

    previous_nav = None
    for snapshot in performance:
        peak = max(peak, snapshot.net_asset_value)
        drawdown = 0.0 if peak == 0 else (peak - snapshot.net_asset_value) / peak
        max_drawdown = max(max_drawdown, drawdown)
        total_gross_exposure += snapshot.gross_exposure_ratio
        if previous_nav is not None and previous_nav != 0:
            daily_returns.append((snapshot.net_asset_value - previous_nav) / previous_nav)
        previous_nav = snapshot.net_asset_value

    total_return = 0.0 if start_nav == 0 else (end_nav - start_nav) / start_nav
    average_nav = sum(snapshot.net_asset_value for snapshot in performance) / len(performance)
    total_traded_notional = sum(fill.gross_notional for fill in fills)
    turnover = 0.0 if average_nav == 0 else total_traded_notional / average_nav
    winning_closed_trades = sum(1 for trade in closed_trades if trade.realized_pnl > 0)
    total_closed = len(closed_trades)
    total_commission = sum(fill.commission for fill in fills)
    total_slippage = sum(fill.slippage for fill in fills)
    total_spread_cost = sum(fill.spread_cost for fill in fills)
    total_stamp_duty = sum(fill.stamp_duty for fill in fills)

    return {
        "total_return": total_return,
        "max_drawdown": max_drawdown,
        "ending_nav": end_nav,
        "average_gross_exposure": total_gross_exposure / len(performance),
        "max_gross_exposure": max(snapshot.gross_exposure_ratio for snapshot in performance),
        "turnover": turnover,
        "trade_count": float(len(fills)),
        "closed_trade_count": float(total_closed),
        "win_rate": 0.0 if total_closed == 0 else winning_closed_trades / total_closed,
        "average_daily_return": 0.0 if not daily_returns else sum(daily_returns) / len(daily_returns),
        "total_commission": total_commission,
        "total_slippage": total_slippage,
        "total_spread_cost": total_spread_cost,
        "total_stamp_duty": total_stamp_duty,
    }


def build_analytics(
    performance: list[PortfolioSnapshot],
    fills: list[Fill],
    closed_trades: list[ClosedTrade],
    benchmark_performance: dict[str, list[PortfolioSnapshot]],
    primary_benchmark: str,
    evaluation_config: EvaluationConfig | None = None,
    instruments: dict[str, object] | None = None,
    basket_snapshots: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    peak = 0.0
    drawdown_series = []
    daily_return_series = []
    previous_nav = None
    for snapshot in performance:
        peak = max(peak, snapshot.net_asset_value)
        drawdown = 0.0 if peak == 0 else (peak - snapshot.net_asset_value) / peak
        drawdown_series.append({"trade_date": snapshot.trade_date, "drawdown": drawdown})
        if previous_nav is not None and previous_nav != 0:
            daily_return_series.append(
                {
                    "trade_date": snapshot.trade_date,
                    "daily_return": (snapshot.net_asset_value - previous_nav) / previous_nav,
                }
            )
        previous_nav = snapshot.net_asset_value

    primary_series = benchmark_performance.get(primary_benchmark, [])
    benchmarks = {
        name: _benchmark_summary(series)
        for name, series in benchmark_performance.items()
    }
    evaluation = _evaluate_run(performance, fills, primary_series, evaluation_config)
    risk_diagnostics = _risk_diagnostics(performance, primary_series)
    basket_diagnostics = _basket_diagnostics(basket_snapshots or [])

    return {
        "daily_returns": daily_return_series,
        "drawdowns": drawdown_series,
        "benchmark": benchmarks.get(primary_benchmark, {}),
        "benchmarks": benchmarks,
        "primary_benchmark": primary_benchmark,
        "evaluation": evaluation,
        "risk_diagnostics": risk_diagnostics,
        "basket_diagnostics": basket_diagnostics,
        "basket_snapshots": basket_snapshots or [],
        "fills_by_instrument": _fills_by_instrument(fills),
        "closed_trades": [asdict(trade) for trade in closed_trades],
    }


def _benchmark_summary(benchmark_performance: list[PortfolioSnapshot]) -> dict[str, object]:
    if not benchmark_performance:
        return {}
    start_nav = benchmark_performance[0].net_asset_value
    end_nav = benchmark_performance[-1].net_asset_value
    peak = benchmark_performance[0].net_asset_value
    max_drawdown = 0.0
    for snapshot in benchmark_performance:
        peak = max(peak, snapshot.net_asset_value)
        drawdown = 0.0 if peak == 0 else (peak - snapshot.net_asset_value) / peak
        max_drawdown = max(max_drawdown, drawdown)
    return {
        "total_return": 0.0 if start_nav == 0 else (end_nav - start_nav) / start_nav,
        "ending_nav": end_nav,
        "max_drawdown": max_drawdown,
        "performance": [asdict(snapshot) for snapshot in benchmark_performance],
    }


def _fills_by_instrument(fills: list[Fill]) -> dict[str, dict[str, float]]:
    grouped: dict[str, dict[str, float]] = {}
    for fill in fills:
        bucket = grouped.setdefault(
            fill.instrument,
            {
                "trade_count": 0.0,
                "gross_notional": 0.0,
                "commission": 0.0,
                "slippage": 0.0,
                "spread_cost": 0.0,
                "stamp_duty": 0.0,
            },
        )
        bucket["trade_count"] += 1.0
        bucket["gross_notional"] += fill.gross_notional
        bucket["commission"] += fill.commission
        bucket["slippage"] += fill.slippage
        bucket["spread_cost"] += fill.spread_cost
        bucket["stamp_duty"] += fill.stamp_duty
    return grouped


def _risk_diagnostics(
    performance: list[PortfolioSnapshot],
    benchmark_performance: list[PortfolioSnapshot],
) -> dict[str, float]:
    strategy_returns = _nav_returns(performance)
    benchmark_returns = _nav_returns(benchmark_performance)
    aligned = min(len(strategy_returns), len(benchmark_returns))
    if aligned <= 1:
        return {
            "beta_to_benchmark": 0.0,
            "correlation_to_benchmark": 0.0,
            "tracking_error": 0.0,
            "relative_volatility": 0.0,
        }

    strategy_window = strategy_returns[-aligned:]
    benchmark_window = benchmark_returns[-aligned:]
    strategy_mean = sum(strategy_window) / aligned
    benchmark_mean = sum(benchmark_window) / aligned
    covariance = sum(
        (strategy - strategy_mean) * (benchmark - benchmark_mean)
        for strategy, benchmark in zip(strategy_window, benchmark_window)
    ) / aligned
    benchmark_variance = sum((benchmark - benchmark_mean) ** 2 for benchmark in benchmark_window) / aligned
    strategy_variance = sum((strategy - strategy_mean) ** 2 for strategy in strategy_window) / aligned
    beta = 0.0 if benchmark_variance <= 0 else covariance / benchmark_variance
    strategy_vol = strategy_variance ** 0.5
    benchmark_vol = benchmark_variance ** 0.5
    correlation = 0.0
    if strategy_vol > 0 and benchmark_vol > 0:
        correlation = covariance / (strategy_vol * benchmark_vol)
    active_returns = [strategy - benchmark for strategy, benchmark in zip(strategy_window, benchmark_window)]
    active_mean = sum(active_returns) / aligned
    tracking_error = (
        sum((value - active_mean) ** 2 for value in active_returns) / aligned
    ) ** 0.5
    return {
        "beta_to_benchmark": beta,
        "correlation_to_benchmark": correlation,
        "tracking_error": tracking_error,
        "relative_volatility": 0.0 if benchmark_vol <= 0 else strategy_vol / benchmark_vol,
    }


def _nav_returns(performance: list[PortfolioSnapshot]) -> list[float]:
    returns: list[float] = []
    previous_nav: float | None = None
    for snapshot in performance:
        if previous_nav is not None and previous_nav != 0:
            returns.append((snapshot.net_asset_value - previous_nav) / previous_nav)
        previous_nav = snapshot.net_asset_value
    return returns


def _basket_diagnostics(basket_snapshots: list[dict[str, object]]) -> dict[str, float]:
    if not basket_snapshots:
        return {
            "average_portfolio_names": 0.0,
            "average_unique_sectors": 0.0,
            "average_unique_industries": 0.0,
            "average_sector_concentration": 0.0,
            "max_sector_concentration": 0.0,
            "average_industry_concentration": 0.0,
            "average_active_sector_deviation": 0.0,
            "average_active_benchmark_bucket_deviation": 0.0,
        }

    count = len(basket_snapshots)
    return {
        "average_portfolio_names": sum(float(snapshot.get("portfolio_names", 0.0) or 0.0) for snapshot in basket_snapshots) / count,
        "average_unique_sectors": sum(float(snapshot.get("unique_sectors", 0.0) or 0.0) for snapshot in basket_snapshots) / count,
        "average_unique_industries": sum(float(snapshot.get("unique_industries", 0.0) or 0.0) for snapshot in basket_snapshots) / count,
        "average_sector_concentration": sum(float(snapshot.get("sector_concentration", 0.0) or 0.0) for snapshot in basket_snapshots) / count,
        "max_sector_concentration": max(float(snapshot.get("sector_concentration", 0.0) or 0.0) for snapshot in basket_snapshots),
        "average_industry_concentration": sum(float(snapshot.get("industry_concentration", 0.0) or 0.0) for snapshot in basket_snapshots) / count,
        "average_active_sector_deviation": sum(float(snapshot.get("active_sector_deviation", 0.0) or 0.0) for snapshot in basket_snapshots) / count,
        "average_active_benchmark_bucket_deviation": sum(
            float(snapshot.get("active_benchmark_bucket_deviation", 0.0) or 0.0)
            for snapshot in basket_snapshots
        ) / count,
    }


def _evaluate_run(
    performance: list[PortfolioSnapshot],
    fills: list[Fill],
    benchmark_performance: list[PortfolioSnapshot],
    evaluation_config: EvaluationConfig | None,
) -> dict[str, object]:
    config = evaluation_config or EvaluationConfig(
        profile_name="default",
        warn_turnover=2.0,
        fail_turnover=3.0,
        warn_min_trade_count=3,
        fail_min_trade_count=1,
        warn_max_drawdown=0.10,
        fail_max_drawdown=0.20,
        warn_min_excess_return=0.0,
        fail_min_excess_return=-0.05,
        flag_underperform_benchmark=True,
        fail_on_zero_trade_run=True,
    )
    warn_flags: list[str] = []
    fail_flags: list[str] = []
    trade_count = len(fills)
    if trade_count == 0:
        fail_flags.append("zero_trade_run")
    elif trade_count <= config.fail_min_trade_count:
        fail_flags.append("insufficient_trade_count")
    elif trade_count <= config.warn_min_trade_count:
        warn_flags.append("low_trade_count")

    turnover = 0.0
    max_drawdown = 0.0
    if performance:
        average_nav = sum(snapshot.net_asset_value for snapshot in performance) / len(performance)
        total_traded_notional = sum(fill.gross_notional for fill in fills)
        turnover = 0.0 if average_nav == 0 else total_traded_notional / average_nav
        peak = performance[0].net_asset_value
        for snapshot in performance:
            peak = max(peak, snapshot.net_asset_value)
            drawdown = 0.0 if peak == 0 else (peak - snapshot.net_asset_value) / peak
            max_drawdown = max(max_drawdown, drawdown)
    if turnover > config.fail_turnover:
        fail_flags.append("excessive_turnover")
    elif turnover > config.warn_turnover:
        warn_flags.append("high_turnover")

    if max_drawdown > config.fail_max_drawdown:
        fail_flags.append("excessive_drawdown")
    elif max_drawdown > config.warn_max_drawdown:
        warn_flags.append("high_drawdown")

    strategy_return = 0.0
    if performance and performance[0].net_asset_value != 0:
        strategy_return = (performance[-1].net_asset_value - performance[0].net_asset_value) / performance[0].net_asset_value
    benchmark_return = 0.0
    if benchmark_performance and benchmark_performance[0].net_asset_value != 0:
        benchmark_return = (
            benchmark_performance[-1].net_asset_value - benchmark_performance[0].net_asset_value
        ) / benchmark_performance[0].net_asset_value
    excess_return = strategy_return - benchmark_return
    if excess_return < config.fail_min_excess_return:
        fail_flags.append("material_benchmark_underperformance")
    elif excess_return < config.warn_min_excess_return:
        warn_flags.append("benchmark_underperformance")
    if config.flag_underperform_benchmark and strategy_return < benchmark_return:
        warn_flags.append("underperformed_benchmark")

    status = "pass"
    if warn_flags:
        status = "warn"
    if fail_flags:
        status = "fail"
    if not config.fail_on_zero_trade_run and "zero_trade_run" in fail_flags:
        fail_flags.remove("zero_trade_run")
        warn_flags.append("zero_trade_run")
        status = "fail" if fail_flags else "warn"
    flags = fail_flags + [flag for flag in warn_flags if flag not in fail_flags]

    return {
        "status": status,
        "flags": flags,
        "warn_flags": warn_flags,
        "fail_flags": fail_flags,
        "trade_count": float(trade_count),
        "turnover": turnover,
        "max_drawdown": max_drawdown,
        "strategy_return": strategy_return,
        "benchmark_return": benchmark_return,
        "excess_return": excess_return,
        "policy": {
            "warn_turnover": config.warn_turnover,
            "fail_turnover": config.fail_turnover,
            "warn_min_trade_count": config.warn_min_trade_count,
            "fail_min_trade_count": config.fail_min_trade_count,
            "warn_max_drawdown": config.warn_max_drawdown,
            "fail_max_drawdown": config.fail_max_drawdown,
            "warn_min_excess_return": config.warn_min_excess_return,
            "fail_min_excess_return": config.fail_min_excess_return,
            "flag_underperform_benchmark": config.flag_underperform_benchmark,
            "fail_on_zero_trade_run": config.fail_on_zero_trade_run,
            "profile_name": config.profile_name,
        },
    }


def write_run_artifacts(
    output_dir: Path,
    run_name: str,
    summary: dict[str, float],
    analytics: dict[str, object],
    fills: list[Fill],
    performance: list[PortfolioSnapshot],
) -> Path:
    run_dir = output_dir / run_name
    run_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "summary": summary,
        "analytics": analytics,
        "fills": [asdict(fill) for fill in fills],
        "performance": [asdict(snapshot) for snapshot in performance],
    }
    output_path = run_dir / "results.json"
    output_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    write_report_artifacts(
        run_dir=run_dir,
        run_name=run_name,
        summary=summary,
        analytics=analytics,
        fills=payload["fills"],
        performance=payload["performance"],
    )
    run_metadata = analytics.get("run_metadata", {})
    research = analytics.get("research", {})
    evaluation = analytics.get("evaluation", {})
    period = analytics.get("period", {})
    register_catalog_entry(
        output_dir=output_dir,
        entry={
            "artifact_type": "run",
            "artifact_name": run_name,
            "profile_name": str(research.get("profile_name", "default")),
            "profile_version": str(research.get("profile_version", "unversioned")),
            "strategy_family": str(run_metadata.get("strategy_family", "unknown")),
            "sweep_type": str(run_metadata.get("sweep_type", "baseline")),
            "research_tranche": str(run_metadata.get("research_tranche", "") or ""),
            "research_slice_name": str(run_metadata.get("research_slice_name", "all")),
            "ranking_mode": str(run_metadata.get("ranking_mode", "global")),
            "score_transform": str(run_metadata.get("score_transform", "raw")),
            "control_profile": str(run_metadata.get("control_profile", "") or ""),
            "promotion_candidate": bool(run_metadata.get("promotion_candidate", False)),
            "evaluation_status": str(evaluation.get("status", "unknown")),
            "period_label": str(period.get("label", "full_sample")),
            "primary_path": str(output_path),
            "summary_path": str(run_dir / "summary.md"),
        },
    )
    return output_path
