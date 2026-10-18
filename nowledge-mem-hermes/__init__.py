"""Personal Hermes: one native NM Memory Provider, no duplicate general-hook sync."""
from .personal_provider import PersonalNowledgeMemProvider


def register(ctx):
    if hasattr(ctx, "register_memory_provider"):
        ctx.register_memory_provider(PersonalNowledgeMemProvider())
    # General-plugin discovery can visit the same directory. Deliberately no fallback
    # post_llm_call hook: it lacks reliable scope and would double-capture native turns.
