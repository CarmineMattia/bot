from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spike import plan


driver = importlib.import_module("spike.__main__")


class OneGestureTurnTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env = patch.dict(os.environ, {"BOT_BRAIN": "0"}, clear=False)
        self._env.start()
        self.observation = {
            "source": "a11y",
            "summary": "org.gnome.Ptyxis: Terminal",
            "focused": {"app_id": "org.gnome.Ptyxis", "role": "terminal"},
            "fingerprint": "unchanged",
        }

    def tearDown(self) -> None:
        self._env.stop()

    def test_type_text_enter_failure_does_not_retype(self) -> None:
        act_result = {
            "error": "Enter failed",
            "method": "type+enter",
            "focused": self.observation["focused"],
            "typed": True,
        }
        with (
            patch.object(driver, "load_state", return_value=driver.SpikeState()),
            patch.object(driver, "save_state"),
            patch.object(driver.overlay, "show"),
            patch.object(driver.overlay, "clear"),
            patch.object(driver.confirm, "abortable_pause", return_value=False),
            patch.object(driver.time, "sleep"),
            patch.object(
                driver.a11y,
                "observe",
                side_effect=[self.observation, self.observation],
            ),
            patch.object(driver.act, "perform", return_value=act_result) as perform,
        ):
            result = driver.run_turn("type secret and enter", pause_ms=0)

        perform.assert_called_once()
        self.assertEqual(result["outcome"], "stop")
        self.assertFalse(result["retried"])
        self.assertIn("Enter failed", result["user_reply"])

    def test_successful_click_without_a11y_delta_is_not_retried(self) -> None:
        act_result = {
            "error": None,
            "method": "a11y_action",
            "target": {"role": "push button", "name": "New Folder"},
        }
        with (
            patch.object(driver, "load_state", return_value=driver.SpikeState()),
            patch.object(driver, "save_state"),
            patch.object(driver.overlay, "show"),
            patch.object(driver.overlay, "clear"),
            patch.object(driver.confirm, "abortable_pause", return_value=False),
            patch.object(driver.time, "sleep"),
            patch.object(
                driver.a11y,
                "observe",
                side_effect=[self.observation, self.observation],
            ),
            patch.object(driver.act, "perform", return_value=act_result) as perform,
        ):
            result = driver.run_turn("click New Folder", pause_ms=0)

        perform.assert_called_once()
        self.assertEqual(result["outcome"], "ok")
        self.assertFalse(result["transition"])
        self.assertFalse(result["retried"])
        self.assertIn("click trusted", result["user_reply"])


class PersistentLogRedactionTests(unittest.TestCase):
    def test_type_text_is_redacted_in_state_but_not_turn_result(self) -> None:
        secret = "correct horse battery staple"
        state = driver.SpikeState()
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / ".spike_state.json"
            with (
                patch.object(driver, "STATE_PATH", state_path),
                patch("builtins.print"),
            ):
                result = driver._emit(
                    state,
                    announce=f"Type {secret!r}",
                    step={"type": "TypeText", "text": secret, "submit": True},
                    decision="auto",
                    outcome="ok",
                    reply="typed",
                    observation={"summary": "terminal"},
                )
            persisted_text = state_path.read_text()
            persisted = json.loads(persisted_text)

        self.assertEqual(result["step"]["text"], secret)
        self.assertNotIn(secret, persisted_text)
        entry = persisted["action_log"][0]
        self.assertEqual(entry["step"]["text"], "<omitted from persistent log>")
        self.assertEqual(entry["step"]["text_chars"], len(secret))
        self.assertNotIn(secret, entry["announce"])


class CodeTaskSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env = patch.dict(os.environ, {"BOT_BRAIN": "0"}, clear=False)
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()

    def test_cancel_during_announce_is_logged_and_saved(self) -> None:
        state = driver.SpikeState()
        with (
            patch.object(driver, "load_state", return_value=state),
            patch.object(driver, "save_state") as save_state,
            patch.object(driver.overlay, "show"),
            patch.object(driver.overlay, "clear"),
            patch.object(driver.confirm, "wait_confirm", return_value="confirm"),
            patch.object(driver.confirm, "abortable_pause", return_value=True),
            patch.object(driver.omp_tool, "run_task") as run_task,
        ):
            result = driver.run_turn(
                "code explain the private design",
                pause_ms=0,
                confirm_forced="yes",
            )

        run_task.assert_not_called()
        save_state.assert_called_once_with(state)
        self.assertEqual(result["outcome"], "cancelled")
        self.assertEqual(result["action_log_len"], 1)
        self.assertEqual(state.action_log[0].outcome, "cancelled")
        self.assertEqual(
            state.action_log[0].step["prompt"],
            "<omitted from persistent log>",
        )

    def test_turn_act_drops_events_and_truncates_stderr(self) -> None:
        act_result = {
            "error": None,
            "method": "omp_print_json",
            "returncode": 0,
            "format": "jsonl",
            "response": "Task complete",
            "event_count": 2,
            "events": [{"secret": "raw event"}],
            "stderr": "x" * (driver.MAX_TURN_STDERR_CHARS + 100),
        }
        with (
            patch.object(driver, "save_state"),
            patch.object(driver.overlay, "show"),
            patch.object(driver.overlay, "clear"),
            patch.object(driver.confirm, "abortable_pause", return_value=False),
            patch.object(driver.omp_tool, "run_task", return_value=act_result),
        ):
            result = driver._run_code_task(
                step={
                    "type": "CodeTask",
                    "prompt": "test",
                    "workspace": str(driver.ROOT),
                },
                announce="Ask omp: test",
                decision="ask",
                state=driver.SpikeState(),
                pause_ms=0,
                raise_only=False,
                user_confirm="confirm",
            )

        self.assertNotIn("events", result["act"])
        self.assertEqual(result["act"]["response"], "Task complete")
        self.assertEqual(result["act"]["event_count"], 2)
        self.assertEqual(result["act"]["format"], "jsonl")
        self.assertEqual(len(result["act"]["stderr"]), driver.MAX_TURN_STDERR_CHARS)


class TypeParserTests(unittest.TestCase):
    def test_embedded_submit_word_is_preserved(self) -> None:
        self.assertEqual(
            plan.plan_gui_step("type please submit this form"),
            {
                "type": "TypeText",
                "text": "please submit this form",
                "submit": False,
            },
        )

    def test_trailing_submit_cue_is_consumed(self) -> None:
        self.assertEqual(
            plan.plan_gui_step("type hello and submit"),
            {"type": "TypeText", "text": "hello", "submit": True},
        )


if __name__ == "__main__":
    unittest.main()
