# Personal Hermes — Nowledge Mem Provider

This is the **EdgarZhong Personal Hermes fork** of the official `nowledge-co/community/nowledge-mem-hermes` integration. It is not an upstream Nowledge release. Provider version: **0.6.0**. Original transport and normalization helpers remain in `client.py`, `provider.py` and `skill_outcome.py`; `personal_*.py` implements this fork's policy.

## One provider, three responsibilities

| Runtime | Static NM Context Bundle | Turn-start candidate index | Completed-turn Thread sync |
|---|---|---|---|
| Interactive main Conversation | Yes, without Working Memory | Yes | Yes |
| Independent cron task's own main Session | No | No | Yes |
| Noting, delegate/subagent, review and other auxiliary runtimes | No | No | No |

No NM MCP server. No `nmem_*` model tools. No `queue_prefetch`, automatic distillation, MD mirroring or managed-skill outcome reporting. Agent-controlled NM operations use the existing terminal and `nmem` CLI. Background Intelligence must stay **disabled in NM itself**; this plugin does not change that setting.

Notebook/Noting owns the current Conversation's working state. NM owns durable personal knowledge and user-managed personal context. Memory mutation still requires the existing Secretary approval mechanism. Full design: [docs/PHASE3.md](docs/PHASE3.md).

## Install from this fork

