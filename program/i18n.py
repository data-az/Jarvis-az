"""Языки: интерфейс и голосовые команды.

Интерфейс: tr("русская строка") возвращает английский текст, если выбран английский.
Команды: английская фраза переводится в уже известную русскую
("volume plus one" -> "звук плюс 1"), поэтому вся логика выполнения общая.
"""
import re

LANG = "ru"          # "ru" или "en"; выставляется при запуске из настроек


def set_language(code):
    global LANG
    LANG = "en" if code == "en" else "ru"


def tr(text):
    if LANG == "en":
        return EN_UI.get(text, text)
    return text


# ─── интерфейс: русская строка -> английская ───────────────────
# Ключ — русский текст из кода. Нет в словаре — остаётся русский.
EN_UI = {
    "Главная": "Home",
    "Команды": "Commands",
    "Система": "System",
    "О программе": "About",
    "Настройки": "Settings",
    "Найти команду": "Search commands",
    "Процессор": "Processor",
    "Память": "Memory",
    "Диск": "Disk",
    "Громкость": "Volume",
    "Слушаю": "Listening",
    "Ожидаю команду": "Waiting for a command",
    "Привет, я Jarvis AZ": "Hi, I'm Jarvis AZ",
    "Скажите «Джарвис» и команду": "Say “Jarvis” and a command",
    "Версия": "Version",
    "Голосовой ассистент для Windows": "Voice assistant for Windows",
    "Разработчик": "Developer",
    "Язык": "Language",
    "Время работы компьютера": "Computer uptime",
    "Жесты": "Gestures",
    "Фон": "Background",
    "Сменить фон": "Change background",
    "Сохранённые фоны": "Saved backgrounds",
    "Применить": "Apply",
    "Удалить": "Delete",
    "Сохранить текущий": "Save current",
    "Сбросить": "Reset",
    "Готово": "Done",
    "Затемнение": "Dimming",
    "Режим фона": "Background mode",
    "Фон на весь экран": "Full window",
    "Фон кроме левого меню": "All except left menu",
    "Без фона": "No background",
    "Фон под верхней полосой": "Background under the top bar",
    "Перетащите картинку мышью. Колёсико — масштаб.": "Drag the picture with the mouse. Wheel — zoom.",
    "Картинка сохранится в папку программы.": "The picture is copied into the program folder.",
    "Имя фона": "Background name",
    "Язык интерфейса": "Interface language",
    "Язык голоса": "Voice language",
    "Распознавание речи": "Speech recognition",
    "Голосовой ответ после действия": "Voice reply after an action",
    "Распознавание жестов (камера)": "Gesture recognition (camera)",
    "Камера": "Camera",
    "Микрофон": "Microphone",
    "Музыка": "Music",
    "Графика": "Graphics",
    "Графика + команды": "Graphics + commands",
    "Музыка + микрофон": "Music + microphone",
    "Пользовательские команды": "Custom commands",
    "Добавить": "Add",
    "Очистить": "Clear",
    "Файл": "File",
    "Обновить": "Refresh",
    "Запустить": "Run",
    "Перезагрузить": "Restart",
    "Закрыть": "Close",
    "Инфо": "Info",
    "Информация": "Information",
    "Выбрать": "Choose",
    "Очистка кэша и временных файлов": "Clear cache and temporary files",
    "Перезагрузить всё (микрофон, звук, аудио)": "Restart everything (microphone, sound, audio)",
    "Системный (по умолчанию)": "System default",
    "Выберите устройство для распознавания голоса": "Choose the device for speech recognition",
    "Готов к работе": "Ready",
    "Готов к очистке": "Ready to clean",
    "Перезагрузка выполнена!": "Restart done!",
    "Ошибка перезагрузки": "Restart failed",
    "Перезагрузка...": "Restarting...",
    "Логи": "Logs",
    "Что показывать в консоли при распознавании. Файл в папке logs пишется полностью.": "What to show in the console during recognition. The logs folder always keeps everything.",
    "Время: часы, минуты, секунды": "Time: hours, minutes, seconds",
    "Миллисекунды": "Milliseconds",
    "Длительность фразы": "Phrase length",
    "Громкость фразы (дБ)": "Phrase volume (dB)",
    "Кто ответил (движок)": "Which engine answered",
    "Что распознано (текст)": "Recognized text",
    "Уверенность движка": "Engine confidence",
    "Решение: команда или нет": "Decision: command or not",
    "Задержка после конца фразы": "Delay after the phrase ends",
    "Очередь распознавания": "Recognition queue",
    "Открыть папку логов": "Open logs folder",
    "Тип команды": "Command type",
    "Файл или программа": "File or program",
    "Папка": "Folder",
    "Сайт": "Website",
    "Адрес сайта": "Website address",
    "Введите адрес сайта!": "Enter the website address!",
    "Выберите папку для команды!": "Choose a folder for the command!",
    "Выберите папку": "Choose a folder",
    "не выбрано": "not selected",
    "сайт": "site",
    "папка": "folder",
    "1. Покажите открытую ладонь. Светодиод станет зелёным.": "1. Show an open palm. The LED turns green.",
    "2. Нарисуйте указательным пальцем букву М в воздухе.": "2. Draw the letter M in the air with your index finger.",
    "3. Откроется браузер.": "3. The browser opens.",
    "Google, English (online)": "Google, English (online)",
    "Google, русский (онлайн)": "Google, Russian (online)",
    "Vosk, English (offline, fast)": "Vosk, English (offline, fast)",
    "Vosk, русский (офлайн, быстро)": "Vosk, Russian (offline, fast)",
    "Введите команду!": "Enter a command!",
    "Включить приветствие": "Enable greeting",
    "Внимание: ": "Warning: ",
    "Все фразы идут параллельно. Выполняется первая распознанная команда.": "All phrases are processed in parallel. The first recognized command runs.",
    "Выберите картинку": "Choose a picture",
    "Выберите команду для удаления!": "Choose a command to delete!",
    "Выберите папку с музыкой": "Choose the music folder",
    "Выберите файл для команды!": "Choose a file for the command!",
    "Выберите файл или программу": "Choose a file or program",
    "Выберите хотя бы один движок. Пока выбора нет, будет Vosk, русский.": "Select at least one engine. Until then, Vosk Russian is used.",
    "Выбрать файл": "Choose file",
    "Выключено": "Off",
    "Голосовой ассистент с визуализацией": "Voice assistant with visualization",
    "Если жест не пришёл за 5 секунд, светодиод снова станет красным.": "If no gesture arrives within 5 seconds, the LED turns red again.",
    "Ждёт открытую ладонь": "Waiting for an open palm",
    "Жесты рукой (камера)": "Hand gestures (camera)",
    "Звук и голос": "Sound and voice",
    "Интерфейс": "Interface",
    "Как пользоваться:": "How to use:",
    "Камера запускается...": "Camera starting...",
    "Команда существует": "Command already exists",
    "Команда...": "Command...",
    "Ладонь распознана, ждёт жест": "Palm detected, waiting for a gesture",
    "Мой фон": "My background",
    "Не удалось скопировать картинку.": "Could not copy the picture.",
    "Очистка всех команд": "Clear all commands",
    "Очистка...": "Clearing...",
    "Ошибка": "Error",
    "Папка не выбрана": "No folder selected",
    "Пока эти движки не работают.": "These engines are not working yet.",
    "Полноэкранный режим (F11)": "Full screen (F11)",
    "Свои команды": "Custom commands",
    "Сохранить фон": "Save background",
    "Удалить ВСЕ пользовательские команды?": "Delete ALL custom commands?",
    "Язык меняется после перезапуска Jarvis.": "The language changes after restarting Jarvis.",
    "без фона": "no background",
    "кроме меню": "except menu",
    "на весь экран": "full window",
    "нет модели {lang}: распакуйте её рядом с 11.py": "no {lang} model: unpack it next to 11.py",
    "установите vosk: pip install vosk": "install vosk: pip install vosk",
    "файл не выбран": "no file selected",
}

