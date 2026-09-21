from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from menu_costing.domain.ledger import Store
from menu_costing.domain.models import (
    IngredientInput,
    KitchenProfile,
    PantryItem,
    Purchase,
    Recipe,
)
from menu_costing.domain.pantry import load_pantry
from menu_costing.domain.units import ConversionTable
from menu_costing.tools import Settings, Tool, build_tools

REPO = Path(__file__).resolve().parents[1]
PANTRY_XLSX = REPO / "profile" / "data" / "despensa_dona_maria.xlsx"
CONVERSIONS = REPO / "profile" / "plugins" / "menu_costing" / "data" / "conversions.yaml"


@pytest.fixture(scope="session")
def table() -> ConversionTable:
    return ConversionTable.model_validate(yaml.safe_load(CONVERSIONS.read_text("utf-8")))


@pytest.fixture(scope="session")
def pantry_path() -> Path:
    return PANTRY_XLSX


@pytest.fixture(scope="session")
def pantry() -> list[PantryItem]:
    return load_pantry(PANTRY_XLSX)


@pytest.fixture
def complete_kitchen() -> KitchenProfile:
    return KitchenProfile(
        burners=4,
        oven=False,
        pressure_cooker=True,
        air_fryer=False,
        blender=True,
        fuel="gas",
        fridge_space="medio",
        time_per_batch_minutes=90,
        techniques={"refogar": True, "massa fresca": False},
    )


@pytest.fixture
def stroganoff() -> Recipe:
    """A liked recipe whose gate closes: one item short, one missing, both covered by purchases."""
    return Recipe(
        id="r1",
        title="Estrogonofe de carne",
        url="https://example.org/estrogonofe",
        yield_portions=4,
        ingredients=[
            IngredientInput(name="alcatra", quantity=1, unit="kg", pantry_item="Miolo de alcatra"),
            IngredientInput(name="cebola", quantity=1, unit="cebola", pantry_item="Cebola"),
            IngredientInput(name="creme de leite", quantity=200, unit="g", pantry_item=None),
        ],
        equipment_required=["fogao"],
        burners_needed=2,
        techniques_required=["refogar"],
        liked=True,
        purchases=[
            Purchase(
                ingredient="alcatra", quantity=200, unit="g", price_brl=8.5, confirmed_by_cook=True
            ),
            Purchase(
                ingredient="creme de leite",
                quantity=200,
                unit="g",
                price_brl=4.5,
                confirmed_by_cook=True,
            ),
        ],
    )


@pytest.fixture
def settings() -> Settings:
    return Settings(
        pantry_path=PANTRY_XLSX,
        conversions_path=CONVERSIONS,
        budget_brl=80.0,
        platform_fee=0.10,
        margins=(0.20, 0.35, 0.50),
    )


@pytest.fixture
def tools(settings: Settings, tmp_path: Path) -> dict[str, Tool]:
    return {tool.name: tool for tool in build_tools(settings, Store(tmp_path))}
