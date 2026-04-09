import sys
import logging
import socket
import threading
from datetime import datetime
from typing import Optional, Dict

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QListWidget, QTextEdit, QLineEdit, QPushButton,
    QLabel, QStatusBar, QMenuBar, QMenu, QDialog, QFormLayout,
    QDialogButtonBox, QListWidgetItem, QMessageBox, QTabWidget,
    QInputDialog, QSystemTrayIcon, QStyle, QCheckBox, QProgressBar
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSize, QEvent
from PyQt6.QtGui import QFont, QColor, QAction, QPixmap, QPainter, QBrush, QTextCursor

from config import ConfigManager
from xmpp_client import XMPPThread, Contact

logger = logging.getLogger(__name__)


class LoginDialog(QDialog):
    login_requested = pyqtSignal(str, str, str, int)

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle("Вход в Мопс")
        self.setModal(True)
        self.setFixedSize(400, 400)
        layout = QVBoxLayout()

        title = QLabel("🔐 Мессенджер Мопс")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        form = QFormLayout()
        self.server_input = QLineEdit(self.config_manager.config.server.host)
        self.server_input.setPlaceholderText("lazycat.foneonlab.ru")
        form.addRow("Сервер:", self.server_input)

        self.port_input = QLineEdit(str(self.config_manager.config.server.port))
        self.port_input.setPlaceholderText("5222")
        form.addRow("Порт:", self.port_input)

        self.username_input = QLineEdit(self.config_manager.config.user.username)
        self.username_input.setPlaceholderText("логин (без @домен)")
        form.addRow("Логин:", self.username_input)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Пароль")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        if self.config_manager.config.user.save_password:
            self.password_input.setText(self.config_manager.config.user.password)
        form.addRow("Пароль:", self.password_input)

        settings = QVBoxLayout()
        self.save_password_check = QCheckBox("Сохранить пароль")
        self.save_password_check.setChecked(self.config_manager.config.user.save_password)
        settings.addWidget(self.save_password_check)
        self.auto_login_check = QCheckBox("Автоматический вход")
        self.auto_login_check.setChecked(self.config_manager.config.user.auto_login)
        settings.addWidget(self.auto_login_check)
        form.addRow("Настройки:", settings)
        layout.addLayout(form)

        hint = QLabel("Подсказка: введите только имя пользователя, домен добавится автоматически")
        hint.setStyleSheet("color: #888; font-size: 10px; padding: 5px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept_login)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

        if self.config_manager.config.user.auto_login and self.config_manager.config.user.username:
            QTimer.singleShot(100, self.auto_login)

    def auto_login(self):
        if self.config_manager.config.user.username and self.config_manager.config.user.password:
            self.accept_login()

    def accept_login(self):
        server = self.server_input.text().strip()
        port_text = self.port_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text()

        if not server or not username or not password:
            QMessageBox.warning(self, "Ошибка", "Заполните все поля")
            return
        try:
            port = int(port_text) if port_text else 5222
            if not (1 <= port <= 65535):
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "Ошибка", "Неверный порт (1-65535)")
            return

        self.config_manager.config.server.host = server
        self.config_manager.config.server.port = port
        self.config_manager.config.user.username = username
        self.config_manager.config.user.save_password = self.save_password_check.isChecked()
        self.config_manager.config.user.auto_login = self.auto_login_check.isChecked()
        if self.save_password_check.isChecked():
            self.config_manager.config.user.password = password
        else:
            self.config_manager.config.user.password = ""
        self.config_manager.save_config()

        self.login_requested.emit(username, password, server, port)
        self.accept()


