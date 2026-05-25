"""Hermes plugin entrypoint for LearnBuddy.

This is a pre-alpha placeholder. Production family-specific plugins must not be
copied here verbatim; extract generic, tested pieces only.
"""
from __future__ import annotations

PLUGIN_NAME = "learnbuddy-learning"
PLUGIN_VERSION = "0.1.0-alpha.0"


def register(ctx):  # pragma: no cover - depends on Hermes plugin runtime
    """Register tools with Hermes once the public plugin API is finalized."""
    # Intentionally empty for the initial repository scaffold.
    # Next step: add bounded tools using the current Hermes PluginContext API.
    return None
