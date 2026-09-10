from __future__ import annotations

import importlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import ANY, patch

from spike import omp_tool, plan, policy


driver = importlib.import_module("spike.__main__")


class CodeTaskPlannerPolicyTests(unittest.TestCase):
    def test_code_phrase_plans_one_workspace_scoped_task(self) -> None:
        workspace = Path("/tmp/example-repo")
        self.assertEqual(
            plan.plan_step("code explain README.md", workspace=workspace),
            {
                "type": "CodeTask",
                "prompt": "explain README.md",
                "workspace": str(workspace),
            },
        )

    def test_read_only_task_still_requires_confirmation(self) -> None:
        self.assertEqual(
            policy.decide({"type": "CodeTask", "prompt": "explain README.md"}),
            "ask",
        )

    def test_sensitive_and_mutating_tasks_ask(self) -> None:
        for prompt in (
            "add parser tests",
            "read /etc/passwd",
            "inspect ../../.ssh/id_rsa",
            "summarize .env",
        ):
            with self.subTest(prompt=prompt):
                self.assertEqual(
                    policy.decide({"type": "CodeTask", "prompt": prompt}),
                    "ask",
                )


class OmpToolTests(unittest.TestCase):
    def test_environment_drops_unrelated_credentials(self) -> None:
        with patch.dict(
            os.environ,
            {
                "PATH": "/usr/bin",
                "OPENAI_API_KEY": "model-provider-secret",
                "GITHUB_TOKEN": "unrelated-secret",
            },
            clear=True,
        ):
            child_env = omp_tool._subprocess_env()

        self.assertEqual(child_env["PATH"], "/usr/bin")
        self.assertIn("OPENAI_API_KEY", child_env)
        self.assertNotIn("GITHUB_TOKEN", child_env)

    @patch("spike.omp_tool.subprocess.run")
    def test_workspace_must_be_repository_root(self, run) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = omp_tool.run_task("explain README.md", Path(tmp))

        self.assertIn("not a repository root", result["error"])
        run.assert_not_called()

    @patch("spike.omp_tool.shutil.which", side_effect=["/usr/bin/omp", None])
    @patch("spike.omp_tool.subprocess.run")
    def test_missing_sandbox_fails_closed(self, run, _which) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / ".git").mkdir()
            result = omp_tool.run_task("explain README.md", workspace)

        self.assertIn("bwrap executable required", result["error"])
        run.assert_not_called()

    @patch(
        "spike.omp_tool.shutil.which",
        side_effect=["/usr/bin/omp", "/usr/bin/bwrap"],
    )
    @patch("spike.omp_tool.subprocess.run")
    def test_run_task_invokes_one_json_print_process(self, run, _which) -> None:
        run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=(
                '{"type":"session","id":"one"}\n'
                '{"type":"message_end","message":{"role":"assistant",'
                '"content":[{"type":"text","text":"README explained"}]}}\n'
            ),
            stderr="",
        )
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / ".git").mkdir()
            result = omp_tool.run_task("explain README.md", workspace)

        self.assertIsNone(result["error"])
        self.assertEqual(result["format"], "jsonl")
        self.assertEqual(result["response"], "README explained")
        run.assert_called_once_with(
            [
                "/usr/bin/bwrap",
                "--die-with-parent",
                "--new-session",
                "--unshare-pid",
                "--ro-bind",
                "/",
                "/",
                "--bind",
                str(workspace.resolve()),
                str(workspace.resolve()),
                "--tmpfs",
                "/tmp",
                "--proc",
                "/proc",
                "--dev",
                "/dev",
                "--chdir",
                str(workspace.resolve()),
                "/usr/bin/omp",
                "--cwd",
                str(workspace.resolve()),
                "--mode",
                "json",
                "--approval-mode",
                "write",
                "--no-session",
                "--no-extensions",
                "--no-skills",
                "--no-rules",
                "--no-lsp",
                "--tools",
                "read,grep,find,ls,edit,write",
                "--print",
                "explain README.md",
            ],
            cwd=workspace.resolve(),
            capture_output=True,
            text=True,
            timeout=900.0,
            check=False,
            env=ANY,
        )

    @patch(
        "spike.omp_tool.shutil.which",
        side_effect=["/usr/bin/omp", "/usr/bin/bwrap"],
    )
    @patch("spike.omp_tool.subprocess.run")
    def test_non_json_output_falls_back_without_second_run(self, run, _which) -> None:
        run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="plain result\n",
            stderr="",
        )
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / ".git").mkdir()
            result = omp_tool.run_task("inspect README.md", workspace)

        self.assertEqual(result["format"], "text_fallback")
        self.assertEqual(result["response"], "plain result")
        run.assert_called_once()


class CodeTaskTurnTests(unittest.TestCase):
    def test_confirmed_write_task_passes_gate_once(self) -> None:
        omp_result = {
            "error": None,
            "method": "omp_print_json",
            "returncode": 0,
            "format": "jsonl",
            "response": "Tests added",
            "event_count": 2,
            "stderr": "",
        }
        with (
            patch.object(driver, "load_state", return_value=driver.SpikeState()),
            patch.object(driver, "save_state"),
            patch.object(driver.overlay, "show"),
            patch.object(driver.overlay, "clear"),
            patch.object(driver.a11y, "observe", side_effect=AssertionError("GUI observe called")),
            patch.object(driver.omp_tool, "run_task", return_value=omp_result) as run_task,
        ):
            result = driver.run_turn(
                "code add parser tests",
                pause_ms=0,
                confirm_forced="yes",
            )

        self.assertEqual(result["policy"], "ask")
        self.assertEqual(result["user_confirm"], "confirm")
        self.assertEqual(result["outcome"], "ok")
        run_task.assert_called_once_with("add parser tests", driver.ROOT)

    @patch.object(driver.a11y, "observe", side_effect=AssertionError("GUI observe called"))
    @patch.object(driver.overlay, "clear")
    @patch.object(driver.overlay, "show")
    @patch.object(driver.confirm, "abortable_pause", return_value=False)
    @patch.object(driver, "save_state")
    @patch.object(driver, "load_state", return_value=driver.SpikeState())
    @patch.object(driver.omp_tool, "run_task")
    def test_read_only_code_turn_returns_gui_shaped_result(
        self,
        run_task,
        _load_state,
        _save_state,
        _pause,
        show,
        _clear,
        _observe,
    ) -> None:
        run_task.return_value = {
            "error": None,
            "method": "omp_print_json",
            "returncode": 0,
            "format": "jsonl",
            "response": "README explained",
            "event_count": 2,
            "stderr": "",
        }

        result = driver.run_turn(
            "code explain README.md",
            pause_ms=0,
            confirm_forced="yes",
        )

        self.assertEqual(result["policy"], "ask")
        self.assertEqual(result["user_confirm"], "confirm")
        self.assertEqual(result["outcome"], "ok")
        self.assertEqual(result["observation"]["source"], "omp")
        self.assertEqual(result["user_reply"], "README explained")
        run_task.assert_called_once_with("explain README.md", driver.ROOT)
        self.assertEqual(show.call_args_list[0].args[0]["phase"], "announce")


if __name__ == "__main__":
    unittest.main()