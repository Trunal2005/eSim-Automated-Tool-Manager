import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from esim_tool_manager.gui.main_window import MainWindow
from esim_tool_manager.data.database import DatabaseManager
from esim_tool_manager.data.registry import RegistryManager
from esim_tool_manager.core.dependency_checker import DependencyChecker
from esim_tool_manager.core.config_manager import ConfigManager
from esim_tool_manager.core.installer import Installer
from esim_tool_manager.core.updater import Updater
from esim_tool_manager.core.doctor import Doctor
from esim_tool_manager.infra.os_detect import get_system_info

def run():
    app = QApplication(sys.argv)
    
    # Initialize services
    db_path = Path("esim_tools.db")
    db = DatabaseManager(db_path=db_path)
    db.__enter__()
    registry = RegistryManager(db)
    registry.initialize()
    system_info = get_system_info()
    checker = DependencyChecker(registry, system_info)
    config = ConfigManager(registry, system_info)
    installer = Installer(registry, checker, system_info)
    updater = Updater(registry, system_info)
    doctor = Doctor(registry, system_info)

    services = {
        "db": db,
        "registry": registry,
        "checker": checker,
        "config": config,
        "installer": installer,
        "updater": updater,
        "doctor": doctor,
    }
    
    window = MainWindow(services)
    window.show()
    
    def step1_refresh():
        # Force a refresh and wait for it to complete
        window._refresh_status()
        QTimer.singleShot(2000, capture_dashboard)
        
    def capture_dashboard():
        window.grab().save("docs/screenshots/dashboard.png")
        window.tabs.setCurrentIndex(1)
        QTimer.singleShot(1000, capture_install_update)

    def capture_install_update():
        window.grab().save("docs/screenshots/install_update.png")
        window.tabs.setCurrentIndex(2)
        QTimer.singleShot(1000, capture_history)

    def capture_history():
        window.grab().save("docs/screenshots/history.png")
        app.quit()

    # Wait a bit for the window to appear before starting the process
    QTimer.singleShot(500, step1_refresh)
    
    sys.exit(app.exec())

if __name__ == "__main__":
    run()
