from __future__ import annotations

import importlib
import unittest
from unittest.mock import patch

from spike import act, plan, policy


driver = importlib.import_module("spike.__main__")


class HotkeyPlannerTests(unittest.TestCase):
    def test_new_tab_is_explicit_hotkey(self) -> None:
        self.assertEqual(
            plan.plan_gui_step("new tab"),
            {
                "type": "Hotkey",
                "keys": ["ctrl", "shift", "t"],
                "app_id": "org.gnome.Ptyxis",
            },
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
    @patch(
        "spike.a11y.observe",
        return_value={
            "focused": {"app_id": "org.gnome.Ptyxis", "title": "t"},
            "frames": [
                {
                    "app_id": "org.gnome.Ptyxis",
                    "title": "t",
                    "flags": ["ACTIVE"],
                }
            ],
        },
    )
    def test_perform_hotkey_uses_ydotool(self, _obs, hot) -> None:
        result = act._perform_hotkey(
            {
                "type": "Hotkey",
                "keys": ["ctrl", "shift", "t"],
                "app_id": "org.gnome.Ptyxis",
            }
        )
        self.assertIsNone(result.get("error"), result)
        self.assertEqual(result.get("method"), "ydotool_key")
        hot.assert_called_once_with(["ctrl", "shift", "t"])


class HotkeyTurnTests(unittest.TestCase):
    def test_successful_hotkey_without_a11y_delta_is_not_retried(self) -> None:
        observation = {
            "source": "a11y",
            "summary": "org.gnome.Ptyxis: Terminal",
            "focused": {
                "app_id": "org.gnome.Ptyxis",
                "title": "Terminal",
            },
            "fingerprint": "unchanged",
        }
        act_result = {
            "error": None,
            "method": "ydotool_key",
            "keys": ["ctrl", "shift", "t"],
            "focused_before": observation["focused"],
        }
        with (
            patch.object(driver, "load_state", return_value=driver.SpikeState()),
            patch.object(driver, "save_state"),
            patch.object(driver.overlay, "show"),
            patch.object(driver.overlay, "clear"),
            patch.object(driver.confirm, "abortable_pause", return_value=False),
            patch.object(driver.time, "sleep"),
            patch.object(driver.a11y, "observe", side_effect=[observation, observation]),
            patch.object(driver.act, "perform", return_value=act_result) as perform,
        ):
            result = driver.run_turn("new tab", pause_ms=0)

        perform.assert_called_once()
        self.assertEqual(result["outcome"], "ok")
        self.assertFalse(result["transition"])
        self.assertFalse(result["retried"])
        self.assertIn("chord trusted", result["user_reply"])


if __name__ == "__main__":
    unittest.main()
