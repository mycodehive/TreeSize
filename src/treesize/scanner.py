"""Metadata-only, cancellable disk scanner.

Hard links are counted once per directory entry, as are sizes across mounted
filesystems. Reparse points, symbolic links and offline/cloud placeholders are
not followed. Directory metadata itself is not included in allocated bytes.
The result is a point-in-time best effort: files may change during a scan.
"""

from __future__ import annotations

import ctypes
import heapq
import os
import stat
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Iterator


@dataclass(slots=True, eq=False)
class ScanNode:
    path: str
    name: str
    is_dir: bool
    size: int = 0
    allocated: int = 0
    files: int = 0
    folders: int = 0
    modified: float = 0
    children: list[ScanNode] = field(default_factory=list)
    parent: ScanNode | None = field(default=None, repr=False)
    error: str = ""
    skipped: bool = False


@dataclass(slots=True)
class ScanResult:
    root: ScanNode
    elapsed: float
    cancelled: bool
    errors: list[tuple[str, str]]
    skipped: int


_MAX_ERRORS = 1000
_REPARSE_POINT = 0x400
_CLOUD_ATTRIBUTES = 0x1000 | 0x40000 | 0x400000
_get_compressed_size = None
if os.name == "nt":
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _get_compressed_size = _kernel32.GetCompressedFileSizeW
    _get_compressed_size.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    _get_compressed_size.restype = wintypes.DWORD


def _native_path(path: str) -> str:
    if path.startswith("\\\\?\\"):
        return path
    if path.startswith("\\\\"):
        return "\\\\?\\UNC\\" + path[2:]
    return "\\\\?\\" + os.path.abspath(path)


