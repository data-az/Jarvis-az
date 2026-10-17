# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════╗
║                    JARVIS AZ v1.8                           ║
║              Голосовой ассистент с визуализацией            ║
╚══════════════════════════════════════════════════════════════╝
"""

import sys
import math
import random
import time
import os
import threading
import webbrowser
import json
import html
import importlib.util
import re
import subprocess
import platform
import urllib.parse
from datetime import datetime

import numpy as np
import queue
import psutil
import pyaudio
import speech_recognition as sr
import audio_output
import shutil
import i18n
import backdrop as bgmod
import apps
from gestures import GestureEngine
from i18n import tr, ALL_COMMANDS_EN

import logging
from logging.handlers import RotatingFileHandler

import ctypes
from ctypes import cast, POINTER


# ═══════════════════════════════════════════════════════════════
# 0. СОВМЕСТИМОСТЬ: ВЕРСИЯ WINDOWS И ВЫБОР QT
# ═══════════════════════════════════════════════════════════════

def windows_version():
    """(major, minor, build). RtlGetVersion не зависит от манифеста Python и не врёт."""
    try:
        class OSVERSIONINFOW(ctypes.Structure):
            _fields_ = [("dwOSVersionInfoSize", ctypes.c_uint32),
                        ("dwMajorVersion", ctypes.c_uint32),
                        ("dwMinorVersion", ctypes.c_uint32),
                        ("dwBuildNumber", ctypes.c_uint32),
                        ("dwPlatformId", ctypes.c_uint32),
                        ("szCSDVersion", ctypes.c_wchar * 128)]
        info = OSVERSIONINFOW()
        info.dwOSVersionInfoSize = ctypes.sizeof(info)
        if ctypes.windll.ntdll.RtlGetVersion(ctypes.byref(info)) == 0:
            return info.dwMajorVersion, info.dwMinorVersion, info.dwBuildNumber
    except Exception:
        pass
    try:
        v = sys.getwindowsversion()
        return v.major, v.minor, v.build
    except Exception:
        return (0, 0, 0)


WIN_VER = windows_version()
IS_LEGACY_WIN = 0 < WIN_VER[0] < 10      # Windows 7 / 8 / 8.1


def _qt_order():
    """Windows 8.1: только PyQt5 (Qt 5.15). Qt 6 на 8.1 не запускается:
    падает с "could not load the Qt platform plugin windows", поэтому запасного
    PySide6 там нет. Windows 10/11: PySide6, PyQt5 как запасной.
    Принудительно: переменная окружения JARVIS_QT=PyQt5 или PySide6."""
    forced = os.environ.get("JARVIS_QT", "").strip()
    if forced in ("PyQt5", "PySide6"):
        return (forced,)
    return ("PyQt5",) if IS_LEGACY_WIN else ("PySide6", "PyQt5")


QT_API = None
_qt_errors = []
for _api in _qt_order():
    try:
        if _api == "PySide6":
            from PySide6.QtCore import Qt, QTimer, QPoint, QPointF
            from PySide6.QtGui import QImage, QPixmap, QFont, QPainter, QPen, QColor, QPainterPath
            from PySide6.QtWidgets import (
                QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                QPushButton, QLabel, QMessageBox, QDialog, QCheckBox,
                QComboBox, QLineEdit, QListWidget, QFileDialog, QGroupBox,
                QTabWidget, QSlider, QScrollArea, QSizePolicy,
                QStackedWidget, QFrame, QInputDialog
            )
        else:
            from PyQt5.QtCore import Qt, QTimer, QPoint, QPointF
            from PyQt5.QtGui import QImage, QPixmap, QFont, QPainter, QPen, QColor, QPainterPath
            from PyQt5.QtWidgets import (
                QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                QPushButton, QLabel, QMessageBox, QDialog, QCheckBox,
                QComboBox, QLineEdit, QListWidget, QFileDialog, QGroupBox,
                QTabWidget, QSlider, QScrollArea, QSizePolicy,
                QStackedWidget, QFrame, QInputDialog
            )
        QT_API = _api
        break
    except ImportError as _e:
        _qt_errors.append(f"{_api}: {_e}")

if QT_API is None:
    if IS_LEGACY_WIN:
        _hint = ("Установите PyQt5 одной командой:\n"
                 "    python -m pip install PyQt5==5.15.11\n"
                 "и запустите программу снова.")
    else:
        _hint = "Установите библиотеку одной командой:\n    python -m pip install PySide6"
    print("Не найдена библиотека интерфейса (Qt).")
    print(_hint)
    for _line in _qt_errors:
        print("  ", _line)
    try:
        input("Нажмите Enter, чтобы закрыть...")
    except Exception:
        pass
    sys.exit(1)


def event_global_pos(event):
    """Позиция курсора на экране: Qt 6 и Qt 5 называют метод по-разному."""
    try:
        return event.globalPosition().toPoint()     # Qt 6
    except AttributeError:
        return event.globalPos()                    # Qt 5


def run_exec(obj):
    """exec() у Qt 6, exec_() у старых привязок."""
    fn = getattr(obj, "exec", None)
    return fn() if fn else obj.exec_()


# Рабочая папка = папка программы: иначе logs/, sounds/ и script/ создаются там,
# откуда запущен ярлык (например, в System32), и звуки не находятся.
try:
    os.chdir(os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__)))
except Exception:
    pass

# Консоль старой Windows может не уметь часть символов: заменяем их, а не падаем.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# 1. КОНФИГУРАЦИЯ
# ═══════════════════════════════════════════════════════════════

VERSION = "2.4.5"
QUALITY_MODE = 4
SCRIPT_FOLDER = "script"

# Палитра: почти монохром + один спокойный акцент на состояния
COLORS = {"bg": "#0e0e0f", "cyan": "#e8e8e8"}
UI = {
    "text": "#e8e8e8",
    "dim": "#6b6b70",
    "border": "#202022",
    "ok": "#7ddc9a",
    "error": "#e57373",
}
STATE_COLORS = {
    "idle": (232, 232, 232),
    "success": (125, 220, 154),
    "error": (229, 115, 115),
}

# Твои кастомные команды
MY_SOUNDS = {
    "wo": ["woman", "girl", "mom", "мама", "баба", "гирл", "герл", "вумен", "вуман", "женшина", "женщина"],
    "med": ["medic", "брат", "медик", "пиро", "mge", "brother"],
}

# Триггерные слова
TRIGGER_WORDS = ["джарвис", "jarvis", "джарвис аз", "jarvis az", "jarvisaz", "джарвисаз"]


# ═══════════════════════════════════════════════════════════════
# 2. ЛОГИРОВАНИЕ
# ═══════════════════════════════════════════════════════════════

os.makedirs("logs", exist_ok=True)

log_file = os.path.join("logs", f"jarvis_{datetime.now().strftime('%Y-%m-%d')}.log")

logger = logging.getLogger('JARVIS_AZ')
logger.setLevel(logging.DEBUG)

# Что показывать при распознавании (вкладка «Логи» в настройках). Файл в logs/ пишется полностью.
LOG_OPTS = {"time": True, "ms": True, "phrase": True, "volume": True, "engine": True,
            "words": True, "confidence": False, "decision": True, "lag": True, "queue": False}
LOG_OPTION_LABELS = [
    ("time", "Время: часы, минуты, секунды"),
    ("ms", "Миллисекунды"),
    ("phrase", "Длительность фразы"),
    ("volume", "Громкость фразы (дБ)"),
    ("engine", "Кто ответил (движок)"),
    ("words", "Что распознано (текст)"),
    ("confidence", "Уверенность движка"),
    ("decision", "Решение: команда или нет"),
    ("lag", "Задержка после конца фразы"),
    ("queue", "Очередь распознавания"),
]


class ConsoleFormatter(logging.Formatter):
    """Консоль: время по настройкам. Строки распознавания (nostamp) пишут время фразы сами."""

    def format(self, record):
        prefix = ""
        if LOG_OPTS["time"] and not getattr(record, "nostamp", False):
            ts = datetime.fromtimestamp(record.created)
            prefix = ts.strftime("%H:%M:%S")
            if LOG_OPTS["ms"]:
                prefix += f".{ts.microsecond // 1000:03d}"
            prefix += " | "
        return f"{prefix}{record.levelname} | {record.getMessage()}"


formatter = logging.Formatter('%(asctime)s.%(msecs)03d | %(levelname)s | %(message)s', datefmt='%H:%M:%S')

# Файловый обработчик
file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)

# Консольный обработчик
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(ConsoleFormatter())

logger.addHandler(file_handler)
logger.addHandler(console_handler)

log_info = logger.info
log_error = logger.error
log_debug = logger.debug

log_info(f"🖥 Windows {WIN_VER[0]}.{WIN_VER[1]} (сборка {WIN_VER[2]}), Python {platform.python_version()}, Qt: {QT_API}")
if IS_LEGACY_WIN and QT_API != "PyQt5":
    log_error("⚠️ Windows 8.1 без PyQt5 не работает. Выполните: python -m pip install PyQt5==5.15.11")


# ═══════════════════════════════════════════════════════════════
# 3. ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
# ═══════════════════════════════════════════════════════════════

command_status = "idle"
status_timer = 0

smooth_cpu = 0.0
last_cpu_time = 0.0
is_running = True

fullscreen_mode = False
greeting_mode = False
music_folder = ""

user_commands = {}
settings_dialog = None

heard_text = ""
heard_time = 0.0
mic_index = None
mic_reload = False
voice_reply = False
language = "ru"              # язык интерфейса и голоса: "ru" | "en"
gestures_enabled = False     # распознавание жестов камерой

# Движки распознавания речи: можно включать несколько сразу
ENGINES = ("vosk_ru", "vosk_en", "google_ru", "google_en")
DEFAULT_ENGINES = ["vosk_ru"]
recognition_engines = list(DEFAULT_ENGINES)

# Фон окна (см. backdrop.py) и сохранённые фоны
current_bg = bgmod.normalize_bg(None)
saved_backgrounds = []


# ═══════════════════════════════════════════════════════════════
# 4. УПРАВЛЕНИЕ ГРОМКОСТЬЮ
# ═══════════════════════════════════════════════════════════════

def get_volume_interface():
    try:
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        devices = AudioUtilities.GetSpeakers()
        if hasattr(devices, "EndpointVolume"):      # новые версии pycaw
            return devices.EndpointVolume
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return cast(interface, POINTER(IAudioEndpointVolume))
    except Exception as e:
        log_error(f"Ошибка получения интерфейса громкости: {e}")
        return None


def set_volume(level):
    try:
        vol = get_volume_interface()
        if vol:
            vol.SetMasterVolumeLevelScalar(level / 100.0, None)
            log_info(f"🔊 Громкость: {level}%")
            return True
    except:
        pass

    try:
        current = 50
        diff = level - current
        key = 0xAF if diff > 0 else 0xAE
        for _ in range(abs(diff) // 2):
            ctypes.windll.user32.keybd_event(key, 0, 0, 0)
            ctypes.windll.user32.keybd_event(key, 0, 2, 0)
            time.sleep(0.01)
        return True
    except:
        return False


def get_volume():
    try:
        vol = get_volume_interface()
        if vol:
            return int(vol.GetMasterVolumeLevelScalar() * 100)
    except:
        pass
    return 50


def volume_up(amount):
    current = get_volume()
    new_volume = min(100, current + amount)
    set_volume(new_volume)
    return new_volume


def volume_down(amount):
    current = get_volume()
    new_volume = max(0, current - amount)
    set_volume(new_volume)
    return new_volume


def volume_mute():
    try:
        vol = get_volume_interface()
        if vol:
            vol.SetMute(True, None)
            log_info("🔇 Звук выключен")
            return True
    except:
        pass

    try:
        ctypes.windll.user32.keybd_event(0xAD, 0, 0, 0)
        ctypes.windll.user32.keybd_event(0xAD, 0, 2, 0)
        return True
    except:
        return False


def volume_unmute():
    try:
        vol = get_volume_interface()
        if vol:
            vol.SetMute(False, None)
            log_info("🔊 Звук включен")
            return True
    except:
        pass

    try:
        ctypes.windll.user32.keybd_event(0xAD, 0, 0, 0)
        ctypes.windll.user32.keybd_event(0xAD, 0, 2, 0)
        return True
    except:
        return False


def volume_max():
    set_volume(100)


# ═══════════════════════════════════════════════════════════════
# 5. ЗАХВАТ АУДИО
# ═══════════════════════════════════════════════════════════════

pa_instance = pyaudio.PyAudio()
audio_stream = None
voice_level = 0.0
_audio_lock = threading.Lock()


def init_audio():
    global audio_stream
    try:
        with _audio_lock:
            audio_stream = pa_instance.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=44100,
                input=True,
                frames_per_buffer=1024
            )
        log_info("🎤 Аудио поток инициализирован")
    except Exception as e:
        log_error(f"❌ Ошибка инициализации аудио: {e}")
        audio_stream = None


def get_audio_level():
    global voice_level, audio_stream
    if audio_stream is None:
        return 0.0

    try:
        with _audio_lock:
            if audio_stream is None:
                return 0.0

            avail = audio_stream.get_read_available()
            if avail <= 0:
                return min(1.5, voice_level)

            data = audio_stream.read(min(avail, 4096), exception_on_overflow=False)
            audio_data = np.frombuffer(data, dtype=np.int16)
            volume = np.abs(audio_data).mean()

            voice_level = voice_level * 0.7 + (volume / 4500) * 0.3
            return min(1.5, voice_level)
    except:
        return 0.0


init_audio()


# ═══════════════════════════════════════════════════════════════
# 6. ДЕЙСТВИЯ (ЭКШЕНЫ)
# ═══════════════════════════════════════════════════════════════

def _tap_keys(*vks, hold=0.03):
    """Нажимает сочетание клавиш и отпускает в обратном порядке."""
    user32 = ctypes.windll.user32
    for vk in vks:
        user32.keybd_event(vk, 0, 0, 0)
    time.sleep(hold)
    for vk in reversed(vks):
        user32.keybd_event(vk, 0, 2, 0)


def take_screenshot():
    """Windows 10/11: Win+Shift+S (вырезка области).
    Windows 8/8.1 такого сочетания не знают, там Win+PrtScn: весь экран сразу
    сохраняется в «Изображения\\Снимки экрана»."""
    VK_LWIN, VK_SHIFT, VK_S, VK_SNAPSHOT = 0x5B, 0x10, 0x53, 0x2C
    try:
        if IS_LEGACY_WIN:
            _tap_keys(VK_LWIN, VK_SNAPSHOT)
            log_info("📸 Скриншот: Win+PrtScn (папка Изображения\\Снимки экрана)")
        else:
            _tap_keys(VK_LWIN, VK_SHIFT, VK_S)
            log_info("📸 Скриншот: Win+Shift+S")
        return True
    except Exception as e:
        log_error(f"❌ Ошибка скриншота: {e}")
        return False


def empty_recycle_bin():
    try:
        SHEmptyRecycleBin = ctypes.windll.shell32.SHEmptyRecycleBinW
        flags = 0x00000001 | 0x00000002 | 0x00000004
        result = SHEmptyRecycleBin(None, None, flags)
        if result == 0:
            log_info("🗑 Корзина очищена")
            audio_output.play_trigger("привет")
            return True
    except Exception as e:
        log_error(f"❌ Ошибка очистки корзины: {e}")
    return False


def restart_explorer():
    try:
        subprocess.run("taskkill /f /im explorer.exe", shell=True, capture_output=True)
        time.sleep(1)
        subprocess.Popen("explorer.exe", shell=True)
        log_info("🔄 Проводник перезапущен")
        audio_output.play_trigger("привет")
        return True
    except Exception as e:
        log_error(f"❌ Ошибка перезапуска проводника: {e}")
        return False


def minimize_all_windows():
    try:
        if platform.system() == "Windows":
            user32 = ctypes.WinDLL('user32')
            user32.keybd_event(0x5B, 0, 0, 0)
            user32.keybd_event(0x44, 0, 0, 0)
            time.sleep(0.05)
            user32.keybd_event(0x44, 0, 2, 0)
            user32.keybd_event(0x5B, 0, 2, 0)
            log_info("🪟 Все окна свернуты")
            audio_output.play_trigger("привет")
            return True
    except Exception as e:
        log_error(f"❌ Ошибка сворачивания окон: {e}")
        return False


def shutdown_pc():
    os.system("shutdown /s /t 1")
    log_info("🔄 Выключение...")
    audio_output.play_trigger("стоп")
    return True


def restart_pc():
    os.system("shutdown /r /t 1")
    log_info("🔄 Перезагрузка...")
    audio_output.play_trigger("привет")
    return True


def lock_pc():
    ctypes.windll.user32.LockWorkStation()
    log_info("🔒 ПК заблокирован")
    audio_output.play_trigger("привет")
    return True


def _camera_app_registered():
    """Есть ли в системе обработчик microsoft.windows.camera:"""
    try:
        import winreg
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "microsoft.windows.camera"))
        return True
    except Exception:
        return False


def open_camera():
    obs_paths = [
        r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\OBS Studio.lnk",
        r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
        r"C:\Program Files (x86)\obs-studio\bin\64bit\obs64.exe"
    ]

    for path in obs_paths:
        if os.path.exists(path):
            os.startfile(path)
            log_info("📷 OBS Studio запущен")
            audio_output.play_trigger("привет")
            return True

    # На старой Windows без приложения «Камера» адрес microsoft.windows.camera:
    # открыл бы окно «Чем открыть?», поэтому сначала проверяем, что он зарегистрирован.
    if IS_LEGACY_WIN and not _camera_app_registered():
        log_error("❌ Приложение «Камера» не найдено. Установите OBS Studio "
                  "или приложение «Камера» из Магазина Windows")
        return False

    subprocess.run(["start", "microsoft.windows.camera:"], shell=True)
    log_info("📷 Камера Windows запущена")
    audio_output.play_trigger("привет")
    return True


def clean_system():
    log_info("🧹 Начало очистки...")
    deleted_count = 0
    deleted_size = 0

    temp_folders = [
        os.environ.get('TEMP', ''),
        os.environ.get('TMP', ''),
        os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Temp'),
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Temp'),
    ]

    for folder in temp_folders:
        if folder and os.path.exists(folder):
            try:
                for root, dirs, files in os.walk(folder):
                    for file in files:
                        try:
                            path = os.path.join(root, file)
                            if os.path.exists(path):
                                size = os.path.getsize(path)
                                os.remove(path)
                                deleted_count += 1
                                deleted_size += size
                        except:
                            pass
            except:
                pass

    os.system("ipconfig /flushdns > nul 2>&1")
    log_info("✅ DNS кэш очищен")

    browser_paths = [
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Google', 'Chrome', 'User Data', 'Default', 'Cache'),
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'Edge', 'User Data', 'Default', 'Cache'),
    ]

    for path in browser_paths:
        if os.path.exists(path):
            try:
                for root, dirs, files in os.walk(path):
                    for file in files:
                        try:
                            file_path = os.path.join(root, file)
                            if os.path.exists(file_path):
                                size = os.path.getsize(file_path)
                                os.remove(file_path)
                                deleted_count += 1
                                deleted_size += size
                        except:
                            pass
            except:
                pass

    deleted_mb = deleted_size / (1024 * 1024)
    log_info(f"✅ Очищено! Удалено {deleted_count} файлов ({deleted_mb:.2f} MB)")
    return deleted_count, deleted_mb


def google_search(query):
    encoded = urllib.parse.quote(query)
    webbrowser.open(f"https://www.google.com/search?q={encoded}")
    log_info(f"🔍 Поиск: {query}")


# ─── ПРОГРАММЫ И ИГРЫ: «открой spotify» (таблица в apps.py) ───
# ВСЕ НОВЫЕ КОМАНДЫ ДОЛЖНЫ ВЫПОЛНЯТЬСЯ С КАСТОМНЫМИ ГОЛОСАМИ:
# после запуска играет звук «кастом» (да сэр, делаю, хорошо), без платной озвучки.

_APP_SKIP_WORDS = ("uninstall", "удал", "readme", "help", "справк", "manual", "docs", "license",
                   "лиценз", "website", "сайт", "support", "документац")
_start_menu_cache = {"time": 0.0, "items": []}


def _start_menu_items(force=False):
    """Все ярлыки из меню «Пуск»: [(имя в нижнем регистре, путь)]. Список обновляется раз в минуту."""
    now = time.time()
    if not force and _start_menu_cache["items"] and now - _start_menu_cache["time"] < 60:
        return _start_menu_cache["items"]
    items = []
    roots = [os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "Microsoft", "Windows", "Start Menu", "Programs"),
             os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs")]
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for folder, _dirs, files in os.walk(root):
            for f in files:
                base, ext = os.path.splitext(f)
                if ext.lower() in (".lnk", ".url"):
                    items.append((base.lower(), os.path.join(folder, f)))
    _start_menu_cache.update(time=now, items=items)
    return items


def _find_start_menu(names):
    """Ярлык, в имени которого есть одно из names. Из подходящих берётся самое короткое имя:
    «Steam», а не «Steam Support Center»."""
    for force in (False, True):                      # со второго раза список читаем заново (вдруг только что установили)
        items = _start_menu_items(force)
        for name in names.split("|"):
            name = name.strip().lower()
            found = [(n, p) for n, p in items
                     if name in n and not any(w in n for w in _APP_SKIP_WORDS)]
            if found:
                return min(found, key=lambda x: len(x[0]))[1]
    return None


def _protocol_registered(scheme):
    """Есть ли в Windows программа для адреса вида spotify: (иначе откроется окно «Чем открыть?»)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, scheme) as key:
            winreg.QueryValueEx(key, "URL Protocol")
        return True
    except Exception:
        return False


