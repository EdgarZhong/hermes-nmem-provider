"""Personal Hermes: one native NM Memory Provider, no duplicate general-hook sync."""
from pathlib import Path
from .personal_provider import PersonalNowledgeMemProvider


def register(ctx):
    if hasattr(ctx, "register_memory_provider"):
        ctx.register_memory_provider(PersonalNowledgeMemProvider())
        if hasattr(ctx, "register_skill"):
            ctx.register_skill("nm-cli", Path(__file__).parent / "skills" / "nm-cli" / "SKILL.md",
                               "Read NM via CLI and prepare approved memory changes")
    # General-plugin discovery can visit the same directory. Deliberately no fallback
    # post_llm_call hook: it lacks reliable scope and would double-capture native turns.
