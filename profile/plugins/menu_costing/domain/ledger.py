"""On-disk state of a consultation: the kitchen, pantry amendments and one file per session."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, TypeAdapter

from .models import Consultation, KitchenProfile, PantryAmendment

_AMENDMENTS = TypeAdapter(list[PantryAmendment])


class Store:
    """The kitchen and the amendments outlive sessions: one cook, one kitchen, one pantry."""

    def __init__(self, root: Path) -> None:
        self.root = root

    @property
    def kitchen_path(self) -> Path:
        return self.root / "kitchen.json"

    @property
    def amendments_path(self) -> Path:
        return self.root / "pantry_amendments.json"

    def session_path(self, session_id: str) -> Path:
        return self.root / "sessions" / f"{session_id}.json"

    def load_kitchen(self) -> KitchenProfile:
        if not self.kitchen_path.exists():
            return KitchenProfile()
        return KitchenProfile.model_validate_json(self.kitchen_path.read_text("utf-8"))

    def save_kitchen(self, profile: KitchenProfile) -> None:
        _write(self.kitchen_path, profile)

    def load_amendments(self) -> list[PantryAmendment]:
        if not self.amendments_path.exists():
            return []
        return _AMENDMENTS.validate_json(self.amendments_path.read_text("utf-8"))

    def save_amendments(self, amendments: list[PantryAmendment]) -> None:
        payload = _AMENDMENTS.dump_json(amendments, indent=2)
        _write_bytes(self.amendments_path, payload)

    def load_consultation(self, session_id: str, budget_brl: float) -> Consultation:
        path = self.session_path(session_id)
        if not path.exists():
            return Consultation(session_id=session_id, budget_brl=budget_brl)
        return Consultation.model_validate_json(path.read_text("utf-8"))

    def save_consultation(self, consultation: Consultation) -> None:
        _write(self.session_path(consultation.session_id), consultation)


def _write(path: Path, model: BaseModel) -> None:
    _write_bytes(path, model.model_dump_json(indent=2).encode("utf-8"))


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(payload)
    os.replace(tmp, path)
