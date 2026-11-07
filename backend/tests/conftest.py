"""Tests never call a real model, whatever LLM_MODE the developer's .env file sets."""

import os

# An environment variable wins over the .env file, and this runs before any test imports settings.
os.environ["LLM_MODE"] = "fake"
