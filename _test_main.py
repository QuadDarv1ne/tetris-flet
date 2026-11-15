import sys, traceback
sys.tracebacklimit = 50
try:
    import tetris_flet as m
    # создаём мок Page
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
            self.add = lambda *args: None
            self.update = lambda: None
            self.run_task = lambda *a, **k: None
            self.on_keyboard_event = None
            self.data_dir = None
            self.assets_dir = None
    p = MockPage()
    m.main(p)
    print("main() completed OK")
except Exception as e:
    traceback.print_exc()
