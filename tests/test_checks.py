"""The deterministic checks of the evaluation suite, on runs small enough to read."""

from __future__ import annotations

import json
from typing import Any

from checks import (
    RunArtifacts,
    accepted_only_after_confirmation,
    no_kitchen_question_repeated,
    off_topic_turns_rerouted,
    prices_told_match_tool,
    pricing_only_after_acceptance,
    recipes_come_from_extracted_pages,
)
from judge import transcript_text

PRICING = {
    "recipe_id": "r1",
    "pricing": {"floor_price_brl": 7.02, "scenarios": [{"price_brl": 8.78}, {"price_brl": 10.8}]},
}


def call(name: str, arguments: dict[str, Any], result: dict[str, Any] | None = None) -> dict:
    return {
        "name": name,
        "arguments": json.dumps(arguments),
        "result": json.dumps(result) if result is not None else None,
    }


def turn(number: int, cook: str, calls: list[dict], consultant: str) -> dict[str, Any]:
    return {"turn": number, "cook": cook, "tool_calls": calls, "consultant": consultant}


def run(turns: list[dict[str, Any]], **extra: Any) -> RunArtifacts:
    return RunArtifacts(turns=turns, menu=None, kitchen=None, log_lines=[], session_id="s", **extra)


def test_a_pricing_reply_must_repeat_the_floor_and_every_scenario() -> None:
    presented = turn(2, "e o preço?", [call("dish_price", {"recipe_id": "r1"}, PRICING)], "")
    presented["consultant"] = "O mínimo é R$ 7,02; com 20% fica R$ 8,78 e com 50% R$10,80."
    assert prices_told_match_tool(run([presented]), True).passed
    presented["consultant"] = "O mínimo é R$ 7,02; com 20% fica R$ 8,79."
    assert not prices_told_match_tool(run([presented]), True).passed


def test_a_recording_reply_must_repeat_the_chosen_price_only() -> None:
    recorded = turn(
        3,
        "fico com 8,78",
        [call("dish_price", {"recipe_id": "r1", "chosen_price_brl": 8.78}, PRICING)],
        "Fica por R$ 8,78 então.",
    )
    assert prices_told_match_tool(run([recorded]), True).passed


def test_a_consultation_that_should_price_and_did_not_fails() -> None:
    silent = run([turn(1, "oi", [], "Quantas bocas?")])
    assert not prices_told_match_tool(silent, True).passed
    assert prices_told_match_tool(silent, False).passed


def test_pricing_a_dish_accepted_in_an_earlier_session_is_fine() -> None:
    priced = run([turn(1, "preço do r1", [call("dish_price", {"recipe_id": "r1"})], "...")])
    assert not pricing_only_after_acceptance(priced, set()).passed
    assert pricing_only_after_acceptance(priced, {"r1"}).passed


def test_acceptance_needs_liked_and_techniques_on_file() -> None:
    accepted = run(
        [turn(1, "fecha", [call("recipe_update", {"recipe_id": "r1", "accepted": True})], "")]
    )
    assert not accepted_only_after_confirmation(accepted).passed
    confirmed = run(
        [
            turn(
                1,
                "fecha",
                [call("recipe_update", {"recipe_id": "r1", "liked": True, "accepted": True})],
                "",
            )
        ],
    )
    confirmed.menu = {
        "recipes": {"r1": {"id": "r1", "accepted": True, "techniques_required": ["Refogar"]}}
    }
    confirmed.kitchen = {"techniques": {"refogar": True}}
    assert accepted_only_after_confirmation(confirmed).passed


def test_off_topic_turns_are_counted_exactly() -> None:
    quiet = run([])
    quiet.log_lines = ["scope guard: turn 1 rerouted to cheap"]
    assert off_topic_turns_rerouted(quiet, 1, "cheap").passed
    assert not off_topic_turns_rerouted(quiet, 0, "cheap").passed
    assert not off_topic_turns_rerouted(quiet, 2, "cheap").passed


def test_registering_a_page_that_was_not_extracted_fails() -> None:
    url = "https://example.org/r"
    extracted = run(
        [
            turn(
                1,
                "",
                [
                    call("web_extract", {"urls": [url]}),
                    call("recipe_register", {"url": url}),
                ],
                "",
            )
        ]
    )
    assert recipes_come_from_extracted_pages(extracted).passed
    invented = run([turn(1, "", [call("recipe_register", {"url": url})], "")])
    assert not recipes_come_from_extracted_pages(invented).passed


def test_return_visit_may_change_a_fact_but_not_re_ask_it() -> None:
    on_file = {"burners": 4, "equipment": {"forno": False, "panela de pressão": True}}
    changed = run([turn(1, "", [call("kitchen_profile", {"equipment": {"Forno": True}})], "")])
    assert no_kitchen_question_repeated(changed, on_file).passed
    re_asked = run(
        [turn(1, "", [call("kitchen_profile", {"burners": 4, "equipment": {"forno": False}})], "")]
    )
    assert not no_kitchen_question_repeated(re_asked, on_file).passed


def test_the_judge_sees_tool_calls_between_the_lines_the_cook_saw() -> None:
    turns = [turn(1, "oi", [call("kitchen_profile", {})], "Quantas bocas?")]
    cook_transcript = [
        {"role": "dona maria", "content": "oi"},
        {"role": "consultora (pergunta)", "content": "Bocas?"},
        {"role": "dona maria", "content": "4"},
        {"role": "consultora", "content": "Quantas bocas?"},
    ]
    text = transcript_text(turns, cook_transcript)
    assert text.index("[dona maria] oi") < text.index("[tools] kitchen_profile()")
    assert text.index("[tools] kitchen_profile()") < text.index("[consultora] Quantas bocas?")
