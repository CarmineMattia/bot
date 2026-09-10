from __future__ import annotations

import unittest
from unittest.mock import patch

from spike import act, plan, policy, ydo


class HotkeyPlannerTests(unittest.TestCase):
    def test_new_tab_is_explicit_hotkey(self) -> None:
        self.assertEqual(
            plan.plan_gui_step("new tab"),
            {"type": "Hotkey", "keys": ["ctrl", "shift", "t"]},
        )

    def test_click_new_tab_remains_a11y_click(self) -> None:
        self.assertEqual(
            plan.plan_gui_step("click New Tab"),
            {
                "type": "ClickA11y",
                "role": "push button",
                "name": "New Tab",
                "window": None,
            },
        )


class HotkeyPolicyTests(unittest.TestCase):
    def test_ptyxis_new_tab_is_auto_allowed(self) -> None:
        self.assertEqual(
            policy.decide({"type": "Hotkey", "keys": ["ctrl", "shift", "t"]}),
            "auto",
        )

    def test_other_hotkeys_still_require_confirmation(self) -> None:
        self.assertEqual(
            policy.decide({"type": "Hotkey", "keys": ["alt", "f4"]}),
            "ask",
        )


class HotkeyActuationTests(unittest.TestCase):
    @patch("spike.ydo.hotkey", return_value=None)
    @patch("spike.a11y.observe", return_value={"focused": {"app_id": "ptyxis", "title": "t"}})
    def test_perform_hotkey_uses_ydotool(self, _obs, hot) -> None:
        result = act._perform_hotkey({"type": "Hotkey", "keys": ["ctrl", "shift", "t"]})
        self.assertIsNone(result.get("error"))
        self.assertEqual(result.get("method"), "ydotool_key")
        hot.assert_called_once_with(["ctrl", "shift", "t"])


if __name__ == "__main__":
    unittest.main()
