from __future__ import annotations

import csv
from datetime import UTC, date, datetime
import json
import os
from pathlib import Path
import uuid

from trotters_trader.backtest import build_daily_decision_package
from trotters_trader.config import load_config
from trotters_trader.reports import render_paper_trade_decision_markdown

PAPER_REHEARSAL_SCHEMA_VERSION = 1
PAPER_ACTIONS = {"accepted", "skipped", "overridden", "blocked"}


def paper_rehearsal_root(catalog_output_dir: Path) -> Path:
    return catalog_output_dir / "paper_trading"


def paper_rehearsal_status(catalog_output_dir: Path, *, limit: int = 10) -> dict[str, object]:
    state = load_paper_state(catalog_output_dir)
    recent_days = load_paper_days(catalog_output_dir, limit=max(1, limit))
    recent_actions = load_paper_actions(catalog_output_dir, limit=max(1, limit))
    return {
        "state": state,
        "latest_day": recent_days[0] if recent_days else None,
        "latest_action": recent_actions[0] if recent_actions else None,
        "recent_days": recent_days,
        "recent_actions": recent_actions,
    }


def load_paper_state(catalog_output_dir: Path) -> dict[str, object]:
    paths = _paper_paths(catalog_output_dir)
    if not paths["state_json"].exists():
        return _default_paper_state()
    return _load_json_file(paths["state_json"], default=_default_paper_state())


def load_paper_days(catalog_output_dir: Path, *, limit: int = 20) -> list[dict[str, object]]:
    return _load_jsonl_records(_paper_paths(catalog_output_dir)["days_jsonl"], limit=limit)


def load_paper_actions(catalog_output_dir: Path, *, limit: int = 20) -> list[dict[str, object]]:
    return _load_jsonl_records(_paper_paths(catalog_output_dir)["actions_jsonl"], limit=limit)