class ContactItemWidget(QWidget):
    def __init__(self, contact: Contact):
        super().__init__()
        self.contact = contact
        self.setup_ui()
        self.update_ui()

    def setup_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(8, 4, 8, 4)
        self.status_indicator = QLabel("●")
        self.status_indicator.setFixedSize(12, 12)
        self.avatar_label = QLabel()
        self.avatar_label.setFixedSize(36, 36)
        info = QVBoxLayout()
        info.setSpacing(2)
        self.name_label = QLabel()
        self.name_label.setStyleSheet("font-weight: bold;")
        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: #888; font-size: 11px;")
        info.addWidget(self.name_label)
        info.addWidget(self.status_label)
        layout.addWidget(self.status_indicator)
        layout.addWidget(self.avatar_label)
        layout.addLayout(info)
        self.setLayout(layout)

    def update_ui(self):
        self.name_label.setText(self.contact.name)
        self.status_label.setText(self.get_status_text())
        self.update_avatar()
        self.update_status_indicator()

    def get_status_text(self):
        m = {'chat': '🟢 Онлайн', 'away': '🟡 Отошел', 'xa': '⚫ Недоступен', 'dnd': '🔴 Не беспокоить', 'offline': '⚪ Офлайн'}
        return m.get(self.contact.show, self.contact.show)

    def update_avatar(self):
        pixmap = QPixmap(36, 36)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self.get_status_color()
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, 36, 36)
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, self.contact.name[0].upper())
        painter.end()
        self.avatar_label.setPixmap(pixmap)

    def get_status_color(self):
        colors = {'chat': QColor(76, 175, 80), 'away': QColor(255, 152, 0),
                  'xa': QColor(255, 87, 34), 'dnd': QColor(244, 67, 54), 'offline': QColor(158, 158, 158)}
        return colors.get(self.contact.show, QColor(158, 158, 158))

    def update_status_indicator(self):
        color = self.get_status_color()
        self.status_indicator.setStyleSheet(f"QLabel {{ color: {color.name()}; font-weight: bold; font-size: 14px; }}")

    def update_contact(self, contact):
        self.contact = contact
        self.update_ui()


class ChatWindow(QWidget):
    send_message_signal = pyqtSignal(str, str)

    def __init__(self, contact_jid: str, contact_name: str):
        super().__init__()
        self.contact_jid = contact_jid
        self.contact_name = contact_name
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        header = QLabel(f"💬 Чат с {self.contact_name}")
        header.setStyleSheet("background-color: #333; padding: 10px; border-bottom: 1px solid #444; font-weight: bold;")
        layout.addWidget(header)

        self.history = QTextEdit()
        self.history.setReadOnly(True)
        self.history.setStyleSheet("background-color: #1e1e1e; color: white; border: none; font-size: 13px; padding: 10px;")
        layout.addWidget(self.history)

        input_panel = QWidget()
        input_layout = QHBoxLayout(input_panel)
        input_layout.setContentsMargins(10, 10, 10, 10)
        self.message_input = QLineEdit()
        self.message_input.setPlaceholderText("Введите сообщение...")
        self.message_input.setStyleSheet("padding: 10px; border: 2px solid #4CAF50; border-radius: 5px; background-color: #2b2b2b; color: white;")
        self.message_input.returnPressed.connect(self._send_message)
        self.send_button = QPushButton("Отправить")
        self.send_button.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 10px 20px; border: none; border-radius: 5px;")
        self.send_button.clicked.connect(self._send_message)
        input_layout.addWidget(self.message_input)
        input_layout.addWidget(self.send_button)
        layout.addWidget(input_panel)

        self.setLayout(layout)

    def add_message(self, message: str, sender: str, is_own: bool = False):
        timestamp = datetime.now().strftime("%H:%M")
        if is_own:
            alignment, bg, color = "right", "#2E7D32", "#4CAF50"
        else:
            alignment, bg, color = "left", "#424242", "#2196F3"
        html = f"""
        <div style="margin: 10px 0; text-align: {alignment};">
            <div style="color: {color}; font-size: 11px; margin-bottom: 3px;">
                {sender} <span style="color: #888;">{timestamp}</span>
            </div>
            <div style="background-color: {bg}; color: white; padding: 8px 12px; border-radius: 12px; display: inline-block; max-width: 70%; word-wrap: break-word; text-align: left;">
                {message.replace('\n', '<br>')}
            </div>
        </div>
        """
        self.history.insertHtml(html)
        self.history.verticalScrollBar().setValue(self.history.verticalScrollBar().maximum())

    def _send_message(self):
        msg = self.message_input.text().strip()
        if msg:
            self.send_message_signal.emit(self.contact_jid, msg)
            self.add_message(msg, "Вы", is_own=True)
            self.message_input.clear()


