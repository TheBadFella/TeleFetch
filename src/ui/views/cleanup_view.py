from PySide6.QtWidgets import QMessageBox, QPushButton, QLabel, QWidget, QVBoxLayout, QHBoxLayout

from ui.components.group_cleanup_dialog import GroupCleanupDialog
from workers.cleanup_worker import CleanupWorker


class CleanupView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.group_cleanup_dialog = None
        self.cleanup_worker = CleanupWorker(parent=self)
        self.cleanup_worker.start()
        self.setup_ui()
        self.connect_signals()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 20, 40, 40)
        layout.setSpacing(24)

        card = QWidget()
        card.setObjectName("WhiteCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(16)

        title = QLabel("Group Cleanup")
        title.setObjectName("MainHeader")
        card_layout.addWidget(title)

        desc = QLabel(
            "Review stale joined items by cutoff, or scan every joined chat and channel with no last-message filtering."
        )
        desc.setObjectName("MutedText")
        desc.setWordWrap(True)
        card_layout.addWidget(desc)

        action_row = QHBoxLayout()

        self.btn_cleanup_test = QPushButton("Test Telegram Connection")
        self.btn_cleanup_test.setObjectName("SecondaryButton")
        self.btn_cleanup_test.clicked.connect(self.cleanup_worker.test_connection)
        action_row.addWidget(self.btn_cleanup_test)

        self.btn_cleanup_open = QPushButton("Open Stale Cleanup")
        self.btn_cleanup_open.setObjectName("PrimaryButton")
        self.btn_cleanup_open.clicked.connect(lambda: self.open_group_cleanup_dialog("stale"))
        action_row.addWidget(self.btn_cleanup_open)

        self.btn_cleanup_open_all = QPushButton("Open All Cleanup")
        self.btn_cleanup_open_all.setObjectName("PrimaryButton")
        self.btn_cleanup_open_all.clicked.connect(lambda: self.open_group_cleanup_dialog("all"))
        action_row.addWidget(self.btn_cleanup_open_all)
        action_row.addStretch()
        card_layout.addLayout(action_row)

        help_text = QLabel(
            "Use Stale Cleanup for inactivity-based review, or All Cleanup to manually review everything you have joined."
        )
        help_text.setObjectName("DialogStatus")
        help_text.setWordWrap(True)
        card_layout.addWidget(help_text)

        layout.addWidget(card)
        layout.addStretch()

    def connect_signals(self):
        self.cleanup_worker.signals.connection_test_completed.connect(self.on_connection_test_completed)
        self.cleanup_worker.signals.scan_progress.connect(self.on_group_cleanup_scan_progress)
        self.cleanup_worker.signals.scan_completed.connect(self.on_group_cleanup_scan_completed)
        self.cleanup_worker.signals.leave_completed.connect(self.on_group_cleanup_leave_completed)
        self.cleanup_worker.signals.error.connect(self.on_group_cleanup_error)

    def stop(self):
        if self.cleanup_worker.isRunning():
            self.cleanup_worker.stop()
            self.cleanup_worker.wait(2000)

    def on_connection_test_completed(self, success, message):
        title = "Telegram Connection" if success else "Telegram Connection Failed"
        if success:
            QMessageBox.information(self, title, message)
        else:
            QMessageBox.warning(self, title, message)

    def handle_group_cleanup_scan_request(self, mode, cutoff_iso):
        if mode == "all":
            self.cleanup_worker.scan_all_joined_items()
        else:
            self.cleanup_worker.scan_inactive_items(cutoff_iso)

    def open_group_cleanup_dialog(self, mode="stale"):
        if self.group_cleanup_dialog is None:
            self.group_cleanup_dialog = GroupCleanupDialog(mode=mode, parent=self)
            self.group_cleanup_dialog.scanRequested.connect(self.handle_group_cleanup_scan_request)
            self.group_cleanup_dialog.leaveRequested.connect(self.cleanup_worker.leave_items)
            self.group_cleanup_dialog.finished.connect(self.on_group_cleanup_dialog_closed)
        elif getattr(self.group_cleanup_dialog, "mode", "stale") != mode:
            self.group_cleanup_dialog.close()
            self.group_cleanup_dialog = GroupCleanupDialog(mode=mode, parent=self)
            self.group_cleanup_dialog.scanRequested.connect(self.handle_group_cleanup_scan_request)
            self.group_cleanup_dialog.leaveRequested.connect(self.cleanup_worker.leave_items)
            self.group_cleanup_dialog.finished.connect(self.on_group_cleanup_dialog_closed)

        self.group_cleanup_dialog.show()
        self.group_cleanup_dialog.raise_()
        self.group_cleanup_dialog.activateWindow()

    def on_group_cleanup_dialog_closed(self, _result=None):
        self.group_cleanup_dialog = None

    def on_group_cleanup_scan_completed(self, rows, cutoff_iso):
        if self.group_cleanup_dialog:
            self.group_cleanup_dialog.populate_results(rows, cutoff_iso)

    def on_group_cleanup_scan_progress(self, scanned_groups, matches, phase):
        if self.group_cleanup_dialog:
            self.group_cleanup_dialog.update_scan_progress(scanned_groups, matches, phase)

    def on_group_cleanup_leave_completed(self, results):
        if self.group_cleanup_dialog:
            self.group_cleanup_dialog.handle_leave_results(results)

    def on_group_cleanup_error(self, message):
        if self.group_cleanup_dialog:
            self.group_cleanup_dialog.show_error(message)
        else:
            QMessageBox.warning(self, "Group Cleanup", message)
