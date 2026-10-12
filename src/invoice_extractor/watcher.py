"""Watch-folder mode: poll a directory and process new or changed invoice PDFs.

Polling (rather than OS file-system events) is used deliberately: it behaves the
same on Windows, macOS, Linux, network shares and synced folders (OneDrive,
Dropbox), where native events are often unreliable.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .config import Settings
from .exporters import export_excel, export_json
from .extractor import ExtractionError
from .models import Invoice
from .pipeline import process_file

log = logging.getLogger(__name__)

Signature = tuple[int, int]  # (mtime_ns, size)


@dataclass
class FolderWatcher:
    settings: Settings
    skip_existing: bool = False
    clock: Callable[[], float] = time.time
    results: dict[str, Invoice] = field(default_factory=dict)
    failures: dict[str, str] = field(default_factory=dict)
    _seen: dict[str, Signature] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.settings.input_dir.mkdir(parents=True, exist_ok=True)
        if self.skip_existing:
            for path in self._pdfs():
                self._seen[path.name] = self._signature(path)
            log.info("ignoring %d existing PDF(s)", len(self._seen))

    def _pdfs(self) -> list[Path]:
        return sorted(p for p in self.settings.input_dir.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")

    @staticmethod
    def _signature(path: Path) -> Signature:
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_size

    def _is_settled(self, path: Path) -> bool:
        """Skip files that are still being written/copied."""
        return self.clock() - path.stat().st_mtime >= self.settings.watch_settle_seconds

    def pending(self) -> list[Path]:
        ready: list[Path] = []
        for path in self._pdfs():
            if self._seen.get(path.name) == self._signature(path):
                continue
            if self._is_settled(path):
                ready.append(path)
        return ready

    def scan_once(self) -> list[Invoice]:
        """Process every pending file once; re-export the combined report if anything changed."""
        processed: list[Invoice] = []
        for path in self.pending():
            signature = self._signature(path)
            try:
                invoice = process_file(path, self.settings)
            except ExtractionError as exc:
                log.error("%s", exc)
                self.failures[path.name] = str(exc)
            except Exception as exc:  # noqa: BLE001 - keep watching after a bad file
                log.exception("failed to process %s", path.name)
                self.failures[path.name] = f"{type(exc).__name__}: {exc}"
            else:
                self.results[path.name] = invoice
                self.failures.pop(path.name, None)
                processed.append(invoice)
            self._seen[path.name] = signature

        # Forget files that were deleted from the folder.
        present = {p.name for p in self._pdfs()}
        removed = [name for name in self._seen if name not in present]
        for name in removed:
            self._seen.pop(name, None)
            self.results.pop(name, None)

        if processed or removed:
            self.export()
        return processed

    def export(self) -> None:
        invoices = [self.results[name] for name in sorted(self.results)]
        export_excel(invoices, self.settings.output_dir / self.settings.excel_filename)
        export_json(invoices, self.settings.output_dir / self.settings.json_filename)

    def run(self, max_iterations: int | None = None) -> None:
        log.info("watching %s every %.1fs (Ctrl+C to stop)", self.settings.input_dir.resolve(),
                 self.settings.watch_interval)
        iterations = 0
        try:
            while max_iterations is None or iterations < max_iterations:
                new = self.scan_once()
                if new:
                    log.info("processed %d new/changed invoice(s); %d total", len(new), len(self.results))
                iterations += 1
                if max_iterations is None or iterations < max_iterations:
                    time.sleep(self.settings.watch_interval)
        except KeyboardInterrupt:
            log.info("stopped watching")
