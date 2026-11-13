import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import flet as ft

import tetris_flet as tetris


class FakeAudio:
    def __init__(self):
        self.events = []
        self.music_playing = False
        self.supports_volume_control = False

    def play_sfx(self, name):
        self.events.append(name)

    def mount(self):
        pass

    def set_volume(self, volume):
        pass

    def toggle_music(self, enabled):
        self.music_playing = enabled

    def start_music(self):
        self.music_playing = True

    def stop_music(self):
        self.music_playing = False


class FakePage:
    def __init__(self):
        self.window = SimpleNamespace()
        self.overlay = []
        self.controls = []
        self.shown_dialogs = []

    def add(self, *controls):
        self.controls.extend(controls)

    def update(self):
        pass

    def show_dialog(self, dialog):
        dialog.open = True
        self.shown_dialogs.append(dialog)

    def run_task(self, task):
        self.game_loop = task


def walk_controls(control):
    yield control
    for child in getattr(control, "controls", []):
        yield from walk_controls(child)
    content = getattr(control, "content", None)
    if content is not None:
        yield from walk_controls(content)


class GameLogicTests(unittest.TestCase):
    def make_game(self, mode="1P", **kwargs):
        self.audio = FakeAudio()
        settings = tetris.Settings(sound=False, music=False, start_level=1)
        return tetris.PlayerGame(settings, self.audio, mode=mode, **kwargs)

    def test_settings_load_normalizes_values_for_ui_controls(self):
        test_cases = (
            (99, 2.0, 15, 1.0),
            (-4, -0.5, 1, 0.0),
            (3, float("nan"), 3, 0.7),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            for level, volume, expected_level, expected_volume in test_cases:
                with self.subTest(level=level, volume=volume):
                    path.write_text(
                        json.dumps({
                            "start_level": level,
                            "volume": volume,
                            "player_name": "  A very long player name  ",
                        }),
                        encoding="utf-8",
                    )
                    with patch.object(tetris.Settings, "_path", return_value=path):
                        settings = tetris.Settings.load()

                    self.assertEqual(settings.start_level, expected_level)
                    self.assertEqual(settings.volume, expected_volume)
                    self.assertEqual(settings.player_name, "A very long pl")

    def test_settings_load_parses_boolean_strings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text(
                json.dumps({
                    "sound": "false",
                    "music": "true",
                    "ghost": "off",
                }),
                encoding="utf-8",
            )
            with patch.object(tetris.Settings, "_path", return_value=path):
                settings = tetris.Settings.load()

        self.assertFalse(settings.sound)
        self.assertTrue(settings.music)
        self.assertFalse(settings.ghost)

    def test_settings_load_preserves_values_with_invalid_numeric_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text(
                json.dumps({
                    "sound": False,
                    "music": False,
                    "start_level": "invalid",
                    "volume": "invalid",
                    "player_name": "Preserved",
                }),
                encoding="utf-8",
            )
            with patch.object(tetris.Settings, "_path", return_value=path):
                settings = tetris.Settings.load()

        self.assertFalse(settings.sound)
        self.assertFalse(settings.music)
        self.assertEqual(settings.start_level, 1)
        self.assertEqual(settings.volume, 0.7)
        self.assertEqual(settings.player_name, "Preserved")

    def test_settings_save_writes_json_without_leaving_temp_files(self):
        settings = tetris.Settings(player_name="Tester")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            with patch.object(tetris.Settings, "_path", return_value=path):
                settings.save()

            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["player_name"], "Tester")
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_settings_save_preserves_previous_file_on_replace_error(self):
        settings = tetris.Settings()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text("previous settings", encoding="utf-8")
            with (
                patch.object(tetris.Settings, "_path", return_value=path),
                patch.object(
                    tetris.os, "replace",
                    side_effect=OSError("read-only"),
                ),
                self.assertRaisesRegex(OSError, "read-only"),
            ):
                settings.save()

            self.assertEqual(
                path.read_text(encoding="utf-8"), "previous settings"
            )
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_high_score_save_propagates_write_errors(self):
        with patch.object(
            tetris.os, "replace", side_effect=OSError("read-only")
        ), self.assertRaisesRegex(OSError, "read-only"):
            tetris.save_high_score(100)

    def test_score_commit_logs_storage_errors_without_stopping_game(self):
        game = self.make_game()
        game.score = 100

        with (
            patch.object(
                tetris, "save_high_score", side_effect=OSError("read-only")
            ),
            patch.object(
                tetris, "add_to_leaderboard",
                side_effect=OSError("read-only"),
            ),
            self.assertLogs("tetris_flet", level="ERROR") as captured,
        ):
            game._commit_high_score()

        self.assertEqual(len(captured.records), 2)
        self.assertTrue(game._score_committed)
        self.assertEqual(game.high_score, 100)

    def test_audio_volume_uses_full_range_only_for_mp3(self):
        audio = object.__new__(tetris.AudioManager)
        audio.available = True
        audio._music_handle = "music"
        audio._music_is_mp3 = True
        self.assertTrue(audio.supports_volume_control)

        with patch.object(tetris, "_mci_cmd") as mci_command:
            audio.set_volume(1.0)
        mci_command.assert_called_once_with("setaudio music volume to 1000")

        audio._music_is_mp3 = False
        self.assertFalse(audio.supports_volume_control)
        with patch.object(tetris, "_mci_cmd") as mci_command:
            audio.set_volume(1.0)
        mci_command.assert_not_called()

    def test_malformed_leaderboard_data_is_ignored(self):
        valid_entry = {
            "name": "Runner",
            "score": 150,
            "lines": 4,
            "level": 1,
            "time": 12.5,
        }
        data = {
            "SPRINT": [
                valid_entry,
                {"name": "Broken", "time": "invalid"},
                {},
                None,
            ],
            "1P": "not a list",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "leaderboard.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with patch.object(tetris, "LEADERBOARD_PATH", path):
                sprint_entries = tetris.get_leaderboard("SPRINT")
                marathon_entries = tetris.get_leaderboard("1P")

        self.assertEqual(sprint_entries, [valid_entry])
        self.assertEqual(marathon_entries, [])

    def test_stats_mode_title_does_not_reload_game_module(self):
        import session_stats

        module_before = sys.modules["tetris_flet"]
        runner_before = ft.run

        title = session_stats.mod_mode_title(tetris.MODE_1P)

        self.assertEqual(title, tetris.MODE_TITLES[tetris.MODE_1P])
        self.assertIs(sys.modules["tetris_flet"], module_before)
        self.assertIs(ft.run, runner_before)

    def test_stats_render_closes_figure_when_saving_fails(self):
        import session_stats

        game = self.make_game()
        open_figures = set(session_stats.plt.get_fignums())
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "missing" / "report.png"
            with self.assertRaises(OSError):
                session_stats.render_session_stats(game, str(output))

        self.assertEqual(
            set(session_stats.plt.get_fignums()), open_figures
        )

    def test_t_spin_line_clear_updates_level(self):
        game = self.make_game()
        game.board = [[None] * tetris.COLS for _ in range(tetris.ROWS)]
        game.current = {"kind": "T", "rotation": 0, "x": 3, "y": 18}
        game.lines = 9
        game._last_action_was_rotate = True
        game.board[18][3] = "#"
        game.board[18][5] = "#"
        for column in range(tetris.COLS):
            if column not in (3, 4, 5):
                game.board[19][column] = "#"

        game._lock_piece()

        self.assertEqual(game.lines, 10)
        self.assertEqual(game.level, 2)
        self.assertEqual(game.score, 800)
        self.assertEqual(game.stats["single"], 1)
        self.assertEqual(game.stats["tspins"], 1)
        self.assertIn("level_up", self.audio.events)

    def test_start_level_change_applies_only_to_new_game(self):
        game = self.make_game()
        game.lines = 9
        game.settings.start_level = 5
        game.board = [[None] * tetris.COLS for _ in range(tetris.ROWS)]
        game.current = {"kind": "O", "rotation": 0, "x": 3, "y": 18}
        for column in range(tetris.COLS):
            if column not in (4, 5):
                game.board[19][column] = "#"

        game._lock_piece()
        new_game = tetris.PlayerGame(game.settings, self.audio)

        self.assertEqual(game.level, 2)
        self.assertEqual(new_game.level, 5)

    def test_sprint_victory_does_not_spawn_another_piece(self):
        game = self.make_game(mode="SPRINT", sprint_target=1)
        game.board = [[None] * tetris.COLS for _ in range(tetris.ROWS)]
        game.current = {"kind": "O", "rotation": 0, "x": 3, "y": 18}
        for column in range(tetris.COLS):
            if column not in (4, 5):
                game.board[19][column] = "#"
        game.board[0] = ["#"] * 9 + [None]
        commits = []
        game._commit_high_score = lambda: commits.append(game.lines)
        locked_piece = game.current.copy()

        game._lock_piece()

        self.assertTrue(game.game_over)
        self.assertEqual(game.lines, 1)
        self.assertEqual(commits, [1])
        self.assertEqual(game.current, locked_piece)

    def test_sprint_victory_records_bonuses_from_final_piece(self):
        game = self.make_game(mode="SPRINT", sprint_target=1)
        game.board = [[None] * tetris.COLS for _ in range(tetris.ROWS)]
        game.current = {"kind": "T", "rotation": 0, "x": 3, "y": 18}
        game._last_action_was_rotate = True
        game.board[18][3] = "#"
        game.board[18][5] = "#"
        for column in range(tetris.COLS):
            if column not in (3, 4, 5):
                game.board[19][column] = "#"
        entries = []

        with (
            patch.object(tetris, "save_high_score"),
            patch.object(
                tetris,
                "add_to_leaderboard",
                side_effect=lambda mode, entry: entries.append(entry.copy()),
            ),
        ):
            game._lock_piece()

        self.assertEqual(game.score, 800)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["score"], 800)

    def test_sprint_overflow_victory_commits_result_only_once(self):
        game = self.make_game(mode="SPRINT", sprint_target=1)
        game.current = {"kind": "I", "rotation": 1, "x": 2, "y": -1}
        game.board[0] = [
            "#" if column != 4 else None for column in range(tetris.COLS)
        ]
        committed_entries = []
        with (
            patch.object(tetris, "save_high_score"),
            patch.object(
                tetris,
                "add_to_leaderboard",
                side_effect=lambda mode, entry: committed_entries.append(entry),
            ),
        ):
            game._lock_piece()

        self.assertTrue(game.game_over)
        self.assertEqual(game.lines, 1)
        self.assertEqual(len(committed_entries), 1)

    def test_sprint_failure_is_not_added_to_time_leaderboard(self):
        game = self.make_game(mode="SPRINT", sprint_target=40)
        game.lines = 12
        game.game_over = True

        with (
            patch.object(tetris, "save_high_score"),
            patch.object(tetris, "add_to_leaderboard") as add_entry,
        ):
            game._commit_high_score()

        add_entry.assert_not_called()

    def test_b2b_max_tracks_the_full_difficult_clear_chain(self):
        game = self.make_game()
        for _ in range(3):
            game.board = [[None] * tetris.COLS for _ in range(tetris.ROWS)]
            game.current = {"kind": "I", "rotation": 1, "x": 2, "y": 16}
            for row in range(16, 20):
                game.board[row] = [
                    "#" if column != 4 else None
                    for column in range(tetris.COLS)
                ]
            game._lock_piece()

        self.assertEqual(game.stats["tetrises"], 3)
        self.assertEqual(game.stats["b2b_max"], 3)
        self.assertEqual(game.b2b_count, 3)

    def test_no_clear_piece_preserves_back_to_back_chain(self):
        game = self.make_game()
        game.b2b = True
        game.b2b_count = 2
        game.current = {"kind": "O", "rotation": 0, "x": 3, "y": 18}

        game._lock_piece()

        self.assertTrue(game.b2b)
        self.assertEqual(game.b2b_count, 2)

    def test_battle_attacks_accumulate_until_they_are_resolved(self):
        game = self.make_game(mode=tetris.MODE_2P_BATTLE)
        for _ in range(2):
            game.board = [[None] * tetris.COLS for _ in range(tetris.ROWS)]
            game.current = {"kind": "I", "rotation": 1, "x": 2, "y": 16}
            for row in range(16, 20):
                game.board[row] = [
                    "#" if column != 4 else None
                    for column in range(tetris.COLS)
                ]
            game._lock_piece()

        self.assertEqual(game.last_sent_garbage, 7)

    def test_simultaneous_battle_attacks_cancel_each_other(self):
        player1 = self.make_game(mode=tetris.MODE_2P_BATTLE)
        player2 = self.make_game(mode=tetris.MODE_2P_BATTLE)
        player1.last_sent_garbage = 3
        player2.last_sent_garbage = 2

        tetris.resolve_battle_garbage(player1, player2)

        self.assertEqual(player1.pending_garbage, 0)
        self.assertEqual(player2.pending_garbage, 1)
        self.assertEqual(player1.last_sent_garbage, 0)
        self.assertEqual(player2.last_sent_garbage, 0)

    def test_battle_finishes_and_commits_the_winner(self):
        loser = self.make_game(mode=tetris.MODE_2P_BATTLE)
        winner = tetris.PlayerGame(
            loser.settings, self.audio, name="Player 2",
            mode=tetris.MODE_2P_BATTLE,
        )
        loser.game_over = True

        with patch.object(winner, "_commit_high_score") as commit_winner:
            self.assertTrue(tetris.finish_battle_if_needed(loser, winner))
            self.assertFalse(tetris.finish_battle_if_needed(loser, winner))

        self.assertTrue(winner.game_over)
        self.assertEqual(winner.battle_result, "ПОБЕДА!")
        self.assertEqual(loser.battle_result, "Победил Player 2")
        commit_winner.assert_called_once()

    def test_simultaneous_battle_game_overs_are_a_draw(self):
        player1 = self.make_game(mode=tetris.MODE_2P_BATTLE)
        player2 = self.make_game(mode=tetris.MODE_2P_BATTLE)
        player1.game_over = True
        player2.game_over = True

        with (
            patch.object(player1, "_commit_high_score") as commit_player1,
            patch.object(player2, "_commit_high_score") as commit_player2,
        ):
            self.assertTrue(tetris.finish_battle_if_needed(player1, player2))

        self.assertEqual(player1.battle_result, "НИЧЬЯ!")
        self.assertEqual(player2.battle_result, "НИЧЬЯ!")
        commit_player1.assert_called_once()
        commit_player2.assert_called_once()

    def test_battle_result_is_shown_on_game_over_overlay(self):
        game = self.make_game(mode=tetris.MODE_2P_BATTLE)
        game.game_over = True
        game.battle_result = "ПОБЕДА!"
        widgets = {
            "score": SimpleNamespace(value=""),
            "lines": SimpleNamespace(value=""),
            "level": SimpleNamespace(value=""),
            "tspin": SimpleNamespace(value=""),
            "combo": SimpleNamespace(value=""),
            "b2b": SimpleNamespace(value=""),
            "hold": SimpleNamespace(shapes=[]),
            "nexts": [SimpleNamespace(shapes=[]) for _ in range(3)],
            "field": SimpleNamespace(shapes=[]),
            "overlay": SimpleNamespace(visible=False),
            "overlay_text": SimpleNamespace(value=""),
            "overlay_sub": SimpleNamespace(value=""),
        }

        tetris.update_player_ui(widgets, game)

        self.assertTrue(widgets["overlay"].visible)
        self.assertEqual(widgets["overlay_text"].value, "ПОБЕДА!")
        self.assertIn("Счёт:", widgets["overlay_sub"].value)

    def test_piece_previews_are_flat_canvas_shapes(self):
        for kind in tetris.SHAPE_KINDS:
            with self.subTest(kind=kind):
                shapes = tetris.build_piece_preview(kind, 84, 46, 11)
                self.assertEqual(len(shapes), 25)
                self.assertFalse(any(isinstance(shape, list) for shape in shapes))

    def test_hard_drop_preserves_rotation_for_t_spin_detection(self):
        game = self.make_game()
        game.current = {"kind": "T", "rotation": 1, "x": 3, "y": -1}
        game._last_action_was_rotate = True
        seen_rotation_state = []
        game._detect_tspin = lambda: seen_rotation_state.append(
            game._last_action_was_rotate
        ) or game._last_action_was_rotate

        game.hard_drop()

        self.assertEqual(seen_rotation_state, [True])
        self.assertTrue(game.last_tspin)

    def test_gravity_preserves_rotation_state_for_t_spin(self):
        game = self.make_game()
        game.current = {"kind": "T", "rotation": 1, "x": 3, "y": -1}
        game._last_action_was_rotate = True

        game.step_down()

        self.assertEqual(game.current["y"], 0)
        self.assertTrue(game._last_action_was_rotate)

    def test_holding_piece_checks_for_blocked_spawn(self):
        game = self.make_game()
        game.current = {"kind": "O", "rotation": 0, "x": 3, "y": -1}
        game.hold_kind = "I"
        game.board[0][3] = "#"
        game._commit_high_score = lambda: None

        game.hold()

        self.assertTrue(game.game_over)
        self.assertEqual(game.current["kind"], "I")
        self.assertFalse(game.can_hold)
        self.assertNotIn("hold", self.audio.events)

    def test_holding_piece_swaps_once_without_consuming_queue(self):
        game = self.make_game()
        game.current = {"kind": "O", "rotation": 0, "x": 3, "y": -1}
        game.hold_kind = "I"
        queue_before = game.next_queue()

        game.hold()
        game.hold()

        self.assertEqual(game.current["kind"], "I")
        self.assertEqual(game.hold_kind, "O")
        self.assertFalse(game.can_hold)
        self.assertEqual(game.next_queue(), queue_before)

    def test_holding_piece_clears_previous_rotation_state(self):
        game = self.make_game()
        game.current = {"kind": "L", "rotation": 0, "x": 3, "y": -1}
        game.hold_kind = "T"
        game.rotate()
        self.assertTrue(game._last_action_was_rotate)

        game.hold()

        self.assertEqual(game.current["kind"], "T")
        self.assertFalse(game._last_action_was_rotate)

    def test_time_trial_timer_does_not_start_while_paused(self):
        for mode in (tetris.MODE_SPRINT, tetris.MODE_ULTRA):
            with self.subTest(mode=mode):
                game = self.make_game(mode=mode)
                game.paused = True

                tetris.handle_player_key(game, "left")

                self.assertIsNone(game.start_time)
                game.paused = False
                tetris.handle_player_key(game, "left")
                self.assertIsNotNone(game.start_time)

    def test_elapsed_uses_monotonic_clock(self):
        game = self.make_game(mode="SPRINT")
        with (
            patch("time.time", return_value=10_000),
            patch("time.monotonic", return_value=100),
        ):
            game.start_timer()
        with (
            patch("time.time", return_value=-10_000),
            patch("time.monotonic", return_value=110),
        ):
            self.assertEqual(game.elapsed(), 10)

    def test_standard_mode_timer_starts_when_game_is_created(self):
        with patch("time.monotonic", side_effect=[100, 110]):
            game = self.make_game(mode=tetris.MODE_1P)
            self.assertEqual(game.start_time, 100)
            self.assertEqual(game.elapsed(), 10)

    @patch("time.monotonic", side_effect=[100, 110, 200, 210, 319, 320])
    def test_ultra_timer_excludes_pause_time(self, _mock_time):
        game = self.make_game(mode="ULTRA", ultra_duration=120)
        game._commit_high_score = lambda: None
        game.start_timer()
        game.paused = True

        self.assertEqual(game.elapsed(), 10)
        game.check_ultra_timeout()
        self.assertFalse(game.game_over)

        game.paused = False
        game.check_ultra_timeout()
        self.assertFalse(game.game_over)
        game.check_ultra_timeout()

        self.assertTrue(game.game_over)
        self.assertEqual(game.elapsed(), 120)

    @patch("time.monotonic", return_value=110)
    def test_completed_game_timer_stays_frozen(self, _mock_time):
        game = self.make_game()
        game.start_time = 100
        with (
            patch.object(tetris, "save_high_score"),
            patch.object(tetris, "add_to_leaderboard"),
        ):
            game._commit_high_score()

        self.assertEqual(game.finish_time, 110)
        self.assertEqual(game.elapsed(), 10)

    def test_only_strictly_higher_score_is_marked_as_new_record(self):
        test_cases = ((100, 100, False), (100, 101, True), (100, 50, False))
        for high_score, score, expected in test_cases:
            with self.subTest(high_score=high_score, score=score):
                game = self.make_game()
                game.high_score = high_score
                game.score = score
                with (
                    patch.object(tetris, "save_high_score"),
                    patch.object(tetris, "add_to_leaderboard"),
                ):
                    game._commit_high_score()

                self.assertEqual(game.new_high_score, expected)

    def test_reset_clears_pause_and_t_spin_state(self):
        game = self.make_game()
        game.tspin_count = 3
        game._paused_duration = 12
        game._score_committed = True
        game.new_high_score = True
        game.paused = True

        game.reset()

        self.assertFalse(game.paused)
        self.assertFalse(game._score_committed)
        self.assertFalse(game.new_high_score)
        self.assertEqual(game._paused_duration, 0)
        self.assertIsNone(game._paused_at)
        self.assertEqual(game.tspin_count, 0)


