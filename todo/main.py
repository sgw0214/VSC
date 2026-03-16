from __future__ import annotations

import json
import socket
import subprocess
import sys
import threading
import tkinter as tk
from datetime import date, datetime
from pathlib import Path
from tkinter import messagebox, ttk


APP_TITLE = "월간 할 일 보드"
DATA_FILE = Path(__file__).with_name("tasks.json")
TASK_NAME = "TodoDailyReminder"
DEFAULT_REMINDER_TIME = "08:00"
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 49281

PALETTE = {
    "app_bg": "#ddd6c8",
    "sidebar_bg": "#2f3a34",
    "sidebar_text": "#f4efe4",
    "sidebar_muted": "#d5ccbd",
    "card_bg": "#fffdf8",
    "note_bg": "#f3eee3",
    "row_bg": "#f7f3eb",
    "border": "#d9cebc",
    "text": "#243127",
    "muted": "#6b675f",
    "primary": "#415c46",
    "primary_hover": "#314736",
    "secondary": "#d8ccb9",
    "secondary_hover": "#cbbda8",
    "chip_fixed_bg": "#dde8d7",
    "chip_fixed_fg": "#33503a",
    "chip_flex_bg": "#efe1c8",
    "chip_flex_fg": "#765532",
    "chip_reminder_bg": "#d7e4ea",
    "chip_reminder_fg": "#38576a",
    "chip_soft_bg": "#ece3d4",
    "chip_soft_fg": "#62584b",
    "done_bg": "#dfe9dc",
    "done_fg": "#36523d",
    "waiting_bg": "#efe5d6",
    "waiting_fg": "#7b6345",
}

TITLE_FONT = ("Segoe UI Semibold", 18)
CARD_TITLE_FONT = ("Segoe UI Semibold", 11)
BODY_FONT = ("Malgun Gothic", 10)
META_FONT = ("Segoe UI", 8)
CHIP_FONT = ("Segoe UI Semibold", 8)


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def today_text() -> str:
    return date.today().isoformat()


def current_month_text() -> str:
    return datetime.now().strftime("%Y-%m")


