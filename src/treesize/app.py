"""Native Qt desktop interface. Scanning, exports and networking use workers."""
from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QThread, QTimer, QUrl, QStorageInfo, QSortFilterProxyModel
from PySide6.QtGui import QAction, QColor, QDesktopServices, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QLineEdit, QSplitter, QTreeView, QHeaderView, QTabWidget, QTableWidget,
    QTableWidgetItem, QFileDialog, QMessageBox, QProgressBar, QMenu, QDialog,
    QDialogButtonBox, QFormLayout, QCheckBox, QPlainTextEdit, QSystemTrayIcon, QAbstractItemView,
)

from . import APP_NAME, VERSION
from .scanner import scan, largest_files, extension_summary
from .reports import format_bytes, export_csv, export_json
from .models import DiskTreeModel, UsageDelegate
from .treemap import Treemap
from .settings import Settings, load_settings, save_settings, get_token, set_token, normalize_repository
from .updater import GitHubUpdater, UPDATE_INTERVAL_SECONDS

STYLE = """
QWidget { font-family: 'Segoe UI', 'Malgun Gothic', sans-serif; font-size: 13px; color: #29384e; }
QMainWindow, QDialog { background: #f4f7fc; }
QFrame#sidebar { background: #14263f; border: none; }
QFrame#sidebar QLabel { color: #a9bad0; background: transparent; }
QFrame#sidebar QLabel#brand { color: white; font-size: 21px; font-weight: 700; }
QFrame#sidebar QPushButton { background: #1e3553; color: #e0eafa; border: none; text-align: left; padding: 11px 14px; border-radius: 7px; }
QFrame#sidebar QPushButton:hover { background: #2a476c; }
QLabel#title { font-size: 25px; font-weight: 700; color: #152d4d; }
QLabel#muted { color: #7a8799; }
QLabel#cardValue { font-size: 24px; font-weight: 700; color: #17375e; }
QFrame#card { background: white; border: 1px solid #e1e7f0; border-radius: 10px; }
QPushButton { background: white; border: 1px solid #d8e1ed; border-radius: 6px; padding: 8px 13px; }
QPushButton:hover { background: #edf4ff; border-color: #a8c3ea; }
QPushButton:disabled { color: #a3adbb; background: #f2f4f7; }
QPushButton#primary { background: #3478e5; border-color: #3478e5; color: white; font-weight: 600; }
QPushButton#primary:hover { background: #2865c7; }
QLineEdit { background: white; border: 1px solid #d8e1ed; border-radius: 6px; padding: 9px 11px; }
QTreeView, QTableWidget, QPlainTextEdit { background: white; border: 1px solid #e1e7f0; border-radius: 5px; alternate-background-color: #f8faff; selection-background-color: #e1edff; selection-color: #173b69; }
QTreeView::item { height: 30px; }
QTreeView::item:hover { background: #edf4ff; }
QHeaderView::section { background: #f2f5fa; color: #64758c; border: none; border-bottom: 1px solid #e1e7f0; padding: 10px 8px; font-weight: 600; }
QTabWidget::pane { border: 1px solid #e1e7f0; background: white; border-radius: 6px; }
QTabBar::tab { padding: 10px 18px; color: #718199; }
QTabBar::tab:selected { color: #2467cd; background: white; border-bottom: 2px solid #3478e5; }
QProgressBar { background: #e6edf6; border: none; border-radius: 3px; min-height: 6px; max-height: 6px; }
QProgressBar::chunk { background: #3478e5; border-radius: 3px; }
QFrame#updateBanner { background: #e6f2ff; border: 1px solid #b9d6fb; border-radius: 8px; }
QStatusBar { background: #eaf0f8; color: #70829b; }
QSplitter::handle { background: #e6edf6; height: 7px; width: 7px; }
"""


class Task(QThread):
    completed = Signal(object)
    failed = Signal(str)
    progress = Signal(object)

    def __init__(self, function, parent=None):
        super().__init__(parent)
        self.function = function

    def run(self):
        try:
            self.completed.emit(self.function(self.progress.emit))
        except Exception as exc:
            self.failed.emit(str(exc))


