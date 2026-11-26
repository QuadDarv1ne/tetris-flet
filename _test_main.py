import sys, traceback
sys.tracebacklimit = 50
try:
    import tetris_flet as m
    # создаём мок Page (совместим с Flet 1.x: show_dialog/pop_dialog)
    import flet as ft

    class MockPage:
        def __init__(self):
            self.title = ""
            self.bgcolor = None
            self.theme_mode = None
            self.padding = None
            self.theme = None
            self.window = ft.Window()
            self.overlay = []
            self.controls = []
            self._dialogs = []
            self.add = lambda *args: None
            self.update = lambda: None
            self.run_task = lambda *a, **k: None
            self.on_keyboard_event = None
            self.data_dir = None
            self.assets_dir = None
            self.width = 1100
            self.height = 820
            self.on_resize = None

        def show_dialog(self, dialog):
            if dialog in self._dialogs:
                raise RuntimeError("Dialog is already opened")
            dialog.open = True
            self._dialogs.append(dialog)

        def pop_dialog(self):
            dialog = next(
                (d for d in reversed(self._dialogs) if d.open), None
            )
            if dialog:
                dialog.open = False
            return dialog

    p = MockPage()
    m.main(p)
    print("main() completed OK")
except Exception:
    traceback.print_exc()
