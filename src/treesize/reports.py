"""Streaming report export. No file contents are read or transmitted."""
from __future__ import annotations

import csv
import json
import os
import tempfile
from pathlib import Path

from .scanner import iter_nodes


def format_bytes(value: int) -> str:
    number = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if abs(number) < 1024 or unit == "PiB":
            return f"{number:,.0f} {unit}" if unit == "B" else f"{number:,.2f} {unit}"
        number /= 1024
    return str(value)


def _csv_text(value: str) -> str:
    # Excel must not interpret user-controlled filenames as formulas.
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def export_csv(root, destination: str, cancelled: bool = False) -> None:
    """Atomic UTF-8 BOM CSV, safe to open in Korean Excel."""
    path = Path(destination)
    fd, temporary = tempfile.mkstemp(prefix=".treesize-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["path", "type", "bytes", "allocated_bytes", "files", "folders", "modified_unix", "status", "scan_partial"])
            for node in iter_nodes(root):
                writer.writerow([_csv_text(node.path), "folder" if node.is_dir else "file", node.size,
                                 node.allocated, node.files, node.folders, node.modified,
                                 _csv_text(node.error or ("skipped" if node.skipped else "ok")), cancelled])
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def export_json(root, destination: str, cancelled: bool = False) -> None:
    """Flat streaming JSON avoids recursion limits on very deep folder trees."""
    path = Path(destination)
    fd, temporary = tempfile.mkstemp(prefix=".treesize-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write('{"format":1,"partial":' + str(cancelled).lower() + ',"nodes":[')
            first = True
            for node in iter_nodes(root):
                if not first:
                    stream.write(",\n")
                first = False
                json.dump({"path": node.path, "directory": node.is_dir, "bytes": node.size,
                           "allocated_bytes": node.allocated, "files": node.files, "folders": node.folders,
                           "modified": node.modified, "skipped": node.skipped, "error": node.error},
                          stream, ensure_ascii=True)
            stream.write("]}")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