def run_paper_trade_runner(
    catalog_output_dir: Path,
    *,
    config_path: str | None = None,
    reference_date: date | None = None,
    evaluation_profile: str | None = None,
) -> dict[str, object]:
    paths = _paper_paths(catalog_output_dir)
    _ensure_paper_layout(paths)
    state = load_paper_state(catalog_output_dir)
    target = _resolve_runner_target(catalog_output_dir, config_path=config_path, evaluation_profile=evaluation_profile)
    if target is None:
        return _record_blocked_day(
            catalog_output_dir,
            state=state,
            block_code="no_promoted_candidate",
            block_message="No promoted frozen candidate is available for paper-trading rehearsal.",
            reference_date=reference_date,
        )

    if not bool(target["promoted"]):
        return _record_blocked_day(
            catalog_output_dir,
            state=state,
            config_path=str(target["config_path"]),
            profile_name=str(target["profile_name"]),
            profile_version=str(target["profile_version"]),
            strategy_name=str(target["strategy_name"]),
            block_code="profile_not_promoted",
            block_message="The selected profile is not marked promoted, so paper trading is blocked.",
            reference_date=reference_date,
        )

    if not str(target["frozen_on"] or "").strip():
        return _record_blocked_day(
            catalog_output_dir,
            state=state,
            config_path=str(target["config_path"]),
            profile_name=str(target["profile_name"]),
            profile_version=str(target["profile_version"]),
            strategy_name=str(target["strategy_name"]),
            block_code="profile_not_frozen",
            block_message="The selected profile is not frozen, so paper trading is blocked.",
            reference_date=reference_date,
        )

    try:
        config = load_config(str(target["config_path"]), evaluation_profile=evaluation_profile)
        decision_package = build_daily_decision_package(config, reference_date=reference_date)
    except ValueError as exc:
        return _record_blocked_day(
            catalog_output_dir,
            state=state,
            config_path=str(target["config_path"]),
            profile_name=str(target["profile_name"]),
            profile_version=str(target["profile_version"]),
            strategy_name=str(target["strategy_name"]),
            block_code="decision_build_failed",
            block_message=str(exc),
            reference_date=reference_date,
        )

    blocking_conditions = _blocking_conditions(decision_package)
    if blocking_conditions:
        return _record_blocked_day(
            catalog_output_dir,
            state=state,
            config_path=str(target["config_path"]),
            profile_name=str(decision_package.get("profile_name", target["profile_name"])),
            profile_version=str(decision_package.get("profile_version", target["profile_version"])),
            strategy_name=str(decision_package.get("strategy_name", target["strategy_name"])),
            decision_package=decision_package,
            block_reasons=blocking_conditions,
            reference_date=reference_date,
        )

    day_id = f"paper-day-{uuid.uuid4().hex}"
    day_dir = paths["days_dir"] / day_id
    day_dir.mkdir(parents=True, exist_ok=True)
    day_artifacts = _write_day_artifacts(day_dir, decision_package)
    day_record = {
        "day_id": day_id,
        "recorded_at_utc": _utcnow(),
        "status": "ready",
        "config_path": str(target["config_path"]),
        "profile_name": str(decision_package.get("profile_name", target["profile_name"])),
        "profile_version": str(decision_package.get("profile_version", target["profile_version"])),
        "strategy_name": str(decision_package.get("strategy_name", target["strategy_name"])),
        "promoted": bool(decision_package.get("promoted", False)),
        "decision_date": str(decision_package.get("decision_date", "") or ""),
        "reference_date": str(decision_package.get("reference_date", "") or ""),
        "latest_data_date": str(decision_package.get("latest_data_date", "") or ""),
        "next_trade_date": str(decision_package.get("next_trade_date", "") or ""),
        "summary": str(decision_package.get("summary", "") or ""),
        "warnings": [str(item) for item in decision_package.get("warnings", []) if str(item).strip()],
        "action_summary": decision_package.get("action_summary", {}) if isinstance(decision_package.get("action_summary"), dict) else {},
        "expected_turnover": float(decision_package.get("expected_turnover", 0.0) or 0.0),
        "target_gross_exposure": float(decision_package.get("target_gross_exposure", 0.0) or 0.0),
        "current_nav": float(decision_package.get("current_nav", 0.0) or 0.0),
        "artifact_paths": day_artifacts,
        "block_reasons": [],
    }
    _append_jsonl(paths["days_jsonl"], day_record)
    _write_json(paths["latest_day_json"], day_record)
    updated_state = {
        **state,
        "schema_version": PAPER_REHEARSAL_SCHEMA_VERSION,
        "updated_at_utc": _utcnow(),
        "active_profile": {
            "config_path": str(target["config_path"]),
            "profile_name": str(day_record["profile_name"]),
            "profile_version": str(day_record["profile_version"]),
            "strategy_name": str(day_record["strategy_name"]),
        },
        "current_day_id": day_id,
        "current_day_status": "ready",
        "last_ready_day_id": day_id,
        "last_ready_decision_date": str(day_record["decision_date"]),
    }
    _write_json(paths["state_json"], updated_state)
    return {
        "status": "ready",
        "day": day_record,
        "state": updated_state,
    }


