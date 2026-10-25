import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt, QPersistentModelIndex
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from treesize.app import MainWindow
from treesize.models import DiskTreeModel
from treesize.scanner import ScanNode
from treesize.settings import Settings
from treesize.updater import UPDATE_INTERVAL_SECONDS, Release
from treesize.treemap import partition


APP = QApplication.instance() or QApplication([])


class GuiTests(unittest.TestCase):
    def test_model_parent_and_selection_survive_sort(self):
        root = ScanNode('/r', 'root', True)
        a = ScanNode('/r/a', 'a', True, size=10, parent=root)
        b = ScanNode('/r/b', 'b', True, size=20, parent=root)
        child = ScanNode('/r/a/c', 'c', False, parent=a)
        a.children = [child]; root.children = [a, b]
        model = DiskTreeModel(root)
        index = model.index_for_node(a)
        persistent = QPersistentModelIndex(index)
        self.assertIs(model.parent(model.index_for_node(child)).internalPointer(), a)
        self.assertEqual(model.index_for_node(a, 1).data(Qt.ItemDataRole.UserRole + 1), 10)
        model.sort(0, Qt.SortOrder.AscendingOrder)
        self.assertEqual(persistent.row(), 0)
        self.assertIs(model.index(persistent.row(), 0, model.index(0, 0)).internalPointer(), a)
        self.assertFalse(model.index(1, 0).isValid())

    def test_four_hour_timer_and_startup_check(self):
        with patch('treesize.app.load_settings', return_value=Settings()), patch('treesize.app.QTimer.singleShot') as startup:
            window = MainWindow()
            self.assertEqual(window.update_timer.interval(), 4 * 60 * 60 * 1000)
            self.assertTrue(window.update_timer.isActive())
            self.assertEqual(startup.call_args.args[0], 1200)
            window.close()

    def test_auto_updates_can_be_disabled(self):
        with patch('treesize.app.load_settings', return_value=Settings(check_updates=False)):
            window = MainWindow()
            self.assertFalse(window.update_timer.isActive())
            window.check_updates(False)
            self.assertIsNone(window.update_task)
            window.close()

    def test_new_release_shows_banner_without_installing(self):
        release = Release("1.1.0", "v1.1.0", "test", "https://github.com/mycodehive/TreeSize/releases/tag/v1.1.0", "installer", "url", "sums")
        window = MainWindow(automatic_updates=False)
        window.settings.check_updates = True
        with patch.object(window, '_updater') as updater:
            updater.return_value.check.return_value = release
            window.check_updates(False)
            for _ in range(100):
                APP.processEvents(); QTest.qWait(5)
                if not window.jobs:
                    break
        self.assertIs(window.release, release)
        self.assertFalse(window.banner.isHidden())
        self.assertIn("1.1.0", window.banner_label.text())
        self.assertIsNone(window.download_task)
        window.close()

    def test_treemap_area_represents_bytes(self):
        rectangles = partition([("large", 75), ("small", 25)], 0, 0, 100, 100)
        areas = {item[0]: rect[2] * rect[3] for item, rect in rectangles}
        self.assertEqual(areas, {"large": 7500, "small": 2500})


if __name__ == '__main__':
    unittest.main()
