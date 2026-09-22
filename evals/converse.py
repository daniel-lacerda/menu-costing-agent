"""Drive a full consultation with a simulated cook, using the same runtime as the CLI.

Run inside the Hermes environment with HERMES_HOME set to the profile (scripts/converse.sh).
The consultant is the real agent: same provider, toolsets, plugin, skills and session store.
The cook is a cheap model playing a scenario whose facts it only reveals when asked.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

import yaml
from openai import OpenAI
from pydantic import BaseModel, Field

END_MARK = "[FIM]"


class Scenario(BaseModel):
    name: str
    opening: str
    max_turns: int = Field(gt=0)
    persona: str
    facts: str
    behaviour: str
    state: Path | None = Field(
        default=None, description="Directory copied over the consultation store before the run"
    )


class SimulatedCook:
    """Answers both chat turns and clarify prompts from the scenario, never from the consultant."""

    def __init__(self, scenario: Scenario, client: OpenAI, model: str) -> None:
        self.scenario = scenario
        self.client = client
        self.model = model
        self.transcript: list[dict[str, str]] = []

    def _instructions(self) -> str:
        return (
            f"{self.scenario.persona}\n\nFatos sobre você (revele só se perguntada):\n"
            f"{self.scenario.facts}\n\nComo se comportar:\n{self.scenario.behaviour}\n\n"
            "Responda com uma única mensagem curta, em português, só com o que a Dona Maria diria."
        )

    def reply(self, consultant_message: str) -> str:
        self.transcript.append({"role": "consultora", "content": consultant_message})
        history = "\n\n".join(f"[{t['role']}] {t['content']}" for t in self.transcript)
        answer = self._ask(f"Conversa até agora:\n\n{history}\n\nSua próxima mensagem:")
        self.transcript.append({"role": "dona maria", "content": answer})
        return answer

    def clarify(self, question: str, choices: list[str] | None, multi_select: bool = False) -> str:
        options = ""
        if choices:
            kind = (
                "Pode escolher mais de uma, separadas por vírgula."
                if multi_select
                else "Escolha uma."
            )
            options = f"\nOpções: {', '.join(choices)}. {kind} Responda com o texto exato da opção."
        history = "\n\n".join(f"[{t['role']}] {t['content']}" for t in self.transcript)
        answer = self._ask(
            f"Conversa até agora:\n\n{history}\n\nA consultora pergunta: {question}{options}\n"
            "Responda de forma curta."
        )
        self.transcript.append({"role": "consultora (pergunta)", "content": question})
        self.transcript.append({"role": "dona maria", "content": answer})
        return answer

    def _ask(self, prompt: str) -> str:
        response = self.client.responses.create(
            model=self.model, instructions=self._instructions(), input=prompt
        )
        return response.output_text.strip()


def cheap_model(config: dict[str, Any]) -> str:
    """The small model the profile already routes off-topic turns to."""
    settings = config["plugins"]["entries"]["menu_costing"]["settings"]
    return str(settings["scope_model"])


def build_agent(session_id: str, cook: SimulatedCook, model: str | None = None) -> Any:
    from hermes_cli.config import load_config
    from hermes_cli.runtime_provider import resolve_runtime_provider
    from hermes_cli.tools_config import _get_platform_tools
    from hermes_state_registry import acquire
    from run_agent import AIAgent

    config = load_config()
    runtime = resolve_runtime_provider(
        requested=config["model"]["provider"], target_model=config["model"]["default"]
    )
    return AIAgent(
        model=model or config["model"]["default"],
        api_key=runtime.get("api_key"),
        base_url=runtime.get("base_url"),
        provider=runtime.get("provider"),
        requested_provider=runtime.get("requested_provider"),
        api_mode=runtime.get("api_mode"),
        enabled_toolsets=sorted(_get_platform_tools(config, "cli")),
        quiet_mode=True,
        session_id=session_id,
        platform="cli",
        session_db=acquire(),
        clarify_callback=cook.clarify,
    )


def reset_store(home: Path, scenario: Scenario, scenario_dir: Path) -> None:
    """Every run starts from the scenario's declared state, never from a previous run's.

    Hermes memory (USER.md, MEMORY.md) is reset too: preferences one simulated cook stated
    must not leak into the next scenario.
    """
    store = home / "consultations"
    shutil.rmtree(store, ignore_errors=True)
    shutil.rmtree(home / "memories", ignore_errors=True)
    (home / "memories").mkdir()
    if scenario.state is not None:
        shutil.copytree(scenario_dir / scenario.state, store)


def tool_calls_in(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each call with the result the tool returned, so checks can compare prose with data."""
    results = {
        message.get("tool_call_id"): message.get("content")
        for message in messages
        if message.get("role") == "tool"
    }
    calls: list[dict[str, Any]] = []
    for message in messages:
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            calls.append(
                {
                    "name": function.get("name"),
                    "arguments": function.get("arguments"),
                    "result": results.get(call.get("id")),
                }
            )
    return calls


