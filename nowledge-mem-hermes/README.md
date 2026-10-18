# Personal Hermes — Nowledge Mem Provider

This is the **EdgarZhong Personal Hermes fork** of the official `nowledge-co/community/nowledge-mem-hermes` integration. It is not an upstream Nowledge release. Provider version: **0.6.0**. Original transport and normalization helpers remain in `client.py`, `provider.py` and `skill_outcome.py`; `personal_*.py` implements this fork's policy.

## One provider, three responsibilities

| Runtime | Static NM Context Bundle | Turn-start memory pointer index | Completed-turn Thread sync |
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
skills:
  external_dirs:
    - plugins/nowledge-mem/skills
```

The installer appends this profile-relative native skill root without replacing other skill settings, so `nm-cli` is discoverable in new root prompts and `skill_view`. Metadata HTTP requests also require a native `curl` executable; they use its default transport, keep secrets off command arguments, and fail explicitly if it is unavailable.

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

Existing `space_by_identity` and `space_template` resolution is retained. This fork deliberately ignores ambient `NMEM_SPACE`/`NMEM_SPACE_ID` for per-profile determinism; if none resolves, the provider passes an explicit empty space so the HTTP and CLI clients consistently use the NM default. An explicit empty `space` has the same effect. The API connection URL must be the usable NM API base, not a website login URL.

`system_prompt_block()` uses the official `context read --source-app hermes --no-working-memory` CLI, including the bound Space, and never falls back to `wm read`. Each native root-prompt build or actual rebuild fetches the Bundle once; the host owns assembled-root caching/restoration. The Provider adds no per-Thread cache that could outlive a compression rebuild. Noting may inherit the parent's already-frozen prompt under the existing cache-parity contract; it does not independently run this Provider.

`prefetch()` performs normal `nmem --json m search`, including short Chinese queries. It returns only intact IDs, titles and available dates, plus the short keyword anchor `Memory check: use nmem CLI if needed.` The detailed recall policy lives once in the static system prompt; the anchor only links the per-turn payload to that policy. It does not inject full Memory bodies, reuse stale query results, or report pointers as memories already read. Host trivial-prompt skipping and historical `api_content` replay are unchanged.

## Profile → NM space binding

Spaces are managed in NM; Hermes profiles are managed in Hermes. The link is one profile-scoped provider config file:

```json
// $HERMES_HOME/nowledge-mem.json
{"space": "Work"}
```

- The plugin receives the current profile's `hermes_home` from the host and reads that home's `nowledge-mem.json`; no central profile map or profile-name parsing is required.
- `space` is a visible NM space name or alias. An explicit empty string (`"space": ""`) or an omitted value uses the NM **Default** space.
- Hermes `profile create --clone` already copies `<provider>.json` into the new profile, so the binding travels with the clone; edit the clone's file to point at a different space.
- A newly created NM space is empty; existing Memories/Threads remain in Default until moved explicitly.
- NM connection URL/key remain global (`~/.nowledge-mem/config.json` / `NMEM_API_URL` / `NMEM_API_KEY`). A profile can select a different space, not a different NM account.

The provider's Bundle, recall client and Thread client are all constructed with the resolved space. For the agent's **manual** `nmem` commands, there is no wrapper: the system prompt's `Active space` section requires explicit `--space "<space>"` on every command and forbids access to another space unless the user explicitly asks. Without that prompt constraint, ambient CLI state could target another lane.

The provider requires a profile with the `terminal` tool (to run `nmem`) and the `memory` toolset (Hermes gates the provider prompt block through it). It does not register model-callable NM tools, MCP, or a fallback reader.

## Thread capture and recovery

The modern Hermes `MemoryManager` runs `sync_turn()` on its serialized background worker. This fork relies on that host contract, as the current official synchronous sync implementation does; older hosts that invoke it inline are not supported for latency guarantees. Do not register a second `post_llm_call` fallback.

Interactive Secretary sessions use a **read-only** existing `secretary_session_bindings` lookup and the host's canonical History Foreground. Physical compaction continuations with the same Conversation Ref share an archive. No new Secretary identity is minted. Ordinary Hermes and standalone cron use their own Session identity. Thread IDs are namespaced `hermes-personal-<identity>` so the fork does not overwrite archives produced by the old integration.

Only user/assistant prose and normalized timestamps are archived. Tool results, hidden/Noting scaffolding and recognized compaction summaries are excluded. This is **not a full tool/multimodal execution trace**. Hermes `state.db` remains authoritative and must be backed up.

Acknowledged transcript fingerprints are stored under `$HERMES_HOME/nowledge-mem-personal/receipts.sqlite3`; no transcript bodies or credentials are stored there. Only an affirmative JSON success acknowledgement advances the cursor; malformed, ambiguous, negative or mismatched Thread responses leave it unchanged. A subsequent completed turn retries. Session-end only retries the last snapshot already admitted by the completed-turn hook; it never admits an interrupted closing tail. Resuming retries at the next completed turn. A first batch uses official `threads import --file`; subsequent suffix imports carry the acknowledged message count and a stable idempotency key. A timeout after server commit can still cause an at-least-once retry; exactly-once delivery is not claimed.

An edit/rewind that changes an already-archived prefix is deliberately **not silently appended or overwritten**. Sync returns and logs reconciliation-required; explicit archive reconciliation is a deployment operation, not yet implemented here. Unsupported combined summary/user carriers on non-Secretary hosts are not claimed lossless. Scope failures deny that observation rather than guess. Independent cron sync is allowed, but cron children remain excluded.

## Approved Memory creation and exact provenance

Normal reading, editing and management use official `nmem`. The narrow helper
creates through official CLI, takes its actual returned ID, then attaches only
`metadata.hermes_provenance` to that same Memory. Main supplies approved natural
language content, native `notebook:<type>` labels and exact sources. Read original
evidence with `conversation_history`; pointer titles and NM Threads are not the
originals. `/propose-persistence`, a capacity notice or `--apply` is not approval.

```json
{"version":1,"sources":[{"conversation_ref":"<actual Ref>","message_uid":"<actual UID>"}]}
```

```bash
# Preview: no CLI/network calls. Always pass the profile's bound space explicitly.
python3 "$HERMES_HOME/plugins/nowledge-mem/personal_cli.py" create \
  --space 'Work' \
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