def launch_app(app):
    """Пробует способы запуска из apps.py по порядку. True, если что-то запустилось."""
    import glob
    for kind, value in app["launch"]:
        try:
            if kind == "lnk":
                path = _find_start_menu(value)
                if path:
                    os.startfile(path)
                    log_info(f"🚀 {app['title']}: ярлык {os.path.basename(path)}")
                    return True
            elif kind == "exe":
                for pattern in value.split("|"):
                    for path in glob.glob(os.path.expandvars(pattern)):
                        if os.path.isfile(path):
                            os.startfile(path)
                            log_info(f"🚀 {app['title']}: {path}")
                            return True
            elif kind == "proto":
                if _protocol_registered(value):
                    os.startfile(f"{value}:")
                    log_info(f"🚀 {app['title']}: протокол {value}:")
                    return True
            elif kind == "steam":
                if _protocol_registered("steam"):
                    os.startfile(f"steam://rungameid/{value}")
                    log_info(f"🚀 {app['title']}: Steam, игра {value}")
                    return True
            elif kind == "cmd":
                subprocess.Popen(f'start "" {value}', shell=True)
                log_info(f"🚀 {app['title']}: команда {value}")
                return True
            elif kind == "url":
                webbrowser.open(value)
                log_info(f"🚀 {app['title']}: сайт {value}")
                return True
        except Exception as e:
            log_error(f"⚠️ {app['title']}: способ «{kind}» не сработал: {e}")
    log_error(f"❌ Не нашёл «{app['title']}» на этом компьютере (нет ярлыка в меню «Пуск»)")
    return False


def restart_jarvis():
    global audio_stream, voice_level, mic_reload
    mic_reload = True
    log_info("🔄 Перезагрузка JARVIS AZ...")

    try:
        if audio_stream:
            with _audio_lock:
                audio_stream.stop_stream()
                audio_stream.close()
            audio_stream = None

        time.sleep(0.3)
        init_audio()
        voice_level = 0.0

        try:
            audio_output.reset_queues()
        except:
            pass

        global command_status, status_timer
        command_status = "idle"
        status_timer = time.time()

        log_info("✅ JARVIS AZ перезагружен!")
        return True
    except Exception as e:
        log_error(f"❌ Ошибка перезагрузки: {e}")
        return False


# ═══════════════════════════════════════════════════════════════
# 7. ХРАНЕНИЕ ДАННЫХ
# ═══════════════════════════════════════════════════════════════

os.makedirs(SCRIPT_FOLDER, exist_ok=True)

COMMANDS_FILE = os.path.join(SCRIPT_FOLDER, "user_commands.json")
SETTINGS_FILE = os.path.join(SCRIPT_FOLDER, "settings.json")


def _norm_command(v):
    """Старый формат: строка-путь. Новый: {"type": file | folder | url, "target": ...}."""
    if isinstance(v, str):
        return {"type": "file", "target": v} if v else None
    if isinstance(v, dict) and v.get("target"):
        kind = v.get("type", "file")
        return {"type": kind if kind in ("file", "folder", "url") else "file", "target": str(v["target"])}
    return None


def open_custom_command(item):
    """Открывает файл, программу, папку или сайт из пользовательской команды."""
    if item.get("type") == "url":
        webbrowser.open(item["target"])
    else:
        os.startfile(item["target"])


def _command_label(item):
    kind = item.get("type", "file")
    target = item.get("target", "")
    if kind == "url":
        return f"{tr('сайт')}: {target}"
    name = os.path.basename(os.path.normpath(target)) or target
    if kind == "folder":
        return f"{tr('папка')}: {name}"
    return name


def load_commands():
    global user_commands
    if os.path.exists(COMMANDS_FILE):
        try:
            with open(COMMANDS_FILE, 'r', encoding='utf-8') as f:
                raw = json.load(f)
                user_commands = {k: n for k, v in raw.items() if (n := _norm_command(v))}
            log_info(f"📂 Загружено {len(user_commands)} команд")
        except:
            user_commands = {}


def save_commands():
    try:
        with open(COMMANDS_FILE, 'w', encoding='utf-8') as f:
            json.dump(user_commands, f, ensure_ascii=False, indent=2)
        log_info(f"💾 Сохранено {len(user_commands)} команд")
    except Exception as e:
        log_error(f"❌ Ошибка сохранения: {e}")


def load_settings():
    global QUALITY_MODE, greeting_mode, current_bg, saved_backgrounds, fullscreen_mode
    global music_folder, mic_index, voice_reply, language, gestures_enabled, recognition_engines
    if not os.path.exists(SETTINGS_FILE):
        return
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return

    QUALITY_MODE = data.get('quality_mode', 4)
    mic_index = data.get('mic_index', None)
    voice_reply = bool(data.get('voice_reply', False))
    greeting_mode = bool(data.get('greeting_mode', False))
    fullscreen_mode = bool(data.get('fullscreen_mode', False))
    music_folder = data.get('music_folder', "")
    language = "en" if data.get('language') == "en" else "ru"
    gestures_enabled = bool(data.get('gestures_enabled', False))
    LOG_OPTS.update({k: bool(v) for k, v in data.get('log_options', {}).items() if k in LOG_OPTS})

    # Движки: старые значения 'vosk' и 'google' переводим в новые имена
    engines = data.get('recognition_engines')
    if not isinstance(engines, list):
        old = data.get('recognition_mode', 'google')
        engines = ['vosk_ru'] if old == 'vosk' else ['google_ru']
    migrated = []
    for e in engines:
        e = {'vosk': 'vosk_ru', 'google': 'google_ru'}.get(e, e)
        if e in ENGINES and e not in migrated:
            migrated.append(e)
    recognition_engines = migrated or list(DEFAULT_ENGINES)

    # Фон: старый custom_background превращаем в режим «на весь экран»
    if 'current_bg' in data:
        current_bg = bgmod.normalize_bg(data.get('current_bg'))
    else:
        old_bg = data.get('custom_background')
        if old_bg and os.path.exists(old_bg):
            current_bg = bgmod.normalize_bg({"mode": "full", "image": old_bg})
        else:
            current_bg = bgmod.normalize_bg(None)
    saved_backgrounds = [bgmod.normalize_bg(x) for x in data.get('saved_backgrounds', [])
                         if isinstance(x, dict)]


def save_settings():
    try:
        data = {
            'language': language,
            'recognition_engines': list(recognition_engines),
            'voice_reply': voice_reply,
            'gestures_enabled': gestures_enabled,
            'current_bg': current_bg,
            'saved_backgrounds': saved_backgrounds,
            'quality_mode': QUALITY_MODE,
            'greeting_mode': greeting_mode,
            'fullscreen_mode': fullscreen_mode,
            'music_folder': music_folder,
            'mic_index': mic_index,
            'log_options': dict(LOG_OPTS),
        }
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_error(f"❌ Ошибка сохранения настроек: {e}")


load_commands()
load_settings()
i18n.set_language(language)


# ═══════════════════════════════════════════════════════════════
# 8. СПИСОК КОМАНД (ДЛЯ ИНФО)
# ═══════════════════════════════════════════════════════════════

ALL_COMMANDS = {
    "🔊 Управление звуком": [
        "звук плюс 1,5,10,15,30,50 — увеличить громкость",
        "звук минус 1,5,10,15,30,50 — уменьшить громкость",
        "полный звук, макс — 100%",
        "выключить звук — выключить",
        "включить звук — включить"
    ],
    "📸 Скриншот": ["скриншот, снимок, скрин — Win+Shift+S"],
    "🌐 Поиск": ["поиск, ищи, найти, гуглить [запрос]"],
    "💻 Система": ["браузер, гугл — открыть Google", "проводник, папка — открыть папку", "ютуб — YouTube", "tf2 — Team Fortress 2"],
    "🪟 Окна": ["сверни все окна — Win+D", "перезагрузи проводник"],
    "🗑 Корзина": ["очисти корзину, удали мусор"],
    "📷 Камера": ["запусти камеру, открой камеру"],
    "🔒 Блокировка": ["заблокируй компьютер, блокировка"],
    "🔄 Управление ПК": ["выключи компьютер", "перезагрузи компьютер"],
    "🛠 Утилиты": ["очистка, чистка — очистить систему", "рестарт, перезагрузка — перезагрузить Джарвиса", "стоп, выход — выключить"]
}


