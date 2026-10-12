from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from invoice_extractor.config import Settings

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"


@pytest.fixture(scope="session")
def samples_dir() -> Path:
    return SAMPLES


@pytest.fixture(scope="session")
def expected() -> dict[str, dict]:
    entries = json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8"))
    return {entry["file"]: entry for entry in entries}


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        input_dir=tmp_path / "inbox",
        output_dir=tmp_path / "out",
        tolerance=Decimal("0.01"),
        watch_interval=0.0,
        watch_settle_seconds=0.0,
    )
