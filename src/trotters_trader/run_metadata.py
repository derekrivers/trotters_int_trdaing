from __future__ import annotations


def classify_run_name(run_name: str) -> tuple[str, str, str, str]:
    if "_tranche_" in run_name:
        tranche_value = run_name.split("_tranche_", 1)[1]
        return ("cross_sectional_momentum", "research_tranche", "tranche", tranche_value)
    if "_slice_" in run_name:
        slice_value = run_name.split("_slice_", 1)[1]
        if "_split-" in slice_value:
            slice_value = slice_value.split("_split-", 1)[0]
        return ("cross_sectional_momentum", "universe_slice", "slice", slice_value)
    if "_ranking_" in run_name:
        ranking_value = run_name.split("_ranking_", 1)[1]
        if "_split-" in ranking_value:
            ranking_value = ranking_value.split("_split-", 1)[0]
        return ("cross_sectional_momentum", "ranking_sweep", "scenario", ranking_value)
    if "_construct_" in run_name:
        construction_value = run_name.split("_construct_", 1)[1]
        if "_split-" in construction_value:
            construction_value = construction_value.split("_split-", 1)[0]
        return ("cross_sectional_momentum", "construction_sweep", "scenario", construction_value)
    if "_risk_" in run_name:
        risk_value = run_name.split("_risk_", 1)[1]
        if "_split-" in risk_value:
            risk_value = risk_value.split("_split-", 1)[0]
        return ("cross_sectional_momentum", "risk_sweep", "scenario", risk_value)
    if "_regime_" in run_name:
        regime_value = run_name.split("_regime_", 1)[1]
        if "_split-" in regime_value:
            regime_value = regime_value.split("_split-", 1)[0]
        return ("cross_sectional_momentum", "regime_sweep", "scenario", regime_value)
    if "_sector_" in run_name:
        sector_value = run_name.split("_sector_", 1)[1]
        if "_split-" in sector_value:
            sector_value = sector_value.split("_split-", 1)[0]
        return ("cross_sectional_momentum", "sector_sweep", "scenario", sector_value)
    if "_wf_" in run_name:
        walkforward_value = run_name.split("_wf_", 1)[1]
        return ("cross_sectional_momentum", "walk_forward", "window", walkforward_value)
    if "_split-" in run_name:
        return ("unknown", "validation_split", "period", run_name.split("_split-", 1)[1])
    if "_profile-" in run_name:
        profile_name = run_name.split("_profile-", 1)[1].split("_", 1)[0]
        if run_name.endswith("_sma_cross"):
            return ("sma_cross", "evaluation_profile", "profile", profile_name)
        if run_name.endswith("_cross_sectional_momentum"):
            return ("cross_sectional_momentum", "evaluation_profile", "profile", profile_name)
        if run_name.endswith("_mean_reversion"):
            return ("mean_reversion", "evaluation_profile", "profile", profile_name)
    if "_thr_sma_" in run_name:
        return ("sma_cross", "threshold", "signal_threshold", run_name.split("_thr_sma_", 1)[1])
    if "_thr_mom_" in run_name:
        return ("cross_sectional_momentum", "threshold", "min_score", run_name.split("_thr_mom_", 1)[1])
    if "_thr_mr_" in run_name:
        return ("mean_reversion", "threshold", "min_score", run_name.split("_thr_mr_", 1)[1])
    if "_sens_" in run_name:
        return ("mixed", "sensitivity", "scenario", run_name.split("_sens_", 1)[1])
    if "_mom_n-" in run_name:
        return ("cross_sectional_momentum", "momentum_sweep", "scenario", run_name.split("_mom_", 1)[1])
    if "_momref_n-" in run_name:
        return ("cross_sectional_momentum", "momentum_refine", "scenario", run_name.split("_momref_", 1)[1])
    if "_momprof_" in run_name:
        return ("cross_sectional_momentum", "momentum_profile", "profile", run_name.split("_momprof_", 1)[1])
    if run_name.endswith("_sma_cross"):
        return ("sma_cross", "strategy_compare", "strategy", "sma_cross")
    if run_name.endswith("_cross_sectional_momentum"):
        return ("cross_sectional_momentum", "strategy_compare", "strategy", "cross_sectional_momentum")
    if run_name.endswith("_mean_reversion"):
        return ("mean_reversion", "strategy_compare", "strategy", "mean_reversion")
    if "_s" in run_name and "_l" in run_name:
        suffix = run_name.split("_s", 1)[1]
        return ("sma_cross", "parameter_grid", "windows", suffix)
    return ("unknown", "baseline", "run_name", run_name)


def run_metadata(
    run_name: str,
    *,
    default_strategy_family: str = "unknown",
    research_tranche: str = "",
    research_slice_name: str = "all",
    ranking_mode: str = "global",
    score_transform: str = "raw",
    control_profile: str = "",
    promotion_candidate: bool = False,
) -> dict[str, str | bool]:
    strategy_family, sweep_type, parameter_name, parameter_value = classify_run_name(run_name)
    if strategy_family == "unknown" and sweep_type == "baseline":
        strategy_family = default_strategy_family
    return {
        "strategy_family": strategy_family,
        "sweep_type": sweep_type,
        "parameter_name": parameter_name,
        "parameter_value": parameter_value,
        "research_tranche": research_tranche,
        "research_slice_name": research_slice_name,
        "ranking_mode": ranking_mode,
        "score_transform": score_transform,
        "control_profile": control_profile,
        "promotion_candidate": promotion_candidate,
    }
