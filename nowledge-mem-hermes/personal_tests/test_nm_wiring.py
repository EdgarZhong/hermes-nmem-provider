"""Personal installer/native skills and CLI syntax checks; no NM or model IO."""

import importlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT.parent.parent / "hermes-secretary"
sys.path.insert(0, str(HOST))
PACKAGE = types.ModuleType("_nm_wiring_test")
PACKAGE.__path__ = [str(ROOT)]
sys.modules[PACKAGE.__name__] = PACKAGE
CLI = importlib.import_module(PACKAGE.__name__ + ".personal_cli")
INSTALLER = importlib.import_module(PACKAGE.__name__ + ".install_personal")
SOURCES = {"version": 1, "sources": [
    {"conversation_ref": "conv_approved", "message_uid": "uid_approved"},
]}


def temporary_home():
    base = ROOT.parent / "temp-r3-personal"
    base.mkdir(exist_ok=True)
    return tempfile.TemporaryDirectory(dir=base)


class CliSpaceTests(unittest.TestCase):
    def client(self):
        client = Mock()
        client._api_url.return_value = "https://nm.invalid"
        client.cli_env = {"PATH": os.environ.get("PATH", "")}
        return client

    def test_confirmed_create_keeps_space_labels_body_and_partial_id(self):
        client = self.client()
        client.memory_get.side_effect = PermissionError("metadata unavailable")
        completed = subprocess.CompletedProcess([], 0, b'{"id":"created-exact-id"}')
        with (
            patch.object(CLI, "_resolve_nmem", return_value="/native/nmem"),
            patch.object(CLI.subprocess, "run", return_value=completed) as run,
            redirect_stderr(io.StringIO()) as receipt,
        ):
            result = CLI.create_memory(client, "Approved\n正文", SOURCES,
                                       title="Approved title", labels=["notebook:situation"],
                                       space="profile-space")
        argv = run.call_args.args[0]
        self.assertEqual(argv, ["/native/nmem", "--json", "--api-url", "https://nm.invalid",
                                "m", "add", "--stdin", "--source", "hermes-secretary",
                                "--space", "profile-space", "--title", "Approved title",
                                "-l", "notebook:situation"])
        self.assertEqual(run.call_args.kwargs["input"], "Approved\n正文".encode())
        run.assert_called_once()
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["memory_id"], "created-exact-id")
        self.assertEqual(json.loads(receipt.getvalue())["memory_id"], "created-exact-id")
        client.memory_get.assert_called_once_with("created-exact-id")
        client.request_json.assert_not_called()

    def test_ambiguous_create_has_no_metadata_or_retry(self):
        client = self.client()
        for result in (subprocess.CompletedProcess([], 2, b""),
                       subprocess.CompletedProcess([], 0, b'{"memory":{"id":"nested"}}')):
            with (
                self.subTest(returncode=result.returncode),
                patch.object(CLI, "_resolve_nmem", return_value="/native/nmem"),
                patch.object(CLI.subprocess, "run", return_value=result) as run,
            ):
                outcome = CLI.create_memory(client, "approved", SOURCES, space="profile-space")
            self.assertEqual(outcome["status"], "creation_unknown")
            self.assertIsNone(outcome["memory_id"])
            run.assert_called_once()
        client.memory_get.assert_not_called()
        client.request_json.assert_not_called()

    @unittest.skipUnless(shutil.which("nmem"), "Official CLI is not installed")
    def test_actual_cli_help_accepts_helper_space_position_and_rejects_old(self):
        exe = shutil.which("nmem")
        native_run = subprocess.run
        calls = []

        def help_only(argv, **kwargs):
            # This terminal help flag stops the real parser before any service IO.
            result = native_run([*argv, "--help"], **kwargs)
            calls.append(result)
            return result

        with (
            patch.object(CLI, "_resolve_nmem", return_value=exe),
            patch.object(CLI.subprocess, "run", side_effect=help_only),
        ):
            outcome = CLI.create_memory(self.client(), "unused", SOURCES, space="profile-space")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].returncode, 0, calls[0].stderr.decode())
        self.assertIn(b"--space", calls[0].stdout)
        self.assertEqual(outcome["status"], "creation_unknown")  # help is not a write receipt
        old = native_run([exe, "--space", "profile-space", "m", "add", "--help"],
                         capture_output=True, timeout=10)
        self.assertNotEqual(old.returncode, 0)
        self.assertIn(b"unexpected argument", old.stderr)


