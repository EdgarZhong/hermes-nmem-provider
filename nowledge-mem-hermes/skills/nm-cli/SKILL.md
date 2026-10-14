---
name: nm-cli
description: Read NM memory using CLI and prepare user-approved writes carrying Hermes evidence metadata.
---

# Personal Hermes NM workflow

Use this for explicit memory maintenance, not as a mandatory preflight on every turn.

Read with `nmem --json m search QUERY -n 5`, then `nmem --json m show ID` when the full fact is needed. Candidate titles are pointers, not verified knowledge. Read original Hermes evidence with session_history (current Conversation) or the authorized cross-Conversation history tool. Never invent or shorten source IDs.

NM Background Intelligence stays off. Do not run automatic distill/dreaming, rewrite Context Bundle, or mirror MD files. Noting candidates are not approval. The main Secretary conversation reviews the original evidence and requests approval before a durable mutation.

Store source identities in `metadata.hermes_provenance` using version 1 and an array of exact `{conversation_ref, message_uid}` sources. Keep the Memory content free of IDs. Do not populate NM-native source_thread_id using a Hermes Conversation Ref.

The installed `personal_cli.py write --input FILE` only previews. After the existing approval, `--history-home HERMES_HOME --apply` verifies host source identities, writes, and checks readback. Use an explicit retry-stable Memory ID. To update, first `personal_cli.py read ID`, then supply `--update --expected-sha` from that read. The helper cannot authenticate human approval or atomically lock the NM Server; do not treat flags as permission.

Do not independently capture threads: the Provider's sync_turn already archives admitted main conversations and standalone cron main Sessions. Do not invoke queue_prefetch or add a second sync hook.
