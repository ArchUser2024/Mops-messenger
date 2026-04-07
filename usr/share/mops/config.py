import json
import os
from dataclasses import dataclass, asdict
from enum import Enum

class ConnectionStatus(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    AUTHENTICATING = "authenticating"
    AUTHENTICATED = "authenticated"
    ERROR = "error"

@dataclass
class ServerConfig:
    host: str = "lazycat.foneonlab.ru"
    port: int = 5222
    use_ssl: bool = True
    use_tls: bool = True
    resource: str = "MopsDesktop"

@dataclass
class UserConfig:
    username: str = ""
    password: str = ""
    auto_login: bool = False
    save_password: bool = False

@dataclass
class AppConfig:
    server: ServerConfig = None
    user: UserConfig = None
    window_geometry: dict = None

    def __post_init__(self):
        if self.server is None:
            self.server = ServerConfig()
        if self.user is None:
            self.user = UserConfig()
        if self.window_geometry is None:
            self.window_geometry = {"width": 1200, "height": 800, "x": 100, "y": 100}

class ConfigManager:
    def __init__(self, config_file="settings.json"):
        self.config_file = config_file
        self.config = self.load_config()

    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return AppConfig(
                    server=ServerConfig(**data.get('server', {})),
                    user=UserConfig(**data.get('user', {})),
                    window_geometry=data.get('window_geometry', {})
                )
            except Exception as e:
                print(f"Ошибка загрузки конфигурации: {e}")
        return AppConfig()

    def save_config(self):
        try:
            config_dict = {
                'server': asdict(self.config.server),
                'user': asdict(self.config.user),
                'window_geometry': self.config.window_geometry
            }
            if not self.config.user.save_password:
                config_dict['user']['password'] = ""
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_dict, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Ошибка сохранения конфигурации: {e}")

    def update_window_geometry(self, x, y, width, height):
        self.config.window_geometry = {'x': x, 'y': y, 'width': width, 'height': height}
        self.save_config()