def app_icon():
    pixmap = QPixmap(64, 64); pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(QColor("#3478e5")); painter.drawRoundedRect(0, 0, 64, 64, 14, 14)
    for x, y, w, h, color in [(12, 13, 23, 38, "#ffffff"), (39, 13, 13, 17, "#b7d3ff"), (39, 34, 13, 17, "#7db1ff")]:
        painter.setBrush(QColor(color)); painter.drawRoundedRect(x, y, w, h, 3, 3)
    painter.end()
    return QIcon(pixmap)


class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("설정 · 업데이트"); self.setMinimumWidth(530)
        self.saved = None
        layout = QVBoxLayout(self)
        title = QLabel("GitHub 업데이트 설정"); title.setObjectName("title"); layout.addWidget(title)
        form = QFormLayout()
        self.repository = QLineEdit(settings.repository)
        self.repository.setPlaceholderText("https://github.com/mycodehive/TreeSize")
        form.addRow("배포 저장소", self.repository)
        self.automatic = QCheckBox("실행 시 및 실행 중 4시간마다 확인"); self.automatic.setChecked(settings.check_updates)
        form.addRow("자동 확인", self.automatic)
        self.token = QLineEdit(); self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.token.setPlaceholderText("변경할 때만 입력 · 빈칸이면 기존 토큰 유지")
        form.addRow("GitHub 토큰", self.token)
        self.remove = QCheckBox("이 저장소에 저장된 토큰 삭제"); form.addRow("", self.remove)
        layout.addLayout(form)
        info = QLabel("공개 저장소는 토큰 없이 사용할 수 있습니다.\n비공개 저장소는 해당 저장소의 Contents: Read-only 토큰이 필요합니다.\n토큰은 Windows 자격 증명 관리자에 저장됩니다.\n새 버전은 알림 후 직접 설치를 선택할 수 있습니다.")
        info.setWordWrap(True); info.setObjectName("muted"); layout.addWidget(info)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def save(self):
        try:
            repository = normalize_repository(self.repository.text())
            if self.remove.isChecked() or self.token.text().strip():
                set_token(repository, "" if self.remove.isChecked() else self.token.text())
            settings = Settings(repository, self.automatic.isChecked())
            save_settings(settings)
            self.saved = settings
            self.accept()
        except Exception as exc:
            QMessageBox.warning(self, "설정을 저장할 수 없습니다", str(exc))


