#!/usr/bin/env bash
# Personal fork installer contract. All writes stay in this disposable directory.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT
export HERMES_HOME="$TEMP/profile with spaces"
mkdir -p "$HERMES_HOME"
printf 'model: keep-this-model\nmemory:\n  nudge_interval: 17\n' > "$HERMES_HOME/config.yaml"
printf 'preserve user-owned memory\n' > "$HERMES_HOME/USER.md"

python3 "$ROOT/install_personal.py" --home "$HERMES_HOME" > "$TEMP/preview.json"
test ! -e "$HERMES_HOME/plugins"
python3 - "$TEMP/preview.json" <<'PY'
import json,sys
assert json.load(open(sys.argv[1]))['status']=='preview'
PY
bash "$ROOT/setup.sh" > "$TEMP/installed.json"
python3 - "$HERMES_HOME" "$TEMP/installed.json" <<'PY'
import json,sys,yaml
from pathlib import Path
home=Path(sys.argv[1]); result=json.load(open(sys.argv[2]))
assert result['status']=='installed'
cfg=yaml.safe_load((home/'config.yaml').read_text())
assert cfg['model']=='keep-this-model'
assert cfg['memory']=={'nudge_interval':17,'provider':'nowledge-mem','memory_enabled':False,'user_profile_enabled':False}
assert (home/'USER.md').read_text()=='preserve user-owned memory\n'
assert (Path(result['backup'])/'config.yaml').is_file()
for name in ['__init__.py','personal_provider.py','personal_client.py','personal_scope.py','personal_cli.py','client.py','provider.py']:
    assert (home/'plugins'/'nowledge-mem'/name).is_file(),name
assert (home/'plugins/nowledge-mem/skills/nm-cli/SKILL.md').is_file()
PY
# Reinstall is configuration-idempotent and still preserves MD files.
cp "$HERMES_HOME/config.yaml" "$TEMP/before.yaml"
bash "$ROOT/setup.sh" > "$TEMP/reinstalled.json"
cmp "$HERMES_HOME/config.yaml" "$TEMP/before.yaml"

export HERMES_HOME="$TEMP/conflicting-provider"
mkdir -p "$HERMES_HOME"
printf 'memory:\n  provider: different-provider\n' > "$HERMES_HOME/config.yaml"
cp "$HERMES_HOME/config.yaml" "$TEMP/conflict-before.yaml"
if bash "$ROOT/setup.sh" > "$TEMP/conflict.out" 2>&1; then
  echo 'Expected a conflicting provider to be refused' >&2
  exit 1
fi
cmp "$HERMES_HOME/config.yaml" "$TEMP/conflict-before.yaml"
test ! -e "$HERMES_HOME/plugins"
echo 'Personal Bash installer: preview, staged install, backup, repeat and conflict checks passed.'
