import unittest
from types import SimpleNamespace
from unittest.mock import patch

import flet as ft

import tetris_flet as tetris


class FakeAudio:
    def __init__(self):
        self.events = []

    def play_sfx(self, name):
        self.events.append(name)

    def mount(self):
        pass

    def set_volume(self, volume):
        pass

    def toggle_music(self, enabled):
        pass

    def start_music(self):
        pass

    def stop_music(self):
        pass


class FakePage:
    def __init__(self):
        self.window = SimpleNamespace()
        self.overlay = []
        self.controls = []

    def add(self, *controls):
        self.controls.extend(controls)

    def update(self):
        pass

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
        self.assertIn("level_up", self.audio.events)

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

    @patch("time.time", side_effect=[100, 110, 200, 210, 319, 320])
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

    @patch("time.time", return_value=110)
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

    def test_reset_clears_pause_and_t_spin_state(self):
        game = self.make_game()
        game.tspin_count = 3
        game._paused_duration = 12
        game._score_committed = True
        game.paused = True

        game.reset()

        self.assertFalse(game.paused)
        self.assertFalse(game._score_committed)
        self.assertEqual(game._paused_duration, 0)
        self.assertIsNone(game._paused_at)
        self.assertEqual(game.tspin_count, 0)


class AppInteractionTests(unittest.TestCase):
    def setUp(self):
        self.settings = tetris.Settings(sound=False, music=False, ghost=False)
        self.settings.save = lambda: None
        self.audio = FakeAudio()
        self.page = FakePage()
        with (
            patch.object(tetris.Settings, "load", return_value=self.settings),
            patch.object(tetris, "AudioManager", return_value=self.audio),
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

    def test_saving_or_cancelling_settings_resumes_game(self):
        settings_button = self.control(
            lambda item: isinstance(item, ft.IconButton)
            and item.tooltip == "Настройки (S)"
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


if __name__ == "__main__":
    unittest.main()
