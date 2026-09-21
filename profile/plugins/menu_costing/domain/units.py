"""Units of measure: pantry unit strings, base units and recipe measure conversion."""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field

from .errors import DomainError

BaseUnit = Literal["g", "ml", "un"]

_SIMPLE_UNITS: dict[str, tuple[BaseUnit, float]] = {
    "kg": ("g", 1000.0),
    "g": ("g", 1.0),
    "l": ("ml", 1000.0),
    "ml": ("ml", 1.0),
    "un": ("un", 1.0),
}
# Spreadsheet units such as "un 500g" or "balde 2kg": a counted package whose size is in the text.
_PACKAGE_UNIT = re.compile(r"^(?P<label>[a-z]+)\s+(?P<size>\d+(?:[.,]\d+)?)\s*(?P<unit>kg|g|l|ml)$")


def fold(text: str) -> str:
    """Case- and accent-insensitive key for matching names the model types against names in data."""
    stripped = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(stripped.lower().split())


class PantryUnit(BaseModel):
    """How one spreadsheet unit of an item maps to a base unit (g, ml or un)."""

    base: BaseUnit
    per_unit: float = Field(gt=0, description="Base units contained in one spreadsheet unit")


def parse_pantry_unit(text: str) -> PantryUnit:
    key = fold(text)
    if key in _SIMPLE_UNITS:
        base, per_unit = _SIMPLE_UNITS[key]
        return PantryUnit(base=base, per_unit=per_unit)
    match = _PACKAGE_UNIT.match(key)
    if match is None:
        raise ValueError(f"Unrecognized pantry unit: {text!r}")
    base, factor = _SIMPLE_UNITS[match["unit"]]
    return PantryUnit(base=base, per_unit=float(match["size"].replace(",", ".")) * factor)


class ItemProfile(BaseModel):
    """Culinary facts about one pantry item needed to convert recipe measures."""

    density_g_per_ml: float | None = Field(default=None, gt=0)
    piece_g: float | None = Field(default=None, gt=0, description="Mass of one piece")
    piece_aliases: list[str] = Field(default_factory=list, description="Units meaning one piece")


class ConversionTable(BaseModel):
    volume_ml: dict[str, float]
    mass_g: dict[str, float]
    count: list[str]
    items: dict[str, ItemProfile] = Field(default_factory=dict)

    def profile_for(self, pantry_item: str) -> ItemProfile:
        folded = {fold(name): profile for name, profile in self.items.items()}
        return folded.get(fold(pantry_item), ItemProfile())

    def accepted_units(self) -> list[str]:
        return sorted({*self.volume_ml, *self.mass_g, *self.count})


class Conversion(BaseModel):
    quantity: float
    unit: BaseUnit
    note: str = Field(description="How the recipe measure became a base quantity, for the cook")


def convert_measure(
    quantity: float, unit: str, base: BaseUnit, item_name: str, table: ConversionTable
) -> Conversion:
    """Convert a recipe measure into the pantry item's base unit."""
    key = fold(unit)
    profile = table.profile_for(item_name)
    folded_volume = {fold(k): v for k, v in table.volume_ml.items()}
    folded_mass = {fold(k): v for k, v in table.mass_g.items()}
    folded_count = {fold(k) for k in table.count} | {fold(a) for a in profile.piece_aliases}

    if key in folded_count:
        if base == "un":
            return Conversion(quantity=quantity, unit="un", note=f"{quantity:g} {unit}")
        if profile.piece_g is None:
            raise DomainError(
                f"Não sei quanto pesa uma unidade de {item_name}. Informe a quantidade em gramas."
            )
        grams = quantity * profile.piece_g
        if base == "ml":
            return _grams_to_ml(grams, item_name, profile, f"{quantity:g} {unit} = {grams:g} g")
        return Conversion(quantity=grams, unit="g", note=f"{quantity:g} {unit} = {grams:g} g")

    if key in folded_mass:
        grams = quantity * folded_mass[key]
        if base == "g":
            return Conversion(quantity=grams, unit="g", note=_note(quantity, unit, grams, "g"))
        if base == "ml":
            return _grams_to_ml(grams, item_name, profile, f"{quantity:g} {unit}")
        raise _counted_only(item_name)

    if key in folded_volume:
        millilitres = quantity * folded_volume[key]
        if base == "ml":
            return Conversion(
                quantity=millilitres, unit="ml", note=_note(quantity, unit, millilitres, "ml")
            )
        if base == "g":
            if profile.density_g_per_ml is None:
                raise DomainError(
                    f"Não tenho a densidade de {item_name} para converter volume em massa. "
                    "Informe a quantidade em gramas."
                )
            grams = millilitres * profile.density_g_per_ml
            return Conversion(
                quantity=grams,
                unit="g",
                note=f"{quantity:g} {unit} = {millilitres:g} ml = {grams:g} g",
            )
        raise _counted_only(item_name)

    raise DomainError(
        f"Unidade de medida desconhecida: {unit!r}. "
        f"Use uma destas: {', '.join(table.accepted_units())}."
    )


def _note(quantity: float, unit: str, converted: float, base: str) -> str:
    """Echo the measure as given; add the base quantity only when it differs."""
    if fold(unit) == base:
        return f"{quantity:g} {unit}"
    return f"{quantity:g} {unit} = {converted:g} {base}"


def _grams_to_ml(grams: float, item_name: str, profile: ItemProfile, prefix: str) -> Conversion:
    if profile.density_g_per_ml is None:
        raise DomainError(
            f"Não tenho a densidade de {item_name} para converter massa em volume. "
            "Informe a quantidade em mililitros."
        )
    millilitres = grams / profile.density_g_per_ml
    return Conversion(quantity=millilitres, unit="ml", note=f"{prefix} = {millilitres:g} ml")


def _counted_only(item_name: str) -> DomainError:
    return DomainError(
        f"{item_name} está contado em unidades na despensa e o tamanho da embalagem não é "
        "conhecido. Pergunte à cozinheira o tamanho e registre com pantry_amend, ou informe a "
        "quantidade em unidades."
    )
