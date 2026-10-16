---
name: nm-cli
description: Use official nmem for memory management; create approved Memories with exact Hermes provenance through the narrow helper.
---

# Personal Hermes NM workflow

Use this for explicit memory maintenance, not mandatory preflight on every turn.
Read with `nmem --json m search QUERY -n 5`, then `nmem --json m show ID` when
needed. Candidate titles are pointers, not verified facts. Read original Hermes
evidence with `conversation_history` within its authorized scope. Never invent
or shorten `(conversation_ref, message_uid)` or substitute physical Session/row
IDs or NM Thread IDs. Main must check corrections and actual support in the
originals; the helper only checks the supplied provenance's JSON shape.

Only Main executes specifically user-approved content and destination. A
Candidate, `/propose-persistence`, capacity notice, available credential or
`--apply` is not approval. Preserve inherited content labels as
`notebook:<type>` through official CLI label fields (map `implicit_gap` to
`situation`). Direct-message material needs no invented Notebook ancestry.
Keep opaque source IDs out of the natural-language Memory body and out of
NM-native `source_thread_id` / Message provenance fields.

## New Memory: official creation, then metadata only

Use `personal_cli.py` from this plugin's checkout or installed plugin directory;
do not copy a development machine's path or connection file. Prepare an
approved UTF-8 body file and a provenance JSON file with this structure. Values
below are illustrative: supply the complete real Hermes identities.

```json
{"version":1,"sources":[{"conversation_ref":"conv_example","message_uid":"uid_example"}]}
```

From the plugin directory, preview first (no CLI/network calls):

```bash
python3 personal_cli.py create --content-file approved.md --provenance-file provenance.json --title 'Approved understanding' --label 'notebook:situation'
```

After specific approval, repeat with `--apply`. Main supplies the exact body,
title, labels and sources; the helper does not rewrite or infer them. It invokes
a native official executable using an argument array, equivalent to:

```text
nmem --json --api-url <resolved-host-url> [--space <selected-space>] m add --stdin --source hermes-secretary [--title <title>] [-l <label> ...]
```

The body is passed as UTF-8 stdin bytes, not a shell command or command-line
argument. Each input file is limited to 256 KiB. The helper never passes a
caller-chosen Memory ID to creation. Only exit 0 and a valid top-level JSON `id`
confirm the ID, matching the official CLI JSON example. No text scraping,
nested-ID guessing, automatic create retry, HTTP Memory creation, body editing,
History membership check, expected-SHA protocol or full write/readback cycle.
The old helper `read` / `write` / `--update` commands are removed, not aliases.

Connection uses the existing client's host env/config/default resolution.
`--api-url` **before** `create` or `attach` is the official-style one-off override;
otherwise `NMEM_API_URL`, `NMEM_API_KEY` and the host's shared NM config apply.
The resolved URL/key are frozen in memory and supplied to both CLI and HTTP;
keys are only in subprocess environment / HTTP headers, never output or argv.
No helper-specific connection file is added. Remote means the same selected
remote URL, not a second local service. `create --space` is passed to official
CLI; ambient Space configuration remains intact. Attachment addresses the exact
returned ID without moving it between Spaces. Use the **same destination** when
repairing, including any one-off URL override.

Native executables are supported; `.cmd` / `.bat` shims are rejected before
creation rather than passing approved text through a command shell. Install or
select a native official executable for such a host; this is not a tested
Windows-bundled-shim route. There is no automatic installation.

## Outcomes and repair

The final stdout line is JSON. After confirmed creation, an additional JSON
receipt with the real ID is flushed to stderr **before** metadata attachment.
Retain that ID in the normal Conversation trajectory. Raw CLI/server output,
Memory body and credentials are never echoed by the helper.

| Status | Meaning / action |
|---|---|
| `preview` (exit 0) | No CLI/network calls and no writes. |
| `complete` (exit 0) | Metadata was already present or its HTTP request was acknowledged; not an independent storage verification. |
| `failed` (exit 1) | Input/preparation failure before the CLI call; no creation attempt. |
| `partial` (exit 2) | The known ID remains; metadata is unconfirmed. Repair only that ID, never create again. |
| `creation_unknown` (exit 3) | CLI invocation/communication error, timeout, interruption, nonzero exit or unsupported JSON. No ID guessed and no metadata attempted. Inspect with official CLI before any further write. |

For `partial`, keep the same provenance file and exact returned ID:

```bash
python3 personal_cli.py attach ACTUAL_RETURNED_ID --provenance-file provenance.json
# Apply the same previously approved attachment; this never calls m add:
python3 personal_cli.py attach ACTUAL_RETURNED_ID --provenance-file provenance.json --apply
```

The narrow HTTP step reads the existing Memory and PATCHes only a `metadata`
object with `hermes_provenance` merged into the metadata it read. Unrelated
metadata from that read is retained. Repeating an identical attachment is a
no-op. This read/modify/write has no server CAS: concurrent metadata edits can
race, so do not run competing metadata writers. The two creation/attachment
steps are **not atomic**. `http_acknowledged` does not claim full readback or
end-to-end validation; a failed response may still mean a PATCH was applied.
If a process is killed before it can emit any receipt, investigate with official
CLI instead of blind creation retry.

## Other operations and deferred checks

Normal search, read, edit, delete and management use official `nmem` directly;
consult its help instead of expanding this helper. Do not independently capture
Threads: admitted completed-Turn archival belongs to the single Provider. NM
Background Intelligence remains off by operator policy; do not enable automatic
distillation, add a second sync hook, or rewrite owner-governed Bundle/Policy.

Round 3 local basic simulated call checks passed on 2026-10-17. Checks are limited to syntax,
arguments, simulated creation JSON and call ordering: preview makes no calls;
create happens once; failed/ambiguous create never PATCHes; failed attachment
retains ID; repair never creates; unrelated metadata is retained; CLI/HTTP share
the selected host connection and diagnostics contain no credentials. No strict
independent suite or real NM test writes are authorized. The isolated
`parse_created_id` and `attach_metadata` contracts need the local basic check
against the actual deployed host CLI/server in the later authorized deployment; unsupported shapes must not be guessed. No actual NM service was contacted.

Official CLI references reviewed for this code-only change:
https://mem.nowledge.co/docs/cli (JSON output uses `.id`; stdin, labels and
connection options), and https://pypi.org/project/nmem-cli/0.9.20/ (shared host
configuration priority). No official CLI or live NM command was executed.
