"""Minimal sanitization utilities vendored from rlm-docsync.

Only _sha256_text is needed by the docs action (no PII-Shield integration).
"""

from __future__ import annotations

import hashlib


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
