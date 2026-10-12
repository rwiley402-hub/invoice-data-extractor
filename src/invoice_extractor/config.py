"""Configuration: defaults <- config.yaml <- environment variables (.env supported)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

log = logging.getLogger(__name__)

DEFAULT_CONFIG_FILE = Path("config.yaml")


@dataclass
class Settings:
    input_dir: Path = Path("samples")
    output_dir: Path = Path("output")
    excel_filename: str = "invoices.xlsx"
    json_filename: str = "invoices.json"
    tolerance: Decimal = Decimal("0.01")
    watch_interval: float = 5.0
    watch_settle_seconds: float = 2.0
    ocr_enabled: bool = False
    ocr_language: str = "eng"
    log_level: str = "INFO"


_ENV_MAP: dict[str, tuple[str, type]] = {
    "INVOICE_INPUT_DIR": ("input_dir", Path),
    "INVOICE_OUTPUT_DIR": ("output_dir", Path),
    "INVOICE_TOLERANCE": ("tolerance", Decimal),
    "INVOICE_WATCH_INTERVAL": ("watch_interval", float),
    "INVOICE_OCR_ENABLED": ("ocr_enabled", bool),
    "INVOICE_OCR_LANGUAGE": ("ocr_language", str),
    "LOG_LEVEL": ("log_level", str),
}


def _coerce(value: Any, kind: type) -> Any:
    if kind is bool:
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
    if kind is Decimal:
        return Decimal(str(value))
    return kind(value)


def load_settings(config_file: Path | None = None) -> Settings:
    load_dotenv()
    settings = Settings()
    path = Path(config_file or os.getenv("INVOICE_CONFIG", DEFAULT_CONFIG_FILE))
    if path.is_file():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        flat = {
            "input_dir": raw.get("paths", {}).get("input_dir"),
            "output_dir": raw.get("paths", {}).get("output_dir"),
            "excel_filename": raw.get("export", {}).get("excel_filename"),
            "json_filename": raw.get("export", {}).get("json_filename"),
            "tolerance": raw.get("validation", {}).get("tolerance"),
            "watch_interval": raw.get("watch", {}).get("interval_seconds"),
            "watch_settle_seconds": raw.get("watch", {}).get("settle_seconds"),
            "ocr_enabled": raw.get("ocr", {}).get("enabled"),
            "ocr_language": raw.get("ocr", {}).get("language"),
            "log_level": raw.get("logging", {}).get("level"),
        }
        for key, value in flat.items():
            if value is not None:
                default = getattr(settings, key)
                setattr(settings, key, _coerce(value, type(default)) if not isinstance(default, Path) else Path(value))
    elif config_file is not None:
        log.warning("config file %s not found, using defaults", path)

    for env_key, (attr, kind) in _ENV_MAP.items():
        if (value := os.getenv(env_key)) not in (None, ""):
            setattr(settings, attr, _coerce(value, kind))
    return settings
