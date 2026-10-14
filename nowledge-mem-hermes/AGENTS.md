# Personal Hermes NM Provider

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
