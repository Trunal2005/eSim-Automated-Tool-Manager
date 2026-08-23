"""Worker threads for the GUI to keep the main event loop responsive.

Uses PyQt6 QThread to run backend service methods asynchronously
and emit signals back to the main thread upon completion.

Architecture Note:
To solve Bug 1 (SQLite thread-safety violation), we chose the pattern of 
scoping a new SQLite connection to each QThread worker's run() method. 
Passing the db_path to the worker and re-instantiating the core services 
(DatabaseManager, RegistryManager, DependencyChecker, etc.) inside run() 
is the cleanest approach. It guarantees thread safety because the SQLite 
connection object never crosses thread boundaries, and it requires minimal 
changes to the core service APIs since they already encapsulate their own DB access.
"""

from typing import Any, Callable
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from esim_tool_manager.core.dependency_checker import DependencyChecker
from esim_tool_manager.core.config_manager import ConfigManager
from esim_tool_manager.core.doctor import Doctor
from esim_tool_manager.core.installer import Installer
from esim_tool_manager.data.database import DatabaseManager
from esim_tool_manager.data.registry import RegistryManager
from esim_tool_manager.infra.os_detect import get_system_info


class WorkerSignals(QObject):
    """Defines the signals available from a running worker thread."""
    finished = pyqtSignal()
    error = pyqtSignal(str)
    result = pyqtSignal(object)
    progress = pyqtSignal(str)


def _init_thread_services(db_path: Path) -> dict[str, Any]:
    """Helper to initialize a new set of services scoped to the current thread."""
    db = DatabaseManager(db_path=db_path)
    db.__enter__()  # Open connection
    registry = RegistryManager(db)
    # We do not call registry.initialize() here to avoid running migrations concurrently.
    # The main thread already ran migrations on startup.
    
    system_info = get_system_info()
    checker = DependencyChecker(registry, system_info)
    config_manager = ConfigManager(registry, system_info)
    installer = Installer(registry, checker, system_info)
    
    return {
        "db": db,
        "registry": registry,
        "checker": checker,
        "config": config_manager,
        "installer": installer,
    }


class StatusWorker(QThread):
    """Worker for fetching system status asynchronously."""

    def __init__(self, db_path: Path) -> None:
        super().__init__()
        self.db_path = db_path
        self.signals = WorkerSignals()

    def run(self) -> None:
        db = None
        try:
            services = _init_thread_services(self.db_path)
            db = services["db"]
            checker: DependencyChecker = services["checker"]
            
            res = checker.get_summary()
            self.signals.result.emit(res)
        except Exception as e:
            self.signals.error.emit(str(e))
        finally:
            if db:
                db.close()
            self.signals.finished.emit()


class InstallWorker(QThread):
    """Worker for running installations asynchronously."""

    def __init__(
        self,
        db_path: Path,
        tool_id: str | None = None,
        profile: str | None = None,
        dry_run: bool = True,
    ) -> None:
        super().__init__()
        self.db_path = db_path
        self.tool_id = tool_id
        self.profile = profile
        self.dry_run = dry_run
        self.signals = WorkerSignals()

    def run(self) -> None:
        db = None
        try:
            services = _init_thread_services(self.db_path)
            db = services["db"]
            installer: Installer = services["installer"]

            self.signals.progress.emit("Starting installation...")
            
            # Simple confirmation callback that auto-accepts (the GUI handles confirmation beforehand)
            def auto_confirm(msg: str) -> bool:
                return True

            if self.tool_id:
                res = installer.install_tool(
                    self.tool_id, dry_run=self.dry_run, confirm_callback=auto_confirm
                )
                self.signals.result.emit([res])
            else:
                res_list = installer.install_all(
                    profile_name=self.profile, dry_run=self.dry_run, confirm_callback=auto_confirm
                )
                self.signals.result.emit(res_list)
                
            self.signals.progress.emit("Installation complete.")
        except Exception as e:
            self.signals.error.emit(str(e))
        finally:
            if db:
                db.close()
            self.signals.finished.emit()