# Полные строки английского текста для голоса и логов не нужны: логи остаются русскими.


# ─── команды: английская фраза -> русская ──────────────────────
EN_COMMANDS = [
    ("volume plus", "звук плюс"),
    ("volume up", "звук плюс"),
    ("volume minus", "звук минус"),
    ("volume down", "звук минус"),
    ("max volume", "звук макс"),
    ("full volume", "звук макс"),
    ("unmute", "включить звук"),
    ("mute", "выключить звук"),
    ("screenshot", "скриншот"),
    ("take a screenshot", "скриншот"),
    ("empty recycle bin", "очисти корзину"),
    ("recycle bin", "очисти корзину"),
    ("minimize all windows", "сверни все окна"),
    ("show desktop", "сверни все окна"),
    ("open explorer", "проводник"),
    ("file explorer", "проводник"),
    ("open folder", "проводник"),
    ("open camera", "открой камеру"),
    ("lock computer", "заблокируй компьютер"),
    ("lock the computer", "заблокируй компьютер"),
    ("shut down", "выключи компьютер"),
    ("shutdown", "выключи компьютер"),
    ("restart computer", "перезагрузи компьютер"),
    ("open browser", "открой браузер"),
    ("open google", "открой гугл"),
    ("youtube", "ютуб"),
    ("music", "музыка"),
    ("clean system", "очистка"),
    ("search for", "поиск"),
    ("search", "поиск"),
    ("google", "гугл"),
    ("restart jarvis", "рестарт"),
    ("restart", "рестарт"),
    ("stop", "стоп"),
    ("exit", "выход"),
    ("hello", "привет"),
    ("team fortress", "тим фортрес"),
]

