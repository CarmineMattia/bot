from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from spike import brain, plan, policy


class BrainValidateTests(unittest.TestCase):
    def test_focus_allowlisted(self) -> None:
        step = brain.validate_step(
            {"type": "FocusWindow", "app_id": "org.gnome.Ptyxis"},
            classify="gui",
            workspace=Path("/tmp/repo"),
        )
        self.assertEqual(step["type"], "FocusWindow")
        self.assertEqual(step["app_id"], "org.gnome.Ptyxis")

    def test_focus_unknown_rejected(self) -> None:
        with self.assertRaises(brain.BrainError):
            brain.validate_step(
                {"type": "FocusWindow", "app_id": "com.evil.App"},
                classify="gui",
                workspace=Path("/tmp/repo"),
            )

    def test_talk_step(self) -> None:
        step = brain.validate_step(
            {"type": "Talk", "reply": "hello"},
            classify="talk",
            workspace=Path("/tmp/repo"),
        )
        self.assertEqual(step, {"type": "Talk", "reply": "hello"})
        self.assertEqual(policy.decide(step), "auto")

    def test_code_injects_workspace(self) -> None:
        step = brain.validate_step(
            {"type": "CodeTask", "prompt": "explain README"},
            classify="code",
            workspace=Path("/tmp/repo"),
        )
        self.assertEqual(step["workspace"], str(Path("/tmp/repo").resolve()))
        self.assertEqual(policy.decide(step), "ask")

    def test_hotkey_allowlist(self) -> None:
        step = brain.validate_step(
            {"type": "Hotkey", "keys": ["ctrl", "shift", "t"], "app_id": "org.gnome.Ptyxis"},
            classify="gui",
            workspace=Path("/tmp/repo"),
        )
        self.assertEqual(step["keys"], ["ctrl", "shift", "t"])

    def test_extract_json_fences(self) -> None:
        obj = brain._extract_json('```json\n{"classify":"talk","step":{"type":"Talk","reply":"x"}}\n```')
        self.assertEqual(obj["classify"], "talk")


class BrainPlanFallbackTests(unittest.TestCase):
    def test_stub_used_when_brain_disabled(self) -> None:
        with patch.dict(os.environ, {"BOT_BRAIN": "0"}, clear=False):
            step = plan.plan_step("focus files", workspace=Path("/tmp/repo"), use_brain=False)
        self.assertEqual(step["type"], "FocusWindow")

    def test_brain_error_falls_back_to_stub(self) -> None:
        with patch("spike.brain.enabled", return_value=True), patch(
            "spike.brain.plan", side_effect=brain.BrainError("down")
        ):
            step = plan.plan_step("focus the terminal", workspace=Path("/tmp/repo"), use_brain=True)
        self.assertEqual(step["app_id"], "org.gnome.Ptyxis")

    def test_brain_success_used(self) -> None:
        fake = {"type": "Talk", "reply": "from brain"}
        with patch("spike.brain.enabled", return_value=True), patch(
            "spike.brain.plan", return_value=fake
        ):
            step = plan.plan_step("what is bot?", workspace=Path("/tmp/repo"), use_brain=True)
        self.assertEqual(step, fake)


class BrainHttpTests(unittest.TestCase):
    def test_chat_parses_assistant_content(self) -> None:
        payload = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "classify": "gui",
                                "step": {
                                    "type": "FocusWindow",
                                    "app_id": "org.gnome.Nautilus",
                                },
                            }
                        ),
                    }
                }
            ]
        }

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps(payload).encode()

        with patch.dict(
            os.environ,
            {"BOT_BRAIN": "1", "BOT_LLM_BASE_URL": "http://127.0.0.1:9/v1"},
            clear=False,
        ), patch("urllib.request.urlopen", return_value=_Resp()):
            step = brain.plan("focus files", workspace=Path("/tmp/repo"))
        self.assertEqual(step["app_id"], "org.gnome.Nautilus")


if __name__ == "__main__":
    unittest.main()
