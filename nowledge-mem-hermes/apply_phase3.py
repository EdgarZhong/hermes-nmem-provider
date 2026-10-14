#!/usr/bin/env python3
"""Deterministic, fork-only activation of the reviewed Personal Hermes policy.

Changes one integrations.json object and the Hermes integration's own assets.
No user profile, running NM service, upstream repository or package registry is touched.
"""
from pathlib import Path
import json
import re

VERSION = '0.6.0'
ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'nowledge-mem-hermes'
FORK = 'EdgarZhong/hermes-nmem-provider'


def activate():
    # Repository contract: registry is updated before runtime/version-bearing assets.
    path = ROOT / 'integrations.json'
    original = path.read_text(encoding='utf-8')
    marker = re.search(r'"id"\s*:\s*"hermes"', original)
    if not marker:
        raise RuntimeError('Hermes integration registry entry is absent')
    start = original.rfind('{', 0, marker.start())
    entry, length = json.JSONDecoder().raw_decode(original[start:])
    if entry.get('id') != 'hermes':
        raise RuntimeError('Ambiguous registry entry')
    entry['version'] = VERSION
    entry['transport'] = 'cli'
    entry.setdefault('capabilities', {}).update(workingMemory=False, distill=False, autoRecall=True, autoCapture=True)
    entry.setdefault('autonomy', {}).update(bootstrap='automatic', recall='automatic', distill='manual', threads='automatic-capture')
    entry['autonomy']['bestResultRequires'] = [
        'Use the Personal Hermes fork installer and keep NM Background Intelligence disabled',
        'Keep nmem available; agent-controlled NM operations use CLI, not MCP or provider function tools',
        'Main conversations receive static Context Bundle without Working Memory and lightweight turn-start candidates',
        'Only main conversations and independent cron main Sessions are captured; auxiliary/delegate/Noting Sessions are excluded',
        'Memory mutations require existing Secretary approval and validated Hermes source identities']
    entry['toolNaming'] = {'convention': 'cli-direct', 'note': 'Single native Memory Provider; no nmem_* function schemas. Context Bundle, candidate recall and scoped Thread sync share one provider.'}
    command = 'python3 nowledge-mem-hermes/install_personal.py --home "$HERMES_HOME" --apply'
    entry.setdefault('install', {}).update(command=command, updateCommand=command,
        detectionHint='Personal Hermes fork checkout; explicit HERMES_HOME',
        agentGuide={'prompt':'Use the fork README and PHASE3.md; preview install first, preserve user config, do not enable NM background intelligence.',
                    'promptZh':'按本 fork 的 README 与 PHASE3.md 安装；先预览并保留用户配置，不启用 NM 后台智能。'})
    entry['threadSave'] = {'method':'native-hooks','runtime':'hermes','note':'sync_turn acknowledged incremental archive; main + standalone cron only; no automatic Memory distillation.'}
    entry['skills'] = ['nm-cli']
    entry['slashCommands'] = []
    rendered = json.dumps(entry, ensure_ascii=False, indent=2).splitlines()
    replacement = rendered[0] + '\n' + '\n'.join('    '+line for line in rendered[1:])
    updated = original[:start] + replacement + original[start+length:]
    # Prove no other integration's meaning changed.
    before, after = json.loads(original), json.loads(updated)
    old_others = [x for x in before['integrations'] if x.get('id') != 'hermes']
    new_others = [x for x in after['integrations'] if x.get('id') != 'hermes']
    assert old_others == new_others
    path.write_text(updated, encoding='utf-8')
    (PLUGIN/'__init__.py').write_text('''"""Personal Hermes: one native NM Memory Provider, no duplicate general-hook sync."""
from pathlib import Path
from .personal_provider import PersonalNowledgeMemProvider


def register(ctx):
    if hasattr(ctx, "register_memory_provider"):
        ctx.register_memory_provider(PersonalNowledgeMemProvider())
        if hasattr(ctx, "register_skill"):
            ctx.register_skill("nm-cli", Path(__file__).parent / "skills" / "nm-cli" / "SKILL.md",
                               "Read NM via CLI and prepare approved memory changes")
    # General-plugin discovery can visit the same directory. Deliberately no fallback
    # post_llm_call hook: it lacks reliable scope and would double-capture native turns.
''',encoding='utf-8')
    (PLUGIN/'plugin.yaml').write_text('''name: nowledge-mem
version: 0.6.0
description: "Personal Hermes: static Context Bundle, lightweight recall, scoped Thread sync; CLI-first."
hooks: []
author: "Nowledge Labs; Personal Hermes fork"
''',encoding='utf-8')
    (PLUGIN/'AGENTS.md').write_text('''# Personal Hermes NM Provider

The user-approved PHASE3.md overrides the inherited upstream behavioral guidance.

- Keep one Memory Provider. Do not add MCP or nmem_* model tools.
- NM Background Intelligence stays OFF; no automatic distillation or proactive Memory writes.
- Main conversations: static Context Bundle without Working Memory, turn-start candidates, thread sync.
- Standalone cron main Sessions: thread sync only. Noting/delegate/subagent/review/other backgrounds: none.
- Preserve upstream client/provider helpers. Personal policy lives in personal_*.py, registered from __init__.py.
- Original Hermes evidence is addressed by (conversation_ref, message_uid), stored in metadata.hermes_provenance.
- Respect existing Secretary approval. The CLI --apply flag is not an authorization capability.
- Run python3 -m unittest discover -s nowledge-mem-hermes/personal_tests -v.
- Do not modify user profiles, real NM data, other integrations or publish registries during tests.
- session_search changes belong in the separate Secretary Core repository; this plugin does not monkey-patch it.
''',encoding='utf-8')
    (PLUGIN/'setup.sh').write_text('''#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -f "$HERE/install_personal.py" ]]; then
  echo "Clone EdgarZhong/hermes-nmem-provider and run this script from that checkout." >&2
  exit 1
fi
exec python3 "$HERE/install_personal.py" --home "${HERMES_HOME:-$HOME/.hermes}" --apply "$@"
''',encoding='utf-8')
    (PLUGIN/'setup.ps1').write_text('''$ErrorActionPreference = "Stop"
$homeDir = $env:HERMES_HOME
if (-not $homeDir) { $homeDir = Join-Path $env:LOCALAPPDATA "hermes" }
python (Join-Path $PSScriptRoot "install_personal.py") --home $homeDir --apply @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
''',encoding='utf-8')
    changelog = PLUGIN/'CHANGELOG.md'
    text = changelog.read_text(encoding='utf-8')
    header = '''# Personal Hermes 0.6.0 — 2026-10-14

Fork-only delivery, based on official Hermes Provider 0.5.24. No npm/PyPI/marketplace publication.

- Register one CLI-first policy Provider; retain upstream transport and normalization helpers.
- Exclude Working Memory; freeze stable Context Bundle; remove proactive-save and nmem tool guidance.
- Query-centered turn-start candidate pointers, bounded timeout/output; no queue_prefetch.
- Main + independent cron main Thread capture; deny background/delegate/Noting Sessions.
- Profile-scoped acknowledgement cursor; retry unacknowledged data; refuse divergent rewritten history.
- Hermes source identities stored in Memory metadata via preview-first CLI helper with readback verification.
- Explicit-home installer, unchanged MD backups, configuration preservation, policy and HTTP fixture tests.
- Live Hermes/NM acceptance remains a separate deployment step; see docs/TEST_REPORT.md.

---

'''
    if not text.startswith('# Personal Hermes 0.6.0'):
        changelog.write_text(header+text,encoding='utf-8')


if __name__=='__main__': activate()
