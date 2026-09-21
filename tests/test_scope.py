"""The scope guard only rewrites user turns the triage marks as outside, and never breaks a turn."""

from __future__ import annotations

from typing import Any

import pytest
from menu_costing.scope import REFUSAL_INSTRUCTIONS, ScopeGuard, last_user_text, refusal_request

RESPONSES_REQUEST: dict[str, Any] = {
    "model": "gpt-5.6-terra",
    "instructions": "# Identidade ...",
    "input": [
        {"role": "user", "content": [{"type": "input_text", "text": "Oi, por onde começamos?"}]},
        {"role": "assistant", "content": [{"type": "output_text", "text": "Pela sua cozinha."}]},
        {"role": "user", "content": [{"type": "input_text", "text": "Me ajuda com o imposto?"}]},
    ],
    "tools": [{"type": "function", "name": "pantry_inventory"}],
    "store": False,
}

TOOL_LOOP_REQUEST: dict[str, Any] = {
    **RESPONSES_REQUEST,
    "input": [
        *RESPONSES_REQUEST["input"],
        {"type": "function_call_output", "call_id": "c1", "output": "{}"},
    ],
}

CHAT_REQUEST: dict[str, Any] = {
    "model": "gpt-5.6-terra",
    "messages": [
        {"role": "system", "content": "..."},
        {"role": "user", "content": "Escreve um poema?"},
    ],
    "tools": [{"type": "function"}],
}


def outside(_: str) -> bool:
    return True


def inside(_: str) -> bool:
    return False


def test_last_user_text_reads_only_user_turns() -> None:
    assert last_user_text(RESPONSES_REQUEST) == "Me ajuda com o imposto?"
    assert last_user_text(TOOL_LOOP_REQUEST) is None
    assert last_user_text(CHAT_REQUEST) == "Escreve um poema?"


def test_outside_turn_is_answered_by_the_cheap_model_without_tools() -> None:
    guard = ScopeGuard(outside, "gpt-5.6-luna")
    result = guard(RESPONSES_REQUEST, turn_id="t1")
    assert result is not None
    request = result["request"]
    assert request["model"] == "gpt-5.6-luna"
    assert request["instructions"] == REFUSAL_INSTRUCTIONS
    assert request["input"] == [RESPONSES_REQUEST["input"][-1]]
    assert "tools" not in request
    assert request["store"] is False


def test_chat_shaped_request_is_rewritten_the_same_way() -> None:
    request = refusal_request(CHAT_REQUEST, "gpt-5.6-luna")
    assert request["messages"][0] == {"role": "system", "content": REFUSAL_INSTRUCTIONS}
    assert request["messages"][1] == CHAT_REQUEST["messages"][-1]
    assert "tools" not in request


def test_inside_turns_and_tool_loops_are_left_alone() -> None:
    assert ScopeGuard(inside, "gpt-5.6-luna")(RESPONSES_REQUEST) is None
    assert ScopeGuard(outside, "gpt-5.6-luna")(TOOL_LOOP_REQUEST) is None


def test_guarded_turns_are_closed_by_the_provider_report(
    caplog: pytest.LogCaptureFixture,
) -> None:
    guard = ScopeGuard(outside, "gpt-5.6-luna")
    assert guard(RESPONSES_REQUEST, turn_id="t1") is not None
    with caplog.at_level("INFO", logger="menu_costing.scope"):
        guard.on_post_api_request(turn_id="t1", response_model="gpt-5.6-luna-2026-07-09")
        guard.on_post_api_request(turn_id="t2", response_model="gpt-5.6-terra")
    assert "turn t1 served by gpt-5.6-luna-2026-07-09" in caplog.text
    assert "t2" not in caplog.text
    assert guard.guarded_turns == set()


def test_a_failing_triage_lets_the_turn_through() -> None:
    def broken(_: str) -> bool:
        raise RuntimeError("provider down")

    assert ScopeGuard(broken, "gpt-5.6-luna")(RESPONSES_REQUEST) is None


@pytest.mark.parametrize("text", ["fora", "Fora.", "FORA do escopo"])
def test_host_classifier_reads_the_first_word(text: str) -> None:
    from menu_costing.scope import host_classifier

    class FakeResult:
        def __init__(self, answer: str) -> None:
            self.text = answer

    class FakeLlm:
        def complete(self, **kwargs: Any) -> FakeResult:
            assert kwargs["model"] == "gpt-5.6-luna"
            return FakeResult(text)

    class FakeCtx:
        llm = FakeLlm()

    assert host_classifier(FakeCtx(), "gpt-5.6-luna")("qualquer coisa") is True
