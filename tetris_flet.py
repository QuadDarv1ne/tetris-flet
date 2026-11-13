"""
Tetris — кроссплатформенная игра на Python + Flet (v2: мультиплеер + музыка).

Возможности:
  РЕЖИМЫ:
    • 1P  Marathon      — классическая одиночная игра
    • 2P  Co-op         — два игрока на одном экране, каждый считает свой счёт
    • 2P  Battle        — бой: за 2+ линии противник получает garbage lines
  ГЕЙМПЛЕЙ:
    • 7 классических тетромино, 4 поворота (wall-kick)
    • 7-bag рандомизатор
    • Hold piece (C / Shift), очередь из 3 следующих, ghost piece
    • Hard drop (Пробел), soft drop (↓)
    • Система очков, уровни, ускорение, T-spin-дружественная фиксация
  АУДИО (аутентичные звуки Тетриса):
    • Фоновая музыка — "Коробейники" (классическая тема), зацикленная
    • SFX: move, rotate, lock, hard_drop, line_clear, tetris (4 линии),
      level_up, hold, game_over
    • Кнопки mute (звук) / mute (музыка), регулятор громкости
  ПРОЧЕЕ:
    • Сохранение рекорда и настроек
    • Адаптивный layout + экранные кнопки для мобильных
    • Диалог настроек, пауза, рестарт

Управление:
  Игрок 1 (синие кантролы):  A/D — движение, W — поворот, S — мягкое падение,
                              Space — hard drop, Q — hold
  Игрок 2 (оранжевые) в 2P:  ←/→ — движение, ↑ — поворот, ↓ — мягкое,
                              Enter — hard drop, RightShift — hold
  Общее:                      P — пауза, R — рестарт, M — муз. вкл/выкл,
                              N — звук вкл/выкл, Esc — выход

Запуск:
  python tetris_flet.py
  flet run tetris_flet.py        # горячая перезагрузка
  flet run tetris_flet.py -w     # веб-версия

Аудио-ассеты лежат в ./assets/audio/. Если их нет — игра запустится без звука.
"""

from __future__ import annotations

import asyncio
import base64
import json
import math
import os
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import flet as ft
import flet.canvas as cv

try:
    import platform
    IS_WINDOWS = platform.system() == "Windows"
    if IS_WINDOWS:
        import ctypes
        import ctypes.wintypes
        _winmm = ctypes.windll.winmm
except ImportError:
    IS_WINDOWS = False
    _winmm = None

# ---------------------------------------------------------------------------
# Пути к аудио-ассетам. Ищем в нескольких местах, чтобы работало и при
# запуске из scripts/, и после копирования в download/ (где ассеты лежат
# рядом с tetris_flet.py в ./assets/audio/).
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent
_CANDIDATES = [
    ROOT / "assets" / "audio",          # рядом со скриптом
    ROOT.parent / "assets" / "audio",   # на уровень выше (dev layout)
    Path.cwd() / "assets" / "audio",    # из текущей директории
]
ASSETS_DIR = next((p for p in _CANDIDATES if p.exists()), _CANDIDATES[0])

# ---------------------------------------------------------------------------
# Параметры игрового поля
# ---------------------------------------------------------------------------

COLS = 10
ROWS = 20
CELL = 28

FIELD_W = COLS * CELL
FIELD_H = ROWS * CELL

BG_COLOR = "#0f1117"
GRID_COLOR = "#1c2030"
PANEL_BG = "#151825"
ACCENT_P1 = "#22d3ee"
ACCENT_P2 = "#fb923c"
GARBAGE_COLOR = "#52525b"

# ---------------------------------------------------------------------------
# Фигуры (тетромино) — 4 поворота, координаты в сетке 4x4
# ---------------------------------------------------------------------------

SHAPES = {
    "I": [
        [(0, 1), (1, 1), (2, 1), (3, 1)],
        [(2, 0), (2, 1), (2, 2), (2, 3)],
        [(0, 2), (1, 2), (2, 2), (3, 2)],
        [(1, 0), (1, 1), (1, 2), (1, 3)],
    ],
    "O": [
        [(1, 0), (2, 0), (1, 1), (2, 1)],
        [(1, 0), (2, 0), (1, 1), (2, 1)],
        [(1, 0), (2, 0), (1, 1), (2, 1)],
        [(1, 0), (2, 0), (1, 1), (2, 1)],
    ],
    "T": [
        [(0, 1), (1, 1), (2, 1), (1, 0)],
        [(1, 0), (1, 1), (1, 2), (2, 1)],
        [(0, 1), (1, 1), (2, 1), (1, 2)],
        [(1, 0), (1, 1), (1, 2), (0, 1)],
    ],
    "S": [
        [(1, 0), (2, 0), (0, 1), (1, 1)],
        [(1, 0), (1, 1), (2, 1), (2, 2)],
        [(1, 1), (2, 1), (0, 2), (1, 2)],
        [(0, 0), (0, 1), (1, 1), (1, 2)],
    ],
    "Z": [
        [(0, 0), (1, 0), (1, 1), (2, 1)],
        [(2, 0), (1, 1), (2, 1), (1, 2)],
        [(0, 1), (1, 1), (1, 2), (2, 2)],
        [(1, 0), (0, 1), (1, 1), (0, 2)],
    ],
    "J": [
        [(0, 0), (0, 1), (1, 1), (2, 1)],
        [(1, 0), (2, 0), (1, 1), (1, 2)],
        [(0, 1), (1, 1), (2, 1), (2, 2)],
        [(1, 0), (1, 1), (0, 2), (1, 2)],
    ],
    "L": [
        [(2, 0), (0, 1), (1, 1), (2, 1)],
        [(1, 0), (1, 1), (1, 2), (2, 2)],
        [(0, 1), (1, 1), (2, 1), (0, 2)],
        [(0, 0), (1, 0), (1, 1), (1, 2)],
    ],
}

SHAPE_COLORS = {
    "I": "#22d3ee",
    "O": "#facc15",
    "T": "#a855f7",
    "S": "#22c55e",
    "Z": "#ef4444",
    "J": "#3b82f6",
    "L": "#f97316",
}

SHAPE_KINDS = list(SHAPES.keys())


# ---------------------------------------------------------------------------
# Настройки и рекорд
# ---------------------------------------------------------------------------

@dataclass
class Settings:
    sound: bool = True
    music: bool = True
    ghost: bool = True
    start_level: int = 1
    volume: float = 0.7
    player_name: str = "Player1"
    last_mode: str = "1P"

    @classmethod
    def load(cls):
        try:
            data = json.loads(cls._path().read_text(encoding="utf-8"))
            start_level = int(data.get("start_level", 1))
            volume = float(data.get("volume", 0.7))
            if not math.isfinite(volume):
                volume = 0.7
            player_name = data.get("player_name", "Player1")
            if not isinstance(player_name, str):
                player_name = "Player1"
            player_name = player_name.strip() or "Player1"
            return cls(
                sound=bool(data.get("sound", True)),
                music=bool(data.get("music", True)),
                ghost=bool(data.get("ghost", True)),
                start_level=max(1, min(15, start_level)),
                volume=max(0.0, min(1.0, volume)),
                player_name=player_name[:14],
                last_mode=str(data.get("last_mode", "1P")),
            )
        except Exception:
            return cls()

    def save(self):
        try:
            self._path().write_text(json.dumps({
                "sound": self.sound, "music": self.music,
                "ghost": self.ghost, "start_level": self.start_level,
                "volume": self.volume,
                "player_name": self.player_name,
                "last_mode": self.last_mode,
            }), encoding="utf-8")
        except Exception:
            pass

    @staticmethod
    def _path():
        return Path.home() / ".tetris_flet.json"


def load_high_score():
    try:
        p = Path.home() / ".tetris_flet_score.json"
        return int(json.loads(p.read_text(encoding="utf-8")).get("high", 0))
    except Exception:
        return 0


