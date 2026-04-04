from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QCheckBox, QComboBox, 
    QFrame, QFileDialog, QSpinBox, QMessageBox
)
from PySide6.QtCore import Qt, Signal
import json
import os
from resource_utils import get_project_root

CONFIG_FILE = os.path.join(get_project_root(), "config.json")
ENV_FILE = os.path.join(get_project_root(), ".env")
PROXY_USER_ENV_KEY = "PROXY_USER"
PROXY_PASS_ENV_KEY = "PROXY_PASS"


def _parse_env_value(raw_value):
    value = raw_value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        if value[0] == '"':
            try:
                return json.loads(value)
            except Exception:
                pass
        return value[1:-1]
    return value


def _format_env_value(value):
    if value == "":
        return ""
    if any(ch.isspace() for ch in value) or any(ch in value for ch in '#=\\"'):
        return json.dumps(value)
    return value


def _load_env_values():
    env_values = {}
    if not os.path.exists(ENV_FILE):
        return env_values

    try:
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                key, value = stripped.split("=", 1)
                env_values[key.strip()] = _parse_env_value(value)
    except Exception as e:
        print(f"Error loading env values: {e}")

    return env_values


def _save_env_values(updates):
    lines = []
    if os.path.exists(ENV_FILE):
        try:
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            print(f"Error reading env file: {e}")

    new_lines = []
    handled_keys = set()
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            new_lines.append(line if line.endswith("\n") else f"{line}\n")
            continue

        key, _ = line.split("=", 1)
        key = key.strip()
        if key not in updates:
            new_lines.append(line if line.endswith("\n") else f"{line}\n")
            continue

        handled_keys.add(key)
        value = updates[key]
        if value:
            new_lines.append(f"{key}={_format_env_value(value)}\n")

    for key, value in updates.items():
        if key not in handled_keys and value:
            new_lines.append(f"{key}={_format_env_value(value)}\n")

    try:
        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
    except Exception as e:
        print(f"Error writing env file: {e}")


def _sanitize_config(config_data):
    sanitized = dict(config_data)
    proxy = dict(sanitized.get("proxy", {}))
    proxy.pop("user", None)
    proxy.pop("pass", None)
    sanitized["proxy"] = proxy
    return sanitized

