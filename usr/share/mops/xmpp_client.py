import asyncio
import slixmpp
import ssl
import logging
from typing import Dict, Optional
from dataclasses import dataclass
from PyQt6.QtCore import QObject, pyqtSignal, QThread

logger = logging.getLogger(__name__)

@dataclass
class Contact:
    jid: str
    name: str
    status: str = "offline"
    show: str = "offline"
    subscription: str = "none"

    @property
    def is_online(self) -> bool:
        return self.show not in ['offline', 'unavailable']


class SimpleXMPPClient(slixmpp.ClientXMPP):
    def __init__(self, jid: str, password: str):
        super().__init__(jid, password)

        # Базовые плагины
        self.register_plugin('xep_0030')
        self.register_plugin('xep_0199')
        self.register_plugin('xep_0045')
        self.register_plugin('xep_0085')

        # Обработчики
        self.add_event_handler("session_start", self.on_session_start)
        self.add_event_handler("message", self.on_message)
        self.add_event_handler("presence", self.on_presence)
        self.add_event_handler("disconnected", self.on_disconnected)

        self.message_callback = None
        self.presence_callback = None
        self.login_success_callback = None

    async def on_session_start(self, event):
        self.send_presence()
        await self.get_roster()
        if self.login_success_callback:
            self.login_success_callback()

    def on_message(self, msg):
        if msg['type'] in ('chat', 'normal') and msg['body']:
            from_jid = str(msg['from']).split('/')[0]
            if self.message_callback:
                self.message_callback(from_jid, msg['body'])

    def on_presence(self, pres):
        from_jid = str(pres['from']).split('/')[0]
        show = pres['show'] or 'offline'
        status = pres['status'] or ''
        if self.presence_callback:
            self.presence_callback(from_jid, show, status)

    def on_disconnected(self, event):
        logger.info("Отключено от сервера")

    def send_chat_message(self, to_jid: str, message: str):
        try:
            self.send_message(mto=to_jid, mbody=message, mtype='chat')
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения: {e}")
            return False


class XMPPWorker(QObject):
    connection_status = pyqtSignal(str)
    message_received = pyqtSignal(str, str)
    contact_updated = pyqtSignal(object)
    login_success = pyqtSignal()
    login_failed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.jid = None
        self.password = None
        self.server = None
        self.port = None
        self.use_legacy_ssl = False
        self.client = None
        self.loop = None

    def login(self, jid, password, server, port, use_legacy_ssl=False):
        self.jid = jid
        self.password = password
        self.server = server
        self.port = port
        self.use_legacy_ssl = use_legacy_ssl
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._run())

    async def _run(self):
        self.client = SimpleXMPPClient(self.jid, self.password)
        self.client.message_callback = self._on_message
        self.client.presence_callback = self._on_presence
        self.client.login_success_callback = lambda: self.login_success.emit()

        self.connection_status.emit("Подключение...")
        try:
            if self.use_legacy_ssl:
                # Создаём SSL-контекст с отключённой проверкой сертификата
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                self.client.ssl_context = ctx
            # Подключаемся (передаём кортеж (host, port) — работает во всех версиях slixmpp)
            await self.client.connect((self.server, self.port))

            self.connection_status.emit("Аутентификация...")
            # Ждём события отключения (клиент работает в фоне)
            disconnected = asyncio.Event()
            self.client.add_event_handler("disconnected", lambda e: disconnected.set())
            await disconnected.wait()

        except Exception as e:
            self.login_failed.emit(str(e))
        finally:
            if self.client:
                self.client.disconnect()

    def _on_message(self, from_jid, body):
        self.message_received.emit(from_jid, body)

    def _on_presence(self, from_jid, show, status):
        contact = Contact(jid=from_jid, name=from_jid.split('@')[0], show=show, status=status)
        self.contact_updated.emit(contact)

    def send_message(self, to_jid, message):
        if self.client:
            self.client.send_chat_message(to_jid, message)

    def disconnect(self):
        if self.client:
            self.client.disconnect()
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)


class XMPPThread(QThread):
    connection_status = pyqtSignal(str)
    message_received = pyqtSignal(str, str)
    contact_updated = pyqtSignal(object)
    login_success = pyqtSignal()
    login_failed = pyqtSignal(str)

    def __init__(self, jid, password, server, port, use_legacy_ssl=False):
        super().__init__()
        self.jid = jid
        self.password = password
        self.server = server
        self.port = port
        self.use_legacy_ssl = use_legacy_ssl
        self.worker = None

    def run(self):
        self.worker = XMPPWorker()
        self.worker.connection_status.connect(self.connection_status)
        self.worker.message_received.connect(self.message_received)
        self.worker.contact_updated.connect(self.contact_updated)
        self.worker.login_success.connect(self.login_success)
        self.worker.login_failed.connect(self.login_failed)
        self.worker.login(self.jid, self.password, self.server, self.port, self.use_legacy_ssl)

    def send_message(self, to_jid, message):
        if self.worker:
            self.worker.send_message(to_jid, message)

    def disconnect(self):
        if self.worker:
            self.worker.disconnect()
            self.worker = None
