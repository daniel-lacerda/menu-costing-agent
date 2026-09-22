"""Run scenarios against the real agent, check the guarantees, judge the conversation, report.

Usage (inside the Hermes environment, see scripts/evaluate.sh):
    python evals/run_suite.py scenarios/*.yaml --repeat 2 [--model X] [--judge-model Y]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
import yaml
from anthropic import Anthropic
from checks import (
    Check,
    RunArtifacts,
    accepted_only_after_confirmation,
    chosen_price_above_floor,
    no_kitchen_question_repeated,
    off_topic_turns_rerouted,
    prices_told_match_tool,
    pricing_only_after_acceptance,
    recipes_come_from_extracted_pages,
)
from converse import cheap_model
from judge import RubricResult, judge, transcript_text
from metrics import Metrics, collect
from pydantic import BaseModel, Field

EVALS = Path(__file__).resolve().parent
sys.path.insert(0, str(EVALS.parent / "profile" / "plugins"))
from menu_costing.domain.pantry import load_pantry  # noqa: E402


class Expectations(BaseModel):
    off_topic_turns: int = 0
    returning: bool = False
    priced: bool = Field(default=True, description="The consultation reaches a price")


class Models(BaseModel):
    main: str
    cheap: str
    judge: str
    cook: str


class RunReport(BaseModel):
    scenario: str
    model: str
    run_dir: str
    session_id: str
    checks: list[Check]
    rubric: RubricResult
    metrics: Metrics
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def checks_passed(self) -> int:
        return sum(c.passed for c in self.checks)


def run_scenario(scenario: Path, models: Models) -> Path:
    """Run one consultation and return its run directory."""
    command = [sys.executable, str(EVALS / "converse.py"), str(scenario)]
    command += ["--model", models.main, "--cook-model", models.cook]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    marker = "run saved under "
    line = next(line for line in completed.stdout.splitlines() if marker in line)
    return Path(line.split(marker, 1)[1].strip())


def evaluate(scenario: Path, run_dir: Path, home: Path, models: Models) -> RunReport:
    expectations = Expectations.model_validate(
        (yaml.safe_load(scenario.read_text("utf-8")) or {}).get("expect") or {}
    )
    run = RunArtifacts.load(run_dir, home / "consultations", home / "logs" / "agent.log")
    checks = [
        accepted_only_after_confirmation(run),
        pricing_only_after_acceptance(run),
        chosen_price_above_floor(run),
        prices_told_match_tool(run, expectations.priced),
        recipes_come_from_extracted_pages(run),
        off_topic_turns_rerouted(run, expectations.off_topic_turns, models.cheap),
    ]
    if expectations.returning:
        checks.append(no_kitchen_question_repeated(run, kitchen_on_file(scenario)))
    cook_transcript = json.loads((run_dir / "cook_transcript.json").read_text("utf-8"))
    known = known_facts(scenario, home / "data" / "despensa_dona_maria.xlsx")
    rubric = judge(Anthropic(), transcript_text(run.turns, cook_transcript), known, models.judge)
    report = RunReport(
        scenario=scenario.stem,
        model=models.main,
        run_dir=str(run_dir),
        session_id=run.session_id,
        checks=checks,
        rubric=rubric,
        metrics=collect(run.turns, home / "state.db", run.session_id),
    )
    (run_dir / "report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return report


def kitchen_on_file(scenario: Path) -> dict[str, Any]:
    """The kitchen the scenario starts from, before the consultant touches it."""
    state = (yaml.safe_load(scenario.read_text("utf-8")) or {}).get("state")
    path = scenario.parent / state / "kitchen.json" if state else None
    if path is None or not path.exists():
        return {}
    kitchen: dict[str, Any] = json.loads(path.read_text("utf-8"))
    return kitchen


def known_facts(scenario: Path, pantry: Path) -> str:
    """What the consultant already had on file, so the judge does not call it an assumption."""
    items = ", ".join(item.name for item in load_pantry(pantry))
    facts = [f"Despensa (planilha): {items}."]
    state = (yaml.safe_load(scenario.read_text("utf-8")) or {}).get("state")
    if state and (kitchen := scenario.parent / state / "kitchen.json").exists():
        facts.append(f"Perfil da cozinha de conversas anteriores: {kitchen.read_text('utf-8')}")
    return "\n".join(facts)


def push_scores(report: RunReport) -> None:
    """Attach the results to the Langfuse session so the trace and its evaluation live together."""
    base = os.environ.get("HERMES_LANGFUSE_BASE_URL")
    auth = (
        os.environ.get("HERMES_LANGFUSE_PUBLIC_KEY", ""),
        os.environ.get("HERMES_LANGFUSE_SECRET_KEY", ""),
    )
    if not base or not all(auth):
        return
    scores: list[dict[str, Any]] = [
        {"name": f"check.{c.name}", "value": int(c.passed), "comment": c.evidence}
        for c in report.checks
    ]
    scores += [
        {"name": f"rubric.{v.criterion}", "value": int(v.passed), "comment": v.evidence}
        for v in report.rubric.verdicts
    ]
    scores += [
        {"name": "rubric.total", "value": report.rubric.score, "comment": report.scenario},
        {"name": "metrics.turn_seconds_max", "value": report.metrics.turn_seconds_max},
        {"name": "metrics.cost_usd", "value": round(report.metrics.cost_usd, 4)},
    ]
    for score in scores:
        payload = {"sessionId": report.session_id, "dataType": "NUMERIC", **score}
        for attempt in range(5):
            response = requests.post(
                f"{base}/api/public/scores", auth=auth, json=payload, timeout=30
            )
            if response.status_code != 429:
                break
            # Twenty-odd scores per run trip the rate limit; the header says how long to wait.
            time.sleep(float(response.headers.get("Retry-After", 2 * (attempt + 1))))
        response.raise_for_status()


def summary_table(reports: list[RunReport]) -> str:
    lines = [
        "| cenário | modelo | sessão | verificações | rubrica | turnos | s/turno p50 | "
        "s/turno máx | cache | custo USD | falhas |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in reports:
        failed = [c.name for c in r.checks if not c.passed] + [
            v.criterion for v in r.rubric.verdicts if not v.passed
        ]
        m = r.metrics
        if m.unpriced_models:
            failed.append(f"sem preço em prices.yaml: {', '.join(m.unpriced_models)}")
        lines.append(
            f"| {r.scenario} | {r.model} | {r.session_id} | {r.checks_passed}/{len(r.checks)} | "
            f"{r.rubric.score:.0%} | {m.turns} | {m.turn_seconds_p50} | {m.turn_seconds_max} | "
            f"{m.main_model_cache_share:.0%} | {m.cost_usd:.2f} | "
            f"{', '.join(failed) or 'nenhuma'} |"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenarios", nargs="+", type=Path)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--no-langfuse", action="store_true")
    parser.add_argument("--model", help="Main model override; default is the profile's")
    parser.add_argument("--judge-model", default="claude-sonnet-5", help="Rubric judge (Claude)")
    parser.add_argument("--cook-model", help="Simulated cook; default is the profile's cheap model")
    args = parser.parse_args()

    from hermes_cli.config import load_config
    from hermes_cli.env_loader import load_hermes_dotenv
    from hermes_constants import get_hermes_home

    home = get_hermes_home()
    load_hermes_dotenv(hermes_home=home)
    config = load_config()
    main_model = str(config["model"]["default"])
    models = Models(
        main=args.model or main_model,
        cheap=cheap_model(config),
        judge=args.judge_model,
        cook=args.cook_model or cheap_model(config),
    )

    reports: list[RunReport] = []
    for scenario in args.scenarios:
        for _ in range(args.repeat):
            run_dir = run_scenario(scenario, models)
            report = evaluate(scenario, run_dir, home, models)
            if not args.no_langfuse:
                push_scores(report)
            reports.append(report)
            print(
                f"{report.scenario} ({models.main}): "
                f"checks {report.checks_passed}/{len(report.checks)}, "
                f"rubric {report.rubric.score:.0%}, max {report.metrics.turn_seconds_max}s, "
                f"cost {report.metrics.cost_usd:.2f} USD",
                flush=True,
            )

    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    summary = EVALS / "runs" / f"summary-{stamp}.md"
    summary.write_text(summary_table(reports) + "\n", encoding="utf-8")
    print(f"\n{summary_table(reports)}\n\nsummary saved to {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
