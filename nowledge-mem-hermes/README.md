# Personal Hermes — Nowledge Mem Provider

This is the **EdgarZhong Personal Hermes fork** of the official `nowledge-co/community/nowledge-mem-hermes` integration. It is not an upstream Nowledge release. Provider version: **0.6.0**. Original transport and normalization helpers remain in `client.py`, `provider.py` and `skill_outcome.py`; `personal_*.py` implements this fork's policy.

## One provider, three responsibilities

| Runtime | Static NM Context Bundle | Turn-start memory pointer index | Completed-turn Thread sync |
|---|---|---|---|
| Interactive main Conversation | Yes, without Working Memory | Yes | Yes |
| Independent cron task's own main Session | No | No | Yes |
| Noting, delegate/subagent, review and other auxiliary runtimes | No | No | No |

No NM MCP server. No `nmem_*` model tools. No `queue_prefetch`, automatic distillation, MD mirroring or managed-skill outcome reporting. Approved Memory creation uses the existing narrow helper through terminal; other permitted NM operations use official `nmem` CLI. Background Intelligence must stay **disabled in NM itself**; this plugin does not change that setting.

Notebook/Noting owns the current Conversation's working state. NM owns durable personal knowledge and user-managed personal context. Memory mutation still requires the existing Secretary approval mechanism. Full design: [docs/PHASE3.md](docs/PHASE3.md).

## Install from this fork

