"""Генератор аудио-ассетов для Tetris.

Синтезирует:
  - music_korobeiniki.wav  — тема "Коробейники" (классическая мелодия
    Тетриса), аранжировка для square-wave + бас, ~30 сек, зацикливается
  - sfx_move.wav           — короткий "клик" перемещения
  - sfx_rotate.wav         — поворот (восходящий blip)
  - sfx_lock.wav           — фиксация фигуры (низкий tonk)
  - sfx_line_clear.wav     — очистка линий (арпеджио)
  - sfx_tetris.wav         — 4 линии (фанфары)
  - sfx_level_up.wav       — частотный свип вверх
  - sfx_hold.wav           — удержание (короткий bip)
  - sfx_game_over.wav      — нисходящая каденция

Все звуки пишутся как 16-bit PCM WAV (моно, 22050 Гц).
Запуск: python generate_audio.py [output_dir]
"""

from __future__ import annotations

import math
import os
import struct
import sys
import wave
from pathlib import Path

SAMPLE_RATE = 22050
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "assets" / "audio"


# ---------------------------------------------------------------------------
# Низкоуровневые помощники
# ---------------------------------------------------------------------------

def _env_adsr(n, a, d, s, r, total):
    """ADSR-огибающая: a — атака (доля), d — спад до сустейна,
    s — уровень сустейна, r — релиз (доля)."""
    a_n = int(a * total)
    d_n = int(d * total)
    r_n = int(r * total)
    s_n = total - a_n - d_n - r_n
    if s_n < 0:
        s_n = 0
        r_n = total - a_n - d_n
    env = []
    for i in range(a_n):
        env.append(i / max(a_n, 1))
    for i in range(d_n):
        env.append(1.0 - (1.0 - s) * (i / max(d_n, 1)))
    for i in range(s_n):
        env.append(s)
    for i in range(r_n):
        env.append(s * (1.0 - i / max(r_n, 1)))
    while len(env) < total:
        env.append(0.0)
    return env[:total]


def _waveform(t, freq, kind="square", duty=0.5):
    """Синтез одной формы волны."""
    if kind == "sine":
        return math.sin(2 * math.pi * freq * t)
    if kind == "square":
        ph = (freq * t) % 1.0
        return 1.0 if ph < duty else -1.0
    if kind == "triangle":
        ph = (freq * t) % 1.0
        return 4 * abs(ph - 0.5) - 1.0
    if kind == "saw":
        ph = (freq * t) % 1.0
        return 2 * ph - 1.0
    if kind == "pulse25":
        ph = (freq * t) % 1.0
        return 1.0 if ph < 0.25 else -1.0
    return 0.0


def synth_note(freq, duration, volume=0.25, kind="square",
               decay=4.0, attack=0.01):
    """Одиночная нота с экспоненциальным затуханием и быстрой атакой."""
    n = int(SAMPLE_RATE * duration)
    out = bytearray()
    a_n = int(attack * SAMPLE_RATE)
    for i in range(n):
        t = i / SAMPLE_RATE
        v = _waveform(t, freq, kind)
        # атака
        if i < a_n:
            v *= i / max(a_n, 1)
        # экспоненциальный спад
        env = math.exp(-decay * t / max(duration, 1e-6))
        sample = int(volume * env * v * 32767)
        sample = max(-32768, min(32767, sample))
        out += struct.pack("<h", sample)
    return bytes(out)


def synth_rest(duration):
    n = int(SAMPLE_RATE * duration)
    return b"\x00\x00" * n


def mix(*chunks):
    if not chunks:
        return b""
    length = max(len(c) for c in chunks) // 2
    out = bytearray()
    for i in range(length):
        s = 0
        cnt = 0
        for c in chunks:
            if i * 2 + 2 <= len(c):
                (val,) = struct.unpack("<h", c[i * 2:i * 2 + 2])
                s += val
                cnt += 1
        if cnt:
            s = s // cnt
        s = max(-32768, min(32767, s))
        out += struct.pack("<h", s)
    return bytes(out)


def concat(*chunks):
    return b"".join(chunks)


def to_wav(pcm: bytes) -> bytes:
    import io
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


