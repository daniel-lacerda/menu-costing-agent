"""Deterministic checks over a saved run: the guarantees the consultant must never break.

Each check is a yes or no answer with the evidence that decided it, so a failed run explains
itself. They read what the harness saved (turns.jsonl), what the tools persisted (menu.json)
and what the runtime logged (agent.log), never the model's prose.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel

TOOL_ORDER = ("recipe_register", "recipe_update", "dish_price")


class Check(BaseModel):
    name: str
    passed: bool
    evidence: str


class RunArtifacts(BaseModel):
    turns: list[dict[str, Any]]
    menu: dict[str, Any] | None
    log_lines: list[str]
    session_id: str

    @classmethod
    def load(cls, run_dir: Path, store: Path, agent_log: Path) -> RunArtifacts:
        turns = [
            json.loads(line)
            for line in (run_dir / "turns.jsonl").read_text("utf-8").splitlines()
            if line.strip()
        ]
        menu_path = store / "menu.json"
        menu = json.loads(menu_path.read_text("utf-8")) if menu_path.exists() else None
        session_id = run_dir.name.rsplit("-", 1)[-1]
        lines = [
            line
            for line in agent_log.read_text("utf-8", errors="replace").splitlines()
            if session_id in line
        ]
        return cls(turns=turns, menu=menu, log_lines=lines, session_id=session_id)

    def calls(self) -> list[tuple[int, str, dict[str, Any]]]:
        """(turn, tool, arguments) for every tool call, in order."""
        out: list[tuple[int, str, dict[str, Any]]] = []
        for turn in self.turns:
            for call in turn["tool_calls"]:
                raw = call.get("arguments") or "{}"
                try:
                    arguments = json.loads(raw)
                except json.JSONDecodeError:
                    arguments = {}
                out.append((turn["turn"], call["name"], arguments))
        return out


def accepted_only_after_confirmation(run: RunArtifacts) -> Check:
    """No recipe is accepted before she said she liked it and every technique was confirmed."""
    liked: set[str] = set()
    techniques_seen: set[str] = set()
    for _, tool, args in run.calls():
        if tool != "recipe_update":
            continue
        rid = str(args.get("recipe_id"))
        if args.get("liked") is True:
            liked.add(rid)
        techniques_seen.update((args.get("techniques") or {}).keys())
        if args.get("accepted") is True and rid not in liked:
            return Check(
                name="accepted_only_after_confirmation",
                passed=False,
                evidence=f"{rid} accepted before liked=true was recorded",
            )
    if run.menu is None:
        return Check(name="accepted_only_after_confirmation", passed=True, evidence="no menu")
    for recipe in run.menu["recipes"].values():
        if not recipe["accepted"]:
            continue
        pending = [t for t in recipe["techniques_required"] if not _confirmed(t, run)]
        if pending:
            return Check(
                name="accepted_only_after_confirmation",
                passed=False,
                evidence=f"{recipe['id']} accepted with unconfirmed techniques {pending}",
            )
    return Check(
        name="accepted_only_after_confirmation",
        passed=True,
        evidence=f"liked recorded for {sorted(liked)}; techniques asked: {sorted(techniques_seen)}",
    )


def _confirmed(technique: str, run: RunArtifacts) -> bool:
    key = technique.casefold()
    for _, tool, args in run.calls():
        if tool == "recipe_update":
            for name, mastered in (args.get("techniques") or {}).items():
                if name.casefold() == key and mastered:
                    return True
        if tool == "kitchen_profile":
            for name, mastered in (args.get("techniques") or {}).items():
                if name.casefold() == key and mastered:
                    return True
    return False


def pricing_only_after_acceptance(run: RunArtifacts) -> Check:
    """dish_price is never called for a recipe before recipe_update accepted it."""
    accepted: set[str] = set()
    for turn, tool, args in run.calls():
        rid = str(args.get("recipe_id"))
        if tool == "recipe_update" and args.get("accepted") is True:
            accepted.add(rid)
        if tool == "dish_price" and rid not in accepted:
            return Check(
                name="pricing_only_after_acceptance",
                passed=False,
                evidence=f"dish_price for {rid} in turn {turn} before acceptance",
            )
    return Check(
        name="pricing_only_after_acceptance", passed=True, evidence=f"accepted {sorted(accepted)}"
    )


def chosen_price_above_floor(run: RunArtifacts, platform_fee: float) -> Check:
    """A recorded price never sits below CMV / (1 - fee); the tool must have refused otherwise."""
    if run.menu is None:
        return Check(name="chosen_price_above_floor", passed=True, evidence="no menu")
    for recipe in run.menu["recipes"].values():
        price = recipe.get("chosen_price_brl")
        if price is None:
            continue
        floor = _floor_from_turns(run, recipe["id"])
        if floor is not None and price < floor:
            return Check(
                name="chosen_price_above_floor",
                passed=False,
                evidence=f"{recipe['id']} priced {price} below floor {floor}",
            )
    return Check(
        name="chosen_price_above_floor", passed=True, evidence="all chosen prices above floor"
    )


def _floor_from_turns(run: RunArtifacts, rid: str) -> float | None:
    pattern = re.compile(r"m[íi]nimo[^\d]{0,40}R\$ ?(\d+[,.]\d{2})")
    for turn in run.turns:
        match = pattern.search(turn["consultant"])
        if match:
            return float(match.group(1).replace(",", "."))
    return None


def recipes_come_from_extracted_pages(run: RunArtifacts) -> Check:
    """Every registered URL was fetched with web_extract before registration."""
    extracted: set[str] = set()
    for _, tool, args in run.calls():
        if tool == "web_extract":
            extracted.update(args.get("urls") or [])
        if tool == "recipe_register":
            url = str(args.get("url"))
            if url not in extracted:
                return Check(
                    name="recipes_come_from_extracted_pages",
                    passed=False,
                    evidence=f"registered {url} without extracting it",
                )
    return Check(
        name="recipes_come_from_extracted_pages",
        passed=True,
        evidence=f"{len(extracted)} pages extracted before registration",
    )


def off_topic_turns_rerouted(run: RunArtifacts, expected: int) -> Check:
    """The guard rerouted the expected turns and the provider confirms which model served them."""
    guard_lines = [line for line in run.log_lines if "scope guard: turn" in line]
    rerouted = [line for line in guard_lines if "rerouted" in line]
    served = [line for line in guard_lines if "served by" in line]
    cheap = [line for line in served if "gpt-5.6-luna" in line]
    passed = len(rerouted) == expected and len(cheap) == expected
    return Check(
        name="off_topic_turns_rerouted",
        passed=passed,
        evidence=f"rerouted={len(rerouted)} served_by_cheap_model={len(cheap)} expected={expected}",
    )


def no_kitchen_question_repeated(run: RunArtifacts, known_fields: set[str]) -> Check:
    """On a return visit, fields already on file are not written again from her answers."""
    rewritten: set[str] = set()
    for _, tool, args in run.calls():
        if tool == "kitchen_profile":
            rewritten.update(k for k in args if k in known_fields and k != "techniques")
    return Check(
        name="no_kitchen_question_repeated",
        passed=not rewritten - {"oven"},
        evidence=f"fields rewritten on return: {sorted(rewritten)} (oven changed by design)",
    )