Use Python from your Hermes environment (the host's locked `ruamel.yaml` is used by the installer). Do not run the upstream curl installer, which would replace this fork with upstream policy.

First obtain this checkout (or enter your existing checkout):

```bash
git clone https://github.com/EdgarZhong/hermes-nmem-provider.git
cd hermes-nmem-provider
```

The Memory creation tool is independent of Hermes: standard Python plus the running
host's official `nmem` CLI and native `curl`, with no Python packages to install.
For a first installation, place the single file at the same path on this Mac and the cloud host
(`scripts` is the intended spelling). Existing prepared tools are protected originals:
do not overwrite, delete, unlock or bypass protection without explicit maintenance authorization.
Read the source before extending it; use a separate `~/scripts/custom/` copy marked unaccepted.

```bash
mkdir -p "$HOME/scripts"
install -m 555 nowledge-mem-hermes/nmem_memory.py "$HOME/scripts/nmem-memory.py"
python3 ~/scripts/nmem-memory.py create --help
```

Keep each host's existing NM configuration and credentials there; do not copy credentials
from the development machine. The script body is not a user configuration file and needs
no dotfiles symlink or global shell change. The following plugin install is separate.

```bash
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

The Provider directly supplies the creation instruction in its system prompt; this fork does not register or install an `nm-cli` Skill or append a native skill root. Other skill configuration is retained. Metadata HTTP requests also require a native `curl` executable; they use its default transport, keep secrets off command arguments, and fail explicitly if it is unavailable.

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

By default the provider's Bundle, recall client and Thread client use the resolved `space`. An optional `thread_sync_space` string overrides only automatic Thread synchronization; Bundle, recall and the model's Active space keep using `space`. For the agent's **manual** `nmem` commands, there is no wrapper: the system prompt's `Active space` section requires explicit `--space "<space>"` on every command and forbids access to another space unless the user explicitly asks. Without that prompt constraint, ambient CLI state could target another lane.

For an explicitly requested independent automatic Thread target, the configuration syntax is:

```json
{"space": "考研复习", "thread_sync_space": "default"}
```

`thread_sync_space` accepts the existing NM Space names/aliases and Default; an explicit empty string also selects Default and clears ambient Space state. Omit the key to inherit `space` and preserve the exact legacy receipt key, including the distinction between unresolved `null`, blank and named Default. A present non-string value (including JSON `null`) rejects initialization safely. This optional override is configured directly in the profile JSON; the existing setup form is unchanged. It applies at initialization, with no live switching or migration of old Threads, receipts or Memories. The selected synchronization Space is used consistently for uploads, readback, fork anchors, pending writes, receipts and cold-instance observations. It does not change manual Memory targets, approval rules or any model prompt. With an explicit override and no matching local ledger, an exact-ID read must confirm remote absence before the first import. An existing Thread (in any Space) or an inconclusive lookup pauses sync instead of adopting or moving it. This read uses the existing client transport; no new migration path is introduced. The read-before-import check is not an atomic server-side create reservation.

The provider requires a profile with the `terminal` tool (to run `nmem`) and the `memory` toolset (Hermes gates the provider prompt block through it). It does not register model-callable NM tools, MCP, or a fallback reader.

## NM Thread synchronization and fork continuation

The modern Hermes `MemoryManager` runs `sync_turn()` on its serialized background worker. This fork relies on that host contract, as the current official synchronous sync implementation does; older hosts that invoke it inline are not supported for latency guarantees. Do not register a second `post_llm_call` fallback.

Interactive Secretary sessions use a **read-only** existing `secretary_session_bindings` lookup and the host's canonical History Foreground. Physical compaction continuations with the same Conversation Ref continue the same NM Thread branch. No new Secretary identity is minted. Ordinary Hermes and standalone cron use their own Session identity. Initial Thread IDs are namespaced `hermes-personal-<identity>`; later History forks create separate NM Threads without overwriting earlier ones.

Only user/assistant prose and normalized timestamps are synchronized. Tool results, hidden/Noting scaffolding and recognized compaction summaries are excluded. A new fork Thread starts with a plugin-generated system message explaining its continuation. This is **not a full tool/multimodal execution trace**. Hermes `state.db` remains authoritative and must be backed up.

Acknowledged transcript fingerprints, branch locators and pending upload intent are stored under `$HERMES_HOME/nowledge-mem-personal/receipts.sqlite3`; no transcript bodies or credentials are stored there. Only an affirmative JSON success acknowledgement or matching same-Thread readback advances the cursor. Pending writes with unknown results are confirmed through read-only official CLI calls before any further upload; they are not blindly replayed. Session-end only uses the last snapshot already admitted by the completed-turn hook, never an interrupted closing tail. A first batch uses official `threads import --file`; subsequent suffix imports carry the acknowledged remote message count, including any continuation header, and a stable idempotency key. Global exactly-once delivery is not claimed.

When an edit/rewind changes an already-synchronized prefix, the plugin finds the longest shared prefix and creates a new NM Thread. Its first message identifies the preceding NM Thread and the last shared message by its real NM Message ID and owning NM Thread; subsequent messages contain only the divergent suffix. Common content is not uploaded again, earlier Threads remain intact, and later turns append to the current branch. An empty suffix waits for a real new message. An unconfirmed native anchor, wrong Space or unknown write pauses synchronization without inventing an ID or creating another replacement Thread. Unsupported combined summary/user carriers on non-Secretary hosts are not claimed lossless. Scope failures deny that observation rather than guess. Independent cron sync is allowed, but cron children remain excluded.

## Approved Memory creation and exact provenance

Other permitted operations, including approved edits to ordinary Memory fields, use official `nmem`; only incorrect creation metadata requires specifically approved deletion followed by fresh creation. The independent single-file tool
sends one official `POST /memories` with the approved body, title, labels, exact Space and
arbitrary Metadata object; it never creates through CLI first or automatically
retries. It does not recognize Main, query History or import any Hermes module. The Hermes caller supplies approved natural language content, native `notebook:<type>` labels and exact sources in `metadata.hermes_provenance`. Read original
evidence with `conversation_history`; pointer titles and NM Threads are not the
originals. `/propose-persistence`, a capacity notice or `--apply` is not approval.

```json
{"hermes_provenance":{"version":1,"sources":[{"conversation_ref":"<actual Ref>","message_uid":"<actual UID>"}]}}
```

```bash
# Preview: no CLI/network calls. Always pass the profile's bound space explicitly.
python3 ~/scripts/nmem-memory.py create \
  --space 'Work' \
  --content-file approved.md --metadata-file metadata.json \
  --title 'Approved understanding' --label 'notebook:situation'
# Execute the specific approved content/destination by adding --apply.
```

Both preview and apply require explicit nonempty `--space`; use `--space default`
for Default. Missing, empty and whitespace-only selectors fail before file/configuration
reads or CLI/network calls. The tool never infers a destination from a Profile or ambient Space.

Connection uses the running host's existing NM configuration. A one-off
`--api-url` comes before `create`. The resolved endpoint/key are pinned
for official CLI reads and the existing HTTP transport. The CLI resolves the
selected Space name/alias to its real stored ID; ambient Space variables do not
override the chosen destination. Credentials never enter arguments or diagnostics.
Creation uses the documented 32,768-character body / 200-character title limits.
`--metadata-file` accepts any JSON object (including `{}`); the tool does not
interpret source identities or require a Hermes-specific field. Help includes
plain-text/JSON examples, label repetition, Space selection, connection precedence
and failure meanings. Help and preview do not read NM configuration or invoke CLI/network.

The API response's actual `memory.id` is retained before readback. `complete`
requires the approved body/title, inherited labels, exact Space and provenance
to match subsequent official CLI / precise-ID GET reads. A successful POST echo
alone is insufficient. `partial` preserves the known ID and pending sources;
`creation_unknown` means no confirmed ID and must be investigated through the
official CLI before further writes. Neither result retries creation, falls back
to CLI creation or replaces a whole Memory with PUT.

The old plugin-local `personal_cli.py create --provenance-file ...` only wraps
that legacy provenance object as Metadata and forwards creation to this same implementation;
installed compatibility wrappers load `~/scripts/nmem-memory.py`. It is not a second creator.
The old explicit `attach` command is retained with its original metadata-only
semantics for compatibility. An authorized attempt on an existing synthetic
Memory was accepted but ignored `hermes_provenance`; its subsequent GET and
`partial` history remain valid. This create-route change does not repair that
old ID or establish a supported arbitrary Metadata update contract. Do not
repeat the old failed target without a new specific contract and authorization.
See [PHASE3 §4.1](docs/PHASE3.md)
and root [CLAUDE.md](../CLAUDE.md) for current acceptance evidence and boundaries.
Model-facing helper guidance lives directly in the personal Provider system prompt; no Skill invocation is required. Source, disk installation, loaded runtime and real-service acceptance are tracked separately. Historical failed provenance samples remain failed at their recorded versions; later successful samples do not repair those IDs.

## Tests and boundaries

```bash
# Run from this repository root; keep the Hermes PM interpreter and canonical runner.
mkdir -p temp-r3-personal/runner
for name in test_personal test_security test_r3_provider test_r3_thread test_http test_nm_wiring test_memory_create_api; do
  ln -sfn "$PWD/nowledge-mem-hermes/personal_tests/$name.py" "temp-r3-personal/runner/$name.py"
done
HERMES_PYTHON="$PWD/../hermes-secretary/.venv/bin/python" \
  PYTHONPATH="$PWD/../hermes-secretary" \
  ../hermes-secretary/scripts/run_tests.sh "$PWD/temp-r3-personal/runner/" -q
```

The ignored source symlinks avoid pytest treating the hyphenated plugin directory as an importable package; each test still resolves its original source location. The canonical runner isolates each file in its own process. Select affected files or node IDs for normal maintenance rather than repeating the whole suite. Tests use synthetic clients or disposable loopback HTTP, real Hermes SessionDB, canonical History and MemoryManager where appropriate. Runtime databases live in this checkout's ignored `temp-r3-personal/` tree; they do not access a real profile or NM account. Other upstream suites are not the personal policy contract. [docs/TEST_REPORT.md](docs/TEST_REPORT.md) is historical baseline evidence only; current versions and effective evidence are indexed in root [CLAUDE.md](../CLAUDE.md).

公共History由 **EdgarZhong/hermes-secretary** 的新版 `conversation_history` 承担，原生 `session_search` 保留。本插件不monkey-patch Core工具；旧PHASE3的session_search改造计划已撤销。

Acceptance and deployment records are indexed in root [CLAUDE.md](../CLAUDE.md) and the
[Secretary operations log](../../hermes-secretary/docs/operations-log.md). An ordinary host
run may auto-sync Threads; always select a local fixture endpoint for isolated development.
The native finalizer admits only completed, uninterrupted, nonfailed turns; public host
verdict wiring belongs to Secretary. No sample establishes global exactly-once delivery.