def save_wav(path: Path, pcm: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    print(f"  saved {path.name}  ({len(pcm) // 2} samples, "
          f"{len(pcm) // 2 / SAMPLE_RATE:.2f}s, {len(to_wav(pcm))} bytes)")


# ---------------------------------------------------------------------------
# Ноты — частоты (Гц). Korobeiniki в Am (ля-минор).
# ---------------------------------------------------------------------------

NOTE_FREQS = {
    "C2": 65.41, "D2": 73.42, "E2": 82.41, "F2": 87.31, "G2": 98.00,
    "A2": 110.00, "B2": 123.47,
    "C3": 130.81, "D3": 146.83, "E3": 164.81, "F3": 174.61, "G3": 196.00,
    "A3": 220.00, "B3": 246.94,
    "C4": 261.63, "D4": 293.66, "E4": 329.63, "F4": 349.23, "G4": 392.00,
    "A4": 440.00, "B4": 493.88, "A#4": 466.16, "G#4": 415.30,
    "C5": 523.25, "D5": 587.33, "E5": 659.25, "F5": 698.46, "G5": 783.99,
    "A5": 880.00, "B5": 987.77, "A#5": 932.33, "G#5": 830.61,
    "C6": 1046.50, "D6": 1174.66, "E6": 1318.51, "F6": 1396.91,
    "G6": 1567.98, "A6": 1760.00, "B6": 1975.53,
    "rest": 0,
}


def n(name, duration, volume=0.25, kind="square", decay=4.0):
    """Нота по имени. Если 'rest' — тишина."""
    if name == "rest" or name is None:
        return synth_rest(duration)
    return synth_note(NOTE_FREQS[name], duration, volume, kind, decay)


# ---------------------------------------------------------------------------
# Мелодия "Коробейники" (Тема А из Tetris).
# Транскрипция в ля-миноре. Темп ~120 BPM, восьмые = 0.25 сек.
# ---------------------------------------------------------------------------

EIGHTH = 0.20   # длительность восьмой ноты (сек) — чуть быстрее для драйва
QUARTER = 0.40
HALF = 0.80

# Мелодия (правая рука) — пара фраз, затем повтор.
# Это упрощённая, но узнаваемая транскрипция Korobeiniki.
MELODY = [
    # Фраза 1
    ("E5", EIGHTH), ("B4", EIGHTH), ("C5", EIGHTH), ("D5", EIGHTH),
    ("C5", EIGHTH), ("B4", EIGHTH), ("A4", EIGHTH), ("A4", EIGHTH),
    ("rest", EIGHTH), ("C5", EIGHTH), ("E5", EIGHTH), ("A5", EIGHTH),
    ("G5", EIGHTH), ("E5", EIGHTH), ("C5", EIGHTH), ("E5", EIGHTH),
    ("D5", EIGHTH), ("B4", EIGHTH), ("rest", EIGHTH), ("B4", EIGHTH),
    ("C5", EIGHTH), ("D5", EIGHTH), ("E5", EIGHTH),
    ("C5", EIGHTH), ("A4", EIGHTH), ("A4", EIGHTH), ("rest", EIGHTH),
    # Фраза 2
    ("rest", EIGHTH), ("D5", EIGHTH), ("F5", EIGHTH), ("A5", EIGHTH),
    ("A#4", EIGHTH), ("A5", EIGHTH), ("A5", EIGHTH), ("G5", EIGHTH),
    ("E5", EIGHTH), ("C5", EIGHTH), ("E5", EIGHTH), ("D5", EIGHTH),
    ("C5", EIGHTH), ("B4", EIGHTH), ("B4", EIGHTH), ("C5", EIGHTH),
    ("D5", EIGHTH), ("E5", EIGHTH), ("C5", EIGHTH), ("A4", EIGHTH),
    ("A4", EIGHTH), ("rest", EIGHTH), ("rest", QUARTER),
]

# Бас (левая рука) — упрощённая "ум-па" октавами на A.
BASS = [
    ("A2", QUARTER), ("A2", QUARTER), ("E2", QUARTER), ("E2", QUARTER),
    ("A2", QUARTER), ("A2", QUARTER), ("E2", QUARTER), ("E2", QUARTER),
    ("A2", QUARTER), ("A2", QUARTER), ("E2", QUARTER), ("E2", QUARTER),
    ("A2", QUARTER), ("A2", QUARTER), ("E2", QUARTER), ("E2", QUARTER),
    ("A2", QUARTER), ("A2", QUARTER), ("E2", QUARTER), ("E2", QUARTER),
    ("A2", QUARTER), ("A2", QUARTER), ("E2", QUARTER), ("E2", QUARTER),
    ("A2", QUARTER), ("A2", QUARTER), ("E2", QUARTER), ("E2", QUARTER),
    ("A2", QUARTER), ("A2", QUARTER), ("E2", QUARTER), ("E2", QUARTER),
    ("A2", QUARTER), ("A2", QUARTER), ("E2", QUARTER), ("E2", QUARTER),
    ("A2", QUARTER), ("A2", QUARTER), ("E2", QUARTER), ("E2", QUARTER),
    ("A2", QUARTER), ("A2", QUARTER), ("E2", QUARTER), ("E2", QUARTER),
]


def build_korobeiniki():
    """Собирает мелодию (мелодия + бас) и возвращает PCM."""
    # мелодия: pulse/square для характерного 8-битного звука
    melody_pcm = concat(*[n(name, dur, volume=0.22, kind="square", decay=3.0)
                          for name, dur in MELODY])
    # бас: треугольная волна, мягче
    bass_pcm = concat(*[n(name, dur, volume=0.30, kind="triangle", decay=2.0)
                        for name, dur in BASS])
    # выравниваем длины
    m_len = len(melody_pcm)
    b_len = len(bass_pcm)
    if b_len < m_len:
        bass_pcm = bass_pcm + b"\x00\x00" * ((m_len - b_len) // 2)
    elif m_len < b_len:
        melody_pcm = melody_pcm + b"\x00\x00" * ((b_len - m_len) // 2)
    return mix(melody_pcm, bass_pcm)


# ---------------------------------------------------------------------------
# SFX — аутентичные короткие звуки тетриса
# ---------------------------------------------------------------------------

def sfx_move():
    """Короткий 'тик' перемещения — square 220 Гц, 30 мс."""
    return synth_note(220, 0.03, volume=0.18, kind="square", decay=12)


def sfx_rotate():
    """Восходящий blip поворота — два тона."""
    return concat(
        synth_note(440, 0.025, volume=0.18, kind="square", decay=10),
        synth_note(660, 0.035, volume=0.20, kind="square", decay=8),
    )


def sfx_lock():
    """Фиксация — низкий 'тонк'."""
    return mix(
        synth_note(110, 0.08, volume=0.30, kind="square", decay=8),
        synth_note(55, 0.10, volume=0.25, kind="triangle", decay=6),
    )


def sfx_line_clear():
    """Очистка линий — восходящее арпеджио."""
    notes = [("C5", 0.05), ("E5", 0.05), ("G5", 0.05), ("C6", 0.10)]
    return concat(*[synth_note(NOTE_FREQS[n], d, volume=0.25, kind="square",
                              decay=5)
                   for n, d in notes])


def sfx_tetris():
    """4 линии — фанфары."""
    notes = [
        ("C5", 0.07), ("E5", 0.07), ("G5", 0.07), ("C6", 0.07),
        ("E6", 0.07), ("G6", 0.18),
    ]
    return concat(*[synth_note(NOTE_FREQS[n], d, volume=0.28, kind="square",
                               decay=4)
                    for n, d in notes])


def sfx_level_up():
    """Level up — восходящий частотный свип."""
    n_total = int(SAMPLE_RATE * 0.35)
    out = bytearray()
    phase = 0.0
    f0, f1 = 330.0, 1320.0
    for i in range(n_total):
        t = i / SAMPLE_RATE
        freq = f0 + (f1 - f0) * (t / 0.35)
        phase += 2 * math.pi * freq / SAMPLE_RATE
        v = math.sin(phase)
        env = math.exp(-2.0 * t / 0.35)
        sample = int(0.25 * env * v * 32767)
        sample = max(-32768, min(32767, sample))
        out += struct.pack("<h", sample)
    return bytes(out)


def sfx_hold():
    """Удержание — короткий 'бип'."""
    return synth_note(880, 0.05, volume=0.18, kind="square", decay=14)


def sfx_game_over():
    """Game over — нисходящая каденция (3 ноты)."""
    return concat(
        synth_note(440, 0.18, volume=0.28, kind="triangle", decay=3),
        synth_note(330, 0.18, volume=0.28, kind="triangle", decay=3),
        synth_note(220, 0.35, volume=0.30, kind="triangle", decay=2),
    )


def sfx_hard_drop():
    """Hard drop — свист + удар."""
    return mix(
        concat(
            synth_note(660, 0.03, volume=0.18, kind="square", decay=10),
            synth_note(880, 0.04, volume=0.18, kind="square", decay=10),
        ),
        synth_note(80, 0.10, volume=0.28, kind="triangle", decay=8),
    )


# ---------------------------------------------------------------------------
# Главная функция
# ---------------------------------------------------------------------------

def generate(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Генерация аудио в {out_dir}/")

    # Музыка: "Коробейники", проигрывается ~25 сек, зацикливается
    print("  → music_korobeiniki.wav")
    music_pcm = build_korobeiniki()
    save_wav(out_dir / "music_korobeiniki.wav", music_pcm)

    # SFX
    print("  → SFX")
    save_wav(out_dir / "sfx_move.wav", sfx_move())
    save_wav(out_dir / "sfx_rotate.wav", sfx_rotate())
    save_wav(out_dir / "sfx_lock.wav", sfx_lock())
    save_wav(out_dir / "sfx_hard_drop.wav", sfx_hard_drop())
    save_wav(out_dir / "sfx_line_clear.wav", sfx_line_clear())
    save_wav(out_dir / "sfx_tetris.wav", sfx_tetris())
    save_wav(out_dir / "sfx_level_up.wav", sfx_level_up())
    save_wav(out_dir / "sfx_hold.wav", sfx_hold())
    save_wav(out_dir / "sfx_game_over.wav", sfx_game_over())

    print("Готово.")


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    generate(out)