def default_data() -> dict:
    return {
        "fixed_tasks": [],
        "flexible_tasks": [],
        "memo": "",
        "settings": {
            "reminder_time": DEFAULT_REMINDER_TIME,
            "last_popup_date": "",
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
        converted = []
        for item in raw:
            task = sanitize_flexible_task(item)
            if task is not None:
                converted.append(task)
        data["flexible_tasks"] = sorted(converted, key=lambda task: task["id"])
        return data

    if not isinstance(raw, dict):
        return data

    fixed_tasks = []
    for item in raw.get("fixed_tasks", []):
        task = sanitize_fixed_task(item)
        if task is not None:
            fixed_tasks.append(task)

    flexible_tasks = []
    fallback_tasks = raw.get("tasks", [])
    source_tasks = raw.get("flexible_tasks", fallback_tasks)
    for item in source_tasks:
        task = sanitize_flexible_task(item)
        if task is not None:
            flexible_tasks.append(task)

    settings = raw.get("settings", {})
    reminder_time = str(settings.get("reminder_time", DEFAULT_REMINDER_TIME))
    last_popup_date = str(settings.get("last_popup_date", ""))

    data["fixed_tasks"] = sorted(fixed_tasks, key=lambda task: task["id"])
    data["flexible_tasks"] = sorted(flexible_tasks, key=lambda task: task["id"])
    data["memo"] = str(raw.get("memo", ""))
    data["settings"] = {
        "reminder_time": reminder_time,
        "last_popup_date": last_popup_date,
    }
    return data


def save_data(data: dict) -> None:
    with DATA_FILE.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def next_id(items: list[dict]) -> int:
    if not items:
        return 1
    return max(int(item["id"]) for item in items) + 1


def parse_reminder_time(value: str) -> tuple[int, int] | None:
    text = value.strip()
    parts = text.split(":")
    if len(parts) != 2:
        return None

    hour_text, minute_text = parts
    if not hour_text.isdigit() or not minute_text.isdigit():
        return None

    hour = int(hour_text)
    minute = int(minute_text)
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
    if candidate.exists():
        return candidate
    return executable


def decode_output(raw: bytes) -> str:
    for encoding in ("utf-8", "cp949"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode(errors="replace")


def scheduled_task_exists() -> bool:
    result = subprocess.run(
        ["schtasks", "/Query", "/TN", TASK_NAME],
        capture_output=True,
        shell=False,
    )
    return result.returncode == 0


def register_daily_task(reminder_time: str = DEFAULT_REMINDER_TIME) -> str:
    parsed = parse_reminder_time(reminder_time)
    if parsed is None:
        raise ValueError("알림 시간 형식은 HH:MM 이어야 합니다.")

    task_command = f'"{pythonw_path()}" "{Path(__file__).resolve()}"'
    result = subprocess.run(
        [
            "schtasks",
            "/Create",
            "/SC",
            "DAILY",
            "/TN",
            TASK_NAME,
            "/TR",
            task_command,
            "/ST",
            reminder_time,
            "/F",
        ],
        capture_output=True,
        shell=False,
    )
    if result.returncode != 0:
        stderr_text = decode_output(result.stderr).strip()
        stdout_text = decode_output(result.stdout).strip()
        message = stderr_text or stdout_text or "작업 스케줄러 등록에 실패했습니다."
        raise RuntimeError(message)

    stdout_text = decode_output(result.stdout).strip()
    return stdout_text or "작업 스케줄러 등록 완료"


def send_command_to_existing_instance(command: str) -> bool:
    try:
        with socket.create_connection((SERVER_HOST, SERVER_PORT), timeout=0.4) as client:
            client.sendall(command.encode("utf-8"))
        return True
    except OSError:
        return False


class ScrollableFrame(tk.Frame):
    def __init__(self, master: tk.Widget, background: str) -> None:
        super().__init__(master, bg=background, bd=0, highlightthickness=0)

        self.canvas = tk.Canvas(
            self,
            highlightthickness=0,
            bd=0,
            relief="flat",
            background=background,
        )
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.content = tk.Frame(self.canvas, bg=background, bd=0, highlightthickness=0)

        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.window_id = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.content.bind("<Configure>", self._update_scroll_region)
        self.canvas.bind("<Configure>", self._resize_content)
        self.canvas.bind("<Enter>", self._bind_mousewheel)
        self.canvas.bind("<Leave>", self._unbind_mousewheel)

    def _update_scroll_region(self, _event: tk.Event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _resize_content(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self.window_id, width=event.width)

    def _bind_mousewheel(self, _event: tk.Event) -> None:
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, _event: tk.Event) -> None:
        self.canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event: tk.Event) -> None:
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


class TodoApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.data = load_data()
        self.memo_after_id: str | None = None
        self.server_socket: socket.socket | None = None
        self.server_stop_event = threading.Event()
        self.server_thread: threading.Thread | None = None
        self.fixed_count_label: tk.Label | None = None
        self.flex_count_label: tk.Label | None = None
        self.reminder_chip: tk.Label | None = None
        self.schedule_chip: tk.Label | None = None

        self._configure_window()
        self._build_ui()
        self.refresh_all()
        self.root.after(1200, self.check_daily_reminder)

    def _configure_window(self) -> None:
        self.root.title(APP_TITLE)
        self.root.geometry("980x610")
        self.root.minsize(860, 520)
        self.root.configure(bg=PALETTE["app_bg"])
        self.root.option_add("*Font", "{Malgun Gothic} 9")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure(
            "Primary.TButton",
            font=("Segoe UI Semibold", 9),
            padding=(10, 5),
            borderwidth=0,
            relief="flat",
            background=PALETTE["primary"],
            foreground="#ffffff",
        )
        style.map(
            "Primary.TButton",
            background=[("active", PALETTE["primary_hover"]), ("pressed", PALETTE["primary_hover"])],
        )

        style.configure(
            "Secondary.TButton",
            font=("Segoe UI Semibold", 9),
            padding=(10, 5),
            borderwidth=0,
            relief="flat",
            background=PALETTE["secondary"],
            foreground=PALETTE["text"],
        )
        style.map(
            "Secondary.TButton",
            background=[("active", PALETTE["secondary_hover"]), ("pressed", PALETTE["secondary_hover"])],
        )

        style.configure(
            "Ghost.TButton",
            font=("Segoe UI", 8),
            padding=(8, 3),
            borderwidth=0,
            relief="flat",
            background=PALETTE["card_bg"],
            foreground=PALETTE["muted"],
        )
        style.map(
            "Ghost.TButton",
            background=[("active", "#f1ece2"), ("pressed", "#ebe3d4")],
            foreground=[("active", PALETTE["text"])],
        )

        style.configure(
            "Task.TCheckbutton",
            background=PALETTE["row_bg"],
            foreground=PALETTE["text"],
            font=BODY_FONT,
        )
        style.map(
            "Task.TCheckbutton",
            background=[
                ("active", PALETTE["row_bg"]),
                ("selected", PALETTE["row_bg"]),
                ("!selected", PALETTE["row_bg"]),
            ],
        )

        style.configure(
            "Task.TEntry",
            fieldbackground=PALETTE["card_bg"],
            foreground=PALETTE["text"],
            bordercolor=PALETTE["border"],
            lightcolor=PALETTE["border"],
            darkcolor=PALETTE["border"],
            padding=(8, 6),
        )

    def _build_ui(self) -> None:
        container = tk.Frame(self.root, bg=PALETTE["app_bg"], padx=12, pady=12)
        container.pack(fill="both", expand=True)
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(0, weight=1)

        shell = tk.Frame(container, bg=PALETTE["app_bg"])
        shell.grid(row=0, column=0, sticky="nsew")
        shell.grid_columnconfigure(0, weight=0)
        shell.grid_columnconfigure(1, weight=1)
        shell.grid_rowconfigure(0, weight=1)

        sidebar = tk.Frame(
            shell,
            bg=PALETTE["sidebar_bg"],
            bd=0,
            highlightthickness=1,
            highlightbackground="#46554d",
            highlightcolor="#46554d",
            padx=16,
            pady=16,
            width=240,
        )
        sidebar.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)

        tk.Label(
            sidebar,
            text=APP_TITLE,
            bg=PALETTE["sidebar_bg"],
            fg=PALETTE["sidebar_text"],
            font=TITLE_FONT,
        ).grid(row=0, column=0, sticky="w")

        self.date_label = tk.Label(
            sidebar,
            text="",
            bg=PALETTE["sidebar_bg"],
            fg=PALETTE["sidebar_muted"],
            font=META_FONT,
        )
        self.date_label.grid(row=1, column=0, sticky="w", pady=(4, 14))

        tk.Label(
            sidebar,
            text="매일 08:00에 창을 앞으로 띄워 오늘 확인을 다시 도와줍니다.",
            bg=PALETTE["sidebar_bg"],
            fg=PALETTE["sidebar_muted"],
            font=META_FONT,
            justify="left",
            wraplength=200,
        ).grid(row=2, column=0, sticky="ew", pady=(0, 14))

        ttk.Button(
            sidebar,
            text="오늘 보기",
            style="Secondary.TButton",
            command=lambda: self.show_reminder_popup(force=True),
        ).grid(row=3, column=0, sticky="ew")
        ttk.Button(
            sidebar,
            text="8시 등록",
            style="Primary.TButton",
            command=self.register_schedule_from_ui,
        ).grid(row=4, column=0, sticky="ew", pady=(6, 14))

        self.fixed_count_label = self._create_sidebar_stat(sidebar, 5)
        self.flex_count_label = self._create_sidebar_stat(sidebar, 6)
        self.reminder_chip = self._create_sidebar_stat(sidebar, 7)
        self.schedule_chip = self._create_sidebar_stat(sidebar, 8)

        main_area = tk.Frame(shell, bg=PALETTE["app_bg"])
        main_area.grid(row=0, column=1, sticky="nsew")
        main_area.grid_columnconfigure(0, weight=1)
        main_area.grid_columnconfigure(1, weight=1)
        main_area.grid_rowconfigure(0, weight=12)
        main_area.grid_rowconfigure(1, weight=8)

        self.fixed_panel = self._build_task_panel(
            main_area,
            row=0,
            column=0,
            title="매월 고정 할 일",
            hint="이번 달에 한 번 체크",
            add_command=self.add_fixed_task,
            clear_command=None,
        )
        self.flexible_panel = self._build_task_panel(
            main_area,
            row=0,
            column=1,
            title="수시 할 일",
            hint="생길 때마다 추가",
            add_command=self.add_flexible_task,
            clear_command=self.clear_completed_flexible_tasks,
        )
        self._build_memo_panel(main_area, row=1, column=0, columnspan=2)

    def _build_task_panel(
        self,
        parent: tk.Widget,
        row: int,
        column: int,
        title: str,
        hint: str,
        add_command,
        clear_command,
    ) -> dict:
        panel = self._create_card(parent)
        panel.grid(row=row, column=column, sticky="nsew", padx=(0, 10 if column == 0 else 0), pady=(0, 10))
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(2, weight=1)

        top_row = tk.Frame(panel, bg=PALETTE["card_bg"])
        top_row.grid(row=0, column=0, sticky="ew")
        top_row.grid_columnconfigure(0, weight=1)
        tk.Label(top_row, text=title, bg=PALETTE["card_bg"], fg=PALETTE["text"], font=CARD_TITLE_FONT).grid(row=0, column=0, sticky="w")
        count_label = self._create_chip(top_row, PALETTE["chip_soft_bg"], PALETTE["chip_soft_fg"])
        count_label.grid(row=0, column=1, sticky="e")
        tk.Label(top_row, text=hint, bg=PALETTE["card_bg"], fg=PALETTE["muted"], font=META_FONT).grid(row=1, column=0, sticky="w", pady=(2, 0))

        input_row = tk.Frame(panel, bg=PALETTE["card_bg"])
        input_row.grid(row=1, column=0, sticky="ew", pady=(10, 10))
        input_row.grid_columnconfigure(0, weight=1)

        entry = ttk.Entry(input_row, style="Task.TEntry")
        entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        entry.bind("<Return>", lambda _event: add_command())

        ttk.Button(input_row, text="추가", style="Primary.TButton", command=add_command).grid(row=0, column=1)
        if clear_command is not None:
            ttk.Button(input_row, text="완료 정리", style="Secondary.TButton", command=clear_command).grid(row=0, column=2, padx=(6, 0))

        scrollable = ScrollableFrame(panel, background=PALETTE["card_bg"])
        scrollable.grid(row=2, column=0, sticky="nsew")

        return {
            "panel": panel,
            "entry": entry,
            "list": scrollable,
            "count": count_label,
        }

    def _build_memo_panel(self, parent: tk.Widget, row: int, column: int, columnspan: int) -> None:
        panel = self._create_card(parent, background=PALETTE["note_bg"])
        panel.grid(row=row, column=column, columnspan=columnspan, sticky="nsew")
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(1, weight=1)

        top_row = tk.Frame(panel, bg=PALETTE["note_bg"])
        top_row.grid(row=0, column=0, sticky="ew")
        top_row.grid_columnconfigure(0, weight=1)
        tk.Label(top_row, text="메모장", bg=PALETTE["note_bg"], fg=PALETTE["text"], font=CARD_TITLE_FONT).grid(row=0, column=0, sticky="w")
        auto_save_label = self._create_chip(top_row, PALETTE["chip_reminder_bg"], PALETTE["chip_reminder_fg"])
        auto_save_label.configure(text="생각나는 건 바로 적기")
        auto_save_label.grid(row=0, column=1, sticky="e")

        text_frame = tk.Frame(panel, bg=PALETTE["note_bg"])
        text_frame.grid(row=1, column=0, sticky="nsew", pady=(10, 8))
        text_frame.grid_columnconfigure(0, weight=1)
        text_frame.grid_rowconfigure(0, weight=1)

        self.memo_text = tk.Text(
            text_frame,
            wrap="word",
            undo=True,
            relief="flat",
            bd=0,
            padx=12,
            pady=10,
            font=BODY_FONT,
            background=PALETTE["card_bg"],
            foreground=PALETTE["text"],
            insertbackground=PALETTE["text"],
            highlightthickness=1,
            highlightbackground=PALETTE["border"],
            highlightcolor=PALETTE["border"],
        )
        memo_scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.memo_text.yview)
        self.memo_text.configure(yscrollcommand=memo_scrollbar.set)
        self.memo_text.grid(row=0, column=0, sticky="nsew")
        memo_scrollbar.grid(row=0, column=1, sticky="ns")
        self.memo_text.bind("<KeyRelease>", self.on_memo_changed)

        button_row = tk.Frame(panel, bg=PALETTE["note_bg"])
        button_row.grid(row=2, column=0, sticky="ew")
        button_row.grid_columnconfigure(0, weight=1)
        tk.Label(
            button_row,
            text="아이디어, 연락할 것, 이번 달 메모를 자유롭게 적어두세요.",
            bg=PALETTE["note_bg"],
            fg=PALETTE["muted"],
            font=META_FONT,
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(button_row, text="지금 저장", style="Ghost.TButton", command=self.save_memo).grid(row=0, column=1, sticky="e")

    def _create_chip(self, parent: tk.Widget, background: str, foreground: str) -> tk.Label:
        return tk.Label(
            parent,
            text="",
            bg=background,
            fg=foreground,
            font=CHIP_FONT,
            padx=10,
            pady=5,
            bd=0,
        )

    def _create_sidebar_stat(self, parent: tk.Widget, row: int) -> tk.Label:
        frame = tk.Frame(parent, bg="#39443d", padx=10, pady=9)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 6))
        label = tk.Label(
            frame,
            text="",
            bg="#39443d",
            fg=PALETTE["sidebar_text"],
            font=("Segoe UI Semibold", 9),
            justify="left",
            anchor="w",
        )
        label.pack(fill="x")
        return label

    def _create_card(self, parent: tk.Widget, background: str | None = None) -> tk.Frame:
        card_background = background or PALETTE["card_bg"]
        return tk.Frame(
            parent,
            bg=card_background,
            bd=0,
            highlightthickness=1,
            highlightbackground=PALETTE["border"],
            highlightcolor=PALETTE["border"],
            padx=12,
            pady=12,
        )

    def start_server(self) -> None:
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((SERVER_HOST, SERVER_PORT))
            self.server_socket.listen()
            self.server_socket.settimeout(1.0)
        except OSError:
            self.server_socket = None
            return

        self.server_thread = threading.Thread(target=self._server_loop, daemon=True)
        self.server_thread.start()

    def _server_loop(self) -> None:
        assert self.server_socket is not None
        while not self.server_stop_event.is_set():
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

            if payload == "REMIND":
                self.root.after(0, self.show_reminder_popup)
            else:
                self.root.after(0, self.bring_to_front)

    def refresh_all(self) -> None:
        self.refresh_clock()
        self.memo_text.delete("1.0", "end")
        self.memo_text.insert("1.0", self.data.get("memo", ""))
        self.refresh_fixed_tasks()
        self.refresh_flexible_tasks()
        self.refresh_summary()
        self.refresh_schedule_status()

    def refresh_clock(self) -> None:
        self.date_label.configure(text=datetime.now().strftime("%Y년 %m월  %d일 %H:%M"))

    def refresh_summary(self) -> None:
        fixed_tasks = self.data["fixed_tasks"]
        fixed_done = sum(1 for task in fixed_tasks if task["completed_month"] == current_month_text())
        flexible_tasks = self.data["flexible_tasks"]
        flexible_done = sum(1 for task in flexible_tasks if task["completed"])
        flexible_remaining = len(flexible_tasks) - flexible_done

        reminder_time = self.data["settings"].get("reminder_time", DEFAULT_REMINDER_TIME)
        self.fixed_count_label.configure(text=f"매월 고정 할 일\n{fixed_done}/{len(fixed_tasks)} 완료")
        self.flex_count_label.configure(text=f"수시 할 일\n{flexible_remaining}개 진행 중")
        self.reminder_chip.configure(text=f"매일 알림\n{reminder_time} 창 앞으로")
        self.fixed_panel["count"].configure(text=f"이번 달 남은 일  {len(fixed_tasks) - fixed_done}")
        self.flexible_panel["count"].configure(text=f"진행 중  {flexible_remaining}")

    def refresh_fixed_tasks(self) -> None:
        self._clear_task_list(self.fixed_panel["list"].content)
        tasks = self.data["fixed_tasks"]
        if not tasks:
            self._render_empty_state(self.fixed_panel["list"].content, "아직 매월 고정 할 일이 없습니다.")
            return

        for row_index, task in enumerate(tasks):
            is_done_this_month = task["completed_month"] == current_month_text()
            variable = tk.BooleanVar(value=is_done_this_month)
            self._render_task_row(
                parent=self.fixed_panel["list"].content,
                row_index=row_index,
                title=task["title"],
                variable=variable,
                meta_text="이번 달 완료" if is_done_this_month else "이번 달 대기",
                meta_background=PALETTE["done_bg"] if is_done_this_month else PALETTE["waiting_bg"],
                meta_foreground=PALETTE["done_fg"] if is_done_this_month else PALETTE["waiting_fg"],
                toggle_command=lambda task_id=task["id"], state=variable: self.toggle_fixed_task(task_id, state.get()),
                delete_command=lambda task_id=task["id"]: self.delete_fixed_task(task_id),
            )

    def refresh_flexible_tasks(self) -> None:
        self._clear_task_list(self.flexible_panel["list"].content)
        tasks = self.data["flexible_tasks"]
        if not tasks:
            self._render_empty_state(self.flexible_panel["list"].content, "아직 수시 할 일이 없습니다.")
            return

        for row_index, task in enumerate(tasks):
            variable = tk.BooleanVar(value=task["completed"])
            created_at = task["created_at"] or "기록 없음"
            self._render_task_row(
                parent=self.flexible_panel["list"].content,
                row_index=row_index,
                title=task["title"],
                variable=variable,
                meta_text=created_at,
                meta_background=PALETTE["chip_soft_bg"],
                meta_foreground=PALETTE["chip_soft_fg"],
                toggle_command=lambda task_id=task["id"], state=variable: self.toggle_flexible_task(task_id, state.get()),
                delete_command=lambda task_id=task["id"]: self.delete_flexible_task(task_id),
            )

    def refresh_schedule_status(self) -> None:
        if scheduled_task_exists():
            self.schedule_chip.configure(text="스케줄 상태\n08:00 등록됨")
        else:
            self.schedule_chip.configure(text="스케줄 상태\n미등록")

    def _clear_task_list(self, container: tk.Widget) -> None:
        for child in container.winfo_children():
            child.destroy()

    def _render_empty_state(self, parent: tk.Widget, message: str) -> None:
        empty_row = tk.Frame(parent, bg=PALETTE["card_bg"], pady=10)
        empty_row.grid(row=0, column=0, sticky="ew")
        tk.Label(
            empty_row,
            text=message,
            bg=PALETTE["card_bg"],
            fg=PALETTE["muted"],
            font=META_FONT,
        ).pack(anchor="w")

    def _render_task_row(
        self,
        parent: tk.Widget,
        row_index: int,
        title: str,
        variable: tk.BooleanVar,
        meta_text: str,
        meta_background: str,
        meta_foreground: str,
        toggle_command,
        delete_command,
    ) -> None:
        row = tk.Frame(
            parent,
            bg=PALETTE["row_bg"],
            bd=0,
            highlightthickness=1,
            highlightbackground="#ede5d8",
            highlightcolor="#ede5d8",
            padx=8,
            pady=6,
        )
        row.grid(row=row_index, column=0, sticky="ew", pady=(0, 6))
        row.grid_columnconfigure(0, weight=1)

        ttk.Checkbutton(
            row,
            text=title,
            variable=variable,
            style="Task.TCheckbutton",
            command=toggle_command,
        ).grid(row=0, column=0, sticky="w")

        tk.Label(
            row,
            text=meta_text,
            bg=meta_background,
            fg=meta_foreground,
            font=META_FONT,
            padx=8,
            pady=3,
        ).grid(row=0, column=1, padx=(6, 6), sticky="e")

        ttk.Button(
            row,
            text="삭제",
            style="Ghost.TButton",
            command=delete_command,
        ).grid(row=0, column=2, sticky="e")

    def add_fixed_task(self) -> None:
        title = self.fixed_panel["entry"].get().strip()
        if not title:
            messagebox.showwarning("입력 필요", "매월 고정 할 일을 입력하세요.")
            return

        self.data["fixed_tasks"].append(
            {
                "id": next_id(self.data["fixed_tasks"]),
                "title": title,
                "completed_month": "",
            }
        )
        save_data(self.data)
        self.fixed_panel["entry"].delete(0, "end")
        self.refresh_fixed_tasks()
        self.refresh_summary()

    def add_flexible_task(self) -> None:
        title = self.flexible_panel["entry"].get().strip()
        if not title:
            messagebox.showwarning("입력 필요", "수시 할 일을 입력하세요.")
            return

        self.data["flexible_tasks"].append(
            {
                "id": next_id(self.data["flexible_tasks"]),
                "title": title,
                "completed": False,
                "created_at": now_text(),
            }
        )
        save_data(self.data)
        self.flexible_panel["entry"].delete(0, "end")
        self.refresh_flexible_tasks()
        self.refresh_summary()

    def toggle_fixed_task(self, task_id: int, completed: bool) -> None:
        for task in self.data["fixed_tasks"]:
            if task["id"] == task_id:
                task["completed_month"] = current_month_text() if completed else ""
                break

        save_data(self.data)
        self.refresh_fixed_tasks()
        self.refresh_summary()

    def toggle_flexible_task(self, task_id: int, completed: bool) -> None:
        for task in self.data["flexible_tasks"]:
            if task["id"] == task_id:
                task["completed"] = completed
                break

        save_data(self.data)
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
            messagebox.showinfo("완료 정리", "정리할 완료 항목이 없습니다.")
            return

        save_data(self.data)
        self.refresh_flexible_tasks()
        self.refresh_summary()

    def on_memo_changed(self, _event: tk.Event) -> None:
        if self.memo_after_id is not None:
            self.root.after_cancel(self.memo_after_id)
        self.memo_after_id = self.root.after(500, self.save_memo)

    def save_memo(self) -> None:
        self.memo_after_id = None
        self.data["memo"] = self.memo_text.get("1.0", "end-1c")
        save_data(self.data)

    def check_daily_reminder(self) -> None:
        if is_due_for_reminder(self.data):
            self.show_reminder_popup()
        self.root.after(30_000, self.check_daily_reminder)

    def bring_to_front(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(1500, lambda: self.root.attributes("-topmost", False))
        try:
            self.root.focus_force()
        except tk.TclError:
            pass

    def show_reminder_popup(self, force: bool = False) -> None:
        due_now = is_due_for_reminder(self.data)
        if not force and not due_now:
            self.bring_to_front()
            return

        if due_now:
            self.data["settings"]["last_popup_date"] = today_text()
            save_data(self.data)
            self.refresh_summary()
        self.bring_to_front()

        fixed_total = len(self.data["fixed_tasks"])
        fixed_done = sum(1 for task in self.data["fixed_tasks"] if task["completed_month"] == current_month_text())
        flexible_remaining = sum(1 for task in self.data["flexible_tasks"] if not task["completed"])
        messagebox.showinfo(
            "오늘 할 일 확인",
            (
                "오늘 할 일을 확인하세요.\n\n"
                f"- 매월 고정 할 일: {fixed_done}/{fixed_total} 완료\n"
                f"- 수시 할 일: {flexible_remaining}개 남음"
            ),
        )

    def register_schedule_from_ui(self) -> None:
        reminder_time = str(self.data["settings"].get("reminder_time", DEFAULT_REMINDER_TIME))
        try:
            register_daily_task(reminder_time)
        except (RuntimeError, ValueError) as error:
            messagebox.showerror("작업 스케줄러", str(error))
            return

        self.refresh_schedule_status()
        messagebox.showinfo("작업 스케줄러", f"매일 {reminder_time} 자동 실행이 등록되었습니다.")

    def on_close(self) -> None:
        self.save_memo()
        self.server_stop_event.set()
        if self.server_socket is not None:
            try:
                self.server_socket.close()
            except OSError:
                pass
        self.root.destroy()


def main() -> None:
    initial_data = load_data()
    command = "REMIND" if is_due_for_reminder(initial_data) else "SHOW"
    if send_command_to_existing_instance(command):
        return

    root = tk.Tk()
    app = TodoApp(root)
    app.start_server()
    if is_due_for_reminder(app.data):
        root.after(1400, app.show_reminder_popup)
    root.mainloop()


if __name__ == "__main__":
    main()