class ConnectionTestDialog(QDialog):
    def __init__(self, server: str, port: int, parent=None):
        super().__init__(parent)
        self.server = server
        self.port = port
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle("Диагностика подключения")
        self.setModal(True)
        self.setFixedSize(550, 450)
        layout = QVBoxLayout()
        title = QLabel(f"Тестирование подключения к {self.server}")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setStyleSheet("background-color: #1e1e1e; color: white; font-family: monospace; font-size: 12px; padding: 10px; border: 1px solid #444;")
        layout.addWidget(self.output)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        btn = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn.rejected.connect(self.reject)
        layout.addWidget(btn)
        self.setLayout(layout)
        threading.Thread(target=self.run_tests, daemon=True).start()

    def log(self, msg, error=False):
        color = "#ff4444" if error else "#44ff44"
        prefix = "✗" if error else "✓"
        self.output.append(f'<span style="color: {color};">{prefix} {msg}</span>')
        self.output.verticalScrollBar().setValue(self.output.verticalScrollBar().maximum())

    def run_tests(self):
        self.log("=== Диагностика подключения ===\n")
        self.log("1. Проверка DNS...")
        try:
            ip = socket.gethostbyname(self.server)
            self.log(f"DNS разрешен: {self.server} → {ip}")
        except Exception as e:
            self.log(f"Ошибка DNS: {e}", error=True)

        self.log("\n2. Проверка портов:")
        for port in [5222, 5223, 9090, 5229, 5269]:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                res = sock.connect_ex((self.server, port))
                sock.close()
                if res == 0:
                    self.log(f"Порт {port} открыт")
                else:
                    self.log(f"Порт {port} закрыт", error=True)
            except:
                self.log(f"Порт {port}: ошибка проверки", error=True)

        self.log("\n=== Рекомендации ===")
        self.log("• Порт 5222 – обычное XMPP-соединение (без шифрования)")
        self.log("• Порт 5223 – устаревшее SSL-соединение")
        self.log("• Порт 9090 – веб-интерфейс Openfire")
        self.log("• Используйте порт 5222, если он открыт, и 5223, если нет.")
        self.progress.setValue(100)


