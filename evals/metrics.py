"""Latency and cost of a run, read from the harness timings and from Hermes' own usage table.

Behaviour checks say whether the consultant did the right thing; these say what it cost the
cook in waiting time and the operator in tokens. Both belong in the same report.
"""

from __future__ import annotations

import sqlite3
import statistics
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ModelUsage(BaseModel):
    model: str
    task: str
    api_calls: int
    input_tokens: int = Field(description="Uncached input tokens, as Hermes accounts them")
    cache_read_tokens: int
    cache_write_tokens: int
    output_tokens: int
    estimated_cost_usd: float | None


class Metrics(BaseModel):
    turns: int
    tool_calls: int
    turn_seconds_p50: float
    turn_seconds_max: float
    usage: list[ModelUsage]

    @property
    def cost_usd(self) -> float:
        return sum(u.estimated_cost_usd or 0.0 for u in self.usage)

    @property
    def main_model_cache_share(self) -> float:
        """Share of main-model input served from the prompt cache; the system prompt is the bulk."""
        main = [u for u in self.usage if not u.task]
        read = sum(u.cache_read_tokens for u in main)
        total = sum(u.input_tokens + u.cache_read_tokens + u.cache_write_tokens for u in main)
        return read / total if total else 0.0


def collect(turns: list[dict[str, Any]], state_db: Path, session_id: str) -> Metrics:
    seconds = [float(t["seconds"]) for t in turns if "seconds" in t]
    con = sqlite3.connect(f"file:{state_db}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT model, task, api_call_count, input_tokens, cache_read_tokens, "
        "cache_write_tokens, output_tokens, estimated_cost_usd "
        "FROM session_model_usage WHERE session_id = ?",
        (session_id,),
    ).fetchall()
    con.close()
    return Metrics(
        turns=len(turns),
        tool_calls=sum(len(t["tool_calls"]) for t in turns),
        turn_seconds_p50=round(statistics.median(seconds), 1) if seconds else 0.0,
        turn_seconds_max=round(max(seconds), 1) if seconds else 0.0,
        usage=[
            ModelUsage(
                model=row[0],
                task=row[1] or "",
                api_calls=int(row[2] or 0),
                input_tokens=int(row[3] or 0),
                cache_read_tokens=int(row[4] or 0),
                cache_write_tokens=int(row[5] or 0),
                output_tokens=int(row[6] or 0),
                estimated_cost_usd=row[7],
            )
            for row in rows
        ],
    )
