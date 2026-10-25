import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from treesize.scanner import ScanNode, extension_summary, iter_nodes, largest_files, scan


class ScannerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_totals_extensions_and_largest(self):
        (self.root / "one").mkdir()
        (self.root / "one" / "empty").mkdir()
        (self.root / "one" / "a.TXT").write_bytes(b"a" * 11)
        (self.root / "b.txt").write_bytes(b"b" * 19)
        (self.root / "README").write_bytes(b"c" * 3)
        result = scan(str(self.root))
        self.assertEqual((result.root.size, result.root.files, result.root.folders), (33, 3, 2))
        self.assertFalse(result.cancelled)
        self.assertFalse(result.errors)
        self.assertEqual([node.size for node in largest_files(result.root, 2)], [19, 11])
        self.assertEqual(largest_files(result.root, 0), [])
        summary = extension_summary(result.root)
        self.assertEqual((summary[0]["extension"], summary[0]["size"], summary[0]["files"]), (".txt", 30, 2))
        self.assertEqual(summary[1]["extension"], "(no extension)")
        self.assertGreaterEqual(result.root.allocated, 0)
        for node in iter_nodes(result.root):
            for child in node.children:
                self.assertIs(child.parent, node)

    def test_symlinks_are_skipped_and_root_symlink_rejected(self):
        (self.root / "folder").mkdir()
        (self.root / "folder" / "data").write_bytes(b"hello")
        try:
            (self.root / "folder" / "loop").symlink_to(self.root, target_is_directory=True)
            (self.root / "link").symlink_to(self.root / "folder", target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation is unavailable")
        result = scan(str(self.root))
        self.assertEqual(result.root.size, 5)
        self.assertEqual(result.root.files, 1)
        self.assertEqual(result.skipped, 2)
        with self.assertRaises(ValueError):
            scan(str(self.root / "link"))

    def test_missing_and_file_root(self):
        with self.assertRaises(FileNotFoundError):
            scan(str(self.root / "missing"))
        target = self.root / "file"
        target.touch()
        with self.assertRaises(NotADirectoryError):
            scan(str(target))

    def test_precancelled_and_progress(self):
        (self.root / "data").write_bytes(b"hello")
        event = threading.Event()
        updates = []
        def progress(update):
            updates.append(update)
            event.set()
        result = scan(str(self.root), event, progress)
        self.assertTrue(result.cancelled)
        self.assertEqual(result.root.size, 0)
        self.assertEqual(result.root.files, 0)
        self.assertTrue(result.root.skipped)
        self.assertTrue(all({"files", "folders", "bytes", "path", "elapsed"} <= update.keys() for update in updates))

    def test_cancellation_keeps_partial_aggregate(self):
        (self.root / "pending").mkdir()
        for index in range(3):
            (self.root / f"file{index}").write_bytes(b"hello")
        event = threading.Event()
        from treesize import scanner
        allocation = scanner._allocated_bytes
        calls = []
        def cancelling_allocation(path, metadata):
            calls.append(path)
            event.set()
            return allocation(path, metadata)
        with mock.patch.object(scanner, "_allocated_bytes", cancelling_allocation):
            result = scan(str(self.root), event)
        self.assertTrue(result.cancelled)
        self.assertEqual(result.root.size, 5)
        self.assertEqual(result.root.files, 1)
        self.assertEqual(sum(node.size for node in largest_files(result.root)), result.root.size)

    def test_permission_failure_continues(self):
        (self.root / "denied").mkdir()
        (self.root / "data").write_bytes(b"hello")
        original = os.scandir
        def guarded(path):
            if os.fspath(path) == str(self.root / "denied"):
                raise PermissionError("denied by test")
            return original(path)
        with mock.patch("treesize.scanner.os.scandir", side_effect=guarded):
            result = scan(str(self.root))
        self.assertEqual(result.root.size, 5)
        self.assertEqual(len(result.errors), 1)
        self.assertIn("denied", result.errors[0][1])
        self.assertEqual(result.skipped, 1)

    def test_deep_filesystem_and_nonrecursive_helpers(self):
        cursor = self.root
        for _ in range(120):
            cursor = cursor / "d"
            cursor.mkdir()
        (cursor / "data").write_bytes(b"abc")
        result = scan(str(self.root))
        self.assertEqual(result.root.folders, 120)
        self.assertEqual(result.root.size, 3)
        synthetic = ScanNode("/", "root", True)
        cursor_node = synthetic
        for index in range(2000):
            child = ScanNode(str(index), str(index), True, parent=cursor_node)
            cursor_node.children.append(child)
            cursor_node = child
        self.assertEqual(sum(1 for _ in iter_nodes(synthetic)), 2001)

    @unittest.skipIf(os.name == "nt", "POSIX allocation assertion")
    def test_sparse_file_logical_and_allocated_are_distinct(self):
        path = self.root / "sparse.bin"
        with path.open("wb") as stream:
            stream.seek(8 * 1024 * 1024)
            stream.write(b"x")
        result = scan(str(self.root))
        self.assertEqual(result.root.size, 8 * 1024 * 1024 + 1)
        self.assertEqual(result.root.allocated, path.stat().st_blocks * 512)


if __name__ == "__main__":
    unittest.main()
