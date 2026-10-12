"""Command-line interface.

Examples::

    python -m invoice_extractor extract samples/ --out output
    python -m invoice_extractor extract samples/invoice_03_bluepeak.pdf --format json
    python -m invoice_extractor watch --input inbox --out output
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .config import Settings, load_settings
from .pipeline import export_all, process_files
from .watcher import FolderWatcher

log = logging.getLogger("invoice_extractor")


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="invoice-extractor", description="Extract structured data from invoice PDFs.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", type=Path, help="path to config.yaml (default: ./config.yaml)")
    parser.add_argument("--log-level", help="override log level (DEBUG, INFO, WARNING...)")
    sub = parser.add_subparsers(dest="command", required=True)

    ext = sub.add_parser("extract", help="extract one or more PDFs / folders")
    ext.add_argument("paths", nargs="*", type=Path, help="PDF files or folders (default: input_dir from config)")
    ext.add_argument("--out", type=Path, help="output directory")
    ext.add_argument("--format", choices=("excel", "json", "both"), default="both")
    ext.add_argument("--strict", action="store_true", help="exit with code 2 if any invoice fails validation")

    watch = sub.add_parser("watch", help="poll a folder and process new PDFs as they arrive")
    watch.add_argument("--input", type=Path, help="folder to watch (default: input_dir from config)")
    watch.add_argument("--out", type=Path, help="output directory")
    watch.add_argument("--interval", type=float, help="seconds between scans")
    watch.add_argument("--skip-existing", action="store_true", help="ignore PDFs already in the folder at start-up")
    watch.add_argument("--once", action="store_true", help="run a single scan and exit")
    return parser


def _cmd_extract(args: argparse.Namespace, settings: Settings) -> int:
    paths = args.paths or [settings.input_dir]
    invoices, failures = process_files(paths, settings)
    if not invoices and not failures:
        log.error("no PDF files found in %s", ", ".join(map(str, paths)))
        return 1
    formats = ("excel", "json") if args.format == "both" else (args.format,)
    written = export_all(invoices, settings, formats) if invoices else []

    valid = sum(inv.validation.is_valid for inv in invoices)
    print(f"\nProcessed {len(invoices)} invoice(s): {valid} valid, {len(invoices) - valid} invalid, "
          f"{len(failures)} failed to parse.")
    for inv in invoices:
        status = "OK " if inv.validation.is_valid else "BAD"
        print(f"  [{status}] {inv.source_file:<32} {inv.invoice_number or '?':<14} "
              f"{inv.vendor or '?':<30} {inv.total} {inv.currency}")
    for path in written:
        print(f"  -> {path}")
    if failures:
        return 1
    return 2 if args.strict and valid < len(invoices) else 0


def _cmd_watch(args: argparse.Namespace, settings: Settings) -> int:
    if args.input:
        settings.input_dir = args.input
    if args.interval:
        settings.watch_interval = args.interval
    watcher = FolderWatcher(settings, skip_existing=args.skip_existing)
    watcher.run(max_iterations=1 if args.once else None)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings(args.config)
    if args.log_level:
        settings.log_level = args.log_level
    configure_logging(settings.log_level)
    if getattr(args, "out", None):
        settings.output_dir = args.out
    if args.command == "extract":
        return _cmd_extract(args, settings)
    return _cmd_watch(args, settings)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
