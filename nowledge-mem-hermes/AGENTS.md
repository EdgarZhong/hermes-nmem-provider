# Personal Hermes NM Provider

The user's confirmed Phase 3 architectural decisions override inherited upstream behavioral guidance. docs/PHASE3.md distinguishes confirmed user requirements from Existing code, Target contracts, and expressly labeled engineering convergences awaiting user review; do not treat those convergences as earlier user approvals.

- Keep one Memory Provider. Do not add MCP or nmem_* model tools.
- NM Background Intelligence stays OFF; no automatic distillation or proactive Memory writes.
- Main conversations: static Context Bundle without Working Memory, turn-start candidates, thread sync.
- Standalone cron main Sessions: thread sync only. Noting/delegate/subagent/review/other backgrounds: none.
- Preserve upstream client/provider helpers. Personal policy lives in personal_*.py, registered from __init__.py.
- Original Hermes evidence is addressed by (conversation_ref, message_uid), stored in metadata.hermes_provenance.
- Respect existing Secretary approval. The CLI --apply flag is not an authorization capability.
- Run python3 -m unittest discover -s nowledge-mem-hermes/personal_tests -v.
- Do not modify user profiles, real NM data, other integrations or publish registries during tests.
- History implementation and tool exposure are distinct. `session_history` retains the existing 02/04 **mandatory eligible-Main** injection and dedicated Noting Parent-only access; other lawful native exposure is untouched. `session_search` is NOT force-injected into Main: retain its **native** `session_search` toolset, platform defaults, `platform_toolsets`, per-session selections, `agent.disabled_toolsets`, and registered check_fn; replace only the same registered Schema/Handler and existing tool-aware `SESSION_SEARCH_GUIDANCE` text (docs/PHASE3.md §§0.6, 3.2–3.15). Noting/NM on/off never switches implementation semantics or forces Search availability. Do not extend Noting Child cross-Conversation rights.
- Phase 3 `session_search` is a **reuse-first enhancement of Hermes's existing search engine**: preserve native FTS5/CJK/LIKE, native ranking, hidden-source Discovery/Browse, physical lineage dedup, current-live-context suppression, Cron demotion, native toolset/check_fn/profile selection, bounded Browse and existing direct Session read scope. Add a thin result/identity projection only: eligible genuine user Main → `kind=conversation` with canonical `(conversation_ref,message_uid)`; original native-visible Cron/other non-user execution → `kind=session` with physical `(session_id,message_id)` read locator (not personal Provenance). Never mint a Cron Conversation Ref or add a new search engine/index/tool. Golden before/after native candidate visibility and rank fixtures are required (docs/PHASE3.md §§0.7–0.8, 3, 5.2).
- `session_search` code/Schema/Prompt changes belong in the separate Secretary Core repository; this plugin does not monkey-patch them.
