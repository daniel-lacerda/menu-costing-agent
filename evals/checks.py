"""Deterministic checks over a saved run: the guarantees the consultant must never break.

Each check is a yes or no answer with the evidence that decided it, so a failed run explains
itself. They read what the harness saved (turns.jsonl, including every tool result), what the
tools persisted (menu.json) and what the runtime logged (agent.log). The one check that reads
the consultant's prose does so to confirm the prose repeats the tool's numbers.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class Check(BaseModel):
    name: str
    passed: bool
    evidence: str


class ToolCall(BaseModel):
    turn: int
    name: str
    arguments: dict[str, Any]
    result: dict[str, Any] | None


class RunArtifacts(BaseModel):
    turns: list[dict[str, Any]]
    menu: dict[str, Any] | None
    kitchen: dict[str, Any] | None
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
        kitchen_path = store / "kitchen.json"
        kitchen = json.loads(kitchen_path.read_text("utf-8")) if kitchen_path.exists() else None
        session_id = run_dir.name.rsplit("-", 1)[-1]
        lines = [
            line
            for line in agent_log.read_text("utf-8", errors="replace").splitlines()
            if session_id in line
        ]
        return cls(turns=turns, menu=menu, kitchen=kitchen, log_lines=lines, session_id=session_id)

    def calls(self) -> list[ToolCall]:
        out: list[ToolCall] = []
        for turn in self.turns:
            for call in turn["tool_calls"]:
                out.append(
                    ToolCall(
                        turn=turn["turn"],
                        name=call["name"],
                        arguments=_json_or_empty(call.get("arguments")),
                        result=_json_or_none(call.get("result")),
                    )
                )
        return out

    def consultant_text(self, turn: int) -> str:
        return next(t["consultant"] for t in self.turns if t["turn"] == turn)


def _json_or_empty(raw: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_or_none(raw: str | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def accepted_only_after_confirmation(run: RunArtifacts) -> Check:
    """No recipe is accepted before she said she liked it and every technique was confirmed."""
    liked: set[str] = set()
    techniques_seen: set[str] = set()
    for call in run.calls():
        if call.name != "recipe_update":
            continue
        rid = str(call.arguments.get("recipe_id"))
        if call.arguments.get("liked") is True:
            liked.add(rid)
        techniques_seen.update((call.arguments.get("techniques") or {}).keys())
        if call.arguments.get("accepted") is True and rid not in liked:
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
    """Confirmed in this run, or already on file in the kitchen profile from an earlier one."""
    key = technique.casefold()
    on_file = {k.casefold(): v for k, v in ((run.kitchen or {}).get("techniques") or {}).items()}
    if on_file.get(key):
        return True
    for call in run.calls():
        if call.name in ("recipe_update", "kitchen_profile"):
            for name, mastered in (call.arguments.get("techniques") or {}).items():
                if name.casefold() == key and mastered:
                    return True
    return False


def pricing_only_after_acceptance(run: RunArtifacts) -> Check:
    """dish_price is never called for a recipe before recipe_update accepted it."""
    accepted: set[str] = set()
    for call in run.calls():
        rid = str(call.arguments.get("recipe_id"))
        if call.name == "recipe_update" and call.arguments.get("accepted") is True:
            accepted.add(rid)
        if call.name == "dish_price" and rid not in accepted:
            return Check(
                name="pricing_only_after_acceptance",
                passed=False,
                evidence=f"dish_price for {rid} in turn {call.turn} before acceptance",
            )
    return Check(
        name="pricing_only_after_acceptance", passed=True, evidence=f"accepted {sorted(accepted)}"
    )


def _pricings(run: RunArtifacts) -> list[ToolCall]:
    return [c for c in run.calls() if c.name == "dish_price" and c.result and "pricing" in c.result]


def chosen_price_above_floor(run: RunArtifacts) -> Check:
    """A price recorded in this run never sits below the floor dish_price had computed for it."""
    floors: dict[str, float] = {}
    for call in _pricings(run):
        assert call.result is not None
        rid = str(call.arguments.get("recipe_id"))
        chosen = call.arguments.get("chosen_price_brl")
        if chosen is not None and (rid not in floors or chosen < floors[rid]):
            return Check(
                name="chosen_price_above_floor",
                passed=False,
                evidence=f"{rid} priced {chosen} with tool floor {floors.get(rid)}",
            )
        floors[rid] = call.result["pricing"]["floor_price_brl"]
    return Check(
        name="chosen_price_above_floor",
        passed=True,
        evidence=f"floors from dish_price: {floors}",
    )


def prices_told_match_tool(run: RunArtifacts, expected: bool) -> Check:
    """The prices she hears are the ones dish_price returned, verbatim.

    A turn that records her choice must answer with that price; a turn that only presents the
    pricing must answer with the floor and every scenario. The consultant explains numbers; it
    must not produce them. Reading the prose here is the point: it is compared against the
    tool results of the same turn.
    """
    pricings = _pricings(run)
    if not pricings:
        return Check(
            name="prices_told_match_tool",
            passed=not expected,
            evidence="dish_price never returned a pricing in this run",
        )
    for turn in sorted({c.turn for c in pricings}):
        calls = [c for c in pricings if c.turn == turn]
        chosen = [
            c.arguments["chosen_price_brl"] for c in calls if "chosen_price_brl" in c.arguments
        ]
        if chosen:
            amounts = [float(chosen[-1])]
        else:
            last = calls[-1].result
            assert last is not None
            amounts = [last["pricing"]["floor_price_brl"]] + [
                s["price_brl"] for s in last["pricing"]["scenarios"]
            ]
        told = run.consultant_text(turn)
        absent = [a for a in amounts if not re.search(rf"R\$\s?{_brl(a)}", told)]
        if absent:
            return Check(
                name="prices_told_match_tool",
                passed=False,
                evidence=f"turn {turn}: tool returned {absent} but the reply omits them",
            )
    return Check(
        name="prices_told_match_tool",
        passed=True,
        evidence=f"{len(pricings)} pricing calls answered with the tool's numbers",
    )


def _brl(amount: float) -> str:
    return re.escape(f"{amount:.2f}".replace(".", ","))


def recipes_come_from_extracted_pages(run: RunArtifacts) -> Check:
    """Every registered URL was fetched with web_extract before registration."""
    extracted: set[str] = set()
    for call in run.calls():
        if call.name == "web_extract":
            extracted.update(call.arguments.get("urls") or [])
        if call.name == "recipe_register":
            url = str(call.arguments.get("url"))
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


def off_topic_turns_rerouted(run: RunArtifacts, expected: int, cheap_model: str) -> Check:
    """Off-topic turns, and only those, were served by the cheap model the provider reports."""
    guard_lines = [line for line in run.log_lines if "scope guard: turn" in line]
    rerouted = [line for line in guard_lines if "rerouted" in line]
    served = [line for line in guard_lines if "served by" in line]
    cheap = [line for line in served if cheap_model in line]
    count_ok = len(rerouted) >= expected if expected else not rerouted
    return Check(
        name="off_topic_turns_rerouted",
        passed=count_ok and len(cheap) == len(rerouted),
        evidence=(
            f"rerouted={len(rerouted)} served_by_{cheap_model}={len(cheap)} expected={expected}"
        ),
    )


def no_kitchen_question_repeated(run: RunArtifacts, known_fields: set[str]) -> Check:
    """On a return visit, fields already on file are not written again from her answers."""
    rewritten: set[str] = set()
    for call in run.calls():
        if call.name == "kitchen_profile":
            rewritten.update(k for k in call.arguments if k in known_fields and k != "techniques")
    return Check(
        name="no_kitchen_question_repeated",
        passed=not rewritten - {"oven"},
        evidence=f"fields rewritten on return: {sorted(rewritten)} (oven changed by design)",
    )
