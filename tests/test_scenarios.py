"""The seeded states the evaluation scenarios start from must load with the current models."""

from __future__ import annotations

from pathlib import Path

import pytest
from menu_costing.domain.ledger import Store

STATES = sorted((Path(__file__).resolve().parents[1] / "evals" / "scenarios" / "state").iterdir())


@pytest.mark.parametrize("state", STATES, ids=[s.name for s in STATES])
def test_scenario_state_loads(state: Path) -> None:
    store = Store(state)
    assert store.load_kitchen() is not None
    menu = store.load_menu(budget_brl=80.0)
    assert all(r.accepted for r in menu.recipes.values())
