"""DocEvidencePack: the output artifact of a doc-sync run.

Vendored from rlm-docsync. Each pack has a SHA-256 hash chain so
consumers can verify no entries were tampered with or reordered.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .claims import ClaimResult
from .sanitization import _sha256_text as _sha256


@dataclass
class DocEvidencePack:
    """Immutable evidence pack produced by a doc-sync run."""

    manifest_hash: str
    runner: str = "guardspine-docs-action"
    runner_version: str = "1.0.0"
    timestamp: str = ""
    results: list[ClaimResult] = field(default_factory=list)
    hash_chain: list[str] = field(default_factory=list)
    immutability_proof: dict[str, Any] = field(default_factory=dict)
    sanitization: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = (
                datetime.now(timezone.utc)
                .isoformat(timespec="seconds")
            )

    def build_hash_chain(self) -> list[str]:
        """Build canonical proof and update hash_chain."""
        links: list[dict[str, Any]] = []
        previous_hash = "genesis"

        for idx, result in enumerate(self.results):
            item_id = f"claim-{idx:04d}"
            content_type = "guardspine/docsync-claim"
            content = result.to_dict()
            content_json = json.dumps(content, sort_keys=True, separators=(",", ":"))
            content_hash = _sha256(content_json)
            chain_input = (
                f"{idx}|{item_id}|{content_type}|{content_hash}|{previous_hash}"
            )
            chain_hash = _sha256(chain_input)
            links.append({
                "sequence": idx,
                "item_id": item_id,
                "content_type": content_type,
                "content_hash": content_hash,
                "previous_hash": previous_hash,
                "chain_hash": chain_hash,
            })
            previous_hash = chain_hash

        concatenated = "".join(link["chain_hash"] for link in links)
        root_hash = _sha256(concatenated)
        self.immutability_proof = {"hash_chain": links, "root_hash": root_hash}
        self.hash_chain = [link["chain_hash"] for link in links]
        return self.hash_chain

    def to_json(self, indent: int = 2) -> str:
        if not self.hash_chain:
            self.build_hash_chain()
        items = []
        for idx, result in enumerate(self.results):
            item_content = result.to_dict()
            content_json = json.dumps(item_content, sort_keys=True, separators=(",", ":"))
            items.append({
                "item_id": f"claim-{idx:04d}",
                "sequence": idx,
                "content_type": "guardspine/docsync-claim",
                "content": item_content,
                "content_hash": _sha256(content_json),
            })
        payload: dict[str, Any] = {
            "version": "1.0.0",
            "manifest_hash": self.manifest_hash,
            "runner": self.runner,
            "runner_version": self.runner_version,
            "timestamp": self.timestamp,
            "items": items,
            "immutability_proof": self.immutability_proof,
            "results": [r.to_dict() for r in self.results],
            "hash_chain": self.hash_chain,
        }
        return json.dumps(payload, indent=indent, sort_keys=False)

    def verify(self) -> tuple[bool, str]:
        """Verify hash chain integrity. Returns (True, "ok") or (False, reason)."""
        if not self.hash_chain:
            if not self.results:
                return True, "ok"
            self.build_hash_chain()

        if len(self.hash_chain) != len(self.results):
            return False, (
                f"chain length ({len(self.hash_chain)}) != "
                f"results length ({len(self.results)})"
            )
        prev = "genesis"
        for i, result in enumerate(self.results):
            content = result.to_dict()
            content_json = json.dumps(content, sort_keys=True, separators=(",", ":"))
            item_id = f"claim-{i:04d}"
            content_type = "guardspine/docsync-claim"
            content_hash = _sha256(content_json)
            expected = _sha256(f"{i}|{item_id}|{content_type}|{content_hash}|{prev}")
            if i >= len(self.hash_chain):
                return False, f"chain too short at index {i}"
            if self.hash_chain[i] != expected:
                return False, (
                    f"hash mismatch at index {i}: "
                    f"expected {expected}, got {self.hash_chain[i]}"
                )
            prev = expected
        return True, "ok"
