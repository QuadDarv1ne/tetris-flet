"""Экран статистики завершённой сессии.
Генерирует графики matplotlib по данным PlayerGame.stats и сохраняет PNG.
Вызывается из основной игры по кнопке или клавише после game over."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np

# Шрифты с поддержкой кириллицы
try:
    fm.fontManager.addfont(
        "/usr/share/fonts/truetype/chinese/NotoSansSC-Regular.ttf")
except Exception:
    pass
plt.rcParams["font.sans-serif"] = ["Noto Sans SC", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# Цветовая палитра под тёмную тему игры
BG = "#0a0b10"
PANEL = "#161922"
ACCENT = "#22d3ee"
AMBER = "#fbbf24"
PURPLE = "#a855f7"
GREEN = "#22c55e"
RED = "#ef4444"
GREY = "#6b7280"

_MODE_TITLES = {
    "1P": "1 игрок — Marathon",
    "2P_COOP": "2 игрока — Co-op",
    "2P_BATTLE": "2 игрока — Battle",
    "SPRINT": "Sprint — 40 линий на время",
    "ULTRA": "Ultra — 120 сек на максимум очков",
}


def _style_axes(ax, title, ylabel=""):
    ax.set_facecolor(PANEL)
    ax.set_title(title, color=ACCENT, fontsize=11, fontweight="bold", pad=10)
    ax.tick_params(colors="#9ca3af", labelsize=9)
    ax.yaxis.label.set_color("#9ca3af")
    ax.xaxis.label.set_color("#9ca3af")
    for spine in ax.spines.values():
        spine.set_color("#2a2f3a")
    ax.grid(True, color="#1c2030", linewidth=0.6, alpha=0.7)


def render_session_stats(game, out_path):
    """Создаёт PNG-отчёт со статистикой завершённой игры.

    Args:
        game: PlayerGame с заполненным .stats и .score/.lines/.level.
        out_path: путь или бинарный файловый объект для PNG.
    Returns:
        переданный путь или файловый объект.
    """
    st = game.stats
    fig, axes = plt.subplots(2, 2, figsize=(12, 7),
                             constrained_layout=True)
    fig.patch.set_facecolor(BG)

    # --- 1. Распределение очисток линий (bar chart) ---
    ax = axes[0, 0]
    labels = ["Single", "Double", "Triple", "Tetris"]
    values = [st["single"], st["double"], st["triple"], st["tetrises"]]
    colors = ["#60a5fa", "#34d399", "#fbbf24", "#a855f7"]
    bars = ax.bar(labels, values, color=colors, edgecolor="#2a2f3a",
                  linewidth=1)
    for bar, v in zip(bars, values):
        if v > 0:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.1,
                    str(v), ha="center", va="bottom", color="white",
                    fontsize=10, fontweight="bold")
    _style_axes(ax, "Очистки линий", "Количество")
    ax.set_ylim(0, max(values) + 1 if values else 1)

    # --- 2. T-spin и Combo статистика (bar chart) ---
    ax = axes[0, 1]
    labels2 = ["T-spin", "Combos", "Max combo", "B2B max"]
    values2 = [st["tspins"], st["combos"], st["max_combo"], st["b2b_max"]]
    colors2 = [PURPLE, AMBER, "#f97316", "#eab308"]
    bars = ax.barh(labels2, values2, color=colors2, edgecolor="#2a2f3a",
                   linewidth=1)
    for bar, v in zip(bars, values2):
        if v > 0:
            ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height() / 2,
                    str(v), ha="left", va="center", color="white",
                    fontsize=10, fontweight="bold")
    _style_axes(ax, "T-spin / Combo / B2B", "Количество")
    ax.set_xlim(0, max(values2) + 1 if values2 else 1)

    # --- 3. Сводка ключевых метрик (текстовая панель) ---
    ax = axes[1, 0]
    ax.set_facecolor(PANEL)
    ax.set_xlim(0, 10); ax.set_ylim(0, 10)
    ax.set_xticks([]); ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_color("#2a2f3a")
    ax.set_title("Сводка сессии", color=ACCENT, fontsize=11,
                 fontweight="bold", pad=10)
    elapsed = game.elapsed()
    m, sec = int(elapsed // 60), elapsed - int(elapsed // 60) * 60
    time_str = f"{m:02d}:{sec:05.2f}"
    pps = st["pieces"] / elapsed if elapsed > 0 else 0
    lpm = game.lines / (elapsed / 60) if elapsed > 0 else 0
    info_lines = [
        (f"Имя игрока:", game.name, "white"),
        (f"Режим:", mod_mode_title(game.mode), AMBER),
        (f"Финальный счёт:", f"{game.score:,}", GREEN),
        (f"Линии очищены:", f"{game.lines}", ACCENT),
        (f"Уровень достигнут:", f"{game.level}", ACCENT),
        (f"Время игры:", time_str, AMBER),
        (f"Фигур поставлено:", f"{st['pieces']}", "white"),
        (f"TPS (фигур/сек):", f"{pps:.2f}", "white"),
        (f"LPM (линий/мин):", f"{lpm:.1f}", "white"),
    ]
    y = 9.2
    for label, val, color in info_lines:
        ax.text(0.4, y, label, color="#9ca3af", fontsize=10, va="top",
                family="monospace")
        ax.text(5.2, y, val, color=color, fontsize=10, va="top",
                fontweight="bold", family="monospace")
        y -= 0.92

    # --- 4. Эффективность: очки на фигуру / очки на линию ---
    ax = axes[1, 1]
    ax.set_facecolor(PANEL)
    ax.set_xlim(0, 10); ax.set_ylim(0, 10)
    ax.set_xticks([]); ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_color("#2a2f3a")
    ax.set_title("Эффективность", color=ACCENT, fontsize=11,
                 fontweight="bold", pad=10)
    pts_per_piece = game.score / st["pieces"] if st["pieces"] else 0
    pts_per_line = game.score / game.lines if game.lines else 0
    tetris_rate = (st["tetrises"] / max(st["single"] + st["double"]
                   + st["triple"] + st["tetrises"], 1) * 100)
    tspin_rate = (st["tspins"] / max(st["pieces"], 1) * 100)
    eff_lines = [
        (f"Очков/фигуру:", f"{pts_per_piece:.1f}", ACCENT),
        (f"Очков/линию:", f"{pts_per_line:.1f}", ACCENT),
        (f"Tetris-rate:", f"{tetris_rate:.1f}%", PURPLE),
        (f"T-spin-rate:", f"{tspin_rate:.2f}%", PURPLE),
        (f"Общий рекорд:", f"{game.high_score:,}", AMBER),
    ]
    y = 9.0
    for label, val, color in eff_lines:
        ax.text(0.4, y, label, color="#9ca3af", fontsize=10, va="top",
                family="monospace")
        ax.text(5.6, y, val, color=color, fontsize=10, va="top",
                fontweight="bold", family="monospace")
        y -= 1.1
    # оценка сессии
    if getattr(game, "new_high_score", False) and game.score > 0:
        grade = "НОВЫЙ РЕКОРД!"
        grade_color = AMBER
    elif tetris_rate > 30 or st["tspins"] >= 3:
        grade = "Отличная игра!"
        grade_color = GREEN
    elif st["combos"] >= 5:
        grade = "Мастер комбо!"
        grade_color = "#f97316"
    else:
        grade = "Хорошая игра!"
        grade_color = ACCENT
    ax.text(5, 1.0, grade, ha="center", va="center", color=grade_color,
            fontsize=13, fontweight="bold")

    # заголовок всего отчёта
    fig.suptitle("СТАТИСТИКА СЕССИИ",
                 color=ACCENT, fontsize=15, fontweight="bold", y=1.0)

    try:
        fig.savefig(out_path, dpi=90, facecolor=fig.get_facecolor())
    finally:
        plt.close(fig)
    return out_path


def mod_mode_title(mode):
    """Возвращает читаемое название режима по ключу."""
    return _MODE_TITLES.get(mode, mode)


if __name__ == "__main__":
    # Быстрый smoke-тест без создания временного файла.
    import io
    import time
    import tetris_flet as mod

    class FA:
        def play_sfx(self, n): pass

    g = mod.PlayerGame(mod.Settings(), FA(), 0, "TestPlayer",
                       mod.ACCENT_P1, mode="1P")
    g.score = 12450
    g.lines = 28
    g.level = 3
    g.high_score = 12000
    now = time.monotonic()
    g.start_time = now - 145.5
    g.finish_time = now
    assert abs(g.elapsed() - 145.5) < 0.01
    g.stats = {"pieces": 95, "tspins": 2, "tetrises": 3,
               "combos": 8, "max_combo": 4, "b2b_max": 2,
               "single": 6, "double": 4, "triple": 2}
    output = io.BytesIO()
    render_session_stats(g, output)
    png = output.getvalue()
    from PIL import Image

    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(png) > 5000
    with Image.open(io.BytesIO(png)) as im:
        h = im.convert("L").histogram()
    print("rendered PNG size:", len(png))
    print("non-white ratio:", round(1 - h[255] / sum(h), 3))
    print("SESSION STATS OK")
