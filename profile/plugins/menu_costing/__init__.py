"""Hermes plugin entry point: wires settings and storage into the tools and registers them."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .domain.ledger import Store
from .tools import TOOLSET, Settings, build_tools

if TYPE_CHECKING:
    from hermes_cli.plugins import PluginContext

_PLUGIN_DIR = Path(__file__).resolve().parent


def register(ctx: PluginContext) -> None:
    from hermes_constants import get_hermes_home

    home = get_hermes_home()
    settings = Settings(
        pantry_path=home / str(ctx.get_config("pantry_path", "data/despensa_dona_maria.xlsx")),
        conversions_path=_PLUGIN_DIR / "data" / "conversions.yaml",
        budget_brl=float(ctx.get_config("budget_brl", 80.0)),
        platform_fee=float(ctx.get_config("platform_fee", 0.10)),
        margins=tuple(float(m) for m in ctx.get_config("margins", [0.20, 0.35, 0.50])),
    )
    store = Store(home / "consultations")
    for tool in build_tools(settings, store):
        ctx.register_tool(name=tool.name, toolset=TOOLSET, schema=tool.schema, handler=tool.handler)
