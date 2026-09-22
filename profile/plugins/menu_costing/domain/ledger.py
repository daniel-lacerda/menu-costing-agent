"""On-disk state of the cook: her kitchen, her pantry amendments and her launch menu."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, TypeAdapter

from .models import KitchenProfile, Menu, PantryAmendment

_AMENDMENTS = TypeAdapter(list[PantryAmendment])


class Store:
    """Everything here outlives sessions: one cook, one kitchen, one pantry, one launch menu."""

    def __init__(self, root: Path) -> None:
        self.root = root

    @property
    def kitchen_path(self) -> Path:
        return self.root / "kitchen.json"

    @property
    def amendments_path(self) -> Path:
        return self.root / "pantry_amendments.json"

    @property
    def menu_path(self) -> Path:
        return self.root / "menu.json"

    def load_kitchen(self) -> KitchenProfile:
        if not self.kitchen_path.exists():
            return KitchenProfile()
        return KitchenProfile.model_validate_json(self.kitchen_path.read_text("utf-8"))

    def save_kitchen(self, profile: KitchenProfile) -> None:
        _write(self.kitchen_path, profile)

    def kitchen_updated_at(self) -> datetime | None:
        if not self.kitchen_path.exists():
            return None
        return datetime.fromtimestamp(self.kitchen_path.stat().st_mtime, tz=UTC)

    def load_amendments(self) -> list[PantryAmendment]:
        if not self.amendments_path.exists():
            return []
        return _AMENDMENTS.validate_json(self.amendments_path.read_text("utf-8"))

    def save_amendments(self, amendments: list[PantryAmendment]) -> None:
        payload = _AMENDMENTS.dump_json(amendments, indent=2)
        _write_bytes(self.amendments_path, payload)

    def load_menu(self, budget_brl: float) -> Menu:
        if not self.menu_path.exists():
            return Menu(budget_brl=budget_brl)
        return Menu.model_validate_json(self.menu_path.read_text("utf-8"))

    def save_menu(self, menu: Menu) -> None:
        _write(self.menu_path, menu)


def _write(path: Path, model: BaseModel) -> None:
    _write_bytes(path, model.model_dump_json(indent=2).encode("utf-8"))


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(payload)
    os.replace(tmp, path)
