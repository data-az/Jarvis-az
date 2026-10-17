"""Команды «открой <программа или игра>». Только данные и разбор фраз, без Windows API
(сам запуск делает launch_app в 11.py), поэтому разбор проверяется тестами.

ВСЕ НОВЫЕ КОМАНДЫ ДОЛЖНЫ ВЫПОЛНЯТЬСЯ С КАСТОМНЫМИ ГОЛОСАМИ:
после запуска играет звук «кастом» (да сэр, делаю, хорошо), а не платная озвучка.

Как добавить свою программу: допиши строку в APPS (внизу таблицы).
  P("Название", "алиас|другой алиас", способ запуска, способ запуска, ...)   — программа
  G(...) — то же самое для игры.
Способы запуска пробуются по порядку, пока один не сработает:
  ("lnk", "имя ярлыка|другое имя")  ярлык в меню «Пуск» (самый надёжный способ)
  ("exe", r"путь\\к\\файлу.exe|другой путь")  можно с %ПЕРЕМЕННЫМИ% и *
  ("proto", "spotify")              протокол Windows, например spotify:
  ("steam", 105600)                 игра Steam по номеру (steam://rungameid/...)
  ("cmd", "python")                 команда в новом окне консоли
  ("url", "https://...")            сайт, если больше ничего нет
Алиасы пиши основой слова: «террари» поймает «террария», «террарию».
"""
import re

VERBS = ("открой", "открыть", "запусти", "запустить")


def _norm(text):
    t = text.lower().replace("ё", "е")
    t = re.sub(r"[^\w\s+]", " ", t)
    return " ".join(t.split())


def P(title, aliases, *launch, show=None):
    return {"title": title, "kind": "программа", "aliases": aliases.split("|"),
            "launch": list(launch), "show": show}


def G(title, aliases, *launch, show=None):
    return {"title": title, "kind": "игра", "aliases": aliases.split("|"),
            "launch": list(launch), "show": show}