def load_config():
    default_config = {
        "download_path": "downloads",
        "download_limit": 5,
        "max_speed_kb": 0,
        "dark_mode": None,  # None = follow Windows system setting
        "proxy": {
            "enabled": False,
            "type": "SOCKS5",
            "host": "",
            "port": "",
            "user": "",
            "pass": ""
        }
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                proxy_data = data.pop("proxy", {})
                default_config.update(data)
                if isinstance(proxy_data, dict):
                    default_config["proxy"].update(proxy_data)
        except Exception as e:
            print(f"Error loading config: {e}")

    env_values = _load_env_values()
    proxy = default_config.get("proxy", {})
    proxy["user"] = env_values.get(PROXY_USER_ENV_KEY, proxy.get("user", ""))
    proxy["pass"] = env_values.get(PROXY_PASS_ENV_KEY, proxy.get("pass", ""))
    return default_config

def save_config(config_data):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(_sanitize_config(config_data), f, indent=4)
    except Exception as e:
        print(f"Error saving config: {e}")

class SettingsView(QWidget):
    logoutRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(24)

        # Header
        lbl_header = QLabel("Settings")
        lbl_header.setObjectName("MainHeaderLarge")
        layout.addWidget(lbl_header)

        # Card Container
        card = QFrame()
        card.setObjectName("WhiteCard")
        clayout = QVBoxLayout(card)
        clayout.setContentsMargins(24, 24, 24, 24)
        clayout.setSpacing(16)

        # 1. Download Path
        lbl_path = QLabel("Default Download Path")
        lbl_path.setObjectName("SectionHeader")
        
        path_row = QHBoxLayout()
        self.input_path = QLineEdit("downloads")
        self.input_path.setReadOnly(True)
        self.btn_browse = QPushButton("Browse...")
        self.btn_browse.setObjectName("SecondaryButton")
        self.btn_browse.clicked.connect(self.browse_path)
        
        self.btn_open = QPushButton("📂 Open")
        self.btn_open.setObjectName("PrimaryButton")
        self.btn_open.clicked.connect(self.open_folder)
        
        path_row.addWidget(self.input_path)
        path_row.addWidget(self.btn_browse)
        path_row.addWidget(self.btn_open)
        
        clayout.addWidget(lbl_path)
        clayout.addLayout(path_row)

        # Divider
        div1 = QFrame()
        div1.setObjectName("Divider")
        clayout.addWidget(div1)

        # 2. Proxy Settings
        lbl_proxy = QLabel("Proxy Configuration")
        lbl_proxy.setObjectName("SectionHeader")
        clayout.addWidget(lbl_proxy)
        
        self.chk_enable_proxy = QCheckBox("Enable Proxy")
        clayout.addWidget(self.chk_enable_proxy)

        proxy_form = QVBoxLayout()
        proxy_row1 = QHBoxLayout()
        
        self.combo_proxy_type = QComboBox()
        self.combo_proxy_type.addItems(["SOCKS5", "SOCKS4", "HTTP"])
        self.input_proxy_host = QLineEdit()
        self.input_proxy_host.setPlaceholderText("Host/IP")
        self.input_proxy_port = QLineEdit()
        self.input_proxy_port.setPlaceholderText("Port")
        
        proxy_row1.addWidget(self.combo_proxy_type)
        proxy_row1.addWidget(self.input_proxy_host)
        proxy_row1.addWidget(self.input_proxy_port)
        proxy_form.addLayout(proxy_row1)
        
        proxy_row2 = QHBoxLayout()
        self.input_proxy_user = QLineEdit()
        self.input_proxy_user.setPlaceholderText("Username (Optional)")
        self.input_proxy_pass = QLineEdit()
        self.input_proxy_pass.setPlaceholderText("Password (Optional)")
        self.input_proxy_pass.setEchoMode(QLineEdit.Password)
        
        proxy_row2.addWidget(self.input_proxy_user)
        proxy_row2.addWidget(self.input_proxy_pass)
        proxy_form.addLayout(proxy_row2)
        
        clayout.addLayout(proxy_form)

        # Divider
        div2 = QFrame()
        div2.setObjectName("Divider")
        clayout.addWidget(div2)

        # 3. Download Limits
        lbl_limits = QLabel("Download Limits")
        lbl_limits.setObjectName("SectionHeader")
        clayout.addWidget(lbl_limits)
        
        limit_form = QVBoxLayout()
        limit_row1 = QHBoxLayout()
        self.lbl_limit_desc = QLabel("Concurrent Downloads:")
        self.spin_limit = QSpinBox()
        self.spin_limit.setRange(1, 100)
        self.spin_limit.setValue(5)
        limit_row1.addWidget(self.lbl_limit_desc)
        limit_row1.addWidget(self.spin_limit)
        limit_row1.addStretch()
        
        limit_row2 = QHBoxLayout()
        self.lbl_speed_desc = QLabel("Max Speed (KB/s, 0=unlimited):")
        self.spin_speed = QSpinBox()
        self.spin_speed.setRange(0, 999999)
        self.spin_speed.setValue(0)
        limit_row2.addWidget(self.lbl_speed_desc)
        limit_row2.addWidget(self.spin_speed)
        limit_row2.addStretch()
        
        limit_form.addLayout(limit_row1)
        limit_form.addLayout(limit_row2)
        clayout.addLayout(limit_form)

        # Divider
        div3 = QFrame()
        div3.setObjectName("Divider")
        clayout.addWidget(div3)

        # 4. Save Button
        save_row = QHBoxLayout()
        self.btn_save = QPushButton("Save Config")
        self.btn_save.setObjectName("SuccessButton")
        self.btn_save.clicked.connect(self.save_settings)
        save_row.addStretch()
        save_row.addWidget(self.btn_save)
        clayout.addLayout(save_row)

        clayout.addWidget(QFrame(frameShape=QFrame.HLine, frameShadow=QFrame.Sunken))
        
        logout_row = QHBoxLayout()
        self.btn_logout = QPushButton("🚪 Logout from Telegram")
        self.btn_logout.setObjectName("LogoutBtn") # Assumed styled already
        self.btn_logout.setCursor(Qt.PointingHandCursor)
        self.btn_logout.clicked.connect(self.logout_clicked)
        logout_row.addWidget(self.btn_logout)
        logout_row.addStretch()
        clayout.addLayout(logout_row)

        layout.addWidget(card)
        layout.addStretch()
        
        self.load_settings()

    def load_settings(self):
        config = load_config()
        self.input_path.setText(config.get("download_path", "downloads"))
        self.spin_limit.setValue(config.get("download_limit", 5))
        self.spin_speed.setValue(config.get("max_speed_kb", 0))
        
        proxy = config.get("proxy", {})
        self.chk_enable_proxy.setChecked(proxy.get("enabled", False))
        self.combo_proxy_type.setCurrentText(proxy.get("type", "SOCKS5"))
        self.input_proxy_host.setText(proxy.get("host", ""))
        self.input_proxy_port.setText(str(proxy.get("port", "")))
        self.input_proxy_user.setText(proxy.get("user", ""))
        self.input_proxy_pass.setText(proxy.get("pass", ""))

    def save_settings(self):
        config = {
            "download_path": self.input_path.text(),
            "download_limit": self.spin_limit.value(),
            "max_speed_kb": self.spin_speed.value(),
            "proxy": {
                "enabled": self.chk_enable_proxy.isChecked(),
                "type": self.combo_proxy_type.currentText(),
                "host": self.input_proxy_host.text(),
                "port": self.input_proxy_port.text()
            }
        }
        save_config(config)
        _save_env_values({
            PROXY_USER_ENV_KEY: self.input_proxy_user.text(),
            PROXY_PASS_ENV_KEY: self.input_proxy_pass.text()
        })
        # Notify user it was saved properly
        QMessageBox.information(self, "Settings Saved", "Configuration saved successfully!")

    def browse_path(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Download Directory")
        if folder:
            self.input_path.setText(folder)

    def open_folder(self):
        path = self.input_path.text()
        if os.path.exists(path):
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(path)))
        else:
            QMessageBox.warning(self, "Folder Not Found", f"The directory does not exist yet:\n{path}")

    def logout_clicked(self):
        self.logoutRequested.emit()