Use Python from your Hermes environment (the host's locked `ruamel.yaml` is used by the installer). Do not run the upstream curl installer, which would replace this fork with upstream policy.

```bash
git clone https://github.com/EdgarZhong/hermes-nmem-provider.git
cd hermes-nmem-provider
# Preview: no user profile or NM writes.
python3 nowledge-mem-hermes/install_personal.py --home "$HOME/.hermes"
# Install only after reviewing the preview.
python3 nowledge-mem-hermes/install_personal.py --home "$HOME/.hermes" --apply
```

For another Hermes profile, supply its actual home. Windows uses the same Python installer with an explicit `--home`, or the checkout's `setup.ps1`. The installer backs up the previous plugin and config, preserves other configuration, does not delete MEMORY.md/USER.md, and sets:

```yaml
memory:
  provider: nowledge-mem
  memory_enabled: false
  user_profile_enabled: false
```

Do **not** disable the whole `memory` toolset: some Hermes versions also gate external provider Prompt blocks through it. Restart Hermes after install. New conversations load the new prompt; an already-pinned old root prompt may require a normal host rebuild/new conversation. The installer does not rewrite old conversation prompts or enable background intelligence.

## Configuration

Connection credentials and URL stay in the normal `nmem` client configuration. No secrets in command arguments. The plugin's optional `$HERMES_HOME/nowledge-mem.json` controls policy budgets and the existing NM lane:

```json
{
  "timeout": 8,
  "recall_timeout": 2,
  "recall_limit": 5,
  "recall_max_chars": 2400,
  "space": "",
  "agent_identity": ""
}
```

Existing `space_by_identity`, `space_template`, `NMEM_SPACE` and legacy `NMEM_SPACE_ID` resolution are retained. Leave `space` out to use the existing ambient fallback; an explicit empty `space` uses the NM default. The API connection URL must be the usable NM API base, not a website login URL.

`system_prompt_block()` requests `/context/bundle?include_working_memory=false` and never falls back to `wm read`. Each native root-prompt build or actual rebuild fetches the Bundle once; the host owns assembled-root caching/restoration. The Provider adds no per-Thread cache that could outlive a compression rebuild. Noting may inherit the parent's already-frozen prompt under the existing cache-parity contract; it does not independently run this Provider.

`prefetch()` performs normal `nmem --json m search`, including short Chinese queries. It returns only intact IDs, titles and available dates, plus a context-sufficiency reminder. It does not inject full Memory bodies, reuse stale query results, or report candidates as memories already read. Host trivial-prompt skipping and historical `api_content` replay are unchanged.

## Thread capture and recovery

The modern Hermes `MemoryManager` runs `sync_turn()` on its serialized background worker. This fork relies on that host contract, as the current official synchronous sync implementation does; older hosts that invoke it inline are not supported for latency guarantees. Do not register a second `post_llm_call` fallback.

Interactive Secretary sessions use a **read-only** existing `secretary_session_bindings` lookup and the host's canonical History Foreground. Physical compaction continuations with the same Conversation Ref share an archive. No new Secretary identity is minted. Ordinary Hermes and standalone cron use their own Session identity. Thread IDs are namespaced `hermes-personal-<identity>` so the fork does not overwrite archives produced by the old integration.

Only user/assistant prose and normalized timestamps are archived. Tool results, hidden/Noting scaffolding and recognized compaction summaries are excluded. This is **not a full tool/multimodal execution trace**. Hermes `state.db` remains authoritative and must be backed up.

Acknowledged transcript fingerprints are stored under `$HERMES_HOME/nowledge-mem-personal/receipts.sqlite3`; no transcript bodies or credentials are stored there. Only an affirmative JSON success acknowledgement advances the cursor; malformed, ambiguous, negative or mismatched Thread responses leave it unchanged. A subsequent completed turn retries. Session-end only retries the last snapshot already admitted by the completed-turn hook; it never admits an interrupted closing tail. Resuming retries at the next completed turn. HTTP timeout after server commit can still cause an at-least-once retry; append requests retain the existing deduplicate flag; actual server deduplication has not been verified, and exactly-once delivery is not claimed.

An edit/rewind that changes an already-archived prefix is deliberately **not silently appended or overwritten**. Sync returns and logs reconciliation-required; explicit archive reconciliation is a deployment operation, not yet implemented here. Unsupported combined summary/user carriers on non-Secretary hosts are not claimed lossless. Scope failures deny that observation rather than guess. Independent cron sync is allowed, but cron children remain excluded.

## Approved Memory creation and exact provenance

Normal reading, editing and management use official `nmem`. The narrow helper
creates through official CLI, takes its actual returned ID, then attaches only
`metadata.hermes_provenance` to that same Memory. Main supplies approved natural
language content, native `notebook:<type>` labels and exact sources. Read original
evidence with `conversation_history`; candidate titles and NM Threads are not the
originals. `/propose-persistence`, a capacity notice or `--apply` is not approval.

```json
{"version":1,"sources":[{"conversation_ref":"<actual Ref>","message_uid":"<actual UID>"}]}
```

```bash
# Preview: no CLI/network calls.
python3 "$HERMES_HOME/plugins/nowledge-mem/personal_cli.py" create \
  --content-file approved.md --provenance-file provenance.json \
  --title 'Approved understanding' --label 'notebook:situation'
# Execute the specific approved content/destination by adding --apply.
# If creation succeeded but attachment failed, use the returned actual ID:
python3 "$HERMES_HOME/plugins/nowledge-mem/personal_cli.py" attach ACTUAL_ID \
  --provenance-file provenance.json --apply
```

Connection uses the running host's existing NM configuration. A one-off
`--api-url` comes before `create`/`attach` and is shared by CLI and Metadata HTTP;
use the same destination during repair. Credentials never enter command arguments
or diagnostics. Metadata attachment preserves unrelated fields from its read.
These two steps are not atomic: `partial` retains the created ID, while
`creation_unknown` must be investigated through official CLI before any new write.
Repair never creates again. The previous `read`/`write`/expected-SHA/History
membership protocol is removed. See the installed [nm-cli skill](skills/nm-cli/SKILL.md)
for exact statuses and the small-script basic-check boundary.

## Tests and boundaries

```bash
# Use the Hermes PM interpreter; Thread integration needs Hermes on PYTHONPATH.
/path/to/hermes/.venv/bin/python -m unittest discover -s nowledge-mem-hermes/personal_tests -p 'test_r3_provider.py' -v
PYTHONPATH=/path/to/hermes /path/to/hermes/.venv/bin/python -m unittest discover -s nowledge-mem-hermes/personal_tests -p 'test_r3_thread.py' -v
```

The P1 tests load retained upstream helpers with an ABC fixture. The P3 tests use real Hermes SessionDB, canonical History and MemoryManager egress/background sync with a disposable local HTTP server. Runtime databases live in this checkout's ignored `temp-r3-personal/` tree. They do not access a real profile or NM account. The upstream suite targets the old policy and is retained for reference; the R3 policy is tested separately; old personal helper and Bundle-cache assertions require retirement before running the historical whole-directory suite. See [docs/TEST_REPORT.md](docs/TEST_REPORT.md) for historical baseline evidence only; current R3 status and evidence locations are in the repository root [CLAUDE.md](../CLAUDE.md).

公共History由 **EdgarZhong/hermes-secretary** 的新版 `conversation_history` 承担，原生 `session_search` 保留。本插件不monkey-patch Core工具；旧PHASE3的session_search改造计划已撤销。

Real NM writes, real server ACK/deduplication and cloud deployment remain unverified
and unauthorized in this round. An ordinary host run may auto-sync Threads; always
select a local fixture endpoint before isolated development, never a real account
for a supposedly read-only trial. The native finalizer must admit only completed,
uninterrupted, nonfailed turns; public host verdict wiring belongs to Secretary.