APPS = [
    # ── музыка и общение ──
    P("Spotify", "спотифай|спотик|spotify",
      ("lnk", "spotify"), ("exe", r"%APPDATA%\Spotify\Spotify.exe"), ("proto", "spotify")),
    P("Яндекс Музыка", "яндекс музык|yandex music",
      ("lnk", "яндекс музыка|yandex music"), ("url", "https://music.yandex.ru"),
      show="яндекс музыка, yandex music"),
    P("Discord", "дискорд|discord", ("lnk", "discord"), ("proto", "discord")),
    P("Telegram", "телеграм|телега|telegram",
      ("lnk", "telegram"), ("exe", r"%APPDATA%\Telegram Desktop\Telegram.exe"), ("proto", "tg")),
    P("WhatsApp", "ватсап|вацап|вотсап|whatsapp", ("lnk", "whatsapp"), ("proto", "whatsapp")),
    P("Viber", "вайбер|viber", ("lnk", "viber"), ("exe", r"%LOCALAPPDATA%\Viber\Viber.exe")),
    P("Zoom", "зум|zoom", ("lnk", "zoom"), ("exe", r"%APPDATA%\Zoom\bin\Zoom.exe")),
    P("Skype", "скайп|skype", ("lnk", "skype"), ("proto", "skype")),
    P("Microsoft Teams", "тимс|teams", ("lnk", "microsoft teams|teams"), ("proto", "msteams")),

    # ── браузеры ──
    P("Google Chrome", "гугл хром|хром|chrome",
      ("lnk", "google chrome"),
      ("exe", r"%ProgramFiles%\Google\Chrome\Application\chrome.exe|"
              r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe|"
              r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")),
    P("Microsoft Edge", "эдж|edge|майкрософт эдж", ("lnk", "microsoft edge"), ("proto", "microsoft-edge")),
    P("Firefox", "файрфокс|фаерфокс|мозилла|firefox", ("lnk", "firefox")),
    P("Opera", "опера|опера гх|opera gx|opera", ("lnk", "opera gx|opera")),
    P("Яндекс Браузер", "яндекс браузер|яндекс|yandex",
      ("lnk", "yandex|яндекс"), ("exe", r"%LOCALAPPDATA%\Yandex\YandexBrowser\Application\browser.exe")),
    P("Brave", "брейв|brave", ("lnk", "brave")),

    # ── разработка ──
    P("Python", "питон|пайтон|python",
      ("lnk", "python|idle"), ("cmd", "python")),
    P("Python IDLE", "идл|idle", ("lnk", "idle")),
    P("VS Code", "вс код|вэ эс код|vs code|vscode|visual studio code|вижуал студио код",
      ("lnk", "visual studio code"), ("exe", r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe")),
    P("Visual Studio", "вижуал студио|visual studio", ("lnk", "visual studio")),
    P("PyCharm", "пайчарм|пичарм|pycharm", ("lnk", "pycharm")),
    P("Android Studio", "андроид студио|android studio", ("lnk", "android studio")),
    P("GitHub Desktop", "гитхаб|github desktop|github", ("lnk", "github desktop")),
    P("Docker", "докер|docker", ("lnk", "docker desktop|docker")),
    P("Postman", "постман|postman", ("lnk", "postman")),
    P("Unity Hub", "юнити|unity hub|unity", ("lnk", "unity hub")),
    P("Blender", "блендер|blender", ("lnk", "blender")),
    P("Командная строка", "командная строка|командную строку|cmd|консоль|терминал", ("cmd", "cmd")),
    P("PowerShell", "повершелл|павершелл|powershell", ("cmd", "powershell")),

    # ── эмуляторы и запуск игр ──
    P("BlueStacks", "блюстакс|блю стакс|блустакс|блю стэкс|bluestacks|blue stacks",
      ("lnk", "bluestacks"),
      ("exe", r"%ProgramFiles%\BlueStacks_nxt\HD-Player.exe|%ProgramFiles%\BlueStacks X\BlueStacks X.exe")),
    P("Steam", "стим|steam", ("lnk", "steam"), ("exe", r"%ProgramFiles(x86)%\Steam\steam.exe"), ("proto", "steam")),
    P("Epic Games", "эпик геймс|эпик|epic games|epic",
      ("lnk", "epic games launcher"), ("proto", "com.epicgames.launcher")),
    P("Battle.net", "батлнет|батл нет|battle net",
      ("lnk", "battle.net"), ("exe", r"%ProgramFiles(x86)%\Battle.net\Battle.net Launcher.exe")),
    P("EA app", "иэй апп|ea app|ориджин|origin", ("lnk", "ea app|ea|origin")),
    P("Ubisoft Connect", "юбисофт|ubisoft|юплей|uplay", ("lnk", "ubisoft connect|uplay")),
    P("Xbox", "иксбокс|хбокс|xbox", ("lnk", "xbox"), ("proto", "xbox")),
    P("GeForce Experience", "джифорс|geforce experience|geforce", ("lnk", "geforce experience|nvidia app")),

    # ── игры ──
    G("Minecraft", "майнкрафт|minecraft",
      ("lnk", "minecraft launcher|minecraft"),
      ("exe", r"%ProgramFiles(x86)%\Minecraft Launcher\MinecraftLauncher.exe|"
              r"%ProgramFiles%\Minecraft Launcher\MinecraftLauncher.exe"),
      ("proto", "minecraft")),
    G("Roblox", "роблокс|роблэкс|roblox",
      ("lnk", "roblox player|roblox"), ("url", "https://www.roblox.com/home")),
    G("Roblox Studio", "роблокс студио|roblox studio", ("lnk", "roblox studio")),
    G("Terraria", "террари|terraria", ("lnk", "terraria"), ("steam", 105600),
      show="террария, terraria"),
    G("Counter-Strike 2", "кс 2|кс2|кс го|ксго|контр страйк|counter strike|cs2|cs go|csgo",
      ("lnk", "counter-strike 2|counter-strike"), ("steam", 730)),
    G("Dota 2", "дота|доту|dota", ("lnk", "dota 2"), ("steam", 570)),
    G("GTA V", "гта 5|гта пять|гта|gta 5|gta v|gta", ("lnk", "grand theft auto v"), ("steam", 271590)),
    G("Among Us", "амонг ас|амонг|амогус|among us", ("lnk", "among us"), ("steam", 945360)),
    G("Rust", "раст|rust", ("steam", 252490)),
    G("PUBG", "пабг|pubg", ("steam", 578080)),
    G("Apex Legends", "апекс|apex", ("lnk", "apex legends"), ("steam", 1172470)),
    G("Stardew Valley", "стардью|stardew", ("lnk", "stardew valley"), ("steam", 413150)),
    G("Valheim", "вальхейм|valheim", ("steam", 892970)),
    G("Project Zomboid", "зомбоид|project zomboid", ("steam", 108600)),
    G("Lethal Company", "летал компани|lethal company", ("steam", 1966720)),
    G("Fall Guys", "фол гайс|fall guys", ("lnk", "fall guys"), ("steam", 1097150)),
    G("Warframe", "варфрейм|warframe", ("lnk", "warframe"), ("steam", 230410)),
    G("Cyberpunk 2077", "киберпанк|cyberpunk", ("lnk", "cyberpunk 2077"), ("steam", 1091500)),
    G("The Witcher 3", "ведьмак|witcher", ("lnk", "witcher 3"), ("steam", 292030)),
    G("Euro Truck Simulator 2", "евро трак|euro truck", ("lnk", "euro truck simulator 2"), ("steam", 227300)),
    G("Don't Starve Together", "донт старв|dont starve|don t starve", ("steam", 322330)),
    G("Hollow Knight", "холлоу найт|hollow knight", ("steam", 367520)),
    G("Subnautica", "сабнавтика|subnautica", ("steam", 264710)),
    G("Phasmophobia", "фазмофобия|phasmophobia", ("steam", 739630)),
    G("Dead by Daylight", "дбд|дед бай дейлайт|dead by daylight", ("steam", 381210)),
    G("Brawlhalla", "бравлхалла|brawlhalla", ("steam", 291550)),
    G("Left 4 Dead 2", "лефт фор дед|left 4 dead|l4d2", ("steam", 550)),
    G("Garry's Mod", "гаррис мод|гмод|garrys mod|gmod", ("steam", 4000)),
    G("Valorant", "валорант|valorant", ("lnk", "valorant|riot client")),
    G("League of Legends", "лига легенд|league of legends", ("lnk", "league of legends")),
    G("Genshin Impact", "геншин|genshin", ("lnk", "genshin impact|genshin")),
    G("Fortnite", "фортнайт|fortnite", ("lnk", "fortnite")),
    G("osu!", "осу|osu", ("lnk", "osu")),

    # ── обычные программы ──
    P("Блокнот", "блокнот|notepad", ("exe", r"%WINDIR%\System32\notepad.exe")),
    P("Notepad++", "ноутпад плюс плюс|нотпад плюс плюс|notepad++|notepad plus plus", ("lnk", "notepad++")),
    P("Калькулятор", "калькулятор|calculator", ("exe", r"%WINDIR%\System32\calc.exe")),
    P("Paint", "паинт|пейнт|paint", ("exe", r"%WINDIR%\System32\mspaint.exe")),
    P("Ножницы", "ножницы|snipping tool", ("exe", r"%WINDIR%\System32\SnippingTool.exe"), ("proto", "ms-screenclip")),
    P("Диспетчер задач", "диспетчер задач|task manager|taskmgr", ("exe", r"%WINDIR%\System32\Taskmgr.exe")),
    P("Панель управления", "панель управления|control panel", ("cmd", "control")),
    P("Параметры Windows", "параметры windows|параметры виндовс|настройки виндовс", ("proto", "ms-settings")),
    P("Word", "ворд|word", ("lnk", "word")),
    P("Excel", "эксель|ексель|excel", ("lnk", "excel")),
    P("PowerPoint", "повер поинт|павер поинт|powerpoint", ("lnk", "powerpoint")),
    P("Outlook", "аутлук|outlook", ("lnk", "outlook")),
    P("OBS Studio", "обс|obs studio|obs", ("lnk", "obs studio"),
      ("exe", r"%ProgramFiles%\obs-studio\bin\64bit\obs64.exe")),
    P("VLC", "влс|vlc", ("lnk", "vlc media player|vlc")),
    P("WinRAR", "винрар|winrar", ("lnk", "winrar")),
    P("7-Zip", "7 зип|seven zip|7zip|7 zip", ("lnk", "7-zip file manager|7-zip")),
    P("Photoshop", "фотошоп|photoshop", ("lnk", "photoshop")),
    P("Premiere Pro", "премьер|premiere", ("lnk", "premiere pro")),
    P("After Effects", "афтер эффектс|after effects", ("lnk", "after effects")),
    P("DaVinci Resolve", "давинчи|davinci", ("lnk", "davinci resolve")),
    P("Figma", "фигма|figma", ("lnk", "figma")),
    P("Notion", "ношн|notion", ("lnk", "notion")),
    P("Obsidian", "обсидиан|obsidian", ("lnk", "obsidian")),
    P("Wallpaper Engine", "валлпейпер энджин|wallpaper engine", ("lnk", "wallpaper engine"), ("steam", 431960)),
    P("qBittorrent", "кубит торрент|qbittorrent", ("lnk", "qbittorrent")),
    P("AnyDesk", "эни деск|anydesk", ("lnk", "anydesk")),
    P("TeamViewer", "тимвьювер|teamviewer", ("lnk", "teamviewer")),
    P("MSI Afterburner", "афтербернер|afterburner", ("lnk", "msi afterburner")),
    P("CCleaner", "сиклинер|ccleaner", ("lnk", "ccleaner")),
]


# ─── разбор фразы ──────────────────────────────────────────────

def _build_index():
    pairs = []
    for app in APPS:
        for alias in app["aliases"]:
            a = _norm(alias)
            if a:
                # основа слова + до трёх букв окончания: «террари» ловит «террарию»
                rx = re.compile(r"(?<!\w)" + re.escape(a) + r"\w{0,3}(?!\w)")
                pairs.append((len(a), rx, app))
    pairs.sort(key=lambda p: -p[0])          # длинные фразы первыми: «roblox studio» раньше «roblox»
    return pairs


_INDEX = _build_index()
_VERB_RX = re.compile(r"(?<!\w)(?:" + "|".join(VERBS) + r")(?!\w)")


def find_app(text):
    """«открой спотифай», «запусти майнкрафт» -> запись из APPS или None.
    Без слова «открой»/«запусти» ничего не находит."""
    t = _norm(text)
    m = _VERB_RX.search(t)
    if not m:
        return None
    rest = t[m.end():]
    for _n, rx, app in _INDEX:
        if rx.search(rest):
            return app
    return None


def list_apps():
    """Для блока на странице «Команды»: [(фраза, название, тип)], игры и программы по алфавиту."""
    rows = []
    for app in APPS:
        if app["show"]:
            shown = app["show"]
        else:                                  # первое русское и первое английское название
            ru = next((a for a in app["aliases"] if re.search("[а-я]", a)), None)
            en = next((a for a in app["aliases"] if not re.search("[а-я]", a)), None)
            shown = ", ".join(x for x in (ru, en) if x)
        rows.append((f"открой {shown}", app["title"], app["kind"]))
    rows.sort(key=lambda r: (r[2] != "программа", r[1].lower()))
    return rows