def save_high_score(value):
    try:
        (Path.home() / ".tetris_flet_score.json").write_text(
            json.dumps({"high": int(value)}), encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Таблица рекордов (топ-10) с разделением по режимам
# ---------------------------------------------------------------------------

LEADERBOARD_PATH = Path.home() / ".tetris_flet_leaderboard.json"


def _normalize_leaderboard_entry(entry):
    if not isinstance(entry, dict):
        return None
    if not all(key in entry for key in ("score", "lines", "level", "time")):
        return None
    try:
        score = int(entry.get("score", 0))
        lines = int(entry.get("lines", 0))
        level = int(entry.get("level", 1))
        elapsed = float(entry.get("time", 0))
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(elapsed) or elapsed < 0:
        return None

    name = entry.get("name", "?")
    if not isinstance(name, str):
        name = "?"
    normalized = dict(entry)
    normalized.update({
        "name": name.strip()[:14] or "?",
        "score": max(0, score),
        "lines": max(0, lines),
        "level": max(1, level),
        "time": elapsed,
    })
    if "tspin" in entry:
        try:
            normalized["tspin"] = max(0, int(entry["tspin"]))
        except (TypeError, ValueError, OverflowError):
            normalized["tspin"] = 0
    return normalized


def load_leaderboard():
    """Возвращает dict: {mode: [{"name": str, "score": int,
    "lines": int, "level": int, "time": float}, ...]}."""
    try:
        data = json.loads(LEADERBOARD_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            boards = {}
            for mode, entries in data.items():
                if not isinstance(mode, str) or not isinstance(entries, list):
                    continue
                valid_entries = []
                for entry in entries:
                    normalized = _normalize_leaderboard_entry(entry)
                    if normalized is not None:
                        valid_entries.append(normalized)
                boards[mode] = valid_entries
            return boards
    except Exception:
        pass
    return {}


def add_to_leaderboard(mode: str, entry: dict, max_entries: int = 10):
    """Добавляет запись в таблицу рекордов режима mode.
    entry: {name, score, lines, level, time}.
    Сортировка: по убыванию score (для Sprint — по возрастанию time)."""
    boards = load_leaderboard()
    lst = boards.get(mode, [])
    lst.append(entry)
    if mode == "SPRINT":
        # Sprint: чем меньше время — тем лучше
        lst.sort(key=lambda e: e.get("time", 9999))
    else:
        lst.sort(key=lambda e: e.get("score", 0), reverse=True)
    boards[mode] = lst[:max_entries]
    try:
        LEADERBOARD_PATH.write_text(json.dumps(boards), encoding="utf-8")
    except Exception:
        pass
    return boards[mode]


def get_leaderboard(mode: str):
    return load_leaderboard().get(mode, [])


def _fmt_time(t):
    """Форматирует секунды в mm:ss.ss для таблицы рекордов."""
    try:
        t = float(t)
    except (TypeError, ValueError):
        return "—"
    m = int(t // 60)
    s = t - m * 60
    return f"{m:02d}:{s:05.2f}"


# ---------------------------------------------------------------------------
# Аудио-менеджер: музыка (loop) + SFX через flet_audio
# ---------------------------------------------------------------------------

SFX_FILES = {
    "move": "sfx_move.wav",
    "rotate": "sfx_rotate.wav",
    "lock": "sfx_lock.wav",
    "hard_drop": "sfx_hard_drop.wav",
    "line_clear": "sfx_line_clear.wav",
    "tetris": "sfx_tetris.wav",
    "level_up": "sfx_level_up.wav",
    "hold": "sfx_hold.wav",
    "game_over": "sfx_game_over.wav",
    "garbage": "sfx_lock.wav",  # повторно используем lock
}

# Музыка: приоритет — официальный MP3, fallback — синтезированный WAV.
MUSIC_WAV = "music_korobeiniki.wav"


# ── MCI-обёртка для Windows ───────────────────────────────────────────
if IS_WINDOWS and _winmm:
    _buf = ctypes.create_unicode_buffer(256)

    def _mci_cmd(cmd: str) -> int:
        """Выполнить MCI-команду, вернуть код ошибки (0 = ok)."""
        return _winmm.mciSendStringW(cmd, _buf, 255, 0)
else:
    _mci_cmd = None


class AudioManager:
    """Управляет фоновой музыкой (зацикленной) и короткими SFX.
    На Windows использует нативный MCI (winmm) — работает без flet_audio.
    На других платформах — отключается."""

    def __init__(self, page: ft.Page, settings: Settings):
        self.page = page
        self.settings = settings
        self._music_handle: Optional[str] = None  # alias: 'm' или 'm_wav'
        self._sfx_handles: dict = {}
        self._music_loaded = False
        self._music_is_mp3 = False
        self.available = bool(IS_WINDOWS and _mci_cmd and ASSETS_DIR.exists())
        if not self.available:
            print("[audio] MCI недоступен или нет ассетов в", ASSETS_DIR)
            return

        # Открываем SFX-файлы (WAV)
        for name, fname in SFX_FILES.items():
            path = ASSETS_DIR / fname
            if path.exists():
                alias = f"sfx_{name}"
                try:
                    _mci_cmd(f'open "{path}" type waveaudio alias {alias}')
                    self._sfx_handles[name] = alias
                except Exception as e:
                    print(f"[audio] не удалось открыть {fname}: {e}")

        # Музыка: MP3 (repeat) → WAV (fallback)
        mp3_path = ASSETS_DIR / "music_korobeiniki.mp3"
        wav_path = ASSETS_DIR / MUSIC_WAV
        if mp3_path.exists():
            try:
                _mci_cmd(f'open "{mp3_path}" type mpegvideo alias m')
                self._music_handle = "m"
                self._music_is_mp3 = True
                self._music_loaded = True
                self.set_volume(settings.volume)
                print("[audio] музыка: официальный MP3 (MCI)")
            except Exception as e:
                print(f"[audio] MP3 не загрузился: {e}")
                self._load_music_wav(wav_path)
        elif wav_path.exists():
            self._load_music_wav(wav_path)

    def _load_music_wav(self, wav_path: Path):
        """Загрузить WAV-файл как fallback для музыки.
        WAV-драйвер MCI не поддерживает setaudio (winmm error 261)."""
        try:
            _mci_cmd(f'open "{wav_path}" type waveaudio alias m_wav')
            self._music_handle = "m_wav"
            self._music_is_mp3 = False
            self._music_loaded = True
            print("[audio] музыка: синтезированный WAV (MCI, громкость = макс)")
        except Exception as e:
            print(f"[audio] WAV не загрузился: {e}")

    def mount(self):
        """Ничего не требуется для MCI-бэкенда."""
        pass

    def start_music(self):
        if not self.available or not self._music_loaded:
            return
        if not self.settings.music:
            return
        try:
            _mci_cmd(f'play {self._music_handle} repeat')
        except Exception:
            pass

    def stop_music(self):
        if not self.available or not self._music_loaded:
            return
        try:
            _mci_cmd(f'pause {self._music_handle}')
        except Exception:
            pass

    def toggle_music(self, on: bool):
        if on:
            self.start_music()
        else:
            self.stop_music()

    def play_sfx(self, name: str):
        if not self.available or not self.settings.sound:
            return
        alias = self._sfx_handles.get(name)
        if not alias:
            return
        try:
            # from 0 — перезапуск эффекта с начала; waveaudio не даёт менять громкость
            _mci_cmd(f'play {alias} from 0')
        except Exception:
            pass

    def set_volume(self, vol: float):
        """Громкость доступна только для MP3-плеера (MPEG-Video driver).
        Для WAV-эффектов winmm setaudio не поддерживает (error 261)."""
        if not self.available or not self._music_handle:
            return
        try:
            _mci_cmd(f'setaudio {self._music_handle} volume to {int(vol * 600)}')
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 7-bag рандомизатор
# ---------------------------------------------------------------------------

class Bag:
    def __init__(self):
        self._queue: List[str] = []
        self._refill()
        self._refill()

    def _refill(self):
        bag = SHAPE_KINDS[:]
        random.shuffle(bag)
        self._queue.extend(bag)

    def take(self):
        if len(self._queue) <= 7:
            self._refill()
        return self._queue.pop(0)

    def peek(self, n):
        while len(self._queue) < n:
            self._refill()
        return self._queue[:n]


# ---------------------------------------------------------------------------
# Игровая логика одного игрока
# ---------------------------------------------------------------------------

class PlayerGame:
    """Полная игровая логика одного игрока. В режиме Battle умеет принимать
    garbage lines от противника и отправлять их при очистке 2+ линий."""

    def __init__(self, settings: Settings, audio: AudioManager,
                 high_score: int = 0, name: str = "P1",
                 accent: str = ACCENT_P1, mode: str = "1P",
                 sprint_target: int = 40, ultra_duration: int = 120):
        self.settings = settings
        self.audio = audio
        self.high_score = high_score
        self.name = name
        self.accent = accent
        self.mode = mode                          # "1P", "2P_COOP", "2P_BATTLE", "SPRINT", "ULTRA"
        self.sprint_target = sprint_target       # линий для победы в Sprint
        self.ultra_duration = ultra_duration     # секунд в режиме Ultra
        self.bag = Bag()
        self.pending_garbage = 0
        self.start_time = None    # время старта (для Sprint/Ultra таймера)
        self.finish_time = None   # время завершения
        self._paused_at = None
        self._paused_duration = 0.0
        self._paused = False
        self.last_tspin = False
        self.last_sent_garbage = 0
        # статистика сессии
        self.stats = {
            "pieces": 0, "tspins": 0, "tetrises": 0,
            "combos": 0, "max_combo": 0, "b2b_max": 0,
            "single": 0, "double": 0, "triple": 0,
        }
        self.reset()

    def reset(self):
        self.board = [[None] * COLS for _ in range(ROWS)]
        self.score = 0
        self.lines = 0
        self.level = self.settings.start_level
        self.game_over = False
        self.hold_kind = None
        self.can_hold = True
        self.bag = Bag()
        self.current = None
        self.pending_garbage = 0
        self.start_time = None
        self.finish_time = None
        self._score_committed = False
        self._paused_at = None
        self._paused_duration = 0.0
        self._paused = False
        self.last_tspin = False
        self.tspin_count = 0
        self.last_sent_garbage = 0
        self._last_action_was_rotate = False
        # Combo / Back-to-Back
        self.combo = -1                # -1 = не было очисток подряд
        self.b2b = False               # был ли предыдущий клир Tetris/T-spin
        self.b2b_count = 0
        # индикатор для UI (последнее событие)
        self.last_combo_text = ""
        self.last_b2b_text = ""
        # сброс статистики сессии
        self.stats = {
            "pieces": 0, "tspins": 0, "tetrises": 0,
            "combos": 0, "max_combo": 0, "b2b_max": 0,
            "single": 0, "double": 0, "triple": 0,
        }
        self._spawn()
        # применить накопленный garbage сразу при старте (обычно 0)

    def start_timer(self):
        import time
        if self.start_time is None and not self.paused:
            self.start_time = time.time()

    def elapsed(self):
        import time
        if self.start_time is None:
            return 0.0
        end = self.finish_time if self.finish_time else time.time()
        paused = self._paused_duration
        if self.paused and self._paused_at is not None:
            paused += max(0.0, end - max(self._paused_at, self.start_time))
        return max(0.0, end - self.start_time - paused)

    def format_time(self):
        t = self.elapsed()
        m = int(t // 60)
        s = t - m * 60
        return f"{m:02d}:{s:05.2f}"

    # --- helpers ---------------------------------------------------------

    def _cells_of(self, kind, rotation, ox, oy):
        return [(ox + dx, oy + dy) for (dx, dy) in SHAPES[kind][rotation]]

    def _spawn(self, kind=None):
        if kind is None:
            kind = self.bag.take()
        self.current = {
            "kind": kind,
            "rotation": 0,
            "x": COLS // 2 - 2,
            "y": -1,
        }
        self.can_hold = True
        if self._collides(self.current):
            self.game_over = True
            self.audio.play_sfx("game_over")
            self._commit_high_score()

    def _collides(self, piece):
        cells = self._cells_of(piece["kind"], piece["rotation"],
                               piece["x"], piece["y"])
        for cx, cy in cells:
            if cx < 0 or cx >= COLS:
                return True
            if cy >= ROWS:
                return True
            if cy >= 0 and self.board[cy][cx] is not None:
                return True
        return False

    # --- действия ---------------------------------------------------------

    def move(self, dx, dy):
        if self.game_over or self.paused:
            return False
        new = dict(self.current)
        new["x"] += dx
        new["y"] += dy
        if not self._collides(new):
            self.current = new
            if dx != 0:
                self.audio.play_sfx("move")
            # движение сбрасывает флаг T-spin (последнее действие — не поворот)
            self._last_action_was_rotate = False
            return True
        return False

    @property
    def paused(self):
        return getattr(self, "_paused", False)

    @paused.setter
    def paused(self, v):
        import time
        value = bool(v)
        if value == self.paused:
            return
        if value:
            self._paused_at = time.time()
        elif self._paused_at is not None:
            if self.start_time is not None and self.finish_time is None:
                self._paused_duration += max(
                    0.0, time.time() - self._paused_at)
            self._paused_at = None
        self._paused = value

    def rotate(self):
        if self.game_over or self.paused:
            return False
        new = dict(self.current)
        new["rotation"] = (self.current["rotation"] + 1) % 4
        for kick in (0, -1, 1, -2, 2):
            test = dict(new)
            test["x"] += kick
            if not self._collides(test):
                self.current = test
                self.audio.play_sfx("rotate")
                # поворот — кандидат на T-spin
                self._last_action_was_rotate = True
                return True
        return False

    def hard_drop(self):
        if self.game_over or self.paused:
            return
        was_rotate = self._last_action_was_rotate
        dropped = 0
        while self.move(0, 1):
            dropped += 1
        self._last_action_was_rotate = was_rotate
        self.score += dropped * 2
        self.audio.play_sfx("hard_drop")
        # hard drop сохраняет флаг поворота (T-spin возможен после hard drop)
        self._lock_piece()

    def soft_drop(self):
        if self.game_over or self.paused:
            return
        if self.move(0, 1):
            self.score += 1
        else:
            self._lock_piece()

    def hold(self):
        if self.game_over or self.paused or not self.can_hold:
            return
        cur_kind = self.current["kind"]
        if self.hold_kind is None:
            self.hold_kind = cur_kind
            self._spawn()
        else:
            new_kind = self.hold_kind
            self.hold_kind = cur_kind
            self._spawn(new_kind)
        self.can_hold = False
        if self.game_over:
            return
        self.audio.play_sfx("hold")

    def step_down(self):
        if self.game_over or self.paused:
            return
        if not self.move(0, 1):
            self._lock_piece()

    def _lock_piece(self):
        kind = self.current["kind"]
        color = SHAPE_COLORS[kind]
        # T-spin определение: последнее действие — поворот, и ≥3 из 4
        # диагональных углов вокруг центра T-фигуры заняты.
        is_tspin = self._detect_tspin()
        self.last_tspin = is_tspin
        if is_tspin:
            self.tspin_count = getattr(self, "tspin_count", 0) + 1
            self.stats["tspins"] += 1
        self.stats["pieces"] += 1
        overflow = False
        for cx, cy in self._cells_of(self.current["kind"],
                                     self.current["rotation"],
                                     self.current["x"],
                                     self.current["y"]):
            if cy < 0:
                overflow = True
                continue
            if 0 <= cy < ROWS and 0 <= cx < COLS:
                self.board[cy][cx] = color
        cleared = self._clear_lines()
        # --- Combo и Back-to-Back (B2B) ---
        # B2B: подряд идущие Tetris или T-spin с очисткой линий
        is_difficult = (cleared == 4) or (is_tspin and cleared >= 1)
        combo_bonus = 0
        b2b_bonus = 0
        if cleared > 0:
            self.combo += 1
            if self.combo >= 1:
                # Combo: 50 * combo * level
                combo_bonus = 50 * self.combo * self.level
                self.score += combo_bonus
                self.stats["combos"] += 1
                self.stats["max_combo"] = max(self.stats["max_combo"],
                                              self.combo)
            if is_difficult:
                self.b2b_count = self.b2b_count + 1 if self.b2b else 1
                self.stats["b2b_max"] = max(self.stats["b2b_max"],
                                             self.b2b_count)
                if self.b2b:
                    # B2B бонус: +50% от базовых очков за этот клир
                    base_pts = {1: 100, 2: 300, 3: 500, 4: 800}
                    if is_tspin:
                        ts_points = {1: 800, 2: 1200, 3: 1600}
                        base_pts = ts_points
                    b2b_bonus = base_pts.get(cleared, 0) * self.level // 2
                    self.score += b2b_bonus
            else:
                self.b2b_count = 0
            self.b2b = is_difficult
        else:
            self.combo = -1   # сброс комбо
            # B2B сохраняется только при сложных клирах; пустой клир обрывает
            self.b2b = False
            self.b2b_count = 0
        # T-spin бонусы: T-spin Single/Double/Triple дают больше очков
        if is_tspin:
            if cleared == 0:
                # T-spin mini / без линий — небольшой бонус
                self.score += 400 * self.level
                self.audio.play_sfx("rotate")
            else:
                # T-spin с очисткой — большие очки
                ts_points = {1: 800, 2: 1200, 3: 1600}
                self.score += ts_points.get(cleared, 800) * self.level
                self.audio.play_sfx("tetris")  # звук как за тетрис
        if cleared > 0 and not is_tspin:
            if cleared == 4:
                self.audio.play_sfx("tetris")
                self.stats["tetrises"] += 1
            else:
                self.audio.play_sfx("line_clear")
                if cleared == 1: self.stats["single"] += 1
                elif cleared == 2: self.stats["double"] += 1
                elif cleared == 3: self.stats["triple"] += 1
        elif cleared == 0 and not is_tspin:
            self.audio.play_sfx("lock")
        if cleared > 0:
            before = self.level
            self.level = self.settings.start_level + self.lines // 10
            if self.level != before:
                self.audio.play_sfx("level_up")
        # текстовые индикаторы для UI
        self.last_combo_text = (f"COMBO ×{self.combo}"
                                if self.combo >= 1 else "")
        if b2b_bonus > 0:
            self.last_b2b_text = "B2B!"
        elif is_difficult:
            self.last_b2b_text = ""
        elif cleared == 0:
            self.last_b2b_text = ""
        # в режиме Battle: очистка 2+ линий отправляет garbage противнику
        # T-spin Double/Triple и B2B Tetris отправляют больше
        if is_tspin and cleared >= 1:
            base_garbage = max(2, cleared)
        else:
            base_garbage = max(0, cleared - 1) if cleared >= 2 else 0
        if b2b_bonus > 0 and base_garbage > 0:
            base_garbage += 1   # B2B добавляет +1 garbage
        self.last_sent_garbage += base_garbage
        # принять накопленный garbage
        if self.pending_garbage > 0 and not overflow:
            self._apply_garbage(self.pending_garbage)
            self.pending_garbage = 0
        sprint_victory = (
            self.mode == "SPRINT" and self.lines >= self.sprint_target
        )
        if sprint_victory:
            self.audio.play_sfx("level_up")
        if overflow:
            self.game_over = True
            self.audio.play_sfx("game_over")
            self._commit_high_score()
            return
        if sprint_victory:
            self._commit_high_score()
        # сбросить флаг последнего действия (после фиксации фигуры)
        self._last_action_was_rotate = False
        if not self.game_over:
            self._spawn()

    def _detect_tspin(self):
        """Определяет T-spin: последним действием был поворот, фигура — T,
        и хотя бы 3 из 4 диагональных углов вокруг её центра заняты."""
        if self.current["kind"] != "T":
            return False
        if not getattr(self, "_last_action_was_rotate", False):
            return False
        cx = self.current["x"] + 1  # центр T в локальных координатах (1,1)
        cy = self.current["y"] + 1
        # 4 диагональных угла вокруг центра
        corners = [(cx - 1, cy - 1), (cx + 1, cy - 1),
                   (cx - 1, cy + 1), (cx + 1, cy + 1)]
        filled = 0
        for ax, ay in corners:
            if ax < 0 or ax >= COLS or ay >= ROWS:
                filled += 1  # границы считаются занятыми
            elif ay >= 0 and self.board[ay][ax] is not None:
                filled += 1
        return filled >= 3

    def _clear_lines(self):
        new_board = []
        cleared = 0
        for row in self.board:
            if all(cell is not None for cell in row):
                cleared += 1
            else:
                new_board.append(row)
        for _ in range(cleared):
            new_board.insert(0, [None] * COLS)
        self.board = new_board
        self.lines += cleared
        points = {0: 0, 1: 100, 2: 300, 3: 500, 4: 800}
        self.score += points.get(cleared, 0) * self.level
        # Sprint: при достижении целевого числа линий — победа
        if (self.mode == "SPRINT" and cleared > 0
                and self.lines >= self.sprint_target
                and not self.game_over):
            import time
            self.game_over = True
            self.finish_time = time.time()
        return cleared

    def check_ultra_timeout(self):
        """В режиме Ultra завершает игру по истечении лимита времени."""
        if (self.mode == "ULTRA" and not self.game_over
                and self.start_time is not None and not self.paused):
            if self.elapsed() >= self.ultra_duration:
                self.game_over = True
                self.finish_time = (
                    self.start_time + self._paused_duration
                    + self.ultra_duration)
                self._commit_high_score()
                self.audio.play_sfx("level_up")

    def _apply_garbage(self, n_lines):
        """Добавляет n_lines строк garbage снизу, со случайной дырой."""
        for _ in range(n_lines):
            hole = random.randint(0, COLS - 1)
            row = [GARBAGE_COLOR if c != hole else None
                   for c in range(COLS)]
            # поднять поле
            if any(self.board[0][c] is not None for c in range(COLS)):
                # верхняя строка занята → game over
                self.game_over = True
                self.audio.play_sfx("game_over")
                self._commit_high_score()
                return
            self.board.pop(0)
            self.board.append(row)
        self.audio.play_sfx("garbage")

    def receive_garbage(self, n):
        self.pending_garbage += n

    def _commit_high_score(self):
        if self._score_committed:
            return
        self._score_committed = True
        if self.finish_time is None:
            import time
            self.finish_time = time.time()
        if self.score > self.high_score:
            self.high_score = self.score
            save_high_score(self.score)
        # добавить запись в таблицу рекордов режима
        entry = {
            "name": self.name,
            "score": self.score,
            "lines": self.lines,
            "level": self.level,
            "time": round(self.elapsed(), 2),
            "tspin": getattr(self, "tspin_count", 0),
        }
        if self.mode != "SPRINT" or self.lines >= self.sprint_target:
            try:
                add_to_leaderboard(self.mode, entry)
            except Exception:
                pass

    def ghost_cells(self):
        if not self.current or self.game_over:
            return []
        cur = dict(self.current)
        while True:
            cur["y"] += 1
            if self._collides(cur):
                cur["y"] -= 1
                break
        if cur["y"] == self.current["y"]:
            return []
        return self._cells_of(cur["kind"], cur["rotation"],
                               cur["x"], cur["y"])

    def next_queue(self, n=3):
        return self.bag.peek(n)


def resolve_battle_garbage(player1: PlayerGame, player2: PlayerGame):
    attack1 = player1.last_sent_garbage
    attack2 = player2.last_sent_garbage
    cancelled = min(attack1, attack2)
    player1.last_sent_garbage = 0
    player2.last_sent_garbage = 0
    if attack2 > cancelled:
        player1.receive_garbage(attack2 - cancelled)
    if attack1 > cancelled:
        player2.receive_garbage(attack1 - cancelled)


# ---------------------------------------------------------------------------
# Отрисовка
# ---------------------------------------------------------------------------

def hex_to_rgba(hex_color, alpha=1.0):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def lighten(hex_color, factor=0.5):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    r = int(r + (255 - r) * factor)
    g = int(g + (255 - g) * factor)
    b = int(b + (255 - b) * factor)
    return f"#{r:02x}{g:02x}{b:02x}"


def darken(hex_color, factor=0.4):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    r = int(r * (1 - factor))
    g = int(g * (1 - factor))
    b = int(b * (1 - factor))
    return f"#{r:02x}{g:02x}{b:02x}"


def _cell_at(x, y, color, cell=CELL, alpha=1.0, ghost=False):
    shapes = []
    fill_color = hex_to_rgba(color, alpha) if alpha < 1 else color
    shapes.append(cv.Rect(x, y, cell, cell,
                          paint=ft.Paint(color=fill_color,
                                         style=ft.PaintingStyle.FILL)))
    if ghost:
        shapes.append(cv.Rect(
            x + 1, y + 1, cell - 2, cell - 2,
            paint=ft.Paint(color=hex_to_rgba(color, 0.6), stroke_width=1,
                           style=ft.PaintingStyle.STROKE)
        ))
    else:
        light = lighten(color, 0.55)
        dark = darken(color, 0.45)
        shapes.append(cv.Line(x, y, x + cell, y,
                              paint=ft.Paint(color=light, stroke_width=2,
                                             style=ft.PaintingStyle.STROKE)))
        shapes.append(cv.Line(x, y, x, y + cell,
                              paint=ft.Paint(color=light, stroke_width=2,
                                             style=ft.PaintingStyle.STROKE)))
        shapes.append(cv.Line(x, y + cell, x + cell, y + cell,
                              paint=ft.Paint(color=dark, stroke_width=2,
                                             style=ft.PaintingStyle.STROKE)))
        shapes.append(cv.Line(x + cell, y, x + cell, y + cell,
                              paint=ft.Paint(color=dark, stroke_width=2,
                                             style=ft.PaintingStyle.STROKE)))
        shapes.append(cv.Rect(
            x + 3, y + 3, cell // 3, cell // 4,
            paint=ft.Paint(color=hex_to_rgba("#ffffff", 0.25),
                           style=ft.PaintingStyle.FILL)
        ))
    return shapes


def _flatten(lists):
    out = []
    for item in lists:
        if isinstance(item, list):
            out.extend(item)
        else:
            out.append(item)
    return out


def build_field_shapes(game: PlayerGame):
    shapes = [cv.Fill(ft.Paint(color=BG_COLOR))]
    grid_paint = ft.Paint(color=GRID_COLOR, stroke_width=1,
                          style=ft.PaintingStyle.STROKE)
    for i in range(COLS + 1):
        x = i * CELL
        shapes.append(cv.Line(x, 0, x, FIELD_H, paint=grid_paint))
    for j in range(ROWS + 1):
        y = j * CELL
        shapes.append(cv.Line(0, y, FIELD_W, y, paint=grid_paint))

    for row_idx, row in enumerate(game.board):
        for col_idx, cell in enumerate(row):
            if cell is not None:
                shapes.append(_cell_at(col_idx * CELL, row_idx * CELL, cell))

    if game.current and not game.game_over:
        if game.settings.ghost:
            color = SHAPE_COLORS[game.current["kind"]]
            for cx, cy in game.ghost_cells():
                if cy >= 0:
                    shapes.append(_cell_at(cx * CELL, cy * CELL, color,
                                           alpha=0.22, ghost=True))
        cur = game.current
        for cx, cy in game._cells_of(cur["kind"], cur["rotation"],
                                     cur["x"], cur["y"]):
            if cy >= 0:
                shapes.append(_cell_at(cx * CELL, cy * CELL,
                                       SHAPE_COLORS[cur["kind"]]))

    # индикатор накопленного garbage (полоска справа)
    if game.pending_garbage > 0:
        bar_h = min(game.pending_garbage * CELL, FIELD_H)
        shapes.append(cv.Rect(
            FIELD_W + 4, FIELD_H - bar_h, 6, bar_h,
            paint=ft.Paint(color="#ef4444", style=ft.PaintingStyle.FILL)
        ))
    return _flatten(shapes)


def build_piece_preview(kind, panel_w, panel_h, cell):
    shapes = [cv.Fill(ft.Paint(color="#0d1018"))]
    if kind is None:
        return shapes
    cells = SHAPES[kind][0]
    color = SHAPE_COLORS[kind]
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    w = (maxx - minx + 1)
    h = (maxy - miny + 1)
    offset_x = (panel_w - w * cell) // 2
    offset_y = (panel_h - h * cell) // 2
    for dx, dy in cells:
        x = offset_x + (dx - minx) * cell
        y = offset_y + (dy - miny) * cell
        shapes.append(_cell_at(x, y, color, cell=cell))
    return _flatten(shapes)


# ---------------------------------------------------------------------------
# UI: главное окно с режимами 1P / 2P Co-op / 2P Battle
# ---------------------------------------------------------------------------

MODE_1P = "1P"
MODE_2P_COOP = "2P_COOP"
MODE_2P_BATTLE = "2P_BATTLE"
MODE_SPRINT = "SPRINT"
MODE_ULTRA = "ULTRA"

SPRINT_TARGET = 40        # линий для победы в Sprint
ULTRA_DURATION = 120      # секунд в режиме Ultra

MODE_TITLES = {
    MODE_1P: "1 игрок — Marathon",
    MODE_2P_COOP: "2 игрока — Co-op",
    MODE_2P_BATTLE: "2 игрока — Battle",
    MODE_SPRINT: f"Sprint — {SPRINT_TARGET} линий на время",
    MODE_ULTRA: f"Ultra — {ULTRA_DURATION} сек на максимум очков",
}


def make_player_ui(game: PlayerGame, accent: str, compact: bool = False):
    """Создаёт виджеты одной игровой панели (поле + статистика + hold/next)."""
    score_t = ft.Text("0", size=20 if compact else 24,
                     weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE)
    lines_t = ft.Text("0", size=16, color=ft.Colors.CYAN_200)
    level_t = ft.Text(str(game.level), size=16, color=ft.Colors.CYAN_200)
    timer_t = ft.Text("00:00.00", size=18, weight=ft.FontWeight.BOLD,
                      color=ft.Colors.AMBER_300)
    tspin_t = ft.Text("", size=11, color=ft.Colors.PURPLE_300,
                      weight=ft.FontWeight.BOLD)
    combo_t = ft.Text("", size=11, color=ft.Colors.ORANGE_300,
                      weight=ft.FontWeight.BOLD)
    b2b_t = ft.Text("", size=11, color=ft.Colors.YELLOW_300,
                    weight=ft.FontWeight.BOLD)

    hold_w, hold_h = 84, 60
    hold_c = cv.Canvas(width=hold_w, height=hold_h,
                      shapes=build_piece_preview(game.hold_kind, hold_w,
                                                  hold_h, 12))
    next_w, next_h = 84, 46
    nexts = [cv.Canvas(width=next_w, height=next_h,
                      shapes=build_piece_preview(None, next_w, next_h, 11))
            for _ in range(3)]

    field_c = cv.Canvas(width=FIELD_W, height=FIELD_H,
                       shapes=build_field_shapes(game))
    field_box = ft.Container(content=field_c, bgcolor=BG_COLOR,
                             border_radius=6)

    ov_t = ft.Text("", size=22, weight=ft.FontWeight.BOLD,
                   color=ft.Colors.WHITE, text_align=ft.TextAlign.CENTER)
    ov_s = ft.Text("", size=12, color=ft.Colors.GREY_300,
                   text_align=ft.TextAlign.CENTER)
    overlay = ft.Container(
        content=ft.Column([ov_t, ov_s],
                          alignment=ft.MainAxisAlignment.CENTER,
                          horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        alignment=ft.Alignment.CENTER, visible=False,
        bgcolor=ft.Colors.with_opacity(0.78, "#000000"), expand=True,
    )
    field_stack = ft.Stack([field_box, overlay],
                           width=FIELD_W, height=FIELD_H)

    def card(title, value, color=ft.Colors.GREY_400):
        return ft.Container(
            padding=ft.Padding.symmetric(vertical=8, horizontal=10),
            bgcolor=PANEL_BG, border_radius=6,
            content=ft.Column([
                ft.Text(title, size=9, color=color),
                value,
            ], spacing=1),
        )

    name_t = ft.Text(game.name, size=13, weight=ft.FontWeight.BOLD,
                    color=accent)

    # В режиме Sprint показываем таймер и прогресс, иначе — счёт
    panel_items = [name_t]
    if game.mode == "SPRINT":
        panel_items.append(card("ВРЕМЯ", timer_t, ft.Colors.AMBER_300))
        progress = ft.ProgressBar(
            value=min(1.0, game.lines / max(game.sprint_target, 1)),
            color=accent, bgcolor="#1c2030", width=120)
        panel_items.append(card("ЛИНИИ %d/%d" % (
            game.lines, game.sprint_target), progress, ft.Colors.CYAN_200))
        panel_items.append(card("УРОВЕНЬ", level_t))
    elif game.mode == "ULTRA":
        # Ultra: таймер обратного отсчёта + счёт
        panel_items.append(card("ОСТАЛОСЬ", timer_t, ft.Colors.AMBER_300))
        panel_items.append(card("СЧЁТ", score_t, accent))
        remaining = max(0, game.ultra_duration - game.elapsed())
        progress = ft.ProgressBar(
            value=min(1.0, remaining / max(game.ultra_duration, 1)),
            color=accent, bgcolor="#1c2030", width=120)
        panel_items.append(card("ВРЕМЯ", progress, ft.Colors.CYAN_200))
        panel_items.append(card("ЛИНИИ", lines_t))
    else:
        panel_items.append(card("СЧЁТ", score_t, accent))
        panel_items.append(
            ft.Row([card("ЛИНИИ", lines_t), card("УРОВЕНЬ", level_t)],
                   spacing=6))
    panel_items.append(card("HOLD", hold_c))
    panel_items.append(card("СЛЕДУЮЩИЕ",
        ft.Column(nexts, spacing=2,
                  horizontal_alignment=ft.CrossAxisAlignment.CENTER)))
    # индикаторы T-spin / Combo / B2B в одну строку
    panel_items.append(ft.Row([tspin_t, combo_t, b2b_t], spacing=6,
                              alignment=ft.MainAxisAlignment.CENTER))

    panel = ft.Column(panel_items, spacing=5, width=140 if compact else 160,
       horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    widgets = {
        "score": score_t, "lines": lines_t, "level": level_t,
        "timer": timer_t, "tspin": tspin_t, "combo": combo_t, "b2b": b2b_t,
        "hold": hold_c, "nexts": nexts, "field": field_c,
        "overlay": overlay, "overlay_text": ov_t, "overlay_sub": ov_s,
    }
    return panel, field_stack, widgets, game


def update_player_ui(widgets: dict, game: PlayerGame):
    w = widgets
    w["score"].value = str(game.score)
    w["lines"].value = str(game.lines)
    w["level"].value = str(game.level)
    # таймер: для Ultra — обратный отсчёт, иначе — нарастающий
    if "timer" in w:
        if game.mode == "ULTRA":
            remaining = max(0, game.ultra_duration - game.elapsed())
            m = int(remaining // 60)
            s = remaining - m * 60
            w["timer"].value = f"{m:02d}:{s:05.2f}"
            # краснеет при < 10 сек
            w["timer"].color = (ft.Colors.RED_400 if remaining < 10
                                else ft.Colors.AMBER_300)
        else:
            w["timer"].value = game.format_time()
            w["timer"].color = ft.Colors.AMBER_300
    # индикатор T-spin
    if "tspin" in w:
        if getattr(game, "last_tspin", False):
            tspin_count = getattr(game, "tspin_count", 1)
            w["tspin"].value = f"T-SPIN ×{tspin_count}"
        else:
            w["tspin"].value = ""
    # индикатор Combo
    if "combo" in w:
        combo = getattr(game, "combo", -1)
        if combo >= 1:
            w["combo"].value = f"COMBO ×{combo}"
        else:
            w["combo"].value = ""
    # индикатор B2B
    if "b2b" in w:
        if getattr(game, "b2b", False):
            w["b2b"].value = "B2B!"
        else:
            w["b2b"].value = ""
    hold_w, hold_h = 84, 60
    w["hold"].shapes = build_piece_preview(game.hold_kind, hold_w, hold_h, 12)
    next_w, next_h = 84, 46
    nxt = game.next_queue(3)
    for i, c in enumerate(w["nexts"]):
        kind = nxt[i] if i < len(nxt) else None
        c.shapes = build_piece_preview(kind, next_w, next_h, 11)
    w["field"].shapes = build_field_shapes(game)
    if game.game_over:
        w["overlay"].visible = True
        # Sprint胜利 / Ultra время вышло / обычный game over
        if game.mode == "SPRINT" and game.lines >= game.sprint_target:
            w["overlay_text"].value = "ПОБЕДА!"
            w["overlay_sub"].value = (
                f"Время: {game.format_time()}  •  R — заново")
        elif game.mode == "ULTRA" and game.elapsed() >= game.ultra_duration:
            w["overlay_text"].value = "ВРЕМЯ ВЫШЛО!"
            w["overlay_sub"].value = (
                f"Счёт: {game.score}  •  R — заново")
        else:
            w["overlay_text"].value = "GAME OVER"
            w["overlay_sub"].value = "R — заново"
    elif game.paused:
        w["overlay"].visible = True
        w["overlay_text"].value = "ПАУЗА"
        w["overlay_sub"].value = "P — продолжить"
    else:
        w["overlay"].visible = False


# ---------------------------------------------------------------------------
# Управление для двух игроков
# ---------------------------------------------------------------------------

# Игрок 1: A/D движение, W поворот, S soft, Space hard drop, Q hold
# Игрок 2: ←/→ движение, ↑ поворот, ↓ soft, Enter hard drop, RightShift hold
P1_KEYS = {
    "left": "A", "right": "D", "rotate": "W",
    "soft": "S", "hard": "Space", "hold": "Q",
}
P2_KEYS = {
    "left": "Arrow Left", "right": "Arrow Right", "rotate": "Arrow Up",
    "soft": "Arrow Down", "hard": "Enter", "hold": "Shift",
}


def handle_player_key(game: PlayerGame, action: str):
    # запуск таймера при первом действии (для Sprint/Ultra)
    if (game.mode in ("SPRINT", "ULTRA") and not game.game_over
            and not game.paused and game.start_time is None):
        if action in ("left", "right", "rotate", "soft", "hard", "hold"):
            game.start_timer()
    if action == "left":
        game.move(-1, 0)
    elif action == "right":
        game.move(1, 0)
    elif action == "rotate":
        game.rotate()
    elif action == "soft":
        game.soft_drop()
    elif action == "hard":
        game.hard_drop()
    elif action == "hold":
        game.hold()


# ---------------------------------------------------------------------------
# Мобильные экранные кнопки
# ---------------------------------------------------------------------------

def make_touch_controls(game: PlayerGame, accent: str):
    def btn(icon, on_click, w=64):
        b = ft.Container(
            content=ft.Icon(icon, color=accent, size=22),
            width=w, height=48, bgcolor=PANEL_BG, border_radius=10,
            alignment=ft.Alignment.CENTER, ink=True,
        )
        b.on_click = on_click
        return b

    def act(fn):
        return lambda e: (fn(), )

    return ft.Column([
        ft.Row([
            btn(ft.Icons.ARROW_BACK, lambda e: game.move(-1, 0)),
            btn(ft.Icons.ROTATE_RIGHT, lambda e: game.rotate()),
            btn(ft.Icons.ARROW_DOWNWARD, lambda e: game.soft_drop()),
            btn(ft.Icons.ARROW_FORWARD, lambda e: game.move(1, 0)),
        ], alignment=ft.MainAxisAlignment.CENTER, spacing=8),
        ft.Row([
            btn(ft.Icons.SWAP_VERT, lambda e: game.hold(), w=90),
            btn(ft.Icons.ARROW_DROP_DOWN_CIRCLE,
                lambda e: game.hard_drop(), w=90),
        ], alignment=ft.MainAxisAlignment.CENTER, spacing=8),
    ], spacing=6)


# ---------------------------------------------------------------------------
# Главная функция
# ---------------------------------------------------------------------------

def main(page: ft.Page):
    page.title = "Tetris — Flet (Multiplayer + Music)"
    page.bgcolor = "#0a0b10"
    page.padding = ft.Padding.all(10)
    page.window.width = 1100
    page.window.height = 820
    page.window.resizable = True
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.CYAN)

    settings = Settings.load()
    audio = AudioManager(page, settings)
    high_score = load_high_score()

    # --- состояние приложения ---
    # последний выбранный режим восстанавливается из настроек
    initial_mode = settings.last_mode if settings.last_mode in MODE_TITLES else MODE_1P
    state = {
        "mode": initial_mode,
        "games": [],            # список PlayerGame
        "widgets": [],          # параллельный список widgets dict
        "panels": [],           # параллельный список (panel, field_stack)
        "running": False,
        "loop_task": None,
    }

    # --- верхняя панель ---
    mode_dd = ft.Dropdown(
        label="Режим",
        value=initial_mode,
        width=240,
        options=[
            ft.dropdown.Option(MODE_1P, MODE_TITLES[MODE_1P]),
            ft.dropdown.Option(MODE_2P_COOP, MODE_TITLES[MODE_2P_COOP]),
            ft.dropdown.Option(MODE_2P_BATTLE, MODE_TITLES[MODE_2P_BATTLE]),
            ft.dropdown.Option(MODE_SPRINT, MODE_TITLES[MODE_SPRINT]),
            ft.dropdown.Option(MODE_ULTRA, MODE_TITLES[MODE_ULTRA]),
        ],
    )

    high_t = ft.Text(str(high_score), size=16, color=ft.Colors.AMBER_300)
    sound_btn = ft.IconButton(
        ft.Icons.VOLUME_UP if settings.sound else ft.Icons.VOLUME_OFF,
        icon_color=ft.Colors.CYAN_300, tooltip="Звук (N)",
    )
    music_btn = ft.IconButton(
        ft.Icons.MUSIC_NOTE if settings.music else ft.Icons.MUSIC_OFF,
        icon_color=ft.Colors.AMBER_300, tooltip="Музыка (M)",
    )
    pause_btn = ft.IconButton(ft.Icons.PAUSE, icon_color=ft.Colors.AMBER_300,
                              tooltip="Пауза (P)")
    restart_btn = ft.IconButton(ft.Icons.REFRESH,
                                icon_color=ft.Colors.GREEN_300,
                                tooltip="Рестарт (R)")
    settings_btn = ft.IconButton(ft.Icons.SETTINGS,
                                 icon_color=ft.Colors.CYAN_300,
                                 tooltip="Настройки (Ctrl+S)")
    leaderboard_btn = ft.IconButton(ft.Icons.EMOJI_EVENTS,
                                    icon_color=ft.Colors.AMBER_400,
                                    tooltip="Таблица рекордов (L)")
    stats_btn = ft.IconButton(ft.Icons.ANALYTICS,
                              icon_color=ft.Colors.PURPLE_300,
                              tooltip="Статистика сессии (T)")

    top_bar = ft.Row([
        ft.Text("TETRIS", size=18, weight=ft.FontWeight.BOLD,
                color=ft.Colors.CYAN_300),
        mode_dd,
        ft.Container(
            padding=ft.Padding.symmetric(vertical=4, horizontal=10), bgcolor=PANEL_BG,
            border_radius=6,
            content=ft.Column([
                ft.Text("РЕКОРД", size=8, color=ft.Colors.GREY_400),
                high_t,
            ], spacing=0),
        ),
        ft.Container(expand=True),
        stats_btn,
        leaderboard_btn,
        sound_btn, music_btn, pause_btn, restart_btn, settings_btn,
    ], alignment=ft.MainAxisAlignment.START, spacing=6,
       vertical_alignment=ft.CrossAxisAlignment.CENTER)

    # --- контейнер игрового поля (пересоздаётся при смене режима) ---
    game_area = ft.Column([], spacing=8, scroll=ft.ScrollMode.AUTO)
    touch_area = ft.Column([], spacing=8)

    # --- диалог настроек ---
    sound_sw = ft.Switch(label="Звук", value=settings.sound)
    music_sw = ft.Switch(label="Музыка", value=settings.music)
    ghost_sw = ft.Switch(label="Призрак-тень", value=settings.ghost)
    vol_sl = ft.Slider(min=0, max=1, value=settings.volume,
                       label="Громкость {value:.0%}", width=200)
    level_dd = ft.Dropdown(
        label="Стартовый уровень", value=str(settings.start_level),
        options=[ft.dropdown.Option(str(i)) for i in range(1, 16)],
        width=180,
    )
    name_field = ft.TextField(
        label="Имя игрока", value=settings.player_name,
        width=260, max_length=14, text_size=13,
    )

    settings_dlg = ft.AlertDialog(
        modal=False, title=ft.Text("Настройки"),
        content=ft.Column([
            name_field,
            sound_sw, music_sw, ghost_sw, vol_sl, level_dd,
            ft.Text("Имя и стартовый уровень применятся при рестарте (R).",
                    size=11, color=ft.Colors.GREY_400),
        ], tight=True, spacing=10),
        actions=[
            ft.TextButton("Отмена", on_click=lambda e: close_settings()),
            ft.FilledButton("Сохранить", on_click=lambda e: save_settings_click()),
        ],
        open=False,
    )

    def save_settings_click(e=None):
        settings.sound = bool(sound_sw.value)
        settings.music = bool(music_sw.value)
        settings.ghost = bool(ghost_sw.value)
        settings.volume = float(vol_sl.value)
        settings.start_level = int(level_dd.value or 1)
        # имя игрока: убираем пустые, ограничиваем длину
        nm = (name_field.value or "").strip() or "Player1"
        settings.player_name = nm[:14]
        settings.save()
        audio.settings = settings
        audio.set_volume(settings.volume)
        audio.toggle_music(settings.music)
        refresh_icons()
        for g in state["games"]:
            g.paused = False
        settings_dlg.open = False
        refresh_all()

    def close_settings(e=None):
        settings_dlg.open = False
        for g in state["games"]:
            g.paused = False
        refresh_all()

    def open_settings(e=None):
        if state["games"]:
            for g in state["games"]:
                g.paused = True
        sound_sw.value = settings.sound
        music_sw.value = settings.music
        ghost_sw.value = settings.ghost
        vol_sl.value = settings.volume
        level_dd.value = str(settings.start_level)
        settings_dlg.open = True
        refresh_all()
        page.update()

    page.overlay.append(settings_dlg)

    # --- диалог таблицы рекордов ---
    leaderboard_dlg = ft.AlertDialog(
        modal=False, title=ft.Text("🏆 Таблица рекордов"),
        content=ft.Column([], tight=True, spacing=10, scroll=ft.ScrollMode.AUTO,
                          width=480, height=420),
        actions=[
            ft.TextButton("Закрыть", on_click=lambda e: close_leaderboard()),
        ],
        open=False,
    )

    def render_leaderboard():
        """Заполняет диалог таблицы рекордов данными для всех режимов."""
        cols = []
        for mode_key, mode_title in MODE_TITLES.items():
            entries = get_leaderboard(mode_key)
            rows = []
            # заголовок
            rows.append(ft.Row([
                ft.Text("#", size=11, weight=ft.FontWeight.BOLD,
                        color=ft.Colors.AMBER_300, width=24),
                ft.Text("Имя", size=11, weight=ft.FontWeight.BOLD,
                        color=ft.Colors.AMBER_300, expand=True),
                ft.Text("Счёт", size=11, weight=ft.FontWeight.BOLD,
                        color=ft.Colors.AMBER_300, width=70, text_align=ft.TextAlign.RIGHT),
                ft.Text("Линии", size=11, weight=ft.FontWeight.BOLD,
                        color=ft.Colors.AMBER_300, width=50, text_align=ft.TextAlign.RIGHT),
                ft.Text("Время", size=11, weight=ft.FontWeight.BOLD,
                        color=ft.Colors.AMBER_300, width=70, text_align=ft.TextAlign.RIGHT),
            ], spacing=4))
            if not entries:
                rows.append(ft.Text("— пока пусто —", size=11,
                                    color=ft.Colors.GREY_500, italic=True))
            for i, e in enumerate(entries[:10], 1):
                rank_color = ft.Colors.GREY_300
                if i == 1:
                    rank_color = ft.Colors.YELLOW_400
                elif i == 2:
                    rank_color = ft.Colors.GREY_200
                elif i == 3:
                    rank_color = ft.Colors.ORANGE_400
                rows.append(ft.Row([
                    ft.Text(str(i), size=11, color=rank_color, width=24),
                    ft.Text(e.get("name", "?"), size=11,
                            color=ft.Colors.WHITE, expand=True),
                    ft.Text(str(e.get("score", 0)), size=11,
                            color=ft.Colors.CYAN_200, width=70,
                            text_align=ft.TextAlign.RIGHT),
                    ft.Text(str(e.get("lines", 0)), size=11,
                            color=ft.Colors.GREY_300, width=50,
                            text_align=ft.TextAlign.RIGHT),
                    ft.Text(_fmt_time(e.get("time", 0)), size=11,
                            color=ft.Colors.AMBER_200, width=70,
                            text_align=ft.TextAlign.RIGHT),
                ], spacing=4))
            cols.append(ft.Column([
                ft.Text(mode_title, size=13, weight=ft.FontWeight.BOLD,
                        color=ft.Colors.CYAN_300),
                *rows,
            ], spacing=2))
        leaderboard_dlg.content.controls = cols

    def open_leaderboard(e=None):
        render_leaderboard()
        leaderboard_dlg.open = True
        page.update()

    def close_leaderboard(e=None):
        leaderboard_dlg.open = False
        page.update()

    page.overlay.append(leaderboard_dlg)
    leaderboard_btn.on_click = lambda e: open_leaderboard()

    # --- диалог статистики сессии (PNG-отчёт) ---
    stats_dlg = ft.AlertDialog(
        modal=False, title=ft.Text("Статистика сессии"),
        content=ft.Column([], tight=True, spacing=8,
                          scroll=ft.ScrollMode.AUTO,
                          width=520, height=460),
        actions=[
            ft.TextButton("Закрыть", on_click=lambda e: close_stats()),
        ],
        open=False,
    )
    # путь к сохранённому PNG (для показа)
    stats_image = ft.Image(src="", width=520, height=300, fit=ft.BoxFit.CONTAIN,
                           border_radius=6)
    stats_caption = ft.Text("", size=11, color=ft.Colors.GREY_400,
                            text_align=ft.TextAlign.CENTER)
    stats_dlg.content.controls = [stats_image, stats_caption]

    def open_stats(e=None):
        """Генерирует PNG-отчёт по последней завершённой игре и показывает его."""
        if not state["games"]:
            return
        # берём первую игру (для 2P — можно расширить)
        g = state["games"][0]
        try:
            # ленивый импорт, чтобы matplotlib не требовался при запуске
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "session_stats",
                str(Path(__file__).parent / "session_stats.py"))
            ss = importlib.util.module_from_spec(spec)
            import sys as _sys
            _sys.modules["session_stats"] = ss
            spec.loader.exec_module(ss)
        except Exception as ex:
            stats_caption.value = f"Ошибка генерации: {ex}"
            stats_image.src = ""
            stats_dlg.open = True
            page.update()
            return
        # временный файл для PNG
        out = Path.home() / ".tetris_session_stats.png"
        try:
            ss.render_session_stats(g, str(out))
            if out.exists():
                # base64 для встраивания
                import base64 as _b64
                data = out.read_bytes()
                b64 = _b64.b64encode(data).decode("ascii")
                stats_image.src = f"data:image/png;base64,{b64}"
                stats_caption.value = (
                    f"Игрок: {g.name}  •  Счёт: {g.score}  •  "
                    f"Линии: {g.lines}  •  Время: {g.format_time()}")
            else:
                stats_caption.value = "Не удалось создать отчёт"
        except Exception as ex:
            stats_caption.value = f"Ошибка: {ex}"
        stats_dlg.open = True
        page.update()

    def close_stats(e=None):
        stats_dlg.open = False
        page.update()

    page.overlay.append(stats_dlg)
    stats_btn.on_click = lambda e: open_stats()

    # --- пересоздание игровой сессии ---
    def start_new_session():
        mode = state["mode"]
        # сохраняем последний выбранный режим
        settings.last_mode = mode
        settings.save()
        pname = settings.player_name or "Player1"
        games = []
        widgets = []
        panels = []

        if mode == MODE_1P:
            g = PlayerGame(settings, audio, high_score, pname, ACCENT_P1,
                           mode=MODE_1P)
            games.append(g)
            p, fs, w, _ = make_player_ui(g, ACCENT_P1)
            panels.append((p, fs))
            widgets.append(w)
        elif mode == MODE_SPRINT:
            # Sprint: цель — 40 линий, таймер идёт с первого хода
            g = PlayerGame(settings, audio, high_score, pname, ACCENT_P1,
                           mode=MODE_SPRINT, sprint_target=SPRINT_TARGET)
            games.append(g)
            p, fs, w, _ = make_player_ui(g, ACCENT_P1)
            panels.append((p, fs))
            widgets.append(w)
        elif mode == MODE_ULTRA:
            # Ultra: 120 секунд на максимум очков
            g = PlayerGame(settings, audio, high_score, pname, ACCENT_P1,
                           mode=MODE_ULTRA, ultra_duration=ULTRA_DURATION)
            games.append(g)
            p, fs, w, _ = make_player_ui(g, ACCENT_P1)
            panels.append((p, fs))
            widgets.append(w)
        elif mode == MODE_2P_COOP:
            g1 = PlayerGame(settings, audio, high_score, "Игрок 1", ACCENT_P1,
                            mode=MODE_2P_COOP)
            g2 = PlayerGame(settings, audio, high_score, "Игрок 2", ACCENT_P2,
                            mode=MODE_2P_COOP)
            games.extend([g1, g2])
            for g, accent in [(g1, ACCENT_P1), (g2, ACCENT_P2)]:
                p, fs, w, _ = make_player_ui(g, accent, compact=True)
                panels.append((p, fs))
                widgets.append(w)
        elif mode == MODE_2P_BATTLE:
            g1 = PlayerGame(settings, audio, high_score, "Игрок 1", ACCENT_P1,
                            mode=MODE_2P_BATTLE)
            g2 = PlayerGame(settings, audio, high_score, "Игрок 2", ACCENT_P2,
                            mode=MODE_2P_BATTLE)
            games.extend([g1, g2])
            for g, accent in [(g1, ACCENT_P1), (g2, ACCENT_P2)]:
                p, fs, w, _ = make_player_ui(g, accent, compact=True)
                panels.append((p, fs))
                widgets.append(w)

        state["games"] = games
        state["widgets"] = widgets
        state["panels"] = panels

        # перерисовать game_area
        game_area.controls.clear()
        if mode in (MODE_1P, MODE_SPRINT, MODE_ULTRA):
            p, fs = panels[0]
            sprint_hint = ft.Text(
                "Очисти 40 линий как можно быстрее! Таймер идёт с первого хода.",
                size=12, color=ft.Colors.AMBER_300,
                visible=(mode == MODE_SPRINT))
            ultra_hint = ft.Text(
                f"Собери максимум очков за {ULTRA_DURATION} секунд! "
                "Таймер идёт с первого хода.",
                size=12, color=ft.Colors.AMBER_300,
                visible=(mode == MODE_ULTRA))
            game_area.controls.append(
                ft.Column([
                    sprint_hint,
                    ultra_hint,
                    ft.Row([p, ft.Container(content=fs, padding=4,
                                              bgcolor="#0a0b10",
                                              border_radius=10)],
                           alignment=ft.MainAxisAlignment.CENTER,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER,
                           spacing=12)
                ], spacing=6, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
            )
        else:
            rows = []
            for p, fs in panels:
                rows.append(
                    ft.Column([p, ft.Container(content=fs, padding=4,
                                                 bgcolor="#0a0b10",
                                                 border_radius=10)],
                              spacing=4,
                              horizontal_alignment=ft.CrossAxisAlignment.CENTER)
                )
            title = ft.Text(
                "BATTLE: очищай 2+ линии, чтобы забросать противника garbage!",
                size=12, color=ft.Colors.RED_300,
                visible=(mode == MODE_2P_BATTLE))
            game_area.controls.append(
                ft.Column([
                    title,
                    ft.Row(rows, alignment=ft.MainAxisAlignment.CENTER,
                            spacing=20,
                            vertical_alignment=ft.CrossAxisAlignment.START),
                ], spacing=6, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
            )

        # мобильные кнопки: только для 1P (для 2P клавиатура обязательна)
        touch_area.controls.clear()
        if mode == MODE_1P:
            touch_area.controls.append(
                make_touch_controls(games[0], ACCENT_P1))

        state["running"] = True
        refresh_all()
        page.update()
        # запустить музыку
        if settings.music:
            audio.start_music()

    def refresh_all():
        nonlocal high_score
        for g, w in zip(state["games"], state["widgets"]):
            update_player_ui(w, g)
        # обновить рекорд
        cur_max = max([g.score for g in state["games"]] + [0])
        high_score = max(
            [high_score] + [g.high_score for g in state["games"]])
        high_t.value = str(max(high_score, cur_max))
        try:
            page.update()
        except Exception:
            pass

    def refresh_icons():
        sound_btn.icon = (ft.Icons.VOLUME_UP if settings.sound
                          else ft.Icons.VOLUME_OFF)
        music_btn.icon = (ft.Icons.MUSIC_NOTE if settings.music
                          else ft.Icons.MUSIC_OFF)

    # --- обработчики кнопок ---
    def on_mode_change(e):
        state["mode"] = mode_dd.value
        start_new_session()

    def on_pause(e=None):
        any_paused = any(g.paused for g in state["games"])
        for g in state["games"]:
            if not g.game_over:
                g.paused = not any_paused
                if g.paused:
                    audio.stop_music()
                else:
                    if settings.music:
                        audio.start_music()
        refresh_all()

    def on_restart(e=None):
        start_new_session()

    def on_sound_toggle(e=None):
        settings.sound = not settings.sound
        settings.save()
        audio.settings = settings
        refresh_icons()
        page.update()

    def on_music_toggle(e=None):
        settings.music = not settings.music
        settings.save()
        audio.settings = settings
        audio.toggle_music(settings.music)
        refresh_icons()
        page.update()

    mode_dd.on_change = on_mode_change
    pause_btn.on_click = on_pause
    restart_btn.on_click = on_restart
    settings_btn.on_click = lambda e: open_settings()
    sound_btn.on_click = on_sound_toggle
    music_btn.on_click = on_music_toggle

    # --- клавиатура ---
    def on_key(e: ft.KeyboardEvent):
        key = e.key
        if key == "Escape":
            if stats_dlg.open:
                close_stats()
            elif leaderboard_dlg.open:
                close_leaderboard()
            elif settings_dlg.open:
                close_settings()
            else:
                page.window.close()
            return
        if settings_dlg.open or leaderboard_dlg.open or stats_dlg.open:
            return
        if key == "S" or key == "s":
            # S — это ещё и soft-drop P1; откроем настройки по Ctrl+S
            if e.ctrl:
                open_settings()
                return
        if key == "M" or key == "m":
            on_music_toggle()
            return
        if key == "N" or key == "n":
            on_sound_toggle()
            return
        if key == "P" or key == "p":
            on_pause()
            return
        if key == "R" or key == "r":
            on_restart()
            return
        if key == "L" or key == "l":
            open_leaderboard()
            return
        if key == "T" or key == "t":
            open_stats()
            return
        if not state["games"]:
            return

        # определяем, какому игроку адресован ключ
        # P1: A/D/W/S/Space/Q ; P2: стрелки/Enter/Shift
        # Замечание: 'S' для P1 обрабатывается ниже как soft-drop
        mode = state["mode"]

        # P1
        if mode in (MODE_1P, MODE_2P_COOP, MODE_2P_BATTLE,
                    MODE_SPRINT, MODE_ULTRA):
            g1 = state["games"][0]
            if key in ("A", "a"):
                handle_player_key(g1, "left"); refresh_all(); return
            if key in ("D", "d"):
                handle_player_key(g1, "right"); refresh_all(); return
            if key in ("W", "w"):
                handle_player_key(g1, "rotate"); refresh_all(); return
            if key in ("S", "s"):
                handle_player_key(g1, "soft"); refresh_all(); return
            if key == " " or key == "Space" or key == "Spacebar":
                handle_player_key(g1, "hard"); refresh_all(); return
            if key in ("Q", "q"):
                handle_player_key(g1, "hold"); refresh_all(); return

        # P2
        if mode in (MODE_2P_COOP, MODE_2P_BATTLE) and len(state["games"]) > 1:
            g2 = state["games"][1]
            if key == "Arrow Left":
                handle_player_key(g2, "left"); refresh_all(); return
            if key == "Arrow Right":
                handle_player_key(g2, "right"); refresh_all(); return
            if key == "Arrow Up":
                handle_player_key(g2, "rotate"); refresh_all(); return
            if key == "Arrow Down":
                handle_player_key(g2, "soft"); refresh_all(); return
            if key == "Enter":
                handle_player_key(g2, "hard"); refresh_all(); return
            if key == "Shift":
                handle_player_key(g2, "hold"); refresh_all(); return

    page.on_keyboard_event = on_key

    # --- сборка страницы ---
    page.add(
        ft.Column([
            top_bar,
            ft.Container(
                content=ft.Text(
                    "P1: A/D движение, W поворот, S мягкое, "
                    "Space hard drop, Q hold\n"
                    "P2: ←/→ движение, ↑ поворот, ↓ мягкое, Enter hard drop, "
                    "RightShift hold\n"
                    "Общее: P пауза, R рестарт, M музыка, N звук, "
                    "L рекорды, T статистика, Ctrl+S настройки",
                    size=10, color=ft.Colors.GREY_500),
                padding=ft.Padding.only(left=8, bottom=4),
            ),
            game_area,
            touch_area,
        ], spacing=4, scroll=ft.ScrollMode.AUTO)
    )

    # --- монтируем аудио и запускаем первую сессию ---
    audio.mount()
    refresh_icons()
    page.update()
    start_new_session()

    # --- игровой цикл ---
    async def game_loop():
        await asyncio.sleep(0.3)
        last_step = 0.0
        while state["running"]:
            import time
            now = time.time()
            # частота шагов падения (по уровню самого продвинутого игрока)
            levels = [g.level for g in state["games"]
                      if not g.game_over and not g.paused]
            lvl = max(levels) if levels else 1
            step_interval = max(0.08, 0.8 - (lvl - 1) * 0.07)
            # в Sprint/Ultra-режимах гравитация чуть быстрее (драйв)
            if state["mode"] in (MODE_SPRINT, MODE_ULTRA):
                step_interval = max(0.05, step_interval * 0.85)
            if now - last_step >= step_interval:
                for g in state["games"]:
                    if not g.game_over and not g.paused:
                        g.step_down()
                # Battle: пересылка garbage между игроками
                if (state["mode"] == MODE_2P_BATTLE
                        and len(state["games"]) == 2):
                    g1, g2 = state["games"]
                    resolve_battle_garbage(g1, g2)
                last_step = now
            # проверяем таймаут Ultra-режима для всех игр
            for g in state["games"]:
                if g.mode == MODE_ULTRA and not g.game_over and not g.paused:
                    g.check_ultra_timeout()
            # refresh экрана каждые ~50ms (для плавного обновления таймера)
            refresh_all()
            await asyncio.sleep(0.05)

    page.run_task(game_loop)


if __name__ == "__main__":
    ft.run(main)