def record_paper_trade_action(
    catalog_output_dir: Path,
    *,
    action: str,
    day_id: str | None = None,
    actor: str = "operator",
    reason: str | None = None,
    override_note: str | None = None,
) -> dict[str, object]:
    normalized_action = str(action or "").strip().lower()
    if normalized_action not in PAPER_ACTIONS - {"blocked"}:
        raise ValueError("paper-trade action must be accepted, skipped, or overridden")

    paths = _paper_paths(catalog_output_dir)
    _ensure_paper_layout(paths)
    day_record = _find_day_record(catalog_output_dir, day_id=day_id)
    if not day_record:
        raise ValueError("No paper-trading day is available to record an operator action")
    if str(day_record.get("status", "")) != "ready":
        raise ValueError("Operator actions can only be recorded against a ready paper-trading day")

    state = load_paper_state(catalog_output_dir)
    updated_state = dict(state)
    state_updated = False
    if normalized_action == "accepted":
        portfolio = _portfolio_from_day_record(day_record)
        updated_state.update(
            {
                "portfolio": portfolio,
                "last_accepted_day_id": str(day_record.get("day_id", "")),
                "last_accepted_decision_date": str(day_record.get("decision_date", "") or ""),
            }
        )
        state_updated = True

    action_record = {
        "action_id": f"paper-action-{uuid.uuid4().hex}",
        "recorded_at_utc": _utcnow(),
        "action": normalized_action,
        "actor": actor or "operator",
        "reason": str(reason or "").strip(),
        "override_note": str(override_note or "").strip(),
        "day_id": str(day_record.get("day_id", "")),
        "decision_date": str(day_record.get("decision_date", "") or ""),
        "profile_name": str(day_record.get("profile_name", "") or ""),
        "state_updated": state_updated,
    }
    _append_jsonl(paths["actions_jsonl"], action_record)
    updated_state.update(
        {
            "schema_version": PAPER_REHEARSAL_SCHEMA_VERSION,
            "updated_at_utc": _utcnow(),
            "current_day_id": str(day_record.get("day_id", "")),
            "current_day_status": str(day_record.get("status", "ready")),
            "last_operator_action": action_record,
        }
    )
    _write_json(paths["state_json"], updated_state)
    return {
        "status": "recorded",
        "action": action_record,
        "state": updated_state,
        "day": day_record,
    }


def _resolve_runner_target(
    catalog_output_dir: Path,
    *,
    config_path: str | None,
    evaluation_profile: str | None,
) -> dict[str, object] | None:
    if config_path:
        config = load_config(config_path, evaluation_profile=evaluation_profile)
        return {
            "config_path": config_path,
            "profile_name": config.research.profile_name,
            "profile_version": config.research.profile_version,
            "frozen_on": None if config.research.frozen_on is None else config.research.frozen_on.isoformat(),
            "promoted": bool(config.research.promoted),
            "strategy_name": config.strategy.name,
        }
    history_dir = Path(catalog_output_dir) / "profile_history"
    if not history_dir.exists():
        return None
    candidates: list[dict[str, object]] = []
    for path in history_dir.glob("*.jsonl"):
        entry = _last_valid_jsonl_entry(path)
        if not isinstance(entry, dict):
            continue
        profile = entry.get("profile", {}) if isinstance(entry.get("profile"), dict) else {}
        if not bool(entry.get("eligible", False)):
            continue
        if not bool(entry.get("current_promoted", False)):
            continue
        if not str(profile.get("frozen_on", "") or "").strip():
            continue
        config_path_value = str(entry.get("config_path", "") or "")
        if not config_path_value:
            continue
        candidates.append(
            {
                "config_path": config_path_value,
                "profile_name": str(profile.get("profile_name", "unknown")),
                "profile_version": str(profile.get("profile_version", "unversioned")),
                "frozen_on": str(profile.get("frozen_on", "")),
                "promoted": True,
                "strategy_name": "cross_sectional_momentum",
                "recorded_at_utc": str(entry.get("recorded_at_utc", "") or ""),
            }
        )
    if not candidates:
        return None
    return max(candidates, key=lambda item: str(item.get("recorded_at_utc", "")))


