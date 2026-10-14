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
- `session_history` and redesigned `session_search` are permanent Secretary Core History/Provenance capabilities for eligible Main Conversations, independent of global/local Noting and NM availability. Noting-off does NOT restore legacy physical Session search. `session_history` keeps the frozen 02 contract; the one canonical `session_search` Schema and native Search System Prompt replacement are targets in docs/PHASE3.md §§3.2–3.15. Noting Child remains Parent-history-only; no auxiliary cross-Conversation privilege expansion.
- `session_search` code/Schema/Prompt changes belong in the separate Secretary Core repository; this plugin does not monkey-patch them.
