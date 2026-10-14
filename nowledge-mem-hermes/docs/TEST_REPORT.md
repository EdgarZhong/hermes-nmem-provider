# Personal Hermes 0.6.0 — Final test report

Recorded from completed GitHub Actions runs, not a planned result. Date: 2026-10-14.

## Tested revision and execution evidence

Final tested source/test revision: `41466f152d0c2b647f557915d3a9ef0080188273`.

| Execution | Result | Evidence |
| --- | --- | --- |
| Personal policy + local HTTP fixture suite, Linux Python 3.12 | **53 tests, all passed** | [Run 38497930321](https://github.com/EdgarZhong/hermes-nmem-provider/actions/runs/38497930321) |
| Retained upstream helper tests + fork release/registration assertions, Linux Python 3.11 | Passed; Windows-only cases skipped on Linux | [Linux job 115637867548](https://github.com/EdgarZhong/hermes-nmem-provider/actions/runs/38497930347/job/115637867548) |
| Personal policy suite + Bash installer, Linux Python 3.11 | **53 policy tests passed; installer passed** | Same Linux job |
| Retained upstream helper tests + fork release/registration assertions, Windows Python 3.11 | Passed, including Windows client cases | [Windows job 115637867721](https://github.com/EdgarZhong/hermes-nmem-provider/actions/runs/38497930347/job/115637867721) |
| Personal policy suite + native PowerShell installer, Windows Python 3.11 | **53 policy tests passed; installer passed** | Same Windows job |
| Inherited repository endpoint validator | Passed | [Run 38497930213](https://github.com/EdgarZhong/hermes-nmem-provider/actions/runs/38497930213) |

The same 53 policy tests execute on multiple platforms; these are not claimed as 159 distinct scenarios. The 49-test first delivery report is superseded by this report.

## What actually ran

The policy tests import the retained upstream `client.py`, `provider.py` and `skill_outcome.py` helpers. The real fork registration entry point is checked to expose exactly one native Provider and no duplicate general-hook sync. Coverage includes:

- Main, independent cron, Noting, delegate/subagent, review and unknown-source policy boundaries.
- Static Bundle loading, `include_working_memory=false`, no Working Memory fallback, and frozen context reuse.
- Short Chinese input; bounded, intact-ID candidate indexes; duplicate candidates; no Memory-body injection; timeout/empty-result reminder behavior; no stale result substitution.
- No `nmem_*` model-tool schemas, no queue-prefetch calls or built-in MD mirroring.
- Thread incremental writes, acknowledged cursors, restart, retry after failed upload, session switch, canonical compaction-history fixtures and refusal of rewritten archive prefixes.
- Metadata preview without NM I/O, source-identity validation boundaries, explicit create/update preconditions, preservation of unrelated metadata and content/metadata readback verification.
- Batch transfer into Hermes' host egress scrubber; missing scrubber fails closed for direct canonical-history export.
- Actual localhost HTTP requests, Space/identity query transport, credential headers, redirects refused without forwarding credentials, response streams closed, and inherited import/append payload shapes.
- Installer preview, configuration preservation, backup, repeat install, conflicting-provider refusal, retained MD files and installed module/skill completeness. Bash and native Windows PowerShell launchers are exercised in disposable homes.

## Test-double boundaries

Hermes' host ABC, canonical History Foreground and egress handoff are mocked in the isolated policy suite. The batch egress tests verify the whole transcript is handed to the host boundary; they do not claim to validate Hermes' real redaction algorithm. NM writes and Memory responses use controlled fixtures. The HTTP transport suite makes real requests to a disposable local HTTP server, **not a live NM Server**.

Upstream tests for the retained helper implementation remain enabled. Three inherited assertions were revised for the approved fork contract: version `0.6.0`, no `post_llm_call` fallback, and absence of a secondary fallback Provider. The installer tests now test this fork's explicit-home installer rather than the retired upstream downloader. No production defect was hidden by deselecting those tests.

An earlier Windows run found unclosed SQLite handles in the *test fixture*; the fixture now explicitly closes its connection. The rerun shown above passed. HTTP error response handles were also closed explicitly after the initial resource warning.

## Delivery boundary and known limitations

- No running user Hermes profile or real NM account was accessed or changed. No real Memory was written, no Background Intelligence setting was changed, and no package or marketplace publication was performed.
- Live Hermes Agent-loop + NM Server end-to-end acceptance is **not performed**. In particular, live NM metadata write semantics, host Context Bundle refresh and actual runtime-scope behavior still require deployment verification.
- `personal_cli.py --apply` is an explicit write switch, not an authenticated user-approval token. The existing Secretary approval flow must authorize invocation. Source existence checks do not prove the prose is logically entailed by the evidence.
- Update preconditions detect stale reads but are not server-atomic compare-and-swap. This helper is designed for the user's single-writer setup.
- Thread transport uses acknowledged, retryable delivery with server deduplication; exactly-once delivery is not claimed.
- Changing already-archived history through rewind/edit causes a reconciliation-required stop. Automatic remote deletion or replacement of those earlier archive rows is not implemented.
- Thread capture is normalized user/assistant prose and timestamps, not a full tool/multimodal execution trace. Hermes original history remains authoritative.
- macOS-specific deployment was not run; Linux and Windows automated checks above passed.
- The separately agreed `session_search` Core redesign is specified in PHASE3.md but **not implemented in this Provider repository**. No Agent Core monkey patch was introduced.

The temporary write-enabled delivery/migration workflows removed themselves or were deleted after use. Ongoing Provider and regression workflows are read-only and do not deploy or alter real NM data.
