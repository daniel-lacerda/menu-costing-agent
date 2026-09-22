"""Run scenarios against the real agent, check the guarantees, judge the conversation, report.

Usage (inside the Hermes environment, see scripts/evaluate.sh):
    python evals/run_suite.py evals/scenarios/*.yaml --repeat 2
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
import yaml
from checks import (
    Check,
    RunArtifacts,
    accepted_only_after_confirmation,
    chosen_price_above_floor,
    no_kitchen_question_repeated,
    off_topic_turns_rerouted,
    pricing_only_after_acceptance,
    recipes_come_from_extracted_pages,
)
from judge import RubricResult, judge, transcript_text
from openai import OpenAI
from pydantic import BaseModel, Field

EVALS = Path(__file__).resolve().parent


class Expectations(BaseModel):
    off_topic_turns: int = 0
    returning: bool = False


class RunReport(BaseModel):
    scenario: str
    run_dir: str
    session_id: str
    checks: list[Check]
    rubric: RubricResult
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def checks_passed(self) -> int:
        return sum(c.passed for c in self.checks)


def run_scenario(scenario: Path) -> Path:
    """Run one consultation and return its run directory."""
    completed = subprocess.run(
        [sys.executable, str(EVALS / "converse.py"), str(scenario)],
        check=True,
        capture_output=True,
        text=True,
    )
    marker = "run saved under "
    line = next(line for line in completed.stdout.splitlines() if marker in line)
    return Path(line.split(marker, 1)[1].strip())


def evaluate(scenario: Path, run_dir: Path, home: Path, platform_fee: float) -> RunReport:
    expectations = Expectations.model_validate(
        (yaml.safe_load(scenario.read_text("utf-8")) or {}).get("expect") or {}
    )
    run = RunArtifacts.load(run_dir, home / "consultations", home / "logs" / "agent.log")
    checks = [
        accepted_only_after_confirmation(run),
        pricing_only_after_acceptance(run),
        chosen_price_above_floor(run, platform_fee),
        recipes_come_from_extracted_pages(run),
        off_topic_turns_rerouted(run, expectations.off_topic_turns),
    ]
    if expectations.returning:
        known = {
            "burners",
            "oven",
            "pressure_cooker",
            "air_fryer",
            "blender",
            "fuel",
            "fridge_space",
            "time_per_batch",
        }
        checks.append(no_kitchen_question_repeated(run, known))
    cook_transcript = json.loads((run_dir / "cook_transcript.json").read_text("utf-8"))
    known = known_facts(scenario, home / "data" / "despensa_dona_maria.xlsx")
    rubric = judge(OpenAI(), transcript_text(run.turns, cook_transcript), known)
    report = RunReport(
        scenario=scenario.stem,
        run_dir=str(run_dir),
        session_id=run.session_id,
        checks=checks,
        rubric=rubric,
    )
    (run_dir / "report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return report


def known_facts(scenario: Path, pantry: Path) -> str:
    """What the consultant already had on file, so the judge does not call it an assumption."""
    sys.path.insert(0, str(EVALS.parent / "profile" / "plugins"))
    from menu_costing.domain.pantry import load_pantry

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
    scores = [
        {"name": f"check.{c.name}", "value": int(c.passed), "comment": c.evidence}
        for c in report.checks
    ]
    scores += [
        {"name": f"rubric.{v.criterion}", "value": int(v.passed), "comment": v.evidence}
        for v in report.rubric.verdicts
    ]
    scores.append(
        {"name": "rubric.total", "value": report.rubric.score, "comment": report.scenario}
    )
    for score in scores:
        response = requests.post(
            f"{base}/api/public/scores",
            auth=auth,
            json={"sessionId": report.session_id, "dataType": "NUMERIC", **score},
            timeout=30,
        )
        response.raise_for_status()


def summary_table(reports: list[RunReport]) -> str:
    lines = ["| cenário | sessão | verificações | rubrica | falhas |", "|---|---|---|---|---|"]
    for r in reports:
        failed = [c.name for c in r.checks if not c.passed] + [
            v.criterion for v in r.rubric.verdicts if not v.passed
        ]
        lines.append(
            f"| {r.scenario} | {r.session_id} | {r.checks_passed}/{len(r.checks)} | "
            f"{r.rubric.score:.0%} | {', '.join(failed) or 'nenhuma'} |"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenarios", nargs="+", type=Path)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--no-langfuse", action="store_true")
    args = parser.parse_args()

    from hermes_cli.config import load_config
    from hermes_cli.env_loader import load_hermes_dotenv
    from hermes_constants import get_hermes_home

    home = get_hermes_home()
    load_hermes_dotenv(hermes_home=home)
    settings: dict[str, Any] = (
        load_config()
        .get("plugins", {})
        .get("entries", {})
        .get("menu_costing", {})
        .get("settings", {})
    )
    platform_fee = float(settings.get("platform_fee", 0.10))

    reports: list[RunReport] = []
    for scenario in args.scenarios:
        for _ in range(args.repeat):
            run_dir = run_scenario(scenario)
            report = evaluate(scenario, run_dir, home, platform_fee)
            if not args.no_langfuse:
                push_scores(report)
            reports.append(report)
            print(
                f"{report.scenario}: checks {report.checks_passed}/{len(report.checks)}, "
                f"rubric {report.rubric.score:.0%}",
                flush=True,
            )

    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    summary = EVALS / "runs" / f"summary-{stamp}.md"
    summary.write_text(summary_table(reports) + "\n", encoding="utf-8")
    print(f"\n{summary_table(reports)}\n\nsummary saved to {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
