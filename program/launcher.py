# -*- coding: utf-8 -*-
"""Активатор Jarvis AZ. Его запускает START_JARVIS.bat, руками открывать не нужно.

Что делает:
  1. проверяет, какие нужные библиотеки уже есть в вашем Python, а каких нет;
  2. ставит ТОЛЬКО недостающие и пишет, сколько КБ каждая заняла;
  3. скачивает русскую модель Vosk, если её нет (один раз);
  4. запускает 11.py.

Тяжёлые необязательные библиотеки ставятся только если они нужны по настройкам:
  opencv-python и mediapipe  только если включены жесты;
  pyttsx3                    только если включён голосовой ответ.
Если всё уже на месте, запуск занимает пару секунд.
Ключ --no-launch: проверить и доустановить, но программу не запускать.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, ".setup_state.json")
SETTINGS_FILE = os.path.join(HERE, "script", "settings.json")

MODEL_NAME = "vosk-model-small-ru-0.22"
MODEL_URL = "https://alphacephei.com/vosk/models/" + MODEL_NAME + ".zip"
MODEL_RETRY_AFTER = 24 * 3600        # после неудачной загрузки повторяем не чаще раза в сутки

QT5 = "PyQt5==5.15.11"
# Запасные способы для капризных пакетов (пробуются по очереди после обычного)
FALLBACKS = {
    "playsound==1.2.2": [["--no-build-isolation", "playsound==1.2.2"], ["playsound==1.3.0"]],
}


def say(text=""):
    print(text, flush=True)


for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(errors="replace")
    except Exception:
        pass


def fmt_kb(n_bytes):
    """12 345 КБ (с пробелом между тысячами)."""
    return f"{round(n_bytes / 1024):,}".replace(",", " ") + " КБ"


# ─── состояние между запусками ─────────────────────────────────

def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_state():
    return load_json(STATE_FILE)


def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ─── проверка системы ──────────────────────────────────────────

def is_legacy_windows():
    """Windows 7 / 8 / 8.1: там работает только Qt 5 (PyQt5)."""
    try:
        return sys.getwindowsversion().major < 10
    except Exception:
        return False


def check_environment():
    """Возвращает True, если можно продолжать. Остальное только предупреждения."""
    if os.name != "nt":
        say("Jarvis AZ работает только в Windows.")
        return False
    v = sys.version_info
    if v < (3, 9):
        say(f"Python {v.major}.{v.minor} слишком старый. Нужен Python 3.11 (python.org).")
        return False
    if v >= (3, 13):
        say(f"! Python {v.major}.{v.minor} очень новый: часть библиотек (pyaudio, mediapipe) может не поставиться.")
        say("  Надёжнее всего Python 3.11. Если будут ошибки, поставьте его с python.org.")
    if sys.maxsize <= 2 ** 32:
        say("! У вас 32-разрядный Python. Современный Qt (PySide6) на нём не работает.")
    tmp = os.path.normcase(os.path.realpath(tempfile.gettempdir()))
    here = os.path.normcase(os.path.realpath(HERE))
    if here.startswith(tmp + os.sep):
        say("Похоже, архив не распакован: Jarvis запущен прямо из архива.")
        say("Закройте это окно, распакуйте всю папку (правая кнопка → Извлечь всё) и запустите заново.")
        return False
    return True


# ─── что нужно поставить ───────────────────────────────────────

def wanted_extras(settings):
    """Какие необязательные группы нужны по настройкам (по умолчанию как в программе)."""
    engines = settings.get("recognition_engines")
    return {
        "vosk": True if not isinstance(engines, list) else any(str(e).startswith("vosk") for e in engines),
        "tts": bool(settings.get("voice_reply")),
        "gestures": bool(settings.get("gestures_enabled")),
    }


def package_list(legacy, settings):
    """[{'label', 'mods' (достаточно любого), 'attempts', 'required', 'why'}] только то, что нужно."""
    def req(pip_name, mod, why):
        return {"label": pip_name.split("==")[0], "mods": [mod], "required": True, "why": why,
                "attempts": [[pip_name]] + FALLBACKS.get(pip_name, [])}

    def opt(pip_name, mod, why):
        d = req(pip_name, mod, why)
        d["required"] = False
        return d

    qt = {"label": "Qt (окно программы)", "required": True, "why": "интерфейс",
          "mods": ["PyQt5"] if legacy else ["PySide6", "PyQt5"],
          "attempts": [[QT5]] if legacy else [["PySide6"], [QT5]]}
    items = [qt,
             req("numpy", "numpy", "анимация"),
             req("psutil", "psutil", "нагрузка CPU и памяти"),
             req("SpeechRecognition", "speech_recognition", "микрофон"),
             req("pyaudio", "pyaudio", "микрофон"),
             req("playsound==1.2.2", "playsound", "звуки"),
             opt("comtypes", "comtypes", "громкость звука"),
             opt("pycaw", "pycaw", "громкость звука")]
    extras = wanted_extras(settings)
    if extras["vosk"]:
        items.append(opt("vosk", "vosk", "распознавание речи без интернета"))
    if extras["tts"]:
        items.append(opt("pyttsx3", "pyttsx3", "голосовой ответ"))
    if extras["gestures"]:
        items.append(opt("opencv-python", "cv2", "жесты камерой"))
        items.append(opt("mediapipe", "mediapipe", "жесты камерой"))
    return items


# ─── проверка и установка ──────────────────────────────────────

def missing_modules(py, modules):
    """Какие из modules не найдены в Python py."""
    code = ("import importlib.util as u, json, sys; "
            "print(json.dumps([m for m in sys.argv[1:] if u.find_spec(m) is None]))")
    try:
        out = subprocess.check_output([py, "-c", code] + list(modules), stderr=subprocess.DEVNULL)
        return json.loads(out.decode("utf-8", "replace").strip().splitlines()[-1])
    except Exception:
        return list(modules)


_SIZE_CODE = r'''
import json, sys
import importlib.metadata as md
known = json.loads(sys.stdin.read())          # None: нужны только имена, размеры не считаем
known = None if known is None else set(known)
names, new = [], {}
for d in md.distributions():
    try:
        name = (d.metadata["Name"] or "").lower().replace("_", "-")
    except Exception:
        continue
    if not name:
        continue
    names.append(name)
    if known is None or name in known:
        continue
    size = 0
    for f in (d.files or []):
        try:
            size += d.locate_file(f).stat().st_size
        except Exception:
            pass
    new[name] = [d.version, size]
print(json.dumps({"all": sorted(set(names)), "new": new}))
'''


def snapshot(py, known):
    """Все установленные пакеты; для тех, которых нет в known, ещё версия и размер в байтах."""
    try:
        out = subprocess.run([py, "-c", _SIZE_CODE], input=json.dumps(None if known is None else sorted(known)).encode(),
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True).stdout
        data = json.loads(out.decode("utf-8", "replace").strip().splitlines()[-1])
        return set(data["all"]), data["new"]
    except Exception:
        return set(known or []), {}


def need_user_install():
    """Python стоит в защищённую папку (Program Files): ставим в профиль пользователя (--user)."""
    if sys.prefix != getattr(sys, "base_prefix", sys.prefix):      # внутри venv прав хватает
        return False
    try:
        import sysconfig
        return not os.access(sysconfig.get_paths()["purelib"], os.W_OK)
    except Exception:
        return False


def pip(py, args):
    """pip сам рисует полосу загрузки (МБ и скорость). True, если установка удалась."""
    cmd = [py, "-m", "pip", "install", "--disable-pip-version-check", "--no-input"]
    if need_user_install():
        cmd.append("--user")
    try:
        return subprocess.call(cmd + list(args)) == 0
    except OSError:
        return False


def ensure_pip(py):
    try:
        if subprocess.call([py, "-m", "pip", "--version"], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL) == 0:
            return True
        subprocess.call([py, "-m", "ensurepip", "--upgrade"], stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)
        return subprocess.call([py, "-m", "pip", "--version"], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL) == 0
    except OSError:
        return False


def internet_ok():
    try:
        urllib.request.urlopen("https://pypi.org/", timeout=6).close()
        return True
    except Exception:
        return False


def install_item(py, item):
    """Пробует способы установки по очереди. True, если один сработал."""
    for args in item["attempts"]:
        if pip(py, args):
            return True
    return False


def report_installed(new):
    """Печатает, что именно появилось и сколько КБ заняло. Возвращает сумму в байтах."""
    total = 0
    for name, (version, size) in sorted(new.items()):
        total += size
        say(f"      + {name} {version}: {fmt_kb(size)}")
    return total


def ensure_packages(py, items):
    """Проверяет библиотеки, ставит недостающие. Возвращает (не удалось обязательных, не удалось необязательных)."""
    missing = set(missing_modules(py, sorted({m for it in items for m in it["mods"]})))
    absent = [it for it in items if all(m in missing for m in it["mods"])]

    say("Проверяю библиотеки:")
    for it in items:
        mark = "✗ нет   " if it in absent else "✓ есть  "
        say(f"  {mark} {it['label']}  ({it['why']})")
    if not absent:
        say("Всё нужное уже установлено, ничего ставить не надо.")
        return [], []

    say()
    say(f"Не хватает: {len(absent)}. Ставлю только их (нужен интернет).")
    if not ensure_pip(py):
        say("! В этом Python нет pip. Переустановите Python 3.11 с python.org (галочка pip и Add to PATH).")
        return [it["label"] for it in absent if it["required"]], [it["label"] for it in absent if not it["required"]]
    if any(it["label"] == "playsound" for it in absent):
        pip(py, ["--upgrade", "setuptools", "wheel"])          # старый setuptools не собирает playsound

    known, _ = snapshot(py, None)
    total = 0
    bad_required, bad_optional = [], []
    for i, it in enumerate(absent, 1):
        say()
        say(f"[{i}/{len(absent)}] {it['label']} — {it['why']}")
        if install_item(py, it):
            known, new = snapshot(py, known)
            got = report_installed(new)
            total += got
            say(f"  ✓ готово, установлено {fmt_kb(got)}")
        else:
            say(f"  ✗ {it['label']} не поставился.")
            (bad_required if it["required"] else bad_optional).append(it)
    say()
    say(f"Итого установлено: {fmt_kb(total)} ({total / 1048576:.1f} МБ).")

    if bad_required or bad_optional:
        if not internet_ok():
            say("Похоже, нет интернета или его блокирует антивирус/прокси. Проверьте соединение и запустите ещё раз.")
        if any(it["label"] == "pyaudio" for it in bad_required):
            say("Для pyaudio обычно нужен Python 3.11 (64-разрядный): у него есть готовая сборка.")
    return [it["label"] for it in bad_required], bad_optional


# ─── модель Vosk ───────────────────────────────────────────────

def _is_model_dir(path):
    return os.path.isdir(os.path.join(path, "am")) or os.path.isdir(os.path.join(path, "conf"))


def have_ru_model():
    """Та же логика, что в 11.py: папка vosk-model*-ru* рядом с программой."""
    try:
        names = sorted(os.listdir(HERE))
    except OSError:
        return False
    for name in names:
        path = os.path.join(HERE, name)
        low = name.lower()
        if not os.path.isdir(path) or not low.startswith("vosk-model") or "-ru" not in low:
            continue
        if _is_model_dir(path):
            return True
        try:
            if any(os.path.isdir(os.path.join(path, s)) and _is_model_dir(os.path.join(path, s))
                   for s in os.listdir(path)):
                return True
        except OSError:
            pass
    return False


def vosk_ru_wanted():
    """Нужна ли русская модель: по умолчанию да, если пользователь сам не выключил Vosk RU."""
    engines = load_json(SETTINGS_FILE).get("recognition_engines")
    if isinstance(engines, list):
        return "vosk_ru" in engines or "vosk" in engines
    return True


def download(url, dest, progress=True, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "JarvisAZ-launcher"})
    with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as out:
        total = int(r.headers.get("Content-Length") or 0)
        done, last = 0, -1
        while True:
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if progress and total:
                pct = done * 100 // total
                if pct // 5 != last // 5:
                    last = pct
                    print(f"\r  скачано {pct}%  ({fmt_kb(done)} из {fmt_kb(total)})", end="", flush=True)
        if progress:
            print()
    return done


def install_model(url=MODEL_URL, name=MODEL_NAME):
    """Скачивает и распаковывает модель рядом с 11.py. Возвращает True при успехе."""
    tmp_zip = os.path.join(HERE, "model.download")
    tmp_dir = os.path.join(HERE, "model.unpack")
    try:
        download(url, tmp_zip)
        shutil.rmtree(tmp_dir, ignore_errors=True)
        with zipfile.ZipFile(tmp_zip) as z:
            z.extractall(tmp_dir)
        inner = os.path.join(tmp_dir, name)
        if not os.path.isdir(inner):                 # на случай другой упаковки
            subs = [d for d in os.listdir(tmp_dir) if os.path.isdir(os.path.join(tmp_dir, d))]
            inner = os.path.join(tmp_dir, subs[0]) if subs else ""
        if not inner or not _is_model_dir(inner):
            return False
        target = os.path.join(HERE, name)
        shutil.rmtree(target, ignore_errors=True)
        shutil.move(inner, target)
        return True
    except Exception as e:
        say(f"  не получилось: {e}")
        return False
    finally:
        try:
            os.remove(tmp_zip)
        except OSError:
            pass
        shutil.rmtree(tmp_dir, ignore_errors=True)


def ensure_model(state):
    if have_ru_model() or not vosk_ru_wanted():
        return
    if "vosk" in state.get("optional_failed", []):       # без библиотеки vosk модель всё равно бесполезна
        return
    if time.time() - state.get("model_failed_at", 0) < MODEL_RETRY_AFTER:
        return
    say()
    say("Скачиваю русскую модель распознавания речи Vosk (один раз)...")
    if install_model():
        state.pop("model_failed_at", None)
        say("  Модель готова.")
    else:
        state["model_failed_at"] = time.time()
        say("  ! Модель не скачалась. Без неё работает движок Google (нужен интернет):")
        say("    Настройки → Звук и голос → включите «Google, русский».")
        say("    Или скачайте модель вручную (см. ИНСТРУКЦИЯ.txt, раздел «Vosk»). Повторная попытка будет завтра.")
    save_state(state)


# ─── запуск ────────────────────────────────────────────────────

def main(argv):
    say("=" * 56)
    say("   JARVIS AZ")
    say("=" * 56)
    if not check_environment():
        return 1

    py = sys.executable
    state = load_state()
    settings = load_json(SETTINGS_FILE)
    items = package_list(is_legacy_windows(), settings)

    failed, failed_optional = ensure_packages(py, items)
    if failed:
        say()
        say("Не удалось установить: " + ", ".join(failed))
        say("Что делать: проверьте интернет, поставьте Python 3.11 (64-bit) с python.org и запустите START_JARVIS.bat ещё раз.")
        say("Если опять не выйдет, пришлите этот текст целиком.")
        return 1
    if failed_optional:
        why = {it["label"]: it["why"] for it in failed_optional}
        say("Без этого Jarvis работает, просто без возможности: " + "; ".join(sorted(set(why.values()))) + ".")
        state["optional_failed"] = sorted(set(state.get("optional_failed", [])) |
                                          {m for it in failed_optional for m in it["mods"]})
        save_state(state)

    ensure_model(state)

    if "--no-launch" in argv:
        say("Всё готово.")
        return 0

    say()
    say("Запускаю Jarvis...")
    say()
    os.chdir(HERE)
    rc = subprocess.call([py, "11.py"])
    if rc != 0:
        say()
        say(f"Jarvis завершился с ошибкой (код {rc}). Текст ошибки выше.")
        say("Подробности: папка program\\logs. Решения частых проблем: ИНСТРУКЦИЯ.txt.")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
