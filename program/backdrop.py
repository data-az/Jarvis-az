"""Фон окна: настройки и геометрия. Без Qt, поэтому тестируется отдельно.

Режимы:
  full        — картинка на всё окно
  except_menu — картинка справа от левого меню, меню остаётся сплошным
  none        — фон выключен (по умолчанию)
Флаг top: картинка идёт под верхней полосой (True) или полоса остаётся сплошной (False).
"""
import os

MODES = ("full", "except_menu", "none")
DEFAULT_BG = {
    "name": "",
    "image": "",          # путь внутри папки программы, например script/backgrounds/x.jpg
    "mode": "none",
    "dim": 60,            # 0 — без затемнения, 90 — почти чёрный
    "top": True,
    "offset": [0, 0],     # сдвиг картинки относительно центра, px
    "scale": 1.0,         # 1.0 — картинка заполняет область
}


def normalize_bg(data):
    """Приводит словарь из settings.json к безопасным значениям."""
    out = dict(DEFAULT_BG)
    if isinstance(data, dict):
        out.update({k: v for k, v in data.items() if k in DEFAULT_BG})
    out["name"] = str(out["name"])[:60]
    out["image"] = str(out["image"] or "")
    out["mode"] = out["mode"] if out["mode"] in MODES else "none"
    try:
        out["dim"] = max(0, min(90, int(out["dim"])))
    except (TypeError, ValueError):
        out["dim"] = DEFAULT_BG["dim"]
    out["top"] = bool(out["top"])
    try:
        scale = float(out["scale"])
    except (TypeError, ValueError):
        scale = 1.0
    out["scale"] = max(1.0, min(4.0, scale))
    try:
        ox, oy = out["offset"]
        out["offset"] = [int(ox), int(oy)]
    except (TypeError, ValueError):
        out["offset"] = [0, 0]
    return out


def paint_area(mode, win_w, win_h, sidebar_w, top_h, top_covered):
    """Прямоугольник (x, y, w, h), куда рисуется фон, или None, если фона нет."""
    if mode == "none":
        return None
    if mode == "full":
        x, w = 0, win_w
    else:  # except_menu
        x, w = sidebar_w, win_w - sidebar_w
    if top_covered:
        y, h = 0, win_h
    else:
        y, h = top_h, win_h - top_h
    return (x, y, max(0, w), max(0, h))


def cover_size(img_w, img_h, area_w, area_h, scale):
    """Размер картинки: минимум, чтобы закрыть область, умноженный на масштаб."""
    if img_w <= 0 or img_h <= 0 or area_w <= 0 or area_h <= 0:
        return (0, 0)
    k = max(area_w / img_w, area_h / img_h) * scale
    return (round(img_w * k), round(img_h * k))


def clamp_offset(offset, img_w, img_h, area_w, area_h):
    """Сдвиг не даёт картинке уйти так, чтобы в области появился пустой край."""
    ox, oy = offset
    max_x = max(0, (img_w - area_w) // 2)
    max_y = max(0, (img_h - area_h) // 2)
    return [max(-max_x, min(max_x, ox)), max(-max_y, min(max_y, oy))]


def image_rect(img_w, img_h, area, scale, offset):
    """Где рисовать картинку внутри области: (x, y, w, h), уже с учётом сдвига и зажима."""
    ax, ay, aw, ah = area
    w, h = cover_size(img_w, img_h, aw, ah, scale)
    ox, oy = clamp_offset(offset, w, h, aw, ah)
    x = ax + (aw - w) // 2 + ox
    y = ay + (ah - h) // 2 + oy
    return (x, y, w, h)


def scale_on_wheel(scale, wheel_steps):
    """Колёсико: шаг 10% от текущего масштаба, ограничен 1.0–4.0."""
    return max(1.0, min(4.0, scale * (1.1 ** wheel_steps)))


def saved_bg_path(script_folder, filename):
    return os.path.join(script_folder, "backgrounds", os.path.basename(filename))