Current target-service limitation: an authorized metadata-only PATCH on an existing synthetic Memory was accepted but ignored `hermes_provenance`; a subsequent GET confirmed the attachment was absent while the original fields were unchanged. The helper correctly reported `partial`. Metadata persistence is **not verified or complete**; do not treat HTTP success, a created Memory, or skill discovery as complete provenance delivery. The exact supported update contract remains unresolved; see root [CLAUDE.md](../CLAUDE.md) for the current evidence and deployment state.

## Tests and boundaries

```bash
# Run from this repository root; keep the Hermes PM interpreter and canonical runner.
mkdir -p temp-r3-personal/runner
for name in test_personal test_security test_r3_provider test_r3_thread; do
  ln -sfn "$PWD/nowledge-mem-hermes/personal_tests/$name.py" "temp-r3-personal/runner/$name.py"
done
HERMES_PYTHON="$PWD/../hermes-secretary/.venv/bin/python" \
  PYTHONPATH="$PWD/../hermes-secretary" \
  ../hermes-secretary/scripts/run_tests.sh "$PWD/temp-r3-personal/runner/" -q
```

The ignored source symlinks avoid pytest treating the hyphenated plugin directory as an importable package; each test still resolves its original source location. The canonical runner isolates each file in its own process. Current local verification (2026-10-17): 4 personal files **95 PASS**; upstream `test_release_contract` + `test_space_resolution` **16 PASS**. No real NM was contacted. The P1 tests load retained upstream helpers with an ABC fixture. The P3 tests use real Hermes SessionDB, canonical History and MemoryManager egress/background sync with a disposable local HTTP server. The maintained personal/security tests cover the current policy and narrow metadata smoke checks. Runtime databases live in this checkout's ignored `temp-r3-personal/` tree; they do not access a real profile or NM account. Other upstream suites are not the personal policy contract. See [docs/TEST_REPORT.md](docs/TEST_REPORT.md) for historical baseline evidence only; actual run versions and coverage are recorded in root [CLAUDE.md](../CLAUDE.md).

公共History由 **EdgarZhong/hermes-secretary** 的新版 `conversation_history` 承担，原生 `session_search` 保留。本插件不monkey-patch Core工具；旧PHASE3的session_search改造计划已撤销。

Earlier real Thread/Bundle samples and the current failed Metadata attachment are recorded separately in root CLAUDE.md; server deduplication beyond those samples and cloud deployment remain unverified
and unauthorized in this round. An ordinary host run may auto-sync Threads; always
select a local fixture endpoint before isolated development, never a real account
for a supposedly read-only trial. The native finalizer must admit only completed,
uninterrupted, nonfailed turns; public host verdict wiring belongs to Secretary.
