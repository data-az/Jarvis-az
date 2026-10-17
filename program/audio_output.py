import threading
import os
import random
from playsound import playsound

SOUND_FOLDER = "sounds"

TRIGGER_SOUNDS = {
    "кастом": "yes.wav,y3.wav",
    "привет": "hi.wav,hi2.wav",
    "браузер": "browser_open.mp3,poj.wav,yes.wav,z.wav,zap.wav",
    "brave": "browser_open.mp3,poj.wav,yes.wav,z.wav,zap.wav",
    "tf2": "poj.wav,team.mp3,y3.wav,yes.wav,z.wav,zap.wav",
    "тим фортрес": "poj.wav,team.mp3,y3.wav,yes.wav,z.wav,zap.wav",
    "стоп": "yes.wav,off.wav",
    "выход": "off.wav,yes.wav",
    "команда добавлена": "autosb.wav,command_added.mp3,new.wav,pozd.wav,prin.wav,zap.wav",
    "фон изменён": "now.wav,obraz.wav,obraz2.wav,pozd.wav,prin.wav,zap.wav",
    "очистка": "dio.wav,dio2.wav,poj.wav,y3.wav,yes.wav,z.wav",
    "youtube": "yt.mp3,z.wav,zap.wav,y3.wav,yes.wav",
    "ютуб": "yt.wav,z.wav,zap.wav,y3.wav,yes.wav",
    "поиск": "poj.wav,z.wav,zap.wav,yes.wav",
    "проводник": "yes.wav,y3.wav",
    # 👇 ТВОИ ЗВУКИ (ДОБАВЛЯЙ СВОИ)
    "wo": "ik.mp3",
    "med": "med.mp3",
    # "моя_команда": "мой_звук.mp3",
}

_play_queues = {}

def get_next_file(trigger_word):
    files = []
    trigger_word_lower = trigger_word.lower()

    for key, value in TRIGGER_SOUNDS.items():
        if key in trigger_word_lower:
            files = [f.strip() for f in value.split(",")]
            break

    if not files:
        files = [f.strip() for f in TRIGGER_SOUNDS.get("кастом", "yes.wav").split(",")]

    if not files:
        return None

    existing = [f for f in files if os.path.exists(os.path.join(SOUND_FOLDER, f))]
    files = existing or files          # не выбираем файлы, которых нет на диске

    if len(files) == 1:
        return files[0]

    if trigger_word not in _play_queues:
        _play_queues[trigger_word] = files.copy()
        random.shuffle(_play_queues[trigger_word])

    next_file = _play_queues[trigger_word].pop(0)

    if not _play_queues[trigger_word]:
        _play_queues[trigger_word] = files.copy()
        random.shuffle(_play_queues[trigger_word])

    return next_file

def play_sound_file(file_path):
    if os.path.exists(file_path):
        try:
            playsound(file_path)
        except Exception as e:
            print(f"[ЗВУК] Ошибка: {e}")
    else:
        print(f"[ЗВУК] Файл не найден: {file_path}")

def play_notification(trigger_word):
    file_name = get_next_file(trigger_word)
    if not file_name:
        return

    file_path = os.path.join(SOUND_FOLDER, file_name)
    sound_thread = threading.Thread(target=play_sound_file, args=(file_path,), daemon=True)
    sound_thread.start()
    print(f"[ЗВУК] {trigger_word} → {file_name}")

def play_trigger(trigger_word):
    trigger_word_lower = trigger_word.lower()

    if trigger_word_lower in TRIGGER_SOUNDS:
        play_notification(trigger_word_lower)
        return True

    for key in TRIGGER_SOUNDS.keys():
        if key in trigger_word_lower:
            play_notification(key)
            return True

    print(f"[ЗВУК] Триггер не найден, используем кастом: {trigger_word}")
    play_notification("кастом")
    return True

def reset_queues():
    global _play_queues
    _play_queues = {}
    print("[ЗВУК] Очереди сброшены")

def get_all_triggers():
    return list(TRIGGER_SOUNDS.keys())