class MainWindow(QMainWindow):
    def __init__(self, automatic_updates=True):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} · v{VERSION}")
        self.setWindowIcon(app_icon()); self.resize(1440, 920); self.setMinimumSize(1040, 720)
        self.settings = load_settings()
        self.result = None; self.model = DiskTreeModel(); self.selected = None
        self.scan_task = None; self.update_task = None; self.download_task = None
        self.cancel_scan = threading.Event(); self.jobs = []; self.release = None
        self.notified_versions = set(); self.closing = False
        self._build_ui()
        self.update_timer = QTimer(self)
        self.update_timer.setInterval(UPDATE_INTERVAL_SECONDS * 1000)
        self.update_timer.timeout.connect(lambda: self.check_updates(False))
        if automatic_updates and self.settings.check_updates:
            self.update_timer.start()
            QTimer.singleShot(1200, lambda: self.check_updates(False))
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.setToolTip(APP_NAME); self.tray.show()
            self.tray.messageClicked.connect(self.showNormal)

    def _button(self, text, callback, primary=False):
        button = QPushButton(text); button.clicked.connect(callback)
        if primary:
            button.setObjectName("primary")
        return button

    def _build_ui(self):
        outer = QWidget(); row = QHBoxLayout(outer); row.setContentsMargins(0, 0, 0, 0); row.setSpacing(0)
        self.setCentralWidget(outer)
        sidebar = QFrame(); sidebar.setObjectName("sidebar"); sidebar.setFixedWidth(218)
        side = QVBoxLayout(sidebar); side.setContentsMargins(20, 28, 20, 18); side.setSpacing(12)
        brand = QLabel("▦  TreeSize"); brand.setObjectName("brand"); side.addWidget(brand)
        side.addWidget(QLabel("EXPLORER  /  DISK ANALYZER")); side.addSpacing(25)
        side.addWidget(QLabel("내 저장 공간"))
        for text, path in [("⌂   사용자 폴더", Path.home()), ("↓   다운로드", Path.home() / "Downloads")]:
            side.addWidget(self._button(text, lambda checked=False, p=str(path): self.start_scan(p)))
        side.addWidget(self._button("＋   폴더 선택", self.choose_folder)); side.addSpacing(16)
        side.addWidget(QLabel("연결된 드라이브"))
        seen = set()
        for storage in QStorageInfo.mountedVolumes():
            path = storage.rootPath()
            if storage.isValid() and storage.isReady() and path not in seen and (os.name == "nt" or path == "/"):
                seen.add(path)
                name = storage.displayName() or path
                button = self._button(f"▣   {name[:21]}", lambda checked=False, p=path: self.start_scan(p))
                button.setToolTip(f"{path}\n{format_bytes(storage.bytesAvailable())} 사용 가능")
                side.addWidget(button)
        side.addStretch()
        privacy = QLabel("로컬에서 안전하게 분석\n파일 내용은 읽지 않습니다"); privacy.setWordWrap(True); side.addWidget(privacy)
        side.addWidget(self._button("⚙   설정", self.show_settings))
        side.addWidget(QLabel(f"v{VERSION}  ·  Windows x64")); row.addWidget(sidebar)
        main = QWidget(); layout = QVBoxLayout(main); layout.setContentsMargins(26, 23, 26, 16); layout.setSpacing(14)
        row.addWidget(main, 1)
        header = QHBoxLayout()
        titles = QVBoxLayout(); title = QLabel("디스크 사용량 분석"); title.setObjectName("title"); titles.addWidget(title)
        subtitle = QLabel("큰 폴더부터 살펴보고, 저장 공간을 되찾으세요."); subtitle.setObjectName("muted"); titles.addWidget(subtitle)
        header.addLayout(titles); header.addStretch()
        self.update_button = self._button("업데이트 확인", lambda: self.check_updates(True)); header.addWidget(self.update_button)
        layout.addLayout(header)
        self.banner = QFrame(); self.banner.setObjectName("updateBanner")
        banner_row = QHBoxLayout(self.banner); self.banner_label = QLabel(); banner_row.addWidget(self.banner_label, 1)
        self.install_button = self._button("다운로드 및 설치", self.download_update, True); banner_row.addWidget(self.install_button)
        banner_row.addWidget(self._button("변경 내용", self.release_notes)); self.banner.hide(); layout.addWidget(self.banner)
        navigation = QHBoxLayout()
        self.path = QLineEdit(); self.path.setPlaceholderText("분석할 폴더 경로를 입력하거나 폴더를 선택하세요")
        self.path.returnPressed.connect(lambda: self.start_scan(self.path.text()))
        navigation.addWidget(self.path, 1)
        navigation.addWidget(self._button("폴더 선택", self.choose_folder))
        self.scan_button = self._button("분석 시작", lambda: self.start_scan(self.path.text()), True); navigation.addWidget(self.scan_button)
        self.stop_button = self._button("중지", self.stop_scan); self.stop_button.setEnabled(False); navigation.addWidget(self.stop_button)
        layout.addLayout(navigation)
        cards = QHBoxLayout(); self.metrics = []
        for label in ["파일 크기", "디스크 할당", "파일 / 폴더", "분석 시간"]:
            card = QFrame(); card.setObjectName("card"); content = QVBoxLayout(card); content.setContentsMargins(16, 12, 16, 12)
            small = QLabel(label); small.setObjectName("muted"); content.addWidget(small)
            value = QLabel("—"); value.setObjectName("cardValue"); content.addWidget(value); self.metrics.append(value); cards.addWidget(card)
        layout.addLayout(cards)
        self.capacity = QLabel("폴더 또는 드라이브를 선택하면 분석이 시작됩니다."); self.capacity.setObjectName("muted"); layout.addWidget(self.capacity)
        tools = QHBoxLayout()
        self.search = QLineEdit(); self.search.setPlaceholderText("파일·폴더 이름 검색  ·  폴더 트리 필터")
        self.search.setMaximumWidth(430); tools.addWidget(self.search); tools.addStretch()
        tools.addWidget(self._button("상위 폴더", self.navigate_up))
        self.export_button = self._button("결과 내보내기", self.export_report); self.export_button.setEnabled(False); tools.addWidget(self.export_button)
        layout.addLayout(tools)
        split = QSplitter(Qt.Orientation.Vertical)
        self.tree = QTreeView(); self.tree.setAlternatingRowColors(True); self.tree.setUniformRowHeights(True)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.proxy = QSortFilterProxyModel(self); self.proxy.setRecursiveFilteringEnabled(True)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive); self.proxy.setFilterKeyColumn(0)
        self.proxy.setSourceModel(self.model); self.tree.setModel(self.proxy)
        self.tree.setItemDelegate(UsageDelegate(self.tree)); self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(1, Qt.SortOrder.DescendingOrder)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu); self.tree.customContextMenuRequested.connect(self.context_menu)
        self.tree.selectionModel().currentChanged.connect(self.selection_changed)
        self._column_widths(); split.addWidget(self.tree)
        self.tabs = QTabWidget(); self.map = Treemap(); self.map.activated.connect(self.select_node)
        self.tabs.addTab(self.map, "공간 지도")
        self.large_table = self.make_table(["파일 이름", "크기", "위치"]); self.tabs.addTab(self.large_table, "대용량 파일 TOP 100")
        self.large_table.cellDoubleClicked.connect(self.open_large_location)
        self.extension_table = self.make_table(["확장자", "파일 크기", "디스크 할당", "파일 수"]); self.tabs.addTab(self.extension_table, "파일 유형")
        self.error_table = self.make_table(["경로", "내용"]); self.tabs.addTab(self.error_table, "접근 오류")
        split.addWidget(self.tabs); split.setSizes([430, 250]); layout.addWidget(split, 1)
        self.selection_label = QLabel("항목을 선택하면 해당 폴더의 공간 지도가 표시됩니다.")
        self.selection_label.setObjectName("muted"); self.selection_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.selection_label)
        self.progress_bar = QProgressBar(); self.progress_bar.setTextVisible(False); self.progress_bar.hide(); layout.addWidget(self.progress_bar)
        self.update_status = QLabel("GitHub 업데이트 대기"); self.statusBar().addPermanentWidget(self.update_status)
        self.statusBar().showMessage("준비됨 · 파일 크기는 1 KiB = 1,024 B 기준입니다.")
        self.search_timer = QTimer(self); self.search_timer.setSingleShot(True); self.search_timer.setInterval(300)
        self.search.textChanged.connect(lambda: self.search_timer.start())
        self.search_timer.timeout.connect(lambda: self.proxy.setFilterFixedString(self.search.text()))

    def _column_widths(self):
        self.tree.header().setStretchLastSection(False)
        for i, width in enumerate([330, 125, 125, 130, 95, 95, 155]):
            self.tree.setColumnWidth(i, width)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)

    def make_table(self, columns):
        table = QTableWidget(0, len(columns)); table.setHorizontalHeaderLabels(columns)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True); table.verticalHeader().hide()
        table.horizontalHeader().setStretchLastSection(True)
        for i in range(len(columns) - 1):
            table.setColumnWidth(i, 260 if i == 0 else 140)
        return table

    def launch(self, function, done, failed, progress=None):
        task = Task(function, self); self.jobs.append(task)
        task.completed.connect(done); task.failed.connect(failed)
        if progress:
            task.progress.connect(progress)
        task.finished.connect(lambda: self._job_finished(task))
        task.start(); return task

    def _job_finished(self, task):
        if task in self.jobs:
            self.jobs.remove(task)
        task.deleteLater()

    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, "분석할 폴더 선택", self.path.text() or str(Path.home()))
        if path:
            self.start_scan(path)

    def start_scan(self, path):
        if self.scan_task or self.download_task or self.closing:
            return
        path = str(path).strip().strip('"')
        if not path:
            self.choose_folder(); return
        self.path.setText(path); self.cancel_scan = threading.Event()
        self.scan_button.setEnabled(False); self.stop_button.setEnabled(True); self.export_button.setEnabled(False)
        self.progress_bar.setRange(0, 0); self.progress_bar.show()
        def work(progress):
            result = scan(path, self.cancel_scan, progress)
            return result, largest_files(result.root), extension_summary(result.root)
        self.scan_task = self.launch(work, self.scan_completed, self.scan_failed, self.scan_progress)

    def stop_scan(self):
        self.cancel_scan.set(); self.stop_button.setEnabled(False)
        self.statusBar().showMessage("분석 중지 요청 · 현재까지의 결과를 정리하고 있습니다.")

    def scan_progress(self, data):
        self.metrics[0].setText(format_bytes(data["bytes"]))
        self.metrics[2].setText(f'{data["files"]:,} / {data["folders"]:,}')
        self.metrics[3].setText(f'{data["elapsed"]:.1f}초')
        self.statusBar().showMessage("분석 중 · " + data["path"])

    def _scan_idle(self):
        self.scan_task = None; self.scan_button.setEnabled(True); self.stop_button.setEnabled(False)
        self.export_button.setEnabled(self.result is not None); self.progress_bar.hide()

    def scan_completed(self, payload):
        self.result, largest, extensions = payload; root = self.result.root
        self._scan_idle(); self.path.setText(root.path)
        old = self.model; self.model = DiskTreeModel(root, self)
        self.proxy.setSourceModel(self.model); old.deleteLater()
        self.model.sort(1, Qt.SortOrder.DescendingOrder); self.tree.expand(self.proxy.index(0, 0))
        self.metrics[0].setText(format_bytes(root.size)); self.metrics[1].setText(format_bytes(root.allocated))
        self.metrics[2].setText(f"{root.files:,} / {root.folders:,}"); self.metrics[3].setText(f"{self.result.elapsed:.1f}초")
        try:
            usage = shutil.disk_usage(root.path)
            self.capacity.setText(f"드라이브 전체 {format_bytes(usage.total)}   ·   사용 중 {format_bytes(usage.used)}   ·   여유 {format_bytes(usage.free)}")
        except OSError:
            self.capacity.setText("드라이브 전체 용량을 가져올 수 없습니다.")
        self.fill_table(self.large_table, [[n.name, format_bytes(n.size), n.path] for n in largest])
        self.large_nodes = largest
        self.fill_table(self.extension_table, [[n["extension"], format_bytes(n["size"]), format_bytes(n["allocated"]), f'{n["files"]:,}'] for n in extensions])
        self.fill_table(self.error_table, self.result.errors)
        self.tabs.setTabText(3, f"접근 오류 ({len(self.result.errors):,})")
        self.select_node(root)
        status = "중지됨 · 부분 결과" if self.result.cancelled else "분석 완료"
        self.statusBar().showMessage(f"{status} · {root.files:,}개 파일 · 건너뛴 항목 {self.result.skipped:,}개")

    def scan_failed(self, error):
        self._scan_idle()
        if self.result:
            root = self.result.root
            self.path.setText(root.path)
            for metric, text in zip(self.metrics, [format_bytes(root.size), format_bytes(root.allocated), f"{root.files:,} / {root.folders:,}", f"{self.result.elapsed:.1f}초"]):
                metric.setText(text)
        self.statusBar().showMessage("분석 실패 · " + error)
        if not self.closing:
            QMessageBox.warning(self, "폴더를 분석할 수 없습니다", error)

    def fill_table(self, table, rows):
        table.setRowCount(len(rows))
        for r, values in enumerate(rows):
            for c, value in enumerate(values):
                item = QTableWidgetItem(str(value)); item.setToolTip(str(value)); table.setItem(r, c, item)

    def selection_changed(self, current, previous):
        if current.isValid():
            node = self.proxy.mapToSource(current).internalPointer()
            self.selected = node; self.map.set_node(node)
            self.selection_label.setText(f"{node.path}   ·   {format_bytes(node.size)}")
            self.selection_label.setToolTip(node.path)

    def select_node(self, node):
        self.search.clear(); self.proxy.setFilterFixedString("")
        current = node.parent
        ancestors = []
        while current:
            ancestors.append(current); current = current.parent
        for ancestor in reversed(ancestors):
            self.tree.expand(self.proxy.mapFromSource(self.model.index_for_node(ancestor)))
        index = self.proxy.mapFromSource(self.model.index_for_node(node))
        self.tree.setCurrentIndex(index); self.tree.scrollTo(index)

    def navigate_up(self):
        if self.selected and self.selected.parent:
            self.select_node(self.selected.parent)

    def context_menu(self, point):
        index = self.tree.indexAt(point)
        if not index.isValid():
            return
        node = self.proxy.mapToSource(index).internalPointer()
        menu = QMenu(self)
        menu.addAction("탐색기에서 위치 열기", lambda: self.open_location(node.path, node.is_dir))
        menu.addAction("경로 복사", lambda: QApplication.clipboard().setText(node.path))
        if node.is_dir and not node.skipped:
            menu.addAction("이 폴더 다시 분석", lambda: self.start_scan(node.path))
        menu.exec(self.tree.viewport().mapToGlobal(point))

    def open_location(self, path, is_dir=False):
        try:
            if os.name == "nt":
                if is_dir:
                    os.startfile(path)
                else:
                    subprocess.Popen(["explorer.exe", "/select,", os.path.normpath(path)])
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(path if is_dir else str(Path(path).parent)))
        except OSError as exc:
            QMessageBox.warning(self, "위치를 열 수 없습니다", str(exc))

    def open_large_location(self, row, column):
        if hasattr(self, "large_nodes") and row < len(self.large_nodes):
            self.open_location(self.large_nodes[row].path)

    def export_report(self):
        if not self.result:
            return
        name, selected = QFileDialog.getSaveFileName(self, "분석 결과 내보내기", "disk-usage.csv", "CSV (*.csv);;JSON (*.json)")
        if not name:
            return
        result = self.result; self.export_button.setEnabled(False)
        exporter = export_json if selected.startswith("JSON") or name.lower().endswith(".json") else export_csv
        def done(_):
            self.export_button.setEnabled(True); self.statusBar().showMessage("내보내기 완료 · " + name)
        def failed(error):
            self.export_button.setEnabled(True); QMessageBox.warning(self, "내보내기 실패", error)
        self.launch(lambda progress: exporter(result.root, name, result.cancelled), done, failed)

    def show_settings(self):
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            changed = self.settings.repository != dialog.saved.repository
            self.settings = dialog.saved
            if self.settings.check_updates:
                self.update_timer.start()
            else:
                self.update_timer.stop()
            if changed:
                self.release = None; self.banner.hide()
            self.check_updates(False)

    def _updater(self):
        token = ""
        if os.name == "nt":
            token = get_token(self.settings.repository)
        return GitHubUpdater(self.settings.repository, token)

    def check_updates(self, manual=False):
        if self.update_task or self.download_task or self.closing:
            return
        if not manual and not self.settings.check_updates:
            return
        repository = self.settings.repository
        self.update_button.setEnabled(False); self.update_status.setText("업데이트 확인 중…")
        def work(progress):
            return self._updater().check(VERSION)
        def done(release):
            self.update_task = None; self.update_button.setEnabled(True)
            if repository != self.settings.repository:
                self.update_status.setText("저장소 변경됨 · 다시 확인하세요"); return
            self.update_status.setText(f"{datetime.now():%H:%M} 확인 · " + (f"v{release.version} 사용 가능" if release else "최신 버전"))
            if release:
                self.release = release; self.banner_label.setText(f"새 버전 v{release.version}을 사용할 수 있습니다."); self.banner.show()
                if release.version not in self.notified_versions:
                    self.notified_versions.add(release.version)
                    self.tray.showMessage(APP_NAME, f"새 버전 v{release.version}이 있습니다. 앱에서 업데이트를 설치하세요.", QSystemTrayIcon.MessageIcon.Information, 10000)
                if manual:
                    self.release_notes()
            else:
                self.release = None; self.banner.hide()
                if manual:
                    QMessageBox.information(self, "업데이트", f"현재 v{VERSION}이 최신 버전입니다.")
        def failed(error):
            self.update_task = None; self.update_button.setEnabled(True)
            self.update_status.setText("업데이트 확인 실패 · 설정/연결 확인"); self.update_status.setToolTip(error)
            if manual and not self.closing:
                QMessageBox.warning(self, "업데이트를 확인할 수 없습니다", error)
        self.update_task = self.launch(work, done, failed)

    def release_notes(self):
        if not self.release:
            return
        dialog = QDialog(self); dialog.setWindowTitle(f"새 버전 v{self.release.version}"); dialog.resize(600, 430)
        layout = QVBoxLayout(dialog); text = QPlainTextEdit(); text.setReadOnly(True); text.setPlainText(self.release.notes or "등록된 변경 내용이 없습니다."); layout.addWidget(text)
        link = self._button("GitHub에서 보기", lambda: QDesktopServices.openUrl(QUrl(self.release.url))); layout.addWidget(link)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons); dialog.exec()

    def download_update(self):
        if not self.release or self.download_task:
            return
        if self.scan_task:
            QMessageBox.information(self, "분석 작업 진행 중", "분석이 끝나거나 중지한 뒤 업데이트를 설치하세요."); return
        release = self.release
        answer = QMessageBox.question(self, "업데이트 다운로드", f"v{release.version} 설치 파일을 GitHub에서 내려받으시겠습니까?\n다운로드 후 SHA-256을 검증하고 설치 여부를 다시 묻습니다.")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.install_button.setEnabled(False); self.scan_button.setEnabled(False)
        self.progress_bar.setRange(0, 100); self.progress_bar.setValue(0); self.progress_bar.show()
        def work(progress):
            return self._updater().download(release, lambda count, total: progress((count, total)))
        def report(data):
            count, total = data
            self.progress_bar.setValue(int(100 * count / total) if total else 0)
            self.update_status.setText("다운로드 중 · " + format_bytes(count))
        def done(path):
            self.download_task = None; self.install_button.setEnabled(True); self.scan_button.setEnabled(True); self.progress_bar.hide()
            self.update_status.setText("설치 파일 SHA-256 검증 완료")
            if self.closing:
                return
            answer = QMessageBox.question(self, "업데이트 설치", f"v{release.version} 설치 파일 검증이 완료되었습니다.\n지금 앱을 종료하고 설치 프로그램을 실행하시겠습니까?")
            if answer == QMessageBox.StandardButton.Yes:
                if os.name != "nt":
                    QMessageBox.information(self, "Windows 설치 파일", "Windows에서 실행할 수 있는 설치 파일입니다."); return
                try:
                    subprocess.Popen([str(path)], close_fds=True)
                    self.close()
                except OSError as exc:
                    QMessageBox.warning(self, "설치 프로그램 실행 실패", str(exc))
        def failed(error):
            self.download_task = None; self.install_button.setEnabled(True); self.scan_button.setEnabled(True); self.progress_bar.hide()
            self.update_status.setText("업데이트 다운로드 실패")
            if not self.closing:
                QMessageBox.warning(self, "다운로드 실패", error)
        self.download_task = self.launch(work, done, failed, report)

    def closeEvent(self, event):
        self.closing = True
        if any(task.isRunning() for task in self.jobs):
            self.closing = True; self.cancel_scan.set(); self.update_timer.stop()
            self.setEnabled(False); self.statusBar().showMessage("작업을 정리한 뒤 종료합니다…")
            event.ignore(); QTimer.singleShot(150, self.close)
        else:
            self.update_timer.stop(); self.tray.hide(); event.accept()


def main():
    app = QApplication(sys.argv); app.setApplicationName(APP_NAME); app.setOrganizationName("CodeHive")
    app.setStyle("Fusion"); app.setStyleSheet(STYLE)
    mutex = None
    if os.name == "nt":
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        kernel.CreateMutexW.restype = wintypes.HANDLE
        mutex = kernel.CreateMutexW(None, False, "TreeSizeExplorerMutex")
        if ctypes.get_last_error() == 183:
            QMessageBox.information(None, APP_NAME, "프로그램이 이미 실행 중입니다."); return 0
    window = MainWindow(); window.show()
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        QTimer.singleShot(100, lambda: window.start_scan(sys.argv[1]))
    result = app.exec()
    if mutex:
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]; kernel.CloseHandle(mutex)
    return result
