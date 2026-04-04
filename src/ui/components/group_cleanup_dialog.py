from PySide6.QtCore import QDate, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout
)


class GroupCleanupDialog(QDialog):
    scanRequested = Signal(str, str)
    leaveRequested = Signal(object)

    def __init__(self, mode="stale", parent=None):
        super().__init__(parent)
        self.mode = mode
        self.rows_by_id = {}
        self.all_rows = []
        self.setWindowTitle("Group Cleanup")
        self.setMinimumSize(920, 620)
        self.setup_ui()
        self.apply_table_palette()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        header_text = "Leave inactive Telegram groups" if self.mode == "stale" else "Review all joined chats and channels"
        header = QLabel(header_text)
        header.setObjectName("MainHeader")
        layout.addWidget(header)

        if self.mode == "stale":
            hint_text = (
                "Preview joined groups, channels, and other chat-like dialogs whose last visible message is older than the cutoff date. "
                "Nothing is left until you confirm."
            )
        else:
            hint_text = (
                "Review every joined group, channel, or chat-like dialog on this account, regardless of recent activity. "
                "Nothing is left until you confirm."
            )
        hint = QLabel(hint_text)
        hint.setWordWrap(True)
        hint.setObjectName("MutedText")
        layout.addWidget(hint)

        controls = QHBoxLayout()
        controls.setSpacing(12)

        cutoff_label = QLabel("Inactive before")
        cutoff_label.setObjectName("SectionHeader")
        controls.addWidget(cutoff_label)

        self.cutoff_date = QDateEdit()
        self.cutoff_date.setCalendarPopup(True)
        self.cutoff_date.setDisplayFormat("yyyy-MM-dd")
        self.cutoff_date.setDate(QDate(2025, 8, 1))
        self.cutoff_date.setMinimumWidth(140)
        controls.addWidget(self.cutoff_date)

        self.btn_scan = QPushButton("Scan Stale Items" if self.mode == "stale" else "Scan All Joined Items")
        self.btn_scan.setObjectName("PrimaryButton")
        self.btn_scan.clicked.connect(self.request_scan)
        controls.addWidget(self.btn_scan)

        self.btn_select_all = QPushButton("Select All")
        self.btn_select_all.setObjectName("SecondaryButton")
        self.btn_select_all.clicked.connect(lambda: self.set_all_rows(True))
        controls.addWidget(self.btn_select_all)

        self.btn_clear_selection = QPushButton("Clear Selection")
        self.btn_clear_selection.setObjectName("SecondaryButton")
        self.btn_clear_selection.clicked.connect(lambda: self.set_all_rows(False))
        controls.addWidget(self.btn_clear_selection)

        controls.addStretch()
        layout.addLayout(controls)

        if self.mode != "stale":
            cutoff_label.hide()
            self.cutoff_date.hide()

        self.lbl_status = QLabel("Ready to scan.")
        self.lbl_status.setObjectName("DialogStatus")
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(12)
        filter_row.setContentsMargins(0, 0, 0, 0)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("CleanupSearchInput")
        self.search_input.setPlaceholderText("Search title, username, type, status, or last message...")
        self.search_input.setFixedHeight(36)
        self.search_input.textChanged.connect(self.apply_filters)
        filter_row.addWidget(self.search_input, 1)

        self.status_filter = QComboBox()
        self.status_filter.setObjectName("CleanupStatusFilter")
        self.status_filter.addItem("All Statuses")
        self.status_filter.currentTextChanged.connect(self.apply_filters)
        self.status_filter.setMinimumWidth(180)
        self.status_filter.setMaximumWidth(220)
        self.status_filter.setFixedHeight(36)
        filter_row.addWidget(self.status_filter)

        layout.addLayout(filter_row)

        self.scan_progress = QProgressBar()
        self.scan_progress.setTextVisible(False)
        self.scan_progress.setRange(0, 1)
        self.scan_progress.setValue(0)
        self.scan_progress.hide()
        layout.addWidget(self.scan_progress)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["Leave", "Title", "ID", "Type", "Status", "Last Message", "Archived", "Username"])
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.table.horizontalHeader().setSectionsClickable(True)
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(True)
        self.table.setSortingEnabled(True)
        self.table.itemChanged.connect(self.update_selection_label)
        self.table.cellClicked.connect(self.handle_cell_clicked)
        layout.addWidget(self.table)

        footer = QHBoxLayout()
        footer.setSpacing(12)

        self.lbl_selection = QLabel("0 items selected")
        self.lbl_selection.setObjectName("MutedText")
        footer.addWidget(self.lbl_selection)

        footer.addStretch()

        self.btn_close = QPushButton("Close")
        self.btn_close.setObjectName("SecondaryButton")
        self.btn_close.clicked.connect(self.reject)
        footer.addWidget(self.btn_close)

        self.btn_leave = QPushButton("Leave Selected Items")
        self.btn_leave.setObjectName("LogoutBtn")
        self.btn_leave.clicked.connect(self.request_leave_selected)
        self.btn_leave.setEnabled(False)
        footer.addWidget(self.btn_leave)

        layout.addLayout(footer)

    def request_scan(self):
        cutoff_iso = self.cutoff_date.date().toString("yyyy-MM-dd") if self.mode == "stale" else ""
        if self.mode == "stale":
            message = f"Scanning joined chats and channels inactive before {cutoff_iso}..."
        else:
            message = "Scanning all joined chats and channels..."
        self.set_busy(True, message)
        self.scanRequested.emit(self.mode, cutoff_iso)

    def update_scan_progress(self, scanned_groups, matches, phase):
        phase_label = "archived dialogs" if phase == "archived" else "active dialogs"
        prefix = (
            f"Scanning {phase_label} inactive before {self.cutoff_date.date().toString('yyyy-MM-dd')}..."
            if self.mode == "stale"
            else f"Scanning all {phase_label}..."
        )
        self.lbl_status.setText(f"{prefix} Checked {scanned_groups} items, found {matches} matches so far.")

    def populate_results(self, rows, cutoff_iso):
        self.all_rows = list(rows)
        self.rows_by_id = {row["id"]: row for row in rows}
        self.table.blockSignals(True)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))

        for row_index, row in enumerate(rows):
            checkbox_item = QTableWidgetItem()
            checkbox_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            checkbox_item.setCheckState(Qt.Unchecked)
            checkbox_item.setData(Qt.UserRole, row["id"])
            self.table.setItem(row_index, 0, checkbox_item)
            self.table.setItem(row_index, 1, QTableWidgetItem(row["title"]))
            self.table.setItem(row_index, 2, QTableWidgetItem(row["id"]))
            self.table.setItem(row_index, 3, QTableWidgetItem(row["type"]))
            self.table.setItem(row_index, 4, QTableWidgetItem(row.get("status", "Unknown")))
            self.table.setItem(row_index, 5, QTableWidgetItem(row["last_message_display"]))
            self.table.setItem(row_index, 6, QTableWidgetItem("Yes" if row["archived"] else "No"))
            username_item = QTableWidgetItem(row["username"] or "")
            if row.get("username"):
                username_item.setForeground(QColor("#2BA5E4"))
                username_item.setToolTip("Open in Telegram")
            self.table.setItem(row_index, 7, username_item)

        self.table.blockSignals(False)
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(0, 58)
        self.table.setColumnWidth(1, 240)
        self.table.setColumnWidth(2, 140)
        self.table.setColumnWidth(3, 110)
        self.table.setColumnWidth(4, 170)
        self.table.setColumnWidth(5, 170)
        self.table.setColumnWidth(6, 78)
        self.table.setColumnWidth(7, 180)
        self.table.setSortingEnabled(True)
        self.refresh_status_filter_options()
        self.apply_filters()
        self.set_busy(False)

        if rows:
            if cutoff_iso == "__ALL__" or self.mode != "stale":
                self.lbl_status.setText(
                    f"Found {len(rows)} joined items. Review the list, then leave only the ones you want."
                )
            else:
                self.lbl_status.setText(
                    f"Found {len(rows)} stale joined items before {cutoff_iso}. Review the list, then leave only the ones you want."
                )
        else:
            if cutoff_iso == "__ALL__" or self.mode != "stale":
                self.lbl_status.setText("No joined chats or channels were found.")
            else:
                self.lbl_status.setText(f"No joined chats or channels matched the inactivity cutoff before {cutoff_iso}.")
        self.update_selection_label()

    def refresh_status_filter_options(self):
        current = self.status_filter.currentText()
        statuses = sorted({row.get("status", "Unknown") for row in self.all_rows})
        self.status_filter.blockSignals(True)
        self.status_filter.clear()
        self.status_filter.addItem("All Statuses")
        for status in statuses:
            self.status_filter.addItem(status)
        index = self.status_filter.findText(current)
        self.status_filter.setCurrentIndex(index if index >= 0 else 0)
        self.status_filter.blockSignals(False)

    def apply_filters(self, *_args):
        search_text = self.search_input.text().strip().lower()
        selected_status = self.status_filter.currentText()

        for row_index in range(self.table.rowCount()):
            row_matches = True
            row_id_item = self.table.item(row_index, 0)
            row_id = row_id_item.data(Qt.UserRole) if row_id_item else None
            row = self.rows_by_id.get(row_id, {})

            if selected_status != "All Statuses" and row.get("status", "Unknown") != selected_status:
                row_matches = False

            if row_matches and search_text:
                haystack = " ".join([
                    row.get("title", ""),
                    row.get("id", ""),
                    row.get("type", ""),
                    row.get("status", ""),
                    row.get("last_message_display", ""),
                    row.get("username", "")
                ]).lower()
                row_matches = search_text in haystack

            self.table.setRowHidden(row_index, not row_matches)

    def handle_cell_clicked(self, row_index, column_index):
        if column_index != 7:
            return

        row_id_item = self.table.item(row_index, 0)
        row_id = row_id_item.data(Qt.UserRole) if row_id_item else None
        row = self.rows_by_id.get(row_id, {})
        username = (row.get("username") or "").lstrip("@")
        if not username:
            return

        tg_url = QUrl(f"https://t.me/{username}")
        QDesktopServices.openUrl(tg_url)

    def show_error(self, message):
        self.set_busy(False)
        self.lbl_status.setText(message)
        QMessageBox.warning(self, "Group Cleanup", message)

    def handle_leave_results(self, results):
        self.set_busy(False)
        left_ids = set(results.get("left_ids", []))
        failed = results.get("failed", [])

        if left_ids:
            remaining_rows = []
            for row_index in range(self.table.rowCount()):
                item = self.table.item(row_index, 0)
                if item and item.data(Qt.UserRole) not in left_ids:
                    remaining_rows.append(self.rows_by_id[item.data(Qt.UserRole)])
            self.populate_results(remaining_rows, self.cutoff_date.date().toString("yyyy-MM-dd"))

        if failed:
            failures = "\n".join(
                f"{self.rows_by_id.get(entry['id'], {}).get('title', entry['id'])}: {entry['error']}"
                for entry in failed
            )
            self.lbl_status.setText(
                f"Left {len(left_ids)} items. {len(failed)} failed and still need attention."
            )
            QMessageBox.warning(self, "Some Groups Were Not Left", failures)
        elif left_ids:
            self.lbl_status.setText(f"Left {len(left_ids)} items successfully.")
            QMessageBox.information(self, "Group Cleanup", f"Left {len(left_ids)} items.")
        else:
            self.lbl_status.setText("No groups were left.")

        self.update_selection_label()

    def selected_group_ids(self):
        ids = []
        for row_index in range(self.table.rowCount()):
            item = self.table.item(row_index, 0)
            if item and item.checkState() == Qt.Checked:
                ids.append(item.data(Qt.UserRole))
        return ids

    def set_all_rows(self, checked):
        state = Qt.Checked if checked else Qt.Unchecked
        self.table.blockSignals(True)
        for row_index in range(self.table.rowCount()):
            item = self.table.item(row_index, 0)
            if item:
                item.setCheckState(state)
        self.table.blockSignals(False)
        self.update_selection_label()

    def update_selection_label(self, *_args):
        count = len(self.selected_group_ids())
        self.lbl_selection.setText(f"{count} items selected")
        self.btn_leave.setEnabled(count > 0 and not self.btn_leave.property("busy"))

    def set_busy(self, busy, message=None):
        self.btn_scan.setEnabled(not busy)
        self.btn_select_all.setEnabled(not busy and self.table.rowCount() > 0)
        self.btn_clear_selection.setEnabled(not busy and self.table.rowCount() > 0)
        self.btn_close.setEnabled(not busy)
        self.btn_leave.setProperty("busy", busy)
        self.btn_leave.setEnabled(not busy and len(self.selected_group_ids()) > 0)
        if busy:
            self.scan_progress.setRange(0, 0)
            self.scan_progress.show()
        else:
            self.scan_progress.setRange(0, 1)
            self.scan_progress.setValue(0)
            self.scan_progress.hide()
        if message:
            self.lbl_status.setText(message)

    def request_leave_selected(self):
        selected_ids = self.selected_group_ids()
        if not selected_ids:
            QMessageBox.information(self, "Group Cleanup", "Select at least one item first.")
            return

        reply = QMessageBox.question(
            self,
            "Leave Selected Items",
            f"Leave {len(selected_ids)} selected chats or channels? This removes them from your Telegram account.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self.set_busy(True, f"Leaving {len(selected_ids)} selected items...")
        self.leaveRequested.emit(selected_ids)

    def apply_table_palette(self):
        window_color = self.palette().color(QPalette.Window)
        is_dark = window_color.lightness() < 128

        if is_dark:
            base = QColor("#1E293B")
            alt = QColor("#273449")
            text = QColor("#F8FAFC")
            header_bg = QColor("#0F172A")
            header_text = QColor("#E2E8F0")
            grid = QColor("#334155")
        else:
            base = QColor("#FFFFFF")
            alt = QColor("#F8FAFC")
            text = QColor("#1E293B")
            header_bg = QColor("#E2E8F0")
            header_text = QColor("#1E293B")
            grid = QColor("#CBD5E1")

        palette = self.table.palette()
        palette.setColor(QPalette.Base, base)
        palette.setColor(QPalette.AlternateBase, alt)
        palette.setColor(QPalette.Text, text)
        palette.setColor(QPalette.Button, header_bg)
        palette.setColor(QPalette.ButtonText, header_text)
        palette.setColor(QPalette.Highlight, QColor("#2BA5E4"))
        palette.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
        self.table.setPalette(palette)

        self.table.setStyleSheet(
            f"""
            QTableWidget {{
                background-color: {base.name()};
                alternate-background-color: {alt.name()};
                color: {text.name()};
                gridline-color: {grid.name()};
                border: 1px solid {grid.name()};
                border-radius: 8px;
                selection-background-color: #2BA5E4;
                selection-color: #FFFFFF;
            }}
            QHeaderView::section {{
                background-color: {header_bg.name()};
                color: {header_text.name()};
                border: 0;
                border-right: 1px solid {grid.name()};
                border-bottom: 1px solid {grid.name()};
                padding: 8px;
                font-weight: 600;
            }}
            QTableCornerButton::section {{
                background-color: {header_bg.name()};
                border: 0;
                border-right: 1px solid {grid.name()};
                border-bottom: 1px solid {grid.name()};
            }}
            """
        )

        if is_dark:
            combo_bg = "#111827"
            combo_text = "#F8FAFC"
            combo_border = "#334155"
            combo_hover = "#475569"
        else:
            combo_bg = "#FFFFFF"
            combo_text = "#1E293B"
            combo_border = "#CBD5E1"
            combo_hover = "#94A3B8"

        self.search_input.setStyleSheet(
            f"""
            QLineEdit#CleanupSearchInput {{
                background-color: {combo_bg};
                color: {combo_text};
                border: 1px solid {combo_border};
                border-radius: 6px;
                padding: 0 12px;
                min-height: 36px;
                max-height: 36px;
            }}
            QLineEdit#CleanupSearchInput:focus {{
                border-color: #2BA5E4;
            }}
            """
        )

        self.status_filter.setStyleSheet(
            f"""
            QComboBox#CleanupStatusFilter {{
                background-color: {combo_bg};
                color: {combo_text};
                border: 1px solid {combo_border};
                border-radius: 6px;
                padding: 0 30px 0 12px;
                min-height: 36px;
                max-height: 36px;
            }}
            QComboBox#CleanupStatusFilter:hover {{
                border-color: {combo_hover};
            }}
            QComboBox#CleanupStatusFilter:on {{
                border-color: #2BA5E4;
            }}
            QComboBox#CleanupStatusFilter::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 26px;
                border: none;
                border-left: 1px solid {combo_border};
                background: transparent;
                margin: 0;
            }}
            QComboBox#CleanupStatusFilter::down-arrow {{
                width: 10px;
                height: 10px;
            }}
            QComboBox#CleanupStatusFilter QAbstractItemView {{
                background-color: {combo_bg};
                color: {combo_text};
                border: 1px solid {combo_border};
                selection-background-color: #2BA5E4;
                selection-color: #FFFFFF;
            }}
            """
        )
