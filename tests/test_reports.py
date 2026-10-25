import csv
import json
import tempfile
import unittest
from pathlib import Path

from treesize.reports import export_csv, export_json, format_bytes
from treesize.scanner import ScanNode


class ReportsTests(unittest.TestCase):
    def test_csv_preserves_unicode_quotes_and_escapes_formulas(self):
        root = ScanNode('=SUM(A1)', '한글,폴더', True)
        root.children.append(ScanNode('/tmp/한글,".txt', '한글,".txt', False, size=1024, parent=root))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "output.csv"
            export_csv(root, str(path), cancelled=True)
            self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"))
            with path.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.reader(stream))
            self.assertEqual(rows[1][0], "'=SUM(A1)")
            self.assertEqual(rows[2][0], '/tmp/한글,".txt')
            self.assertEqual(rows[1][-1], "True")

    def test_json_flat_export_handles_deep_tree(self):
        root = ScanNode('/root', 'root', True)
        cursor = root
        for i in range(1200):
            child = ScanNode(f"/root/{i}", str(i), True, parent=cursor)
            cursor.children.append(child); cursor = child
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "output.json"
            export_json(root, str(path), cancelled=False)
            result = json.loads(path.read_text())
            self.assertEqual(len(result["nodes"]), 1201)
            self.assertFalse(result["partial"])

    def test_byte_units(self):
        self.assertEqual(format_bytes(1024), "1.00 KiB")
        self.assertEqual(format_bytes(0), "0 B")
