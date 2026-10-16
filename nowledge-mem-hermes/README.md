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

Use Python from your Hermes environment (`PyYAML` is required by the installer). Do not run the upstream curl installer, which would replace this fork with upstream policy.

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

`system_prompt_block()` requests `/context/bundle?include_working_memory=false` and never falls back to `wm read`. Bundle contents are frozen per logical Conversation in the provider instance; a reset or new instance can obtain a fresh Bundle at the host's next actual root-prompt build. Noting may inherit the parent's already-frozen prompt under the existing cache-parity contract; it does not independently run this Provider.

`prefetch()` performs normal `nmem --json m search`, including short Chinese queries. It returns only intact IDs, titles and available dates, plus a context-sufficiency reminder. It does not inject full Memory bodies, reuse stale query results, or report candidates as memories already read. Host trivial-prompt skipping and historical `api_content` replay are unchanged.

## Thread capture and recovery

The modern Hermes `MemoryManager` runs `sync_turn()` on its serialized background worker. This fork relies on that host contract, as the current official synchronous sync implementation does; older hosts that invoke it inline are not supported for latency guarantees. Do not register a second `post_llm_call` fallback.

Interactive Secretary sessions use a **read-only** existing `secretary_session_bindings` lookup and the host's canonical History Foreground. Physical compaction continuations with the same Conversation Ref share an archive. No new Secretary identity is minted. Ordinary Hermes and standalone cron use their own Session identity. Thread IDs are namespaced `hermes-personal-<identity>` so the fork does not overwrite archives produced by the old integration.

Only user/assistant prose and normalized timestamps are archived. Tool results, hidden/Noting scaffolding and recognized compaction summaries are excluded. This is **not a full tool/multimodal execution trace**. Hermes `state.db` remains authoritative and must be backed up.

Acknowledged transcript fingerprints are stored under `$HERMES_HOME/nowledge-mem-personal/receipts.sqlite3`; no transcript bodies or credentials are stored there. Successful acknowledgements advance the cursor. Failures leave it unchanged; subsequent turns/session-end or resuming the conversation retry. HTTP timeout after server commit can still cause an at-least-once retry; server append deduplication is reused, and exactly-once delivery is not claimed.

An edit/rewind that changes an already-archived prefix is deliberately **not silently appended or overwritten**. Sync logs a reconciliation-required failure; explicit archive reconciliation is a deployment operation, not yet implemented here. Unsupported combined summary/user carriers on non-Secretary hosts are not claimed lossless. Scope failures deny that observation rather than guess. Independent cron sync is allowed, but cron children remain excluded.

## 现有旧helper：Hermes Provenance in Memory metadata

此节描述尚未替换的代码。第三轮目标为官方CLI创建后仅补写Metadata，见[PHASE3现行§4.1](docs/PHASE3.md)；不据以下旧命令继承完整写入协议。

Use `metadata.hermes_provenance`, not prose suffixes or NM-native Thread fields:

```json
{
  "id": "an-explicit-retry-stable-memory-id",
  "title": "Approved decision",
  "content": "The actual durable knowledge, without provenance identifiers.",
  "source": "hermes-secretary",
  "metadata": {
    "hermes_provenance": {
      "version": 1,
      "sources": [
        {"conversation_ref": "<exact host value>", "message_uid": "<exact host value>"}
      ]
    }
  }
}
```

The values above are placeholders, not valid evidence. Use IDs returned by the host History tools. `personal_cli.py` is a shell command, not a registered Agent function:

```bash
# No network write; only validate and preview the payload.
python3 "$HERMES_HOME/plugins/nowledge-mem/personal_cli.py" write --input approved-memory.json
# After the existing Secretary approval, using Hermes' Python environment:
python3 "$HERMES_HOME/plugins/nowledge-mem/personal_cli.py" write --input approved-memory.json \
  --history-home "$HERMES_HOME" --apply
# Read metadata plus an edit precondition digest:
python3 "$HERMES_HOME/plugins/nowledge-mem/personal_cli.py" read MEMORY_ID
# Explicit update also requires --update --expected-sha DIGEST.
```

Applied writes verify all source UIDs against the indicated Secretary History Foreground, preserve unrelated metadata on updates, and read back content/metadata. A stable ID is required; creates refuse an existing ID. Failed readback reports an ambiguous write and does not automatically repeat it. PATCH preconditions are client-side stale-read detection, **not server-atomic compare-and-swap**. Only use this helper under the intended single-writer policy.

`--apply` is **not** user-authentication or an approval capability. A model with unrestricted shell and NM write credentials can bypass prompts; enforce hard isolation outside this helper when needed. The helper verifies source existence, not whether the prose logically follows from the source; the main conversation remains responsible for that review.

## Tests and boundaries

```bash
python3 -m unittest discover -s nowledge-mem-hermes/personal_tests -v
```

These tests load the retained upstream Provider/client helpers with a minimal Hermes ABC fixture, and use fake NM clients plus a disposable local HTTP server. They do not access a real profile or NM account. The upstream suite targets the old policy and is retained for reference; the new policy is tested separately. See [docs/TEST_REPORT.md](docs/TEST_REPORT.md) for actual execution evidence and remaining live acceptance.

公共History由 **EdgarZhong/hermes-secretary** 的新版 `conversation_history` 承担，原生 `session_search` 保留。本插件不monkey-patch Core工具；旧PHASE3的session_search改造计划已撤销。
