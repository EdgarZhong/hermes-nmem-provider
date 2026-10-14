"""Keep this fork's installable provider and update registry on one release."""

import json
from pathlib import Path


def test_hermes_manifest_matches_registry_and_documented_release():
    plugin = Path(__file__).resolve().parents[1]
    manifest = (plugin / "plugin.yaml").read_text(encoding="utf-8")
    version = next(
        line.removeprefix("version:").strip()
        for line in manifest.splitlines()
        if line.startswith("version:")
    )
    registry = json.loads((plugin.parent / "integrations.json").read_text(encoding="utf-8"))
    hermes = next(item for item in registry["integrations"] if item["id"] == "hermes")
    assert version == "0.6.0"
    assert hermes["version"] == version
    assert f"# Personal Hermes {version}" in (plugin / "CHANGELOG.md").read_text(encoding="utf-8")
    assert version in (plugin / "README.md").read_text(encoding="utf-8")
    assert hermes["transport"] == "cli"
    assert hermes["capabilities"]["workingMemory"] is False
    assert hermes["capabilities"]["distill"] is False
    assert hermes["autonomy"]["threads"] == "automatic-capture"
    assert "hooks: []" in manifest