class NativeSkillInstallationTests(unittest.TestCase):
    def test_installed_skill_is_discoverable_from_native_root_and_skill_view(self):
        from hermes_constants import reset_hermes_home_override, set_hermes_home_override

        with temporary_home() as folder, tempfile.TemporaryDirectory() as workspace:
            home = Path(folder) / "profile"
            home.mkdir()
            (home / "config.yaml").write_text(
                "terminal:\n  cwd: " + workspace + "\n", encoding="utf-8")
            token = set_hermes_home_override(home)
            try:
                from agent.prompt_builder import build_skills_system_prompt
                from tools.skills_tool import skill_view

                with patch("urllib.request.urlopen", side_effect=AssertionError("No NM IO")):
                    before = build_skills_system_prompt(available_tools={"skill_view", "terminal"})
                    self.assertNotIn("nm-cli", before)
                    self.assertFalse(json.loads(skill_view("nm-cli", preprocess=False))["success"])
                    # Model index and skill_view are the real host implementations; no plugin registry stub.
                    INSTALLER.install(home, apply=True)
                    after = build_skills_system_prompt(available_tools={"skill_view", "terminal"})
                    self.assertIn("- nm-cli:", after)
                    viewed = json.loads(skill_view("nm-cli", preprocess=False))
                    self.assertTrue(viewed["success"], viewed)
                    installed = home / "plugins/nowledge-mem/skills/nm-cli/SKILL.md"
                    self.assertEqual(Path(viewed["_source_path"]), installed)
                    self.assertEqual(viewed["content"], installed.read_text(encoding="utf-8"))
                    # Profile-local relative config survives clone/move without pointing back to the source home.
                    clone = Path(folder) / "clone"
                    shutil.copytree(home, clone)
                    clone_token = set_hermes_home_override(clone)
                    try:
                        self.assertIn("- nm-cli:", build_skills_system_prompt())
                        clone_view = json.loads(skill_view("nm-cli", preprocess=False))
                        self.assertTrue(clone_view["success"], clone_view)
                        self.assertTrue(Path(clone_view["_source_path"]).is_relative_to(clone))
                    finally:
                        reset_hermes_home_override(clone_token)
            finally:
                reset_hermes_home_override(token)

    def test_preserves_existing_skills_configuration_and_install_is_idempotent(self):
        for external in (["existing-skills"], "existing-skills"):
            with self.subTest(external=external), temporary_home() as folder:
                home = Path(folder)
                config = {"model": "keep-model", "skills": {
                    "external_dirs": external, "disabled": ["operator-disabled"], "create_dir": "custom"}}
                (home / "config.yaml").write_text(json.dumps(config), encoding="utf-8")
                before = (home / "config.yaml").read_bytes()
                INSTALLER.install(home)
                self.assertEqual((home / "config.yaml").read_bytes(), before)
                self.assertFalse((home / "plugins").exists())
                INSTALLER.install(home, apply=True)
                INSTALLER.install(home, apply=True)
                final = INSTALLER.load_config((home / "config.yaml").read_text())
                self.assertEqual(final["skills"], {
                    "external_dirs": ["existing-skills", "plugins/nowledge-mem/skills"],
                    "disabled": ["operator-disabled"], "create_dir": "custom"})
                self.assertEqual(final["model"], "keep-model")

    def test_invalid_skills_config_is_rejected_before_install_writes(self):
        for skills in ([], "invalid", {"external_dirs": {"bad": "path"}},
                       {"external_dirs": ["keep", 42]}):
            with self.subTest(skills=skills), temporary_home() as folder:
                home = Path(folder)
                (home / "config.yaml").write_text(json.dumps({"skills": skills}))
                before = (home / "config.yaml").read_bytes()
                with self.assertRaises(ValueError):
                    INSTALLER.install(home, apply=True)
                self.assertEqual((home / "config.yaml").read_bytes(), before)
                self.assertFalse((home / "plugins").exists())


if __name__ == "__main__":
    unittest.main()
