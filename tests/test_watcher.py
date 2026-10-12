import json
import shutil
from pathlib import Path

from invoice_extractor.config import Settings
from invoice_extractor.watcher import FolderWatcher


def _report(settings: Settings) -> dict:
    return json.loads((settings.output_dir / settings.json_filename).read_text(encoding="utf-8"))


def test_watcher_processes_new_files_once(samples_dir: Path, settings: Settings) -> None:
    watcher = FolderWatcher(settings)
    assert watcher.scan_once() == []

    shutil.copy(samples_dir / "invoice_01_northwind.pdf", settings.input_dir)
    first = watcher.scan_once()
    assert [inv.source_file for inv in first] == ["invoice_01_northwind.pdf"]
    assert watcher.scan_once() == []  # unchanged file is not re-processed

    shutil.copy(samples_dir / "invoice_03_bluepeak.pdf", settings.input_dir)
    assert len(watcher.scan_once()) == 1
    assert _report(settings)["count"] == 2
    assert (settings.output_dir / settings.excel_filename).exists()


def test_watcher_skip_existing_and_removal(samples_dir: Path, settings: Settings) -> None:
    settings.input_dir.mkdir(parents=True)
    shutil.copy(samples_dir / "invoice_01_northwind.pdf", settings.input_dir)
    watcher = FolderWatcher(settings, skip_existing=True)
    assert watcher.scan_once() == []

    shutil.copy(samples_dir / "invoice_07_kestrel.pdf", settings.input_dir)
    assert len(watcher.scan_once()) == 1
    (settings.input_dir / "invoice_07_kestrel.pdf").unlink()
    watcher.scan_once()
    assert _report(settings)["count"] == 0


def test_watcher_waits_for_file_to_settle(samples_dir: Path, settings: Settings) -> None:
    settings.watch_settle_seconds = 60
    watcher = FolderWatcher(settings)
    shutil.copy(samples_dir / "invoice_01_northwind.pdf", settings.input_dir)
    (settings.input_dir / "invoice_01_northwind.pdf").touch()
    assert watcher.pending() == []


def test_watcher_records_failures(settings: Settings) -> None:
    watcher = FolderWatcher(settings)
    (settings.input_dir / "broken.pdf").write_bytes(b"not really a pdf")
    assert watcher.scan_once() == []
    assert "broken.pdf" in watcher.failures


def test_watcher_run_loop_once(samples_dir: Path, settings: Settings) -> None:
    watcher = FolderWatcher(settings)
    shutil.copy(samples_dir / "invoice_05_alderfinch.pdf", settings.input_dir)
    watcher.run(max_iterations=1)
    assert "invoice_05_alderfinch.pdf" in watcher.results
