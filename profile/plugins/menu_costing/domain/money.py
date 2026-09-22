"""Amounts in reais the way the cook reads them: R$ 1.234,56."""

from __future__ import annotations


def brl(amount: float) -> str:
    grouped = f"{amount:,.2f}"
    return "R$ " + grouped.replace(",", "\0").replace(".", ",").replace("\0", ".")


def per_unit(unit_cost: float, unit: str) -> str:
    """Unit cost per kilo or litre when the unit is a gram or a millilitre, else per that unit."""
    scale, label = {"g": (1000, "kg"), "ml": (1000, "L")}.get(unit, (1, unit))
    return f"{brl(unit_cost * scale)}/{label}"