# ═══════════════════════════════════════════════════════════════
# 9. ОСНОВНАЯ КОМАНДА (execute_command)
# ═══════════════════════════════════════════════════════════════

def strip_trigger(t):
    """Убирает обращение («Джарвис, ...») из начала фразы."""
    t = t.strip()
    changed = True
    while changed:
        changed = False
        for w in sorted(TRIGGER_WORDS, key=len, reverse=True):
            if t.startswith(w):
                t = t[len(w):].lstrip(" ,.!?:-—")
                changed = True
    return t


def execute_command(text):
    global command_status, status_timer, music_folder, is_running
    text = i18n.translate_command(text)     # «volume plus 1» -> «звук плюс 1»
    text_lower = text.lower()
    stripped = strip_trigger(text_lower)
    if stripped:                # «джарвис» без команды остаётся приветствием
        text_lower = stripped
    command_status = "idle"

    # ─── СТОП ───────────────────────────────────────────────────
    if "стоп" in text_lower or "выход" in text_lower:
        audio_output.play_trigger("стоп")
        command_status = "success"
        status_timer = time.time()
        time.sleep(0.5)
        is_running = False
        return False

    # ─── ПРИВЕТСТВИЕ ──────────────────────────────────────────
    greetings = ["привет", "джарвис", "jarvis", "здарова", "хай", "hello", "приветик", "салют", "джар"]
    if any(w in text_lower for w in greetings):
        audio_output.play_trigger("привет")
        command_status = "success"
        status_timer = time.time()
        return True

    # ─── КАСТОМНЫЕ КОМАНДЫ (MY_SOUNDS) ───────────────────────
    for sound_key, words in MY_SOUNDS.items():
        if any(w in text_lower for w in words):
            if sound_key == "wo":
                browsers = ["chrome", "msedge", "firefox", "opera", "brave"]
                for b in browsers:
                    subprocess.run(f"taskkill /f /im {b}.exe", shell=True, capture_output=True)
                log_info("🌐 Все браузеры закрыты")

            audio_output.play_trigger(sound_key)
            command_status = "success"
            status_timer = time.time()
            return True

    # ─── ПРОГРАММЫ И ИГРЫ: «открой spotify», «запусти майнкрафт» ─────
    # Свои команды из настроек важнее: если фраза содержит такую, программу не ищем.
    if not any(len(c) >= 3 and c in text_lower for c in user_commands):
        app = apps.find_app(text_lower)
        if app:
            ok = launch_app(app)
            if ok:
                audio_output.play_trigger("кастом")
            command_status = "success" if ok else "error"
            status_timer = time.time()
            return True

    # ─── ПОИСК В GOOGLE ──────────────────────────────────────
    search_keywords = ["поиск", "ищи", "найти", "гуглить", "найди", "поищи", "google", "гугл"]
    for kw in search_keywords:
        if text_lower.startswith(kw):
            query = text_lower.replace(kw, "").strip()
            if query:
                audio_output.play_trigger("поиск")
                google_search(query)
                speak("Ищу")
                command_status = "success"
                status_timer = time.time()
                return True

    # ─── ГРОМКОСТЬ ────────────────────────────────────────────
    if "звук" in text_lower or "громкость" in text_lower:
        if "выключить" in text_lower or "выкл" in text_lower:
            volume_mute()
            audio_output.play_trigger("стоп")
            command_status = "success"
            status_timer = time.time()
            return True

        if "включить" in text_lower or "вкл" in text_lower:
            volume_unmute()
            audio_output.play_trigger("привет")
            command_status = "success"
            status_timer = time.time()
            return True

        if "полный" in text_lower or "макс" in text_lower:
            volume_max()
            audio_output.play_trigger("привет")
            command_status = "success"
            status_timer = time.time()
            return True

        numbers = re.findall(r'\d+', text_lower)

        if "плюс" in text_lower or "+" in text_lower:
            amount = int(numbers[0]) if numbers else 10
            volume_up(amount)
            audio_output.play_trigger("привет")
            command_status = "success"
            status_timer = time.time()
            return True

        if "минус" in text_lower or "-" in text_lower:
            amount = int(numbers[0]) if numbers else 10
            volume_down(amount)
            audio_output.play_trigger("привет")
            command_status = "success"
            status_timer = time.time()
            return True

    # ─── СКРИНШОТ ─────────────────────────────────────────────
    if any(w in text_lower for w in ["скриншот", "снимок", "скрин"]):
        take_screenshot()
        speak("Скриншот")
        audio_output.play_trigger("привет")
        command_status = "success"
        status_timer = time.time()
        return True

    # ─── КОРЗИНА ──────────────────────────────────────────────
    if any(w in text_lower for w in ["очисти корзину", "очисти мусор", "удали мусор"]):
        empty_recycle_bin()
        command_status = "success"
        status_timer = time.time()
        return True

    # ─── ПРОВОДНИК ────────────────────────────────────────────
    if any(w in text_lower for w in ["перезагрузи проводник", "перезапусти проводник"]):
        restart_explorer()
        command_status = "success"
        status_timer = time.time()
        return True

    # ─── СВЕРНУТЬ ОКНА ────────────────────────────────────────
    if any(w in text_lower for w in ["сверни все окна", "сверни всё", "показать рабочий стол"]):
        minimize_all_windows()
        command_status = "success"
        status_timer = time.time()
        return True

    # ─── КАМЕРА ───────────────────────────────────────────────
    if any(w in text_lower for w in ["запусти камеру", "открой камеру", "камера", "вебкамера"]):
        cam_ok = open_camera()
        speak("Открываю камеру" if cam_ok else "Камера не найдена")
        command_status = "success" if cam_ok else "error"
        status_timer = time.time()
        return True

    # ─── БЛОКИРОВКА ───────────────────────────────────────────
    if any(w in text_lower for w in ["заблокируй компьютер", "блокировка", "заблокировать пк"]):
        lock_pc()
        command_status = "success"
        status_timer = time.time()
        return True

    # ─── ВЫКЛЮЧЕНИЕ ПК ──────────────────────────────────────
    if any(w in text_lower for w in ["выключи компьютер", "отключи компьютер", "заверши работу"]):
        shutdown_pc()
        command_status = "success"
        status_timer = time.time()
        return True

    # ─── ПЕРЕЗАГРУЗКА ПК ─────────────────────────────────────
    if any(w in text_lower for w in ["перезагрузи компьютер", "перезапусти компьютер", "рестарт пк"]):
        restart_pc()
        command_status = "success"
        status_timer = time.time()
        return True

    # ─── МУЗЫКА ───────────────────────────────────────────────
    if any(w in text_lower for w in ["музыка", "песня"]):
        if music_folder and os.path.exists(music_folder):
            os.startfile(music_folder)
            speak("Открываю музыку")
            command_status = "success"
            status_timer = time.time()
            return True
        command_status = "error"
        status_timer = time.time()
        return True

    # ─── БРАУЗЕР ──────────────────────────────────────────────
    if any(w in text_lower for w in ["браузер", "гугл", "google"]):
        audio_output.play_trigger("браузер")
        webbrowser.open("https://www.google.com")
        speak("Открываю браузер")
        command_status = "success"
        status_timer = time.time()
        return True

    # ─── ПРОВОДНИК (открыть) ──────────────────────────────────
    if any(w in text_lower for w in ["проводник", "папка", "открой папку", "файл"]):
        audio_output.play_trigger("проводник")
        os.startfile(os.path.expanduser("~"))
        speak("Открываю проводник")
        command_status = "success"
        status_timer = time.time()
        return True

    # ─── TF2 ───────────────────────────────────────────────────
    if any(w in text_lower for w in ["team fortress", "tf", "тф", "тим фортрес", "fortress"]):
        audio_output.play_trigger("tf2")
        speak("Запускаю игру")
        try:
            os.startfile("C:/Users/Admins/Desktop/Team Fortress 2.url")
        except:
            pass
        command_status = "success"
        status_timer = time.time()
        return True

    # ─── ЮТУБ ──────────────────────────────────────────────────
    if any(w in text_lower for w in ["ютуб", "youtube", "video", "видео"]):
        audio_output.play_trigger("ютуб")
        webbrowser.open("https://youtube.com")
        speak("Открываю ютуб")
        command_status = "success"
        status_timer = time.time()
        return True

    # ─── ОЧИСТКА ──────────────────────────────────────────────
    if any(w in text_lower for w in ["очистка", "чистка", "очистить"]):
        audio_output.play_trigger("очистка")
        clean_system()
        speak("Система очищена")
        command_status = "success"
        status_timer = time.time()
        return True

    # ─── РЕСТАРТ ДЖАРВИСА ─────────────────────────────────────
    if any(w in text_lower for w in ["рестарт", "перезагрузка", "перезагрузи", "reset", "ресет", "restart"]):
        audio_output.play_trigger("привет") 

        # 1. Объявляем функцию ВНУТРИ блока (обрати внимание на отступы!)
        def restart_jarvis():
            import sys
            import os
            import subprocess
            
            python = sys.executable
            script_path = sys.argv[0]
            subprocess.Popen([python, script_path], creationflags=subprocess.CREATE_NEW_CONSOLE)
            os._exit(0)

        # 2. ОБЯЗАТЕЛЬНО вызываем её сразу после объявления, иначе она просто запишется в память, но не запустится!
        restart_jarvis()
        
        return True

    # ─── ПОЛЬЗОВАТЕЛЬСКИЕ КОМАНДЫ ─────────────────────────────
    for cmd, item in user_commands.items():
        if cmd in text_lower:
            try:
                audio_output.play_trigger("кастом")
                open_custom_command(item)
                speak("Открываю")
                command_status = "success"
                status_timer = time.time()
                return True
            except:
                pass

    command_status = "error"
    status_timer = time.time()
    return True


# ═══════════════════════════════════════════════════════════════
# 10. ГОЛОСОВОЙ ЦИКЛ
# ═══════════════════════════════════════════════════════════════

_RU_UNITS = {"ноль": 0, "один": 1, "одну": 1, "два": 2, "две": 2, "три": 3, "четыре": 4,
             "пять": 5, "шесть": 6, "семь": 7, "восемь": 8, "девять": 9}
_RU_TEENS = {"десять": 10, "одиннадцать": 11, "двенадцать": 12, "тринадцать": 13, "четырнадцать": 14,
             "пятнадцать": 15, "шестнадцать": 16, "семнадцать": 17, "восемнадцать": 18, "девятнадцать": 19}
_RU_TENS = {"двадцать": 20, "тридцать": 30, "сорок": 40, "пятьдесят": 50, "шестьдесят": 60,
            "семьдесят": 70, "восемьдесят": 80, "девяносто": 90}


def numbers_to_digits(text):
    """Vosk пишет числа словами («двадцать пять»), а команды громкости ждут цифры."""
    words = text.split()
    out = []
    i = 0
    while i < len(words):
        w = words[i]
        if w in _RU_TENS:
            val = _RU_TENS[w]
            if i + 1 < len(words) and _RU_UNITS.get(words[i + 1], 0) > 0:
                val += _RU_UNITS[words[i + 1]]
                i += 1
            out.append(str(val))
        elif w in _RU_TEENS:
            out.append(str(_RU_TEENS[w]))
        elif w == "сто":
            out.append("100")
        elif w in _RU_UNITS:
            out.append(str(_RU_UNITS[w]))
        else:
            out.append(w)
        i += 1
    return " ".join(out)



SEARCH_STRONG = ("поиск", "ищи", "найти", "найди", "поищи", "гуглить")
SEARCH_WEAK = ("гугл", "google")

# Движки распознавания. Можно включать любые сочетания, в том числе все сразу.
ENGINE_LANG = {"vosk_ru": "ru", "vosk_en": "en", "google_ru": "ru", "google_en": "en"}
ENGINE_GOOGLE_CODE = {"ru": "ru-RU", "en": "en-US"}

voice_lang = "ru"                     # язык ответа голосом: выбирается по включённым движкам

_audio_q = queue.Queue(maxsize=3)     # записанные фразы -> разбор по движкам
_cmd_q = queue.Queue()                # распознанная команда -> выполнение
_tts_q = queue.Queue(maxsize=4)       # фразы для голосового ответа

_vosk = None
_vosk_models = {}                     # "ru"/"en" -> модель
_vosk_state = {"ru": "idle", "en": "idle"}   # idle | loading | ready | missing | error
_vosk_lock = threading.Lock()

_utt_lock = threading.Lock()
_utt = {}                             # id фразы -> {"done", "left", "fallback"}
_utt_counter = [0]

# Слова, по которым фраза считается командой. Если фразы нет в списке, её не выполняем:
# так «Open Cloud», распознанное русским движком, не превращается в действие.
KNOWN_KEYWORDS = (
    "стоп", "выход", "привет", "здарова", "хай", "hello", "приветик", "салют", "джар", "джарвис",
    "звук", "громкость", "скрин", "снимок", "скриншот", "очисти", "удали мусор",
    "сверни", "показать рабочий стол", "проводник", "перезагрузи проводник", "перезапусти проводник",
    "папка", "файл", "браузер", "гугл", "google", "ютуб", "youtube", "видео", "video",
    "очистка", "чистка", "очистить", "рестарт", "перезагрузка", "перезагрузи", "reset", "ресет",
    "restart", "музыка", "песня", "камера", "вебкамера", "заблокируй", "блокировка",
    "заблокировать", "выключи", "отключи", "заверши работу", "перезапусти компьютер", "рестарт пк",
    "тим фортрес", "team fortress", "tf", "тф", "fortress", "кастом",
)


def _is_model_dir(path):
    return os.path.isdir(os.path.join(path, "am")) or os.path.isdir(os.path.join(path, "conf"))


def find_vosk_model(lang="ru"):
    """Ищет папку модели рядом с 11.py: vosk-model-...-ru-... или vosk-model-...-en-...
    Модель может лежать и во вложенной папке."""
    base = os.path.dirname(os.path.abspath(__file__))
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return None
    for name in names:
        path = os.path.join(base, name)
        lname = name.lower()
        if not os.path.isdir(path) or not lname.startswith("vosk-model"):
            continue
        if f"-{lang}" not in lname:
            continue
        if _is_model_dir(path):
            return path
        try:
            for sub in sorted(os.listdir(path)):
                inner = os.path.join(path, sub)
                if os.path.isdir(inner) and _is_model_dir(inner):
                    return inner
        except OSError:
            pass
    return None


def load_vosk(lang="ru"):
    """Грузит модель в фоне. Пока её нет, фразы для этого языка не распознаются."""
    global _vosk
    with _vosk_lock:
        if _vosk_state.get(lang) in ("loading", "ready"):
            return
        _vosk_state[lang] = "loading"

    try:
        import vosk
        vosk.SetLogLevel(-1)
    except Exception:
        log_error("❌ Vosk не установлен. Выполните: pip install vosk")
        _vosk_state[lang] = "error"
        return

    path = find_vosk_model(lang)
    if not path:
        log_error(f"❌ Модель Vosk ({lang}) не найдена. Распакуйте её рядом с 11.py")
        _vosk_state[lang] = "missing"
        return

    try:
        t0 = time.time()
        _vosk_models[lang] = vosk.Model(path)
        _vosk = vosk
        _vosk_state[lang] = "ready"
        log_info(f"✅ Vosk ({lang}) готов за {time.time() - t0:.1f} с: {os.path.basename(path)}")
    except Exception as e:
        log_error(f"❌ Не удалось загрузить модель Vosk ({lang}): {e}")
        _vosk_state[lang] = "error"


