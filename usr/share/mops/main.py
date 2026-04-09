#!/usr/bin/env python3
import sys
import logging
from PyQt6.QtWidgets import QApplication
from config import ConfigManager
from gui import MainWindow

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.FileHandler('mops.log'), logging.StreamHandler()]
    )

def main():
    setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("Мопс Мессенджер")
    app.setOrganizationName("MopsTeam")
    config_manager = ConfigManager()
    window = MainWindow(config_manager)
    if (config_manager.config.user.auto_login and
        config_manager.config.user.username and
        config_manager.config.user.password):
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(100, window.show_login)
    else:
        window.show_login()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()