EN_NUMBERS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
}


def numbers_en_to_digits(text):
    """«twenty five» -> «25», «one hundred» -> «100»."""
    words = text.split()
    out = []
    i = 0
    while i < len(words):
        w = words[i]
        if w in EN_NUMBERS:
            val = EN_NUMBERS[w]
            if val in (20, 30, 40, 50, 60, 70, 80, 90) and i + 1 < len(words):
                nxt = EN_NUMBERS.get(words[i + 1])
                if nxt is not None and 1 <= nxt <= 9:
                    val += nxt
                    i += 1
            if w == "hundred" and out and out[-1].isdigit():
                out[-1] = str(int(out[-1]) * 100)
                i += 1
                continue
            out.append(str(val))
        else:
            out.append(w)
        i += 1
    return " ".join(out)


def translate_command(text):
    """Переводит английскую фразу в русскую форму команды. Русские фразы не меняет."""
    t = text.lower()
    t = re.sub(r"[,.!?]", " ", t)
    t = numbers_en_to_digits(t)
    for en, ru in sorted(EN_COMMANDS, key=lambda p: len(p[0]), reverse=True):
        t = re.sub(r"(?<![a-z])" + re.escape(en) + r"(?![a-z])", ru, t)
    return " ".join(t.split())


# ─── голосовой ответ по-английски ─────────────────────────────
EN_VOICE = {
    "Ищу": "Searching",
    "Открываю браузер": "Opening browser",
    "Открываю ютуб": "Opening YouTube",
    "Открываю проводник": "Opening explorer",
    "Запускаю игру": "Starting the game",
    "Открываю камеру": "Opening camera",
    "Камера не найдена": "Camera not found",
    "Скриншот": "Screenshot",
    "Открываю музыку": "Opening music",
    "Система очищена": "System cleaned",
    "Открываю": "Opening",
}


# ─── список команд по-английски (страница «Команды») ──────────
ALL_COMMANDS_EN = {
    "Volume": [
        "volume plus 1, 5, 10, 15, 30, 50 — raise volume",
        "volume minus 1, 5, 10, 15, 30, 50 — lower volume",
        "max volume — 100%",
        "mute — turn sound off",
        "unmute — turn sound on",
    ],
    "Screenshot": ["screenshot — Win+Shift+S (Win 10/11) or Win+PrtScn (Win 8.1)"],
    "Search": ["search, find, google [query] — web search"],
    "System": ["open browser, google — Google", "explorer, folder — open folder",
               "youtube — YouTube", "tf2 — Team Fortress 2"],
    "Windows": ["minimize all windows — Win+D", "restart explorer"],
    "Recycle bin": ["empty recycle bin"],
    "Camera": ["open camera"],
    "Lock": ["lock computer"],
    "Power": ["shut down computer", "restart computer"],
    "Utilities": ["clean system — clear temporary files", "restart Jarvis",
                  "stop, exit — quit Jarvis"],
}

# Русские заголовки категорий -> английские
ALL_COMMANDS_TITLES_EN = {
    "Управление звуком": "Volume", "Скриншот": "Screenshot", "Поиск": "Search",
    "Система": "System", "Окна": "Windows", "Корзина": "Recycle bin", "Камера": "Camera",
    "Блокировка": "Lock", "Управление ПК": "Power", "Утилиты": "Utilities",
}


def english_command_matches(text):
    """True, если английская фраза целиком похожа на команду: «volume plus 5», «open browser».
    Случайные фразы вроде «can you provide music» не проходят, даже если содержат «music»."""
    t = text.lower()
    t = re.sub(r"[,.!?]", " ", t)
    t = " ".join(numbers_en_to_digits(t).split())
    for w in ("jarvis az", "jarvisaz", "jarvis"):
        if t.startswith(w + " ") or t == w:
            t = t[len(w):].strip()
            break
    for en, _ in EN_COMMANDS:
        if t == en:
            return True
        if t.startswith(en + " ") and re.fullmatch(r"\d+", t[len(en) + 1:]):
            return True
    return False
