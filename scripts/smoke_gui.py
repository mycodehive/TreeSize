"""Headless integration check used before Windows release packaging."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from treesize.app import MainWindow, STYLE


def main():
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion"); app.setStyleSheet(STYLE)
    window = MainWindow(automatic_updates=False)
    window.show()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / "Documents").mkdir(); (root / "Video").mkdir()
        (root / "Documents" / "report.txt").write_bytes(b"x" * 2048)
        (root / "Video" / "sample.mp4").write_bytes(b"x" * 8192)
        window.start_scan(str(root))
        deadline = time.monotonic() + 15
        while (window.scan_task is not None or window.jobs) and time.monotonic() < deadline:
            app.processEvents(); QTest.qWait(10)
        assert not window.jobs, "Worker did not finish"
        assert window.result is not None, "Scan produced no result"
        assert window.result.root.size == 10240
        assert window.result.root.files == 2
        assert window.large_table.rowCount() == 2
        assert window.extension_table.rowCount() == 2
        window.select_node(window.result.root.children[0])
        assert window.selected.name in {"Documents", "Video"}
        window.tree.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        app.processEvents()
        window.search.setText("report")
        QTest.qWait(350); app.processEvents()
        assert window.proxy.rowCount() == 1
        window.search.clear(); app.processEvents()
        output = os.environ.get("TREESIZE_SCREENSHOT")
        if output:
            window.select_node(window.result.root)
            app.processEvents(); window.grab().save(output)
    window.close(); app.processEvents()
    print("GUI smoke passed: worker scan, totals, tables, selection, sort, filter, shutdown")


if __name__ == "__main__":
    main()
