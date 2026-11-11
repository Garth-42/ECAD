"""Parts library: catalogue entries (Parts) loaded from JSON files."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

CATEGORIES: frozenset[str] = frozenset(
    {
        "breaker",
        "fuse",
        "contactor",
        "relay",
        "overload",
        "motor",
        "pushbutton",
        "terminal_block",
        "power_supply",
        "plc",
        "other",
    }
)


class UnknownPartError(KeyError):
    """Raised when a part number is not present in the library."""


@dataclass(frozen=True)
class PinDef:
    name: str
    local_pos: tuple[float, float, float]


@dataclass(frozen=True)
class Part:
    part_number: str
    manufacturer: str
    description: str
    category: str
    pins: tuple[PinDef, ...]
    size: tuple[float, float, float]
    current_rating_a: float | None = None
    properties: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.category not in CATEGORIES:
            raise ValueError(
                f"part {self.part_number!r}: category {self.category!r} "
                f"not in {sorted(CATEGORIES)}"
            )

    def pin(self, name: str) -> PinDef:
        for p in self.pins:
            if p.name == name:
                return p
        raise KeyError(f"part {self.part_number!r} has no pin {name!r}")


def _part_from_dict(data: dict, source: str) -> Part:
    try:
        return Part(
            part_number=data["part_number"],
            manufacturer=data["manufacturer"],
            description=data["description"],
            category=data["category"],
            pins=tuple(
                PinDef(name=p["name"], local_pos=tuple(p["local_pos"])) for p in data["pins"]
            ),
            size=tuple(data["size"]),
            current_rating_a=data.get("current_rating_a"),
            properties=data.get("properties", {}),
        )
    except KeyError as exc:
        raise ValueError(f"part file {source}: missing required field {exc}") from exc


class PartLibrary:
    """All known Parts, keyed by part number."""

    def __init__(self, parts: dict[str, Part] | None = None) -> None:
        self._parts: dict[str, Part] = dict(parts or {})

    def add(self, part: Part) -> None:
        self._parts[part.part_number] = part

    def get(self, part_number: str) -> Part:
        try:
            return self._parts[part_number]
        except KeyError:
            raise UnknownPartError(
                f"part number {part_number!r} not in library "
                f"(known: {sorted(self._parts) or 'none'})"
            ) from None

    def __contains__(self, part_number: str) -> bool:
        return part_number in self._parts

    def __len__(self) -> int:
        return len(self._parts)

    def part_numbers(self) -> list[str]:
        return sorted(self._parts)

    def load_directory(self, directory: Path) -> None:
        """Load every ``*.json`` part file under ``directory``.

        Parts loaded here replace same-numbered parts already in the library
        (that is how a project library overrides a bundled part), but two
        files in the *same* directory defining one part number is an error.
        """
        directory = Path(directory)
        if not directory.is_dir():
            raise FileNotFoundError(f"parts directory not found: {directory}")
        seen: dict[str, Path] = {}
        for path in sorted(directory.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError(f"part file {path}: invalid JSON ({exc})") from exc
            part = _part_from_dict(data, str(path))
            if part.part_number in seen:
                raise ValueError(
                    f"part number {part.part_number!r} is defined twice: "
                    f"{seen[part.part_number].name} and {path.name}"
                )
            seen[part.part_number] = path
            self.add(part)

    @classmethod
    def bundled(cls) -> PartLibrary:
        """Library preloaded with the parts shipped under ``library/data/``."""
        lib = cls()
        data_dir = resources.files("panelkit.library") / "data"
        with resources.as_file(data_dir) as directory:
            lib.load_directory(directory)
        return lib
