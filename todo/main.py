from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
from datetime import date, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from PySide6.QtCore import QEvent, QObject, QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizeGrip,
    QSizePolicy,
    QSplitter,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


APP_TITLE = "To Do List"
TASK_NAME = "TodoDailyReminder"
DEFAULT_REMINDER_TIME = "08:00"
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 49281

PALETTE = {
    "app_bg": "#edf2f7",
    "card_bg": "#fbfdff",
    "note_bg": "#f6f9fc",
    "row_bg": "#ffffff",
    "border": "#cfd8e3",
    "text": "#1f2937",
    "muted": "#64748b",
    "primary": "#295f88",
    "primary_hover": "#1f4c6d",
    "secondary": "#dbe7f3",
    "secondary_hover": "#c8d9ea",
    "badge_bg": "#eaf1f8",
    "badge_text": "#3c556d",
    "done_text": "#2d7a5f",
    "done_muted": "#94a3b8",
    "done_bg": "transparent",
}

DATE_FONT = QFont("Malgun Gothic", 12, QFont.DemiBold)
LABEL_FONT = QFont("Malgun Gothic", 9, QFont.DemiBold)
BODY_FONT = QFont("Malgun Gothic", 9)
META_FONT = QFont("Malgun Gothic", 9, QFont.DemiBold)


def app_directory() -> Path:
    if getattr(sys, "frozen", False):
        local_app_data = Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        target = local_app_data / "ToDoList"
        target.mkdir(parents=True, exist_ok=True)
        return target
    return Path(__file__).resolve().parent


DATA_FILE = app_directory() / "tasks.json"


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def today_text() -> str:
    return date.today().isoformat()


def current_month_text() -> str:
    return datetime.now().strftime("%Y-%m")


def task_display_text(title: str, completed: bool, completed_on: str = "") -> str:
    if completed and completed_on:
        return f"{title}  {completed_on}"
    return title


def reminder_time_choices() -> list[str]:
    return [f"{hour:02d}:{minute:02d}" for hour in range(24) for minute in range(0, 60, 5)]


def default_data() -> dict:
    return {
        "fixed_tasks": [],
        "flexible_tasks": [],
        "memo": "",
        "settings": {
            "reminder_time": DEFAULT_REMINDER_TIME,
            "last_popup_date": "",
            "fixed_reset_month": current_month_text(),
        },
    }


def sanitize_fixed_task(item: object) -> dict | None:
    if not isinstance(item, dict):
        return None
    title = str(item.get("title", "")).strip()
    task_id = item.get("id")
    if not title or not isinstance(task_id, int):
        return None
    return {
        "id": task_id,
        "title": title,
        "completed_month": str(item.get("completed_month", item.get("completed_on", "")))[:7],
        "completed_on": str(item.get("completed_on", ""))[:10],
    }


def sanitize_flexible_task(item: object) -> dict | None:
    if not isinstance(item, dict):
        return None
    title = str(item.get("title", "")).strip()
    task_id = item.get("id")
    if not title or not isinstance(task_id, int):
        return None
    return {
        "id": task_id,
        "title": title,
        "completed": bool(item.get("completed", False)),
        "created_at": str(item.get("created_at", "")),
        "completed_on": str(item.get("completed_on", ""))[:10],
    }


def load_data() -> dict:
    data = default_data()
    if not DATA_FILE.exists():
        return data
    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            raw = json.load(file)
    except (OSError, json.JSONDecodeError):
        return data

    if isinstance(raw, list):
        data["flexible_tasks"] = [task for item in raw if (task := sanitize_flexible_task(item)) is not None]
        return data

    if not isinstance(raw, dict):
        return data

    fixed_tasks = [task for item in raw.get("fixed_tasks", []) if (task := sanitize_fixed_task(item)) is not None]
    source_tasks = raw.get("flexible_tasks", raw.get("tasks", []))
    flexible_tasks = [task for item in source_tasks if (task := sanitize_flexible_task(item)) is not None]
    settings = raw.get("settings", {})
    data["fixed_tasks"] = fixed_tasks
    data["flexible_tasks"] = flexible_tasks
    data["memo"] = str(raw.get("memo", ""))
    data["settings"] = {
        "reminder_time": str(settings.get("reminder_time", DEFAULT_REMINDER_TIME)),
        "last_popup_date": str(settings.get("last_popup_date", "")),
        "fixed_reset_month": str(settings.get("fixed_reset_month", "")),
    }
    return data


def save_data(data: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with DATA_FILE.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def next_id(items: list[dict]) -> int:
    return max((int(item["id"]) for item in items), default=0) + 1


def parse_reminder_time(value: str) -> tuple[int, int] | None:
    text = value.strip()
    parts = text.split(":")
    if len(parts) != 2:
        return None
    if not parts[0].isdigit() or not parts[1].isdigit():
        return None
    hour = int(parts[0])
    minute = int(parts[1])
    if hour not in range(24) or minute not in range(60):
        return None
    return hour, minute


def is_due_for_reminder(data: dict, when: datetime | None = None) -> bool:
    current = when or datetime.now()
    reminder_time = str(data.get("settings", {}).get("reminder_time", DEFAULT_REMINDER_TIME))
    parsed = parse_reminder_time(reminder_time)
    if parsed is None:
        return False
    hour, minute = parsed
    target = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    last_popup_date = str(data.get("settings", {}).get("last_popup_date", ""))
    return current >= target and last_popup_date != current.date().isoformat()


def pythonw_path() -> Path:
    executable = Path(sys.executable)
    candidate = executable.with_name("pythonw.exe")
    return candidate if candidate.exists() else executable


def launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable).resolve()}"'
    return f'"{pythonw_path()}" "{Path(__file__).resolve()}"'