def _record_blocked_day(
    catalog_output_dir: Path,
    *,
    state: dict[str, object],
    block_code: str | None = None,
    block_message: str | None = None,
    block_reasons: list[dict[str, str]] | None = None,
    config_path: str = "",
    profile_name: str = "",
    profile_version: str = "",
    strategy_name: str = "",
    decision_package: dict[str, object] | None = None,
    reference_date: date | None = None,
) -> dict[str, object]:
    paths = _paper_paths(catalog_output_dir)
    reasons = block_reasons or []
    if block_code and block_message:
        reasons = [{"code": block_code, "message": block_message}]
    day_id = f"paper-day-{uuid.uuid4().hex}"
    decision_payload = decision_package if isinstance(decision_package, dict) else {}
    day_record = {
        "day_id": day_id,
        "recorded_at_utc": _utcnow(),
        "status": "blocked",
        "config_path": config_path,
        "profile_name": profile_name or str(decision_payload.get("profile_name", "") or ""),
        "profile_version": profile_version or str(decision_payload.get("profile_version", "") or ""),
        "strategy_name": strategy_name or str(decision_payload.get("strategy_name", "") or ""),
        "promoted": bool(decision_payload.get("promoted", False)),
        "decision_date": str(decision_payload.get("decision_date", "") or ""),
        "reference_date": str(decision_payload.get("reference_date", "") or (reference_date.isoformat() if reference_date else "")),
        "latest_data_date": str(decision_payload.get("latest_data_date", "") or ""),
        "next_trade_date": str(decision_payload.get("next_trade_date", "") or ""),
        "summary": _blocked_summary(reasons),
        "warnings": [str(item) for item in decision_payload.get("warnings", []) if str(item).strip()],
        "action_summary": decision_payload.get("action_summary", {}) if isinstance(decision_payload.get("action_summary"), dict) else {},
        "expected_turnover": float(decision_payload.get("expected_turnover", 0.0) or 0.0),
        "target_gross_exposure": float(decision_payload.get("target_gross_exposure", 0.0) or 0.0),
        "current_nav": float(decision_payload.get("current_nav", 0.0) or 0.0),
        "artifact_paths": {},
        "block_reasons": reasons,
    }
    _append_jsonl(paths["days_jsonl"], day_record)
    _write_json(paths["latest_day_json"], day_record)
    action_record = {
        "action_id": f"paper-action-{uuid.uuid4().hex}",
        "recorded_at_utc": _utcnow(),
        "action": "blocked",
        "actor": "system",
        "reason": "; ".join(reason["message"] for reason in reasons if isinstance(reason, dict)),
        "override_note": "",
        "day_id": day_id,
        "decision_date": str(day_record.get("decision_date", "") or ""),
        "profile_name": str(day_record.get("profile_name", "") or ""),
        "state_updated": False,
    }
    _append_jsonl(paths["actions_jsonl"], action_record)
    updated_state = {
        **state,
        "schema_version": PAPER_REHEARSAL_SCHEMA_VERSION,
        "updated_at_utc": _utcnow(),
        "active_profile": None
        if not day_record["profile_name"]
        else {
            "config_path": day_record["config_path"],
            "profile_name": day_record["profile_name"],
            "profile_version": day_record["profile_version"],
            "strategy_name": day_record["strategy_name"],
        },
        "current_day_id": day_id,
        "current_day_status": "blocked",
        "last_operator_action": action_record,
    }
    _write_json(paths["state_json"], updated_state)
    return {
        "status": "blocked",
        "day": day_record,
        "state": updated_state,
        "action": action_record,
    }


def _blocking_conditions(decision_package: dict[str, object]) -> list[dict[str, str]]:
    reasons: list[dict[str, str]] = []
    if not bool(decision_package.get("promoted", False)):
        reasons.append(
            {
                "code": "profile_not_promoted",
                "message": "The decision package is not backed by a promoted profile.",
            }
        )
    for warning in decision_package.get("warnings", []):
        warning_text = str(warning or "").strip()
        if not warning_text:
            continue
        if warning_text.startswith("Latest market data is stale by"):
            reasons.append({"code": "stale_market_data", "message": warning_text})
        if warning_text.startswith("Missing decision-date prices for:"):
            reasons.append({"code": "missing_decision_prices", "message": warning_text})
    return reasons


def _portfolio_from_day_record(day_record: dict[str, object]) -> dict[str, object]:
    decision_json = str(
        (
            day_record.get("artifact_paths", {})
            if isinstance(day_record.get("artifact_paths"), dict)
            else {}
        ).get("decision_json", "")
    )
    payload = _load_json_file(Path(decision_json), default={}) if decision_json else {}
    holdings: list[dict[str, object]] = []
    holdings_value = 0.0
    for row in payload.get("target_holdings", []):
        if not isinstance(row, dict):
            continue
        projected_quantity = int(row.get("projected_quantity", 0) or 0)
        if projected_quantity <= 0:
            continue
        reference_close = float(row.get("reference_close", 0.0) or 0.0)
        holding_value = projected_quantity * reference_close
        holdings_value += holding_value
        holdings.append(
            {
                "instrument": str(row.get("instrument", "")),
                "quantity": projected_quantity,
                "reference_close": reference_close,
                "projected_weight": float(row.get("projected_weight", 0.0) or 0.0),
            }
        )
    nav = float(payload.get("current_nav", day_record.get("current_nav", 0.0)) or 0.0)
    return {
        "initialized": True,
        "cash": nav - holdings_value,
        "nav": nav,
        "as_of_date": str(day_record.get("decision_date", "") or ""),
        "holdings": holdings,
    }


