"""Жесты рукой: открытая ладонь как сигнал и буква М в воздухе.

Модуль разделён на две части:
  * логика (определение пальцев, распознавание буквы, автомат состояний) —
    чистый Python, без камеры, тестируется отдельно;
  * камера (OpenCV + MediaPipe) — импортируется только когда жесты включены,
    поэтому программа работает и без них.

Состояния для светодиода:
  off    — жесты выключены или камера недоступна
  ready  — камера работает, ждёт открытую ладонь (красный)
  armed  — ладонь распознана, ждёт жест «М» (зелёный)
"""
import math
import threading
import time

# Точки MediaPipe Hands: кончики и средние суставы пальцев, запястье.
WRIST = 0
FINGERS = {"index": (8, 6), "middle": (12, 10), "ring": (16, 14), "pinky": (20, 18)}

ARM_TIMEOUT = 5.0        # сек: сколько ждать жеста после открытой ладони
DRAW_END_GAP = 0.5       # сек без указательного пальца — рисование закончено
MIN_PATH_POINTS = 12     # меньше точек — это не буква
MIN_PATH_SIZE = 0.04     # меньше 4% кадра по ширине или высоте — слишком мало
M_THRESHOLD = 0.2        # чем меньше, тем строже совпадение с буквой М

# Эталон буквы М в экранных координатах (y растёт вниз), от 0 до 1.
M_TEMPLATE = [(0.0, 1.0), (0.0, 0.0), (0.5, 0.6), (1.0, 0.0), (1.0, 1.0)]


# ─── определение пальцев ───────────────────────────────────────

def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def finger_extended(lm, name):
    """Палец вытянут, если кончик дальше от запястья, чем средний сустав.
    Не зависит от поворота руки, в отличие от сравнения по вертикали."""
    tip, pip = FINGERS[name]
    wrist = lm[WRIST]
    return _dist(lm[tip], wrist) > _dist(lm[pip], wrist) * 1.1


def is_open_palm(lm):
    return all(finger_extended(lm, f) for f in FINGERS)


def is_index_only(lm):
    """Вытянут только указательный: им рисуют букву."""
    if not finger_extended(lm, "index"):
        return False
    return not any(finger_extended(lm, f) for f in ("middle", "ring", "pinky"))


# ─── распознавание буквы М ─────────────────────────────────────

def _path_length(points):
    return sum(_dist(points[i], points[i + 1]) for i in range(len(points) - 1))


def resample(points, n=40):
    """Равномерно раскладывает точки пути по длине, чтобы скорость руки не важна."""
    if len(points) < 2:
        return list(points) * n
    total = _path_length(points)
    if total == 0:
        return [points[0]] * n
    step = total / (n - 1)
    out = [points[0]]
    acc = 0.0
    src = list(points)
    i = 0
    while len(out) < n and i < len(src) - 1:
        a, b = src[i], src[i + 1]
        seg = _dist(a, b)
        if acc + seg >= step and seg > 0:
            t = (step - acc) / seg
            p = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            out.append(p)
            src[i] = p            # продолжаем от новой точки
            acc = 0.0
        else:
            acc += seg
            i += 1
    while len(out) < n:
        out.append(src[-1])
    return out[:n]


def normalize(points):
    """Сдвигает в левый верхний угол и растягивает до единичного квадрата."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x0, y0 = min(xs), min(ys)
    w = max(xs) - x0 or 1e-6
    h = max(ys) - y0 or 1e-6
    return [((x - x0) / w, (y - y0) / h) for x, y in points]


def shape_distance(path, template=M_TEMPLATE, n=40):
    a = normalize(resample(path, n))
    b = normalize(resample(template, n))
    return sum(_dist(p, q) for p, q in zip(a, b)) / n


def is_letter_m(path):
    if len(path) < MIN_PATH_POINTS:
        return False
    xs = [p[0] for p in path]
    ys = [p[1] for p in path]
    if max(xs) - min(xs) < MIN_PATH_SIZE or max(ys) - min(ys) < MIN_PATH_SIZE:
        return False
    d = min(shape_distance(path), shape_distance(list(reversed(path))))
    return d < M_THRESHOLD


# ─── автомат состояний ─────────────────────────────────────────

class GestureMachine:
    READY, ARMED, DRAWING = "ready", "armed", "drawing"

    def __init__(self, arm_timeout=ARM_TIMEOUT, draw_end_gap=DRAW_END_GAP):
        self.arm_timeout = arm_timeout
        self.draw_end_gap = draw_end_gap
        self.state = self.READY
        self._armed_at = 0.0
        self._last_draw = 0.0
        self._path = []

    def update(self, lm, now):
        """lm — 21 точка руки (x, y) или None, если руки нет в кадре.
        Возвращает список событий: 'armed', 'ready', ('gesture', 'M')."""
        events = []

        if self.state == self.READY:
            if lm is not None and is_open_palm(lm):
                self.state = self.ARMED
                self._armed_at = now
                events.append("armed")

        elif self.state == self.ARMED:
            if now - self._armed_at > self.arm_timeout:
                self.state = self.READY
                events.append("ready")
            elif lm is not None and is_index_only(lm):
                self.state = self.DRAWING
                self._path = [lm[8]]
                self._last_draw = now

        elif self.state == self.DRAWING:
            if lm is not None and is_index_only(lm):
                self._last_draw = now
                last = self._path[-1]
                tip = lm[8]
                if _dist(last, tip) > 0.002:      # отсекаем дрожание на месте
                    self._path.append(tip)
            elif now - self._last_draw > self.draw_end_gap:
                if is_letter_m(self._path):
                    events.append(("gesture", "M"))
                self._path = []
                self.state = self.READY
                events.append("ready")

        return events


# ─── камера ────────────────────────────────────────────────────

class GestureEngine:
    """Работает в отдельном потоке. Состояние читается из главного окна по таймеру."""

    def __init__(self, camera_index=0):
        self.camera_index = camera_index
        self.state = "off"
        self.error = ""
        self._events = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self.state = "off"

    def pop_events(self):
        with self._lock:
            ev, self._events = self._events, []
        return ev

    def _push(self, event):
        with self._lock:
            self._events.append(event)

    def _run(self):
        try:
            import cv2
            import mediapipe as mp
        except Exception as e:
            self.state = "off"
            self.error = f"Не установлены OpenCV или MediaPipe: {e}"
            return

        try:
            hands = mp.solutions.hands.Hands(max_num_hands=1,
                                             min_detection_confidence=0.6,
                                             min_tracking_confidence=0.5)
        except Exception as e:
            self.state = "off"
            self.error = f"MediaPipe не запустился: {e}"
            return

        cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            self.state = "off"
            self.error = "Камера не найдена или занята другой программой"
            hands.close()
            return

        machine = GestureMachine()
        self.state = "ready"
        self.error = ""
        try:
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.05)
                    continue
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                res = hands.process(rgb)
                lm = None
                if res.multi_hand_landmarks:
                    lm = [(p.x, p.y) for p in res.multi_hand_landmarks[0].landmark]
                for ev in machine.update(lm, time.monotonic()):
                    if isinstance(ev, tuple):       # ('gesture', 'M') — для главного окна
                        self._push(ev)
                # светодиод: зелёный, пока ждём жест или рисуем
                self.state = "ready" if machine.state == GestureMachine.READY else "armed"
        finally:
            cap.release()
            hands.close()
            self.state = "off"
