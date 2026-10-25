import ctypes
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock
from types import SimpleNamespace

from treesize.scanner import ScanNode, extension_summary, iter_nodes, largest_files, scan
from treesize import scanner


class WindowsAllocationTests(unittest.TestCase):
    """Exercise Win32 contracts on all hosts, including Linux CI."""

    def setUp(self):
        self.create = mock.Mock(return_value=123)
        self.info = mock.Mock()
        self.close = mock.Mock(return_value=1)
        self.compressed = mock.Mock(return_value=17)
        patcher = mock.patch.multiple(
            scanner, _create_file=self.create, _get_file_info=self.info,
            _close_handle=self.close, _get_compressed_size=self.compressed,
            _get_last_error=mock.Mock(return_value=5), _set_last_error=mock.Mock(),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_structure_layout_matches_windows(self):
        self.assertEqual(ctypes.sizeof(scanner._FileStandardInfo), 24)
        self.assertEqual(scanner._FileStandardInfo.NumberOfLinks.offset, 16)
        self.assertEqual(scanner._FileStandardInfo.DeletePending.offset, 20)
        self.assertEqual(scanner._FileStandardInfo.Directory.offset, 21)

    def test_ordinary_file_uses_actual_allocation_not_logical_size(self):
        for allocated in (4096, 0):
            with self.subTest(allocated=allocated):
                def fill_info(handle, info_class, buffer, length):
                    self.assertEqual((handle, info_class, length), (123, 1, 24))
                    info = ctypes.cast(buffer, ctypes.POINTER(scanner._FileStandardInfo)).contents
                    info.AllocationSize = allocated
                    info.EndOfFile = 19
                    return 1
                self.info.side_effect = fill_info
                self.assertEqual(scanner._allocated_bytes("file.txt", SimpleNamespace(st_size=19, st_file_attributes=0)), allocated)
        self.compressed.assert_not_called()
        self.assertEqual(self.close.call_args_list, [mock.call(123), mock.call(123)])
        args = self.create.call_args.args
        self.assertEqual(args[1:], (0, 7, None, 3, 0x00200000, None))

    def test_compressed_and_sparse_use_storage_size_and_high_dword(self):
        for attributes in (0x800, 0x200, 0xA00):
            with self.subTest(attributes=attributes):
                def compressed_size(path, high_buffer):
                    ctypes.cast(high_buffer, ctypes.POINTER(ctypes.c_uint32)).contents.value = 2
                    return 17
                self.compressed.side_effect = compressed_size
                self.assertEqual(scanner._allocated_bytes("data", SimpleNamespace(st_size=99999, st_file_attributes=attributes)), (2 << 32) | 17)
        self.create.assert_not_called()
        self.info.assert_not_called()
        self.close.assert_not_called()

    def test_sparse_zero_allocation_is_valid(self):
        self.compressed.return_value = 0
        self.assertEqual(scanner._allocated_bytes("data", SimpleNamespace(st_size=99999, st_file_attributes=0x200)), 0)

    def test_compressed_failure_is_reported(self):
        self.compressed.return_value = 0xFFFFFFFF
        with self.assertRaises(OSError):
            scanner._allocated_bytes("data", SimpleNamespace(st_size=99999, st_file_attributes=0x800))
        self.close.assert_not_called()

    def test_compressed_sentinel_with_no_error_is_valid_size(self):
        self.compressed.return_value = 0xFFFFFFFF
        with mock.patch.object(scanner, "_get_last_error", return_value=0):
            self.assertEqual(scanner._allocated_bytes("data", SimpleNamespace(st_size=99999, st_file_attributes=0x800)), 0xFFFFFFFF)

    def test_open_failure_never_closes_invalid_handle(self):
        for invalid in (None, 0, scanner._INVALID_HANDLE_VALUE):
            with self.subTest(invalid=invalid):
                self.create.return_value = invalid
                with self.assertRaises(OSError):
                    scanner._allocated_bytes("file", SimpleNamespace(st_size=19, st_file_attributes=0))
        self.info.assert_not_called()
        self.close.assert_not_called()

    def test_info_failure_closes_handle_and_raises(self):
        self.info.return_value = 0
        with self.assertRaises(OSError):
            scanner._allocated_bytes("file", SimpleNamespace(st_size=19, st_file_attributes=0))
        self.close.assert_called_once_with(123)

    def test_unexpected_query_exception_still_closes_handle(self):
        self.info.side_effect = RuntimeError("test failure")
        with self.assertRaises(RuntimeError):
            scanner._allocated_bytes("file", SimpleNamespace(st_size=19, st_file_attributes=0))
        self.close.assert_called_once_with(123)


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

    @unittest.skipUnless(os.name == "nt", "Real Windows allocation assertion")
    def test_windows_ordinary_file_allocation_is_cluster_rounded(self):
        # Large enough not to be NTFS-resident and intentionally not a cluster
        # multiple; do not assume all Windows volumes use 4 KiB clusters.
        path = self.root / "ordinary.bin"
        path.write_bytes(b"x" * 65537)
        metadata = path.stat()
        if metadata.st_file_attributes & (0x800 | 0x200):
            self.skipTest("Temporary directory inherits compression/sparse attributes")
        sectors_per_cluster = ctypes.c_uint32()
        bytes_per_sector = ctypes.c_uint32()
        free_clusters = ctypes.c_uint32()
        total_clusters = ctypes.c_uint32()
        get_disk_space = ctypes.WinDLL("kernel32", use_last_error=True).GetDiskFreeSpaceW
        get_disk_space.argtypes = [ctypes.c_wchar_p] + [ctypes.POINTER(ctypes.c_uint32)] * 4
        get_disk_space.restype = ctypes.c_int
        if not get_disk_space(path.anchor, ctypes.byref(sectors_per_cluster), ctypes.byref(bytes_per_sector), ctypes.byref(free_clusters), ctypes.byref(total_clusters)):
            self.skipTest("Volume cluster size is unavailable")
        cluster = sectors_per_cluster.value * bytes_per_sector.value
        result = scan(str(self.root))
        self.assertEqual(result.root.size, 65537)
        self.assertEqual(result.root.allocated, ((65537 + cluster - 1) // cluster) * cluster)


if __name__ == "__main__":
    unittest.main()