class AppInteractionTests(unittest.TestCase):
    def setUp(self):
        self.settings = tetris.Settings(sound=False, music=False, ghost=False)
        self.settings.save = lambda: None
        self.audio = FakeAudio()
        self.page = FakePage()
        self.created_games = []
        game_class = tetris.PlayerGame

        def create_game(*args, **kwargs):
            game = game_class(*args, **kwargs)
            self.created_games.append(game)
            return game

        with (
            patch.object(tetris.Settings, "load", return_value=self.settings),
            patch.object(tetris, "AudioManager", return_value=self.audio),
            patch.object(tetris, "load_high_score", return_value=0),
            patch.object(tetris, "PlayerGame", side_effect=create_game),
        ):
            tetris.main(self.page)
        self.root = self.page.controls[0]

    def control(self, predicate):
        return next(
            item for item in walk_controls(self.root) if predicate(item)
        )

    def test_player_one_keys_work_in_time_trial_modes(self):
        mode_dropdown = self.control(
            lambda item: isinstance(item, ft.Dropdown)
            and item.label == "Режим"
        )
        for mode in (tetris.MODE_SPRINT, tetris.MODE_ULTRA):
            with self.subTest(mode=mode):
                mode_dropdown.value = mode
                mode_dropdown.on_change(SimpleNamespace())
                field = self.control(
                    lambda item: isinstance(item, tetris.cv.Canvas)
                    and item.width == tetris.FIELD_W
                    and item.height == tetris.FIELD_H
                )
                before = list(field.shapes)

                self.page.on_keyboard_event(
                    SimpleNamespace(key="A", ctrl=False)
                )

                self.assertNotEqual(field.shapes, before)

    def test_battle_game_over_finishes_match_from_keyboard_refresh(self):
        mode_dropdown = self.control(
            lambda item: isinstance(item, ft.Dropdown)
            and item.label == "Режим"
        )
        games = []
        game_class = tetris.PlayerGame

        def create_game(*args, **kwargs):
            game = game_class(*args, **kwargs)
            games.append(game)
            return game

        mode_dropdown.value = tetris.MODE_2P_BATTLE
        with patch.object(tetris, "PlayerGame", side_effect=create_game):
            mode_dropdown.on_change(SimpleNamespace())
        loser, winner = games
        loser.game_over = True

        self.page.on_keyboard_event(SimpleNamespace(key="A", ctrl=False))

        self.assertTrue(winner.game_over)
        self.assertEqual(loser.battle_result, f"Победил {winner.name}")
        self.assertEqual(winner.battle_result, "ПОБЕДА!")

    def test_settings_shortcut_does_not_conflict_with_soft_drop(self):
        settings_dialog = self.page.overlay[0]
        field = self.control(
            lambda item: isinstance(item, tetris.cv.Canvas)
            and item.width == tetris.FIELD_W
            and item.height == tetris.FIELD_H
        )
        before = list(field.shapes)

        self.page.on_keyboard_event(SimpleNamespace(key="S", ctrl=False))

        self.assertNotEqual(field.shapes, before)
        self.assertFalse(settings_dialog.open)
        self.page.on_keyboard_event(SimpleNamespace(key="S", ctrl=True))
        self.assertTrue(settings_dialog.open)
        settings_dialog.actions[0].on_click(None)

    def test_volume_control_explains_when_backend_cannot_adjust_it(self):
        settings_dialog = self.page.overlay[0]
        volume_slider, volume_hint = settings_dialog.content.controls[4:6]

        self.assertTrue(volume_slider.disabled)
        self.assertTrue(volume_hint.visible)

    def test_saving_or_cancelling_settings_resumes_game(self):
        settings_button = self.control(
            lambda item: isinstance(item, ft.IconButton)
            and item.tooltip == "Настройки (Ctrl+S)"
        )
        field_stack = self.control(
            lambda item: isinstance(item, ft.Stack)
            and item.width == tetris.FIELD_W
            and item.height == tetris.FIELD_H
        )
        settings_dialog = self.page.overlay[0]

        settings_button.on_click(None)
        self.assertTrue(field_stack.controls[1].visible)
        settings_dialog.actions[-1].on_click(None)
        self.assertFalse(field_stack.controls[1].visible)

        settings_button.on_click(None)
        self.assertTrue(field_stack.controls[1].visible)
        settings_dialog.actions[0].on_click(None)
        self.assertFalse(field_stack.controls[1].visible)

    def test_dialog_blocks_game_shortcuts_and_escape_closes_dialog(self):
        settings_button = self.control(
            lambda item: isinstance(item, ft.IconButton)
            and item.tooltip == "Настройки (Ctrl+S)"
        )
        settings_dialog = self.page.overlay[0]
        game = self.created_games[0]
        game_count = len(self.created_games)

        settings_button.on_click(None)
        self.page.on_keyboard_event(SimpleNamespace(key="R", ctrl=False))

        self.assertTrue(settings_dialog.open)
        self.assertTrue(game.paused)
        self.assertEqual(len(self.created_games), game_count)

        self.page.on_keyboard_event(SimpleNamespace(key="Escape", ctrl=False))

        self.assertFalse(settings_dialog.open)
        self.assertFalse(game.paused)

    def test_closing_settings_preserves_preexisting_pause(self):
        pause_button = self.control(
            lambda item: isinstance(item, ft.IconButton)
            and item.tooltip == "Пауза (P)"
        )
        settings_button = self.control(
            lambda item: isinstance(item, ft.IconButton)
            and item.tooltip == "Настройки (Ctrl+S)"
        )
        settings_dialog = self.page.overlay[0]
        game = self.created_games[0]

        self.assertTrue(settings_dialog.modal)
        pause_button.on_click(None)
        settings_button.on_click(None)
        settings_dialog.actions[0].on_click(None)

        self.assertTrue(game.paused)

    def test_saving_music_setting_keeps_paused_game_silent(self):
        pause_button = self.control(
            lambda item: isinstance(item, ft.IconButton)
            and item.tooltip == "Пауза (P)"
        )
        settings_button = self.control(
            lambda item: isinstance(item, ft.IconButton)
            and item.tooltip == "Настройки (Ctrl+S)"
        )
        settings_dialog = self.page.overlay[0]
        music_switch = settings_dialog.content.controls[2]
        game = self.created_games[0]

        pause_button.on_click(None)
        settings_button.on_click(None)
        music_switch.value = True
        settings_dialog.actions[-1].on_click(None)

        self.assertTrue(game.paused)
        self.assertFalse(self.audio.music_playing)
        pause_button.on_click(None)
        self.assertTrue(self.audio.music_playing)

    def test_music_shortcut_keeps_paused_game_silent(self):
        pause_button = self.control(
            lambda item: isinstance(item, ft.IconButton)
            and item.tooltip == "Пауза (P)"
        )
        game = self.created_games[0]
        pause_button.on_click(None)

        self.page.on_keyboard_event(SimpleNamespace(key="M", ctrl=False))

        self.assertTrue(game.paused)
        self.assertTrue(self.settings.music)
        self.assertFalse(self.audio.music_playing)

        pause_button.on_click(None)
        self.assertTrue(self.audio.music_playing)

    def test_settings_write_failure_is_shown_to_the_player(self):
        self.settings.save = Mock(side_effect=OSError("read-only"))
        settings_dialog = self.page.overlay[0]

        settings_dialog.actions[-1].on_click(None)

        self.assertEqual(len(self.page.shown_dialogs), 1)
        error_dialog = self.page.shown_dialogs[0]
        self.assertIsInstance(error_dialog, ft.SnackBar)
        self.assertIn("read-only", error_dialog.content.value)

    def test_committed_high_score_survives_restart(self):
        high_score = self.root.controls[0].controls[2].content.controls[1]
        game = self.created_games[0]
        game.score = 200
        game.high_score = 200
        self.page.on_keyboard_event(SimpleNamespace(key="A", ctrl=False))

        self.page.on_keyboard_event(SimpleNamespace(key="R", ctrl=False))

        self.assertEqual(high_score.value, "200")


if __name__ == "__main__":
    unittest.main()
