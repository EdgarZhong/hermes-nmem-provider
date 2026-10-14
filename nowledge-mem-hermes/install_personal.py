#!/usr/bin/env python3
"""Install this checkout into an explicit Hermes home; default is a dry run."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

FILES = ("__init__.py", "plugin.yaml", "provider.py", "client.py", "skill_outcome.py",
         "personal_provider.py", "personal_client.py", "personal_scope.py", "personal_cli.py")


def load_config(text):
    import yaml
    class UniqueLoader(yaml.SafeLoader):
        pass
    def unique(loader, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if key in result:
                raise ValueError(f"Duplicate configuration key: {key}")
            result[key] = loader.construct_object(value_node, deep=deep)
        return result
    UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique)
    value = yaml.load(text, Loader=UniqueLoader) if text.strip() else {}
    if not isinstance(value, dict):
        raise ValueError("Hermes config must be an object")
    memory = value.get("memory", {})
    if not isinstance(memory, dict):
        raise ValueError("memory config must be an object")
    if memory.get("provider") not in (None, "", "default", "builtin", "built-in", "none", "nowledge-mem"):
        raise ValueError("Another memory provider is selected; refusing to replace it")
    value["memory"] = {**memory, "provider": "nowledge-mem", "memory_enabled": False, "user_profile_enabled": False}
    return value


def install(home: Path, *, apply=False, source=None):
    import yaml
    home = home.expanduser().resolve()
    if home == Path(home.anchor):
        raise ValueError("Refusing filesystem-root Hermes home")
    source = Path(source or Path(__file__).parent)
    for name in FILES:
        if not (source / name).is_file():
            raise ValueError(f"Incomplete plugin checkout: {name}")
    config_path = home / "config.yaml"
    text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    config = load_config(text)
    target = home / "plugins" / "nowledge-mem"
    if not apply:
        return {"status": "preview", "writes": 0, "plugin_dir": str(target),
                "memory": {k: config["memory"][k] for k in ("provider", "memory_enabled", "user_profile_enabled")}, "note": "Existing credentials, other settings and MD files will be retained."}
    home.mkdir(parents=True, exist_ok=True)
    backup = home / ("personal-nm-backup-" + str(time.time_ns()))
    backup.mkdir(mode=0o700)
    if config_path.exists():
        shutil.copy2(config_path, backup / "config.yaml")
    if target.exists():
        shutil.copytree(target, backup / "plugin")
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".personal-nm-", dir=target.parent))
    previous = target.parent / (".personal-nm-old-" + str(time.time_ns()))
    tmp_config = home / (".config-personal-nm-" + str(time.time_ns()))
    try:
        for name in FILES:
            shutil.copy2(source / name, stage / name)
        shutil.copytree(source / "skills", stage / "skills")
        tmp_config.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
        os.chmod(tmp_config, 0o600)
        if target.exists():
            target.rename(previous)
        stage.rename(target)
        try:
            os.replace(tmp_config, config_path)
        except Exception:
            shutil.rmtree(target)
            if previous.exists():
                previous.rename(target)
            raise
        if previous.exists():
            shutil.rmtree(previous)
    except Exception:
        if previous.exists() and not target.exists():
            previous.rename(target)
        raise
    finally:
        if stage.exists():
            shutil.rmtree(stage)
        if tmp_config.exists():
            tmp_config.unlink()
    return {"status": "installed", "plugin_dir": str(target), "backup": str(backup),
            "note": "Restart Hermes. No live NM data or Background Intelligence settings were changed."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    print(json.dumps(install(args.home, apply=args.apply), ensure_ascii=False))


if __name__ == "__main__":
    main()
