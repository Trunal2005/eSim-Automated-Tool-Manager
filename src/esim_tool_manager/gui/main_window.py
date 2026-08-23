"""Main Window for the eSim Tool Manager GUI.

Provides a tabbed interface for:
- System Status (Doctor/Checker summary)
- Installation & Profiles
- Operation History
"""

from __future__ import annotations

import logging
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from esim_tool_manager.core.config_manager import ConfigManager
from esim_tool_manager.core.dependency_checker import DependencyChecker
from esim_tool_manager.core.doctor import Doctor
from esim_tool_manager.core.installer import Installer
from esim_tool_manager.core.updater import Updater
from esim_tool_manager.data.models import ToolStatus
from esim_tool_manager.data.registry import RegistryManager
from esim_tool_manager.data.database import DatabaseManager
from esim_tool_manager.gui.workers import StatusWorker, InstallWorker

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window for the GUI."""

    def __init__(self, services: dict[str, Any]) -> None:
        super().__init__()
        self.services = services
        self.registry: RegistryManager = services["registry"]
        self.checker: DependencyChecker = services["checker"]
        self.config: ConfigManager = services["config"]
        self.installer: Installer = services["installer"]
        self.updater: Updater = services["updater"]
        self.doctor: Doctor = services["doctor"]
        self.db: DatabaseManager = services["db"]

        self.setWindowTitle("eSim Tool Manager")
        self.resize(800, 600)
        self._init_ui()
        self._refresh_status()

    def _init_ui(self) -> None:
        """Initialize the user interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)

        # Create tabs
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        self._init_status_tab()
        self._init_install_tab()
        self._init_history_tab()

    def _init_status_tab(self) -> None:
        """Initialize the System Status tab."""
        status_widget = QWidget()
        layout = QVBoxLayout(status_widget)

        # Header with overall health
        self.health_label = QLabel("Checking system health...")
        self.health_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.health_label)

        # Table for tool status
        self.status_table = QTableWidget()
        self.status_table.setColumnCount(4)
        self.status_table.setHorizontalHeaderLabels(["Tool", "Status", "Installed", "Message"])
        self.status_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.status_table)

        # Refresh button
        refresh_btn = QPushButton("Refresh Status")
        refresh_btn.clicked.connect(self._refresh_status)
        layout.addWidget(refresh_btn)

        self.tabs.addTab(status_widget, "System Status")

    def _init_install_tab(self) -> None:
        """Initialize the Installation tab."""
        install_widget = QWidget()
        layout = QVBoxLayout(install_widget)

        # Profile selection
        profile_layout = QHBoxLayout()
        profile_layout.addWidget(QLabel("Select Profile:"))
        self.profile_combo = QComboBox()
        
        profiles = self.config.get_profiles()
        for p in profiles:
            self.profile_combo.addItem(p.display_name, p.name)
            
        profile_layout.addWidget(self.profile_combo)
        layout.addLayout(profile_layout)

        # Dry run checkbox (checked by default for safety)
        self.dry_run_checkbox = QCheckBox("Dry Run (Simulate only, do not modify system)")
        self.dry_run_checkbox.setChecked(True)
        layout.addWidget(self.dry_run_checkbox)

        # Install button
        self.install_btn = QPushButton("Install Profile")
        self.install_btn.clicked.connect(self._on_install_clicked)
        layout.addWidget(self.install_btn)

        # Log output area
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        layout.addWidget(QLabel("Installation Log:"))
        layout.addWidget(self.log_output)

        self.tabs.addTab(install_widget, "Install & Update")

    def _init_history_tab(self) -> None:
        """Initialize the History tab."""
        history_widget = QWidget()
        layout = QVBoxLayout(history_widget)
        
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(5)
        self.history_table.setHorizontalHeaderLabels(["Time", "Tool", "Method", "Success", "Dry Run"])
        self.history_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.history_table)
        
        refresh_btn = QPushButton("Refresh History")
        refresh_btn.clicked.connect(self._refresh_history)
        layout.addWidget(refresh_btn)
        
        self.tabs.addTab(history_widget, "History")
        
        # Load initial history when tab is changed
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, index: int) -> None:
        if self.tabs.tabText(index) == "History":
            self._refresh_history()

    # --- Actions ---

    def _refresh_status(self) -> None:
        """Fetch and display current tool status asynchronously."""
        self.health_label.setText("Checking system health...")
        self.status_table.setRowCount(0)
        
        self.worker = StatusWorker(db_path=self.db.db_path)
        self.worker.signals.result.connect(self._on_status_result)
        self.worker.signals.error.connect(lambda e: self.health_label.setText(f"Error: {e}"))
        self.worker.start()

    def _on_status_result(self, summary: dict[str, Any]) -> None:
        """Handle the result of the status check."""
        results = summary.get("results", [])
        
        # Compute overall health purely based on OK tools vs missing core tools
        # For simplicity, we just look at the counts
        ok_count = summary.get("status_counts", {}).get(ToolStatus.OK.value, 0)
        total = summary.get("total_tools", 0)
        
        if ok_count == total:
            self.health_label.setText("System Health: ALL TOOLS OK")
            self.health_label.setStyleSheet("font-size: 16px; font-weight: bold; color: green;")
        else:
            self.health_label.setText(f"System Health: {ok_count}/{total} TOOLS OK")
            self.health_label.setStyleSheet("font-size: 16px; font-weight: bold; color: orange;")

        self.status_table.setRowCount(len(results))
        for row, result in enumerate(results):
            tool_item = QTableWidgetItem(result["tool_id"])
            status_item = QTableWidgetItem(result["status"].upper())
            installed_item = QTableWidgetItem(result.get("installed_version") or "-")
            msg_item = QTableWidgetItem(result.get("message", ""))
            
            # Color coding
            if result["status"] == ToolStatus.OK.value:
                status_item.setForeground(Qt.GlobalColor.green)
            elif result["status"] == ToolStatus.MISSING.value:
                status_item.setForeground(Qt.GlobalColor.red)
            elif result["status"] == ToolStatus.OUTDATED.value:
                status_item.setForeground(Qt.GlobalColor.darkYellow)
                
            self.status_table.setItem(row, 0, tool_item)
            self.status_table.setItem(row, 1, status_item)
            self.status_table.setItem(row, 2, installed_item)
            self.status_table.setItem(row, 3, msg_item)

    def _on_install_clicked(self) -> None:
        """Handle install button click."""
        profile_name = self.profile_combo.currentData()
        dry_run = self.dry_run_checkbox.isChecked()
        
        if not dry_run:
            reply = QMessageBox.question(
                self,
                "Confirm Installation",
                "You are about to modify your system. Are you sure you want to proceed?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                return

        self.log_output.clear()
        self.log_output.append(f"Starting {'DRY RUN ' if dry_run else ''}installation of profile '{profile_name}'...\n")
        self.install_btn.setEnabled(False)
        
        self.worker = InstallWorker(db_path=self.db.db_path, profile=profile_name, dry_run=dry_run)
        self.worker.signals.progress.connect(self.log_output.append)
        self.worker.signals.result.connect(self._on_install_result)
        self.worker.signals.error.connect(lambda e: self.log_output.append(f"ERROR: {e}"))
        self.worker.signals.finished.connect(lambda: self.install_btn.setEnabled(True))
        self.worker.start()

    def _on_install_result(self, results: list[Any]) -> None:
        """Handle install results."""
        self.log_output.append("\nInstallation Results:\n" + "-"*40)
        for res in results:
            status = "SUCCESS" if res.success else "FAILED"
            self.log_output.append(f"[{status}] {res.tool_id}: {res.message}")
            
        self._refresh_status()

    def _refresh_history(self) -> None:
        """Fetch and display install history."""
        records = self.registry.get_install_history(limit=50)
        self.history_table.setRowCount(len(records))
        
        for row, rec in enumerate(records):
            time_item = QTableWidgetItem(rec.get("timestamp", ""))
            tool_item = QTableWidgetItem(rec.get("tool_id", ""))
            method_item = QTableWidgetItem(rec.get("method", ""))
            
            success = rec.get("success", 0)
            success_item = QTableWidgetItem("✅" if success else "❌")
            
            dry_run = rec.get("dry_run", 0)
            dry_item = QTableWidgetItem("Yes" if dry_run else "No")
            
            self.history_table.setItem(row, 0, time_item)
            self.history_table.setItem(row, 1, tool_item)
            self.history_table.setItem(row, 2, method_item)
            self.history_table.setItem(row, 3, success_item)
            self.history_table.setItem(row, 4, dry_item)