_vosk_recs = {}                       # язык -> распознаватель Vosk, создаётся один раз
_vosk_rec_locks = {"ru": threading.Lock(), "en": threading.Lock()}


def recognize_vosk(audio, lang):
    """Возвращает варианты распознавания (лучший первым) как список (текст, уверенность).
    Распознаватель создаётся один раз на язык: каждый новый KaldiRecognizer заново
    собирает граф, и на слабом компьютере это занимало около секунды на каждую фразу.
    FinalResult сбрасывает распознаватель для следующей фразы."""
    raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
    with _vosk_rec_locks[lang]:
        rec = _vosk_recs.get(lang)
        if rec is None:
            rec = _vosk.KaldiRecognizer(_vosk_models[lang], 16000)
            rec.SetMaxAlternatives(3)
            _vosk_recs[lang] = rec
        try:
            rec.AcceptWaveform(raw)
            res = json.loads(rec.FinalResult())
        except Exception:
            rec.Reset()
            raise
    if "alternatives" in res:
        out = []
        for a in res["alternatives"]:
            t = (a.get("text") or "").strip()
            if t:
                out.append((t, float(a.get("confidence", 0.0))))
        return out
    t = (res.get("text") or "").strip()
    return [(t, 0.0)] if t else []


def recognize_google_alts(audio, lang):
    """Варианты от Google (лучший первым). Без show_all Google отдаёт только один."""
    raw = sr.Recognizer().recognize_google(audio, language=ENGINE_GOOGLE_CODE[lang], show_all=True)
    if not isinstance(raw, dict):
        return []
    out = []
    for a in raw.get("alternative", []):
        t = (a.get("transcript") or "").strip()
        if t:
            out.append((t, float(a.get("confidence", 0.0))))
    return out


def _stamp(ts):
    """Время фразы: 14:03:21 или 14:03:21.456 (миллисекунды по настройке)."""
    t = datetime.fromtimestamp(ts)
    s = t.strftime("%H:%M:%S")
    if LOG_OPTS["ms"]:
        s += f".{t.microsecond // 1000:03d}"
    return s


def _slog(msg):
    """Строка распознавания: время выводит сама строка, поэтому без префикса консоли."""
    logger.info(msg, extra={"nostamp": True})


def _phrase_start_line(uid, info, engines, qsize):
    o = LOG_OPTS
    parts = []
    if o["time"]:
        parts.append(_stamp(info["t_start"]))
    parts.append(f"фраза #{uid}")
    if o["phrase"]:
        parts.append(f"{info['dur']:.2f} с")
    if o["volume"]:
        parts.append(f"громкость {info['db']:.0f} дБ")
    if o["engine"]:
        parts.append("движки: " + ", ".join(engines))
    if o["queue"]:
        parts.append(f"в очереди {qsize}")
    return " · ".join(parts)


def _engine_line(uid, info, engine, took_ms, shown, conf, status):
    o = LOG_OPTS
    parts = []
    if o["time"]:
        parts.append(_stamp(info["t_start"]))
    parts.append(f"#{uid}")
    if o["engine"]:
        parts.append(engine)
    parts.append(f"{took_ms} мс")
    if o["words"]:
        parts.append(f"«{shown}»" if shown else "(тишина)")
    if o["confidence"] and conf:
        parts.append(f"уверенность {conf:.2f}")
    if o["decision"]:
        parts.append(status)
    return " · ".join(parts)


def _decision_line(uid, info, found, engine):
    o = LOG_OPTS
    parts = []
    if o["time"]:
        parts.append(_stamp(info["t_start"]))
    parts.append(f"#{uid} ▶ выполняю «{found}»")
    if o["engine"]:
        parts.append(f"первым ответил {engine}")
    if o["lag"]:
        parts.append(f"после конца фразы {time.time() - info['t_end']:.2f} с")
    return " · ".join(parts)


def needs_google_for_search(text):
    """Поисковые запросы Vosk распознаёт плохо (любые слова), их уточняет Google."""
    words = strip_trigger(text.lower()).split()
    if not words:
        return False
    if words[0] in SEARCH_STRONG:
        return True
    return words[0] in SEARCH_WEAK and len(words) > 1


def is_known_command(text):
    """Похоже ли распознанное на команду Jarvis. Вызывается после перевода на русский."""
    t = text.lower()
    if any(w in t for w in TRIGGER_WORDS) and not strip_trigger(t):
        return True                                   # одно «Джарвис» — приветствие
    rest = strip_trigger(t)
    if not rest:
        return False
    if any(k in rest for k in KNOWN_KEYWORDS):
        return True
    if any(rest.startswith(k) for k in SEARCH_STRONG + SEARCH_WEAK):
        return True
    if any(w in rest for words in MY_SOUNDS.values() for w in words):
        return True
    if any(cmd in rest for cmd in user_commands):
        return True
    if apps.find_app(rest):
        return True
    return False


# ─── голосовой ответ ───────────────────────────────────────────

def speak(text):
    """Ставит фразу в очередь и сразу возвращается: команда ничего не ждёт."""
    if not voice_reply or not text:
        return
    if voice_lang == "en":
        text = i18n.EN_VOICE.get(text, text)
    try:
        _tts_q.put_nowait(text)
    except queue.Full:
        pass


def _pick_voice(engine, lang):
    prefixes = ("ru",) if lang == "ru" else ("en",)
    markers = ("ru-ru", "russian", "irina", "pavel") if lang == "ru" else ("en-us", "en-gb", "english", "zira", "david")
    for v in engine.getProperty("voices"):
        ident = f"{v.id} {v.name}".lower()
        if any(m in ident for m in markers):
            engine.setProperty("voice", v.id)
            return True
    return False


def tts_worker():
    try:
        try:
            import comtypes
            comtypes.CoInitialize()
        except Exception:
            pass
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", 190)
    except Exception as e:
        log_error(f"🔇 Голосовой ответ недоступен (pip install pyttsx3): {e}")
        return

    current = None
    while is_running:
        try:
            text = _tts_q.get(timeout=0.5)
        except queue.Empty:
            continue
        if current != voice_lang:
            current = voice_lang
            if not _pick_voice(engine, current):
                log_error(f"🔇 Нет голоса Windows для языка «{current}». Установите языковой пакет")
                continue
        try:
            engine.say(text)
            engine.runAndWait()
        except Exception as e:
            log_error(f"🔇 Ошибка озвучивания: {e}")


# ─── запись ────────────────────────────────────────────────────

def _phrase_info(audio, t_end):
    """Время и громкость фразы. Начало считаем как конец минус длительность записи."""
    dur, db = 0.0, -120.0
    try:
        dur = len(audio.frame_data) / (audio.sample_rate * audio.sample_width)
        if audio.sample_width == 2:
            samples = np.frombuffer(audio.frame_data, dtype=np.int16).astype(np.float32)
            if samples.size:
                rms = float(np.sqrt(np.mean(samples * samples)))
                if rms > 0:
                    db = 20 * math.log10(rms / 32768)
    except Exception:
        pass
    return {"t_end": t_end, "t_start": t_end - dur, "dur": dur, "db": db, "id": 0}


def _listen_session(sample_rate):
    """Один сеанс записи. Только слушает и кладёт фразы в очередь вместе с временем."""
    r = sr.Recognizer()
    r.dynamic_energy_threshold = True
    r.non_speaking_duration = 0.3
    r.phrase_threshold = 0.2

    with sr.Microphone(device_index=mic_index, sample_rate=sample_rate) as source:
        r.adjust_for_ambient_noise(source, duration=0.5)
        log_info(f"🎤 Слушаю... (rate={source.SAMPLE_RATE})")

        while is_running and not mic_reload:
            r.pause_threshold = 0.7      # пауза до конца фразы: меньше = режет слова на половине
            try:
                audio = r.listen(source, timeout=1, phrase_time_limit=10)
            except sr.WaitTimeoutError:
                continue

            item = (audio, _phrase_info(audio, time.time()))
            try:
                _audio_q.put_nowait(item)
            except queue.Full:
                try:
                    _audio_q.get_nowait()       # выбрасываем самую старую
                except queue.Empty:
                    pass
                log_info("⚠️ Очередь распознавания полная: самая старая фраза пропущена")
                _audio_q.put_nowait(item)


def audio_listener_loop():
    global mic_reload
    rates = [16000, None]   # 16 кГц = меньше данных; None = родная частота
    idx = 0
    while is_running:
        mic_reload = False
        try:
            _listen_session(rates[idx])
        except Exception as e:
            log_error(f"❌ Ошибка микрофона: {e}")
            if idx < len(rates) - 1:
                idx += 1
            time.sleep(1)


# ─── распознавание: все выбранные движки одновременно ───────────

def _finish_engine(uid, engine, alts, info, took_ms):
    """Учитывает ответ одного движка. Проверяются все варианты, и первая известная команда
    уходит в выполнение. Английская фраза принимается только если целиком похожа на команду."""
    global heard_text, heard_time
    lang = ENGINE_LANG[engine]
    shown = alts[0][0] if alts else ""
    conf = alts[0][1] if alts else 0.0
    found = None
    for text, _ in alts:
        ru = i18n.translate_command(text)
        if is_known_command(ru) and (lang == "ru" or i18n.english_command_matches(text)):
            found = ru
            break

    with _utt_lock:
        st = _utt.get(uid)
        if st is None:
            return
        st["left"] -= 1
        was_done = st["done"]
        if found and not was_done:
            st["done"] = True
            _cmd_q.put(found)
            status = "команда"
        elif found:
            status = "команда, но опоздала: уже выполнено"
        elif not shown:
            status = "пусто"
        else:
            status = "не команда"
        if shown and lang == "ru" and not st["fallback"]:
            st["fallback"] = shown
        note = ""
        if st["left"] <= 0:
            if not st["done"] and st["fallback"]:
                st["done"] = True
                _cmd_q.put(st["fallback"])      # неизвестная фраза: статус «ошибка»
                note = " (неизвестная фраза, статус «ошибка»)"
            _utt.pop(uid, None)

    if shown:
        heard_text = shown
        heard_time = time.time()
    _slog(_engine_line(uid, info, engine, took_ms, shown, conf, status + note))
    if found and not was_done and LOG_OPTS["decision"]:
        _slog(_decision_line(uid, info, found, engine))


def _run_engine(engine, uid, audio, info):
    lang = ENGINE_LANG[engine]
    alts = []
    t0 = time.time()
    try:
        if engine.startswith("vosk"):
            if _vosk_state.get(lang) != "ready":
                load_vosk(lang)
            if _vosk_state.get(lang) == "ready":
                alts = recognize_vosk(audio, lang)
                if lang == "ru":
                    alts = [(numbers_to_digits(t) if ("звук" in t or "громкость" in t) else t, c)
                            for t, c in alts]
                    if alts and needs_google_for_search(alts[0][0]) and "google_ru" not in recognition_engines:
                        try:
                            alts = [(sr.Recognizer().recognize_google(audio, language="ru-RU"), 0.0)]
                        except Exception:
                            pass            # оставляем варианты Vosk
        else:
            alts = recognize_google_alts(audio, lang)
    except sr.UnknownValueError:
        alts = []
    except sr.RequestError as e:
        log_error(f"🌐 Ошибка сети ({engine}): {e}")
    except Exception as e:
        log_error(f"⚠️ Ошибка распознавания ({engine}): {e}")
    _finish_engine(uid, engine, alts, info, int((time.time() - t0) * 1000))


def recognition_worker():
    """Берёт фразу из очереди и запускает все включённые движки параллельно.
    Не ждёт их: следующая фраза обрабатывается сразу."""
    while is_running:
        try:
            audio, info = _audio_q.get(timeout=0.5)
        except queue.Empty:
            continue

        engines = [e for e in ENGINES if e in recognition_engines]
        if not engines:
            continue
        with _utt_lock:
            _utt_counter[0] += 1
            uid = _utt_counter[0]
            _utt[uid] = {"done": False, "left": len(engines), "fallback": "", "cmd": None}
        info["id"] = uid
        _slog(_phrase_start_line(uid, info, engines, _audio_q.qsize()))
        for e in engines:
            threading.Thread(target=_run_engine, args=(e, uid, audio, info), daemon=True).start()


def command_worker():
    """Выполняет команды отдельно, чтобы долгие действия не тормозили распознавание."""
    while is_running:
        try:
            text = _cmd_q.get(timeout=0.5)
        except queue.Empty:
            continue
        try:
            execute_command(text)
        except Exception as e:
            log_error(f"⚠️ Ошибка команды: {e}")


def set_recognition_engines(engines):
    """Меняет набор движков на ходу. Модели Vosk грузятся в фоне при первом включении."""
    global recognition_engines, voice_lang
    recognition_engines = [e for e in ENGINES if e in engines] or list(DEFAULT_ENGINES)
    langs = {ENGINE_LANG[e] for e in recognition_engines}
    voice_lang = "en" if langs == {"en"} else "ru"
    for e in recognition_engines:
        if e.startswith("vosk"):
            threading.Thread(target=load_vosk, args=(ENGINE_LANG[e],), daemon=True).start()


def start_voice_threads():
    set_recognition_engines(recognition_engines)
    for target in (audio_listener_loop, recognition_worker, command_worker, tts_worker):
        threading.Thread(target=target, daemon=True).start()


# ═══════════════════════════════════════════════════════════════
# 11. ВИЗУАЛИЗАЦИЯ
# ═══════════════════════════════════════════════════════════════

