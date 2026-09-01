import importlib.util
import pathlib
import unittest

launcher_path = pathlib.Path(__file__).resolve().parents[1] / "launcher.py"
spec = importlib.util.spec_from_file_location("launcher", launcher_path)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class LauncherHotkeyTests(unittest.TestCase):
    def test_normalize_hotkey_names(self):
        self.assertEqual(launcher.normalize_hotkey_name("left windows"), "windows")
        self.assertEqual(launcher.normalize_hotkey_name("right alt"), "alt")

    def test_should_trigger_combo_after_last_modifier(self):
        pressed = {"ctrl", "windows", "alt"}
        self.assertTrue(launcher.should_trigger_combo(pressed, ("ctrl", "alt", "windows")))


if __name__ == "__main__":
    unittest.main()
