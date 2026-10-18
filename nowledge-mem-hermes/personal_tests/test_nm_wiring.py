"""Personal installer/native skills checks; no NM or model IO."""

import importlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT.parent.parent / "hermes-secretary"
sys.path.insert(0, str(HOST))
PACKAGE = types.ModuleType("_nm_wiring_test")
PACKAGE.__path__ = [str(ROOT)]
sys.modules[PACKAGE.__name__] = PACKAGE
INSTALLER = importlib.import_module(PACKAGE.__name__ + ".install_personal")


def temporary_home():
    base = ROOT.parent / "temp-r3-personal"
    base.mkdir(exist_ok=True)
    return tempfile.TemporaryDirectory(dir=base)


class NativeSkillInstallationTests(unittest.TestCase):
    def test_install_does_not_expose_nm_skill_and_preserves_other_skills(self):
        from hermes_constants import reset_hermes_home_override, set_hermes_home_override

        with temporary_home() as folder, tempfile.TemporaryDirectory() as workspace:
            home = Path(folder) / "profile"
            home.mkdir()
            (home / "config.yaml").write_text("terminal:\n  cwd: " + workspace + "\n")
            other = home / "skills" / "operator-rule"
            other.mkdir(parents=True)
            (other / "SKILL.md").write_text(
                "---\nname: operator-rule\ndescription: Keep another skill\n---\nKeep this rule.\n")
            token = set_hermes_home_override(home)
            try:
                from agent.prompt_builder import build_skills_system_prompt
                from tools.skills_tool import skill_view

                with patch("urllib.request.urlopen", side_effect=AssertionError("No NM IO")):
                    INSTALLER.install(home, apply=True)
                    text = build_skills_system_prompt(available_tools={"skill_view", "terminal"})
                    self.assertNotIn("nm-cli", text)
                    self.assertIn("operator-rule", text)
                    self.assertFalse(json.loads(skill_view("nm-cli", preprocess=False))["success"])
                    self.assertTrue(json.loads(skill_view("operator-rule", preprocess=False))["success"])
                    self.assertFalse((home / "plugins/nowledge-mem/skills/nm-cli/SKILL.md").exists())
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
                    "external_dirs": external,
                    "disabled": ["operator-disabled"], "create_dir": "custom"})
                self.assertEqual(final["model"], "keep-model")

    def test_installer_does_not_validate_or_rewrite_unrelated_skill_settings(self):
        for skills in ([], "operator-owned", {"external_dirs": {"custom": "value"}},
                       {"external_dirs": ["keep", 42]}):
            with self.subTest(skills=skills), temporary_home() as folder:
                home = Path(folder)
                (home / "config.yaml").write_text(json.dumps({"skills": skills}))
                INSTALLER.install(home, apply=True)
                final = INSTALLER.load_config((home / "config.yaml").read_text())
                self.assertEqual(final["skills"], skills)


if __name__ == "__main__":
    unittest.main()