def _allocated_bytes(path: str, metadata: os.stat_result) -> int:
    if _get_compressed_size is not None:
        high = wintypes.DWORD()
        ctypes.set_last_error(0)
        low = _get_compressed_size(_native_path(path), ctypes.byref(high))
        error = ctypes.get_last_error()
        if low == 0xFFFFFFFF and error:
            raise OSError(error, ctypes.FormatError(error), path)
        return (high.value << 32) | low
    return getattr(metadata, "st_blocks", (metadata.st_size + 511) // 512) * 512


def iter_nodes(root: ScanNode) -> Iterator[ScanNode]:
    """Preorder iteration without Python recursion depth limits."""
    pending = [root]
    while pending:
        node = pending.pop()
        yield node
        pending.extend(reversed(node.children))


def largest_files(root: ScanNode, limit: int = 100) -> list[ScanNode]:
    return heapq.nlargest(
        max(0, limit),
        (node for node in iter_nodes(root) if not node.is_dir and not node.skipped),
        key=lambda node: node.size,
    )


def extension_summary(root: ScanNode) -> list[dict]:
    groups: dict[str, dict] = {}
    for node in iter_nodes(root):
        if node.is_dir or node.skipped or not node.files:
            continue
        extension = os.path.splitext(node.name)[1].lower() or "(no extension)"
        group = groups.setdefault(
            extension, {"extension": extension, "size": 0, "allocated": 0, "files": 0}
        )
        group["size"] += node.size
        group["allocated"] += node.allocated
        group["files"] += 1
    return sorted(groups.values(), key=lambda group: (-group["size"], group["extension"]))


def scan(
    path: str,
    cancel: threading.Event | None = None,
    progress: Callable[[dict], None] | None = None,
) -> ScanResult:
    """Scan a directory without reading file contents.

    Permission errors are recorded and scanning continues. At most 1,000 detailed
    errors are retained, followed by a summary if additional errors occurred.
    Cancelling returns a consistent aggregate of the entries already inspected;
    directories discovered but not visited have ``skipped=True``. Progress is
    emitted initially, at most every 0.2 seconds, and once on completion.
    """
    started = time.monotonic()
    cancel = cancel if cancel is not None else threading.Event()
    path = os.path.abspath(os.path.expanduser(os.fspath(path)))
    root_stat = os.stat(path, follow_symlinks=False)
    attributes = getattr(root_stat, "st_file_attributes", 0)
    if stat.S_ISLNK(root_stat.st_mode) or attributes & (_REPARSE_POINT | _CLOUD_ATTRIBUTES):
        raise ValueError("Select a real local directory, not a link or cloud placeholder.")
    if not stat.S_ISDIR(root_stat.st_mode):
        raise NotADirectoryError(path)
    root = ScanNode(path, os.path.basename(path.rstrip(os.sep)) or path, True,
                    modified=root_stat.st_mtime)
    errors: list[tuple[str, str]] = []
    error_count = 0
    skipped = 0
    counts = {"files": 0, "folders": 0, "bytes": 0}
    next_report = started + 0.2

    def record_error(node: ScanNode, exc: OSError) -> None:
        nonlocal error_count
        node.error = str(exc)
        error_count += 1
        if len(errors) < _MAX_ERRORS:
            errors.append((node.path, node.error))

    def report(current_path: str, force: bool = False) -> None:
        nonlocal next_report
        now = time.monotonic()
        if progress is not None and (force or now >= next_report):
            progress({**counts, "path": current_path, "elapsed": now - started})
            next_report = now + 0.2

    report(path, True)
    pending = [root]
    while pending and not cancel.is_set():
        directory = pending.pop()
        try:
            with os.scandir(directory.path) as entries:
                for entry in entries:
                    if cancel.is_set():
                        break
                    child = ScanNode(entry.path, entry.name, False, parent=directory)
                    directory.children.append(child)
                    try:
                        metadata = entry.stat(follow_symlinks=False)
                        attributes = getattr(metadata, "st_file_attributes", 0)
                        child.is_dir = stat.S_ISDIR(metadata.st_mode)
                        child.modified = metadata.st_mtime
                        if child.is_dir:
                            counts["folders"] += 1
                        if stat.S_ISLNK(metadata.st_mode) or attributes & (_REPARSE_POINT | _CLOUD_ATTRIBUTES):
                            child.skipped = True
                            skipped += 1
                        elif child.is_dir:
                            pending.append(child)
                        elif stat.S_ISREG(metadata.st_mode):
                            child.size = metadata.st_size
                            child.files = 1
                            counts["files"] += 1
                            counts["bytes"] += child.size
                            try:
                                child.allocated = _allocated_bytes(child.path, metadata)
                            except OSError as exc:
                                # Logical size remains useful even when allocation
                                # cannot be read; zero never masquerades as exact.
                                child.allocated = child.size
                                record_error(child, exc)
                        else:
                            child.skipped = True
                            skipped += 1
                    except OSError as exc:
                        child.skipped = True
                        skipped += 1
                        record_error(child, exc)
                    report(entry.path)
        except OSError as exc:
            record_error(directory, exc)
            directory.skipped = True
            skipped += 1
        report(directory.path)

    if cancel.is_set():
        for directory in pending:
            directory.skipped = True
            skipped += 1

    # Postorder aggregation also works after cancellation, permission failures or
    # with arbitrarily deep directory trees. Directory counts exclude the node
    # itself and include discovered skipped directory entries.
    frames = [(root, False)]
    while frames:
        node, visited = frames.pop()
        if not node.is_dir:
            continue
        if not visited:
            frames.append((node, True))
            frames.extend((child, False) for child in node.children if child.is_dir)
        else:
            node.size = sum(child.size for child in node.children)
            node.allocated = sum(child.allocated for child in node.children)
            node.files = sum(child.files for child in node.children)
            node.folders = sum(child.folders + int(child.is_dir) for child in node.children)
    if error_count > _MAX_ERRORS:
        errors.append((path, f"{error_count - _MAX_ERRORS:,} additional errors omitted."))
    elapsed = time.monotonic() - started
    report(path, True)
    return ScanResult(root, elapsed, cancel.is_set(), errors, skipped)
