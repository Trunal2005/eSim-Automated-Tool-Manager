"""GUI application entry point."""

import sys
import logging
from PyQt6.QtWidgets import QApplication

from esim_tool_manager.cli.app import get_services
from esim_tool_manager.gui.main_window import MainWindow
from esim_tool_manager.infra.logging_config import setup_logging

logger = logging.getLogger(__name__)


def main() -> None:
    """Entry point for the GUI application."""
    # Setup basic logging for GUI
    setup_logging(console_level=logging.INFO)
    logger.info("Starting eSim Tool Manager GUI...")
    
    app = QApplication(sys.argv)
    
    try:
        # Initialize core services
        services = get_services()
        
        # Create and show main window
        window = MainWindow(services)
        window.show()
        
        # Start event loop
        sys.exit(app.exec())
    except Exception as e:
        logger.critical("Failed to start GUI: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