class ReactorWidget(QWidget):
    """Минималистичная визуализация: тонкое кольцо, которое дышит и реагирует на голос."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(200, 200)
        self.quality = QUALITY_MODE
        self.time = 0.0
        self.level = 0.0
        self.color = list(STATE_COLORS["idle"])
        self.background = None
        self._bg_cache = None
        self._bg_cache_size = None

    def update_quality(self, quality):
        self.quality = quality
        self.update()

    def set_background(self, path):
        """Фон теперь рисует BackdropWidget под виджетом. Здесь ничего не делаем."""
        return

    def tick(self, voice, status):
        self.time += 0.033
        self.level += (min(1.0, voice) - self.level) * 0.35
        target = STATE_COLORS.get(status, STATE_COLORS["idle"])
        for i in range(3):
            self.color[i] += (target[i] - self.color[i]) * 0.12
        self.update()

    def _cover(self, w, h):
        if self._bg_cache is None or self._bg_cache_size != (w, h):
            self._bg_cache = self.background.scaled(
                w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            self._bg_cache_size = (w, h)
        return self._bg_cache

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        if self.background:
            bg = self._cover(w, h)
            p.drawPixmap((w - bg.width()) // 2, (h - bg.height()) // 2, bg)
            p.fillRect(0, 0, w, h, QColor(14, 14, 15, 175))

        cx, cy = w / 2, h / 2
        R = min(w, h) / 2
        base = QColor(int(self.color[0]), int(self.color[1]), int(self.color[2]))
        lvl = self.level

        r0 = R * (0.30 + 0.012 * math.sin(self.time * 1.3)) + lvl * R * 0.10
        center = QPointF(cx, cy)

        # внешние тонкие кольца (их число задаёт настройка «Детализация»)
        rings = (self.quality + 1) // 2
        p.setBrush(Qt.NoBrush)
        for k in range(rings, 0, -1):
            rk = r0 + k * R * 0.10 + lvl * R * 0.04 * k
            c = QColor(base)
            c.setAlpha(min(255, int(70 / k + lvl * 40)))
            p.setPen(QPen(c, 1))
            p.drawEllipse(center, rk, rk)

        # лёгкая заливка
        fill = QColor(base)
        fill.setAlpha(int(10 + lvl * 30))
        p.setPen(Qt.NoPen)
        p.setBrush(fill)
        p.drawEllipse(center, r0, r0)

        # основное кольцо
        ring = QColor(base)
        ring.setAlpha(235)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(ring, 1.6))
        p.drawEllipse(center, r0, r0)

        # тонкие волны по бокам: растут от голоса
        for side in (-1, 1):
            for layer, (amp_k, alpha) in enumerate(((1.0, 120), (0.6, 60))):
                path = QPainterPath()
                x0 = cx + side * (r0 + R * 0.18)
                x1 = cx + side * (w / 2 - 6)
                n = 48
                for i in range(n + 1):
                    t = i / n
                    x = x0 + (x1 - x0) * t
                    envelope = math.sin(math.pi * t) ** 1.5
                    amp = (2 + lvl * R * 0.32) * amp_k * envelope
                    y = cy + math.sin(t * 9 + self.time * 3 + layer * 1.3) * amp
                    if i == 0:
                        path.moveTo(x, y)
                    else:
                        path.lineTo(x, y)
                c = QColor(base)
                c.setAlpha(alpha)
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(c, 1))
                p.drawPath(path)

        # точка в центре
        dot = QColor(base)
        dot.setAlpha(255)
        p.setPen(Qt.NoPen)
        p.setBrush(dot)
        dr = 3 + lvl * 3
        p.drawEllipse(center, dr, dr)


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_win = parent
        self.selected_path = ""

        self.setWindowTitle(tr("Настройки"))
        self.setFixedSize(580, 760)

        self.setStyleSheet("""
            QDialog { background: #0e0e0f; }
            QLabel { color: #d0d0d0; font-size: 13px; }
            QTabWidget::pane { border: none; border-top: 1px solid #202022; padding-top: 10px; }
            QTabBar::tab {
                background: transparent; color: #6b6b70;
                padding: 8px 12px; margin-right: 2px;
                border: none; border-bottom: 1px solid transparent; font-size: 12px;
            }
            QTabBar::tab:selected { color: #f0f0f0; border-bottom: 1px solid #f0f0f0; }
            QTabBar::tab:hover { color: #d0d0d0; }
            QGroupBox {
                border: none; margin-top: 16px; padding-top: 8px;
                color: #6b6b70; font-size: 11px; background: transparent;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 0px; color: #6b6b70; }
            QComboBox, QLineEdit {
                background-color: #161617; color: #e8e8e8;
                border: 1px solid #232325; border-radius: 6px;
                padding: 7px 10px; font-size: 12px;
            }
            QComboBox:hover, QLineEdit:hover, QLineEdit:focus { border: 1px solid #4a4a4e; }
            QComboBox::drop-down { border: none; width: 22px; }
            QComboBox QAbstractItemView {
                background: #161617; color: #e8e8e8;
                border: 1px solid #232325; selection-background-color: #232325;
            }
            QListWidget {
                background-color: #161617; color: #e8e8e8;
                border: 1px solid #232325; border-radius: 6px; padding: 4px;
            }
            QListWidget::item { padding: 4px; }
            QListWidget::item:selected { background-color: #232325; color: #ffffff; }
            QPushButton {
                background: transparent; color: #d0d0d0; font-size: 12px;
                border: 1px solid #2a2a2c; padding: 7px 16px; border-radius: 6px;
            }
            QPushButton:hover { color: #ffffff; border: 1px solid #6b6b70; }
            QCheckBox { color: #e8e8e8; font-size: 12px; spacing: 10px; }
            QCheckBox::indicator {
                width: 16px; height: 16px; border-radius: 4px;
                border: 1px solid #3a3a3d; background-color: #161617;
            }
            QCheckBox::indicator:checked { background-color: #e8e8e8; border: 1px solid #e8e8e8; }
            QSlider::groove:horizontal { height: 2px; background: #2a2a2c; }
            QSlider::sub-page:horizontal { background: #e8e8e8; }
            QSlider::handle:horizontal {
                background: #e8e8e8; width: 12px; height: 12px;
                margin: -5px 0; border-radius: 6px;
            }
            QScrollBar:vertical { background: transparent; width: 8px; }
            QScrollBar::handle:vertical { background: #2a2a2c; border-radius: 4px; min-height: 30px; }
            QScrollBar::handle:vertical:hover { background: #3a3a3d; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { border: none; background: none; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(25, 20, 25, 20)

        title = QLabel(tr("Настройки"))
        title.setStyleSheet("color: #e8e8e8; font-size: 16px; letter-spacing: 1px;")
        main_layout.addWidget(title)

        tabs = QTabWidget()
        tabs.addTab(self._tab_interface(), tr("Интерфейс"))
        tabs.addTab(self._tab_commands(), tr("Команды"))
        tabs.addTab(self._tab_voice(), tr("Звук и голос"))
        tabs.addTab(self._tab_gestures(), tr("Жесты"))
        tabs.addTab(self._tab_system(), tr("Система"))
        tabs.addTab(self._tab_logs(), tr("Логи"))
        tabs.addTab(self._tab_info(), tr("Инфо"))
        main_layout.addWidget(tabs)

        bottom = QHBoxLayout()
        btn_close = QPushButton(tr("Закрыть"))
        btn_close.clicked.connect(self.close)
        btn_apply = QPushButton(tr("Применить"))
        btn_apply.clicked.connect(self.apply_settings)
        bottom.addStretch()
        bottom.addWidget(btn_close)
        bottom.addWidget(btn_apply)
        main_layout.addLayout(bottom)

        self.load_commands()
        self.refresh_backgrounds()

    # ── вкладки ─────────────────────────────────────────────────
    def _tab_interface(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)

        lang_group = QGroupBox(tr("Язык интерфейса"))
        lang_layout = QVBoxLayout(lang_group)
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("Русский", "ru")
        self.lang_combo.addItem("English", "en")
        self.lang_combo.setCurrentIndex(1 if language == "en" else 0)
        lang_layout.addWidget(self.lang_combo)
        hint = QLabel(tr("Язык меняется после перезапуска Jarvis."))
        hint.setStyleSheet("color: #6b6b70; font-size: 11px;")
        lang_layout.addWidget(hint)
        lay.addWidget(lang_group)

        bg_group = QGroupBox(tr("Фон"))
        bg_layout = QVBoxLayout(bg_group)
        btn_change = QPushButton(tr("Сменить фон"))
        btn_change.setCursor(Qt.PointingHandCursor)
        btn_change.setMinimumHeight(40)
        btn_change.setStyleSheet("""
            QPushButton { border: 1px solid #e8e8e8; color: #f0f0f0; font-size: 13px; border-radius: 8px; }
            QPushButton:hover { background: #1c1c1e; }
        """)
        btn_change.clicked.connect(self.change_background)
        bg_layout.addWidget(btn_change)

        self.bg_list = QListWidget()
        self.bg_list.setMinimumHeight(140)
        bg_layout.addWidget(self.bg_list)

        row = QHBoxLayout()
        btn_apply_bg = QPushButton(tr("Применить"))
        btn_apply_bg.clicked.connect(self.apply_saved_background)
        btn_del_bg = QPushButton(tr("Удалить"))
        btn_del_bg.clicked.connect(self.delete_saved_background)
        row.addWidget(btn_apply_bg)
        row.addWidget(btn_del_bg)
        row.addStretch()
        bg_layout.addLayout(row)
        lay.addWidget(bg_group)

        self.fullscreen_check = QCheckBox(tr("Полноэкранный режим (F11)"))
        self.fullscreen_check.setChecked(fullscreen_mode)
        lay.addWidget(self.fullscreen_check)
        lay.addStretch()
        return tab

    def _tab_commands(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        commands_group = QGroupBox(tr("Пользовательские команды"))
        commands_layout = QVBoxLayout(commands_group)

        self.command_list = QListWidget()
        self.command_list.setMinimumHeight(100)
        commands_layout.addWidget(self.command_list)

        input_row = QHBoxLayout()
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText(tr("Команда..."))
        input_row.addWidget(self.command_input, 1)
        commands_layout.addLayout(input_row)

        type_row = QHBoxLayout()
        type_row.addWidget(QLabel(tr("Тип команды")))
        self.cmd_type_combo = QComboBox()
        self.cmd_type_combo.addItem(tr("Файл или программа"), "file")
        self.cmd_type_combo.addItem(tr("Папка"), "folder")
        self.cmd_type_combo.addItem(tr("Сайт"), "url")
        type_row.addWidget(self.cmd_type_combo, 1)
        commands_layout.addLayout(type_row)

        button_row = QHBoxLayout()
        self.btn_browse = QPushButton(tr("Файл"))
        self.btn_browse.setToolTip(tr("Выбрать файл"))
        self.btn_browse.clicked.connect(self.browse_file)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText(tr("Адрес сайта") + " (https://...)")
        self.url_input.setVisible(False)
        self.path_label = QLabel(tr("не выбрано"))
        self.path_label.setStyleSheet("color: #6b6b70; font-size: 11px;")
        button_row.addWidget(self.btn_browse)
        button_row.addWidget(self.url_input, 1)
        button_row.addWidget(self.path_label, 1)
        commands_layout.addLayout(button_row)
        self.cmd_type_combo.currentIndexChanged.connect(self.on_cmd_type_changed)

        action_row = QHBoxLayout()
        btn_add = QPushButton(tr("Добавить"))
        btn_add.clicked.connect(self.add_command)
        btn_del = QPushButton(tr("Удалить"))
        btn_del.clicked.connect(self.delete_command)
        btn_clear = QPushButton(tr("Очистить"))
        btn_clear.clicked.connect(self.clear_commands)
        btn_refresh = QPushButton(tr("Обновить"))
        btn_refresh.clicked.connect(self.load_commands)
        for b in (btn_add, btn_del, btn_clear, btn_refresh):
            action_row.addWidget(b)
        action_row.addStretch()
        commands_layout.addLayout(action_row)

        self.command_counter = QLabel()
        self.command_counter.setStyleSheet("color: #6b6b70; font-size: 10px;")
        commands_layout.addWidget(self.command_counter)

        lay.addWidget(commands_group)
        lay.addStretch()
        return tab

    def _tab_voice(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)

        music_group = QGroupBox(tr("Музыка"))
        music_layout = QVBoxLayout(music_group)
        music_row = QHBoxLayout()
        btn_music = QPushButton(tr("Выбрать"))
        btn_music.clicked.connect(self.select_music_folder)
        self.music_path_label = QLabel(music_folder if music_folder else tr("Папка не выбрана"))
        self.music_path_label.setStyleSheet("color: #6b6b70; font-size: 11px;")
        music_row.addWidget(btn_music)
        music_row.addWidget(self.music_path_label, 1)
        music_layout.addLayout(music_row)
        self.greeting_check = QCheckBox(tr("Включить приветствие"))
        self.greeting_check.setChecked(greeting_mode)
        music_layout.addWidget(self.greeting_check)
        lay.addWidget(music_group)

        mic_group = QGroupBox(tr("Микрофон"))
        mic_layout = QVBoxLayout(mic_group)
        self.mic_combo = QComboBox()
        self.mic_combo.addItem(tr("Системный (по умолчанию)"), None)
        try:
            for i, name in enumerate(sr.Microphone.list_microphone_names()):
                self.mic_combo.addItem(f"{name[:40]}", i)
        except Exception:
            pass
        for i in range(self.mic_combo.count()):
            if self.mic_combo.itemData(i) == mic_index:
                self.mic_combo.setCurrentIndex(i)
        mic_layout.addWidget(self.mic_combo)
        lay.addWidget(mic_group)

        rec_group = QGroupBox(tr("Распознавание речи"))
        rec_layout = QVBoxLayout(rec_group)
        self.engine_checks = {}
        engine_titles = {
            "vosk_ru": tr("Vosk, русский (офлайн, быстро)"),
            "vosk_en": tr("Vosk, English (offline, fast)"),
            "google_ru": tr("Google, русский (онлайн)"),
            "google_en": tr("Google, English (online)"),
        }
        for key in ENGINES:
            cb = QCheckBox(engine_titles[key])
            cb.setChecked(key in recognition_engines)
            cb.toggled.connect(self.update_engine_status)
            self.engine_checks[key] = cb
            rec_layout.addWidget(cb)
        self.engine_status = QLabel()
        self.engine_status.setWordWrap(True)
        self.engine_status.setStyleSheet("color: #6b6b70; font-size: 11px;")
        rec_layout.addWidget(self.engine_status)
        self.voice_reply_check = QCheckBox(tr("Голосовой ответ после действия"))
        self.voice_reply_check.setChecked(voice_reply)
        rec_layout.addWidget(self.voice_reply_check)
        lay.addWidget(rec_group)
        self.update_engine_status()
        lay.addStretch()
        return tab

    def _tab_gestures(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        group = QGroupBox(tr("Жесты рукой (камера)"))
        glay = QVBoxLayout(group)
        self.gestures_check = QCheckBox(tr("Распознавание жестов (камера)"))
        self.gestures_check.setChecked(gestures_enabled)
        glay.addWidget(self.gestures_check)
        self.gesture_status = QLabel()
        self.gesture_status.setWordWrap(True)
        self.gesture_status.setStyleSheet("color: #6b6b70; font-size: 11px;")
        glay.addWidget(self.gesture_status)
        self.gesture_status.setText(self.main_win.gesture_status_text() if self.main_win else "")
        lay.addWidget(group)

        howto = QLabel(
            tr("Как пользоваться:") + "\n\n"
            + tr("1. Покажите открытую ладонь. Светодиод станет зелёным.") + "\n"
            + tr("2. Нарисуйте указательным пальцем букву М в воздухе.") + "\n"
            + tr("3. Откроется браузер.") + "\n\n"
            + tr("Если жест не пришёл за 5 секунд, светодиод снова станет красным.")
        )
        howto.setWordWrap(True)
        howto.setStyleSheet("color: #8a8a8f; font-size: 12px; line-height: 1.6;")
        lay.addWidget(howto)
        lay.addStretch()
        return tab

    def _tab_system(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        system_group = QGroupBox(tr("Система"))
        system_layout = QVBoxLayout(system_group)

        restart_row = QHBoxLayout()
        restart_row.addWidget(QLabel(tr("Перезагрузить всё (микрофон, звук, аудио)")))
        restart_row.addStretch()
        btn_restart = QPushButton(tr("Перезагрузить"))
        btn_restart.clicked.connect(self.restart_jarvis)
        btn_restart.setFixedHeight(32)
        restart_row.addWidget(btn_restart)
        system_layout.addLayout(restart_row)
        self.restart_status = QLabel(tr("Готов к работе"))
        self.restart_status.setStyleSheet("color: #7ddc9a; font-size: 10px;")
        system_layout.addWidget(self.restart_status)

        clean_row = QHBoxLayout()
        clean_row.addWidget(QLabel(tr("Очистка кэша и временных файлов")))
        clean_row.addStretch()
        btn_clean = QPushButton(tr("Запустить"))
        btn_clean.clicked.connect(self.run_cleanup)
        btn_clean.setFixedHeight(28)
        clean_row.addWidget(btn_clean)
        system_layout.addLayout(clean_row)
        self.clean_status = QLabel(tr("Готов к очистке"))
        self.clean_status.setStyleSheet("color: #7ddc9a; font-size: 10px;")
        system_layout.addWidget(self.clean_status)

        lay.addWidget(system_group)
        lay.addStretch()
        return tab

    def _tab_logs(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        head = QLabel(tr("Что показывать в консоли при распознавании. Файл в папке logs пишется полностью."))
        head.setWordWrap(True)
        lay.addWidget(head)
        self.log_checks = {}
        for key, label in LOG_OPTION_LABELS:
            cb = QCheckBox(tr(label))
            cb.setChecked(LOG_OPTS.get(key, False))
            self.log_checks[key] = cb
            lay.addWidget(cb)
        btn_open = QPushButton(tr("Открыть папку логов"))
        btn_open.clicked.connect(self.open_logs_folder)
        lay.addWidget(btn_open, 0, Qt.AlignLeft)
        lay.addStretch()
        return tab

    def open_logs_folder(self):
        try:
            os.startfile(os.path.abspath("logs"))
        except Exception as e:
            log_error(f"Не удалось открыть папку логов: {e}")

    def _tab_info(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        info_group = QGroupBox(tr("Информация"))
        info_layout = QVBoxLayout(info_group)

        cmds = ALL_COMMANDS_EN if language == "en" else ALL_COMMANDS
        titles_map = i18n.ALL_COMMANDS_TITLES_EN if language == "en" else {}
        lines = []
        for category, commands in cmds.items():
            title = titles_map.get(re.sub(r'^[^\w]+', '', category).strip(), category) if titles_map \
                else category
            lines.append(f"\n{title}:")
            lines += [f"  • {c}" for c in commands]

        info_text = QLabel(
            f"Jarvis AZ {VERSION}\n"
            + tr("Голосовой ассистент с визуализацией") + "\n\n"
            + "\n".join(lines)
            + "\n"
            + "\nСБЕР: 2202208528973606"
            + "\nGitHub: https://github.com/data-az"
            + "\nTelegram: https://t.me/Durov_0ffical"
            + "\nVibe: https://vibe.widemade.com/u/aza"
            + f"\n\nWindows {WIN_VER[0]}.{WIN_VER[1]}, Qt: {QT_API}"
        )
        info_text.setStyleSheet("color: #8a8a8f; font-size: 11px;")
        info_text.setWordWrap(True)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        scroll.setWidget(info_text)
        info_layout.addWidget(scroll)
        lay.addWidget(info_group)
        return tab

    # ── фон ─────────────────────────────────────────────────────
    def refresh_backgrounds(self):
        self.bg_list.clear()
        for cfg in saved_backgrounds:
            mode = {"full": tr("на весь экран"), "except_menu": tr("кроме меню"),
                    "none": tr("без фона")}.get(cfg.get("mode"), "")
            self.bg_list.addItem(f"{cfg.get('name') or tr('Без названия')}  ·  {mode}")

    def change_background(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("Выберите картинку"), "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if not path or not self.main_win:
            return
        rel = copy_background_file(path)
        if not rel:
            QMessageBox.warning(self, tr("Ошибка"), tr("Не удалось скопировать картинку."))
            return
        self.close()
        self.main_win.start_background_edit(rel)

    def apply_saved_background(self):
        row = self.bg_list.currentRow()
        if row < 0 or row >= len(saved_backgrounds):
            return
        set_current_background(saved_backgrounds[row])
        if self.main_win:
            self.main_win.apply_background()
        self.close()

    def delete_saved_background(self):
        row = self.bg_list.currentRow()
        if row < 0 or row >= len(saved_backgrounds):
            return
        cfg = saved_backgrounds.pop(row)
        remove_background_file_if_unused(cfg.get("image", ""))
        save_settings()
        self.refresh_backgrounds()

    # ── обработчики ─────────────────────────────────────────────
    def update_engine_status(self):
        chosen = [k for k, cb in self.engine_checks.items() if cb.isChecked()]
        if not chosen:
            self.engine_status.setText(tr("Выберите хотя бы один движок. Пока выбора нет, будет Vosk, русский."))
            return
        missing = []
        for k in chosen:
            if k.startswith("vosk"):
                lang = ENGINE_LANG[k]
                if importlib.util.find_spec("vosk") is None:
                    missing.append(tr("установите vosk: pip install vosk"))
                    break
                if not find_vosk_model(lang):
                    missing.append(tr("нет модели {lang}: распакуйте её рядом с 11.py").format(lang=lang))
        if missing:
            self.engine_status.setText(tr("Внимание: ") + "; ".join(missing) + ". " + tr("Пока эти движки не работают."))
        else:
            self.engine_status.setText(tr("Все фразы идут параллельно. Выполняется первая распознанная команда."))

    def select_music_folder(self):
        global music_folder
        folder = QFileDialog.getExistingDirectory(self, tr("Выберите папку с музыкой"))
        if folder:
            music_folder = folder
            self.music_path_label.setText(folder)
            save_settings()

    def restart_jarvis(self):
        self.restart_status.setText(tr("Перезагрузка..."))
        self.restart_status.setStyleSheet("color: #d6c28a;")
        QApplication.processEvents()

        if restart_jarvis():
            self.restart_status.setText(tr("Перезагрузка выполнена!"))
            self.restart_status.setStyleSheet("color: #7ddc9a;")
            audio_output.play_trigger("привет")
        else:
            self.restart_status.setText(tr("Ошибка перезагрузки"))
            self.restart_status.setStyleSheet("color: #e57373;")

    def run_cleanup(self):
        self.clean_status.setText("⏳ " + tr("Очистка..."))
        self.clean_status.setStyleSheet("color: #d6c28a;")
        QApplication.processEvents()

        count, mb = clean_system()
        self.clean_status.setText(f"{tr('Удалено')} {count} ({mb:.2f} MB)")
        self.clean_status.setStyleSheet("color: #7ddc9a;")
        audio_output.play_trigger("очистка")

    def browse_file(self):
        if self.cmd_type_combo.currentData() == "folder":
            path = QFileDialog.getExistingDirectory(self, tr("Выберите папку"), "")
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, tr("Выберите файл или программу"), "",
                "Все файлы (*.*);;Исполняемые файлы (*.exe);;Ярлыки (*.lnk;*.url);;Скрипты (*.py;*.bat;*.cmd)"
            )
        if path:
            self.selected_path = path
            self.path_label.setText(os.path.basename(os.path.normpath(path)) or path)
            self.path_label.setToolTip(path)

    def on_cmd_type_changed(self, *_):
        kind = self.cmd_type_combo.currentData()
        is_url = kind == "url"
        self.url_input.setVisible(is_url)
        self.btn_browse.setVisible(not is_url)
        self.path_label.setVisible(not is_url)
        self.btn_browse.setText(tr("Папка") if kind == "folder" else tr("Файл"))
        self.selected_path = ""
        self.path_label.setText(tr("не выбрано"))

    def add_command(self):
        cmd = self.command_input.text().strip().lower()
        kind = self.cmd_type_combo.currentData()

        if not cmd:
            QMessageBox.warning(self, tr("Ошибка"), tr("Введите команду!"))
            return

        if kind == "url":
            target = self.url_input.text().strip()
            if not target:
                QMessageBox.warning(self, tr("Ошибка"), tr("Введите адрес сайта!"))
                return
            if not target.lower().startswith(("http://", "https://")):
                target = "https://" + target
            item = {"type": "url", "target": target}
        else:
            target = getattr(self, 'selected_path', '')
            if not target or not os.path.exists(target):
                key = "Выберите папку для команды!" if kind == "folder" else "Выберите файл для команды!"
                QMessageBox.warning(self, tr("Ошибка"), tr(key))
                return
            item = {"type": kind, "target": target}

        if cmd in user_commands:
            reply = QMessageBox.question(
                self, tr("Команда существует"),
                f"{tr('Команда')} '{cmd}' {tr('уже существует.')}\n{tr('Заменить?')}",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                return

        user_commands[cmd] = item
        self.load_commands()
        self.command_input.clear()
        self.url_input.clear()
        self.selected_path = ""
        self.path_label.setText(tr("не выбрано"))
        save_commands()
        audio_output.play_trigger("команда добавлена")

    def delete_command(self):
        current = self.command_list.currentRow()
        if current < 0:
            QMessageBox.warning(self, tr("Ошибка"), tr("Выберите команду для удаления!"))
            return

        item = self.command_list.item(current)
        text = item.text()
        cmd = text.split(" → ")[0].strip()

        if cmd in user_commands:
            del user_commands[cmd]
            self.load_commands()
            save_commands()

    def clear_commands(self):
        if not user_commands:
            return

        reply = QMessageBox.question(
            self, tr("Очистка всех команд"),
            tr("Удалить ВСЕ пользовательские команды?"),
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            user_commands.clear()
            self.load_commands()
            save_commands()

    def load_commands(self):
        self.command_list.clear()
        for cmd, item in user_commands.items():
            self.command_list.addItem(f"{cmd} → {_command_label(item)}")
        self.command_counter.setText(f"{tr('Всего')}: {len(user_commands)}")

    def apply_settings(self):
        global fullscreen_mode, greeting_mode, music_folder, mic_index, mic_reload
        global voice_reply, language, gestures_enabled

        new_lang = self.lang_combo.currentData()
        lang_changed = new_lang != language
        language = new_lang
        i18n.set_language(language)

        chosen = [k for k, cb in self.engine_checks.items() if cb.isChecked()]
        set_recognition_engines(chosen or list(DEFAULT_ENGINES))

        voice_reply = self.voice_reply_check.isChecked()
        greeting_mode = self.greeting_check.isChecked()
        new_mic = self.mic_combo.currentData()
        if new_mic != mic_index:
            mic_index = new_mic
            mic_reload = True

        fullscreen_mode = self.fullscreen_check.isChecked()
        gestures_enabled = self.gestures_check.isChecked()
        for key, cb in self.log_checks.items():
            LOG_OPTS[key] = cb.isChecked()
        save_settings()

        if self.main_win:
            self.main_win.set_gestures_enabled(gestures_enabled)
            if fullscreen_mode:
                self.main_win.go_fullscreen()
            else:
                self.main_win.go_windowed()

        if lang_changed:
            QMessageBox.information(self, tr("Язык"),
                                    "Язык изменится после перезапуска Jarvis.\nLanguage changes after restart.")
        self.close()


# ═══════════════════════════════════════════════════════════════
# 14. ГЛАВНОЕ ОКНО
# ═══════════════════════════════════════════════════════════════

class BarRow(QWidget):
    """Строка «название — значение» с тонкой полосой под ней."""

    def __init__(self, label, suffix="%", big=False, parent=None):
        super().__init__(parent)
        self.label = label
        self.suffix = suffix
        self.big = big
        self.value = 0
        self.text = "—"
        self.setFixedHeight(46 if big else 32)

    def set_value(self, value, text=None):
        value = max(0, min(100, int(value)))
        text = text if text is not None else f"{value}{self.suffix}"
        if value != self.value or text != self.text:
            self.value = value
            self.text = text
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        font = QFont("Segoe UI")
        font.setPixelSize(14 if self.big else 12)
        p.setFont(font)

        p.setPen(QColor(UI["dim"]))
        p.drawText(0, 0, w, h - 10, Qt.AlignLeft | Qt.AlignVCenter, self.label)
        p.setPen(QColor(UI["text"]))
        p.drawText(0, 0, w, h - 10, Qt.AlignRight | Qt.AlignVCenter, self.text)

        y = h - 5
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#232325"))
        p.drawRoundedRect(0, y, w, 2, 1, 1)
        p.setBrush(QColor(UI["text"]))
        p.drawRoundedRect(0, y, int(w * self.value / 100), 2, 1, 1)


# ═══════════════════════════════════════════════════════════════
# 14a. ФОН И ЕГО ХРАНЕНИЕ
# ═══════════════════════════════════════════════════════════════

BACKGROUNDS_FOLDER = os.path.join(SCRIPT_FOLDER, "backgrounds")


def copy_background_file(src):
    """Копирует картинку в папку программы. Возвращает относительный путь или None."""
    try:
        os.makedirs(BACKGROUNDS_FOLDER, exist_ok=True)
        base = os.path.basename(src)
        name, ext = os.path.splitext(base)
        dest_name = base
        n = 1
        while os.path.exists(os.path.join(BACKGROUNDS_FOLDER, dest_name)):
            if os.path.getsize(src) == os.path.getsize(os.path.join(BACKGROUNDS_FOLDER, dest_name)):
                break                                  # такая картинка уже есть
            dest_name = f"{name}_{n}{ext}"
            n += 1
        dest = os.path.join(BACKGROUNDS_FOLDER, dest_name)
        if not os.path.exists(dest):
            import shutil
            shutil.copy2(src, dest)
        return f"{SCRIPT_FOLDER}/backgrounds/{dest_name}"
    except Exception as e:
        log_error(f"❌ Не удалось скопировать фон: {e}")
        return None


def remove_background_file_if_unused(rel):
    """Удаляет копию картинки, если на неё не ссылается ни текущий, ни сохранённый фон."""
    if not rel:
        return
    if current_bg.get("image") == rel or any(c.get("image") == rel for c in saved_backgrounds):
        return
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), rel)
        if os.path.isfile(path) and os.path.commonpath([path, BACKGROUNDS_FOLDER]) == os.path.abspath(BACKGROUNDS_FOLDER):
            os.remove(path)
    except Exception:
        pass


def set_current_background(cfg):
    global current_bg
    current_bg = bgmod.normalize_bg(cfg)


# ═══════════════════════════════════════════════════════════════
# 14b. ОБЩИЕ ВИДЖЕТЫ ГЛАВНОГО ОКНА
# ═══════════════════════════════════════════════════════════════

class LedWidget(QWidget):
    """Круглый светодиод: off — серый, ready — красный, armed — зелёный."""
    COLORS = {"off": "#2a2a2c", "ready": "#e53935", "armed": "#43a047"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(12, 12)
        self.state = "off"

    def set_state(self, state):
        if state != self.state:
            self.state = state
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        color = QColor(self.COLORS.get(self.state, self.COLORS["off"]))
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawEllipse(1, 1, 10, 10)


class BackdropWidget(QWidget):
    """Слой с картинкой фона. Лежит под всем интерфейсом и не перехватывает мышь."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.cfg = bgmod.normalize_bg(None)
        self.sidebar_w = 176
        self.top_h = 46
        self._pixmap = None
        self._scaled = None
        self._scaled_key = None

    def set_config(self, cfg):
        old_image = self.cfg.get("image")
        self.cfg = bgmod.normalize_bg(cfg)
        if self.cfg["image"] != old_image or self._pixmap is None:
            self._pixmap = None
            if self.cfg["image"]:
                pm = QPixmap(os.path.join(os.path.dirname(os.path.abspath(__file__)), self.cfg["image"]))
                self._pixmap = None if pm.isNull() else pm
            self._scaled_key = None
        self.update()

    def paintEvent(self, event):
        if self.cfg["mode"] == "none" or self._pixmap is None:
            return
        area = bgmod.paint_area(self.cfg["mode"], self.width(), self.height(),
                                self.sidebar_w, self.top_h, self.cfg["top"])
        if not area or area[2] <= 0 or area[3] <= 0:
            return
        ax, ay, aw, ah = area
        x, y, w, h = bgmod.image_rect(self._pixmap.width(), self._pixmap.height(), area,
                                      self.cfg["scale"], self.cfg["offset"])
        if self._scaled_key != (w, h):
            self._scaled = self._pixmap.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            self._scaled_key = (w, h)

        p = QPainter(self)
        p.setClipRect(ax, ay, aw, ah)
        p.drawPixmap(x, y, self._scaled)
        dim = int(255 * self.cfg["dim"] / 100)
        if dim:
            p.fillRect(ax, ay, aw, ah, QColor(14, 14, 15, dim))


class JarvisMainWindow(QMainWindow):
    WIN_W, WIN_H = 900, 580
    PAGE_HOME, PAGE_COMMANDS, PAGE_SYSTEM, PAGE_ABOUT = range(4)

    def __init__(self):
        super().__init__()

        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(self.WIN_W, self.WIN_H)
        self.setFocusPolicy(Qt.StrongFocus)

        self.drag_position = QPoint()
        self.is_fullscreen = False
        self.edit_mode = False
        self._bg_drag = None
        self._last_heard = None
        self._last_slow = 0.0
        self._current_page = self.PAGE_HOME
        self.gesture_engine = GestureEngine(camera_index=0)
        self.gesture_led_state = "off"

        self.central_widget = QWidget()
        self.central_widget.setObjectName("Container")
        self.apply_container_style(fullscreen=False)

        root = QVBoxLayout(self.central_widget)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.title_bar = self._build_title_bar()
        root.addWidget(self.title_bar)
        root.addWidget(self._divider(horizontal=True))

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.sidebar = self._build_sidebar()
        body.addWidget(self.sidebar)
        body.addWidget(self._divider(horizontal=False))

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_home_page())
        self.stack.addWidget(self._build_commands_page())
        self.stack.addWidget(self._build_system_page())
        self.stack.addWidget(self._build_about_page())
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)

        self.edit_bar = self._build_edit_bar()
        self.edit_bar.hide()
        root.addWidget(self.edit_bar)

        self.setCentralWidget(self.central_widget)

        # фон лежит под всем интерфейсом
        self.backdrop = BackdropWidget(self.central_widget)
        self.backdrop.setGeometry(self.central_widget.rect())
        self.backdrop.lower()
        self.backdrop.set_config(current_bg)

        self.select_page(self.PAGE_HOME)
        self.apply_backdrop_layout()

        self.timer = QTimer()
        self.timer.timeout.connect(self.loop)
        self.timer.start(33)

        if gestures_enabled:
            self.set_gestures_enabled(True)
        if fullscreen_mode:
            self.go_fullscreen()

        log_info(f"🚀 JARVIS AZ v{VERSION} ЗАПУЩЕН!")

    # ── сборка интерфейса ───────────────────────────────────────
    def _divider(self, horizontal):
        line = QFrame()
        line.setStyleSheet(f"background: {UI['border']}; border: none;")
        if horizontal:
            line.setFixedHeight(1)
        else:
            line.setFixedWidth(1)
        return line

    def _build_title_bar(self):
        bar = QWidget()
        bar.setFixedHeight(46)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(22, 0, 12, 0)
        lay.setSpacing(10)

        title = QLabel("Jarvis AZ")
        title.setStyleSheet(f"color: {UI['text']}; font-size: 13px; letter-spacing: 2px;")
        version = QLabel(f"v{VERSION}")
        version.setStyleSheet(f"color: {UI['dim']}; font-size: 11px;")
        lay.addWidget(title)
        lay.addWidget(version)
        lay.addStretch()

        for symbol, handler, hover in (("–", self.showMinimized, UI['text']),
                                       ("✕", self.close, UI['error'])):
            btn = QPushButton(symbol)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedSize(30, 30)
            btn.setStyleSheet(f"""
                QPushButton {{ background: transparent; color: {UI['dim']};
                              border: none; font-size: 15px; }}
                QPushButton:hover {{ color: {hover}; }}
            """)
            btn.clicked.connect(handler)
            lay.addWidget(btn)
        return bar

    def _build_sidebar(self):
        side = QWidget()
        side.setFixedWidth(176)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(0, 18, 0, 18)
        lay.setSpacing(2)

        self.nav_buttons = []
        items = ((tr("Главная"), self.PAGE_HOME),
                 (tr("Команды"), self.PAGE_COMMANDS),
                 (tr("Система"), self.PAGE_SYSTEM),
                 (tr("О программе"), self.PAGE_ABOUT))
        for text, page in items:
            btn = self._nav_button(text)
            btn.clicked.connect(lambda _=False, pg=page: self.select_page(pg))
            lay.addWidget(btn)
            self.nav_buttons.append(btn)

        lay.addStretch()

        settings_btn = self._nav_button(tr("Настройки"))
        settings_btn.setCheckable(False)
        settings_btn.clicked.connect(self.open_settings)
        lay.addWidget(settings_btn)
        return side

    def _nav_button(self, text):
        btn = QPushButton(text)
        btn.setCheckable(True)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(40)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {UI['dim']};
                border: none; border-left: 2px solid transparent;
                text-align: left; padding-left: 22px; font-size: 13px;
            }}
            QPushButton:hover {{ color: {UI['text']}; }}
            QPushButton:checked {{ color: {UI['text']}; border-left: 2px solid {UI['text']}; }}
        """)
        return btn

    def _build_home_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(32, 22, 32, 22)
        lay.setSpacing(6)

        # показатели в правом верхнем углу
        top = QHBoxLayout()
        top.addStretch()
        card = QWidget()
        card.setFixedWidth(190)
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(0, 0, 0, 0)
        card_lay.setSpacing(0)
        self.home_cpu = BarRow("CPU")
        self.home_ram = BarRow("RAM")
        self.home_vol = BarRow(tr("Громкость"))
        for row in (self.home_cpu, self.home_ram, self.home_vol):
            card_lay.addWidget(row)

        gesture_row = QHBoxLayout()
        gesture_row.setContentsMargins(0, 8, 0, 0)
        self.gesture_led = LedWidget()
        gesture_label = QLabel(tr("Жесты"))
        gesture_label.setStyleSheet(f"color: {UI['dim']}; font-size: 12px;")
        gesture_row.addWidget(self.gesture_led)
        gesture_row.addSpacing(8)
        gesture_row.addWidget(gesture_label)
        gesture_row.addStretch()
        card_lay.addLayout(gesture_row)

        top.addWidget(card)
        lay.addLayout(top)

        greeting = QLabel(tr("Привет, я Jarvis AZ"))
        greeting.setAlignment(Qt.AlignCenter)
        greeting.setStyleSheet(f"color: {UI['text']}; font-size: 28px; font-weight: 300;")
        hint = QLabel(tr("Скажите «Джарвис» и команду"))
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet(f"color: {UI['dim']}; font-size: 13px; letter-spacing: 1px;")
        lay.addWidget(greeting)
        lay.addWidget(hint)

        self.reactor = ReactorWidget()
        self.engine = self.reactor
        lay.addWidget(self.reactor, 1)

        self.heard_label = QLabel()
        self.heard_label.setAlignment(Qt.AlignCenter)
        self.heard_label.setFixedSize(380, 40)
        pill_row = QHBoxLayout()
        pill_row.addStretch()
        pill_row.addWidget(self.heard_label)
        pill_row.addStretch()
        lay.addLayout(pill_row)
        lay.addSpacing(10)

        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        self.dot = QLabel("●")
        self.dot.setStyleSheet(f"color: {UI['dim']}; font-size: 9px;")
        self.status_label = QLabel(self._status_line())
        self.status_label.setStyleSheet(f"color: {UI['dim']}; font-size: 11px;")
        bottom.addWidget(self.dot)
        bottom.addWidget(self.status_label)
        bottom.addStretch()

        clock_col = QVBoxLayout()
        clock_col.setSpacing(0)
        self.clock_label = QLabel()
        self.clock_label.setAlignment(Qt.AlignRight)
        self.clock_label.setStyleSheet(f"color: {UI['text']}; font-size: 18px; font-weight: 300;")
        self.date_label = QLabel()
        self.date_label.setAlignment(Qt.AlignRight)
        self.date_label.setStyleSheet(f"color: {UI['dim']}; font-size: 11px;")
        clock_col.addWidget(self.clock_label)
        clock_col.addWidget(self.date_label)
        bottom.addLayout(clock_col)
        lay.addLayout(bottom)
        return page

    def _status_line(self):
        langs = "Русский" if language == "ru" else "English"
        engines = ", ".join(recognition_engines)
        return f"{tr('Голос')}: {langs}   ·   {engines}"

    def _build_commands_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(32, 22, 32, 22)
        lay.setSpacing(14)

        title = QLabel(tr("Команды"))
        title.setStyleSheet(f"color: {UI['text']}; font-size: 20px; font-weight: 300;")
        lay.addWidget(title)

        self.cmd_search = QLineEdit()
        self.cmd_search.setPlaceholderText(tr("Найти команду"))
        self.cmd_search.setStyleSheet(f"""
            QLineEdit {{ background: #161617; color: {UI['text']};
                        border: 1px solid #232325; border-radius: 8px;
                        padding: 9px 12px; font-size: 13px; }}
            QLineEdit:focus {{ border: 1px solid #4a4a4e; }}
        """)
        self.cmd_search.textChanged.connect(self.filter_commands)
        lay.addWidget(self.cmd_search)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ background: transparent; width: 8px; }}
            QScrollBar::handle:vertical {{ background: #2a2a2c; border-radius: 4px; min-height: 30px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        self.cmd_container = QWidget()
        self.cmd_container.setStyleSheet("background: transparent;")
        self.cmd_layout = QVBoxLayout(self.cmd_container)
        self.cmd_layout.setContentsMargins(0, 0, 8, 0)
        self.cmd_layout.setSpacing(4)
        scroll.setWidget(self.cmd_container)
        lay.addWidget(scroll, 1)
        return page

    def rebuild_commands(self):
        while self.cmd_layout.count():
            item = self.cmd_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.cmd_groups = []

        if language == "en":
            groups = {k: v for k, v in ALL_COMMANDS_EN.items()}
        else:
            groups = {re.sub(r'^[^\w]+', '', k).strip(): v for k, v in ALL_COMMANDS.items()}
        if user_commands:
            groups[tr("Свои команды")] = [f"{name}" for name in user_commands.keys()]

        # отдельный блок: все команды «открой …» для программ и игр, по нажатию раскрывается
        self.apps_header = QPushButton()
        self.apps_header.setCursor(Qt.PointingHandCursor)
        self.apps_header.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {UI['dim']}; border: none; text-align: left;"
            f" font-size: 11px; letter-spacing: 2px; padding-top: 12px; }}"
            f"QPushButton:hover {{ color: {UI['text']}; }}")
        self.apps_header.clicked.connect(self.toggle_apps_block)
        self.cmd_layout.addWidget(self.apps_header)
        self.apps_labels = []
        for phrase, title, kind in apps.list_apps():
            cmd_html = (f"<span style='color:{UI['text']}'>{html.escape(phrase)}</span>"
                        f"&nbsp;&nbsp;<span style='color:{UI['dim']}'>{html.escape(title)} · {kind}</span>")
            lbl = QLabel(cmd_html)
            lbl.setStyleSheet("font-size: 13px; padding: 3px 0;")
            lbl.setWordWrap(True)
            self.cmd_layout.addWidget(lbl)
            self.apps_labels.append((lbl, f"{phrase} {title} {kind}".lower()))

        for clean, lines in groups.items():
            header = QLabel(clean)
            header.setStyleSheet(f"color: {UI['dim']}; font-size: 11px; letter-spacing: 2px; padding-top: 12px;")
            self.cmd_layout.addWidget(header)

            labels = []
            for line in lines:
                cmd, _, desc = line.partition(" — ")
                html_text = f"<span style='color:{UI['text']}'>{html.escape(cmd)}</span>"
                if desc:
                    html_text += f"&nbsp;&nbsp;<span style='color:{UI['dim']}'>{html.escape(desc)}</span>"
                lbl = QLabel(html_text)
                lbl.setStyleSheet("font-size: 13px; padding: 3px 0;")
                lbl.setWordWrap(True)
                self.cmd_layout.addWidget(lbl)
                labels.append((lbl, line.lower()))
            self.cmd_groups.append((header, clean.lower(), labels))

        self.cmd_layout.addStretch()
        self.filter_commands(self.cmd_search.text())

    def toggle_apps_block(self):
        self._apps_open = not getattr(self, "_apps_open", False)
        self.filter_commands(self.cmd_search.text())

    def filter_commands(self, text):
        q = text.strip().lower()
        if hasattr(self, "apps_header"):
            # при поиске блок раскрывается сам и показывает только подходящие программы
            expanded = getattr(self, "_apps_open", False) or bool(q)
            any_app = False
            for lbl, haystack in self.apps_labels:
                match = (not q) or q in haystack or q in "программы и игры"
                lbl.setVisible(expanded and match)
                any_app = any_app or match
            self.apps_header.setVisible(any_app)
            arrow = "▾" if expanded else "▸"
            self.apps_header.setText(f"{arrow}  {tr('Программы и игры')} ({len(self.apps_labels)})")
        for header, title, labels in getattr(self, "cmd_groups", []):
            any_visible = False
            for lbl, haystack in labels:
                show = (not q) or q in haystack or q in title
                lbl.setVisible(show)
                any_visible = any_visible or show
            header.setVisible(any_visible)

    def _build_system_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(32, 22, 32, 22)
        lay.setSpacing(10)

        title = QLabel(tr("Система"))
        title.setStyleSheet(f"color: {UI['text']}; font-size: 20px; font-weight: 300;")
        lay.addWidget(title)
        lay.addSpacing(10)

        self.sys_cpu = BarRow(tr("Процессор"), big=True)
        self.sys_ram = BarRow(tr("Память"), big=True)
        self.sys_disk = BarRow(tr("Диск"), big=True)
        self.sys_vol = BarRow(tr("Громкость"), big=True)
        for row in (self.sys_cpu, self.sys_ram, self.sys_disk, self.sys_vol):
            lay.addWidget(row)

        lay.addSpacing(14)
        self.uptime_label = QLabel()
        self.uptime_label.setStyleSheet(f"color: {UI['dim']}; font-size: 13px;")
        lay.addWidget(self.uptime_label)
        lay.addStretch()
        return page

    def _build_about_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(32, 22, 32, 22)
        lay.setSpacing(8)
        lay.addStretch()

        name = QLabel("Jarvis AZ")
        name.setAlignment(Qt.AlignCenter)
        name.setStyleSheet(f"color: {UI['text']}; font-size: 30px; font-weight: 300; letter-spacing: 3px;")
        ver = QLabel(f"{tr('Версия')} {VERSION}")
        ver.setAlignment(Qt.AlignCenter)
        ver.setStyleSheet(f"color: {UI['dim']}; font-size: 13px;")
        desc = QLabel(tr("Голосовой ассистент для Windows"))
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet(f"color: {UI['dim']}; font-size: 13px;")
        lay.addWidget(name)
        lay.addWidget(ver)
        lay.addSpacing(6)
        lay.addWidget(desc)
        lay.addSpacing(18)

        for key, value in ((tr("Разработчик"), "Azamhon H."), (tr("Язык"), "Python"),
                           ("СБЕР:", "2202208528973606"),
                           (" "," "),
                           ("GitHub", "<a href='https://github.com/data-az'>github.com/data-az</a>"),
                           ("Telegram", "<a href='https://t.me/Durov_0ffical'>@Durov_0ffical</a>"),
                           ("Vibe", "<a href='https://vibe.widemade.com/u/aza'>vibe.widemade.com/u/aza</a>")):
            row = QLabel(f"<span style='color:{UI['dim']}'>{key}</span>"
                         f"&nbsp;&nbsp;&nbsp;<span style='color:{UI['text']}'>{value}</span>")
            row.setAlignment(Qt.AlignCenter)
            row.setStyleSheet("font-size: 13px;")
            row.setOpenExternalLinks(True)
            lay.addWidget(row)
        lay.addStretch()
        return page

    def _build_edit_bar(self):
        """Панель режима настройки фона. Видна только пока фон редактируется."""
        bar = QFrame()
        bar.setStyleSheet(f"QFrame {{ background: #161617; border-top: 1px solid {UI['border']}; }}"
                          f"QLabel {{ background: transparent; color: {UI['dim']}; font-size: 11px; }}")
        lay = QVBoxLayout(bar)
        lay.setContentsMargins(20, 10, 20, 10)
        lay.setSpacing(8)

        hint = QLabel(tr("Перетащите картинку мышью. Колёсико — масштаб."))
        lay.addWidget(hint)

        row1 = QHBoxLayout()
        self.bg_mode_combo = QComboBox()
        self.bg_mode_combo.setStyleSheet(
            f"QComboBox {{ background: #0e0e0f; color: {UI['text']}; border: 1px solid #2a2a2c; "
            "border-radius: 6px; padding: 5px 8px; font-size: 12px; }}")
        for key, label in (("full", tr("Фон на весь экран")),
                           ("except_menu", tr("Фон кроме левого меню")),
                           ("none", tr("Без фона"))):
            self.bg_mode_combo.addItem(label, key)
        self.bg_mode_combo.currentIndexChanged.connect(self._on_bg_mode_changed)
        row1.addWidget(self.bg_mode_combo, 1)

        self.bg_top_check = QCheckBox(tr("Фон под верхней полосой"))
        self.bg_top_check.setStyleSheet(f"QCheckBox {{ color: {UI['text']}; font-size: 12px; }}")
        self.bg_top_check.toggled.connect(self._on_bg_top_changed)
        row1.addWidget(self.bg_top_check)
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel(tr("Затемнение")))
        self.bg_dim_slider = QSlider(Qt.Horizontal)
        self.bg_dim_slider.setRange(0, 90)
        self.bg_dim_slider.valueChanged.connect(self._on_bg_dim_changed)
        row2.addWidget(self.bg_dim_slider, 1)
        lay.addLayout(row2)

        row3 = QHBoxLayout()
        row3.setSpacing(8)
        for text, handler in ((tr("Сбросить"), self.reset_background),
                              (tr("Сохранить текущий"), self.save_current_background),
                              (tr("Готово"), self.end_background_edit)):
            btn = QPushButton(text)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {UI['text']}; border: 1px solid #3a3a3d;"
                " border-radius: 6px; padding: 6px 14px; font-size: 12px; }"
                f"QPushButton:hover {{ border: 1px solid {UI['text']}; }}")
            btn.clicked.connect(handler)
            row3.addWidget(btn)
        row3.addStretch()
        lay.addLayout(row3)
        return bar

    # ── оформление ──────────────────────────────────────────────
    def apply_container_style(self, fullscreen):
        radius = "0px" if fullscreen else "16px"
        border = "none" if fullscreen else f"1px solid {UI['border']}"
        self.central_widget.setStyleSheet(f"""
            QWidget#Container {{
                background-color: {COLORS['bg']};
                border: {border};
                border-radius: {radius};
            }}
            QLabel {{ font-family: 'Segoe UI'; background: transparent; }}
        """)

    def apply_backdrop_layout(self):
        """Левое меню и верхняя полоса становятся прозрачными только там, где под ними картинка."""
        mode = current_bg["mode"]
        top_on = mode != "none" and current_bg["top"]
        side_css = "background: transparent;" if mode == "full" else f"background: {COLORS['bg']};"
        self.sidebar.setStyleSheet(side_css)
        self.title_bar.setStyleSheet("background: transparent;" if top_on else f"background: {COLORS['bg']};")
        self.backdrop.sidebar_w = self.sidebar.width()
        self.backdrop.top_h = self.title_bar.height()
        self.backdrop.set_config(current_bg)

    def apply_background(self):
        self.apply_backdrop_layout()

    def select_page(self, page):
        self._current_page = page
        self.stack.setCurrentIndex(page)
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == page)
        if page == self.PAGE_COMMANDS:
            self.rebuild_commands()
        self._last_slow = 0.0

    # ── режим настройки фона ────────────────────────────────────
    def start_background_edit(self, image_rel):
        global current_bg
        cfg = dict(current_bg)
        cfg["image"] = image_rel
        if cfg["mode"] == "none":
            cfg["mode"] = "full"
        current_bg = bgmod.normalize_bg(cfg)
        self._open_edit_bar(True)

    def _open_edit_bar(self, on):
        self.edit_mode = on
        self.edit_bar.setVisible(on)
        if on:
            self._sync_edit_controls()
        self.apply_backdrop_layout()

    def _sync_edit_controls(self):
        for w in (self.bg_mode_combo, self.bg_top_check, self.bg_dim_slider):
            w.blockSignals(True)
        self.bg_mode_combo.setCurrentIndex(self.bg_mode_combo.findData(current_bg["mode"]))
        self.bg_top_check.setChecked(current_bg["top"])
        self.bg_dim_slider.setValue(current_bg["dim"])
        for w in (self.bg_mode_combo, self.bg_top_check, self.bg_dim_slider):
            w.blockSignals(False)

    def _on_bg_mode_changed(self, _index):
        global current_bg
        current_bg = bgmod.normalize_bg({**current_bg, "mode": self.bg_mode_combo.currentData()})
        self.apply_backdrop_layout()

    def _on_bg_top_changed(self, checked):
        global current_bg
        current_bg = bgmod.normalize_bg({**current_bg, "top": checked})
        self.apply_backdrop_layout()

    def _on_bg_dim_changed(self, value):
        global current_bg
        current_bg = bgmod.normalize_bg({**current_bg, "dim": value})
        self.apply_backdrop_layout()

    def reset_background(self):
        global current_bg
        current_bg = bgmod.normalize_bg(None)
        self._sync_edit_controls()
        self.apply_backdrop_layout()

    def save_current_background(self):
        global saved_backgrounds
        name, ok = QInputDialog.getText(self, tr("Сохранить фон"), tr("Имя фона"),
                                        text=current_bg.get("name") or tr("Мой фон"))
        if not ok or not name.strip():
            return
        cfg = dict(current_bg)
        cfg["name"] = name.strip()
        saved_backgrounds.append(bgmod.normalize_bg(cfg))
        save_settings()
        log_info(f"🖼 Фон сохранён: {cfg['name']}")
        audio_output.play_trigger("фон изменён")

    def end_background_edit(self):
        if current_bg["image"] and current_bg["mode"] == "none":
            pass                                     # картинка есть, но выключена — так и задумано
        save_settings()
        self._open_edit_bar(False)

    # ── окно ────────────────────────────────────────────────────
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "backdrop"):
            self.backdrop.setGeometry(self.central_widget.rect())

    def wheelEvent(self, event):
        global current_bg
        if self.edit_mode:
            steps = event.angleDelta().y() / 120.0
            scale = bgmod.scale_on_wheel(current_bg["scale"], steps)
            current_bg = bgmod.normalize_bg({**current_bg, "scale": scale})
            self.apply_backdrop_layout()
            event.accept()
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F11:
            if self.is_fullscreen:
                self.go_windowed()
            else:
                self.go_fullscreen()
        if event.key() == Qt.Key_Escape and self.edit_mode:
            self.end_background_edit()
        super().keyPressEvent(event)

    def go_fullscreen(self):
        global fullscreen_mode
        fullscreen_mode = True
        self.is_fullscreen = True

        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.apply_container_style(fullscreen=True)
        self.showFullScreen()

    def go_windowed(self):
        global fullscreen_mode
        fullscreen_mode = False
        self.is_fullscreen = False

        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.apply_container_style(fullscreen=False)
        self.showNormal()
        self.setFixedSize(self.WIN_W, self.WIN_H)

    def open_settings(self):
        if self.edit_mode:
            self.end_background_edit()
        run_exec(SettingsDialog(self))

    # ── жесты ───────────────────────────────────────────────────
    def set_gestures_enabled(self, on):
        global gestures_enabled
        gestures_enabled = bool(on)
        if on:
            self.gesture_engine.start()
        else:
            self.gesture_engine.stop()
            self.gesture_led.set_state("off")

    def gesture_status_text(self):
        if self.gesture_engine.error:
            return self.gesture_engine.error
        if not gestures_enabled:
            return tr("Выключено")
        if self.gesture_engine.state == "off":
            return tr("Камера запускается...")
        return tr("Ждёт открытую ладонь") if self.gesture_engine.state == "ready" else tr("Ладонь распознана, ждёт жест")

    def _poll_gestures(self):
        if not gestures_enabled:
            return
        for ev in self.gesture_engine.pop_events():
            if ev == ("gesture", "M"):
                log_info("✋ Жест М: открываю браузер")
                _cmd_q.put("открой браузер")
        state = self.gesture_engine.state if gestures_enabled else "off"
        self.gesture_led.set_state(state if state in ("ready", "armed") else "off")

    # ── мышь: окно или картинка ─────────────────────────────────
    def mousePressEvent(self, event):
        if self.is_fullscreen:
            return
        if event.button() == Qt.LeftButton:
            if self.edit_mode and current_bg["mode"] != "none":
                self._bg_drag = (event.globalPosition().toPoint() if hasattr(event, "globalPosition")
                                 else event.globalPos(), list(current_bg["offset"]))
            else:
                self.drag_position = event_global_pos(event) - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        global current_bg
        if self.is_fullscreen:
            return
        if event.buttons() & Qt.LeftButton:
            if self._bg_drag is not None:
                start, offset0 = self._bg_drag
                now = event_global_pos(event)
                dx, dy = now.x() - start.x(), now.y() - start.y()
                current_bg = bgmod.normalize_bg({**current_bg, "offset": [offset0[0] + dx, offset0[1] + dy]})
                self.apply_backdrop_layout()
            else:
                self.move(event_global_pos(event) - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._bg_drag = None

    # ── состояние ───────────────────────────────────────────────
    def update_status_indicator(self):
        global command_status

        if command_status != "idle" and time.time() - status_timer > 2.0:
            command_status = "idle"

        color = {"success": UI['ok'], "error": UI['error']}.get(command_status, UI['dim'])
        self.dot.setStyleSheet(f"color: {color}; font-size: 9px;")

    def update_texts(self):
        txt = heard_text if (heard_text and time.time() - heard_time < 6.0) else ""
        if txt != self._last_heard:
            self._last_heard = txt
            if txt:
                self.heard_label.setText(txt)
                self.heard_label.setStyleSheet(
                    f"color: {UI['text']}; font-size: 14px; border: 1px solid #3a3a3d; border-radius: 20px;")
            else:
                self.heard_label.setText(tr("Ожидаю команду"))
                self.heard_label.setStyleSheet(
                    f"color: {UI['dim']}; font-size: 13px; border: 1px solid #232325; border-radius: 20px;")

    def update_slow_stats(self):
        """Раз в секунду: нагрузка, диск, громкость, время."""
        global smooth_cpu
        smooth_cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        try:
            disk = psutil.disk_usage(os.path.abspath(os.sep)).percent
        except Exception:
            disk = 0
        vol = get_volume()

        self.home_cpu.set_value(smooth_cpu)
        self.home_ram.set_value(ram)
        self.home_vol.set_value(vol)

        if self._current_page == self.PAGE_SYSTEM:
            self.sys_cpu.set_value(smooth_cpu)
            self.sys_ram.set_value(ram)
            self.sys_disk.set_value(disk)
            self.sys_vol.set_value(vol)
            up = int(time.time() - psutil.boot_time())
            h, rem = divmod(up, 3600)
            m, s = divmod(rem, 60)
            self.uptime_label.setText(f"{tr('Время работы компьютера')}   {h}:{m:02d}:{s:02d}")

        now = datetime.now()
        self.clock_label.setText(now.strftime("%H:%M"))
        self.date_label.setText(now.strftime("%d.%m.%Y"))

    def loop(self):
        global is_running

        if not is_running:
            self.close()
            return

        now = time.time()
        if now - self._last_slow >= 1.0:
            self._last_slow = now
            self.update_slow_stats()

        self.update_status_indicator()
        voice = get_audio_level()
        self.reactor.tick(voice, command_status)
        self.update_texts()
        self._poll_gestures()

    def closeEvent(self, event):
        global is_running, audio_stream, pa_instance
        is_running = False
        self.gesture_engine.stop()

        save_settings()
        log_info("🛑 JARVIS AZ ЗАВЕРШЕН")

        if audio_stream:
            try:
                with _audio_lock:
                    audio_stream.stop_stream()
                    audio_stream.close()
            except Exception:
                pass

        if pa_instance:
            try:
                pa_instance.terminate()
            except Exception:
                pass

        event.accept()


# ═══════════════════════════════════════════════════════════════
# 15. ЗАПУСК
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    start_voice_threads()

    app = QApplication(sys.argv)
    window = JarvisMainWindow()
    window.show()
    sys.exit(run_exec(app))