def decode_output(raw: bytes) -> str:
    for encoding in ("utf-8", "cp949"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode(errors="replace")


def scheduled_task_exists() -> bool:
    result = subprocess.run(["schtasks", "/Query", "/TN", TASK_NAME], capture_output=True, shell=False)
    return result.returncode == 0


def get_registered_task_time() -> str | None:
    result = subprocess.run(["schtasks", "/Query", "/TN", TASK_NAME, "/XML"], capture_output=True, shell=False)
    if result.returncode != 0:
        return None
    try:
        root = ET.fromstring(decode_output(result.stdout))
    except ET.ParseError:
        return None
    boundary = root.find(".//{*}StartBoundary")
    if boundary is None or not boundary.text or "T" not in boundary.text:
        return None
    return boundary.text.split("T", 1)[1][:5]


def register_daily_task(reminder_time: str = DEFAULT_REMINDER_TIME) -> str:
    if parse_reminder_time(reminder_time) is None:
        raise ValueError("알림 시간 형식은 HH:MM 이어야 합니다.")
    task_command = launch_command()
    result = subprocess.run(
        ["schtasks", "/Create", "/SC", "DAILY", "/TN", TASK_NAME, "/TR", task_command, "/ST", reminder_time, "/F"],
        capture_output=True,
        shell=False,
    )
    if result.returncode != 0:
        stderr_text = decode_output(result.stderr).strip()
        stdout_text = decode_output(result.stdout).strip()
        raise RuntimeError(stderr_text or stdout_text or "작업 스케줄러 등록에 실패했습니다.")
    return decode_output(result.stdout).strip() or "작업 스케줄러 등록 완료"


def send_command_to_existing_instance(command: str) -> bool:
    try:
        with socket.create_connection((SERVER_HOST, SERVER_PORT), timeout=0.4) as client:
            client.sendall(command.encode("utf-8"))
        return True
    except OSError:
        return False


class CommandSignals(QObject):
    command_received = Signal(str)


class CommandServer(threading.Thread):
    def __init__(self, signals: CommandSignals) -> None:
        super().__init__(daemon=True)
        self.signals = signals
        self.stop_event = threading.Event()
        self.server_socket: socket.socket | None = None

    def run(self) -> None:
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((SERVER_HOST, SERVER_PORT))
            self.server_socket.listen()
            self.server_socket.settimeout(1.0)
        except OSError:
            self.server_socket = None
            return

        while not self.stop_event.is_set():
            try:
                client, _address = self.server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            with client:
                try:
                    payload = client.recv(128).decode("utf-8").strip().upper()
                except OSError:
                    continue
            if payload:
                self.signals.command_received.emit(payload)

    def stop(self) -> None:
        self.stop_event.set()
        if self.server_socket is not None:
            try:
                self.server_socket.close()
            except OSError:
                pass


class FloatingLauncher(QWidget):
    restore_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(32, 32)
        self.setCursor(Qt.OpenHandCursor)
        self.setToolTip(APP_TITLE)
        self._drag_offset: QPoint | None = None
        self._press_global: QPoint | None = None
        self._moved = False

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(PALETTE["primary_hover"]), 1))
        painter.setBrush(QColor(PALETTE["primary"]))
        painter.drawEllipse(2, 2, 28, 28)
        painter.setPen(QColor(PALETTE["row_bg"]))
        painter.setFont(QFont("Segoe UI", 11, QFont.Black))
        painter.drawText(self.rect(), Qt.AlignCenter, "T")
        painter.end()
        super().paintEvent(event)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton:
            self._press_global = event.globalPosition().toPoint()
            self._drag_offset = event.position().toPoint()
            self._moved = False
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._drag_offset is not None and self._press_global is not None and event.buttons() & Qt.LeftButton:
            current_global = event.globalPosition().toPoint()
            if (current_global - self._press_global).manhattanLength() > 3:
                self._moved = True
            self.move(current_global - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton:
            should_restore = not self._moved
            self._drag_offset = None
            self._press_global = None
            self._moved = False
            self.setCursor(Qt.OpenHandCursor)
            if should_restore:
                self.restore_requested.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class TitleBar(QFrame):
    def __init__(self, owner: "TodoWindow") -> None:
        super().__init__(owner)
        self.owner = owner
        self.setProperty("titlebar", True)
        self.setFixedHeight(30)
        self._drag_offset: QPoint | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(7, 3, 5, 3)
        layout.setSpacing(3)

        icon_label = QLabel()
        icon_label.setPixmap(owner.app_icon.pixmap(14, 14))
        layout.addWidget(icon_label)

        title_label = QLabel(APP_TITLE)
        title_label.setFont(QFont("Malgun Gothic", 9, QFont.DemiBold))
        layout.addWidget(title_label)

        layout.addStretch(1)

        layout.addWidget(self._create_button("버튼", owner.minimize_to_button, 38, "action"))
        layout.addWidget(self._create_button("알림", owner.minimize_to_tray, 38, "action"))
        layout.addSpacing(2)
        layout.addWidget(self._create_button("-", owner.minimize_window, 24, "window"))
        self.maximize_button = self._create_button("[]", owner.toggle_maximized, 26, "window")
        layout.addWidget(self.maximize_button)
        layout.addWidget(self._create_button("X", owner.close, 24, "close"))

    def _create_button(self, text: str, handler, width: int, role: str) -> QPushButton:
        button = QPushButton(text)
        button.setFixedWidth(width)
        button.setProperty("titlebutton", True)
        button.setProperty("titlerole", role)
        button.clicked.connect(handler)
        return button

    def sync_window_state(self) -> None:
        self.maximize_button.setText("[]")

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[override]
        child = self.childAt(event.position().toPoint())
        if event.button() == Qt.LeftButton and not isinstance(child, QPushButton):
            self.owner.toggle_maximized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        child = self.childAt(event.position().toPoint())
        if event.button() == Qt.LeftButton and not isinstance(child, QPushButton):
            self._drag_offset = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton and not self.window().isMaximized():
            self.window().move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        self._drag_offset = None
        super().mouseReleaseEvent(event)


class TaskRowWidget(QFrame):
    toggled = Signal(bool)
    double_clicked = Signal()
    context_menu_requested = Signal(QPoint)
    drag_released = Signal(QPoint)

    def __init__(self, title: str, completed: bool, completed_on: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("taskrow", True)
        self._press_pos: QPoint | None = None
        self._dragging = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)

        self.checkbox = QCheckBox()
        self.checkbox.toggled.connect(self.toggled)
        layout.addWidget(self.checkbox)

        self.title_label = QLabel(title)
        self.title_label.setFont(BODY_FONT)
        self.title_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(self.title_label, 1)

        self.date_label = QLabel()
        self.date_label.setFont(BODY_FONT)
        self.date_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.date_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.date_label.setMinimumWidth(72)
        layout.addWidget(self.date_label, 0, Qt.AlignRight)

        self.set_completed(completed, completed_on)

    def contextMenuEvent(self, event) -> None:  # type: ignore[override]
        self.context_menu_requested.emit(event.globalPos())
        event.accept()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton:
            self._press_pos = event.position().toPoint()
            self._dragging = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._press_pos is not None and event.buttons() & Qt.LeftButton:
            if (event.position().toPoint() - self._press_pos).manhattanLength() >= QApplication.startDragDistance():
                self._dragging = True
                self.setCursor(Qt.SizeAllCursor)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton and self._press_pos is not None:
            dropped = self._dragging
            self._press_pos = None
            self._dragging = False
            self.unsetCursor()
            if dropped:
                self.drag_released.emit(event.globalPosition().toPoint())
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def set_completed(self, completed: bool, completed_on: str = "") -> None:
        self.checkbox.blockSignals(True)
        self.checkbox.setChecked(completed)
        self.checkbox.blockSignals(False)
        self.date_label.setText(completed_on if completed and completed_on else "")
        title_color = PALETTE["done_muted"] if completed else PALETTE["text"]
        date_color = "#a8b4c3" if completed else PALETTE["muted"]
        background = PALETTE["done_bg"] if completed else "transparent"
        title_font = QFont(BODY_FONT)
        title_font.setStrikeOut(completed)
        self.title_label.setFont(title_font)
        self.title_label.setStyleSheet(f"color: {title_color};")
        self.date_label.setStyleSheet(f"color: {date_color};")
        self.setStyleSheet(
            f"""
            QFrame[taskrow="true"] {{
                background: {background};
                border: none;
                border-radius: 6px;
            }}
            QCheckBox {{
                background: transparent;
                border: none;
            }}
            """
        )

    def toggle_checked(self) -> None:
        self.checkbox.setChecked(not self.checkbox.isChecked())


class TodoWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.data = load_data()
        self.app_icon = self._build_icon()
        self.memo_save_timer = QTimer(self)
        self.memo_save_timer.setSingleShot(True)
        self.memo_save_timer.setInterval(400)
        self.memo_save_timer.timeout.connect(self.save_memo)

        self.clock_timer = QTimer(self)
        self.clock_timer.setInterval(60_000)
        self.clock_timer.timeout.connect(self.refresh_clock)

        self.reminder_timer = QTimer(self)
        self.reminder_timer.setInterval(30_000)
        self.reminder_timer.timeout.connect(self.check_daily_reminder)

        self.command_signals = CommandSignals()
        self.command_signals.command_received.connect(self.handle_external_command)
        self.command_server = CommandServer(self.command_signals)

        self.floating_launcher: FloatingLauncher | None = None
        self.tray_mode = False

        self.title_bar: TitleBar | None = None
        self.date_label: QLabel | None = None
        self.reminder_time_combo: QComboBox | None = None
        self.register_button: QPushButton | None = None
        self.fixed_count_badge: QLabel | None = None
        self.flexible_count_badge: QLabel | None = None
        self.fixed_input: QLineEdit | None = None
        self.flexible_input: QLineEdit | None = None
        self.fixed_list: QListWidget | None = None
        self.flexible_list: QListWidget | None = None
        self.memo_edit: QTextEdit | None = None
        self.tray_icon: QSystemTrayIcon | None = None
        self.size_grip: QSizeGrip | None = None

        self.reset_fixed_tasks_if_needed()
        self._configure_window()
        self._build_ui()
        self._apply_styles()
        self._build_tray_icon()
        self.refresh_all()

        self.clock_timer.start()
        self.reminder_timer.start()
        self.command_server.start()

    def _configure_window(self) -> None:
        self.setWindowTitle(APP_TITLE)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.resize(520, 620)
        self.setMinimumSize(420, 430)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(3)

        self.title_bar = TitleBar(self)
        root.addWidget(self.title_bar)

        header = self._create_card()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(5, 4, 5, 4)
        header_layout.setSpacing(3)

        self.date_label = QLabel()
        self.date_label.setFont(DATE_FONT)
        self.date_label.setMinimumWidth(94)
        self.date_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        header_layout.addWidget(self.date_label)

        header_layout.addStretch(1)

        alert_label = QLabel("알림")
        alert_label.setFont(LABEL_FONT)
        header_layout.addWidget(alert_label)

        self.reminder_time_combo = QComboBox()
        self.reminder_time_combo.addItems(reminder_time_choices())
        self.reminder_time_combo.setCurrentText(str(self.data["settings"].get("reminder_time", DEFAULT_REMINDER_TIME)))
        self.reminder_time_combo.currentTextChanged.connect(self.refresh_register_button_state)
        self.reminder_time_combo.setFixedWidth(64)
        header_layout.addWidget(self.reminder_time_combo)

        self.register_button = QPushButton("등록")
        self.register_button.setFixedWidth(42)
        self.register_button.clicked.connect(self.register_schedule_from_ui)
        header_layout.addWidget(self.register_button)
        root.addWidget(header)

        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(5)
        splitter.setOpaqueResize(True)

        fixed_panel, self.fixed_input, self.fixed_list, self.fixed_count_badge = self._build_task_panel(
            "고정 할 일",
            include_cleanup=False,
        )
        self.fixed_input.returnPressed.connect(self.add_fixed_task)
        self.fixed_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.fixed_list.customContextMenuRequested.connect(lambda pos: self.show_task_menu_at_position(self.fixed_list, pos))
        splitter.addWidget(fixed_panel)

        flexible_panel, self.flexible_input, self.flexible_list, self.flexible_count_badge = self._build_task_panel(
            "수시 할 일",
            include_cleanup=True,
        )
        self.flexible_input.returnPressed.connect(self.add_flexible_task)
        self.flexible_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.flexible_list.customContextMenuRequested.connect(
            lambda pos: self.show_task_menu_at_position(self.flexible_list, pos)
        )
        splitter.addWidget(flexible_panel)

        memo_panel = self._build_memo_panel()
        splitter.addWidget(memo_panel)

        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 4)
        splitter.setStretchFactor(2, 2)
        splitter.setSizes([220, 220, 100])

        root.addWidget(splitter, 1)
        self.size_grip = QSizeGrip(central)
        self.size_grip.setFixedSize(18, 18)
        self.size_grip.setToolTip("창 크기 조절")
        self.size_grip.raise_()

    def _build_task_panel(
        self,
        title: str,
        include_cleanup: bool,
    ) -> tuple[QFrame, QLineEdit, QListWidget, QLabel]:
        panel = self._create_card()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(3)

        top = QHBoxLayout()
        top.setSpacing(3)

        title_label = QLabel(title)
        title_label.setFont(LABEL_FONT)
        top.addWidget(title_label)

        entry = QLineEdit()
        entry.setPlaceholderText("일정 추가")
        top.addWidget(entry, 1)

        add_button = QPushButton("추가")
        add_button.clicked.connect(self.add_fixed_task if not include_cleanup else self.add_flexible_task)
        top.addWidget(add_button)

        if include_cleanup:
            cleanup_button = QPushButton("정리")
            cleanup_button.clicked.connect(self.clear_completed_flexible_tasks)
            top.addWidget(cleanup_button)

        count_badge = self._create_badge("0")
        top.addWidget(count_badge)

        layout.addLayout(top)

        task_list = QListWidget()
        task_list.setSelectionMode(QListWidget.NoSelection)
        task_list.setEditTriggers(QListWidget.NoEditTriggers)
        task_list.setAlternatingRowColors(False)
        task_list.setFocusPolicy(Qt.NoFocus)
        task_list.setSpacing(0)
        task_list.setFrameShape(QFrame.NoFrame)
        task_list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        layout.addWidget(task_list, 1)

        return panel, entry, task_list, count_badge

    def _build_memo_panel(self) -> QFrame:
        panel = self._create_card(note=True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(3)

        title = QLabel("메모")
        title.setFont(LABEL_FONT)
        layout.addWidget(title)

        self.memo_edit = QTextEdit()
        self.memo_edit.textChanged.connect(self.schedule_memo_save)
        layout.addWidget(self.memo_edit, 1)
        return panel

    def _build_tray_icon(self) -> None:
        self.setWindowIcon(self.app_icon)
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setToolTip(APP_TITLE)
        self.tray_icon.setIcon(self.app_icon)
        self.tray_icon.activated.connect(self.on_tray_activated)

        menu = QMenu(self)
        open_action = menu.addAction("열기")
        open_action.triggered.connect(self.restore_main_window)
        exit_action = menu.addAction("종료")
        exit_action.triggered.connect(self.on_close)
        self.tray_icon.setContextMenu(menu)

    def _build_icon(self) -> QIcon:
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(PALETTE["primary_hover"]), 2))
        painter.setBrush(QColor(PALETTE["row_bg"]))
        painter.drawRoundedRect(8, 8, 48, 48, 10, 10)
        painter.fillRect(12, 12, 9, 40, QColor(PALETTE["primary"]))
        painter.setPen(QColor(PALETTE["primary_hover"]))
        painter.setFont(QFont("Segoe UI", 24, QFont.Black))
        painter.drawText(22, 47, "T")
        painter.setPen(QPen(QColor(PALETTE["border"]), 2))
        painter.drawLine(28, 18, 50, 18)
        painter.drawLine(28, 27, 46, 27)
        painter.drawLine(28, 36, 42, 36)
        painter.end()
        return QIcon(pixmap)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"""
            QMainWindow {{
                background: {PALETTE["app_bg"]};
            }}
            QFrame[titlebar="true"] {{
                background: #f7fbff;
                border: 1px solid {PALETTE["border"]};
                border-radius: 10px;
            }}
            QFrame[card="true"] {{
                background: {PALETTE["card_bg"]};
                border: 1px solid {PALETTE["border"]};
                border-radius: 13px;
            }}
            QFrame[note="true"] {{
                background: {PALETTE["note_bg"]};
                border: 1px solid {PALETTE["border"]};
                border-radius: 13px;
            }}
            QLabel {{
                color: {PALETTE["text"]};
            }}
            QLineEdit, QComboBox, QTextEdit, QListWidget {{
                background: {PALETTE["row_bg"]};
                border: 1px solid {PALETTE["border"]};
                border-radius: 9px;
                color: {PALETTE["text"]};
                padding: 3px 6px;
                font: 9pt "Malgun Gothic";
            }}
            QComboBox::drop-down {{
                border: none;
                width: 14px;
            }}
            QPushButton {{
                background: {PALETTE["secondary"]};
                border: 1px solid {PALETTE["border"]};
                border-radius: 9px;
                color: {PALETTE["text"]};
                padding: 3px 7px;
                font: 8pt "Malgun Gothic";
            }}
            QPushButton:hover {{
                background: {PALETTE["secondary_hover"]};
            }}
            QPushButton:disabled {{
                background: #eef3f8;
                color: #94a3b8;
                border-color: #d6e0ea;
            }}
            QPushButton[titlebutton="true"] {{
                padding: 2px 6px;
                border-radius: 8px;
                font: 8pt "Malgun Gothic";
            }}
            QPushButton[titlerole="window"] {{
                padding: 1px 4px;
                font: 8pt "Segoe UI";
            }}
            QPushButton[titlerole="close"] {{
                padding: 1px 4px;
                font: 8pt "Segoe UI";
            }}
            QPushButton[titlerole="close"]:hover {{
                background: #d46b62;
                color: #ffffff;
                border-color: #d46b62;
            }}
            QListWidget::item {{
                border: none;
                border-radius: 0;
                margin: 0;
                padding: 0;
                background: transparent;
            }}
            QListWidget::item:selected {{
                background: transparent;
                color: {PALETTE["text"]};
            }}
            QSplitter::handle {{
                background: transparent;
            }}
            QSplitter::handle:vertical {{
                height: 5px;
            }}
            QSizeGrip {{
                background: rgba(41, 95, 136, 0.12);
                border-top-left-radius: 6px;
            }}
            """
        )

    def _create_card(self, note: bool = False) -> QFrame:
        frame = QFrame()
        frame.setProperty("card", not note)
        frame.setProperty("note", note)
        return frame

    def _create_badge(self, text: str) -> QLabel:
        badge = QLabel(text)
        badge.setFont(LABEL_FONT)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(
            f"""
            QLabel {{
                background: {PALETTE["badge_bg"]};
                color: {PALETTE["badge_text"]};
                border: none;
                border-radius: 8px;
                padding: 2px 7px;
                font: 9pt "Malgun Gothic";
            }}
            """
        )
        return badge

    def refresh_all(self) -> None:
        self.reset_fixed_tasks_if_needed()
        self.refresh_clock()
        self.refresh_register_button_state()
        self.refresh_fixed_tasks()
        self.refresh_flexible_tasks()
        self.refresh_summary()
        if self.memo_edit is not None:
            self.memo_edit.blockSignals(True)
            self.memo_edit.setPlainText(self.data.get("memo", ""))
            self.memo_edit.blockSignals(False)

    def refresh_clock(self) -> None:
        if self.reset_fixed_tasks_if_needed():
            self.refresh_fixed_tasks()
            self.refresh_summary()
        if self.date_label is not None:
            self.date_label.setText(datetime.now().strftime("%Y-%m-%d"))

    def reset_fixed_tasks_if_needed(self) -> bool:
        settings = self.data.setdefault("settings", {})
        current_month = current_month_text()
        stored_month = str(settings.get("fixed_reset_month", ""))
        if stored_month == current_month:
            return False

        keep_current_state = not stored_month and any(
            task.get("completed_month") == current_month for task in self.data["fixed_tasks"]
        )
        if not keep_current_state:
            for task in self.data["fixed_tasks"]:
                task["completed_month"] = ""
                task["completed_on"] = ""

        settings["fixed_reset_month"] = current_month
        save_data(self.data)
        return True

    def refresh_register_button_state(self) -> None:
        if self.register_button is None or self.reminder_time_combo is None:
            return
        current_registered = get_registered_task_time()
        selected = self.reminder_time_combo.currentText().strip()
        already_registered = current_registered == selected
        self.register_button.setEnabled(not already_registered)
        self.register_button.setToolTip("이미 등록된 시간입니다." if already_registered else "")

    def refresh_summary(self) -> None:
        fixed_tasks = self.data["fixed_tasks"]
        fixed_done = sum(1 for task in fixed_tasks if task["completed_month"] == current_month_text())
        flexible_tasks = self.data["flexible_tasks"]
        flexible_remaining = len(flexible_tasks) - sum(1 for task in flexible_tasks if task["completed"])

        if self.fixed_count_badge is not None:
            self.fixed_count_badge.setText(f"{len(fixed_tasks) - fixed_done} 남음")
        if self.flexible_count_badge is not None:
            self.flexible_count_badge.setText(f"{flexible_remaining} 진행중")

    def refresh_fixed_tasks(self) -> None:
        if self.fixed_list is None:
            return
        self.fixed_list.blockSignals(True)
        self.fixed_list.clear()
        if not self.data["fixed_tasks"]:
            self._add_placeholder(self.fixed_list)
        else:
            for task in self.data["fixed_tasks"]:
                completed = task["completed_month"] == current_month_text()
                self._add_task_item(
                    self.fixed_list,
                    task["title"],
                    completed,
                    task["id"],
                    str(task.get("completed_on", "")),
                    "fixed",
                )
        self.fixed_list.blockSignals(False)

    def refresh_flexible_tasks(self) -> None:
        if self.flexible_list is None:
            return
        self.flexible_list.blockSignals(True)
        self.flexible_list.clear()
        if not self.data["flexible_tasks"]:
            self._add_placeholder(self.flexible_list)
        else:
            for task in self.data["flexible_tasks"]:
                self._add_task_item(
                    self.flexible_list,
                    task["title"],
                    task["completed"],
                    task["id"],
                    str(task.get("completed_on", "")),
                    "flexible",
                )
        self.flexible_list.blockSignals(False)

    def _add_placeholder(self, widget: QListWidget) -> None:
        item = QListWidgetItem("비어 있음")
        item.setFlags(Qt.NoItemFlags)
        item.setForeground(QColor(PALETTE["muted"]))
        widget.addItem(item)

    def _add_task_item(
        self,
        widget: QListWidget,
        title: str,
        completed: bool,
        task_id: int,
        completed_on: str = "",
        task_kind: str = "flexible",
    ) -> None:
        item = QListWidgetItem()
        item.setFlags(Qt.ItemIsEnabled)
        item.setData(Qt.UserRole, task_id)
        item.setData(Qt.UserRole + 1, title)
        item.setData(Qt.UserRole + 2, task_kind)
        row_widget = TaskRowWidget(title, completed, completed_on, widget)
        row_widget.toggled.connect(lambda checked, current_item=item: self.on_task_toggled(current_item, checked))
        row_widget.double_clicked.connect(lambda current_item=item: self.toggle_task_item(current_item))
        row_widget.context_menu_requested.connect(
            lambda global_pos, current_item=item: self.show_task_menu(current_item, global_pos)
        )
        row_widget.drag_released.connect(
            lambda global_pos, current_item=item: self.on_task_drag_released(current_item, global_pos)
        )
        item.setSizeHint(QSize(0, 28))
        widget.addItem(item)
        widget.setItemWidget(item, row_widget)

    def task_row_widget(self, item: QListWidgetItem) -> TaskRowWidget | None:
        list_widget = item.listWidget()
        if list_widget is None:
            return None
        row_widget = list_widget.itemWidget(item)
        return row_widget if isinstance(row_widget, TaskRowWidget) else None

    def toggle_task_item(self, item: QListWidgetItem) -> None:
        row_widget = self.task_row_widget(item)
        if row_widget is not None:
            row_widget.toggle_checked()

    def on_task_toggled(self, item: QListWidgetItem, completed: bool) -> None:
        task_id = item.data(Qt.UserRole)
        task_kind = str(item.data(Qt.UserRole + 2) or "")
        if task_id is None or task_kind not in {"fixed", "flexible"}:
            return

        completed_on = today_text() if completed else ""
        if task_kind == "fixed":
            for task in self.data["fixed_tasks"]:
                if task["id"] == int(task_id):
                    task["completed_month"] = current_month_text() if completed else ""
                    task["completed_on"] = completed_on
                    break
            self.data["settings"]["fixed_reset_month"] = current_month_text()
        else:
            for task in self.data["flexible_tasks"]:
                if task["id"] == int(task_id):
                    task["completed"] = completed
                    task["completed_on"] = completed_on
                    break

        row_widget = self.task_row_widget(item)
        if row_widget is not None:
            row_widget.set_completed(completed, completed_on)
        save_data(self.data)
        self.refresh_summary()

    def show_task_menu_at_position(self, widget: QListWidget, pos: QPoint) -> None:
        item = widget.itemAt(pos)
        if item is None:
            return
        self.show_task_menu(item, widget.viewport().mapToGlobal(pos))

    def show_task_menu(self, item: QListWidgetItem, global_pos: QPoint) -> None:
        task_id = item.data(Qt.UserRole)
        task_kind = str(item.data(Qt.UserRole + 2) or "")
        if task_id is None or task_kind not in {"fixed", "flexible"}:
            return

        menu = QMenu(self)
        edit_action = menu.addAction("편집")
        delete_action = menu.addAction("삭제")
        chosen = menu.exec(global_pos)
        if chosen == edit_action:
            self.edit_task(task_kind, int(task_id))
        elif chosen == delete_action:
            if task_kind == "fixed":
                self.delete_fixed_task(int(task_id))
            else:
                self.delete_flexible_task(int(task_id))

    def edit_task(self, task_kind: str, task_id: int) -> None:
        tasks = self.data["fixed_tasks"] if task_kind == "fixed" else self.data["flexible_tasks"]
        task = next((item for item in tasks if item["id"] == task_id), None)
        if task is None:
            return

        updated_title, accepted = QInputDialog.getText(self, "할 일 편집", "할 일 내용", text=str(task["title"]))
        if not accepted:
            return

        title = updated_title.strip()
        if not title:
            QMessageBox.warning(self, "입력 필요", "할 일 내용을 입력하세요.")
            return
        if title == task["title"]:
            return

        task["title"] = title
        save_data(self.data)
        if task_kind == "fixed":
            self.refresh_fixed_tasks()
        else:
            self.refresh_flexible_tasks()
        self.refresh_summary()

    def on_task_drag_released(self, item: QListWidgetItem, global_pos: QPoint) -> None:
        list_widget = item.listWidget()
        task_kind = str(item.data(Qt.UserRole + 2) or "")
        if list_widget is None or task_kind not in {"fixed", "flexible"}:
            return

        source_index = list_widget.row(item)
        if source_index < 0:
            return

        insertion_index = self.task_drop_insertion_index(list_widget, global_pos)
        self.move_task(task_kind, source_index, insertion_index)

    def task_drop_insertion_index(self, widget: QListWidget, global_pos: QPoint) -> int:
        viewport_pos = widget.viewport().mapFromGlobal(global_pos)
        count = widget.count()
        if count <= 0:
            return 0

        max_x = max(widget.viewport().width() - 2, 1)
        probe_pos = QPoint(min(max(viewport_pos.x(), 1), max_x), viewport_pos.y())
        target_item = widget.itemAt(probe_pos)
        if target_item is None:
            return 0 if viewport_pos.y() <= 0 else count

        target_row = widget.row(target_item)
        target_rect = widget.visualItemRect(target_item)
        return target_row + 1 if viewport_pos.y() > target_rect.center().y() else target_row

    def move_task(self, task_kind: str, source_index: int, insertion_index: int) -> None:
        tasks = self.data["fixed_tasks"] if task_kind == "fixed" else self.data["flexible_tasks"]
        if not 0 <= source_index < len(tasks):
            return

        bounded_index = max(0, min(insertion_index, len(tasks)))
        if bounded_index in {source_index, source_index + 1}:
            return

        task = tasks.pop(source_index)
        if bounded_index > source_index:
            bounded_index -= 1
        tasks.insert(bounded_index, task)
        save_data(self.data)
        if task_kind == "fixed":
            self.refresh_fixed_tasks()
        else:
            self.refresh_flexible_tasks()

    def on_fixed_item_changed(self, item: QListWidgetItem) -> None:
        task_id = item.data(Qt.UserRole)
        if task_id is None:
            return

        completed = item.checkState() == Qt.Checked
        completed_on = today_text() if completed else ""
        for task in self.data["fixed_tasks"]:
            if task["id"] == int(task_id):
                task["completed_month"] = current_month_text() if completed else ""
                task["completed_on"] = completed_on
                break

        self.data["settings"]["fixed_reset_month"] = current_month_text()
        self.update_task_item_text(item, completed, completed_on)
        self.apply_task_item_style(item, completed)
        save_data(self.data)
        self.refresh_summary()

    def on_flexible_item_changed(self, item: QListWidgetItem) -> None:
        task_id = item.data(Qt.UserRole)
        if task_id is None:
            return

        completed = item.checkState() == Qt.Checked
        completed_on = today_text() if completed else ""
        for task in self.data["flexible_tasks"]:
            if task["id"] == int(task_id):
                task["completed"] = completed
                task["completed_on"] = completed_on
                break

        self.update_task_item_text(item, completed, completed_on)
        self.apply_task_item_style(item, completed)
        save_data(self.data)
        self.refresh_summary()

    def add_fixed_task(self) -> None:
        if self.fixed_input is None:
            return
        title = self.fixed_input.text().strip()
        if not title:
            QMessageBox.warning(self, "입력 필요", "고정 할 일을 입력하세요.")
            return

        self.data["fixed_tasks"].append(
            {"id": next_id(self.data["fixed_tasks"]), "title": title, "completed_month": "", "completed_on": ""}
        )
        save_data(self.data)
        self.fixed_input.clear()
        self.refresh_fixed_tasks()
        self.refresh_summary()

    def add_flexible_task(self) -> None:
        if self.flexible_input is None:
            return
        title = self.flexible_input.text().strip()
        if not title:
            QMessageBox.warning(self, "입력 필요", "수시 할 일을 입력하세요.")
            return

        self.data["flexible_tasks"].append(
            {
                "id": next_id(self.data["flexible_tasks"]),
                "title": title,
                "completed": False,
                "created_at": now_text(),
                "completed_on": "",
            }
        )
        save_data(self.data)
        self.flexible_input.clear()
        self.refresh_flexible_tasks()
        self.refresh_summary()

    def delete_fixed_task(self, task_id: int) -> None:
        self.data["fixed_tasks"] = [task for task in self.data["fixed_tasks"] if task["id"] != task_id]
        save_data(self.data)
        self.refresh_fixed_tasks()
        self.refresh_summary()

    def delete_flexible_task(self, task_id: int) -> None:
        self.data["flexible_tasks"] = [task for task in self.data["flexible_tasks"] if task["id"] != task_id]
        save_data(self.data)
        self.refresh_flexible_tasks()
        self.refresh_summary()

    def clear_completed_flexible_tasks(self) -> None:
        before_count = len(self.data["flexible_tasks"])
        self.data["flexible_tasks"] = [task for task in self.data["flexible_tasks"] if not task["completed"]]
        if len(self.data["flexible_tasks"]) == before_count:
            QMessageBox.information(self, "정리", "정리할 완료 항목이 없습니다.")
            return

        save_data(self.data)
        self.refresh_flexible_tasks()
        self.refresh_summary()

    def schedule_memo_save(self) -> None:
        self.memo_save_timer.start()

    def save_memo(self) -> None:
        if self.memo_edit is None:
            return
        self.data["memo"] = self.memo_edit.toPlainText()
        save_data(self.data)

    def _reminder_message(self) -> str:
        fixed_total = len(self.data["fixed_tasks"])
        fixed_done = sum(1 for task in self.data["fixed_tasks"] if task["completed_month"] == current_month_text())
        flexible_remaining = sum(1 for task in self.data["flexible_tasks"] if not task["completed"])
        return f"고정 {fixed_done}/{fixed_total} 완료 · 수시 {flexible_remaining}개 남음"

    def show_reminder_popup(self, force: bool = False) -> None:
        due_now = is_due_for_reminder(self.data)
        if not force and not due_now:
            self.restore_main_window()
            return

        if due_now:
            self.data["settings"]["last_popup_date"] = today_text()
            save_data(self.data)
            self.refresh_summary()

        if self.tray_mode and self.tray_icon is not None:
            self.tray_icon.showMessage(APP_TITLE, self._reminder_message(), self.tray_icon.icon(), 4000)
            return

        self.restore_main_window()
        QMessageBox.information(self, "오늘 할 일", self._reminder_message())

    def check_daily_reminder(self) -> None:
        if is_due_for_reminder(self.data):
            self.show_reminder_popup()

    def register_schedule_from_ui(self) -> None:
        if self.reminder_time_combo is None:
            return
        reminder_time = self.reminder_time_combo.currentText().strip()
        try:
            register_daily_task(reminder_time)
        except (RuntimeError, ValueError) as error:
            QMessageBox.critical(self, "작업 스케줄러", str(error))
            return

        self.data["settings"]["reminder_time"] = reminder_time
        save_data(self.data)
        self.refresh_register_button_state()

    def minimize_window(self) -> None:
        self.showMinimized()

    def toggle_maximized(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
        if self.title_bar is not None:
            self.title_bar.sync_window_state()

    def minimize_to_button(self) -> None:
        self.tray_mode = False
        if self.tray_icon is not None:
            self.tray_icon.hide()
        self.hide()
        if self.floating_launcher is None:
            self.floating_launcher = FloatingLauncher()
            self.floating_launcher.restore_requested.connect(self.restore_main_window)
        self.floating_launcher.move(self._floating_button_position())
        self.floating_launcher.show()

    def _floating_button_position(self) -> QPoint:
        screen = QApplication.primaryScreen()
        if screen is None:
            return QPoint(1000, 700)
        geometry = screen.availableGeometry()
        return QPoint(geometry.right() - 44, geometry.bottom() - 44)

    def minimize_to_tray(self) -> None:
        if self.tray_icon is None:
            QMessageBox.warning(self, "알림 최소화", "시스템 트레이를 사용할 수 없습니다.")
            return

        self.tray_mode = True
        self.hide()
        if self.floating_launcher is not None:
            self.floating_launcher.hide()
        self.tray_icon.show()
        self.tray_icon.showMessage(APP_TITLE, "트레이로 최소화되었습니다.", self.tray_icon.icon(), 2500)

    def restore_main_window(self) -> None:
        self.tray_mode = False
        if self.floating_launcher is not None:
            self.floating_launcher.hide()
        if self.tray_icon is not None:
            self.tray_icon.hide()
        self.showNormal()
        if self.title_bar is not None:
            self.title_bar.sync_window_state()
        self.raise_()
        self.activateWindow()

    def on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in {QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick}:
            self.restore_main_window()

    def handle_external_command(self, payload: str) -> None:
        if payload == "REMIND":
            self.show_reminder_popup()
        else:
            self.restore_main_window()

    def on_close(self) -> None:
        self.close()

    def changeEvent(self, event) -> None:  # type: ignore[override]
        if event.type() == QEvent.WindowStateChange and self.title_bar is not None:
            self.title_bar.sync_window_state()
        super().changeEvent(event)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        central = self.centralWidget()
        if central is None or self.size_grip is None:
            return
        self.size_grip.move(central.width() - self.size_grip.width() - 2, central.height() - self.size_grip.height() - 2)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.save_memo()
        self.command_server.stop()
        self.clock_timer.stop()
        self.reminder_timer.stop()
        if self.tray_icon is not None:
            self.tray_icon.hide()
        if self.floating_launcher is not None:
            self.floating_launcher.close()
        event.accept()


def main() -> None:
    initial_data = load_data()
    command = "REMIND" if is_due_for_reminder(initial_data) else "SHOW"
    if send_command_to_existing_instance(command):
        return

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    app.setApplicationName(APP_TITLE)
    window = TodoWindow()
    window.show()
    if is_due_for_reminder(window.data):
        QTimer.singleShot(1000, window.show_reminder_popup)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