def exchange(
    agent: Any, turn: int, message: str, history: list[dict[str, Any]] | None, log: TextIO
) -> tuple[str, list[dict[str, Any]]]:
    """One cook message through the agent; returns its answer and the grown history."""
    print(f"\n[{turn}] dona maria: {message}", flush=True)
    started = time.monotonic()
    result = agent.run_conversation(user_message=message, conversation_history=history)
    seconds = round(time.monotonic() - started, 1)
    seen = len(history or [])
    grown: list[dict[str, Any]] = result["messages"]
    calls = tool_calls_in(grown[seen:])
    answer: str = result["final_response"]
    for call in calls:
        print(f"    tool: {call['name']}", flush=True)
    print(f"[{turn}] consultora: {answer}", flush=True)
    record = {
        "turn": turn,
        "cook": message,
        "tool_calls": calls,
        "consultant": answer,
        "seconds": seconds,
        "at": datetime.now(UTC).isoformat(),
    }
    log.write(json.dumps(record, ensure_ascii=False) + "\n")
    log.flush()
    return answer, grown


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", type=Path)
    parser.add_argument(
        "--model", help="Main model override; the provider stays the configured one"
    )
    parser.add_argument(
        "--cook-model",
        help="Model that plays Dona Maria; defaults to the profile's cheap model (scope_model)",
    )
    args = parser.parse_args()

    from hermes_cli.config import load_config
    from hermes_cli.env_loader import load_hermes_dotenv
    from hermes_constants import get_hermes_home
    from hermes_state_ids import new_session_id

    load_hermes_dotenv(hermes_home=get_hermes_home())
    scenario = Scenario.model_validate(yaml.safe_load(args.scenario.read_text("utf-8")))
    reset_store(get_hermes_home(), scenario, args.scenario.parent)
    cook_model = args.cook_model or cheap_model(load_config())
    cook = SimulatedCook(scenario, OpenAI(), cook_model)
    session_id = new_session_id()
    agent = build_agent(session_id, cook, args.model)

    run_dir = Path(__file__).parent / "runs" / f"{scenario.name}-{session_id}"
    run_dir.mkdir(parents=True)
    with (run_dir / "turns.jsonl").open("w", encoding="utf-8") as log:
        history: list[dict[str, Any]] | None = None
        message = scenario.opening
        for turn in range(1, scenario.max_turns + 1):
            answer, history = exchange(agent, turn, message, history, log)
            message = cook.reply(answer)
            if END_MARK in message:
                # The cook's goodbye still deserves an answer; a bare marker does not.
                message = message.replace(END_MARK, "").strip()
                if message:
                    exchange(agent, turn + 1, message, history, log)
                break

    (run_dir / "cook_transcript.json").write_text(
        json.dumps(cook.transcript, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nsession {session_id}; run saved under {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