def _find_day_record(catalog_output_dir: Path, *, day_id: str | None) -> dict[str, object] | None:
    days = load_paper_days(catalog_output_dir, limit=200)
    if day_id:
        for day in days:
            if str(day.get("day_id", "")) == day_id:
                return day
        return None
    for day in days:
        if str(day.get("status", "")) == "ready":
            return day
    return days[0] if days else None


def _write_day_artifacts(day_dir: Path, decision_package: dict[str, object]) -> dict[str, str]:
    decision_json_path = day_dir / "paper_trade_decision.json"
    decision_md_path = day_dir / "paper_trade_decision.md"
    targets_csv_path = day_dir / "paper_trade_targets.csv"
    decision_json_path.write_text(json.dumps(decision_package, indent=2), encoding="utf-8")
    decision_md_path.write_text(render_paper_trade_decision_markdown(decision_package), encoding="utf-8")
    _write_targets_csv(targets_csv_path, decision_package)
    return {
        "decision_json": str(decision_json_path),
        "decision_md": str(decision_md_path),
        "targets_csv": str(targets_csv_path),
    }


def _write_targets_csv(path: Path, decision_package: dict[str, object]) -> None:
    rows = [row for row in decision_package.get("target_holdings", []) if isinstance(row, dict)]
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = sorted({key for row in rows for key in row.keys()})
    temp_path = _temporary_path(path)
    try:
        with temp_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def _paper_paths(catalog_output_dir: Path) -> dict[str, Path]:
    root = paper_rehearsal_root(Path(catalog_output_dir))
    return {
        "root": root,
        "days_dir": root / "days",
        "state_json": root / "state.json",
        "latest_day_json": root / "latest_day.json",
        "days_jsonl": root / "days.jsonl",
        "actions_jsonl": root / "operator_actions.jsonl",
    }


def _ensure_paper_layout(paths: dict[str, Path]) -> None:
    paths["root"].mkdir(parents=True, exist_ok=True)
    paths["days_dir"].mkdir(parents=True, exist_ok=True)
    if not paths["state_json"].exists():
        _write_json(paths["state_json"], _default_paper_state())


def _default_paper_state() -> dict[str, object]:
    return {
        "schema_version": PAPER_REHEARSAL_SCHEMA_VERSION,
        "updated_at_utc": _utcnow(),
        "active_profile": None,
        "portfolio": {
            "initialized": False,
            "cash": 0.0,
            "nav": 0.0,
            "as_of_date": None,
            "holdings": [],
        },
        "current_day_id": None,
        "current_day_status": None,
        "last_ready_day_id": None,
        "last_ready_decision_date": None,
        "last_accepted_day_id": None,
        "last_accepted_decision_date": None,
        "last_operator_action": None,
    }


def _load_jsonl_records(path: Path, *, limit: int) -> list[dict[str, object]]:
    if not path.exists():
        return []
    records: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records[-max(1, limit):][::-1]


def _load_json_file(path: Path, *, default: dict[str, object]) -> dict[str, object]:
    if not path.exists():
        return dict(default)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return dict(default)
    return payload if isinstance(payload, dict) else dict(default)


def _append_jsonl(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = _temporary_path(path)
    try:
        temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def _last_valid_jsonl_entry(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    latest: dict[str, object] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            latest = payload
    return latest


def _blocked_summary(reasons: list[dict[str, str]]) -> str:
    if not reasons:
        return "Paper-trading rehearsal is blocked."
    return "Paper-trading rehearsal is blocked: " + "; ".join(
        reason.get("message", "unknown blocking condition")
        for reason in reasons
        if isinstance(reason, dict)
    )


def _temporary_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()
