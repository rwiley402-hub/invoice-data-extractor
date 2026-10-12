from decimal import Decimal
from pathlib import Path

import pytest

from invoice_extractor.cli import main
from invoice_extractor.config import load_settings


def test_load_settings_from_yaml_and_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "paths:\n  input_dir: inbox\nvalidation:\n  tolerance: 0.05\nocr:\n  enabled: true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("INVOICE_OUTPUT_DIR", str(tmp_path / "reports"))
    settings = load_settings(cfg)
    assert settings.input_dir == Path("inbox")
    assert settings.tolerance == Decimal("0.05")
    assert settings.ocr_enabled is True
    assert settings.output_dir == tmp_path / "reports"


def test_cli_extract_strict_flags_invalid(samples_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    out = tmp_path / "out"
    code = main(["extract", str(samples_dir), "--out", str(out), "--strict"])
    assert code == 2
    assert (out / "invoices.xlsx").exists()
    assert "9 valid, 1 invalid" in capsys.readouterr().out


def test_cli_extract_single_valid_file(samples_dir: Path, tmp_path: Path) -> None:
    code = main(["extract", str(samples_dir / "invoice_02_northwind.pdf"), "--out", str(tmp_path), "--format", "json"])
    assert code == 0
    assert (tmp_path / "invoices.json").exists()
    assert not (tmp_path / "invoices.xlsx").exists()
