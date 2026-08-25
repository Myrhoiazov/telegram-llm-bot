"""Shared inference error type."""
from __future__ import annotations


class InferenceError(Exception):
    """Raised when text generation fails for any reason."""