class MainWindow(QMainWindow):
    def __init__(self, config_manager: ConfigManager):
        super().__init__()
        self.config_manager = config_manager
        self.xmpp_thread = None
        self.contacts: Dict[str, Contact] = {}
        self.chat_windows: Dict[str, ChatWindow] = {}
        self.current_chat = None
        self.setup_ui()
        self.setup_menu()
        self.setup_tray()
        g = self.config_manager.config.window_geometry
        self.setGeometry(g['x'], g['y'], g['width'], g['height'])

    def setup_ui(self):
        self.setWindowTitle("Мопс Мессенджер")
        self.setStyleSheet("QMainWindow { background-color: #2b2b2b; } QWidget { color: white; font-family: 'Segoe UI', Arial; }")
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        contacts_panel = QWidget()
        contacts_panel.setMinimumWidth(250)
        contacts_layout = QVBoxLayout(contacts_panel)
        contacts_layout.setContentsMargins(0, 0, 0, 0)
        contacts_header = QLabel("👥 Контакты")
        contacts_header.setStyleSheet("background-color: #333; padding: 15px; font-size: 14px; font-weight: bold; border-bottom: 1px solid #444;")
        contacts_layout.addWidget(contacts_header)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Поиск контактов...")
        self.search_input.setStyleSheet("padding: 10px; border: none; border-bottom: 1px solid #444; background-color: #333;")
        self.search_input.textChanged.connect(self.filter_contacts)
        contacts_layout.addWidget(self.search_input)
        self.contacts_list = QListWidget()
        self.contacts_list.setStyleSheet("QListWidget { background-color: #2b2b2b; border: none; outline: none; } QListWidget::item { border-bottom: 1px solid #333; } QListWidget::item:hover { background-color: #3a3a3a; } QListWidget::item:selected { background-color: #4CAF50; }")
        self.contacts_list.itemClicked.connect(self.open_chat)
        contacts_layout.addWidget(self.contacts_list)
        splitter.addWidget(contacts_panel)

        self.chat_area = QTabWidget()
        self.chat_area.setTabsClosable(True)
        self.chat_area.tabCloseRequested.connect(self.close_chat_tab)
        self.chat_area.setStyleSheet("QTabWidget::pane { border: none; background-color: #2b2b2b; } QTabBar::tab { background-color: #333; color: white; padding: 8px 16px; margin-right: 2px; border-radius: 4px 4px 0 0; } QTabBar::tab:selected { background-color: #4CAF50; } QTabBar::tab:hover:!selected { background-color: #444; }")
        splitter.addWidget(self.chat_area)
        splitter.setStretchFactor(1, 3)
        main_layout.addWidget(splitter)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel("Не подключено")
        self.status_bar.addPermanentWidget(self.status_label)
        self.connection_indicator = QLabel("●")
        self.connection_indicator.setStyleSheet("color: #f44336; font-weight: bold;")
        self.status_bar.addPermanentWidget(self.connection_indicator)
        self.test_button = QPushButton("Тест")
        self.test_button.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; padding: 4px 8px; border: none; border-radius: 3px; font-size: 10px;")
        self.test_button.clicked.connect(self.quick_test)
        self.status_bar.addPermanentWidget(self.test_button)

    def setup_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("Файл")
        login_action = QAction("Вход", self); login_action.triggered.connect(self.show_login); file_menu.addAction(login_action)
        logout_action = QAction("Выход", self); logout_action.triggered.connect(self.logout); file_menu.addAction(logout_action)
        file_menu.addSeparator()
        exit_action = QAction("Выход", self); exit_action.triggered.connect(self.close); file_menu.addAction(exit_action)
        contacts_menu = menubar.addMenu("Контакты")
        add_action = QAction("Добавить контакт", self); add_action.triggered.connect(self.add_contact); contacts_menu.addAction(add_action)
        refresh_action = QAction("Обновить список", self); refresh_action.triggered.connect(self.refresh_contacts); contacts_menu.addAction(refresh_action)
        settings_menu = menubar.addMenu("Настройки")
        diag_action = QAction("Диагностика подключения", self); diag_action.triggered.connect(self.show_diagnostic); settings_menu.addAction(diag_action)
        ssl_info = QAction("Информация о SSL/TLS", self); ssl_info.triggered.connect(self.show_ssl_info); settings_menu.addAction(ssl_info)
        view_menu = menubar.addMenu("Вид")
        toggle_contacts = QAction("Показать/скрыть контакты", self); toggle_contacts.triggered.connect(self.toggle_contacts_panel); view_menu.addAction(toggle_contacts)
        help_menu = menubar.addMenu("Помощь")
        about_action = QAction("О программе", self); about_action.triggered.connect(self.show_about); help_menu.addAction(about_action)

    def setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
        tray_menu = QMenu()
        show_action = QAction("Показать", self); show_action.triggered.connect(self.show); tray_menu.addAction(show_action)
        hide_action = QAction("Скрыть", self); hide_action.triggered.connect(self.hide); tray_menu.addAction(hide_action)
        tray_menu.addSeparator()
        quit_action = QAction("Выход", self); quit_action.triggered.connect(self.close); tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_activated)
        self.tray_icon.show()

    def tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show(); self.activateWindow()

    def show_login(self):
        dialog = LoginDialog(self.config_manager, self)
        dialog.login_requested.connect(self.login)
        dialog.exec()

    def login(self, username, password, server, port):
        if '@' not in username:
            username = f"{username}@{server}"
            logger.info(f"JID: {username}")
        self.update_status(f"Подключение к {server}:{port}...")
        self.connection_indicator.setStyleSheet("color: #ff9800; font-weight: bold;")
        if self.xmpp_thread:
            self.xmpp_thread.disconnect()
            self.xmpp_thread.wait()
            self.xmpp_thread = None
        use_legacy_ssl = (port == 5223)
        logger.info(f"Режим: {'legacy SSL' if use_legacy_ssl else 'обычное'}")
        self.xmpp_thread = XMPPThread(username, password, server, port, use_legacy_ssl=use_legacy_ssl)
        self.xmpp_thread.connection_status.connect(self.on_connection_status)
        self.xmpp_thread.message_received.connect(self.on_message_received)
        self.xmpp_thread.contact_updated.connect(self.on_contact_updated)
        self.xmpp_thread.login_success.connect(self.on_login_success)
        self.xmpp_thread.login_failed.connect(self.on_login_failed)
        self.xmpp_thread.start()

    def on_connection_status(self, status):
        self.update_status(status)
        if "подключено" in status.lower():
            self.connection_indicator.setStyleSheet("color: #ff9800; font-weight: bold;")
        elif "аутентификация" in status.lower():
            self.connection_indicator.setStyleSheet("color: #ff9800; font-weight: bold;")
        elif "вход выполнен" in status.lower():
            self.connection_indicator.setStyleSheet("color: #4caf50; font-weight: bold;")
        elif "ошибка" in status.lower():
            self.connection_indicator.setStyleSheet("color: #f44336; font-weight: bold;")

    def on_message_received(self, from_jid, message):
        if from_jid in self.chat_windows:
            self.chat_windows[from_jid].add_message(message, from_jid.split('@')[0])
        else:
            contact_name = self.contacts.get(from_jid, from_jid.split('@')[0])
            self.show_notification(f"Новое сообщение от {contact_name}", message)
            if from_jid in self.contacts:
                item = self.find_contact_item(from_jid)
                if item:
                    w = self.contacts_list.itemWidget(item)
                    if w:
                        w.name_label.setStyleSheet("font-weight: bold; color: #4CAF50;")

    def on_contact_updated(self, contact):
        self.contacts[contact.jid] = contact
        item = self.find_contact_item(contact.jid)
        if item:
            w = self.contacts_list.itemWidget(item)
            if w:
                w.update_contact(contact)
        else:
            self.add_contact_to_list(contact)

    def on_login_success(self):
        self.update_status("Вход выполнен")
        QMessageBox.information(self, "Успех", "✓ Вход выполнен успешно!")

    def on_login_failed(self, error):
        self.update_status(f"Ошибка: {error}")
        msg = QMessageBox(self)
        msg.setWindowTitle("Ошибка подключения")
        msg.setIcon(QMessageBox.Icon.Critical)
        msg.setText(f"✗ Не удалось войти\n\n{error}\n\nВозможные причины:\n1. Сервер недоступен\n2. Неправильный логин/пароль\n3. Порт заблокирован")
        test_btn = msg.addButton("Диагностика", QMessageBox.ButtonRole.ActionRole)
        msg.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
        msg.exec()
        if msg.clickedButton() == test_btn:
            self.show_diagnostic()
        self.connection_indicator.setStyleSheet("color: #f44336; font-weight: bold;")

    def find_contact_item(self, jid):
        for i in range(self.contacts_list.count()):
            item = self.contacts_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == jid:
                return item
        return None

    def add_contact_to_list(self, contact):
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, contact.jid)
        item.setSizeHint(QSize(200, 50))
        widget = ContactItemWidget(contact)
        self.contacts_list.addItem(item)
        self.contacts_list.setItemWidget(item, widget)

    def open_chat(self, item):
        jid = item.data(Qt.ItemDataRole.UserRole)
        contact = self.contacts.get(jid)
        if not contact:
            return
        if jid in self.chat_windows:
            idx = self.chat_area.indexOf(self.chat_windows[jid])
            self.chat_area.setCurrentIndex(idx)
        else:
            chat = ChatWindow(jid, contact.name)
            chat.send_message_signal.connect(self.send_message)
            self.chat_windows[jid] = chat
            idx = self.chat_area.addTab(chat, f"💬 {contact.name}")
            self.chat_area.setCurrentIndex(idx)
        self.current_chat = jid
        w = self.contacts_list.itemWidget(item)
        if w:
            w.name_label.setStyleSheet("font-weight: bold; color: white;")

    def send_message(self, to_jid, message):
        if self.xmpp_thread:
            self.xmpp_thread.send_message(to_jid, message)

    def close_chat_tab(self, index):
        w = self.chat_area.widget(index)
        for jid, cw in self.chat_windows.items():
            if cw == w:
                del self.chat_windows[jid]
                break
        self.chat_area.removeTab(index)
        if self.chat_area.count() == 0:
            self.current_chat = None

    def add_contact(self):
        if not self.xmpp_thread:
            QMessageBox.warning(self, "Ошибка", "Сначала выполните вход")
            return
        jid, ok = QInputDialog.getText(self, "Добавить контакт", "Введите JID контакта (user@server):")
        if ok and jid:
            QMessageBox.information(self, "Информация", f"Функция добавления контакта {jid} будет реализована")

    def refresh_contacts(self):
        if not self.xmpp_thread:
            QMessageBox.warning(self, "Ошибка", "Сначала выполните вход")
            return
        QMessageBox.information(self, "Обновление", "Список контактов обновляется...")

    def filter_contacts(self, text):
        for i in range(self.contacts_list.count()):
            item = self.contacts_list.item(i)
            jid = item.data(Qt.ItemDataRole.UserRole)
            contact = self.contacts.get(jid)
            if contact:
                match = text.lower() in contact.name.lower() or text.lower() in contact.jid.lower()
                item.setHidden(not match)

    def toggle_contacts_panel(self):
        splitter = self.centralWidget().layout().itemAt(0).widget()
        panel = splitter.widget(0)
        panel.setVisible(not panel.isVisible())

    def show_diagnostic(self):
        server = self.config_manager.config.server.host
        port = self.config_manager.config.server.port
        dlg = ConnectionTestDialog(server, port, self)
        dlg.exec()

    def quick_test(self):
        server = self.config_manager.config.server.host
        port = self.config_manager.config.server.port
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            res = sock.connect_ex((server, port))
            sock.close()
            if res == 0:
                QMessageBox.information(self, "Тест подключения", f"✓ Сервер {server}:{port} доступен")
            else:
                QMessageBox.critical(self, "Тест подключения", f"✗ Сервер {server}:{port} недоступен")
        except Exception as e:
            QMessageBox.critical(self, "Тест подключения", f"✗ Ошибка: {e}")

    def show_ssl_info(self):
        QMessageBox.information(self, "Информация о подключении",
            "<b>Настройки подключения:</b><br><br>"
            "• Порт 5222 – обычное XMPP-соединение (без шифрования)<br>"
            "• Порт 5223 – устаревшее SSL-соединение (legacy SSL)<br><br>"
            "Если сервер использует STARTTLS на порту 5222, используйте порт 5223 для шифрования.")

    def show_notification(self, title, msg):
        self.tray_icon.showMessage(title, msg[:100], QSystemTrayIcon.MessageIcon.Information, 3000)

    def update_status(self, msg):
        self.status_label.setText(f"Статус: {msg}")

    def show_about(self):
        QMessageBox.about(self, "О программе",
            "<h2>Мопс Мессенджер</h2><p>Версия 0.0.3</p>"
            "<p>Десктопный клиент для Openfire XMPP сервера</p>"
            "<p>Поддержка порта 5223 (SSL)</p>"
            f"<p>Сервер: {self.config_manager.config.server.host}:{self.config_manager.config.server.port}</p>"
            "<p>© 2026</p>")

    def logout(self):
        if self.xmpp_thread:
            self.xmpp_thread.disconnect()
            self.xmpp_thread.wait()
            self.xmpp_thread = None
        self.contacts_list.clear()
        self.chat_area.clear()
        self.chat_windows.clear()
        self.contacts.clear()
        self.update_status("Отключено")
        self.connection_indicator.setStyleSheet("color: #f44336; font-weight: bold;")

    def closeEvent(self, event):
        g = self.geometry()
        self.config_manager.update_window_geometry(g.x(), g.y(), g.width(), g.height())
        self.logout()
        event.ignore()
        self.hide()
        self.tray_icon.showMessage("Мопс Мессенджер", "Приложение продолжает работу в фоновом режиме",
                                   QSystemTrayIcon.MessageIcon.Information, 2000)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange and self.isMinimized():
            self.hide()
            self.tray_icon.showMessage("Мопс Мессенджер", "Приложение свернуто в трей",
                                       QSystemTrayIcon.MessageIcon.Information, 2000)
        super().changeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Мопс Мессенджер")
    cm = ConfigManager()
    win = MainWindow(cm)
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
