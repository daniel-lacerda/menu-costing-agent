"""Hermes plugin entry point: wires settings and storage into the tools and registers them."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .domain.ledger import Store
from .scope import ScopeGuard, host_classifier
from .tools import TOOLSET, Settings, build_tools

if TYPE_CHECKING:
    from hermes_cli.plugins import PluginContext

_PLUGIN_DIR = Path(__file__).resolve().parent


def register(ctx: PluginContext) -> None:
    from hermes_constants import get_hermes_home

    home = get_hermes_home()
    # Every value comes from config.yaml; a missing one fails here, not in the first consultation.
    settings = Settings(
        pantry_path=home / str(ctx.get_config("pantry_path")),
        conversions_path=_PLUGIN_DIR / "data" / "conversions.yaml",
        budget_brl=ctx.get_config("budget_brl"),
        platform_fee=ctx.get_config("platform_fee"),
        margins=ctx.get_config("margins"),
    )
    store = Store(home / "consultations")
    for tool in build_tools(settings, store):
        ctx.register_tool(name=tool.name, toolset=TOOLSET, schema=tool.schema, handler=tool.handler)
    if ctx.get_config("scope_guard"):
        model = str(ctx.get_config("scope_model"))
        guard = ScopeGuard(host_classifier(ctx, model), model)
        ctx.register_middleware("llm_request", guard)
        ctx.register_hook("post_api_request", guard.on_post_api_request)
